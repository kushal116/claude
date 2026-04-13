# src/level_detector.py
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

from config import PIP_SIZE, LEVEL_CLUSTER_PIPS, LEVEL_REACTION_THRESHOLD
PIP = PIP_SIZE


@dataclass
class Level:
    """A single support or resistance level"""
    price:      float
    level_type: str
    touches:    int  = 1
    score:      float = 0.0
    is_round:   bool = False
    bar_index:  int  = 0

    def to_dict(self) -> dict:
        return {
            'price':      self.price,
            'type':       self.level_type,
            'touches':    self.touches,
            'score':      self.score,
            'is_round':   self.is_round,
            'bar_index':  self.bar_index
        }

    def distance_pips(self, price: float) -> float:
        return abs(self.price - price) / PIP

    def __repr__(self):
        tag = "R" if self.level_type == 'resistance' else "S"
        rnd = " [ROUND]" if self.is_round else ""
        return (f"{tag} | {self.price:.5f}{rnd} | "
                f"touches={self.touches} | score={self.score:.1f}")


class LevelDetector:
    def __init__(
        self,
        swing_lookback:      int   = 3,
        cluster_pips:        float = LEVEL_CLUSTER_PIPS,
        min_score:           float = 1.0,
        max_levels:          int   = 20,
        round_number_bonus:  float = 2.0,
    ):
        self.swing_lookback     = swing_lookback
        self.cluster_pips       = cluster_pips
        self.min_score          = min_score
        self.max_levels         = max_levels
        self.round_number_bonus = round_number_bonus
        self.levels: list[Level] = []

    def update(self, bars: list[dict]) -> list[Level]:
        if len(bars) < (self.swing_lookback * 2 + 1):
            return []

        raw = self._find_swings(bars)
        raw += self._find_round_numbers(bars)
        clustered = self._cluster(raw)
        scored    = self._score(clustered, bars)
        filtered  = [l for l in scored if l.score >= self.min_score]
        sorted_levels = sorted(filtered,
                                key=lambda l: l.score,
                                reverse=True)[:self.max_levels]
        self.levels = sorted_levels
        logger.info(f"LevelDetector: found {len(self.levels)} levels")
        return self.levels

    def nearest_level(self, price: float,
                      level_type: Optional[str] = None) -> Optional[Level]:
        candidates = self.levels
        if level_type:
            candidates = [l for l in self.levels
                          if l.level_type == level_type]
        if not candidates:
            return None
        return min(candidates, key=lambda l: l.distance_pips(price))

    def levels_near_price(self, price: float,
                          within_pips: float = 5.0) -> list[Level]:
        return [l for l in self.levels
                if l.distance_pips(price) <= within_pips]

    def is_near_level(self, price: float,
                      within_pips: float = 3.0) -> bool:
        return len(self.levels_near_price(price, within_pips)) > 0

    def _find_swings(self, bars: list[dict]) -> list[Level]:
        levels = []
        n = self.swing_lookback
        for i in range(n, len(bars) - n):
            bar = bars[i]
            left_bars  = bars[i - n: i]
            right_bars = bars[i + 1: i + n + 1]

            is_swing_high = (
                all(bar['high'] > b['high'] for b in left_bars) and
                all(bar['high'] > b['high'] for b in right_bars)
            )
            if is_swing_high:
                levels.append(Level(
                    price=bar['high'], level_type='resistance', bar_index=i))

            is_swing_low = (
                all(bar['low'] < b['low'] for b in left_bars) and
                all(bar['low'] < b['low'] for b in right_bars)
            )
            if is_swing_low:
                levels.append(Level(
                    price=bar['low'], level_type='support', bar_index=i))
        return levels

    def _find_round_numbers(self, bars: list[dict]) -> list[Level]:
        if not bars:
            return []
        highs = [b['high'] for b in bars]
        lows  = [b['low']  for b in bars]
        price_high = max(highs)
        price_low  = min(lows)
        levels = []
        # XAUUSD: round at every 50 pips (e.g. 3200, 3250, 3300)
        # EURUSD: round at every 50 pips (e.g. 1.0800, 1.0850)
        round_step = PIP * 50  # 50 pips in price terms
        start = round(price_low / round_step) * round_step
        end   = round(price_high / round_step) * round_step + round_step
        current = start
        while current <= end:
            current = round(current, 5)
            if price_low <= current <= price_high:
                mid = (price_high + price_low) / 2
                ltype = 'resistance' if current > mid else 'support'
                levels.append(Level(
                    price=current, level_type=ltype,
                    is_round=True, bar_index=len(bars)))
            current += round_step
        return levels

    def _cluster(self, levels: list[Level]) -> list[Level]:
        if not levels:
            return []
        sorted_levels = sorted(levels, key=lambda l: l.price)
        clusters: list[Level] = []
        threshold = self.cluster_pips * PIP
        for level in sorted_levels:
            merged = False
            for cluster in clusters:
                if abs(level.price - cluster.price) <= threshold:
                    cluster.price   = (cluster.price + level.price) / 2
                    cluster.touches += 1
                    if level.is_round:
                        cluster.is_round = True
                    merged = True
                    break
            if not merged:
                clusters.append(Level(
                    price=level.price, level_type=level.level_type,
                    touches=level.touches, is_round=level.is_round,
                    bar_index=level.bar_index))
        return clusters

    def _score(self, levels: list[Level], bars: list[dict]) -> list[Level]:
        total_bars = len(bars)
        for level in levels:
            score = 0.0
            score += level.touches * 1.5
            recency_ratio = level.bar_index / max(total_bars, 1)
            score += recency_ratio * 3.0
            if level.is_round:
                score += self.round_number_bonus
            reaction = self._measure_reaction(level, bars)
            score += reaction
            level.score = round(score, 2)
        return levels

    def _measure_reaction(self, level: Level, bars: list[dict]) -> float:
        reactions = []
        threshold = LEVEL_REACTION_THRESHOLD * PIP
        for i, bar in enumerate(bars):
            touched = (
                abs(bar['high'] - level.price) <= threshold or
                abs(bar['low']  - level.price) <= threshold
            )
            if touched and i + 3 < len(bars):
                future_bars = bars[i + 1: i + 4]
                future_high = max(b['high'] for b in future_bars)
                future_low  = min(b['low']  for b in future_bars)
                move = (future_high - future_low) / PIP
                reactions.append(move)
        if not reactions:
            return 0.0
        avg_reaction = sum(reactions) / len(reactions)
        return min(avg_reaction / 10.0 * 3.0, 3.0)

    def print_levels(self):
        print(f"\n{'='*55}")
        print(f"  DETECTED LEVELS ({len(self.levels)} total)")
        print(f"{'='*55}")
        for i, level in enumerate(self.levels, 1):
            print(f"  {i:2}. {level}")
        print(f"{'='*55}\n")

    def levels_as_dicts(self) -> list[dict]:
        return [l.to_dict() for l in self.levels]


def unit_test():
    print("\nRunning LevelDetector unit tests...\n")
    bars = []
    prices = [
        1.0850, 1.0855, 1.0860, 1.0870, 1.0880,
        1.0895, 1.0900, 1.0895, 1.0880, 1.0870,
        1.0860, 1.0850, 1.0840, 1.0830, 1.0820,
        1.0810, 1.0800, 1.0810, 1.0820, 1.0830,
        1.0840, 1.0850, 1.0860, 1.0870, 1.0880,
    ]
    for i, p in enumerate(prices):
        bars.append({
            'open': p - 0.0003, 'high': p + 0.0005,
            'low':  p - 0.0005, 'close': p + 0.0002,
        })
    detector = LevelDetector()
    levels   = detector.update(bars)
    print(f"  Found {len(levels)} levels")
    detector.print_levels()
    nearest = detector.nearest_level(1.0902)
    print(f"  Nearest level to 1.0902: {nearest}")
    assert len(levels) > 0, "Should detect at least some levels"
    print("\n[PASS] All LevelDetector tests passed!\n")


if __name__ == "__main__":
    unit_test()
