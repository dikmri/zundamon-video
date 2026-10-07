"""VOICEVOX の audio_query から口パク用のキーフレーム列を作る。

口の形は立ち絵 PSD の口レイヤーに合わせて a/i/u/e/o/n（n=閉じ口）の6種類。
"""
from bisect import bisect_right

CLOSED = "n"
# 子音の間も口を閉じておく両唇音（マ行・バ行・パ行）
BILABIAL = {"m", "my", "b", "by", "p", "py"}
VOWEL_SHAPE = {
    "a": "a", "i": "i", "u": "u", "e": "e", "o": "o",
    # 無声化母音（「です」のス等）も同じ口形にする
    "A": "a", "I": "i", "U": "u", "E": "e", "O": "o",
    "N": CLOSED, "cl": CLOSED, "pau": CLOSED,
}


def _segments(query):
    yield query.get("prePhonemeLength") or 0.0, CLOSED
    for phrase in query["accent_phrases"]:
        for m in phrase["moras"]:
            shape = VOWEL_SHAPE.get(m["vowel"], CLOSED)
            if m.get("consonant") and m.get("consonant_length"):
                yield m["consonant_length"], CLOSED if m["consonant"] in BILABIAL else shape
            yield m["vowel_length"], shape
        pause = phrase.get("pause_mora")
        if pause:
            yield (pause.get("consonant_length") or 0.0) + pause["vowel_length"], CLOSED
    yield query.get("postPhonemeLength") or 0.0, CLOSED


def mouth_track(query, duration):
    """[(秒, 口形), ...] を返す。時刻は実際の wav 長 duration に合わせて伸縮する。

    speedScale や前後無音の扱いをエンジン実装に依存させないため、
    名目上の合計長と実測の wav 長の比で全体を伸縮する。
    """
    segments = [(length, shape) for length, shape in _segments(query) if length > 0]
    nominal = sum(length for length, _ in segments)
    if nominal <= 0:
        return [(0.0, CLOSED)]
    k = duration / nominal
    track = []
    t = 0.0
    for length, shape in segments:
        if not track or track[-1][1] != shape:
            track.append((round(t * k, 6), shape))
        t += length
    if track[-1][1] != CLOSED:
        track.append((round(t * k, 6), CLOSED))
    return track


def shape_at(track, t):
    i = bisect_right([k for k, _ in track], t) - 1
    return CLOSED if i < 0 else track[i][1]
