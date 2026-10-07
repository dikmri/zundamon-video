"""セリフ・効果音・BGM を1本のステレオ wav にまとめる。"""
import json
import os
import re
import subprocess
import wave

import numpy as np

from .log import step

SR = 48000


def decode(path, sr=SR):
    """ffmpeg で任意の音声を float32 ステレオ (n, 2) に変換する。"""
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(sr), "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)


def _place(buf, clip, start_sec, gain):
    i = int(round(start_sec * SR))
    if i >= len(buf) or i + len(clip) <= 0:
        return
    j = min(len(buf), i + len(clip))
    s = max(0, -i)
    buf[max(0, i):j] += clip[s:s + (j - max(0, i))] * gain


def loudnorm(src, dst, target=-16.0, true_peak=-1.5, lra=11.0):
    """ffmpeg loudnorm の2パスで、動画配信向けの音量（既定 -16 LUFS）にそろえる。"""
    base = f"loudnorm=I={target}:TP={true_peak}:LRA={lra}"
    with step("audio.loudnorm", {"target": target, "src": str(src)}) as s:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-af", base + ":print_format=json", "-f", "null", "-"],
                           check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = json.loads(re.findall(r"\{[^{}]*\}", r.stderr)[-1])
        measured = (f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
                    f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", base + measured, "-ar", str(SR), str(dst)],
                       check=True)
        s.result = f"input_i={m['input_i']} input_tp={m['input_tp']} -> {target}"
    return dst


def duck_envelope(n, intervals, level=0.25, ramp=0.5, sr=SR):
    """BGM を下げる区間の音量カーブ（1.0=そのまま）。区間の前後 ramp 秒でなめらかに増減する。"""
    env = np.ones(n, dtype=np.float32)
    if not intervals:
        return env
    t = np.arange(n, dtype=np.float32) / sr
    for a, b in intervals:
        down = np.clip((t - (a - ramp / 2)) / ramp, 0, 1)
        up = np.clip(((b + ramp / 2) - t) / ramp, 0, 1)
        env = np.minimum(env, 1 - np.minimum(down, up) * (1 - level))
    return env


def media_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         check=True, capture_output=True, text=True).stdout.strip()
    return float(out)


def has_audio(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                          "-of", "csv=p=0", str(path)], check=True, capture_output=True, text=True).stdout.strip()
    return bool(out)


def transcode_webm(src, dst):
    """描画用の Chromium で確実に再生できる VP9 / 音声なしの WebM にする（元より新しければ作り直さない）。"""
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    with step("media.transcode_webm", {"src": str(src)}) as s:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-an", "-c:v", "libvpx-vp9", "-crf", "30",
                        "-b:v", "0", "-g", "12", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", str(dst)],
                       check=True)
        s.result = f"{dst.stat().st_size} bytes"
    return dst


def mix(total, voices, effects, bgm, out_path, bgm_fade_in=1.0, bgm_fade_out=2.5, loudness=-16.0, duck=()):
    """voices/effects: [(開始秒, パス, 音量)]、bgm: (パス, 音量) か None。"""
    n = int(round(total * SR))
    buf = np.zeros((n, 2), dtype=np.float32)
    cache = {}

    def clip(path):
        if path not in cache:
            cache[path] = decode(path)
        return cache[path]

    with step("audio.mix", {"voices": len(voices), "effects": len(effects), "bgm": str(bgm[0]) if bgm else None,
                            "total": round(total, 2)}) as s:
        for start, path, gain in voices:
            _place(buf, clip(path), start, gain)
        for start, path, gain in effects:
            _place(buf, clip(path), start, gain)
        if bgm:
            b = clip(bgm[0])
            reps = n // len(b) + 1
            track = np.tile(b, (reps, 1))[:n] * bgm[1]
            env = np.ones(n, dtype=np.float32)
            fi, fo = int(bgm_fade_in * SR), int(bgm_fade_out * SR)
            env[:fi] = np.linspace(0, 1, fi, dtype=np.float32)
            env[n - fo:] = np.minimum(env[n - fo:], np.linspace(1, 0, fo, dtype=np.float32))
            env *= duck_envelope(n, list(duck))  # 埋め込み動画の音が鳴る間は BGM を下げる
            buf += track * env[:, None]
        peak = float(np.abs(buf).max()) if n else 0.0
        if peak > 0.97:
            buf *= 0.97 / peak
        pcm = (np.clip(buf, -1, 1) * 32767).astype("<i2")
        # 中間ファイルはプロセスごとに別名にし、完成品は最後に置き換える。
        # 同じ出力先へ build が2つ同時に走っても、互いの途中のファイルを読まないようにするため。
        pid = os.getpid()
        raw_path = out_path.with_name(f"{out_path.stem}_raw_{pid}.wav")
        tmp_path = out_path.with_name(f"{out_path.stem}_tmp_{pid}.wav")
        with wave.open(str(raw_path), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        s.result = f"peak={peak:.3f} {raw_path.name}"
    try:
        if loudness is not None:
            loudnorm(raw_path, tmp_path, target=loudness)
        else:
            raw_path.replace(tmp_path)
        with wave.open(str(tmp_path), "rb") as w:
            got = w.getnframes() / w.getframerate()
        if abs(got - n / SR) > 0.05:
            raise RuntimeError(f"音声の長さが合いません（期待 {n / SR:.2f}s、実際 {got:.2f}s）")
        os.replace(tmp_path, out_path)
    finally:
        for p in (raw_path, tmp_path):
            p.unlink(missing_ok=True)
    return out_path
