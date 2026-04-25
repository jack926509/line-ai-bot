"""公文初稿生成 + 範本庫"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import db
from config import anthropic_client, CLAUDE_MODEL, TZ_NAME

logger = logging.getLogger("lumio.doc_official")


_OFFICIAL_DOC_PROMPT = (
    "依台灣政府公文體格式，撰寫一份公文初稿。\n\n"
    "規範：\n"
    "- 使用機關名稱：「台灣電力股份有限公司發電處環化組」\n"
    "- 結構：受文者 / 主旨 / 說明 / 擬辦 / 陳 / 核\n"
    "- 段落結構為論述型完整段落，避免條列化（除非為說明事項分點）\n"
    "- 行文精簡，公文化語氣，禁用口語與冗詞\n"
    "- 民國紀年：中華民國 {roc_year} 年 {month} 月 {day} 日\n"
    "- 純文字，禁用 Markdown\n\n"
    "資料：\n"
    "受文者：{recipient}\n"
    "主旨：{subject}\n"
    "{points_block}{basis_block}{plan_block}"
    "\n請輸出完整公文初稿。"
)


def gen_official_doc(
    recipient: str,
    subject: str,
    points: list[str] | None = None,
    basis: str | None = None,
    plan: str | None = None,
) -> str:
    """生成公文初稿。recipient 為受文者；subject 為主旨；
    points 為說明事項；basis 為依據；plan 為擬辦方向。"""
    now = datetime.now(ZoneInfo(TZ_NAME))
    points_block = ""
    if points:
        points_block = "說明重點：\n" + "\n".join(f"- {p}" for p in points) + "\n"
    basis_block = f"依據：{basis}\n" if basis else ""
    plan_block = f"擬辦方向：{plan}\n" if plan else ""

    prompt = _OFFICIAL_DOC_PROMPT.format(
        roc_year=now.year - 1911,
        month=now.month,
        day=now.day,
        recipient=recipient,
        subject=subject,
        points_block=points_block,
        basis_block=basis_block,
        plan_block=plan_block,
    )

    try:
        resp = anthropic_client.messages.create(
            model=CLAUDE_MODEL, max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(getattr(b, "text", "") for b in resp.content).strip()
        return f"📋 公文初稿：\n\n{text}\n\n（請自行調整文號、附件與發文日期）"
    except Exception as e:
        logger.warning(f"公文生成失敗: {e}")
        return f"⚠️ 公文生成失敗：{e}"


# ─── 範本庫 ───

def template_add(user_id: str, name: str, body: str, category: str = "一般") -> str:
    tid = db.add_template(user_id, name, category, body)
    return f"📋 範本已新增：「{name}」（分類：{category}，DB id={tid}）"


def template_list(user_id: str) -> str:
    rows = db.list_templates(user_id)
    if not rows:
        return (
            "📋 範本庫是空的\n"
            "說「新增範本：名稱、分類、正文」即可建立"
        )
    lines, current_cat = ["📋 範本庫："], None
    for i, (_id, name, cat, _body) in enumerate(rows, 1):
        if cat != current_cat:
            current_cat = cat
            lines.append(f"\n📂 {cat}")
        lines.append(f"  {i}. {name}")
    lines.append("\n說「套用範本 N」或 /範本 套用 N 取得正文")
    return "\n".join(lines)


def template_apply(user_id: str, index: int) -> str:
    rows = db.list_templates(user_id)
    if index < 1 or index > len(rows):
        return "⚠️ 找不到該編號的範本，用 /範本 查看清單"
    _id, name, cat, body = rows[index - 1]
    return f"📋 範本：「{name}」（{cat}）\n━━━━━━━━━━━\n{body}"


def template_delete(user_id: str, index: int) -> str:
    rows = db.list_templates(user_id)
    if index < 1 or index > len(rows):
        return "⚠️ 找不到該編號的範本"
    tid, name, _cat, _body = rows[index - 1]
    db.delete_template(tid)
    return f"🗑 已刪除範本：「{name}」"


# ─── /範本 slash 入口 ───

def handle_template(text: str, user_id: str) -> str:
    import re
    parts = text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        return template_list(user_id)
    m = re.match(r"(套用|apply)\s*(\d+)$", arg)
    if m:
        return template_apply(user_id, int(m.group(2)))
    m = re.match(r"(刪除?|delete|x)\s*(\d+)$", arg)
    if m:
        return template_delete(user_id, int(m.group(2)))
    return (
        "📋 /範本 用法：\n"
        "  /範本           查看清單\n"
        "  /範本 套用 N    取得第 N 則範本正文\n"
        "  /範本 刪 N      刪除第 N 則\n"
        "新增範本請改說：「新增範本：名稱、分類、正文」"
    )
