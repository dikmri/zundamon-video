"""HTML プレイヤーを Playwright(Chromium) で1フレームずつ撮影し、ffmpeg で mp4 にする。"""
import functools
import http.server
import multiprocessing as mp
import os
import subprocess
import threading
import time
import urllib.parse

from .log import log, step
from .paths import PLAYWRIGHT_BROWSERS, ROOT


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if len(args) > 1 and str(args[1])[:1] in "45":
            log("server.http_error", {"path": self.path}, fmt % args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        if self.path == "/__log":
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace")
            log("preview.js", None, body)
            self.send_response(204)
            self.end_headers()
            return
        self.send_error(404)


def serve(port=0):
    """プロジェクト直下を配信する HTTP サーバーを別スレッドで起動して (server, port) を返す。"""
    handler = functools.partial(_Handler, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    log("server.start", {"root": str(ROOT)}, f"http://127.0.0.1:{port}/")
    return server, port


# 描画用ブラウザは HTTP サーバーを使わず、この仮想オリジンへの要求をディスクから直接返す。
# 複数ブラウザが同時にローカルサーバーへ大量に接続すると、Windows で ERR_NO_BUFFER_SPACE が起きて
# フォントやスクリプトの読み込みが失敗するため。
VIRTUAL_ORIGIN = "http://zv.local"


def _serve_from_disk(route, wid):
    rel = urllib.parse.unquote(urllib.parse.urlparse(route.request.url).path).lstrip("/")
    path = (ROOT / rel).resolve()
    if path.is_file() and (path == ROOT or ROOT in path.parents):
        route.fulfill(path=str(path), headers={"Cache-Control": "no-store"})
    else:
        log("render.not_found", {"worker": wid, "url": route.request.url}, "404")
        route.fulfill(status=404, body="not found")


def _open_page(p, page_path, width, height, wid):
    browser = p.chromium.launch(args=["--force-color-profile=srgb", "--font-render-hinting=none"])
    page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
    page.route(VIRTUAL_ORIGIN + "/**", lambda route: _serve_from_disk(route, wid))
    page.on("console", lambda m: log("render.console", {"worker": wid, "type": m.type}, m.text)
            if m.type in ("error", "warning") or m.text.startswith("[zv]") else None)
    page.on("pageerror", lambda e: log("render.pageerror", {"worker": wid}, str(e)))
    page.goto(f"{VIRTUAL_ORIGIN}/{page_path}?render=1", wait_until="load")
    page.evaluate("window.__ready")
    return browser, page


def _worker(job):
    page_path, first, last, fps, width, height, out_path, wid = job
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(PLAYWRIGHT_BROWSERS)
    from playwright.sync_api import sync_playwright

    with step("render.worker", {"worker": wid, "frames": [first, last], "out": out_path}) as s, sync_playwright() as p:
        browser, page = _open_page(p, page_path, width, height, wid)
        ff = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(fps), out_path],
            stdin=subprocess.PIPE)
        t0 = time.perf_counter()
        for f in range(first, last):
            page.evaluate("t => window.__seek(t)", f / fps)
            ff.stdin.write(page.screenshot(type="jpeg", quality=92))
            if (f - first) % 300 == 0 and f > first:
                log("render.progress", {"worker": wid}, f"{f - first}/{last - first} frames "
                    f"{(f - first) / (time.perf_counter() - t0):.1f} fps")
        ff.stdin.close()
        if ff.wait() != 0:
            raise RuntimeError(f"ffmpeg が失敗しました (worker {wid})")
        browser.close()
        s.result = f"{last - first} frames {(last - first) / (time.perf_counter() - t0):.1f} fps"
    return out_path


def render_video(page_path, total, fps, width, height, audio_path, out_path, workers=4):
    """page_path: ROOT からの相対パス（例 out/h3/index.html）。"""
    n = int(round(total * fps))
    workers = max(1, min(workers, n // fps or 1))
    bounds = [round(i * n / workers) for i in range(workers + 1)]
    seg_dir = out_path.parent / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    jobs = [(page_path, bounds[i], bounds[i + 1], fps, width, height, str(seg_dir / f"seg{i:02d}.mp4"), i)
            for i in range(workers)]
    with step("render.frames", {"frames": n, "workers": workers, "page": page_path}):
        if workers == 1:
            segs = [_worker(jobs[0])]
        else:
            with mp.get_context("spawn").Pool(workers) as pool:
                segs = pool.map(_worker, jobs)

    return mux(segs, audio_path, out_path)


def mux(segs, audio_path, out_path):
    """書き出し済みの映像区間をつなぎ、音声を載せて mp4 にする。"""
    list_file = os.path.join(os.path.dirname(segs[0]), "list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        f.writelines(f"file '{os.path.basename(s)}'\n" for s in segs)
    with step("render.mux", {"audio": str(audio_path), "out": str(out_path)}):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
                        "-i", str(audio_path), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out_path)],
                       check=True)
    return out_path


def snapshot(page_path, times, width, height, out_dir):
    """指定時刻のフレームを PNG で保存する（レイアウト確認用）。"""
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(PLAYWRIGHT_BROWSERS)
    from playwright.sync_api import sync_playwright

    paths = []
    with sync_playwright() as p:
        browser, page = _open_page(p, page_path, width, height, "snap")
        for t in times:
            page.evaluate("t => window.__seek(t)", t)
            path = out_dir / f"frame_{t:07.2f}.png"
            page.screenshot(path=str(path))
            paths.append(path)
            log("render.snapshot", {"t": t}, str(path))
        browser.close()
    return paths
