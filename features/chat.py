"""Claude 對話引擎（含工具呼叫迴圈 + Prompt Caching）"""
import re
import db
from config import anthropic_client, CLAUDE_MODEL
from prompts import SYSTEM_PROMPT, build_date_block
from features.tools import TOOLS, dispatch_tool

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


def _strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'(?<!\w)\*([^*\n]+?)\*(?!\w)', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[([^\]]+?)\]\((https?://[^\)]+)\)', r'\1\n\2', text)
    text = re.sub(r'`([^`]+?)`', r'\1', text)
    return text
