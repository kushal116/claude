# tests/test_setup_classifier.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.setup_classifier import SetupClassifier
from src.buildup_detector import Buildup
from src.level_detector import Level


def _make_buildup(direction='long', bar_count=8):
    level = Level(price=1.0900, level_type='resistance',
                  touches=4, score=6.0, is_round=True)
    bars = [{
        'open': 1.0893, 'high': 1.0897,
        'low': 1.0890, 'close': 1.0894
    }] * bar_count
    return Buildup(
        bars=bars, high=1.0897, low=1.0890,
        nearest_level=level, direction=direction,
        quality_score=8.5, bar_count=bar_count
    ), level


def test_bb_detected_on_break_above():
    buildup, level = _make_buildup(direction='long')
    classifier = SetupClassifier(min_confidence=0.50)
    break_bar = {
        'open': 1.0898, 'high': 1.0905,
        'low': 1.0896, 'close': 1.0903
    }
    recent = buildup.bars + [break_bar]
    setup = classifier.classify(buildup, break_bar, recent, [level])
    assert setup is not None, "Should detect a BB setup"
    assert setup.setup_type == 'BB'
    assert setup.direction == 'BUY'


def test_no_setup_without_break():
    buildup, level = _make_buildup(direction='long')
    classifier = SetupClassifier(min_confidence=0.50)
    # Bar closes below the level -- no break
    no_break_bar = {
        'open': 1.0893, 'high': 1.0897,
        'low': 1.0890, 'close': 1.0894
    }
    recent = buildup.bars + [no_break_bar]
    setup = classifier.classify(buildup, no_break_bar, recent, [level])
    assert setup is None, "Should not detect setup without price break"


def test_no_setup_without_buildup():
    classifier = SetupClassifier()
    bar = {'open': 1.09, 'high': 1.095, 'low': 1.085, 'close': 1.09}
    setup = classifier.classify(None, bar, [bar] * 10, [])
    assert setup is None


def test_confidence_threshold():
    buildup, level = _make_buildup(direction='long')
    # Very high threshold -- should reject
    classifier = SetupClassifier(min_confidence=0.99)
    break_bar = {
        'open': 1.0898, 'high': 1.0905,
        'low': 1.0896, 'close': 1.0903
    }
    recent = buildup.bars + [break_bar]
    setup = classifier.classify(buildup, break_bar, recent, [level])
    assert setup is None, "Should reject when confidence below threshold"
