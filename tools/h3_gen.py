"""MiniMax H3（ローカルの ComfyUI）で、最初のコマ画像から声つきの短い動画を作る。

    uv run python tools/h3_gen.py --image key.png --prompt-file prompt.txt --out pv.mp4 --seconds 5
        [--url http://127.0.0.1:8188] [--comfy-root <ポータブル版>] [--turbo-sampler] [--lora <名前>|none]

H3 が入った ComfyUI（0.30 以降。Desktop 版でもポータブル版でもよい）を先に起動しておくか、
--comfy-root でポータブル版を指定する（その場合は自分で起こしたものだけを最後に止める）。
モデル名の既定は Hugging Face「Comfy-Org/MiniMax-H3」のファイル名。違う名前で置いているなら各オプションで渡す。
--turbo-sampler は MiniMaxH3TurboSampler（カスタムノード）を使う。声や効果音のざらつきが減る。

参照モード（ref2va 重み）は --ref-image（9枚まで）と --ref-audio を渡す。プロンプトの本文で
<Picture N> / <Audio 1> として指す。--audio-source reference は参照音声をそのまま載せる
（VOICEVOX のセリフに口を合わせたいときなど）。

    uv run python tools/h3_gen.py --ref-image key.png --ref-audio line.wav --audio-source reference         --prompt-file prompt.txt --out cut.mp4 --seconds 8
"""
import argparse
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from zvideo.comfy import (H3_DEFAULTS, H3_REF_UNET, ComfyApi, h3_graph, h3_ref_graph,  # noqa: E402
                          start_portable, stop_portable)  # noqa: E402
from zvideo.log import step  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="最初のコマにする画像（省略するとプロンプトだけで作る）")
    ap.add_argument("--ref-image", action="append", default=[], help="参照モード: <Picture N> にする画像（順に）")
    ap.add_argument("--ref-audio", help="参照モード: <Audio 1> にする音声")
    ap.add_argument("--audio-source", choices=("generated", "reference"), default="generated",
                    help="参照モードで載せる音（reference は参照音声をそのまま）")
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--megapixels", type=float, default=0.4, help="0.4 で 832x480（16:9）")
    ap.add_argument("--seed", type=int, default=20261007)
    ap.add_argument("--steps", type=int, default=10)
    ap.add_argument("--url", default=os.environ.get("ZVIDEO_H3_URL", "http://127.0.0.1:8188"))
    ap.add_argument("--comfy-root", default=os.environ.get("ZVIDEO_H3_COMFY_ROOT"))
    ap.add_argument("--turbo-sampler", action="store_true")
    for key in ("unet", "text_encoder", "video_vae", "audio_vae", "lora"):
        ap.add_argument("--" + key.replace("_", "-"), default=None if key == "unet" else H3_DEFAULTS[key])
    ap.add_argument("--lora-strength", type=float, default=0.6)
    ap.add_argument("--keep-server", action="store_true")
    ap.add_argument("--no-free", action="store_true", help="終了時にモデルを降ろさない（続けて生成するとき）")
    a = ap.parse_args(argv)

    prompt = Path(a.prompt_file).read_text(encoding="utf-8").strip()
    api = ComfyApi(a.url)
    pid = None
    if not api.is_up():
        if not a.comfy_root:
            raise SystemExit(f"{a.url} の ComfyUI が応答しません。H3 の入った ComfyUI を起動するか --comfy-root を指定してください")
        pid = start_portable(a.comfy_root, urlparse(a.url).port or 8188, PROJECT / "logs" / "comfy_h3")
    try:
        lora = None if a.lora.lower() == "none" else a.lora
        common = dict(lora=lora, lora_strength=a.lora_strength, steps=a.steps, turbo_sampler=a.turbo_sampler,
                      aspect=a.aspect, megapixels=a.megapixels)
        if a.ref_image or a.ref_audio:
            refs = [api.upload(x) for x in a.ref_image]
            audio = api.upload(a.ref_audio) if a.ref_audio else None
            graph = h3_ref_graph(prompt, refs, audio, a.seconds, a.seed, a.unet or H3_REF_UNET, a.text_encoder,
                                 a.video_vae, a.audio_vae, audio_source=a.audio_source, **common)
        else:
            first = api.upload(a.image) if a.image else None
            graph = h3_graph(prompt, first, a.seconds, a.seed, a.unet or H3_DEFAULTS["unet"], a.text_encoder,
                             a.video_vae, a.audio_vae, **common)
        with step("h3.generate", {"image": a.image, "ref_images": a.ref_image, "ref_audio": a.ref_audio,
                                  "audio_source": a.audio_source, "seconds": a.seconds, "seed": a.seed,
                                  "turbo_sampler": a.turbo_sampler, "prompt_chars": len(prompt)}) as s:
            t0 = time.time()
            files = api.run(graph, timeout=3600)
            videos = [f for f in files if str(f["filename"]).lower().endswith((".mp4", ".webm", ".mov"))]
            if not videos:
                raise RuntimeError(f"動画が出力されませんでした: {files}")
            dest = api.download(videos[0], Path(a.out))
            s.result = {"out": str(dest), "sec": round(time.time() - t0, 1)}
        print("video:", dest)
    finally:
        if not a.no_free:
            api.free()
        if pid and not a.keep_server:
            stop_portable(pid)


if __name__ == "__main__":
    main()
