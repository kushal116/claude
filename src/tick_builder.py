# src/tick_builder.py
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TickBar:
    """Represents a single completed 70-tick OHLC bar"""

    def __init__(self, open_: float, high: float, low: float,
                 close: float, time: datetime, tick_count: int):
        self.open  = open_
        self.high  = high
        self.low   = low
        self.close = close
        self.time  = time
        self.tick_count = tick_count

    def range_pips(self) -> float:
        """Bar range in pips"""
        from config import PIP_SIZE
        return round((self.high - self.low) / PIP_SIZE, 1)

    def is_bullish(self) -> bool:
        return self.close > self.open

    def is_bearish(self) -> bool:
        return self.close < self.open

    def to_dict(self) -> dict:
        return {
            'open':       self.open,
            'high':       self.high,
            'low':        self.low,
            'close':      self.close,
            'time':       self.time,
            'tick_count': self.tick_count,
            'range_pips': self.range_pips()
        }

    def __repr__(self):
        direction = "▲" if self.is_bullish() else "▼"
        return (f"TickBar {direction} | O:{self.open:.5f} "
                f"H:{self.high:.5f} L:{self.low:.5f} "
                f"C:{self.close:.5f} | "
                f"Range:{self.range_pips()}pip | "
                f"Time:{self.time}")


class TickBarBuilder:
    """
    Aggregates raw ticks into fixed-size OHLC bars.
    Volman uses 70-tick bars for EUR/USD scalping.
    """

    def __init__(self, tick_size: int = 70, max_bars: int = 500):
        self.tick_size     = tick_size
        self.max_bars      = max_bars  # Rolling window limit
        self.completed_bars: list[TickBar] = []
        self._tick_count   = 0
        self._current_open: Optional[float] = None
        self._current_high: Optional[float] = None
        self._current_low:  Optional[float] = None
        self._current_close: Optional[float] = None
        self._bar_start_time: Optional[datetime] = None

        logger.info(f"TickBarBuilder initialized | tick_size={tick_size}")

    def on_tick(self, tick: dict) -> Optional[TickBar]:
        """
        Process a single tick.

        Args:
            tick: dict with keys: 'ask', 'bid', 'time'
                  time should be a datetime object

        Returns:
            Completed TickBar if bar just finished, else None
        """
        # Use mid price
        price = (tick['ask'] + tick['bid']) / 2
        time  = tick.get('time', datetime.utcnow())

        # First tick of a new bar
        if self._current_open is None:
            self._current_open      = price
            self._current_high      = price
            self._current_low       = price
            self._bar_start_time    = time
            logger.debug(f"New bar started at {price:.5f}")

        # Update OHLC
        self._current_high  = max(self._current_high, price)
        self._current_low   = min(self._current_low,  price)
        self._current_close = price
        self._tick_count   += 1

        # Check if bar is complete
        if self._tick_count >= self.tick_size:
            return self._close_bar()

        return None

    def _close_bar(self) -> TickBar:
        """Finalize and store the current bar"""
        bar = TickBar(
            open_      = self._current_open,
            high       = self._current_high,
            low        = self._current_low,
            close      = self._current_close,
            time       = self._bar_start_time,
            tick_count = self._tick_count
        )

        self.completed_bars.append(bar)

        # Keep rolling window — drop oldest if over limit
        if len(self.completed_bars) > self.max_bars:
            self.completed_bars.pop(0)

        logger.info(f"Bar closed: {bar}")

        # Reset for next bar
        self._reset()
        return bar

    def _reset(self):
        """Reset state for next bar"""
        self._tick_count     = 0
        self._current_open   = None
        self._current_high   = None
        self._current_low    = None
        self._current_close  = None
        self._bar_start_time = None

    def get_last_n_bars(self, n: int) -> list[TickBar]:
        """Return the last N completed bars"""
        return self.completed_bars[-n:]

    def get_latest_bar(self) -> Optional[TickBar]:
        """Return the most recently completed bar"""
        if self.completed_bars:
            return self.completed_bars[-1]
        return None

    def bars_as_dicts(self) -> list[dict]:
        """Return all bars as list of dicts (for pandas/analysis)"""
        return [b.to_dict() for b in self.completed_bars]

    def current_bar_progress(self) -> dict:
        """Shows how far through the current bar we are"""
        return {
            'ticks_in':    self._tick_count,
            'ticks_left':  self.tick_size - self._tick_count,
            'pct_complete': round(self._tick_count / self.tick_size * 100, 1),
            'current_high': self._current_high,
            'current_low':  self._current_low,
        }

    def total_bars_built(self) -> int:
        return len(self.completed_bars)

    def __repr__(self):
        return (f"TickBarBuilder | "
                f"tick_size={self.tick_size} | "
                f"bars_built={self.total_bars_built()} | "
                f"ticks_in_progress={self._tick_count}")


# ─────────────────────────────────────────────
# LIVE TEST — connects to MT5 and streams ticks
# ─────────────────────────────────────────────
def live_test():
    """Test the builder with real MT5 tick stream"""
    import MetaTrader5 as mt5
    import time

    print("\n🔌 Connecting to MT5...")
    if not mt5.initialize():
        print("❌ MT5 not running — open MetaTrader 5 first")
        return

    symbol  = "EURUSD"
    builder = TickBarBuilder(tick_size=70)

    print(f"✅ Connected | Streaming {symbol} ticks...")
    print(f"   Waiting for first bar to complete (70 ticks)...\n")

    bars_to_collect = 5  # Collect 5 bars then stop
    last_tick_time  = None

    try:
        while builder.total_bars_built() < bars_to_collect:
            tick = mt5.symbol_info_tick(symbol)

            if tick is None:
                time.sleep(0.01)
                continue

            # Only process new ticks
            if last_tick_time == tick.time:
                time.sleep(0.001)
                continue

            last_tick_time = tick.time

            tick_data = {
                'ask':  tick.ask,
                'bid':  tick.bid,
                'time': datetime.fromtimestamp(tick.time)
            }

            completed_bar = builder.on_tick(tick_data)

            if completed_bar:
                print(f"✅ Bar #{builder.total_bars_built()} complete:")
                print(f"   {completed_bar}")
                print(f"   Progress: {builder.current_bar_progress()}\n")

        print(f"\n📊 Done! Built {builder.total_bars_built()} bars")
        print(f"\nLast 3 bars:")
        for bar in builder.get_last_n_bars(3):
            print(f"  {bar}")

    except KeyboardInterrupt:
        print("\n⛔ Stopped by user")
    finally:
        mt5.shutdown()
        print("🔌 MT5 disconnected")


# ─────────────────────────────────────────────
# UNIT TEST — no MT5 needed, uses fake ticks
# ─────────────────────────────────────────────
def unit_test():
    """Test builder logic with synthetic tick data"""
    print("\n🧪 Running unit tests...\n")

    builder = TickBarBuilder(tick_size=10)  # Use 10 ticks for fast testing
    base_price = 1.08500

    # Simulate 25 ticks → should produce 2 complete bars
    for i in range(25):
        price = base_price + (i * 0.00001)
        tick  = {
            'ask':  price + 0.00010,
            'bid':  price,
            'time': datetime.utcnow()
        }
        result = builder.on_tick(tick)
        if result:
            print(f"  ✅ Bar completed: {result}")

    print(f"\n  Total bars built: {builder.total_bars_built()}")
    assert builder.total_bars_built() == 2, "Should have 2 complete bars"

    # Test get_last_n_bars
    last_2 = builder.get_last_n_bars(2)
    assert len(last_2) == 2, "Should return 2 bars"

    # Test bar properties
    bar = builder.get_latest_bar()
    assert bar.high >= bar.low,  "High must be >= Low"
    assert bar.high >= bar.open, "High must be >= Open"
    assert bar.high >= bar.close,"High must be >= Close"

    # Test progress tracking
    progress = builder.current_bar_progress()
    print(f"\n  Current bar progress: {progress}")
    assert 0 <= progress['pct_complete'] <= 100

    print("\n✅ All unit tests passed!\n")


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "unit"

    if mode == "live":
        live_test()
    else:
        unit_test()
