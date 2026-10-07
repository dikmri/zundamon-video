"""ffmpeg / ffprobe でポスター・ダイジェスト・シーク用サムネイルを作り、カタログ JSON を書き出す。

生成物は runtime/portal/<名前>/ に置き、mp4 のサイズと更新時刻が変わらない限り作り直さない。
"""
import json
import subprocess
from datetime import datetime

from ..log import log, step
from ..paths import LOGS, OUT, ROOT, RUNTIME
from .catalog import (asset_url, build_toc, make_entry, parse_data_js, poster_time, preview_times, sprite_plan,
                      thumb_time)
from .site import aggregate_cast

PORTAL_LOG = LOGS / "portal.log"
CATALOG_DIR = RUNTIME / "portal"
# サイト本体。カタログ内の URL はここからの相対パスにする（file:// で直接開いても読めるように）
WEB = ROOT / "portal"
CATALOG_JS = CATALOG_DIR / "catalog.js"
# 公開用サイト（GitHub Pages のリポジトリ）の作業コピー。公開状況は data/published.json に記録する
SITE_DIR = RUNTIME / "site"
PUBLISHED_JSON = SITE_DIR / "data" / "published.json"
# 生成物の作り方を変えたら上げる（キャッシュを無効にする）
GENERATOR = 3


def read_published():
    """公開状況 {"site": {...}, "videos": {id: {asset, version, at}}}。まだ公開していなければ空。"""
    if not PUBLISHED_JSON.is_file():
        return {}
    return json.loads(PUBLISHED_JSON.read_text(encoding="utf-8"))


def video_version(name):
    """mp4 の中身が変わったかを見分ける値（サイズと更新時刻）。"""
    return _version(OUT / name / f"{name}.mp4")


def page_uri():
    """ブラウザで直接開くポータルの URL（file://）。"""
    return (WEB / "index.html").as_uri()


def plog(event, args=None, result=None):
    log(event, args, result, file=PORTAL_LOG)


def _run(cmd, what):
    with step("ffmpeg." + what, {"cmd": " ".join(str(c) for c in cmd[-3:])}, file=PORTAL_LOG):
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError(f"{cmd[0]} が失敗しました: {r.stderr.strip()[-600:]}")
    return r


def probe(mp4):
    r = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
              "stream=width,height:format=duration,size", "-of", "json", mp4], "probe")
    j = json.loads(r.stdout)
    st = (j.get("streams") or [{}])[0]
    return {"duration": float(j["format"]["duration"]), "size": int(j["format"]["size"]),
            "width": st.get("width"), "height": st.get("height")}


def grab(mp4, t, out, width):
    _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", mp4, "-frames:v", "1",
          "-vf", f"scale={width}:-2:flags=lanczos", "-q:v", "3", out], "grab")


def digest(mp4, times, clip, out, width=640):
    """各時刻から clip 秒ずつ切り出してつないだ、無音の短い mp4。"""
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for t in times:
        cmd += ["-ss", f"{t:.2f}", "-t", f"{clip:.2f}", "-i", mp4]
    chains = "".join(f"[{i}:v]scale={width}:-2:flags=lanczos,setsar=1,fps=30,format=yuv420p[v{i}];"
                     for i in range(len(times)))
    joined = "".join(f"[v{i}]" for i in range(len(times)))
    cmd += ["-filter_complex", f"{chains}{joined}concat=n={len(times)}:v=1:a=0[out]", "-map", "[out]", "-an",
            "-c:v", "libx264", "-crf", "27", "-preset", "medium", "-movflags", "+faststart", out]
    _run(cmd, "digest")


def sprite(mp4, plan, out):
    vf = f"fps=1/{plan['interval']}:round=down,scale={plan['w']}:{plan['h']}:flags=bicubic,tile={plan['cols']}x{plan['rows']}"
    _run(["ffmpeg", "-y", "-v", "error", "-i", mp4, "-an", "-vf", vf, "-frames:v", "1", "-q:v", "5", out], "sprite")


CAST_VARIANTS = {
    # 名前: (表情の候補, ポーズの候補, 目, 口)
    "idle": ((None,), (None,), "open", "n"),
    "blink": ((None,), (None,), "closed", "n"),
    "talk": ((None,), (None,), "open", "a"),
    "joy": (("happy", None), ("raise", "present", None), "smile", "a"),
}


def _compose(char_dir, info, face, pose, eyes, mouth):
    from PIL import Image

    canvas = Image.new("RGBA", tuple(info["size"]), (0, 0, 0, 0))

    def put(part):
        if part:
            im = Image.open(char_dir / part["src"]).convert("RGBA")
            if im.size != (part["w"], part["h"]):
                im = im.resize((part["w"], part["h"]), Image.LANCZOS)
            canvas.alpha_composite(im, (part["x"], part["y"]))

    put(info["base"])
    for part in info["poses"].get(pose, []):
        put(part)
    for slot in info["faces"][face]:
        if slot["type"] == "static":
            put(slot["part"])
        elif slot["type"] == "eyes":
            put(slot["parts"].get(eyes) or slot["parts"].get("open"))
        elif slot["type"] == "mouth":
            put(slot["parts"].get(mouth) or slot["parts"].get("n"))
    put(info.get("top"))
    return canvas


def cast_images(character):
    """立ち絵のパーツから、背景が透明な WebP を数種類作る（まばたき・口パク・喜びの切り替え用）。"""
    from ..paths import CHARACTERS

    char_dir = CHARACTERS / character
    spec = char_dir / "char.json"
    if not spec.is_file():
        plog("portal.cast.missing", {"character": character}, str(spec))
        return None
    dest = CATALOG_DIR / "cast" / character
    ver = f"{GENERATOR}-{spec.stat().st_mtime_ns // 1_000_000:x}"
    stamp = dest / "version.txt"
    names = list(CAST_VARIANTS)
    urls = {n: asset_url(dest / f"{n}.webp", WEB, ver) for n in names}
    if stamp.is_file() and stamp.read_text(encoding="utf-8") == ver and all((dest / f"{n}.webp").is_file() for n in names):
        return urls
    with step("portal.cast.compose", {"character": character}, file=PORTAL_LOG) as s:
        from PIL import Image

        info = json.loads(spec.read_text(encoding="utf-8"))
        images = {}
        for n, (faces, poses, eyes, mouth) in CAST_VARIANTS.items():
            face = next((f for f in faces if f in info["faces"]), None) or info["default_face"]
            pose = next((p for p in poses if p in info["poses"]), None) or info["default_pose"]
            images[n] = _compose(char_dir, info, face, pose, eyes, mouth)
        # すべての差分を同じ範囲で切り抜く（重ねて切り替えても位置がずれないように）
        boxes = [im.getbbox() for im in images.values()]
        box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        dest.mkdir(parents=True, exist_ok=True)
        for n, im in images.items():
            im = im.crop(box)
            k = min(1.0, 1100 / im.height)
            if k < 1.0:
                im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
            im.save(dest / f"{n}.webp", "WEBP", quality=88, method=6)
        stamp.write_text(ver, encoding="utf-8")
        s.result = {"box": box, "size": list(im.size)}
    return urls


def _version(mp4):
    st = mp4.stat()
    return f"{st.st_size:x}{st.st_mtime_ns // 1_000_000:x}"


def build_video(name, force=False):
    """1本分の生成物を作り、カタログの1件分を返す。"""
    src = OUT / name
    mp4, data_js = src / f"{name}.mp4", src / "data.js"
    data = parse_data_js(data_js.read_text(encoding="utf-8"))
    ver = _version(mp4)
    dest = CATALOG_DIR / name
    (dest / "thumbs").mkdir(parents=True, exist_ok=True)
    manifest = dest / "manifest.json"
    old = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    fresh = not force and old.get("version") == ver and old.get("generator") == GENERATOR

    toc = build_toc(data["scenes"])
    plan = sprite_plan(data["total"])
    if fresh:
        info = old["info"]
        plog("portal.video.cached", {"name": name}, ver)
    else:
        with step("portal.video.build", {"name": name}, file=PORTAL_LOG) as s:
            info = probe(mp4)
            info["date"] = datetime.fromtimestamp(mp4.stat().st_mtime).isoformat(timespec="seconds")
            grab(mp4, poster_time(data["scenes"]), dest / "poster.jpg", 1280)
            digest(mp4, preview_times(toc, info["duration"]), 1.6, dest / "preview.mp4")
            sprite(mp4, plan, dest / "sprite.jpg")
            for i, e in enumerate(toc):
                grab(mp4, thumb_time(e), dest / "thumbs" / f"{i:02d}.jpg", 480)
            s.result = {"duration": info["duration"], "toc": len(toc)}
        manifest.write_text(json.dumps({"version": ver, "generator": GENERATOR, "info": info}, ensure_ascii=False),
                            encoding="utf-8")

    def u(rel):
        return asset_url(dest / rel, WEB, ver)

    urls = {"video": asset_url(mp4, WEB, ver), "poster": u("poster.jpg"), "preview": u("preview.mp4"),
            "sprite": plan | {"src": u("sprite.jpg")},
            "thumbs": [u(f"thumbs/{i:02d}.jpg") for i in range(len(toc))]}
    entry = make_entry(name, data, info, urls)
    for key, c in data.get("cast", {}).items():
        character = c.get("base_url", "").strip("/").split("/")[-1] or key
        entry["cast"][key]["portrait"] = cast_images(character)
    return entry


def find_videos():
    """out/<名前>/<名前>.mp4 と data.js がそろっているものだけを対象にする。"""
    if not OUT.exists():
        return []
    return sorted(d.name for d in OUT.iterdir()
                  if d.is_dir() and (d / f"{d.name}.mp4").is_file() and (d / "data.js").is_file())


def build_catalog(force=False):
    names = find_videos()
    plog("portal.catalog.scan", {"out": str(OUT)}, {"videos": names})
    videos = []
    for name in names:
        try:
            videos.append(build_video(name, force))
        except Exception as e:  # 1本の失敗で全体を止めない
            plog("portal.video.error", {"name": name}, f"ERROR {type(e).__name__}: {e}")
    videos.sort(key=lambda v: v["date"] or "")
    for i, v in enumerate(videos, 1):
        v["no"] = i

    # 公開用サイト（runtime/site）で公開済みかどうか
    pub = read_published()
    for v in videos:
        v["published"] = v["id"] in pub.get("videos", {})
    cast = aggregate_cast(videos)

    catalog = {"generated": datetime.now().isoformat(timespec="seconds"), "videos": videos, "cast": cast,
               "site": pub.get("site")}
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    # <script> で読める形にする（file:// のページからは fetch で JSON を読めないため）
    body = "window.ZA_CATALOG = " + json.dumps(catalog, ensure_ascii=False) + ";\n"
    tmp = CATALOG_JS.with_suffix(".js.tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(CATALOG_JS)
    old_json = CATALOG_DIR / "catalog.json"
    if old_json.exists():
        old_json.unlink()
    plog("portal.catalog.done", {"videos": len(videos)}, str(CATALOG_JS))
    return catalog
