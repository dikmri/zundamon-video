"""公開用サイト（GitHub Pages）へ動画を公開する。

公開は、ユーザーが書き出した動画を確認して「公開して」と伝えてから行う。書き出しただけでは公開しない。

uv run python -m zvideo.portal.publish --init <owner>/<repo> --all  # 初回: リポジトリを作り、書き出し済みの動画をすべて公開
uv run python -m zvideo.portal.publish <名前> [<名前> ...]          # 指定した動画を公開（書き出し直した動画は差し替え）
uv run python -m zvideo.portal.publish --remove <名前>              # 公開をやめる（リリースの mp4 も消す）
uv run python -m zvideo.portal.publish --build-only                 # 公開用サイトを runtime/site に組み立てるだけ（GitHub には送らない）
uv run python -m zvideo.portal.publish --status                     # 公開状況を表示

動画はサイトのリポジトリのリリース（タグ videos）に置き、サイト本体は main ブランチを GitHub Pages で公開する。
作業コピー: runtime/site/　ログ: logs/portal.log
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
from datetime import datetime

from ..log import step
from ..paths import OUT, PLAYWRIGHT_BROWSERS, ROOT, RUNTIME
from .media import (CATALOG_DIR, PORTAL_LOG, PUBLISHED_JSON, SITE_DIR, WEB, build_catalog, plog, read_published,
                    video_version)
from .site import (asset_name, hls_asset_name, pages_url, parse_remote, public_catalog, public_index_html, release_url,
                   rewrite_playlist, uploads_needed)

TAG = "videos"
DESCRIPTION = "ずんだもんと四国めたんの解説動画アーカイブ（zundamon-video で制作）"
UPLOAD_DIR = RUNTIME / "site_upload"


class PublishError(RuntimeError):
    pass


def _run(args, what, cwd=None, check=True):
    """外部コマンド（git / gh）を実行し、1行ずつログに残す。"""
    shown = " ".join(str(a) for a in args[:6]) + (" …" if len(args) > 6 else "")
    with step(f"publish.{what}", {"cmd": shown}, file=PORTAL_LOG) as s:
        r = subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        s.result = f"exit={r.returncode}"
        if check and r.returncode != 0:
            raise PublishError(f"{shown} が失敗しました: {(r.stderr or r.stdout).strip()[-800:]}")
    return r


def git(*args, what="git", check=True):
    return _run(["git", "-C", SITE_DIR, *args], what, check=check)


def gh(*args, what="gh", check=True):
    return _run(["gh", *args], what, check=check)


# ------------------------------------------------------------------ リポジトリ

def site_repo():
    """作業コピーの remote から (owner, repo)。まだなければ None。"""
    if not (SITE_DIR / ".git").is_dir():
        return None
    r = git("remote", "get-url", "origin", what="git.remote", check=False)
    return parse_remote(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def ensure_repo(slug, remote):
    """作業コピーを用意する。remote=True なら GitHub 上にリポジトリがなければ作る。"""
    current = site_repo()
    if current and slug and "/".join(current) != slug:
        raise PublishError(f"runtime/site は {'/'.join(current)} の作業コピーです（指定: {slug}）")
    owner, repo = current or (slug.split("/", 1) if slug else (None, None))
    if not owner:
        raise PublishError("初回は --init <owner>/<repo> で公開先のリポジトリを指定してください")
    slug = f"{owner}/{repo}"
    exists = remote and gh("repo", "view", slug, "--json", "name", what="gh.repo.view", check=False).returncode == 0
    if remote and not exists:
        gh("repo", "create", slug, "--public", "--description", DESCRIPTION, "--homepage", pages_url(owner, repo),
           what="gh.repo.create")
    if not (SITE_DIR / ".git").is_dir():
        SITE_DIR.mkdir(parents=True, exist_ok=True)
        has_commits = exists and gh("api", f"repos/{slug}/commits?per_page=1", what="gh.api.commits",
                                    check=False).returncode == 0
        if has_commits:
            shutil.rmtree(SITE_DIR)
            gh("repo", "clone", slug, str(SITE_DIR), what="gh.repo.clone")
        else:
            git("init", "-b", "main", what="git.init")
            git("remote", "add", "origin", f"https://github.com/{slug}.git", what="git.remote.add")
        # 作者はツールキットのリポジトリと同じ（noreply アドレス）にする
        for key in ("user.name", "user.email"):
            r = _run(["git", "-C", ROOT, "config", key], "git.config.read", check=False)
            if r.stdout.strip():
                git("config", key, r.stdout.strip(), what="git.config")
    return owner, repo


def has_commits():
    return git("rev-parse", "--verify", "HEAD", what="git.head", check=False).returncode == 0


def commit_and_push(message, co_author=None, push=True):
    git("add", "-A", what="git.add")
    if not git("status", "--porcelain", what="git.status").stdout.strip():
        plog("publish.commit", None, "変更なし")
        return False
    if co_author:
        message += f"\n\nCo-Authored-By: {co_author}"
    git("commit", "-m", message, what="git.commit")
    if push:
        git("push", "-u", "origin", "main", what="git.push")
    return True


def ensure_release(slug):
    if gh("release", "view", TAG, "-R", slug, what="gh.release.view", check=False).returncode == 0:
        return
    gh("release", "create", TAG, "-R", slug, "--title", "Videos", "--target", "main",
       "--notes", "Zunda Archive で公開している動画（mp4）です。サイト: " + pages_url(*slug.split("/")),
       what="gh.release.create")


def ensure_pages(slug):
    if gh("api", f"repos/{slug}/pages", what="gh.pages.view", check=False).returncode == 0:
        return False
    gh("api", "-X", "POST", f"repos/{slug}/pages", "-f", "source[branch]=main", "-f", "source[path]=/",
       what="gh.pages.create")
    return True


def upload_video(slug, name):
    src = OUT / name / f"{name}.mp4"
    asset = asset_name(name)
    path = src
    if asset != src.name:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        path = UPLOAD_DIR / asset
        shutil.copyfile(src, path)
    gh("release", "upload", TAG, str(path), "-R", slug, "--clobber", what="gh.release.upload")
    if path != src:
        path.unlink()
    return asset


def upload_hls(owner, repo, name, version):
    """Safari 向けの HLS を作って上げ、再生リストをサイトに書く。

    iPhone の Safari は、種類不明（application/octet-stream）で返るリリース添付の mp4 を再生できないことがある。
    HLS なら形式を再生リストに書けるので、動画本体は同じリリース添付から範囲指定で読める。
    """
    work = UPLOAD_DIR / "hls" / name
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    seg = hls_asset_name(name)
    _run(["ffmpeg", "-y", "-v", "error", "-i", OUT / name / f"{name}.mp4", "-c", "copy", "-f", "hls", "-hls_time", "6",
          "-hls_playlist_type", "vod", "-hls_segment_type", "fmp4", "-hls_flags", "single_file",
          "-hls_segment_filename", work / seg, work / "video.m3u8"], "ffmpeg.hls")
    gh("release", "upload", TAG, str(work / seg), "-R", f"{owner}/{repo}", "--clobber", what="gh.release.upload_hls")
    playlist = rewrite_playlist((work / "video.m3u8").read_text(encoding="utf-8"), seg,
                                release_url(owner, repo, TAG, seg, version))
    dest = SITE_DIR / "data" / name / "video.m3u8"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(playlist, encoding="utf-8")
    shutil.rmtree(work)


def make_check_clip():
    """確認用ページ（check.html）で使う短い動画。画素形式を一般的な yuv420p（tv レンジ）にしたもの。"""
    dest = SITE_DIR / "check" / "yuv420p.mp4"
    if dest.is_file():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = next(iter(sorted(CATALOG_DIR.glob("*/preview.mp4"))), None)
    if src is None:
        return
    _run(["ffmpeg", "-y", "-v", "error", "-i", src, "-t", "4", "-vf", "scale=in_range=pc:out_range=tv,format=yuv420p",
          "-color_range", "tv", "-c:v", "libx264", "-profile:v", "main", "-crf", "28", "-an", "-movflags", "+faststart",
          dest], "ffmpeg.check_clip")


# ------------------------------------------------------------------ サイトの組み立て

def _local_file(url):
    """公開用カタログ内の data/... の URL から、手元のファイル。"""
    rel = urllib.parse.unquote(url.split("?", 1)[0])
    if not rel.startswith("data/"):
        return None
    return CATALOG_DIR / rel[len("data/"):]


def _copy_if_changed(src, dst):
    if dst.is_file() and dst.stat().st_size == src.stat().st_size and dst.read_bytes() == src.read_bytes():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True


def _referenced(pub):
    urls = []
    for v in pub["videos"]:
        urls += [v["poster"], v["preview"], (v.get("sprite") or {}).get("src"), v["video"].get("hls")]
        urls += [e.get("thumb") for e in v.get("toc", [])]
        for c in v["cast"].values():
            urls += list((c.get("portrait") or {}).values())
    return {u.split("?", 1)[0] for u in urls if u and u.startswith("data/")}


def build_site(owner, repo, published, make_og=False):
    """runtime/site に公開用サイトを組み立てる。"""
    local = build_catalog()
    pub = public_catalog(local, published.get("videos", {}), owner, repo, TAG)
    site_url = pages_url(owner, repo)
    with step("publish.build_site", {"videos": [v["id"] for v in pub["videos"]]}, file=PORTAL_LOG) as s:
        # サイト本体（HTML・CSS・JS）
        html = (WEB / "index.html").read_text(encoding="utf-8")
        (SITE_DIR / "index.html").write_text(public_index_html(html, site_url), encoding="utf-8")
        for sub in ("css", "js"):
            for f in (WEB / sub).iterdir():
                if f.is_file():
                    _copy_if_changed(f, SITE_DIR / sub / f.name)
        _copy_if_changed(WEB / "favicon.svg", SITE_DIR / "favicon.svg")
        _copy_if_changed(WEB / "check.html", SITE_DIR / "check.html")
        make_check_clip()
        (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
        # カタログとサムネイル類
        data = SITE_DIR / "data"
        data.mkdir(parents=True, exist_ok=True)
        (data / "catalog.js").write_text("window.ZA_CATALOG = " + json.dumps(pub, ensure_ascii=False) + ";\n",
                                         encoding="utf-8")
        keep = _referenced(pub)
        copied = 0
        for rel in sorted(keep):
            if rel.endswith(".m3u8"):
                if not (SITE_DIR / rel).is_file():
                    raise PublishError(f"HLS の再生リストがありません: {rel}（--hls で作り直してください）")
                continue
            src = _local_file(rel)
            if not src or not src.is_file():
                raise PublishError(f"サムネイル類が見つかりません: {src}")
            copied += _copy_if_changed(src, SITE_DIR / rel)
        # 公開をやめた動画のファイルを消す
        removed = 0
        for f in list(data.rglob("*")):
            rel = f.relative_to(SITE_DIR).as_posix()
            if f.is_file() and rel not in keep and f.name not in ("catalog.js", "published.json"):
                f.unlink()
                removed += 1
        for d in sorted((p for p in data.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
        if make_og or not (SITE_DIR / "og.jpg").is_file():
            make_og_image()
        s.result = {"copied": copied, "removed": removed, "files": len(keep)}
    return pub


def make_og_image():
    """SNS で共有したときのカード画像（1200×630）。組み立てたサイトのトップを撮る。"""
    from playwright.sync_api import sync_playwright

    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(PLAYWRIGHT_BROWSERS)
    png = SITE_DIR / "og.png"
    with step("publish.og_image", None, file=PORTAL_LOG):
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
            page.goto((SITE_DIR / "index.html").as_uri())
            page.wait_for_timeout(3500)
            page.add_style_tag(content="html{overflow:hidden!important;scrollbar-gutter:auto!important}"
                                       ".topbar,.hero-scroll,.cursor,.toast{display:none!important}")
            page.wait_for_timeout(300)
            page.screenshot(path=str(png))
            b.close()
        _run(["ffmpeg", "-y", "-v", "error", "-i", png, "-q:v", "3", SITE_DIR / "og.jpg"], "ffmpeg.og")
        png.unlink()


# ------------------------------------------------------------------ 実行

def write_published(published):
    PUBLISHED_JSON.parent.mkdir(parents=True, exist_ok=True)
    PUBLISHED_JSON.write_text(json.dumps(published, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="zvideo.portal.publish", description="公開用サイト（GitHub Pages）へ動画を公開する")
    ap.add_argument("names", nargs="*", help="公開する動画（out/<名前>）")
    ap.add_argument("--all", action="store_true", help="書き出し済みの動画をすべて公開する")
    ap.add_argument("--remove", nargs="+", metavar="名前", help="公開をやめる")
    ap.add_argument("--init", metavar="OWNER/REPO", help="初回に公開先のリポジトリを指定する（なければ作る）")
    ap.add_argument("--build-only", action="store_true", help="runtime/site に組み立てるだけで、GitHub には送らない")
    ap.add_argument("--status", action="store_true", help="公開状況を表示する")
    ap.add_argument("--og", action="store_true", help="共有カード画像（og.jpg）を作り直す")
    ap.add_argument("--hls", action="store_true", help="公開中の動画の HLS（Safari 向け）をすべて作り直す")
    ap.add_argument("--co-author", help="コミットに付ける Co-Authored-By")
    a = ap.parse_args(argv)
    plog("publish.cli", {"argv": sys.argv[1:] if argv is None else argv})

    published = read_published()
    if a.status:
        site = published.get("site") or {}
        print("site:", site.get("url", "（未公開）"))
        for name, p in sorted((published.get("videos") or {}).items(), key=lambda kv: kv[1].get("at", "")):
            print(f"  {name}: {p.get('at', '')}  {p.get('asset')}")
        return

    remote = not a.build_only
    owner, repo = ensure_repo(a.init, remote)
    slug = f"{owner}/{repo}"
    published.setdefault("videos", {})
    published["site"] = {"repo": slug, "url": pages_url(owner, repo), "tag": TAG}

    local = build_catalog()
    available = {v["id"] for v in local["videos"]}
    targets = sorted(available) if a.all else list(a.names)
    unknown = [n for n in targets + (a.remove or []) if n not in available and n not in published["videos"]]
    if unknown:
        raise PublishError(f"out/ に見つからない動画です: {', '.join(unknown)}（書き出し済み: {', '.join(sorted(available))}）")

    if remote and not has_commits():
        # リリースを作るにはコミットが1つ要る
        (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
        commit_and_push("Initialize Zunda Archive", a.co_author)

    changed = []
    for name in a.remove or []:
        p = published["videos"].pop(name, None)
        if p and remote:
            gh("release", "delete-asset", TAG, p["asset"], "-R", slug, "-y", what="gh.release.delete_asset", check=False)
            if p.get("hls"):
                gh("release", "delete-asset", TAG, hls_asset_name(name), "-R", slug, "-y",
                   what="gh.release.delete_asset", check=False)
        changed.append(f"-{name}")

    versions = {n: video_version(n) for n in targets}
    need = uploads_needed(published["videos"], versions, targets)
    if need and remote:
        ensure_release(slug)
    titles = {v["id"]: v["title"] for v in local["videos"]}
    for name in need:
        if remote:
            print(f"uploading {name} …", flush=True)
            asset = upload_video(slug, name)
        else:
            asset = asset_name(name)
        published["videos"][name] = {"asset": asset, "version": versions[name], "title": titles.get(name, name),
                                     "at": datetime.now().isoformat(timespec="seconds")}
        changed.append(name)

    # Safari 向けの HLS: まだ作っていない・書き出し直した・--hls のときに作る
    if remote:
        for name, p in published["videos"].items():
            ver = video_version(name) if (OUT / name / f"{name}.mp4").is_file() else p.get("version")
            if a.hls or p.get("hls") != ver:
                print(f"hls {name} …", flush=True)
                upload_hls(owner, repo, name, ver)
                p["hls"] = ver
                if name not in changed:
                    changed.append(f"{name}(hls)")

    # 組み立てだけのときは記録しない（実際には上げていないので、次の公開で上げ損なわないように）
    if remote:
        write_published(published)
    pub = build_site(owner, repo, published, make_og=a.og or bool(changed))
    if not remote:
        print("built:", (SITE_DIR / "index.html").as_uri(), "（未送信）")
        return

    msg = "Publish: " + ", ".join(changed) if changed else "Update site"
    pushed = commit_and_push(msg, a.co_author)
    created = ensure_pages(slug)
    plog("publish.done", {"changed": changed, "pushed": pushed, "pages_created": created},
         {"url": pages_url(owner, repo), "videos": len(pub["videos"])})
    print("site:", pages_url(owner, repo), "（反映まで1〜2分）" if pushed or created else "")
    for v in pub["videos"]:
        mark = "＊" if v["id"] in changed else "　"
        print(f" {mark} No.{v['no']:02d} {v['title']}  {pages_url(owner, repo)}#/watch/{v['id']}")


if __name__ == "__main__":
    try:
        main()
    except PublishError as e:
        plog("publish.error", None, f"ERROR {e}")
        print("ERROR:", e, file=sys.stderr)
        sys.exit(1)
