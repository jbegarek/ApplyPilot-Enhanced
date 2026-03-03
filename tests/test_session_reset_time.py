from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from applypilot.session import estimate_reset_time


def test_estimate_reset_time_parses_clock_and_timezone() -> None:
    msg = "You've hit your limit · resets 9pm (America/New_York)."
    reset_at = estimate_reset_time(msg)

    assert reset_at is not None

    reset_dt = datetime.fromisoformat(reset_at)
    local = reset_dt.astimezone(ZoneInfo("America/New_York"))

    assert local.hour == 21
    assert local.minute == 0
