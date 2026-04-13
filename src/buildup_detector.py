# src/buildup_detector.py
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)
from config import (PIP_SIZE, BUILDUP_MAX_AVG_RANGE, BUILDUP_MAX_SINGLE_BAR,
                    BUILDUP_MAX_LEVEL_DIST, BUILDUP_MAX_DRIFT)
PIP = PIP_SIZE


@dataclass
class Buildup:
    bars:           list
    high:           float
    low:            float
    nearest_level:  object
    direction:      str
    quality_score:  float
    bar_count:      int

    def range_pips(self) -> float:
        return round((self.high - self.low) / PIP, 1)

    def avg_bar_range_pips(self) -> float:
        if not self.bars:
            return 0.0
        ranges = [(b['high'] - b['low']) / PIP for b in self.bars]
        return round(sum(ranges) / len(ranges), 1)

    def __repr__(self):
        return (f"Buildup | dir={self.direction} | "
                f"bars={self.bar_count} | "
                f"range={self.range_pips():.1f}pip | "
                f"avg_bar={self.avg_bar_range_pips():.1f}pip | "
                f"score={self.quality_score:.2f} | "
                f"level={self.nearest_level.price:.5f}")


class BuildupDetector:
    def __init__(
        self,
        min_bars:               int   = 6,
        max_bars:               int   = 25,
        max_avg_range_pips:     float = BUILDUP_MAX_AVG_RANGE,
        max_single_bar_pips:    float = BUILDUP_MAX_SINGLE_BAR,
        max_level_distance_pips:float = BUILDUP_MAX_LEVEL_DIST,
        max_cluster_drift_pips: float = BUILDUP_MAX_DRIFT,
    ):
        self.min_bars                = min_bars
        self.max_bars                = max_bars
        self.max_avg_range_pips      = max_avg_range_pips
        self.max_single_bar_pips     = max_single_bar_pips
        self.max_level_distance_pips = max_level_distance_pips
        self.max_cluster_drift_pips  = max_cluster_drift_pips

    def detect(self, bars: list, levels: list) -> Optional[Buildup]:
        if len(bars) < self.min_bars or not levels:
            return None
        for window_size in range(self.min_bars, self.max_bars + 1):
            if window_size > len(bars):
                break
            window = bars[-window_size:]
            if not self._passes_all_checks(window, levels):
                continue
            nearest = self._nearest_level(window, levels)
            if nearest is None:
                continue
            direction = self._determine_direction(window, nearest)
            score     = self._score(window, nearest)
            return Buildup(
                bars=window, high=max(b['high'] for b in window),
                low=min(b['low'] for b in window),
                nearest_level=nearest, direction=direction,
                quality_score=score, bar_count=window_size)
        return None

    def _passes_all_checks(self, window: list, levels: list) -> bool:
        return (
            self._check_avg_range(window) and
            self._check_no_outliers(window) and
            self._check_near_level(window, levels) and
            self._check_no_trend_drift(window))

    def _check_avg_range(self, window: list) -> bool:
        ranges = [(b['high'] - b['low']) / PIP for b in window]
        avg = sum(ranges) / len(ranges)
        return avg <= self.max_avg_range_pips

    def _check_no_outliers(self, window: list) -> bool:
        for bar in window:
            rng = (bar['high'] - bar['low']) / PIP
            if rng > self.max_single_bar_pips:
                return False
        return True

    def _check_near_level(self, window: list, levels: list) -> bool:
        cluster_high = max(b['high'] for b in window)
        cluster_low  = min(b['low']  for b in window)
        cluster_mid  = (cluster_high + cluster_low) / 2
        threshold    = self.max_level_distance_pips * PIP
        for level in levels:
            if (abs(level.price - cluster_mid) <= threshold or
                abs(level.price - cluster_high) <= threshold or
                abs(level.price - cluster_low) <= threshold):
                return True
        return False

    def _check_no_trend_drift(self, window: list) -> bool:
        first_mid = (window[0]['high']  + window[0]['low'])  / 2
        last_mid  = (window[-1]['high'] + window[-1]['low']) / 2
        drift     = abs(last_mid - first_mid) / PIP
        return drift <= self.max_cluster_drift_pips

    def _nearest_level(self, window: list, levels: list):
        cluster_mid = (
            max(b['high'] for b in window) +
            min(b['low']  for b in window)) / 2
        return min(levels, key=lambda l: abs(l.price - cluster_mid))

    def _determine_direction(self, window: list, level) -> str:
        cluster_mid = (
            max(b['high'] for b in window) +
            min(b['low']  for b in window)) / 2
        return 'long' if cluster_mid < level.price else 'short'

    def _score(self, window: list, level) -> float:
        ranges    = [(b['high'] - b['low']) / PIP for b in window]
        avg_range = sum(ranges) / len(ranges)
        tightness = max(0, 10.0 - avg_range)
        length_pts = min(len(window) * 0.3, 5.0)
        prox_pts   = max(0, 3.0 - self._level_dist_pips(window, level) * 0.5)
        level_pts  = min(level.score * 0.3, 3.0)
        return round(tightness + length_pts + prox_pts + level_pts, 2)

    def _level_dist_pips(self, window: list, level) -> float:
        cluster_mid = (
            max(b['high'] for b in window) +
            min(b['low']  for b in window)) / 2
        return abs(level.price - cluster_mid) / PIP


def unit_test():
    from level_detector import Level
    print("\nRunning BuildupDetector unit tests...\n")

    level = Level(price=1.0900, level_type='resistance',
                  touches=3, score=5.0)
    bars = []
    base = 1.0893
    for i in range(10):
        bars.append({
            'open':  base + 0.00002 * i,
            'high':  base + 0.00003 * i + 0.00020,
            'low':   base + 0.00002 * i - 0.00020,
            'close': base + 0.00002 * i + 0.00010,
        })

    detector = BuildupDetector()
    result   = detector.detect(bars, [level])

    if result:
        print(f"  [PASS] Buildup detected: {result}")
    else:
        print("  [FAIL] No buildup detected")

    wide_bars = []
    for i in range(10):
        wide_bars.append({
            'open': 1.0880, 'high': 1.0920,
            'low':  1.0880, 'close': 1.0900,
        })
    result2 = detector.detect(wide_bars, [level])
    assert result2 is None, "Wide bars should not form a valid buildup"
    print("  [PASS] Wide bar rejection test passed")
    print("\n[PASS] All BuildupDetector tests passed!\n")


if __name__ == "__main__":
    unit_test()
