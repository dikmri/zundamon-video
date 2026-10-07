"""VOICEVOX エンジン（HTTP API）の起動確認と音声合成。合成結果は runtime/cache/voice にキャッシュする。"""
import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import wave

from .log import log, step
from .paths import CACHE, LOGS, VOICEVOX_DIR

HOST = "http://127.0.0.1:50021"
SAMPLE_RATE = 48000


def _request(path, data=None, timeout=60):
    req = urllib.request.Request(HOST + path, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def engine_version():
    try:
        return json.loads(_request("/version", timeout=3))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def ensure_engine(timeout=180):
    version = engine_version()
    if version:
        log("voicevox.ensure_engine", None, f"running {version}")
        return version
    exe = VOICEVOX_DIR / "run.exe"
    if not exe.exists():
        raise RuntimeError("VOICEVOX エンジンがありません。先に `uv run python -m zvideo.setup_env` を実行してください")
    LOGS.mkdir(parents=True, exist_ok=True)
    with step("voicevox.start_engine", {"exe": str(exe)}) as s:
        logf = open(LOGS / "voicevox_engine.log", "ab")
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([str(exe), "--host", "127.0.0.1", "--port", "50021"], cwd=VOICEVOX_DIR,
                         stdout=logf, stderr=subprocess.STDOUT, creationflags=flags)
        t0 = time.time()
        while time.time() - t0 < timeout:
            version = engine_version()
            if version:
                s.result = f"ready {version}"
                return version
            time.sleep(1)
        raise RuntimeError(f"VOICEVOX エンジンが {timeout} 秒以内に起動しませんでした（logs/voicevox_engine.log を確認）")


def wav_duration(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def synthesize(text, speaker, speed=1.0, pitch=0.0, intonation=1.0, volume=1.0, pre=0.05, post=0.08):
    params = {"text": text, "speaker": speaker, "speed": speed, "pitch": pitch,
              "intonation": intonation, "volume": volume, "pre": pre, "post": post, "sr": SAMPLE_RATE}
    key = hashlib.sha1(json.dumps(params, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    cache = CACHE / "voice"
    wav_path, query_path = cache / f"{key}.wav", cache / f"{key}.json"
    if wav_path.exists() and query_path.exists():
        query = json.loads(query_path.read_text(encoding="utf-8"))
        duration = wav_duration(wav_path)
        log("voicevox.synthesize", {"speaker": speaker, "text": text}, f"cache=hit {duration:.2f}s {wav_path.name}")
        return {"wav": wav_path, "query": query, "duration": duration}

    cache.mkdir(parents=True, exist_ok=True)
    args = {"speaker": speaker, "text": text}
    with step("voicevox.audio_query", args):
        qs = urllib.parse.urlencode({"text": text, "speaker": speaker})
        query = json.loads(_request(f"/audio_query?{qs}", data=b""))
    query.update({"speedScale": speed, "pitchScale": pitch, "intonationScale": intonation,
                  "volumeScale": volume, "prePhonemeLength": pre, "postPhonemeLength": post,
                  "outputSamplingRate": SAMPLE_RATE, "outputStereo": False})
    with step("voicevox.synthesis", args) as s:
        wav = _request(f"/synthesis?speaker={speaker}", data=json.dumps(query).encode("utf-8"), timeout=180)
        wav_path.write_bytes(wav)
        query_path.write_text(json.dumps(query, ensure_ascii=False), encoding="utf-8")
        duration = wav_duration(wav_path)
        s.result = f"cache=miss {duration:.2f}s {wav_path.name}"
    return {"wav": wav_path, "query": query, "duration": duration}
