"""ポータルのローカル配信サーバー（任意）。portal/index.html は file:// で直接開いても動く。

サーバーを使うのは、スマホなど他の端末から見るときと、ブラウザ側のログを logs/portal.log に直接残したいとき。
URL の形はリポジトリ内の配置と同じにして、ページ内の相対パスがどちらの開き方でも同じ所を指すようにする。

/portal/...                 サイト本体（/ はここへ転送）
/runtime/portal/...         カタログ（catalog.js）とサムネイル類
/out/<名>/<名>.mp4          動画（Range 要求に対応し、シークできる）
POST /api/log               ブラウザ側のイベントを logs/portal.log に追記
POST /api/rescan            カタログを作り直す
"""
import http.server
import json
import re
import threading
import urllib.parse

from ..paths import OUT
from .media import CATALOG_DIR, WEB, build_catalog, plog
CHUNK = 256 * 1024
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
         ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
         ".mp4": "video/mp4", ".webm": "video/webm", ".ico": "image/x-icon", ".woff2": "font/woff2",
         ".txt": "text/plain; charset=utf-8"}
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
_rescan_lock = threading.Lock()


class RangeError(ValueError):
    pass


def parse_range(header, size):
    """Range ヘッダーを (先頭, 末尾) のバイト位置にする。指定なし・解釈できないときは None（全体を返す）。"""
    if not header:
        return None
    m = _RANGE.match(header.split(",")[0].strip())
    if not m or (not m.group(1) and not m.group(2)):
        return None
    a, b = m.group(1), m.group(2)
    if not a:
        n = int(b)
        return max(0, size - n), size - 1
    start = int(a)
    if start >= size:
        raise RangeError(f"start {start} >= size {size}")
    end = min(int(b), size - 1) if b else size - 1
    if end < start:
        raise RangeError(f"end {end} < start {start}")
    return start, end


def _inside(base, path):
    base, path = base.resolve(), path.resolve()
    return path == base or base in path.parents


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "ZundaArchive/1.0"

    def log_message(self, fmt, *args):
        pass

    def _resolve(self, path):
        """URL を (公開してよい範囲, ファイル) にする。範囲外は None。"""
        parts = [p for p in path.split("/") if p]
        if parts[:1] == ["portal"]:
            return WEB, WEB.joinpath(*(parts[1:] or ["index.html"]))
        if parts[:2] == ["runtime", "portal"]:
            return CATALOG_DIR, CATALOG_DIR.joinpath(*parts[2:])
        if parts[:1] == ["out"] and len(parts) == 3 and parts[2] == f"{parts[1]}.mp4":
            return OUT, OUT / parts[1] / parts[2]
        if parts == ["favicon.ico"]:
            return WEB, WEB / "favicon.svg"
        return None, None

    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head=False):
        url = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(url.path)
        if path in ("/", "/portal"):
            self.send_response(302)
            self.send_header("Location", "/portal/")
            self.end_headers()
            return
        base, file = self._resolve(path)
        if base is None or not _inside(base, file) or not file.is_file():
            plog("http.404", {"path": path})
            self.send_error(404)
            return
        size = file.stat().st_size
        try:
            rng = parse_range(self.headers.get("Range"), size)
        except RangeError as e:
            plog("http.416", {"path": path, "range": self.headers.get("Range")}, str(e))
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return
        start, end = rng or (0, size - 1)
        if path.startswith("/out/") and (rng is None or start == 0):
            plog("http.media", {"path": path, "range": self.headers.get("Range")}, f"size={size}")
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", TYPES.get(file.suffix.lower(), "application/octet-stream"))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        immutable = "v=" in url.query
        self.send_header("Cache-Control", "public, max-age=31536000, immutable" if immutable else "no-cache")
        self.end_headers()
        if head:
            return
        try:
            with file.open("rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    buf = f.read(min(CHUNK, left))
                    if not buf:
                        break
                    self.wfile.write(buf)
                    left -= len(buf)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # シークや画面遷移でブラウザが途中で切るのは正常

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", TYPES[".json"])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        if n > 256 * 1024:
            self._json(413, {"error": "too large"})
            return
        raw = self.rfile.read(n).decode("utf-8", "replace")
        if path == "/api/log":
            try:
                items = json.loads(raw or "[]")
            except json.JSONDecodeError:
                items = [{"event": "log.unparsed", "result": raw[:2000]}]
            for it in items if isinstance(items, list) else [items]:
                plog("web." + str(it.get("event", "?")), it.get("args"), it.get("result"))
            self.send_response(204)
            self.end_headers()
            return
        if path == "/api/rescan":
            with _rescan_lock:
                try:
                    cat = build_catalog(force=False)
                except Exception as e:
                    plog("portal.rescan.error", None, f"ERROR {type(e).__name__}: {e}")
                    self._json(500, {"error": str(e)})
                    return
            self._json(200, {"videos": len(cat["videos"]), "generated": cat["generated"]})
            return
        self._json(404, {"error": "not found"})


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        plog("http.error", {"client": client_address[0]}, f"ERROR {type(exc).__name__}: {exc}")


def serve(host="127.0.0.1", port=8770):
    server = Server((host, port), Handler)
    port = server.server_address[1]
    plog("portal.server.start", {"host": host, "web": str(WEB)}, f"http://{host}:{port}/")
    return server, port
