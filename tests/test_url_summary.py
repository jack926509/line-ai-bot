"""features.url_summary 純函式測試（不觸 Perplexity / 不下載 PDF）。"""
from features.url_summary import _is_pdf_url


class TestIsPdfUrl:
    def test_simple_pdf(self):
        assert _is_pdf_url("https://example.com/doc.pdf") is True

    def test_uppercase_extension(self):
        assert _is_pdf_url("https://example.com/path/Report-2026.PDF") is True

    def test_html(self):
        assert _is_pdf_url("https://example.com/index.html") is False

    def test_root(self):
        assert _is_pdf_url("https://example.com/") is False

    def test_pdf_with_query(self):
        assert _is_pdf_url("https://example.com/file.pdf?download=1") is True

    def test_pdf_substring_in_path_not_extension(self):
        assert _is_pdf_url("https://example.com/pdfshow") is False
