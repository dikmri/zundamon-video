"""WAI-Anima（Anima 系）で作例画像を生成する。

    uv run python tools/anima_gen.py projects/kiritan/media/anima_spec.json [--only key]
        [--url http://127.0.0.1:8190] [--comfy-root D:\\ComfyUI_windows_portable]

--url の ComfyUI が応答しなければ、--comfy-root（または環境変数 ZVIDEO_ANIMA_COMFY_ROOT）の
ポータブル版を裏で起動し、終わったら自分で起こしたものだけを止める。
生成画像は spec と同じフォルダへ <名前>.png で保存する。
作例は全年齢に固定（zvideo.comfy がレーティング safe 以外を拒否し、否定プロンプトに成人向けタグを足す）。
"""
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from zvideo.comfy import ComfyApi, anima_graph, compose_prompt, start_portable, stop_portable  # noqa: E402
from zvideo.log import step  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--url", default=os.environ.get("ZVIDEO_ANIMA_URL", "http://127.0.0.1:8190"))
    ap.add_argument("--comfy-root", default=os.environ.get("ZVIDEO_ANIMA_COMFY_ROOT"))
    ap.add_argument("--extra-args", nargs="*", default=[], help="ポータブル版の起動に足す引数")
    ap.add_argument("--keep-server", action="store_true")
    a = ap.parse_args(argv)
    spec_path = Path(a.spec).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    api = ComfyApi(a.url)
    pid = None
    if not api.is_up():
        if not a.comfy_root:
            raise SystemExit(f"{a.url} の ComfyUI が応答しません。起動するか --comfy-root を指定してください")
        pid = start_portable(a.comfy_root, urlparse(a.url).port or 8190, PROJECT / "logs" / "comfy_anima",
                             a.extra_args)
    try:
        for name, img in spec["images"].items():
            if a.only and name not in a.only:
                continue
            positive = compose_prompt(img["characters"], img["tags"], series=img.get("series", []))
            if img.get("sentence"):
                positive += ". " + img["sentence"]
            w, h = img.get("size", [1344, 768])
            graph = anima_graph(positive, img.get("negative", ", ".join(spec.get("negative", []))),
                                unet=spec["unet"], text_encoder=spec["text_encoder"], vae=spec["vae"],
                                width=w, height=h, seed=img["seed"], steps=spec.get("steps", 28),
                                cfg=spec.get("cfg", 4.5), prefix=f"zundamonVideo/{name}")
            with step("anima.generate", {"name": name, "seed": img["seed"], "size": [w, h], "prompt": positive}) as s:
                files = api.run(graph)
                dest = spec_path.parent / f"{name}.png"
                api.download(files[0], dest)
                (spec_path.parent / f"{name}.prompt.txt").write_text(positive, encoding="utf-8")
                s.result = str(dest)
            print("image:", dest)
    finally:
        api.free()
        if pid and not a.keep_server:
            stop_portable(pid)


if __name__ == "__main__":
    main()
