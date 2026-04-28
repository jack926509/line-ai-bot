"""features.expense 純函式測試（不觸 DB）。"""
from datetime import date
from decimal import Decimal

from features.expense import (
    _fmt_amount, _parse_amount, _bar, _emoji,
    label_period, _parse_date,
    CATEGORIES, CATEGORY_EMOJI,
)


class TestFmtAmount:
    def test_positive(self):
        assert _fmt_amount(120) == "NT$120"

    def test_thousands(self):
        assert _fmt_amount(1234) == "NT$1,234"

    def test_large(self):
        assert _fmt_amount(50000) == "NT$50,000"

    def test_negative_is_income(self):
        # 負數視為收入，顯示為 +NT$
        assert _fmt_amount(-50000) == "+NT$50,000"

    def test_decimal(self):
        # Decimal 也應正常處理
        assert _fmt_amount(Decimal("1234.50")) == "NT$1,234"


class TestParseAmount:
    def test_int(self):
        assert _parse_amount("120") == Decimal("120")

    def test_float(self):
        assert _parse_amount("12.5") == Decimal("12.5")

    def test_thousands_comma(self):
        assert _parse_amount("1,234.50") == Decimal("1234.50")

    def test_invalid(self):
        assert _parse_amount("abc") is None
        assert _parse_amount("") is None

    def test_whitespace(self):
        assert _parse_amount("  150  ") == Decimal("150")


class TestBar:
    def test_zero(self):
        assert _bar(0) == "░" * 10

    def test_full(self):
        assert _bar(100) == "█" * 10

    def test_half(self):
        # 50% → 5 滿 5 空
        assert _bar(50) == "█" * 5 + "░" * 5

    def test_overflow(self):
        # >100 應 clamp 到 width
        bar = _bar(150)
        assert len(bar) == 10

    def test_negative(self):
        bar = _bar(-10)
        assert len(bar) == 10
        assert "█" not in bar


class TestEmoji:
    def test_known_categories(self):
        for cat in CATEGORIES:
            # 每個預設分類都有對應 emoji
            assert _emoji(cat) == CATEGORY_EMOJI[cat]

    def test_unknown_falls_back(self):
        assert _emoji("不存在的分類") == "📦"


class TestLabelPeriod:
    def test_known(self):
        assert label_period("month") == "本月"
        assert label_period("today") == "今日"
        assert label_period("yesterday") == "昨日"
        assert label_period("year") == "今年"

    def test_unknown_passthrough(self):
        assert label_period("custom") == "custom"


class TestParseDate:
    def test_valid(self):
        assert _parse_date("2026-04-29") == date(2026, 4, 29)

    def test_invalid(self):
        assert _parse_date("garbage") is None
        assert _parse_date("2026/04/29") is None  # 不接受斜線

    def test_none(self):
        assert _parse_date(None) is None
        assert _parse_date("") is None
