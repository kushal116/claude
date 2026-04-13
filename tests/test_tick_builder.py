# tests/test_tick_builder.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from src.tick_builder import TickBarBuilder


def _make_tick(price, spread=0.00010):
    return {'ask': price + spread, 'bid': price, 'time': datetime.utcnow()}


def test_bar_completes_at_tick_size():
    builder = TickBarBuilder(tick_size=10)
    result = None
    for i in range(10):
        result = builder.on_tick(_make_tick(1.08500 + i * 0.00001))
    assert result is not None, "Bar should complete after 10 ticks"
    assert builder.total_bars_built() == 1


def test_no_bar_before_tick_size():
    builder = TickBarBuilder(tick_size=10)
    for i in range(9):
        result = builder.on_tick(_make_tick(1.08500))
        assert result is None, "Bar should not complete before tick_size"


def test_multiple_bars():
    builder = TickBarBuilder(tick_size=5)
    bars_built = 0
    for i in range(17):
        result = builder.on_tick(_make_tick(1.08500 + i * 0.00001))
        if result:
            bars_built += 1
    assert bars_built == 3, f"Expected 3 bars from 17 ticks, got {bars_built}"
    assert builder.total_bars_built() == 3


def test_ohlc_values():
    builder = TickBarBuilder(tick_size=5)
    prices = [1.0850, 1.0860, 1.0840, 1.0855, 1.0852]
    bar = None
    for p in prices:
        bar = builder.on_tick(_make_tick(p))
    assert bar is not None
    # Mid prices: each is price + spread/2 = price + 0.00005
    assert bar.high >= bar.low
    assert bar.high >= bar.open
    assert bar.high >= bar.close


def test_rolling_window():
    builder = TickBarBuilder(tick_size=2, max_bars=3)
    for i in range(10):
        builder.on_tick(_make_tick(1.0850 + i * 0.0001))
    assert builder.total_bars_built() == 3, "Should cap at max_bars"


def test_get_last_n_bars():
    builder = TickBarBuilder(tick_size=3)
    for i in range(12):
        builder.on_tick(_make_tick(1.0850 + i * 0.0001))
    last_2 = builder.get_last_n_bars(2)
    assert len(last_2) == 2


def test_current_bar_progress():
    builder = TickBarBuilder(tick_size=10)
    for i in range(4):
        builder.on_tick(_make_tick(1.0850))
    progress = builder.current_bar_progress()
    assert progress['ticks_in'] == 4
    assert progress['ticks_left'] == 6
    assert progress['pct_complete'] == 40.0


def test_bar_is_bullish_bearish():
    builder = TickBarBuilder(tick_size=3)
    # Rising prices -> bullish
    for p in [1.0850, 1.0855, 1.0860]:
        bar = builder.on_tick(_make_tick(p))
    assert bar.is_bullish()
    assert not bar.is_bearish()
