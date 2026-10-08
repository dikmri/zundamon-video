"""ComfyUI API への投入と、WAI-Anima（Anima 系）/ MiniMax H3 用ワークフローの組み立て。

起動済みの ComfyUI（Desktop 版など）には URL で接続する。ポータブル版なら start_portable() で
裏起動し、stop_portable() で止められる（この作業で起こしたものだけを止める）。
"""
import json
import os
import subprocess
import time
from pathlib import Path
import urllib.parse
import urllib.request
import uuid

from .log import log, step

QUALITY = ["masterpiece", "best quality", "score_7"]
# 解説動画の作例は全年齢に固定する。レーティングは safe 以外を受け付けず、
# 否定プロンプトには成人向けレーティングと露出系のタグを必ず足す。
ALWAYS_NEGATIVE = ["nsfw", "explicit", "sensitive", "questionable", "nude", "cleavage", "underwear",
                   "swimsuit", "suggestive"]
BASE_NEGATIVE = ["worst quality", "low quality", "score_1", "score_2", "score_3", "artist name", "blurry",
                 "jpeg artifacts", "lowres", "censor", "watermark", "text", "bad hands", "extra digits"]


def compose_prompt(characters, tags, series=(), rating="safe"):
    """Anima の推奨順（品質・レーティング → キャラ → 作品 → 一般タグ）でタグを並べる。"""
    if rating != "safe":
        raise ValueError("作例は全年齢に固定している（rating は safe のみ）")
    return ", ".join([*QUALITY, rating, *characters, *series, *tags])


def anima_graph(positive, negative, unet, text_encoder, vae, width, height, seed,
                steps=28, cfg=4.5, sampler="euler_ancestral", scheduler="normal", prefix="zvideo/anima"):
    neg_tags = [t.strip() for t in negative.split(",") if t.strip()]
    neg = ", ".join(neg_tags + [t for t in ALWAYS_NEGATIVE if t not in neg_tags])
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": text_encoder, "type": "stable_diffusion",
                                                     "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["2", 0]}},
        "6": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0],
            "seed": seed, "steps": steps, "cfg": cfg, "sampler_name": sampler, "scheduler": scheduler,
            "denoise": 1.0}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": prefix}},
    }


# ---- API -------------------------------------------------------------------

class ComfyApi:
    def __init__(self, url="http://127.0.0.1:8190"):
        self.url = url.rstrip("/")
        self.client_id = uuid.uuid4().hex

    def _req(self, method, path, payload=None, timeout=60):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
        return json.loads(body) if body[:1] in (b"{", b"[") else body

    def is_up(self):
        try:
            self._req("GET", "/system_stats", timeout=3)
            return True
        except OSError:
            return False

    def run(self, graph, timeout=1800):
        """グラフを投入し、完了まで待って出力ファイル情報の一覧を返す。"""
        with step("comfy.run", {"url": self.url, "nodes": len(graph)}) as s:
            res = self._req("POST", "/prompt", {"prompt": graph, "client_id": self.client_id}, timeout=120)
            pid = res["prompt_id"]
            t0 = time.time()
            while time.time() - t0 < timeout:
                hist = self._req("GET", f"/history/{pid}", timeout=30)
                entry = hist.get(pid) if isinstance(hist, dict) else None
                if entry:
                    status = entry.get("status", {})
                    if status.get("status_str") == "error":
                        msgs = [m for m in status.get("messages", []) if m and m[0] == "execution_error"]
                        raise RuntimeError(f"ComfyUI の実行エラー: {json.dumps(msgs, ensure_ascii=False)[:800]}")
                    files = [item for out in entry.get("outputs", {}).values() for v in out.values()
                             if isinstance(v, list) for item in v if isinstance(item, dict) and item.get("filename")]
                    s.result = {"prompt_id": pid, "files": [f["filename"] for f in files],
                                "sec": round(time.time() - t0, 1)}
                    return files
                time.sleep(1.5)
            raise TimeoutError(f"{timeout} 秒以内に終わりませんでした（prompt_id={pid}）")

    def upload(self, path, subfolder="zvideo"):
        """画像を ComfyUI の input へ送り、LoadImage から参照できる名前を返す。"""
        path = Path(path)
        boundary = "----zvideo" + uuid.uuid4().hex
        crlf = chr(13) + chr(10)  # マルチパートの区切り（CRLF）
        fields = [("type", "input"), ("subfolder", subfolder), ("overwrite", "true")]
        head = "".join(f'--{boundary}{crlf}Content-Disposition: form-data; name="{k}"{crlf}{crlf}{v}{crlf}' for k, v in fields)
        head += (f'--{boundary}{crlf}Content-Disposition: form-data; name="image"; filename="{path.name}"{crlf}'
                 f"Content-Type: image/png{crlf}{crlf}")
        body = head.encode() + path.read_bytes() + f"{crlf}--{boundary}--{crlf}".encode()
        req = urllib.request.Request(self.url + "/upload/image", data=body, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=300) as r:
            info = json.loads(r.read())
        name = f"{info['subfolder']}/{info['name']}" if info.get("subfolder") else info["name"]
        log("comfy.upload", {"file": str(path)}, name)
        return name

    def download(self, file_info, dest):
        q = urllib.parse.urlencode({"filename": file_info["filename"], "subfolder": file_info.get("subfolder", ""),
                                    "type": file_info.get("type", "output")})
        data = self._req("GET", f"/view?{q}", timeout=300)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        log("comfy.download", {"file": file_info["filename"]}, str(dest))
        return dest

    def free(self):
        try:
            self._req("POST", "/free", {"unload_models": True, "free_memory": True})
            log("comfy.free", {"url": self.url}, "ok")
        except OSError as e:
            log("comfy.free", {"url": self.url}, f"ERROR {e}")


# ---- ポータブル版 ComfyUI の起動・停止 -------------------------------------------

def start_portable(root, port, logdir, extra_args=()):
    """ポータブル版 ComfyUI を、ブラウザを開かずに裏で起動する。PID を返す。

    出力はファイルへ出す（パイプで受けると、子プロセスがハンドルを持ち続けて呼び出し側が止まる）。
    """
    root, logdir = Path(root), Path(logdir)
    python = root / "python_embeded" / "python.exe"
    if not python.exists():
        raise FileNotFoundError(f"{python} がありません（--comfy-root にはポータブル版のフォルダを指定）")
    logdir.mkdir(parents=True, exist_ok=True)
    out = open(logdir / "comfyui.out.log", "ab")
    err = open(logdir / "comfyui.err.log", "ab")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.Popen([str(python), "-s", "ComfyUI/main.py", "--windows-standalone-build",
                          "--disable-auto-launch", "--port", str(port), *extra_args],
                         cwd=root, stdout=out, stderr=err, stdin=subprocess.DEVNULL, creationflags=flags)
    (logdir / "comfyui.pid").write_text(str(p.pid), encoding="utf-8")
    api = ComfyApi(f"http://127.0.0.1:{port}")
    with step("comfy.start_portable", {"root": str(root), "port": port, "pid": p.pid}):
        t0 = time.time()
        while time.time() - t0 < 300:
            if api.is_up():
                return p.pid
            if p.poll() is not None:
                raise RuntimeError(f"ComfyUI が終了しました（{logdir / 'comfyui.err.log'} を確認）")
            time.sleep(1)
        raise TimeoutError("ComfyUI が 300 秒以内に起動しませんでした")


def stop_portable(pid):
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
    log("comfy.stop_portable", {"pid": pid}, "ok")


# ---- MiniMax H3（ComfyUI 標準ノード）---------------------------------------------

H3_FPS = 24
H3_DEFAULTS = {
    # Hugging Face「Comfy-Org/MiniMax-H3」の ComfyUI 用ファイル名
    "unet": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "text_encoder": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "video_vae": "minimax_h3_video_vae_fp16.safetensors",
    "audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
    "lora": "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors",
}


def h3_frames(seconds):
    """秒を 24fps のフレーム数に直し、H3 が受け付ける 17k+5 へ切り上げる。"""
    n = max(5, int(round(seconds * H3_FPS)))
    return n + (5 - (n % 17)) % 17


def h3_canvas(aspect, megapixels):
    """"16:9" のような比と画素数から、32 の倍数のキャンバスサイズを返す。"""
    rw, rh = (float(x) for x in aspect.split(":"))
    scale = (megapixels * 1_000_000 / (rw * rh)) ** 0.5
    return max(32, round(rw * scale / 32) * 32), max(32, round(rh * scale / 32) * 32)


H3_REF_UNET = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
H3_MAX_REF_IMAGES = 9


def _h3_loaders(unet, text_encoder, video_vae, audio_vae, lora, lora_strength):
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "4": {"class_type": "CLIPLoader", "inputs": {"clip_name": text_encoder, "type": "minimax",
                                                     "device": "default"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": video_vae}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": audio_vae}},
    }
    model = ["1", 0]
    if lora and lora_strength > 0:
        g["2"] = {"class_type": "LoraLoaderModelOnly",
                  "inputs": {"model": model, "lora_name": lora, "strength_model": lora_strength}}
        model = ["2", 0]
    return g, model


def _h3_sample_and_save(g, model, steps, sampler, turbo_sampler, seed, prefix, audio=None):
    """条件付け（ノード "10"）をサンプリングして保存する。audio を渡せば生成音の代わりにそれを載せる。"""
    # Turbo サンプラー（カスタムノード）は映像と音声を別の速さで進める。無ければ標準の er_sde
    g["11"] = ({"class_type": "MiniMaxH3TurboSampler", "inputs": {}} if turbo_sampler
               else {"class_type": "KSamplerSelect", "inputs": {"sampler_name": sampler}})
    g["12"] = {"class_type": "BasicScheduler", "inputs": {"model": model, "scheduler": "simple",
                                                          "steps": steps, "denoise": 1.0}}
    g["13"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["14"] = {"class_type": "BasicGuider", "inputs": {"model": model, "conditioning": ["10", 0]}}
    g["15"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": ["13", 0], "guider": ["14", 0], "sampler": ["11", 0], "sigmas": ["12", 0],
        "latent_image": ["10", 1]}}
    g["16"] = {"class_type": "VAEDecode", "inputs": {"samples": ["15", 0], "vae": ["5", 0]}}
    if audio is None:
        g["17"] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["15", 0], "vae": ["6", 0]}}
        audio = ["17", 0]
    g["18"] = {"class_type": "CreateVideo", "inputs": {"images": ["16", 0], "fps": H3_FPS,
                                                       "audio": audio, "bit_depth": 8}}
    g["19"] = {"class_type": "SaveVideo", "inputs": {"video": ["18", 0], "filename_prefix": prefix,
                                                     "format": "auto", "codec": "auto"}}
    return g


def h3_graph(prompt, first_frame, seconds, seed, unet, text_encoder, video_vae, audio_vae,
             lora=None, lora_strength=0.6, steps=10, sampler="er_sde", turbo_sampler=False,
             aspect="16:9", megapixels=0.4, prefix="video/zvideo_h3"):
    """画像（任意）とプロンプトから、声・効果音つきの動画を作る H3 のグラフ（fl2va 重み）。"""
    width, height = h3_canvas(aspect, megapixels)
    g, model = _h3_loaders(unet, text_encoder, video_vae, audio_vae, lora, lora_strength)
    cond = {"clip": ["4", 0], "vae": ["5", 0], "prompt": prompt, "width": width, "height": height,
            "length": h3_frames(seconds)}
    if first_frame:
        g["20"] = {"class_type": "LoadImage", "inputs": {"image": first_frame}}
        cond["first_frame"] = ["20", 0]
    g["10"] = {"class_type": "MiniMaxH3ImageToVideo", "inputs": cond}
    return _h3_sample_and_save(g, model, steps, sampler, turbo_sampler, seed, prefix)


def h3_ref_graph(prompt, ref_images, ref_audio, seconds, seed, unet, text_encoder, video_vae, audio_vae,
                 lora=None, lora_strength=0.6, steps=10, sampler="er_sde", turbo_sampler=False,
                 aspect="16:9", megapixels=0.4, audio_source="generated", audio_start=0.0,
                 ref_image_size="match", prefix="video/zvideo_h3ref"):
    """参照画像（最大9枚）と参照音声から動画を作る H3 のグラフ（ref2va 重み）。

    プロンプトでは画像を <Picture N>、音声を <Audio 1> として本文から指す。
    audio_source="reference" は参照音声を加工せずそのまま動画に載せる（声の劣化がない）。
    "generated" は H3 が作った音（参照音声の写し＋効果音など）を載せる。
    """
    ref_images = list(ref_images or [])
    if not ref_images and not ref_audio:
        raise ValueError("ref2va には参照画像か参照音声が少なくとも1つ要る")
    if len(ref_images) > H3_MAX_REF_IMAGES:
        raise ValueError(f"参照画像は {H3_MAX_REF_IMAGES} 枚まで: {len(ref_images)}")
    if audio_source not in ("generated", "reference"):
        raise ValueError(f"audio_source は generated か reference: {audio_source!r}")
    if audio_source == "reference" and not ref_audio:
        raise ValueError("audio_source='reference' には参照音声が要る")
    width, height = h3_canvas(aspect, megapixels)
    frames = h3_frames(seconds)
    g, model = _h3_loaders(unet, text_encoder, video_vae, audio_vae, lora, lora_strength)
    cond = {"clip": ["4", 0], "vae": ["5", 0], "audio_vae": ["6", 0], "prompt": prompt, "width": width,
            "height": height, "length": frames, "ref_image_size": ref_image_size}
    for i, name in enumerate(ref_images):
        g[str(30 + i)] = {"class_type": "LoadImage", "inputs": {"image": name}}
        # Autogrow 入力は "<グループ>.<接頭辞><番号>" というドット付きの名前で受ける
        cond[f"ref_images.ref_image_{i}"] = [str(30 + i), 0]
    trimmed = None
    if ref_audio:
        g["40"] = {"class_type": "LoadAudio", "inputs": {"audio": ref_audio}}
        # 生成尺ちょうどに切る。長い音声を渡すと、映像にない区間まで条件付けに混ざる
        g["41"] = {"class_type": "TrimAudioDuration", "inputs": {"audio": ["40", 0], "start_index": audio_start,
                                                                 "duration": frames / H3_FPS}}
        trimmed = ["41", 0]
        cond["ref_audios.ref_audio_0"] = trimmed
    g["10"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": cond}
    return _h3_sample_and_save(g, model, steps, sampler, turbo_sampler, seed, prefix,
                               audio=trimmed if audio_source == "reference" else None)



MUSIC3_DEFAULTS = {
    # Hugging Face「Comfy-Org/MiniMax-Music-3」の ComfyUI 用ファイル名（int8 は VRAM 16GB 向け）
    "unet": "minimax_music3_dit_int8_convrot.safetensors",
    "text_encoder": "minimax_music3_text_encoder_pruned_int8_convrot.safetensors",
    "vae": "minimax_music3_dav.safetensors",
}


def music3_graph(caption, seconds, seed, lyrics="[Intro]\n[Instrumental]\n[Outro]", unet=MUSIC3_DEFAULTS["unet"],
                 text_encoder=MUSIC3_DEFAULTS["text_encoder"], vae=MUSIC3_DEFAULTS["vae"], steps=30, cfg=1.7,
                 enc_cfg=1.7, top_k=50, tiled=False, prefix="audio/zvideo_music3"):
    """MiniMax Music 3 で曲を作るグラフ。既定は歌なし（歌詞の欄はセクションのタグだけ）の BGM。

    caption は曲の説明（英語。Global Metadata / Vocal Details / Arrangement の 3 節で書くと寄る）。
    seconds は上限で、実際の長さは文章エンコードがモデルの判断で決める（40〜55 秒で終わりやすい）。
    文章エンコードは自己回帰で音の条件を 1 フレームずつ作り、モデルが終わりを出した所で止まる。
    空の潜在をその長さより長くすると、条件のない区間が雑音になるので、長さは必ずエンコードの出力に合わせる。
    長い曲が要るときは、別の seed のテイクをつなぐかループする。
    ComfyUI 公式テンプレート audio_minimax_music_3 と同じ構成。
    """
    decode = ({"class_type": "VAEDecodeAudioTiled", "inputs": {"samples": ["7", 0], "vae": ["3", 0],
                                                               "tile_size": 1536, "overlap": 64}} if tiled
              else {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}})
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": text_encoder, "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
        "4": {"class_type": "MiniMaxMusic3TextEncode", "inputs": {
            "clip": ["2", 0], "caption": caption, "lyrics": lyrics, "seed": seed, "max_duration": float(seconds),
            "cfg_scale": enc_cfg, "top_k": top_k}},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "6": {"class_type": "EmptyMiniMaxMusic3LatentAudio", "inputs": {"seconds": ["4", 1], "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0], "seed": seed,
            "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "8": decode,
        "9": {"class_type": "SaveAudio", "inputs": {"audio": ["8", 0], "filename_prefix": prefix}},
    }
