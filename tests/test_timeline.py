import pytest

from zvideo.timeline import Timing, build_timeline

T = Timing(lead_in=0.5, scene_lead=0.4, gap=0.3, scene_tail=0.6, outro=2.0)


def test_lines_are_placed_back_to_back_with_gap():
    tl = build_timeline([{"lines": [{"duration": 1.0}, {"duration": 2.0}]}], T)
    s = tl["scenes"][0]
    assert s["start"] == pytest.approx(0.5)
    assert [(l["start"], l["end"]) for l in s["lines"]] == [
        pytest.approx((0.9, 1.9)), pytest.approx((2.2, 4.2))]
    assert s["end"] == pytest.approx(4.8)
    assert tl["total"] == pytest.approx(6.8)


def test_line_pause_overrides_gap_after_that_line():
    tl = build_timeline([{"lines": [{"duration": 1.0, "pause": 1.0}, {"duration": 1.0}]}], T)
    assert tl["scenes"][0]["lines"][1]["start"] == pytest.approx(0.9 + 1.0 + 1.0)


def test_negative_pause_lets_next_line_overlap():
    tl = build_timeline([{"lines": [{"duration": 1.0, "pause": -0.2}, {"duration": 1.0}]}], T)
    assert tl["scenes"][0]["lines"][1]["start"] == pytest.approx(1.7)


def test_next_scene_starts_where_previous_scene_ends():
    tl = build_timeline([{"lines": [{"duration": 1.0}]}, {"lines": [{"duration": 1.0}]}], T)
    a, b = tl["scenes"]
    assert b["start"] == pytest.approx(a["end"])
    assert b["lines"][0]["start"] == pytest.approx(b["start"] + 0.4)


def test_scene_without_lines_uses_its_duration():
    tl = build_timeline([{"duration": 3.0, "lines": []}], T)
    assert (tl["scenes"][0]["start"], tl["scenes"][0]["end"]) == pytest.approx((0.5, 3.5))


def test_scene_min_duration_extends_short_scene():
    tl = build_timeline([{"duration": 5.0, "lines": [{"duration": 1.0}]}], T)
    assert tl["scenes"][0]["end"] == pytest.approx(5.5)


def test_steps_reveal_at_first_line_that_requests_them():
    tl = build_timeline([{"lines": [{"duration": 1.0, "step": 1},
                                    {"duration": 1.0, "step": 2},
                                    {"duration": 1.0, "step": 1}]}], T)
    steps = tl["scenes"][0]["steps"]
    assert (steps[1], steps[2]) == pytest.approx((0.9, 2.2))


def test_step_zero_is_visible_from_scene_start():
    tl = build_timeline([{"lines": [{"duration": 1.0, "step": 1}]}], T)
    assert tl["scenes"][0]["steps"][0] == pytest.approx(0.5)


def test_scene_without_lines_requires_duration():
    with pytest.raises(ValueError):
        build_timeline([{"lines": []}], T)


def test_step_end_records_when_the_revealing_line_finishes():
    tl = build_timeline([{"lines": [{"duration": 1.0, "step": 1}, {"duration": 2.0, "step": 2}]}], T)
    ends = tl["scenes"][0]["steps_end"]
    assert (ends[1], ends[2]) == pytest.approx((1.9, 4.2))
