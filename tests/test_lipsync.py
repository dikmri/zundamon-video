from zvideo.lipsync import mouth_track, shape_at


def mora(text, vowel, vlen, consonant=None, clen=None):
    return {"text": text, "consonant": consonant, "consonant_length": clen,
            "vowel": vowel, "vowel_length": vlen, "pitch": 5.0}


def query(moras, pre=0.1, post=0.1, speed=1.0, pause=None):
    return {"accent_phrases": [{"moras": moras, "accent": 1, "pause_mora": pause,
                                "is_interrogative": False}],
            "speedScale": speed, "prePhonemeLength": pre, "postPhonemeLength": post}


def test_single_vowel_opens_then_closes():
    q = query([mora("ア", "a", 0.2)])
    assert mouth_track(q, 0.4) == [(0.0, "n"), (0.1, "a"), (0.3, "n")]


def test_times_follow_actual_wav_length_when_speed_changes():
    # speedScale=2 で wav が半分の長さになったら、口の切り替えも半分の時刻になる
    q = query([mora("ア", "a", 0.2)], speed=2.0)
    track = mouth_track(q, 0.2)
    assert [s for _, s in track] == ["n", "a", "n"]
    assert [round(t, 6) for t, _ in track] == [0.0, 0.05, 0.15]


def test_bilabial_consonant_keeps_mouth_closed():
    q = query([mora("マ", "a", 0.15, consonant="m", clen=0.05)])
    assert mouth_track(q, 0.4) == [(0.0, "n"), (0.15, "a"), (0.3, "n")]


def test_other_consonant_opens_with_the_vowel_shape():
    q = query([mora("カ", "a", 0.15, consonant="k", clen=0.05)])
    assert mouth_track(q, 0.4) == [(0.0, "n"), (0.1, "a"), (0.3, "n")]


def test_n_sokuon_and_pause_close_the_mouth():
    q = {"accent_phrases": [
            {"moras": [mora("イ", "i", 0.1), mora("ン", "N", 0.1), mora("ッ", "cl", 0.1)],
             "pause_mora": mora("、", "pau", 0.2)},
            {"moras": [mora("オ", "o", 0.1)], "pause_mora": None}],
         "speedScale": 1.0, "prePhonemeLength": 0.0, "postPhonemeLength": 0.0}
    assert mouth_track(q, 0.6) == [(0.0, "i"), (0.1, "n"), (0.5, "o"), (0.6, "n")]


def test_unvoiced_vowel_uses_lowercase_shape():
    q = query([mora("ス", "U", 0.1, consonant="s", clen=0.05)], pre=0.0, post=0.0)
    assert mouth_track(q, 0.15) == [(0.0, "u"), (0.15, "n")]


def test_repeated_shapes_are_merged():
    q = query([mora("ア", "a", 0.1), mora("ア", "a", 0.1)], pre=0.0, post=0.0)
    assert mouth_track(q, 0.2) == [(0.0, "a"), (0.2, "n")]


def test_shape_at_looks_up_the_active_keyframe():
    track = [(0.0, "n"), (0.1, "a"), (0.3, "n")]
    assert shape_at(track, -1.0) == "n"
    assert shape_at(track, 0.1) == "a"
    assert shape_at(track, 0.29) == "a"
    assert shape_at(track, 5.0) == "n"
