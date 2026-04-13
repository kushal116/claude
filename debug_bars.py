# debug_bars.py — Analyze what the tick bars look like for XAUUSD
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from config import SYMBOL, TICK_SIZE, PIP_SIZE, MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
import MetaTrader5 as mt5

from src.tick_builder import TickBarBuilder
from src.level_detector import LevelDetector
from src.buildup_detector import BuildupDetector

PIP = PIP_SIZE

if not mt5.initialize():
    print("MT5 not running"); sys.exit(1)
mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)

rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 7200)
mt5.shutdown()

print(f"Got {len(rates)} M1 bars\n")

# Build tick bars from M1 data
builder = TickBarBuilder(tick_size=TICK_SIZE)
spread = 0.18

for rate in rates:
    bar_time = datetime.utcfromtimestamp(rate['time'])
    for price in [rate['open'], rate['high'], rate['low'], rate['close']]:
        builder.on_tick({
            'ask': price + spread/2, 'bid': price - spread/2, 'time': bar_time
        })

bars = builder.bars_as_dicts()
print(f"Built {len(bars)} tick bars\n")

if not bars:
    print("No bars built"); sys.exit(1)

# Analyze bar ranges
ranges = [(b['high'] - b['low']) / PIP for b in bars]
ranges.sort()

print(f"BAR RANGE STATISTICS (in pips, PIP={PIP}):")
print(f"  Min range    : {min(ranges):.1f} pips")
print(f"  Max range    : {max(ranges):.1f} pips")
print(f"  Avg range    : {sum(ranges)/len(ranges):.1f} pips")
print(f"  Median range : {ranges[len(ranges)//2]:.1f} pips")
print(f"  10th pctile  : {ranges[len(ranges)//10]:.1f} pips")
print(f"  90th pctile  : {ranges[9*len(ranges)//10]:.1f} pips")

# Show distribution
brackets = [(0,10), (10,20), (20,40), (40,60), (60,100),
            (100,200), (200,500), (500,10000)]
print(f"\n  RANGE DISTRIBUTION:")
for lo, hi in brackets:
    count = sum(1 for r in ranges if lo <= r < hi)
    pct = count / len(ranges) * 100
    bar = '#' * int(pct / 2)
    print(f"    {lo:4}-{hi:4} pips: {count:4} ({pct:5.1f}%) {bar}")

# Check levels
detector = LevelDetector()
levels = detector.update(bars)
print(f"\nS/R LEVELS FOUND: {len(levels)}")
for i, l in enumerate(levels[:10], 1):
    print(f"  {i}. {l}")

# Try buildup detection on different windows
bd = BuildupDetector()
print(f"\nBUILDUP DETECTOR (current params):")
print(f"  max_avg_range={bd.max_avg_range_pips}, "
      f"max_single={bd.max_single_bar_pips}, "
      f"max_level_dist={bd.max_level_distance_pips}")

buildup = bd.detect(bars, levels)
if buildup:
    print(f"  FOUND: {buildup}")
else:
    print(f"  No buildup found with current params")

# Try with looser params
for avg in [80, 120, 200]:
    bd2 = BuildupDetector(max_avg_range_pips=avg, max_single_bar_pips=avg*2,
                          max_level_distance_pips=50, max_cluster_drift_pips=100)
    b = bd2.detect(bars, levels)
    if b:
        print(f"  With max_avg={avg}: FOUND {b}")
    else:
        print(f"  With max_avg={avg}: no buildup")
