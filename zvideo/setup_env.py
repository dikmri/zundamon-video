"""環境構築: VOICEVOX エンジン・立ち絵・フォント・BGM/SE の取得と、立ち絵パーツの書き出し。

uv run python -m zvideo.setup_env            # 未取得のものだけ取得して書き出し
uv run python -m zvideo.setup_env --force-prepare  # 立ち絵パーツを作り直す
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request

from .log import log, step
from .paths import ASSETS, CHARACTERS, PLAYWRIGHT_BROWSERS, RUNTIME, SOZAI_SRC, VOICEVOX_DIR

VOICEVOX_VERSION = "0.25.2"
VOICEVOX_URL = (f"https://github.com/VOICEVOX/voicevox_engine/releases/download/{VOICEVOX_VERSION}/"
                f"voicevox_engine-windows-cpu-{VOICEVOX_VERSION}.7z.001")

GF = "https://github.com/google/fonts/raw/main/ofl"
SE_LAB = "https://soundeffect-lab.info/sound"

# (保存先, URL, Referer)
DOWNLOADS = [
    # 東北ずん子・ずんだもんプロジェクト公式素材 https://zunko.jp/con_illust.html
    (SOZAI_SRC / "zunmon008.psd", "https://zunko.jp/sozai/zundamon/zunmon008.psd", None),
    (SOZAI_SRC / "met004.png", "https://zunko.jp/sozai/methane/met004.png", None),
    # Google Fonts (SIL OFL)
    (ASSETS / "fonts/MPLUSRounded1c-Medium.ttf", f"{GF}/mplusrounded1c/MPLUSRounded1c-Medium.ttf", None),
    (ASSETS / "fonts/MPLUSRounded1c-Bold.ttf", f"{GF}/mplusrounded1c/MPLUSRounded1c-Bold.ttf", None),
    (ASSETS / "fonts/MPLUSRounded1c-ExtraBold.ttf", f"{GF}/mplusrounded1c/MPLUSRounded1c-ExtraBold.ttf", None),
    (ASSETS / "fonts/MPLUSRounded1c-Black.ttf", f"{GF}/mplusrounded1c/MPLUSRounded1c-Black.ttf", None),
    (ASSETS / "fonts/DelaGothicOne-Regular.ttf", f"{GF}/delagothicone/DelaGothicOne-Regular.ttf", None),
    # 魔王魂（クレジット必須: 音楽：魔王魂） https://maou.audio/rule/
    (ASSETS / "bgm/maou_loop_bgm_acoustic50.mp3", "https://maou.audio/sound/bgm/maou_loop_bgm_acoustic50.mp3",
     "https://maou.audio/bgm_acoustic50/"),
    # 効果音ラボ（クレジット任意） https://soundeffect-lab.info/agreement/
    (ASSETS / "se/title.mp3", f"{SE_LAB}/anime/mp3/title1.mp3", f"{SE_LAB}/anime/"),
    (ASSETS / "se/jean.mp3", f"{SE_LAB}/anime/mp3/jean1.mp3", f"{SE_LAB}/anime/"),
    (ASSETS / "se/jajean.mp3", f"{SE_LAB}/anime/mp3/jajean1.mp3", f"{SE_LAB}/anime/"),
    (ASSETS / "se/doon.mp3", f"{SE_LAB}/anime/mp3/doon1.mp3", f"{SE_LAB}/anime/"),
    (ASSETS / "se/pico.mp3", f"{SE_LAB}/anime/mp3/pico-pico-hammer1.mp3", f"{SE_LAB}/anime/"),
    (ASSETS / "se/switch.mp3", f"{SE_LAB}/anime/mp3/sceneswitch1.mp3", f"{SE_LAB}/anime/"),
    (ASSETS / "se/chanchan.mp3", f"{SE_LAB}/anime/mp3/chan-chan1.mp3", f"{SE_LAB}/anime/"),
    (ASSETS / "se/pop.mp3", f"{SE_LAB}/button/mp3/decision22.mp3", f"{SE_LAB}/button/"),
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) zundamonVideo-setup"


def download(dest, url, referer=None):
    if dest.exists() and dest.stat().st_size > 0:
        return "skip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    with step("setup.download", {"url": url, "dest": str(dest)}) as s:
        req = urllib.request.Request(url, headers=headers)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(req, timeout=600) as r, tmp.open("wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        tmp.replace(dest)
        s.result = f"{dest.stat().st_size} bytes"
    return "ok"


def find_7z():
    for c in (shutil.which("7z"), r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if c and os.path.exists(c):
            return c
    raise RuntimeError("7-Zip が見つかりません。VOICEVOX エンジンの展開に必要です")


def ensure_voicevox():
    if (VOICEVOX_DIR / "run.exe").exists():
        return "skip"
    archive = RUNTIME / "downloads" / VOICEVOX_URL.rsplit("/", 1)[1]
    download(archive, VOICEVOX_URL)
    with step("setup.voicevox_extract", {"archive": str(archive)}):
        subprocess.run([find_7z(), "x", "-y", f"-o{RUNTIME / 'voicevox'}", str(archive)],
                       check=True, stdout=subprocess.DEVNULL)
    return "ok"


def ensure_playwright_browser():
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(PLAYWRIGHT_BROWSERS)}
    with step("setup.playwright_install", {"path": str(PLAYWRIGHT_BROWSERS)}):
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True, env=env)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-prepare", action="store_true", help="立ち絵パーツを作り直す")
    args = ap.parse_args(argv)
    for dest, url, ref in DOWNLOADS:
        print(f"{download(dest, url, ref):5s} {dest.relative_to(ASSETS.parent)}")
    print("voicevox", ensure_voicevox())
    ensure_playwright_browser()

    from .characters import prepare_metan, prepare_metan_official, prepare_zundamon, prepare_zundamon_official
    missing = []
    for name, fn in (("zundamon", prepare_zundamon), ("metan", prepare_metan),
                     ("zundamon_official", prepare_zundamon_official), ("metan_official", prepare_metan_official)):
        if args.force_prepare or not (CHARACTERS / name / "char.json").exists():
            try:
                with step("setup.prepare_character", {"name": name}):
                    info = fn()
            except FileNotFoundError as e:
                # 坂本アヒル氏の立ち絵 zip は規約への同意が要るため自動取得しない。残りの準備は続ける
                missing.append(str(e))
                print("missing", name)
                continue
            print("prepared", name, json.dumps({k: info[k] for k in ("size",)}))
        else:
            print("skip    character", name)
    if missing:
        print("\n立ち絵の素材が足りません。次の zip を置いてから、もう一度実行してください:")
        for m in missing:
            print(" -", m)


if __name__ == "__main__":
    main()
