"""features.todo._parse_todo_input 自然語言解析測試。"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from features.todo import _parse_todo_input


_TZ = ZoneInfo("Asia/Taipei")


class TestParseTodoInput:
    def test_plain(self):
        content, cat, due = _parse_todo_input("買牛奶")
        assert content == "買牛奶"
        assert cat == "一般"
        assert due is None

    def test_with_category(self):
        content, cat, due = _parse_todo_input("#工作 寫週報")
        assert content == "寫週報"
        assert cat == "工作"
        assert due is None

    def test_with_today(self):
        content, cat, due = _parse_todo_input("今天 開會")
        today = datetime.now(_TZ).strftime("%Y-%m-%d")
        assert content == "開會"
        assert due == today

    def test_with_tomorrow(self):
        content, cat, due = _parse_todo_input("明天 拜訪客戶")
        tomorrow = (datetime.now(_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")
        assert content == "拜訪客戶"
        assert due == tomorrow

    def test_with_md_date(self):
        content, cat, due = _parse_todo_input("12/25 聖誕禮物")
        assert content == "聖誕禮物"
        # 12/25 應為今年或明年（非空）
        assert due is not None
        assert due.endswith("-12-25")

    def test_category_and_date(self):
        content, cat, due = _parse_todo_input("#家庭 明天 接小孩")
        assert content == "接小孩"
        assert cat == "家庭"
        assert due is not None
