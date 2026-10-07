"""台本 JSON の検証と既定値の補完。"""
import copy

from .reading import apply_reading

META_DEFAULTS = {
    "title": "",
    "fps": 30,
    "width": 1920,
    "height": 1080,
    "reading": {},
    "bgm": None,
    "bgm_volume": 0.12,
    "timing": {},
    "credits": [],
}


class ScriptError(ValueError):
    pass


def strip_markup(text):
    """字幕用の記法（**強調**、改行）を読み上げ文から除く。"""
    return text.replace("**", "").replace("\n", "")


def normalize_script(raw):
    s = copy.deepcopy(raw)
    s["meta"] = {**META_DEFAULTS, **(s.get("meta") or {})}
    cast = s.get("cast") or {}
    if not cast:
        raise ScriptError("cast: 登場キャラクターが1人も定義されていません")
    for key, member in cast.items():
        if not member.get("character"):
            raise ScriptError(f"cast.{key}: character（assets/characters 配下のフォルダ名）が必要です")

    reading = s["meta"]["reading"]
    scenes = s.get("scenes") or []
    if not scenes:
        raise ScriptError("scenes: シーンが1つもありません")
    for i, scene in enumerate(scenes):
        scene.setdefault("id", f"s{i}")
        scene.setdefault("lines", [])
        for j, line in enumerate(scene["lines"]):
            where = f"scenes[{i}].lines[{j}]"
            who = line.get("who")
            if who not in cast:
                raise ScriptError(f"{where}: 未定義の話者 '{who}'（cast: {', '.join(cast)}）")
            text = (line.get("text") or "").strip()
            if not text:
                raise ScriptError(f"{where}: text が空です")
            line["text"] = text
            line.setdefault("face", cast[who].get("face", "normal"))
            line["tts"] = line.get("yomi") or apply_reading(strip_markup(text), reading)
    return s
