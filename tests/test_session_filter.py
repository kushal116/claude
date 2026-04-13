# tests/test_session_filter.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.session_filter import SessionFilter
from datetime import datetime, timedelta


def test_tight_spread_passes():
    f = SessionFilter()
    ok, reason = f._check_spread(0.5)
    assert ok, "Tight spread should pass"


def test_wide_spread_blocked():
    f = SessionFilter()
    ok, reason = f._check_spread(30.0)  # Above MAX_SPREAD_PIPS (25 for gold)
    assert not ok, "Wide spread should be blocked"
    assert "Spread" in reason


def test_zero_positions_passes():
    f = SessionFilter()
    ok, reason = f._check_positions(0)
    assert ok, "Zero positions should pass"


def test_max_positions_blocked():
    f = SessionFilter()
    ok, reason = f._check_positions(1)
    assert not ok, "Should block when at max positions"


def test_news_block():
    f = SessionFilter()
    now = datetime.utcnow()
    f.add_news_event(now + timedelta(minutes=5))  # News in 5 min
    ok, reason = f._check_news_block()
    assert not ok, "Should block near news events"


def test_no_news_passes():
    f = SessionFilter()
    ok, reason = f._check_news_block()
    assert ok, "Should pass when no news events"


def test_clear_news_events():
    f = SessionFilter()
    f.add_news_event(datetime.utcnow())
    f.clear_news_events()
    assert len(f.blocked_times) == 0


def test_time_until_session():
    f = SessionFilter()
    result = f.time_until_session()
    assert 'h' in result and 'm' in result
