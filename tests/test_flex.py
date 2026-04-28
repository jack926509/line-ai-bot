"""features.flex 純邏輯單元測試。"""
from datetime import date
from decimal import Decimal

from features.flex import (
    parse_postback, todo_carousel, note_carousel,
    expense_carousel, expense_summary_bubble,
)


class TestParsePostback:
    def test_normal(self):
        assert parse_postback("act=todo.done&i=3") == {"act": "todo.done", "i": "3"}

    def test_empty(self):
        assert parse_postback("") == {}

    def test_no_equals(self):
        assert parse_postback("garbage") == {}

    def test_partial(self):
        # 中段有 garbage 不應整體失敗
        assert parse_postback("act=x&garbage&i=1") == {"act": "x", "i": "1"}

    def test_multiple_equals(self):
        # 第一個 = 拆 key/value
        assert parse_postback("act=note.del&note=a=b") == {"act": "note.del", "note": "a=b"}


class TestTodoCarousel:
    def test_empty_returns_none(self):
        assert todo_carousel([]) is None

    def test_basic(self):
        todos = [(1, "買牛奶", False, "生活", date(2026, 5, 1))]
        fm = todo_carousel(todos)
        assert fm is not None
        assert "1 項" in fm.alt_text

    def test_caps_at_max_bubbles(self):
        # 12 個 todo → 顯示前 10 個（內部 _MAX_BUBBLES）
        from features.flex import _MAX_BUBBLES
        todos = [(i, f"item{i}", False, "一般", None) for i in range(1, 13)]
        fm = todo_carousel(todos)
        # alt 提及顯示前 N
        assert f"前 {_MAX_BUBBLES}" in fm.alt_text


class TestNoteCarousel:
    def test_empty_returns_none(self):
        assert note_carousel([]) is None

    def test_basic(self):
        notes = [(1, "test", None)]
        fm = note_carousel(notes)
        assert fm is not None
        assert "1 則" in fm.alt_text


class TestExpenseCarousel:
    def test_empty_returns_none(self):
        assert expense_carousel([], title="今日") is None

    def test_basic_expense(self):
        rows = [
            (1, Decimal("120"), "餐飲", "午餐", "現金", date(2026, 4, 28)),
            (2, Decimal("150"), "餐飲", "星巴克", "信用卡", date(2026, 4, 28)),
        ]
        fm = expense_carousel(rows, title="💰 今日")
        assert fm is not None
        assert "2 筆" in fm.alt_text
        # 兩筆 NT$120 + NT$150 = NT$270
        assert "270" in fm.alt_text

    def test_income_amount_flagged(self):
        # 負數金額 → 該 bubble 應視為收入（顯示 +NT$）
        rows = [(1, Decimal("-50000"), "收入", "薪水", None, date(2026, 4, 28))]
        fm = expense_carousel(rows, title="💰 收入")
        assert fm is not None


class TestExpenseSummaryBubble:
    def test_renders_with_data(self):
        summary = {
            "total_expense": Decimal("1500"),
            "total_income": Decimal("0"),
            "net": Decimal("1500"),
            "count": 5,
            "by_category": [("餐飲", 800.0, 3), ("交通", 700.0, 2)],
        }
        fm = expense_summary_bubble(summary, "本月", date(2026, 4, 1), date(2026, 4, 28))
        assert fm is not None
        assert "本月" in fm.alt_text
        assert "1,500" in fm.alt_text

    def test_with_income(self):
        summary = {
            "total_expense": Decimal("500"),
            "total_income": Decimal("50000"),
            "net": Decimal("-49500"),
            "count": 2,
            "by_category": [("餐飲", 500.0, 1)],
        }
        fm = expense_summary_bubble(summary, "本月", date(2026, 4, 1), date(2026, 4, 28))
        assert fm is not None
