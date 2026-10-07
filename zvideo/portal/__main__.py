"""zundamon-video で作った動画のポータル。

uv run python -m zvideo.portal               # カタログを更新して portal/index.html をブラウザで開く（サーバー不要）
uv run python -m zvideo.portal --no-open     # カタログ（サムネイル等）の更新だけ
uv run python -m zvideo.portal --serve       # ローカルサーバーで開く（ブラウザ側のログも logs/portal.log に残る）
uv run python -m zvideo.portal --serve --lan # 同じネットワークのスマホ等からも見られるようにする

`zvideo render` で mp4 を書き出すと、カタログは自動で更新される。
ログ: logs/portal.log（1行1イベント: 時刻 | イベント | 引数 | 結果）
"""
import argparse
import socket
import sys
import webbrowser

from .media import build_catalog, page_uri, plog


def _lan_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="zvideo.portal")
    ap.add_argument("--serve", action="store_true", help="ローカルサーバーで開く")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--lan", action="store_true", help="--serve のとき、LAN 内の他の端末からも接続できるようにする")
    ap.add_argument("--force", action="store_true", help="サムネイル等をすべて作り直す")
    ap.add_argument("--no-open", "--build-only", dest="no_open", action="store_true", help="ブラウザを開かない")
    a = ap.parse_args(argv)
    plog("portal.cli", {"argv": sys.argv[1:] if argv is None else argv})

    cat = build_catalog(force=a.force)
    print(f"catalog: {len(cat['videos'])} videos")
    if not a.serve:
        uri = page_uri()
        print("portal:", uri)
        if not a.no_open:
            webbrowser.open(uri)
            plog("portal.open", {"uri": uri})
        return

    from .server import serve
    server, port = serve("0.0.0.0" if a.lan else "127.0.0.1", a.port)
    url = f"http://127.0.0.1:{port}/portal/"
    print("portal:", url, "(Ctrl+C で終了)")
    if a.lan:
        print("LAN:", f"http://{_lan_ip()}:{port}/portal/")
    print("log: logs/portal.log")
    if not a.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        plog("portal.server.stop")
        server.shutdown()


if __name__ == "__main__":
    main()
