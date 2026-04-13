# tests/test_buildup_detector.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.buildup_detector import BuildupDetector
from src.level_detector import Level


def _tight_bars_near_level(base=1.0893, count=10):
    """Tight bars just below a resistance level"""
    bars = []
    for i in range(count):
        bars.append({
            'open':  base + 0.00002 * i,
            'high':  base + 0.00003 * i + 0.00020,
            'low':   base + 0.00002 * i - 0.00020,
            'close': base + 0.00002 * i + 0.00010,
        })
    return bars


def test_detects_valid_buildup():
    level = Level(price=1.0900, level_type='resistance', touches=3, score=5.0)
    bars = _tight_bars_near_level()
    detector = BuildupDetector(
        max_avg_range_pips=40.0, max_single_bar_pips=70.0,
        max_level_distance_pips=15.0, max_cluster_drift_pips=50.0)
    result = detector.detect(bars, [level])
    assert result is not None, "Should detect a valid buildup"
    assert result.bar_count >= 6
    assert result.direction in ('long', 'short')


def test_rejects_wide_bars():
    level = Level(price=3200.00, level_type='resistance', touches=3, score=5.0)
    wide_bars = []
    for i in range(10):
        wide_bars.append({
            'open': 3190.00, 'high': 3210.00,  # 2000 pip range for gold
            'low': 3190.00, 'close': 3200.00,
        })
    detector = BuildupDetector(
        max_avg_range_pips=40.0, max_single_bar_pips=70.0,
        max_level_distance_pips=15.0, max_cluster_drift_pips=50.0)
    result = detector.detect(wide_bars, [level])
    assert result is None, "Wide bars should not form a valid buildup"


def test_rejects_no_levels():
    bars = _tight_bars_near_level()
    detector = BuildupDetector()
    result = detector.detect(bars, [])
    assert result is None, "Should reject when no levels provided"


def test_rejects_too_few_bars():
    level = Level(price=1.0900, level_type='resistance', touches=3, score=5.0)
    bars = _tight_bars_near_level(count=3)
    detector = BuildupDetector(min_bars=6)
    result = detector.detect(bars, [level])
    assert result is None, "Should reject with fewer bars than min_bars"


def test_buildup_direction_long():
    level = Level(price=1.0900, level_type='resistance', touches=3, score=5.0)
    # Bars below the level -> direction should be 'long'
    bars = _tight_bars_near_level(base=1.0893)
    detector = BuildupDetector(
        max_avg_range_pips=40.0, max_single_bar_pips=70.0,
        max_level_distance_pips=15.0, max_cluster_drift_pips=50.0)
    result = detector.detect(bars, [level])
    if result:
        assert result.direction == 'long'


def test_buildup_quality_score():
    level = Level(price=1.0900, level_type='resistance', touches=3, score=5.0)
    bars = _tight_bars_near_level()
    detector = BuildupDetector(
        max_avg_range_pips=40.0, max_single_bar_pips=70.0,
        max_level_distance_pips=15.0, max_cluster_drift_pips=50.0)
    result = detector.detect(bars, [level])
    if result:
        assert result.quality_score > 0, "Quality score should be positive"
