"""features.chat 純函式測試（不觸發 Anthropic API）。"""
from features.chat import strip_markdown, _split_text


class TestStripMarkdown:
    def test_bold(self):
        assert strip_markdown("**hello**") == "hello"
        assert strip_markdown("__bold__") == "bold"

    def test_italic(self):
        assert strip_markdown("*italic*") == "italic"

    def test_heading(self):
        assert strip_markdown("# Title") == "Title"
        assert strip_markdown("### Sub") == "Sub"

    def test_code(self):
        assert strip_markdown("`code`") == "code"

    def test_link_label_eq_url(self):
        assert strip_markdown("[https://x.co](https://x.co)") == "https://x.co"

    def test_link_label_diff_url(self):
        out = strip_markdown("[詳見](https://example.com)")
        assert "詳見" in out and "https://example.com" in out

    def test_combined(self):
        out = strip_markdown("# 標題\n\n**重點**：請看 `code`")
        assert "**" not in out
        assert "標題" in out
        assert "code" in out


class TestSplitText:
    def test_short_passthrough(self):
        text = "short text"
        assert _split_text(text, 100) == [text]

    def test_paragraph_boundary(self):
        text = "para1\n\npara2\n\npara3"
        chunks = _split_text(text, 6)
        # 每段獨立切
        assert all(len(c) <= 6 for c in chunks)
        joined = "".join(chunks)
        for kw in ["para1", "para2", "para3"]:
            assert kw in joined

    def test_long_single_paragraph_force_split(self):
        text = "a" * 250
        chunks = _split_text(text, 100)
        # 應該被強制切成 ceil(250/100) = 3 段
        assert len(chunks) == 3
        assert "".join(chunks) == text
