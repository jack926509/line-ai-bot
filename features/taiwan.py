"""台灣個人化高頻場景：油價、統一發票對獎、報稅倒數。

油價 / 發票皆透過既有 Perplexity 通道即時抓取，避免維護爬蟲與斷頁風險。
報稅為純倒數，每年 5/1~5/31 申報期間。
"""
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from config import TZ_NAME
from features.perplexity import chat as pplx_chat


_TZ = ZoneInfo(TZ_NAME)


# ── 油價（中油） ─────────────────────────────────


_GAS_SYS = "你是台灣油價即時查詢助手，繁體中文，純文字，禁用 Markdown。"
_GAS_PROMPT = (
    "查詢中油（CPC）今日最新牌價並依下列格式回覆，純文字 + emoji，禁用 Markdown：\n"
    "⛽ 中油牌價（生效日 YYYY-MM-DD）\n"
    "  92 無鉛 NT$xx.x\n"
    "  95 無鉛 NT$xx.x\n"
    "  98 無鉛 NT$xx.x\n"
    "  超級柴油 NT$xx.x\n"
    "如有本週是否調漲／調降，於最後一行補一句說明。"
)


def gas_price() -> str:
    r = pplx_chat(_GAS_SYS, _GAS_PROMPT, recency="week")
    if r["error"]:
        return f"⚠️ 油價查詢失敗：{r['error']}"
    return r["answer"].strip()


# ── 統一發票對獎 ──────────────────────────────────


_INVOICE_SYS = "你是台灣統一發票對獎助手，繁體中文，純文字，禁用 Markdown。"
_INVOICE_PROMPT = (
    "查詢「最新一期 統一發票中獎號碼」並依下列格式回覆：\n"
    "🧾 統一發票（YYY 年 MM-MM 月期）\n"
    "  特別獎（1000 萬）：xxxxxxxx\n"
    "  特獎（200 萬）：xxxxxxxx\n"
    "  頭獎（20 萬）：xxxxxxxx 等三組\n"
    "  增開六獎（200 元）：xxx 等若干組（如有）\n"
    "務必標註開獎期別，避免時序錯亂。"
)

_NUM_RE = re.compile(r"\d{8}")


def invoice_lottery(numbers: str | None = None) -> str:
    """numbers：使用者輸入的 8 位發票號碼，多筆以空白／逗號分隔；None 則僅查中獎號碼。"""
    r = pplx_chat(_INVOICE_SYS, _INVOICE_PROMPT, recency="month")
    if r["error"]:
        return f"⚠️ 發票查詢失敗：{r['error']}"
    base = r["answer"].strip()
    if not numbers:
        return base
    nums = _NUM_RE.findall(numbers)
    if not nums:
        return base + "\n\n⚠️ 未偵測到 8 位數號碼（範例：12345678 23456789）"
    note_lines = ["", "📌 你輸入的號碼："]
    for n in nums:
        note_lines.append(f"  {n}（末三碼 {n[-3:]}）")
    note_lines.append("（請以上方公告為準對獎，正式以財政部公告為主）")
    return base + "\n" + "\n".join(note_lines)


# ── 報稅倒數 ──────────────────────────────────────


def _today_tw() -> date:
    return datetime.now(_TZ).date()


def tax_countdown(today: date | None = None) -> str:
    """5/1~5/31 申報期間內回緊急倒數；其餘日期回下次申報距離。"""
    t = today or _today_tw()
    year = t.year
    season_start = date(year, 5, 1)
    season_end = date(year, 5, 31)

    if t < season_start:
        days = (season_start - t).days
        return (
            f"📅 距離 {year} 年綜所稅申報還有 {days} 天\n"
            f"申報期間：{season_start} ~ {season_end}\n\n"
            "建議現在開始準備：\n"
            "  ① 健保 / 房貸 / 教育學費 / 捐贈收據\n"
            "  ② 保險費（人身保險上限 24,000 元 / 人）\n"
            "  ③ 醫療費自付額收據\n"
            "  ④ 列舉扣除若高於標準扣除額（單身 12.4 萬）才送列舉"
        )

    if t <= season_end:
        days = (season_end - t).days
        urgency = "⚠️ " if days <= 7 else ""
        return (
            f"{urgency}📅 {year} 年綜所稅申報倒數 {days} 天（截止 {season_end}）\n\n"
            "申報方式：\n"
            "  ① 電子申報：財政部電子申報繳稅服務網（推薦）\n"
            "  ② 行動裝置：手機報稅 App\n"
            "  ③ 國稅局臨櫃\n\n"
            "繳稅期限同申報期限；可分期或刷卡。"
        )

    next_start = date(year + 1, 5, 1)
    days = (next_start - t).days
    return (
        f"📅 {year} 年綜所稅申報已截止\n"
        f"下次申報：{next_start}（還有 {days} 天）"
    )
