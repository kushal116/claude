# src/risk_engine.py
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)
from config import PIP_SIZE, PIP_VALUE
PIP = PIP_SIZE


@dataclass
class TradeParams:
    direction:   str
    entry:       float
    stop:        float
    target:      float
    lot_size:    float
    risk_pips:   float
    reward_pips: float
    risk_reward: float
    risk_amount: float

    def __repr__(self):
        return (f"TradeParams | {self.direction} | "
                f"entry={self.entry:.5f} | "
                f"stop={self.stop:.5f} ({self.risk_pips:.1f}pip) | "
                f"target={self.target:.5f} ({self.reward_pips:.1f}pip) | "
                f"lots={self.lot_size} | "
                f"RR={self.risk_reward:.2f} | "
                f"risk=${self.risk_amount:.2f}")


class RiskEngine:
    # Target pips — Gold moves more than forex
    TARGETS = {'BB': 50.0, 'PB': 50.0, 'RB': 60.0, 'FB': 40.0}
    STOP_BUFFER_PIPS = 2.0
    PIP_VALUE_USD    = PIP_VALUE
    MIN_RR           = 0.70
    MAX_LOT_SIZE     = 5.0

    def __init__(self, account_balance: float, risk_pct: float = 1.0):
        self.account_balance = account_balance
        self.risk_pct        = risk_pct
        logger.info(f"RiskEngine | balance=${account_balance} | risk={risk_pct}%")

    def calculate(self, setup) -> Optional[TradeParams]:
        buildup   = setup.buildup
        direction = setup.direction
        entry     = setup.entry_price

        stop   = self._calc_stop(buildup, direction, entry)
        target = self._calc_target(setup.setup_type, direction, entry)

        risk_pips   = abs(entry - stop)   / PIP
        reward_pips = abs(target - entry) / PIP

        if risk_pips <= 0:
            return None

        rr = reward_pips / risk_pips
        if rr < self.MIN_RR:
            logger.info(f"R:R {rr:.2f} below minimum {self.MIN_RR}, skip")
            return None

        risk_amount = self.account_balance * (self.risk_pct / 100)
        lot_size    = self._calc_lot_size(risk_amount, risk_pips)

        return TradeParams(
            direction=direction, entry=entry, stop=stop, target=target,
            lot_size=lot_size, risk_pips=round(risk_pips, 1),
            reward_pips=round(reward_pips, 1),
            risk_reward=round(rr, 2),
            risk_amount=round(risk_amount, 2))

    def _calc_stop(self, buildup, direction, entry):
        buffer = self.STOP_BUFFER_PIPS * PIP
        if direction == 'BUY':
            return round(buildup.low - buffer, 5)
        else:
            return round(buildup.high + buffer, 5)

    def _calc_target(self, setup_type, direction, entry):
        target_pips = self.TARGETS.get(setup_type, 10.0) * PIP
        if direction == 'BUY':
            return round(entry + target_pips, 5)
        else:
            return round(entry - target_pips, 5)

    def _calc_lot_size(self, risk_amount, risk_pips):
        if risk_pips <= 0:
            return 0.01
        lot = risk_amount / (risk_pips * self.PIP_VALUE_USD)
        lot = max(0.01, min(lot, self.MAX_LOT_SIZE))
        return round(lot, 2)

    def update_balance(self, new_balance: float):
        self.account_balance = new_balance


def unit_test():
    from setup_classifier import Setup
    from buildup_detector import Buildup
    from level_detector import Level
    print("\nRunning RiskEngine unit tests...\n")

    level = Level(price=1.0900, level_type='resistance', touches=3, score=5.0)
    bars  = [{'open': 1.0893, 'high': 1.0897,
              'low':  1.0889, 'close': 1.0894}] * 8
    buildup = Buildup(bars=bars, high=1.0897, low=1.0889,
                      nearest_level=level, direction='long',
                      quality_score=8.0, bar_count=8)
    setup = Setup(setup_type='BB', direction='BUY',
                  buildup=buildup, entry_price=1.09015, confidence=0.75)

    engine = RiskEngine(account_balance=10000, risk_pct=1.0)
    params = engine.calculate(setup)

    if params:
        print(f"  [PASS] Trade params: {params}")
        assert params.stop < params.entry
        assert params.target > params.entry
        assert params.lot_size > 0
        assert params.risk_reward >= 0.7
    else:
        print("  [FAIL] No params returned")
    print("\n[PASS] RiskEngine tests passed!\n")


if __name__ == "__main__":
    unit_test()
