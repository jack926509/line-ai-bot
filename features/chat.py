"""Claude 對話引擎（含工具呼叫迴圈）"""
import re
import db
from config import anthropic_client, CLAUDE_MODEL
from prompts import build_system_prompt
from features.tools import TOOLS, dispatch_tool


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
    system = build_system_prompt()

    response = anthropic_client.messages.create(
        model=CLAUDE_MODEL, max_tokens=1000,
        system=system, tools=TOOLS, messages=messages,
    )

    for _ in range(5):
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
            system=system, tools=TOOLS, messages=messages,
        )

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
