"""Claude 對話引擎（含工具呼叫迴圈 + Prompt Caching + 文件分析）"""
import re
import base64
import io
import db
from config import anthropic_client, CLAUDE_MODEL
from prompts import SYSTEM_PROMPT, build_date_block
from features.tools import TOOLS, dispatch_tool

# PDF 處理門檻
_PDF_INLINE_MAX = 4 * 1024 * 1024   # ≤ 4MB → 直接送 Claude（保留排版/表格）
_FILE_SIZE_MAX  = 20 * 1024 * 1024  # > 20MB → 拒絕

_SUMMARIZE_PROMPT = (
    "請用繁體中文摘要這份文件「{filename}」的重點內容。\n"
    "格式：\n"
    "①一句話總結\n"
    "②主要重點（條列）\n"
    "③需要注意或後續行動的事項（如有）\n\n"
    "語氣溫暖專業，如同秘書幫老闆整理會議前必讀摘要。"
)

# 靜態工具列表：在最後一個 tool 加 cache_control，
# 告知 Claude API 快取所有 tool 定義（約 2000 token，5 分鐘 TTL）
_TOOLS_CACHED = TOOLS[:-1] + [{**TOOLS[-1], "cache_control": {"type": "ephemeral"}}]

# Sonnet 4.6 定價參考（USD / 1M tokens）
_PRICE = {"in": 3.0, "cache_write": 3.75, "cache_read": 0.30, "out": 15.0}


def _build_system() -> list[dict]:
    """靜態 SYSTEM_PROMPT 加 cache；動態日期區塊每次重算但 token 少"""
    return [
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": build_date_block()},
    ]


def _log_usage(usage, call_n: int) -> None:
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    regular_in = usage.input_tokens - cache_read
    out = usage.output_tokens
    cost = (
        regular_in * _PRICE["in"] +
        cache_write * _PRICE["cache_write"] +
        cache_read * _PRICE["cache_read"] +
        out * _PRICE["out"]
    ) / 1_000_000
    print(
        f"[Claude #{call_n}] in={usage.input_tokens} "
        f"cache_write={cache_write} cache_read={cache_read} "
        f"out={out} ≈${cost:.5f}"
    )


def ask_claude(user_id: str, text: str, image_b64: str | None = None) -> str:
    content = (
        [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
            {"type": "text", "text": text or "請用繁體中文分析這張圖片"},
        ]
        if image_b64 else text
    )
    db.save_message(user_id, "user", content)
    messages = db.get_history(user_id)
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
    reply = reply or "抱歉，我暫時無法回應，請再試一次～"
    reply = _strip_markdown(reply)
    db.save_message(user_id, "assistant", reply)
    return reply


def analyze_file(user_id: str, file_bytes: bytes, filename: str) -> str:
    """分析上傳的文件（PDF / 純文字），回傳摘要並存入對話記憶"""
    size_mb = len(file_bytes) / 1024 / 1024
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    print(f"[文件分析] {filename} ({size_mb:.1f}MB)")

    if len(file_bytes) > _FILE_SIZE_MAX:
        return f"⚠️ 檔案太大（{size_mb:.1f}MB），目前支援 20MB 以下的文件"

    try:
        if ext == "pdf":
            reply = _analyze_pdf(file_bytes, filename)
        else:
            text = file_bytes.decode("utf-8", errors="replace")
            reply = _call_claude_text(_SUMMARIZE_PROMPT.format(filename=filename), text[:15000])
    except Exception as e:
        print(f"[文件分析] 失敗：{e}")
        return f"⚠️ 文件分析失敗：{e}"

    # 存入對話記憶，後續可追問
    db.save_message(user_id, "user", f"[📄 上傳文件：{filename}（{size_mb:.1f}MB）]")
    db.save_message(user_id, "assistant", reply)
    return reply


def _analyze_pdf(file_bytes: bytes, filename: str) -> str:
    if len(file_bytes) <= _PDF_INLINE_MAX:
        # 小檔案：直接送 Claude，保留完整排版與圖表理解能力
        pdf_b64 = base64.b64encode(file_bytes).decode()
        content = [
            {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
            },
            {"type": "text", "text": _SUMMARIZE_PROMPT.format(filename=filename)},
        ]
        resp = anthropic_client.messages.create(
            model=CLAUDE_MODEL, max_tokens=1500,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
        )
        _log_usage(resp.usage, 1)
    else:
        # 大檔案：pypdf 提取文字再送 Claude
        text = _extract_pdf_text(file_bytes)
        if not text.strip():
            return "⚠️ 無法提取 PDF 文字（可能是純圖片掃描版），請傳送可選取文字的 PDF"
        resp = anthropic_client.messages.create(
            model=CLAUDE_MODEL, max_tokens=1500,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": _SUMMARIZE_PROMPT.format(filename=filename) + f"\n\n文件內容：\n{text[:12000]}"}],
        )
        _log_usage(resp.usage, 1)

    return _strip_markdown("".join(getattr(b, "text", "") for b in resp.content))


def _extract_pdf_text(file_bytes: bytes) -> str:
    """用 pypdf 提取 PDF 文字（處理大檔案，最多 40 頁）"""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages[:40]):
        t = page.extract_text()
        if t:
            pages.append(f"[第{i+1}頁]\n{t}")
    return "\n\n".join(pages)


def _call_claude_text(prompt: str, content: str) -> str:
    resp = anthropic_client.messages.create(
        model=CLAUDE_MODEL, max_tokens=1200,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": f"{prompt}\n\n{content}"}],
    )
    _log_usage(resp.usage, 1)
    return _strip_markdown("".join(getattr(b, "text", "") for b in resp.content))


def _strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'(?<!\w)\*([^*\n]+?)\*(?!\w)', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[([^\]]+?)\]\((https?://[^\)]+)\)', r'\1\n\2', text)
    text = re.sub(r'`([^`]+?)`', r'\1', text)
    return text
