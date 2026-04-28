"""features.workflow 時間計算單元測試。"""
from datetime import datetime
from zoneinfo import ZoneInfo

from features.workflow import _parse_hhmm, _next_daily, _next_weekly

_TZ = ZoneInfo("Asia/Taipei")


class TestParseHhmm:
    def test_valid(self):
        assert _parse_hhmm("09:00") == (9, 0)
        assert _parse_hhmm("23:59") == (23, 59)
        assert _parse_hhmm("00:00") == (0, 0)

    def test_invalid(self):
        assert _parse_hhmm("") is None
        assert _parse_hhmm("9:00") == (9, 0)  # 單位數小時也接受
        assert _parse_hhmm("25:00") is None
        assert _parse_hhmm("12:60") is None
        assert _parse_hhmm("abc") is None
        assert _parse_hhmm("12-30") is None


class TestNextDaily:
    def test_today_future(self):
        # 14:00 看 18:00 → 今天 18:00
        ref = datetime(2026, 4, 28, 14, 0, tzinfo=_TZ)
        nxt = _next_daily("18:00", ref)
        assert nxt == datetime(2026, 4, 28, 18, 0, tzinfo=_TZ)

    def test_today_past_rolls_tomorrow(self):
        # 14:00 看 09:00 → 明天 09:00
        ref = datetime(2026, 4, 28, 14, 0, tzinfo=_TZ)
        nxt = _next_daily("09:00", ref)
        assert nxt == datetime(2026, 4, 29, 9, 0, tzinfo=_TZ)

    def test_exact_now_rolls_tomorrow(self):
        # 邊界：現在剛好就是 spec → 視為已過，排明天
        ref = datetime(2026, 4, 28, 9, 0, tzinfo=_TZ)
        nxt = _next_daily("09:00", ref)
        assert nxt == datetime(2026, 4, 29, 9, 0, tzinfo=_TZ)

    def test_invalid_spec(self):
        ref = datetime(2026, 4, 28, 14, 0, tzinfo=_TZ)
        assert _next_daily("abc", ref) is None


class TestNextWeekly:
    def test_future_weekday_same_week(self):
        # 週二 14:00 看 週五 17:00 → 同週週五
        ref = datetime(2026, 4, 28, 14, 0, tzinfo=_TZ)  # Tue
        nxt = _next_weekly("5|17:00", ref)
        assert nxt == datetime(2026, 5, 1, 17, 0, tzinfo=_TZ)

    def test_past_weekday_rolls_next_week(self):
        # 週二 14:00 看 週一 09:00 → 下週週一
        ref = datetime(2026, 4, 28, 14, 0, tzinfo=_TZ)
        nxt = _next_weekly("1|09:00", ref)
        assert nxt == datetime(2026, 5, 4, 9, 0, tzinfo=_TZ)

    def test_same_weekday_future_time(self):
        # 週二 14:00 看 週二 18:00 → 今天 18:00
        ref = datetime(2026, 4, 28, 14, 0, tzinfo=_TZ)
        nxt = _next_weekly("2|18:00", ref)
        assert nxt == datetime(2026, 4, 28, 18, 0, tzinfo=_TZ)

    def test_same_weekday_past_time(self):
        # 週二 14:00 看 週二 09:00 → 下週週二
        ref = datetime(2026, 4, 28, 14, 0, tzinfo=_TZ)
        nxt = _next_weekly("2|09:00", ref)
        assert nxt == datetime(2026, 5, 5, 9, 0, tzinfo=_TZ)

    def test_invalid_weekday(self):
        ref = datetime(2026, 4, 28, 14, 0, tzinfo=_TZ)
        assert _next_weekly("0|09:00", ref) is None
        assert _next_weekly("8|09:00", ref) is None
        assert _next_weekly("abc|09:00", ref) is None
        assert _next_weekly("3|garbage", ref) is None
