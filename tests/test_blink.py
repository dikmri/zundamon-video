from zvideo.timeline import blink_times


def test_blinks_are_deterministic_for_same_seed():
    assert blink_times(60.0, seed="zundamon") == blink_times(60.0, seed="zundamon")


def test_different_characters_blink_at_different_times():
    assert blink_times(60.0, seed="zundamon") != blink_times(60.0, seed="metan")


def test_blink_intervals_stay_in_natural_range():
    times = blink_times(120.0, seed="x", min_gap=2.5, max_gap=5.5)
    assert 0 < times[0] <= 5.5
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert all(2.5 <= g <= 5.5 for g in gaps)
    assert times[-1] < 120.0
