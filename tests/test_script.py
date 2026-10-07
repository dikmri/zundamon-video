import pytest

from zvideo.script import ScriptError, normalize_script

CAST = {"zundamon": {"character": "zundamon"}, "metan": {"character": "metan"}}


def test_defaults_are_filled_in():
    s = normalize_script({"cast": CAST, "scenes": [{"lines": [{"who": "zundamon", "text": "なのだ"}]}]})
    assert s["meta"]["fps"] == 30
    assert (s["meta"]["width"], s["meta"]["height"]) == (1920, 1080)
    line = s["scenes"][0]["lines"][0]
    assert line["face"] == "normal"
    assert line["tts"] == "なのだ"


def test_reading_dictionary_is_applied_to_tts_but_not_subtitle():
    s = normalize_script({"meta": {"reading": {"H3": "エイチスリー"}}, "cast": CAST,
                          "scenes": [{"lines": [{"who": "metan", "text": "H3よ"}]}]})
    line = s["scenes"][0]["lines"][0]
    assert (line["text"], line["tts"]) == ("H3よ", "エイチスリーよ")


def test_explicit_yomi_wins_over_dictionary():
    s = normalize_script({"meta": {"reading": {"H3": "エイチスリー"}}, "cast": CAST,
                          "scenes": [{"lines": [{"who": "metan", "text": "H3よ", "yomi": "えいちさんよ"}]}]})
    assert s["scenes"][0]["lines"][0]["tts"] == "えいちさんよ"


def test_unknown_speaker_is_reported_with_location():
    with pytest.raises(ScriptError, match=r"scenes\[0\]\.lines\[1\].*tsumugi"):
        normalize_script({"cast": CAST, "scenes": [{"lines": [
            {"who": "zundamon", "text": "a"}, {"who": "tsumugi", "text": "b"}]}]})


def test_empty_text_is_rejected():
    with pytest.raises(ScriptError, match=r"scenes\[0\]\.lines\[0\]"):
        normalize_script({"cast": CAST, "scenes": [{"lines": [{"who": "zundamon", "text": " "}]}]})


def test_emphasis_markup_is_kept_for_subtitle_but_removed_from_tts():
    s = normalize_script({"meta": {"reading": {"H3": "エイチスリー"}}, "cast": CAST,
                          "scenes": [{"lines": [{"who": "metan", "text": "**H3**は2Kよ"}]}]})
    line = s["scenes"][0]["lines"][0]
    assert line["text"] == "**H3**は2Kよ"
    assert line["tts"] == "エイチスリーは2Kよ"


def test_line_break_marker_is_not_read():
    s = normalize_script({"cast": CAST, "scenes": [{"lines": [{"who": "metan", "text": "一行目\n二行目"}]}]})
    assert s["scenes"][0]["lines"][0]["tts"] == "一行目二行目"
