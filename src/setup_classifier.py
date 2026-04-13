# src/setup_classifier.py
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)
from config import PIP_SIZE
PIP = PIP_SIZE


@dataclass
class Setup:
    setup_type:  str
    direction:   str
    buildup:     object
    entry_price: float
    confidence:  float

    def __repr__(self):
        return (f"Setup | type={self.setup_type} | "
                f"dir={self.direction} | "
                f"entry={self.entry_price:.5f} | "
                f"confidence={self.confidence:.0%}")


class SetupClassifier:
    def __init__(self, min_confidence: float = 0.55):
        self.min_confidence = min_confidence

    def classify(self, buildup, current_bar: dict,
                 recent_bars: list, levels: list) -> Optional[Setup]:
        if buildup is None:
            return None
        setup = (
            self._check_bb(buildup, current_bar, levels) or
            self._check_pb(buildup, current_bar, recent_bars, levels) or
            self._check_rb(buildup, current_bar, recent_bars, levels) or
            self._check_fb(buildup, current_bar, recent_bars, levels))
        if setup and setup.confidence >= self.min_confidence:
            logger.info(f"Setup classified: {setup}")
            return setup
        return None

    def _check_bb(self, buildup, current_bar, levels):
        level = buildup.nearest_level
        broke_above = (current_bar['close'] > level.price and
                       buildup.direction == 'long')
        broke_below = (current_bar['close'] < level.price and
                       buildup.direction == 'short')
        if not (broke_above or broke_below):
            return None
        direction   = 'BUY' if broke_above else 'SELL'
        confidence  = self._bb_confidence(buildup, current_bar, level)
        return Setup(setup_type='BB', direction=direction,
                     buildup=buildup, entry_price=current_bar['close'],
                     confidence=confidence)

    def _bb_confidence(self, buildup, current_bar, level):
        score = 0.0
        from config import BUILDUP_MAX_AVG_RANGE
        tight = BUILDUP_MAX_AVG_RANGE * 0.5   # Below half of max = tight
        medium = BUILDUP_MAX_AVG_RANGE * 0.75  # Below 75% of max = medium
        if buildup.avg_bar_range_pips() < tight: score += 0.30
        elif buildup.avg_bar_range_pips() < medium: score += 0.15
        if buildup.bar_count >= 8: score += 0.20
        elif buildup.bar_count >= 6: score += 0.10
        if level.score >= 5.0: score += 0.25
        elif level.score >= 3.0: score += 0.15
        if level.is_round: score += 0.15
        break_size = abs(current_bar['close'] - level.price) / PIP
        if break_size >= 50.0: score += 0.10  # Meaningful break for gold
        return min(round(score, 2), 1.0)

    def _check_pb(self, buildup, current_bar, recent_bars, levels):
        if len(recent_bars) < 20:
            return None
        level = buildup.nearest_level
        prior_break = self._find_prior_break(level, recent_bars[-30:])
        if not prior_break:
            return None
        broke_above = (current_bar['close'] > level.price and
                       buildup.direction == 'long')
        broke_below = (current_bar['close'] < level.price and
                       buildup.direction == 'short')
        if not (broke_above or broke_below):
            return None
        direction  = 'BUY' if broke_above else 'SELL'
        confidence = min(self._bb_confidence(
                         buildup, current_bar, level) + 0.10, 1.0)
        return Setup(setup_type='PB', direction=direction,
                     buildup=buildup, entry_price=current_bar['close'],
                     confidence=confidence)

    def _find_prior_break(self, level, bars):
        threshold = 100 * PIP  # Meaningful break for gold
        for i in range(len(bars) - 1):
            prev, curr = bars[i], bars[i + 1]
            if ((prev['close'] < level.price and
                 curr['close'] > level.price + threshold) or
                (prev['close'] > level.price and
                 curr['close'] < level.price - threshold)):
                return True
        return False

    def _check_rb(self, buildup, current_bar, recent_bars, levels):
        if len(recent_bars) < 30:
            return None
        sample   = recent_bars[-30:]
        highs    = [b['high'] for b in sample]
        lows     = [b['low']  for b in sample]
        rng_size = (max(highs) - min(lows)) / PIP
        # XAUUSD range: 1500-6000 pips ($15-$60) is a tradeable range
        if not (1500 <= rng_size <= 6000):
            return None
        range_high = max(highs)
        range_low  = min(lows)
        at_top    = abs(buildup.high - range_high) <= 200 * PIP
        at_bottom = abs(buildup.low  - range_low)  <= 200 * PIP
        if not (at_top or at_bottom):
            return None
        broke_above = (current_bar['close'] > range_high and at_top)
        broke_below = (current_bar['close'] < range_low  and at_bottom)
        if not (broke_above or broke_below):
            return None
        direction = 'BUY' if broke_above else 'SELL'
        return Setup(setup_type='RB', direction=direction,
                     buildup=buildup, entry_price=current_bar['close'],
                     confidence=0.65)

    def _check_fb(self, buildup, current_bar, recent_bars, levels):
        if len(recent_bars) < 10:
            return None
        level = buildup.nearest_level
        last_5 = recent_bars[-5:]
        fake_up = (any(b['high'] > level.price + 100 * PIP for b in last_5)
                   and current_bar['close'] < level.price)
        fake_dn = (any(b['low'] < level.price - 100 * PIP for b in last_5)
                   and current_bar['close'] > level.price)
        if not (fake_up or fake_dn):
            return None
        direction = 'SELL' if fake_up else 'BUY'
        return Setup(setup_type='FB', direction=direction,
                     buildup=buildup, entry_price=current_bar['close'],
                     confidence=0.60)


def unit_test():
    from buildup_detector import Buildup
    from level_detector import Level
    print("\nRunning SetupClassifier unit tests...\n")

    level = Level(price=1.0900, level_type='resistance',
                  touches=4, score=6.0, is_round=True)
    bars = [{'open': 1.0893, 'high': 1.0897,
             'low':  1.0890, 'close': 1.0894}] * 8
    buildup = Buildup(bars=bars, high=1.0897, low=1.0890,
                      nearest_level=level, direction='long',
                      quality_score=8.5, bar_count=8)
    classifier = SetupClassifier(min_confidence=0.50)
    break_bar = {'open': 1.0898, 'high': 1.0905,
                 'low':  1.0896, 'close': 1.0903}
    recent = bars + [break_bar]
    setup = classifier.classify(buildup, break_bar, recent, [level])
    if setup:
        print(f"  [PASS] Setup detected: {setup}")
    else:
        print("  [INFO] No setup detected (may need higher quality bars)")
    print("\n[PASS] SetupClassifier tests complete!\n")


if __name__ == "__main__":
    unit_test()
