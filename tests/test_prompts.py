"""prompts 純字串組裝測試。"""
from prompts import (
    SYSTEM_PROMPT, SYSTEM_PROMPT_CORE, SYSTEM_PROMPT_TOOLS_GUIDE,
    build_profile_block, build_date_block,
)


class TestPromptSplit:
    def test_combined_equals_full(self):
        assert SYSTEM_PROMPT == SYSTEM_PROMPT_CORE + "\n\n" + SYSTEM_PROMPT_TOOLS_GUIDE

    def test_core_has_identity(self):
        assert "Lumio" in SYSTEM_PROMPT_CORE
        assert "格式" in SYSTEM_PROMPT_CORE

    def test_tools_guide_has_tools(self):
        # 工具指引應提及主要工具
        for token in ["web_search", "gcal", "todo_add", "reminder", "profile_remember"]:
            assert token in SYSTEM_PROMPT_TOOLS_GUIDE


class TestBuildProfileBlock:
    def test_empty(self):
        assert build_profile_block([]) == ""

    def test_single(self):
        out = build_profile_block([("暱稱", "Jack")])
        assert "長期記憶" in out
        assert "暱稱：Jack" in out

    def test_multiple_preserves_order(self):
        facts = [("a", "1"), ("b", "2"), ("c", "3")]
        out = build_profile_block(facts)
        # 順序應與輸入一致
        assert out.index("a：1") < out.index("b：2") < out.index("c：3")


class TestBuildDateBlock:
    def test_contains_now(self):
        block = build_date_block()
        assert "現在時間" in block
        assert "台灣時間" in block

    def test_period_label(self):
        block = build_date_block()
        # period 標籤應是其中之一
        assert any(p in block for p in ["早上", "中午", "下午", "傍晚", "晚上"])
