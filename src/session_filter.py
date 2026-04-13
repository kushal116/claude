# src/session_filter.py
from __future__ import annotations
import logging
from datetime import datetime, time, timedelta
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# pytz is optional — we use datetime.utcnow() directly


from config import MAX_SPREAD_PIPS


class SessionFilter:
    SESSION_START = time(13, 0)
    SESSION_END   = time(17, 0)
    MAX_SPREAD_PIPS = MAX_SPREAD_PIPS
    MAX_OPEN_TRADES = 1

    def __init__(self):
        self.blocked_times: list[datetime] = []

    def is_tradeable(self, spread_pips: float,
                     open_positions: int) -> tuple:
        checks = [
            self._check_session(),
            self._check_spread(spread_pips),
            self._check_positions(open_positions),
            self._check_news_block(),
        ]
        for passed, reason in checks:
            if not passed:
                return False, reason
        return True, 'OK'

    def _check_session(self) -> tuple:
        now = datetime.utcnow().time()
        if self.SESSION_START <= now <= self.SESSION_END:
            return True, 'OK'
        return False, f"Outside session hours ({now.strftime('%H:%M')} UTC)"

    def _check_spread(self, spread_pips: float) -> tuple:
        if spread_pips <= self.MAX_SPREAD_PIPS:
            return True, 'OK'
        return False, f"Spread too wide: {spread_pips:.1f} pips"

    def _check_positions(self, open_positions: int) -> tuple:
        if open_positions < self.MAX_OPEN_TRADES:
            return True, 'OK'
        return False, f"Max positions reached: {open_positions}"

    def _check_news_block(self) -> tuple:
        now = datetime.utcnow()
        block_window = 30
        for news_time in self.blocked_times:
            delta = abs((now - news_time).total_seconds() / 60)
            if delta <= block_window:
                return False, f"News block active (within {block_window}min)"
        return True, 'OK'

    def add_news_event(self, event_time: datetime):
        self.blocked_times.append(event_time)

    def clear_news_events(self):
        self.blocked_times.clear()

    def time_until_session(self) -> str:
        now = datetime.utcnow()
        session_open = now.replace(
            hour=self.SESSION_START.hour,
            minute=self.SESSION_START.minute, second=0)
        if now.time() > self.SESSION_END:
            session_open += timedelta(days=1)
        delta = session_open - now
        hours, rem = divmod(int(delta.total_seconds()), 3600)
        mins = rem // 60
        return f"{hours}h {mins}m"


def unit_test():
    print("\nRunning SessionFilter unit tests...\n")
    f = SessionFilter()

    ok, reason = f._check_spread(0.5)
    assert ok, "Tight spread should pass"
    print("  [PASS] Tight spread passes")

    ok, reason = f._check_spread(2.5)
    assert not ok, "Wide spread should fail"
    print(f"  [PASS] Wide spread blocked: {reason}")

    ok, reason = f._check_positions(0)
    assert ok
    print("  [PASS] Zero positions passes")

    ok, reason = f._check_positions(1)
    assert not ok
    print(f"  [PASS] Max positions blocked: {reason}")

    print(f"\n  Time until next session: {f.time_until_session()}")
    print("\n[PASS] SessionFilter tests passed!\n")


if __name__ == "__main__":
    unit_test()
