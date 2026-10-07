"""字幕の表記を VOICEVOX 向けの読みに置き換える辞書処理。"""
import re


def apply_reading(text, dictionary):
    """辞書の語を長い順に1回だけ置き換える（置換後の文字列は再置換しない）。"""
    if not dictionary:
        return text
    keys = sorted(dictionary, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in keys))
    return pattern.sub(lambda m: dictionary[m.group(0)], text)
