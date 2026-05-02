"""features.taiwan 純函式測試（不觸 Perplexity）。"""
from datetime import date

from features.taiwan import tax_countdown


class TestTaxCountdownBeforeSeason:
    def test_one_day_before(self):
        out = tax_countdown(date(2026, 4, 30))
        assert "還有 1 天" in out
        assert "申報期間：2026-05-01 ~ 2026-05-31" in out

    def test_far_before(self):
        out = tax_countdown(date(2026, 1, 1))
        assert "還有 120 天" in out
        # 早期不顯示緊急提示
        assert "⚠️" not in out


class TestTaxCountdownDuringSeason:
    def test_first_day(self):
        out = tax_countdown(date(2026, 5, 1))
        assert "倒數 30 天" in out
        assert "電子申報" in out
        assert "⚠️" not in out

    def test_mid_season(self):
        out = tax_countdown(date(2026, 5, 15))
        assert "倒數 16 天" in out
        assert "⚠️" not in out

    def test_urgent_within_seven_days(self):
        out = tax_countdown(date(2026, 5, 25))
        assert "倒數 6 天" in out
        # 7 天內顯示緊急標
        assert "⚠️" in out

    def test_last_day(self):
        out = tax_countdown(date(2026, 5, 31))
        assert "倒數 0 天" in out
        assert "⚠️" in out


class TestTaxCountdownAfterSeason:
    def test_just_after(self):
        out = tax_countdown(date(2026, 6, 1))
        assert "已截止" in out
        assert "下次申報：2027-05-01" in out
        assert "還有 334 天" in out

    def test_year_end(self):
        out = tax_countdown(date(2026, 12, 31))
        assert "已截止" in out
        assert "下次申報：2027-05-01" in out


class TestInvoiceNumberRegex:
    """確認對獎號碼解析能容忍多種輸入格式。"""

    def test_regex_extraction(self):
        from features.taiwan import _NUM_RE
        assert _NUM_RE.findall("12345678") == ["12345678"]
        assert _NUM_RE.findall("12345678 23456789") == ["12345678", "23456789"]
        assert _NUM_RE.findall("12345678,23456789") == ["12345678", "23456789"]
        # 7 位數不抓
        assert _NUM_RE.findall("1234567") == []
        # 9 位連續會抓前 8 位（行為定義）
        assert _NUM_RE.findall("123456789") == ["12345678"]
