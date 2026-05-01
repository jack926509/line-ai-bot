"""features.expense 純函式測試（不觸 DB）。"""
from datetime import date
from decimal import Decimal

from features.expense import (
    _fmt_amount, _parse_amount, _bar, _emoji,
    label_period, _parse_date,
    period_range, today_tw,
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


class TestPeriodRange:
    """以週三 2026-04-29 作為固定基準，避開時區邊界與月底特殊情況。"""

    BASE = date(2026, 4, 29)  # 週三

    def test_today(self):
        assert period_range("today", self.BASE) == (self.BASE, self.BASE)

    def test_yesterday(self):
        assert period_range("yesterday", self.BASE) == (date(2026, 4, 28), date(2026, 4, 28))

    def test_week_starts_on_monday(self):
        sd, ed = period_range("week", self.BASE)
        assert sd == date(2026, 4, 27)  # 該週週一
        assert ed == self.BASE

    def test_month_starts_on_first(self):
        sd, ed = period_range("month", self.BASE)
        assert sd == date(2026, 4, 1)
        assert ed == self.BASE

    def test_last_month(self):
        sd, ed = period_range("last_month", self.BASE)
        assert sd == date(2026, 3, 1)
        assert ed == date(2026, 3, 31)

    def test_year(self):
        sd, ed = period_range("year", self.BASE)
        assert sd == date(2026, 1, 1)
        assert ed == self.BASE

    def test_unknown_falls_back_to_today(self):
        assert period_range("custom", self.BASE) == (self.BASE, self.BASE)

    def test_today_tw_returns_date(self):
        # 不驗具體值（依執行時刻），只驗型別與合理範圍
        d = today_tw()
        assert isinstance(d, date)
        assert d.year >= 2025
