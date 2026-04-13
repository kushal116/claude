# tests/test_risk_engine.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.risk_engine import RiskEngine
from src.setup_classifier import Setup
from src.buildup_detector import Buildup
from src.level_detector import Level


def _make_setup(setup_type='BB', direction='BUY', entry=1.09015):
    level = Level(price=1.0900, level_type='resistance', touches=3, score=5.0)
    bars = [{'open': 1.0893, 'high': 1.0897,
             'low': 1.0889, 'close': 1.0894}] * 8
    buildup = Buildup(
        bars=bars, high=1.0897, low=1.0889,
        nearest_level=level, direction='long',
        quality_score=8.0, bar_count=8)
    return Setup(
        setup_type=setup_type, direction=direction,
        buildup=buildup, entry_price=entry, confidence=0.75)


def test_calculates_trade_params():
    engine = RiskEngine(account_balance=10000, risk_pct=1.0)
    setup = _make_setup()
    params = engine.calculate(setup)
    assert params is not None, "Should return trade params"
    assert params.direction == 'BUY'
    assert params.lot_size > 0
    assert params.risk_pips > 0
    assert params.reward_pips > 0


def test_buy_stop_below_entry():
    engine = RiskEngine(account_balance=10000, risk_pct=1.0)
    setup = _make_setup(direction='BUY')
    params = engine.calculate(setup)
    if params:
        assert params.stop < params.entry, "Stop must be below entry for BUY"
        assert params.target > params.entry, "Target must be above entry for BUY"


def test_rr_minimum():
    engine = RiskEngine(account_balance=10000, risk_pct=1.0)
    setup = _make_setup()
    params = engine.calculate(setup)
    if params:
        assert params.risk_reward >= 0.7, "R:R must meet minimum"


def test_lot_size_capped():
    # Huge balance to test cap
    engine = RiskEngine(account_balance=10_000_000, risk_pct=10.0)
    setup = _make_setup()
    params = engine.calculate(setup)
    if params:
        assert params.lot_size <= 5.0, "Lot size should be capped"


def test_risk_amount():
    engine = RiskEngine(account_balance=10000, risk_pct=1.0)
    setup = _make_setup()
    params = engine.calculate(setup)
    if params:
        assert params.risk_amount == 100.0, "1% of 10000 = 100"


def test_update_balance():
    engine = RiskEngine(account_balance=10000, risk_pct=1.0)
    engine.update_balance(20000)
    assert engine.account_balance == 20000


def test_different_setup_types():
    engine = RiskEngine(account_balance=10000, risk_pct=1.0)
    for stype in ['BB', 'PB', 'RB', 'FB']:
        setup = _make_setup(setup_type=stype)
        params = engine.calculate(setup)
        # All should produce valid params (or None if R:R too low)
        if params:
            assert params.reward_pips > 0
