"""1行1イベントのファイルログ。

形式: 時刻 | イベント名 | 引数 | 結果
例:   2026-10-07T13:05:12.345 | voicevox.synthesis | {"speaker": 3, "text": "なのだ"} | ok 1.23s cache=miss
"""
import json
import time
from datetime import datetime

from .paths import LOGS

LOG_FILE = LOGS / "zvideo.log"


def _fmt(value):
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def log(event, args=None, result=None):
    LOGS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="milliseconds")
    line = f"{stamp} | {event} | {_fmt(args)} | {_fmt(result)}"
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line.replace("\n", "\\n") + "\n")


class step:
    """with step("event", args) as s: ...; s.result = "..."  例外もログに残して再送出する。"""

    def __init__(self, event, args=None):
        self.event, self.args, self.result = event, args, None

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        dt = time.perf_counter() - self.t0
        if exc is not None:
            log(self.event, self.args, f"ERROR {exc_type.__name__}: {exc} ({dt:.2f}s)")
            return False
        log(self.event, self.args, f"ok {dt:.2f}s" + (f" {_fmt(self.result)}" if self.result is not None else ""))
        return False
