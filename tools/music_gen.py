"""MiniMax Music 3（ローカルの ComfyUI）で BGM を作る。既定は歌なし。

    uv run python tools/music_gen.py --caption-file bgm.txt --seconds 90 --out bgm.flac [--seed 1]
        [--lyrics "[Intro]\\n[Instrumental]\\n[Outro]"] [--tiled] [--url http://127.0.0.1:8188]

MiniMax Music 3 のモデル（Hugging Face「Comfy-Org/MiniMax-Music-3」の int8 DiT・int8 テキストエンコーダ・VAE）を
読める ComfyUI を先に起動しておく。
--caption-file は曲の説明（英語）。Global Metadata（ジャンル・BPM・調・感情の流れ・用途）/ Vocal Details /
Arrangement（楽器・リズム・質感）の 3 節で具体的に書くと寄る。歌なしなら Vocal Details に "No vocals" と書く。
--seconds は上限で、実際の長さはモデルが決める（40〜55 秒になりやすい）。長い曲が要るときは、seed を変えた
テイクをつなぐかループする。VRAM が足りないときは --tiled。
"""
import argparse
import os
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from zvideo.comfy import MUSIC3_DEFAULTS, ComfyApi, music3_graph  # noqa: E402
from zvideo.log import step  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--caption-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=90.0, help="長さの上限（秒）")
    ap.add_argument("--lyrics", default="[Intro]\n[Instrumental]\n[Outro]",
                    help="歌詞。歌なしはセクションのタグだけ（\\n で改行）")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--tiled", action="store_true", help="音声の復元を分割して行い VRAM を節約する")
    for key in ("unet", "text_encoder", "vae"):
        ap.add_argument("--" + key.replace("_", "-"), default=MUSIC3_DEFAULTS[key])
    ap.add_argument("--url", default=os.environ.get("ZVIDEO_MUSIC_URL", "http://127.0.0.1:8188"))
    ap.add_argument("--no-free", action="store_true", help="終了時にモデルを降ろさない（続けて生成するとき）")
    a = ap.parse_args(argv)

    caption = Path(a.caption_file).read_text(encoding="utf-8").strip()
    lyrics = a.lyrics.replace("\\n", "\n")
    api = ComfyApi(a.url)
    if not api.is_up():
        raise SystemExit(f"{a.url} の ComfyUI が応答しません。MiniMax Music 3 を読める ComfyUI を起動してください")
    graph = music3_graph(caption, a.seconds, a.seed, lyrics=lyrics, unet=a.unet, text_encoder=a.text_encoder,
                         vae=a.vae, steps=a.steps, tiled=a.tiled)
    try:
        with step("music.generate", {"caption": caption[:80], "seconds": a.seconds, "seed": a.seed,
                                     "lyrics": lyrics[:40]}) as s:
            t0 = time.time()
            files = api.run(graph, timeout=3600)
            audio = [f for f in files if str(f["filename"]).lower().endswith((".flac", ".wav", ".mp3", ".opus"))]
            if not audio:
                raise RuntimeError(f"音声が出力されませんでした: {files}")
            dest = api.download(audio[0], Path(a.out))
            s.result = {"out": str(dest), "sec": round(time.time() - t0, 1)}
        print("audio:", dest)
    finally:
        if not a.no_free:
            api.free()


if __name__ == "__main__":
    main()
