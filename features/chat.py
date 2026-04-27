"""Claude 對話引擎（含工具呼叫迴圈 + Prompt Caching + 文件分析）"""
import re
import base64
import io
import logging

import db
from config import anthropic_client, CLAUDE_MODEL, CLAUDE_MODEL_LIGHT
from prompts import SYSTEM_PROMPT, build_date_block
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

# Sonnet 4.6 定價參考（USD / 1M tokens）
_PRICE = {"in": 3.0, "cache_write": 3.75, "cache_read": 0.30, "out": 15.0}

# 共用之 system cache block：所有單次任務（PDF 摘要 / 文字摘要 / 公文）共用，可命中 cache
_CACHED_SYS_BLOCK = {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}


def _with_cache(items: list[dict]) -> list[dict]:
    """於序列最後一個元素加 cache_control，避免綁定特定索引"""
    if not items:
        return items
    return [*items[:-1], {**items[-1], "cache_control": {"type": "ephemeral"}}]


# 靜態工具列表 cache（約 2000 token，5 分鐘 TTL）
_TOOLS_CACHED = _with_cache(TOOLS)


def _build_system() -> list[dict]:
    """完整對話用 system：靜態 cache block + 動態日期區塊（每次重算但 token 少）"""
    return [_CACHED_SYS_BLOCK, {"type": "text", "text": build_date_block()}]


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


def _log_usage(usage, call_n: int) -> None:
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    regular_in = usage.input_tokens - cache_read
    cost = (
        regular_in * _PRICE["in"] +
        cache_write * _PRICE["cache_write"] +
        cache_read * _PRICE["cache_read"] +
        usage.output_tokens * _PRICE["out"]
    ) / 1_000_000
    logger.info(
        f"Claude #{call_n} in={usage.input_tokens} cache_write={cache_write} "
        f"cache_read={cache_read} out={usage.output_tokens} ≈${cost:.5f}"
    )


def simple_complete(prompt: str, max_tokens: int = 1200, with_system: bool = True,
                    model: str | None = None) -> str:
    """一次性 Claude 呼叫（無工具、無對話歷史）。
    供文件摘要、公文生成、會議紀錄整理等短任務共用。"""
    kwargs: dict = {
        "model": model or CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if with_system:
        kwargs["system"] = [_CACHED_SYS_BLOCK]
    resp = anthropic_client.messages.create(**kwargs)
    _log_usage(resp.usage, 1)
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


def chunked_summarize(text: str, final_prompt: str, max_tokens: int = 1500) -> str:
    """長文 map-reduce 摘要：超過上限時分段先粗摘，再合成最終回應。

    final_prompt 必須含 "{content}" 佔位符，會被替換為原文（短）或階段性摘要（長）。
    """
    if len(text) <= _SINGLE_PASS_LIMIT:
        return simple_complete(final_prompt.format(content=text), max_tokens=max_tokens)

    chunks = _split_text(text, _CHUNK_SIZE)
    logger.info(f"長文分段摘要：{len(text)} 字 → {len(chunks)} 段")

    partials: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        prompt = (
            f"以下是長文件第 {i}/{len(chunks)} 段，請以繁體中文擷取重點（條列、純文字、禁用 Markdown），"
            f"保留人事時地物、決議與數字：\n\n{chunk}"
        )
        partial = simple_complete(prompt, max_tokens=800, model=CLAUDE_MODEL_LIGHT)
        partials.append(f"[第 {i} 段重點]\n{partial}")

    merged = "\n\n".join(partials)
    if len(merged) > _SINGLE_PASS_LIMIT:
        merged = merged[:_SINGLE_PASS_LIMIT]
    return simple_complete(final_prompt.format(content=merged), max_tokens=max_tokens)


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
    system = _build_system()

    response = anthropic_client.messages.create(
        model=CLAUDE_MODEL, max_tokens=1000,
        system=system, tools=_TOOLS_CACHED, messages=messages,
    )
    _log_usage(response.usage, 1)

    # 最多 3 輪 tool use（現實場景：1-2 輪已足夠）
    for i in range(3):
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
        _log_usage(response.usage, i + 2)

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
            reply = _analyze_pdf(file_bytes, filename)
        else:
            text = file_bytes.decode("utf-8", errors="replace")
            reply = chunked_summarize(
                text,
                _SUMMARIZE_TEMPLATE.replace("{filename}", filename),
                max_tokens=1500,
            )
    except Exception as e:
        logger.exception(f"文件分析失敗: {e}")
        return f"⚠️ 文件分析失敗：{e}"

    db.save_message(user_id, "user", f"[📄 上傳文件：{filename}（{size_mb:.1f}MB）]")
    db.save_message(user_id, "assistant", reply)
    return reply


def _analyze_pdf(file_bytes: bytes, filename: str) -> str:
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
        _log_usage(resp.usage, 1)
        return strip_markdown("".join(getattr(b, "text", "") for b in resp.content))

    # 大檔案：pypdf 提取文字再送 Claude（必要時自動分段摘要）
    text = _extract_pdf_text(file_bytes)
    if not text.strip():
        return "⚠️ 無法提取 PDF 文字（可能是純圖片掃描版），請傳送可選取文字的 PDF"
    return chunked_summarize(
        text,
        _SUMMARIZE_TEMPLATE.replace("{filename}", filename),
        max_tokens=1500,
    )


def _extract_pdf_text(file_bytes: bytes) -> str:
    """用 pypdf 提取 PDF 文字（最多 40 頁）"""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages[:40]):
        t = page.extract_text()
        if t:
            pages.append(f"[第{i+1}頁]\n{t}")
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
