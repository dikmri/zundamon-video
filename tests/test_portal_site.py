from zvideo.portal.site import (
    aggregate_cast,
    asset_name,
    hls_asset_name,
    pages_url,
    parse_remote,
    public_index_html,
    public_asset_url,
    public_catalog,
    release_url,
    rewrite_playlist,
    uploads_needed,
)


def test_asset_name_keeps_safe_ids():
    assert asset_name("h3") == "h3.mp4"
    assert asset_name("iran_war") == "iran_war.mp4"


def test_asset_name_makes_unsafe_ids_ascii_and_unique():
    a, b = asset_name("動画"), asset_name("別の動画")
    assert a.endswith(".mp4") and a.isascii() and b.isascii() and a != b
    assert asset_name("動画") == a
    assert asset_name("my video").startswith("my-video-")


def test_parse_remote_accepts_https_and_ssh():
    assert parse_remote("https://github.com/dikmri/zunda-archive.git") == ("dikmri", "zunda-archive")
    assert parse_remote("https://github.com/dikmri/zunda-archive") == ("dikmri", "zunda-archive")
    assert parse_remote("git@github.com:dikmri/zunda-archive.git") == ("dikmri", "zunda-archive")


def test_pages_url_for_project_and_user_sites():
    assert pages_url("dikmri", "zunda-archive") == "https://dikmri.github.io/zunda-archive/"
    assert pages_url("dikmri", "dikmri.github.io") == "https://dikmri.github.io/"


def test_release_url_with_version():
    assert release_url("o", "r", "videos", "h3.mp4", "abc") == "https://github.com/o/r/releases/download/videos/h3.mp4?v=abc"


def test_public_asset_url_moves_local_catalog_files_under_data():
    assert public_asset_url("../runtime/portal/h3/poster.jpg?v=1") == "data/h3/poster.jpg?v=1"
    assert public_asset_url("../runtime/portal/cast/metan/idle.webp?v=2") == "data/cast/metan/idle.webp?v=2"
    assert public_asset_url(None) is None


def video(vid, date, who_secs=None):
    return {
        "id": vid, "date": date, "no": 0, "title": vid, "published": True,
        "video": {"src": f"../out/{vid}/{vid}.mp4?v=x", "size": 1},
        "poster": f"../runtime/portal/{vid}/poster.jpg?v=x", "preview": f"../runtime/portal/{vid}/preview.mp4?v=x",
        "sprite": {"src": f"../runtime/portal/{vid}/sprite.jpg?v=x", "interval": 2},
        "toc": [{"title": "a", "thumb": f"../runtime/portal/{vid}/thumbs/00.jpg?v=x"}],
        "lines": [{"who": "z", "text": "なのだ", "start": 0, "end": 1}],
        "cast": {"z": {"name": "ずんだもん", "color": "#2f9a3a", "voice": "V", "portrait": {"idle": "../runtime/portal/cast/z/idle.webp?v=1"},
                       "stats": {"lines": 1, "seconds": who_secs or 1.0, "chars": 3, "ending": ["のだ", 1]}}},
    }


def test_public_catalog_keeps_only_published_videos_and_rewrites_urls():
    cat = {"generated": "g", "videos": [video("b", "2026-10-02"), video("a", "2026-10-01"), video("c", "2026-10-03")], "cast": {}}
    published = {"a": {"asset": "a.mp4", "version": "v1"}, "c": {"asset": "c.mp4", "version": "v3"}}
    pub = public_catalog(cat, published, "o", "r", "videos")
    assert [v["id"] for v in pub["videos"]] == ["a", "c"]
    assert [v["no"] for v in pub["videos"]] == [1, 2]
    a = pub["videos"][0]
    assert a["video"]["src"] == "https://github.com/o/r/releases/download/videos/a.mp4?v=v1"
    assert a["poster"] == "data/a/poster.jpg?v=x"
    assert a["sprite"]["src"] == "data/a/sprite.jpg?v=x"
    assert a["toc"][0]["thumb"] == "data/a/thumbs/00.jpg?v=x"
    assert a["cast"]["z"]["portrait"]["idle"] == "data/cast/z/idle.webp?v=1"
    assert "published" not in a
    assert pub["cast"]["z"]["videos"] == 2
    # 元のカタログは書き換えない
    assert cat["videos"][1]["poster"].startswith("../runtime/portal/")


def test_aggregate_cast_sums_stats_over_videos():
    cast = aggregate_cast([video("a", "1", 2.0), video("b", "2", 3.0)])
    z = cast["z"]
    assert (z["lines"], z["seconds"], z["chars"], z["videos"]) == (2, 5.0, 6, 2)
    assert z["ending"] == ["のだ", 2]


def test_uploads_needed_for_new_and_changed_videos():
    published = {"a": {"version": "1"}, "b": {"version": "2"}}
    local = {"a": "1", "b": "9", "c": "3"}
    assert uploads_needed(published, local, ["a", "b", "c"]) == ["b", "c"]


HTML = """<head>
  <title>Zunda Archive — ずんだもん解説動画アーカイブ</title>
  <meta name="description" content="ずんだもんと四国めたんの解説動画をまとめた個人用アーカイブ。">
  <meta name="za-mode" content="local">
  <meta name="za-catalog" content="../runtime/portal/catalog.js">
</head><body></body>"""


def test_public_index_html_switches_mode_and_catalog():
    out = public_index_html(HTML, "https://o.github.io/r/")
    assert '<meta name="za-mode" content="public">' in out
    assert '<meta name="za-catalog" content="data/catalog.js">' in out
    assert "個人用" not in out


def test_public_index_html_adds_share_card_tags_with_absolute_urls():
    out = public_index_html(HTML, "https://o.github.io/r/")
    assert '<meta property="og:image" content="https://o.github.io/r/og.jpg">' in out
    assert '<meta property="og:url" content="https://o.github.io/r/">' in out
    assert '<meta name="twitter:card" content="summary_large_image">' in out
    assert '<link rel="canonical" href="https://o.github.io/r/">' in out
    assert out.index("og:image") < out.index("</head>")


PLAYLIST = """#EXTM3U
#EXT-X-VERSION:7
#EXT-X-MAP:URI="promo.hls.mp4",BYTERANGE="1846@0"
#EXTINF:8.333333,
#EXT-X-BYTERANGE:2477651@1846
promo.hls.mp4
#EXTINF:8.333333,
#EXT-X-BYTERANGE:2270849@2479497
promo.hls.mp4
#EXT-X-ENDLIST
"""


def test_rewrite_playlist_points_every_reference_to_the_release_url():
    url = "https://github.com/o/r/releases/download/videos/promo.hls.mp4?v=1"
    out = rewrite_playlist(PLAYLIST, "promo.hls.mp4", url)
    assert f'#EXT-X-MAP:URI="{url}",BYTERANGE="1846@0"' in out
    assert out.count(f"\n{url}\n") == 2
    assert "\npromo.hls.mp4\n" not in out
    assert "#EXT-X-BYTERANGE:2270849@2479497" in out


def test_hls_asset_name_follows_the_mp4_name():
    assert hls_asset_name("promo") == "promo.hls.mp4"
    assert hls_asset_name("動画").endswith(".hls.mp4") and hls_asset_name("動画").isascii()


def test_public_catalog_adds_hls_playlist_when_published_with_hls():
    cat = {"generated": "g", "videos": [video("a", "2026-10-01")], "cast": {}}
    published = {"a": {"asset": "a.mp4", "version": "v1", "hls": "v1"}}
    v = public_catalog(cat, published, "o", "r", "videos")["videos"][0]
    assert v["video"]["hls"] == "data/a/video.m3u8?v=v1"
    plain = public_catalog(cat, {"a": {"asset": "a.mp4", "version": "v1"}}, "o", "r", "videos")["videos"][0]
    assert "hls" not in plain["video"]
