"""多步驟工作流（預留，第二批啟用）

未來支援場景示例：
- 「準備明天的會議」→ 拉行程 → 列待辦 → 抓相關文件 → 算最佳出門時間 → 推地圖
- 「結束旅程」→ 列旅程 → 摘要花費 → 整理照片 → 寫筆記
- 「月底結算」→ 拉本月行程 / 待辦完成率 → 生月報

預留 hooks：
- features/scheduler.py: register_one_off(when, callback, args)
- db.workflows 表（已建，未啟用）
- compose_workflow Claude tool（本檔）
"""
import logging

logger = logging.getLogger("lumio.workflow")


def compose_workflow(goal: str, steps: list[dict] | None = None) -> str:
    """工作流編排入口（佔位）。未來將自動拆解 goal → 子步驟 → 排程執行。"""
    return (
        "🚧 多步驟工作流（即將推出）\n\n"
        f"目標：{goal}\n\n"
        "未來將支援自動串聯：\n"
        "  • 拉行程 / 待辦 / 文件\n"
        "  • 計算出門時間與導航\n"
        "  • 一次性 / 週期性排程\n"
        "  • 跨工具編排（公文 + 行程 + 提醒）\n\n"
        "本功能於 Stage 7 實作。"
    )
