"""台本 JSON → 音声合成 → タイムライン → data.js / index.html / audio.wav（→ mp4）を作る。"""
import json
import re
import shutil
from pathlib import Path

from .audio import has_audio, media_duration, mix, transcode_webm
from .lipsync import mouth_track
from .log import log, step
from .paths import ASSETS, CHARACTERS, OUT, ROOT, TEMPLATE
from .script import normalize_script
from .timeline import Timing, blink_times, build_timeline
from .voicevox import ensure_engine, synthesize

# 立ち絵の既定配置（1920x1080 の画面座標でのキャンバス左上 x, y と倍率）。cast の x / y / scale で上書きできる。
DEFAULT_PLACEMENT = {
    # 坂本アヒル氏の立ち絵（PSDTool 版）
    "zundamon": {"left": (-170, 330, 0.72), "right": (1344, 330, 0.72)},
    "metan": {"left": (-240, 368, 0.72), "right": (1365, 368, 0.72)},
    # 公式立ち絵
    "zundamon_official": {"left": (-40, 390, 0.82), "right": (1450, 390, 0.82)},
    "metan_official": {"left": (-80, 340, 0.78), "right": (1440, 340, 0.78)},
}


def _placement(member, info, character):
    pos = member.get("position", "right")
    fallback = (0 if pos == "left" else 1920 - int(info["size"][0] * 0.8), 360, 0.8)
    x, y, k = DEFAULT_PLACEMENT.get(character, {}).get(pos, fallback)
    return pos, member.get("x", x), member.get("y", y), member.get("scale", k)


CLIP_TAG = re.compile(r'<video\b[^>]*\bdata-clip="([^"]+)"[^>]*>', re.I)


def _attr(tag, name):
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return m.group(1) if m else None


CLIP_AFTER_DELAY = 0.3  # data-start="after" のとき、セリフが終わってから再生を始めるまでの間（player.js と同じ値）


def _prepare_clips(html, steps, steps_end, out):
    """data-clip="/projects/.../x.mp4" を描画用 WebM に変え、混ぜる音声の一覧を返す。

    返り値の音声は (開始秒, 元ファイル, 音量, 長さ)。data-volume="0" なら音は混ぜない。
    data-start="after" なら、その段階を出したセリフが終わってから再生する。
    """
    effects = []

    def repl(m):
        tag, src = m.group(0), m.group(1)
        src_path = ROOT / src.lstrip("/")
        if not src_path.exists():
            raise FileNotFoundError(f"埋め込み動画がありません: {src_path}")
        webm = out / "clips" / (src_path.stem + ".webm")
        transcode_webm(src_path, webm)
        dur = media_duration(src_path)
        step_no = int(_attr(tag, "data-step") or 0)
        if _attr(tag, "data-start") == "after":
            start = steps_end.get(step_no, 0.0) + CLIP_AFTER_DELAY
        else:
            start = steps.get(step_no, 0.0)
        volume = float(_attr(tag, "data-volume") or 1.0)
        if volume > 0 and has_audio(src_path):
            effects.append((start, src_path, volume, dur))
        log("build.clip", {"src": src, "step": step_no, "start": round(start, 2)}, f"{dur:.2f}s -> {webm.name}")
        return tag.replace(f'data-clip="{src}"', f'data-clip="clips/{webm.name}"')

    return CLIP_TAG.sub(repl, html), effects


def _se_path(name):
    p = ASSETS / "se" / f"{name}.mp3"
    if not p.exists():
        raise FileNotFoundError(f"効果音 '{name}' がありません: {p}")
    return p


def build(script_path):
    script_path = Path(script_path).resolve()
    raw = json.loads(script_path.read_text(encoding="utf-8"))
    s = normalize_script(raw)
    meta = s["meta"]
    name = meta.get("name") or script_path.parent.name
    out = OUT / name
    out.mkdir(parents=True, exist_ok=True)
    log("build.start", {"script": str(script_path), "out": str(out)})

    # ボード HTML は台本と同じフォルダの別ファイルに書ける（board.html_file）
    for sc in s["scenes"]:
        b = sc.get("board")
        if b and b.get("html_file"):
            b["html"] = (script_path.parent / b["html_file"]).read_text(encoding="utf-8")

    cast = {}
    for key, m in s["cast"].items():
        info = json.loads((CHARACTERS / m["character"] / "char.json").read_text(encoding="utf-8"))
        pos, x, y, k = _placement(m, info, m["character"])
        cast[key] = {"member": m, "info": info, "position": pos, "x": x, "y": y, "scale": k}

    ensure_engine()
    n_lines = sum(len(sc["lines"]) for sc in s["scenes"])
    with step("build.tts", {"lines": n_lines}):
        for sc in s["scenes"]:
            for line in sc["lines"]:
                c = cast[line["who"]]
                v, m = c["info"]["voice"], c["member"]
                if line["face"] not in c["info"]["faces"]:
                    log("build.warn", {"who": line["who"], "face": line["face"]}, "未定義の表情のため既定の表情で表示")
                if line.get("pose") and line["pose"] not in c["info"].get("poses", {}):
                    log("build.warn", {"who": line["who"], "pose": line["pose"]}, "未定義のポーズのため既定のポーズで表示")
                speaker = line.get("speaker") or v["styles"].get(line.get("style") or "normal", v["speaker"])
                r = synthesize(line["tts"], speaker,
                               speed=line.get("speed", m.get("speed", v["speed"])),
                               pitch=line.get("pitch", m.get("pitch", v["pitch"])),
                               intonation=line.get("intonation", m.get("intonation", v["intonation"])),
                               volume=line.get("volume", 1.0))
                line["duration"] = r["duration"]
                line["_wav"] = r["wav"]
                line["mouth"] = mouth_track(r["query"], r["duration"])

    tl = build_timeline(s["scenes"], Timing(**meta["timing"]))
    total = tl["total"]

    voices, effects, lines = [], [], []
    for si, sc in enumerate(tl["scenes"]):
        for se in ([sc["se"]] if isinstance(sc.get("se"), str) else sc.get("se") or []):
            effects.append((sc["start"], _se_path(se), meta.get("se_volume", 0.45)))
        for line in sc["lines"]:
            voices.append((line["start"], line["_wav"], 1.0))
            for se in ([line["se"]] if isinstance(line.get("se"), str) else line.get("se") or []):
                effects.append((line["start"] + line.get("se_offset", 0.0), _se_path(se), meta.get("se_volume", 0.45)))
            lines.append({k: line.get(k) for k in ("who", "text", "start", "end", "face", "pose", "eyes", "motion", "mouth")}
                         | {"scene": si})

    # ボードに埋め込んだ動画: WebM に変換して差し替え、音声は表示時刻に混ぜ、その間 BGM を下げる
    duck = []
    for sc in tl["scenes"]:
        b = sc.get("board")
        if b and b.get("html") and "data-clip" in b["html"]:
            b["html"], clip_effects = _prepare_clips(b["html"], sc["steps"], sc["steps_end"], out)
            for start, path, gain, dur in clip_effects:
                effects.append((start, path, gain))
                duck.append((start, start + dur))

    bgm = (ROOT / meta["bgm"], meta["bgm_volume"]) if meta.get("bgm") else None
    mix(total, voices, effects, bgm, out / "audio.wav", loudness=meta.get("loudness", -16.0), duck=duck)

    data = {
        "meta": {k: meta[k] for k in ("title", "width", "height", "fps")} | {"series": meta.get("series", "")},
        "total": total,
        "cast": {key: {"position": c["position"], "x": c["x"], "y": c["y"], "scale": c["scale"],
                       "flip": c["member"].get("flip", False), "face": c["member"].get("face", "normal"),
                       "pose": c["member"].get("pose", "normal"),
                       "enter_at": c["member"].get("enter_at", 0.0),
                       "color": c["member"].get("color", c["info"]["color"]),
                       "base_url": f"/assets/characters/{c['member']['character']}/", "info": c["info"],
                       "blinks": blink_times(total, seed=key)}
                 for key, c in cast.items()},
        "scenes": [{k: v for k, v in sc.items() if k != "lines"} | {"steps": {str(k): v for k, v in sc["steps"].items()},
                                                                     "steps_end": {str(k): v for k, v in sc["steps_end"].items()}}
                   for sc in tl["scenes"]],
        "lines": lines,
    }
    (out / "data.js").write_text("window.ZV = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")

    extra_css = ""
    style = script_path.parent / "style.css"
    if style.exists():
        shutil.copyfile(style, out / "style.css")
        extra_css = '<link rel="stylesheet" href="style.css">'
    html = (TEMPLATE / "index.html").read_text(encoding="utf-8")
    html = html.replace("{{TITLE}}", meta["title"] or name).replace("{{EXTRA_CSS}}", extra_css)
    (out / "index.html").write_text(html, encoding="utf-8")

    summary = {"name": name, "total": round(total, 2), "scenes": len(tl["scenes"]), "lines": len(lines),
               "page": f"out/{name}/index.html"}
    log("build.done", {"script": str(script_path)}, summary)
    return summary | {"out": out, "meta": meta}
