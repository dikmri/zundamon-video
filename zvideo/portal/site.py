"""公開用サイト（GitHub Pages）のための純粋な変換。

手元のカタログ（runtime/portal/catalog.js の中身）から、公開した動画だけを含むカタログを作る。
動画はサイトのリポジトリのリリース添付に置き、サムネイル類はサイトの data/ に同梱する。
"""
import copy
import hashlib
import re

from .catalog import top_ending

LOCAL_PREFIX = "../runtime/portal/"


def asset_name(video_id):
    """リリース添付のファイル名。英数字と ._- 以外を含む名前は、読める部分とハッシュで ASCII にする。"""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", video_id).strip("-.")
    if safe == video_id and safe:
        return f"{safe}.mp4"
    digest = hashlib.sha1(video_id.encode("utf-8")).hexdigest()[:8]
    return f"{safe or 'video'}-{digest}.mp4"


def hls_asset_name(video_id):
    """HLS 用（断片化した mp4 を1ファイルにまとめたもの）のリリース添付のファイル名。"""
    return asset_name(video_id)[: -len(".mp4")] + ".hls.mp4"


def rewrite_playlist(text, file_name, url):
    """ffmpeg が書いた HLS の再生リスト内の、動画本体のファイル名を url に置き換える。"""
    out = []
    for line in text.splitlines():
        if line.strip() == file_name:
            line = url
        elif line.startswith("#EXT-X-MAP:"):
            line = line.replace(f'URI="{file_name}"', f'URI="{url}"')
        out.append(line)
    return "\n".join(out) + "\n"


def parse_remote(url):
    """git の remote URL から (owner, repo)。"""
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not m:
        raise ValueError(f"GitHub のリポジトリ URL ではありません: {url}")
    return m.group(1), m.group(2)


def pages_url(owner, repo):
    if repo.lower() == f"{owner}.github.io".lower():
        return f"https://{owner}.github.io/"
    return f"https://{owner}.github.io/{repo}/"


def release_url(owner, repo, tag, asset, version=None):
    url = f"https://github.com/{owner}/{repo}/releases/download/{tag}/{asset}"
    return f"{url}?v={version}" if version else url


def public_asset_url(url):
    """手元のカタログ内のファイル（../runtime/portal/...）を、サイト内の data/... に置き換える。"""
    if url and url.startswith(LOCAL_PREFIX):
        return "data/" + url[len(LOCAL_PREFIX):]
    return url


def aggregate_cast(videos):
    """全動画を通した話者ごとの集計（セリフ数・話した秒数・文字数・出演本数・口ぐせ・立ち絵）。"""
    cast = {}
    for v in videos:
        for key, c in v["cast"].items():
            a = cast.setdefault(key, {"name": c["name"], "color": c["color"], "voice": c.get("voice", ""),
                                      "lines": 0, "seconds": 0.0, "chars": 0, "videos": 0, "_texts": []})
            a["lines"] += c["stats"]["lines"]
            a["seconds"] = round(a["seconds"] + c["stats"]["seconds"], 2)
            a["chars"] += c["stats"]["chars"]
            a["videos"] += 1
            # 立ち絵のない動画が後に来ても、既にある立ち絵を消さない
            a["portrait"] = c.get("portrait") or a.get("portrait")
            a["_texts"] += [ln["text"] for ln in v["lines"] if ln["who"] == key]
    for a in cast.values():
        a["ending"] = top_ending(a.pop("_texts"))
    return cast


def _rewrite_portrait(p):
    return {k: public_asset_url(u) for k, u in p.items()} if isinstance(p, dict) else p


def public_catalog(catalog, published, owner, repo, tag):
    """published（id → {asset, version}）にある動画だけの、公開用カタログ。"""
    videos = [copy.deepcopy(v) for v in catalog["videos"] if v["id"] in published]
    videos.sort(key=lambda v: v.get("date") or "")
    for i, v in enumerate(videos, 1):
        p = published[v["id"]]
        v["no"] = i
        v.pop("published", None)
        v["video"]["src"] = release_url(owner, repo, tag, p["asset"], p.get("version"))
        if p.get("hls"):
            # Safari（iPhone・iPad・Mac）向け。再生リストはサイトに置き、動画本体はリリース添付を範囲指定で読む
            v["video"]["hls"] = f"data/{v['id']}/video.m3u8?v={p['hls']}"
        v["poster"] = public_asset_url(v["poster"])
        v["preview"] = public_asset_url(v["preview"])
        if v.get("sprite"):
            v["sprite"]["src"] = public_asset_url(v["sprite"]["src"])
        for e in v.get("toc", []):
            e["thumb"] = public_asset_url(e.get("thumb"))
        for c in v["cast"].values():
            c["portrait"] = _rewrite_portrait(c.get("portrait"))
    cast = aggregate_cast(videos)
    return {"generated": catalog.get("generated"), "videos": videos, "cast": cast,
            "site": {"url": pages_url(owner, repo), "repo": f"{owner}/{repo}"}}


SITE_TITLE = "Zunda Archive — ずんだもん解説動画アーカイブ"
SITE_DESCRIPTION = "ずんだもんと四国めたんが、なんでも解説するのだ。zundamon-video で作った解説動画のアーカイブ。"


def public_index_html(html, site_url):
    """手元用の index.html を公開用にする（カタログの場所・表示の切り替え、SNS で共有したときのカード）。"""
    html = re.sub(r'<meta name="za-mode" content="[^"]*">', '<meta name="za-mode" content="public">', html)
    html = re.sub(r'<meta name="za-catalog" content="[^"]*">', '<meta name="za-catalog" content="data/catalog.js">', html)
    html = re.sub(r'<meta name="description" content="[^"]*">',
                  f'<meta name="description" content="{SITE_DESCRIPTION}">', html)
    share = "\n".join([
        f'  <link rel="canonical" href="{site_url}">',
        '  <meta property="og:type" content="website">',
        '  <meta property="og:site_name" content="Zunda Archive">',
        f'  <meta property="og:title" content="{SITE_TITLE}">',
        f'  <meta property="og:description" content="{SITE_DESCRIPTION}">',
        f'  <meta property="og:url" content="{site_url}">',
        f'  <meta property="og:image" content="{site_url}og.jpg">',
        '  <meta property="og:image:width" content="1200">',
        '  <meta property="og:image:height" content="630">',
        '  <meta property="og:locale" content="ja_JP">',
        '  <meta name="twitter:card" content="summary_large_image">',
    ])
    return html.replace("</head>", share + "\n</head>", 1)


def uploads_needed(published, local_versions, names):
    """names のうち、まだ上げていないか、書き出し直して中身が変わった動画。"""
    return [n for n in names if published.get(n, {}).get("version") != local_versions[n]]
