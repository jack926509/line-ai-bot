"""features.flex 純邏輯單元測試。"""
from datetime import date

from features.flex import parse_postback, todo_carousel, note_carousel


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
