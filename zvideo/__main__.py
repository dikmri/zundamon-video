"""ずんだもん解説動画ジェネレーター CLI

uv run python -m zvideo build   projects/h3/script.json            # 音声合成と data.js / audio.wav まで
uv run python -m zvideo frames  projects/h3/script.json --at 5 30   # 指定秒のフレームを PNG で確認
uv run python -m zvideo render  projects/h3/script.json --workers 4 # mp4 を書き出す
uv run python -m zvideo preview projects/h3/script.json             # ブラウザで音声つき再生
"""
import argparse
import subprocess
import sys
import time
import webbrowser

from .log import log, step


def main(argv=None):
    ap = argparse.ArgumentParser(prog="zvideo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "frames", "render", "preview"):
        p = sub.add_parser(name)
        p.add_argument("script")
        if name == "frames":
            p.add_argument("--at", type=float, nargs="+", required=True, help="秒（複数可）")
        if name == "render":
            p.add_argument("--workers", type=int, default=4)
        if name == "preview":
            p.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    log("cli", {"argv": sys.argv[1:] if argv is None else argv})

    from .build import build
    with step("cli." + a.cmd, {"script": a.script}):
        info = build(a.script)
        out, meta = info["out"], info["meta"]
        print(f"built: {info['page']}  total={info['total']}s scenes={info['scenes']} lines={info['lines']}")
        if a.cmd == "frames":
            from .render import snapshot
            snap_dir = out / "frames"
            snap_dir.mkdir(exist_ok=True)
            for p in snapshot(info["page"], a.at, meta["width"], meta["height"], snap_dir):
                print("frame:", p)
        elif a.cmd == "render":
            from .render import render_video
            mp4 = out / f"{info['name']}.mp4"
            render_video(info["page"], info["total"], meta["fps"], meta["width"], meta["height"],
                         out / "audio.wav", mp4, workers=a.workers)
            # 結合は -shortest なので、音声か映像が欠けると黙って短くなる。尺を台本と照合する
            got = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                        str(mp4)], capture_output=True, text=True, check=True).stdout.strip())
            log("render.verify", {"expected": round(info["total"], 2)}, f"duration={got:.2f}")
            if abs(got - info["total"]) > 0.2:
                raise RuntimeError(f"動画の尺が台本と合いません（期待 {info['total']:.2f}s、実際 {got:.2f}s）")
            print("video:", mp4)
            # 書き出した動画をポータル（portal/index.html）に加える。失敗しても書き出し自体は成功のまま
            try:
                from .portal.media import build_catalog, page_uri
                cat = build_catalog()
                log("render.portal", {"mp4": str(mp4)}, f"ok videos={len(cat['videos'])}")
                print(f"portal: {len(cat['videos'])} 本  {page_uri()}")
            except Exception as e:
                log("render.portal", {"mp4": str(mp4)}, f"ERROR {type(e).__name__}: {e}")
                print("portal: カタログの更新に失敗しました（logs/zvideo.log と logs/portal.log を参照）")
        elif a.cmd == "preview":
            from .render import serve
            server, port = serve(a.port)
            url = f"http://127.0.0.1:{port}/{info['page']}"
            print("preview:", url, "(Ctrl+C で終了)")
            webbrowser.open(url)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                server.shutdown()


if __name__ == "__main__":
    main()
