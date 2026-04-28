"""Claude 對話引擎（含工具呼叫迴圈 + Prompt Caching + 文件分析）"""
import re
import base64
import io
import logging

import db
from config import anthropic_client, CLAUDE_MODEL, CLAUDE_MODEL_LIGHT
from prompts import (
    SYSTEM_PROMPT, SYSTEM_PROMPT_CORE, SYSTEM_PROMPT_TOOLS_GUIDE,
    build_date_block, build_profile_block,
)
from features.tools import TOOLS, dispatch_tool

logger = logging.getLogger("lumio.chat")

# PDF 處理門檻
_PDF_INLINE_MAX = 4 * 1024 * 1024   # ≤ 4MB → 直接送 Claude（保留排版/表格）
_FILE_SIZE_MAX  = 20 * 1024 * 1024  # > 20MB → 拒絕

# 長文件分段門檻（單次摘要送 Claude 的字元上限）
_SINGLE_PASS_LIMIT = 15000
# 分段時每段大小（字元），預留 prompt 額外字數空間
_CHUNK_SIZE = 12000

_SUMMARIZE_PROMPT = (
    "請用繁體中文摘要這份文件「{filename}」的重點內容。\n"
    "格式：\n"
    "①一句話總結\n"
    "②主要重點（條列）\n"
    "③需要注意或後續行動的事項（如有）\n\n"
    "語氣溫暖專業，如同秘書幫老闆整理會議前必讀摘要。"
)

_SUMMARIZE_TEMPLATE = _SUMMARIZE_PROMPT + "\n\n文件內容：\n{content}"

# Anthropic 定價參考（USD / 1M tokens），按模型查表
_PRICE_TABLE: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6":              {"in": 3.0, "cache_write": 3.75, "cache_read": 0.30, "out": 15.0},
    "claude-haiku-4-5-20251001":      {"in": 1.0, "cache_write": 1.25, "cache_read": 0.10, "out":  5.0},
}
_PRICE_DEFAULT = _PRICE_TABLE["claude-sonnet-4-6"]

# 工具呼叫迴圈上限（複雜任務可能跨 4-5 輪）
_MAX_TOOL_TURNS = 6

# 兩段式 system cache：
# - CORE 區塊（人格/格式規則）極少改動，命中率最高
# - TOOLS_GUIDE 區塊（工具指引）變動較頻繁，獨立 cache key
# Anthropic 允許多個 cache_control，每個都會建立 cache breakpoint。
_CACHED_SYS_CORE = {
    "type": "text", "text": SYSTEM_PROMPT_CORE,
    "cache_control": {"type": "ephemeral"},
}
_CACHED_SYS_TOOLS = {
    "type": "text", "text": SYSTEM_PROMPT_TOOLS_GUIDE,
    "cache_control": {"type": "ephemeral"},
}
# 短任務（PDF 摘要 / 公文 / 會議紀錄）只需 CORE（人格與格式），不需工具指引
_CACHED_SYS_BLOCK = _CACHED_SYS_CORE


def _with_cache(items: list[dict]) -> list[dict]:
    """於序列最後一個元素加 cache_control，避免綁定特定索引"""
    if not items:
        return items
    return [*items[:-1], {**items[-1], "cache_control": {"type": "ephemeral"}}]


# 靜態工具列表 cache（約 2000 token，5 分鐘 TTL）
_TOOLS_CACHED = _with_cache(TOOLS)


def _build_system(user_id: str = "") -> list[dict]:
    """完整對話用 system：
    - CORE cache block（人格/格式，極少改動）
    - TOOLS_GUIDE cache block（工具指引，可獨立更新）
    - 使用者長期記憶區塊（變動低；不額外 cache）
    - 動態日期區塊（每次重算）
    """
    blocks: list[dict] = [_CACHED_SYS_CORE, _CACHED_SYS_TOOLS]
    if user_id:
        try:
            facts = db.profile_list(user_id)
        except Exception as e:
            logger.warning(f"讀取 profile 失敗: {e}")
            facts = []
        profile_text = build_profile_block(facts)
        if profile_text:
            blocks.append({"type": "text", "text": profile_text})
    blocks.append({"type": "text", "text": build_date_block()})
    return blocks


def _cache_history_tail(messages: list[dict]) -> list[dict]:
    """對話歷史最後一則訊息之最後 content block 加 cache breakpoint。"""
    if not messages:
        return messages
    last = dict(messages[-1])
    content = last["content"]
    if isinstance(content, str):
        content = [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
    elif isinstance(content, list) and content:
        content = [*content[:-1], {**content[-1], "cache_control": {"type": "ephemeral"}}]
    last["content"] = content
    return [*messages[:-1], last]


def _log_usage(usage, call_n: int, model: str = CLAUDE_MODEL, user_id: str = "") -> None:
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    # input_tokens 已扣掉 cache_read（Anthropic 規範），但保險起見 max(0, …)
    regular_in = max(0, usage.input_tokens - cache_read)
    price = _PRICE_TABLE.get(model, _PRICE_DEFAULT)
    cost = (
        regular_in * price["in"] +
        cache_write * price["cache_write"] +
        cache_read * price["cache_read"] +
        usage.output_tokens * price["out"]
    ) / 1_000_000
    logger.info(
        f"Claude #{call_n} model={model} in={usage.input_tokens} cache_write={cache_write} "
        f"cache_read={cache_read} out={usage.output_tokens} ≈${cost:.5f}"
    )
    db.record_usage(
        user_id=user_id,
        model=model,
        input_tokens=regular_in,
        cache_write_tokens=cache_write,
        cache_read_tokens=cache_read,
        output_tokens=usage.output_tokens,
        cost_usd=cost,
    )


def simple_complete(prompt: str, max_tokens: int = 1200, with_system: bool = True,
                    model: str | None = None, user_id: str = "") -> str:
    """一次性 Claude 呼叫（無工具、無對話歷史）。
    供文件摘要、公文生成、會議紀錄整理等短任務共用。"""
    use_model = model or CLAUDE_MODEL
    kwargs: dict = {
        "model": use_model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if with_system:
        kwargs["system"] = [_CACHED_SYS_BLOCK]
    resp = anthropic_client.messages.create(**kwargs)
    _log_usage(resp.usage, 1, model=use_model, user_id=user_id)
    return strip_markdown("".join(getattr(b, "text", "") for b in resp.content))


def _split_text(text: str, chunk_size: int) -> list[str]:
    """以段落為界切分，避免硬切斷句子。"""
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    paragraphs = re.split(r"\n\s*\n", text)
    buf = ""
    for p in paragraphs:
        if not p.strip():
            continue
        candidate = (buf + "\n\n" + p) if buf else p
        if len(candidate) <= chunk_size:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
        # 單段超過 chunk_size：強制切割
        while len(p) > chunk_size:
            chunks.append(p[:chunk_size])
            p = p[chunk_size:]
        buf = p
    if buf:
        chunks.append(buf)
    return chunks


def chunked_summarize(text: str, final_prompt: str, max_tokens: int = 1500,
                      user_id: str = "") -> str:
    """長文 map-reduce 摘要：超過上限時分段先粗摘，再合成最終回應。

    final_prompt 必須含 "{content}" 佔位符，會被替換為原文（短）或階段性摘要（長）。
    """
    if len(text) <= _SINGLE_PASS_LIMIT:
        return simple_complete(final_prompt.format(content=text), max_tokens=max_tokens,
                               user_id=user_id)

    chunks = _split_text(text, _CHUNK_SIZE)
    logger.info(f"長文分段摘要：{len(text)} 字 → {len(chunks)} 段")

    partials: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        prompt = (
            f"以下是長文件第 {i}/{len(chunks)} 段，請以繁體中文擷取重點（條列、純文字、禁用 Markdown），"
            f"保留人事時地物、決議與數字：\n\n{chunk}"
        )
        partial = simple_complete(prompt, max_tokens=800, model=CLAUDE_MODEL_LIGHT,
                                  user_id=user_id)
        partials.append(f"[第 {i} 段重點]\n{partial}")

    merged = "\n\n".join(partials)
    if len(merged) > _SINGLE_PASS_LIMIT:
        merged = merged[:_SINGLE_PASS_LIMIT]
    return simple_complete(final_prompt.format(content=merged), max_tokens=max_tokens,
                           user_id=user_id)


def ask_claude(user_id: str, text: str, image_b64: str | None = None) -> str:
    content = (
        [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
            {"type": "text", "text": text or "請用繁體中文分析這張圖片"},
        ]
        if image_b64 else text
    )
    db.save_message(user_id, "user", content)
    messages = _cache_history_tail(db.get_history(user_id))
    system = _build_system(user_id=user_id)

    response = anthropic_client.messages.create(
        model=CLAUDE_MODEL, max_tokens=1000,
        system=system, tools=_TOOLS_CACHED, messages=messages,
    )
    _log_usage(response.usage, 1, model=CLAUDE_MODEL, user_id=user_id)

    # 最多 6 輪 tool use（複雜任務如「查行程→比對空檔→新增提醒」可能需 4-5 輪）
    for i in range(_MAX_TOOL_TURNS):
        if response.stop_reason != "tool_use":
            break
        tool_results = [
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": dispatch_tool(block.name, block.input, user_id=user_id),
            }
            for block in response.content if block.type == "tool_use"
        ]
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
        response = anthropic_client.messages.create(
            model=CLAUDE_MODEL, max_tokens=1000,
            system=system, tools=_TOOLS_CACHED, messages=messages,
        )
        _log_usage(response.usage, i + 2, model=CLAUDE_MODEL, user_id=user_id)
        if response.stop_reason == "tool_use" and i == _MAX_TOOL_TURNS - 1:
            logger.warning(f"tool-use 達到上限 {_MAX_TOOL_TURNS} 輪，強制結束")

    reply = "".join(getattr(b, "text", "") for b in response.content)
    reply = strip_markdown(reply or "抱歉，我暫時無法回應，請再試一次～")
    db.save_message(user_id, "assistant", reply)
    return reply


def analyze_file(user_id: str, file_bytes: bytes, filename: str) -> str:
    """分析上傳的文件（PDF / 純文字），回傳摘要並存入對話記憶"""
    size_mb = len(file_bytes) / 1024 / 1024
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    logger.info(f"文件分析 {filename} ({size_mb:.1f}MB)")

    if len(file_bytes) > _FILE_SIZE_MAX:
        return f"⚠️ 檔案太大（{size_mb:.1f}MB），目前支援 20MB 以下的文件"

    try:
        if ext == "pdf":
            reply = _analyze_pdf(file_bytes, filename, user_id=user_id)
        else:
            text = file_bytes.decode("utf-8", errors="replace")
            reply = chunked_summarize(
                text,
                _SUMMARIZE_TEMPLATE.replace("{filename}", filename),
                max_tokens=1500,
                user_id=user_id,
            )
    except Exception as e:
        logger.exception(f"文件分析失敗: {e}")
        return f"⚠️ 文件分析失敗：{e}"

    db.save_message(user_id, "user", f"[📄 上傳文件：{filename}（{size_mb:.1f}MB）]")
    db.save_message(user_id, "assistant", reply)
    return reply


def _analyze_pdf(file_bytes: bytes, filename: str, user_id: str = "") -> str:
    if len(file_bytes) <= _PDF_INLINE_MAX:
        # 小檔案：直接送 Claude，保留完整排版與圖表理解能力
        pdf_b64 = base64.b64encode(file_bytes).decode()
        content = [
            {"type": "document",
             "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
            {"type": "text", "text": _SUMMARIZE_PROMPT.format(filename=filename)},
        ]
        resp = anthropic_client.messages.create(
            model=CLAUDE_MODEL, max_tokens=1500,
            system=[_CACHED_SYS_BLOCK],
            messages=[{"role": "user", "content": content}],
        )
        _log_usage(resp.usage, 1, model=CLAUDE_MODEL, user_id=user_id)
        return strip_markdown("".join(getattr(b, "text", "") for b in resp.content))

    # 大檔案：pypdf 提取文字再送 Claude（必要時自動分段摘要）
    text = _extract_pdf_text(file_bytes)
    if not text.strip():
        return "⚠️ 無法提取 PDF 文字（可能是純圖片掃描版），請傳送可選取文字的 PDF"
    return chunked_summarize(
        text,
        _SUMMARIZE_TEMPLATE.replace("{filename}", filename),
        max_tokens=1500,
        user_id=user_id,
    )


# PDF 解析硬上限：避免單檔耗盡記憶體
_PDF_MAX_PAGES = 60          # 上限頁數（超過僅取前 N 頁）
_PDF_MAX_TEXT_CHARS = 200000 # 累積字元上限（避免極端密文 PDF 爆量）


def _extract_pdf_text(file_bytes: bytes) -> str:
    """逐頁提取 PDF 文字，含頁數與字元雙重上限保護。

    若超過 _PDF_MAX_PAGES 或 _PDF_MAX_TEXT_CHARS 即停止，並於文末加註提示。
    """
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except PdfReadError as e:
        logger.warning(f"PDF 解析失敗（可能加密或損毀）: {e}")
        return ""

    total_pages = len(reader.pages)
    pages: list[str] = []
    accum_chars = 0
    truncated_by = ""
    last_index = -1

    for i in range(min(total_pages, _PDF_MAX_PAGES)):
        last_index = i
        try:
            t = reader.pages[i].extract_text() or ""
        except Exception as e:
            # 單頁失敗不應中斷整體（PDF 內混壞頁是常見情況）
            logger.warning(f"PDF 第 {i+1} 頁解析失敗，跳過: {e}")
            continue
        if not t.strip():
            continue
        pages.append(f"[第{i+1}頁]\n{t}")
        accum_chars += len(t)
        if accum_chars >= _PDF_MAX_TEXT_CHARS:
            truncated_by = f"字數達上限 {_PDF_MAX_TEXT_CHARS}"
            break

    if not truncated_by and total_pages > _PDF_MAX_PAGES:
        truncated_by = f"頁數達上限 {_PDF_MAX_PAGES}/{total_pages}"

    if truncated_by:
        scanned = last_index + 1
        logger.info(f"PDF 提取截斷：{truncated_by}（已掃描 {scanned} 頁）")
        pages.append(f"\n（⚠️ 文件過長，僅解析前 {scanned} 頁；{truncated_by}）")

    return "\n\n".join(pages)


def strip_markdown(text: str) -> str:
    """LINE 不支援 Markdown，於 Claude 輸出後做最終清理。"""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'(?<!\w)\*([^*\n]+?)\*(?!\w)', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    def _link(m):
        label, url = m.group(1), m.group(2)
        return url if label.strip() == url.strip() else f"{label}\n{url}"
    text = re.sub(r'\[([^\]]+?)\]\((https?://[^\)]+)\)', _link, text)

    text = re.sub(r'`([^`]+?)`', r'\1', text)
    return text


# 向後相容別名（避免破壞跨模組 import）
_strip_markdown = strip_markdown
