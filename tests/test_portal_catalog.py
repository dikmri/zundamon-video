import pytest

from zvideo.portal.catalog import (
    asset_url,
    build_toc,
    make_entry,
    display_title,
    parse_credits,
    parse_data_js,
    parse_sources,
    poster_time,
    preview_times,
    speaker_stats,
    split_title,
    sprite_plan,
    summary_items,
    top_ending,
)


def scene(sid, start, end, **board):
    return {"id": sid, "start": start, "end": end, "board": board}


def test_parse_data_js_reads_the_assigned_object():
    d = parse_data_js('window.ZV = {"total": 12.5, "meta": {"title": "て"}};\n')
    assert d == {"total": 12.5, "meta": {"title": "て"}}


def test_split_title_separates_bracket_kicker():
    assert split_title("【ずんだもん解説】MiniMax H3で動画を作るのだ！") == ("ずんだもん解説", "MiniMax H3で動画を作るのだ！")


def test_split_title_without_kicker_keeps_whole_title():
    assert split_title("テスト") == ("", "テスト")


def test_display_title_keeps_lines_and_accent_spans():
    html = '<span class="accent" style="font-size:88px">MiniMax H3</span><br>で動画を<b>作る</b>のだ！'
    assert display_title(html) == [
        [{"t": "MiniMax H3", "accent": True}],
        [{"t": "で動画を作るのだ！", "accent": False}],
    ]


def test_toc_names_opening_chapters_scenes_and_ending():
    toc = build_toc([
        scene("opening", 0.3, 22.3, layout="title"),
        scene("ch1", 22.3, 26.3, layout="chapter", num="その1", heading="H3ってなに？"),
        scene("what", 26.3, 63.7, title="H3ってなに？"),
        scene("summary", 63.7, 80.0, layout="bullets", title="まとめ"),
        scene("ending", 80.0, 88.0),
    ])
    assert [(e["kind"], e["num"], e["title"], e["start"], e["end"]) for e in toc] == [
        ("opening", None, "オープニング", 0.3, 22.3),
        ("chapter", "その1", "H3ってなに？", 22.3, 26.3),
        ("scene", None, "H3ってなに？", 26.3, 63.7),
        ("scene", None, "まとめ", 63.7, 80.0),
        ("ending", None, "エンディング", 80.0, 88.0),
    ]
    assert [e["chapter"] for e in toc] == [None, 1, 1, 1, 1]


def test_toc_merges_untitled_middle_scene_into_previous_entry():
    toc = build_toc([
        scene("h3prompt", 219.6, 238.1, title="H3 のプロンプト"),
        scene("clip", 238.1, 254.0),
        scene("caution", 254.0, 278.9, title="守ること・コツ"),
    ])
    assert [(e["title"], e["start"], e["end"]) for e in toc] == [
        ("H3 のプロンプト", 219.6, 254.0),
        ("守ること・コツ", 254.0, 278.9),
    ]


def test_toc_treats_credits_layout_as_ending():
    toc = build_toc([scene(None, 0.5, 3.0, layout="title"), scene(None, 3.0, 9.0, layout="credits")])
    assert [e["kind"] for e in toc] == ["opening", "ending"]


def test_summary_items_come_from_bullets_scene():
    items = [{"text": "**なぜ始まった？**", "sub": "47年の対立"}, {"text": "最大2K"}]
    scenes = [scene("a", 0, 1, title="x"), scene("summary", 1, 2, layout="bullets", title="まとめ", items=items)]
    assert summary_items(scenes) == [{"text": "**なぜ始まった？**", "sub": "47年の対立"}, {"text": "最大2K", "sub": ""}]


def test_parse_credits_reads_definition_pairs():
    html = """<div class="ending"><h2>ありがとう</h2>
      <dl class="credits" style="font-size:24px">
        <dt>音声</dt><dd>VOICEVOX:ずんだもん / VOICEVOX:四国めたん</dd>
        <dt>音楽 &amp; 効果音</dt><dd>音楽：<b>魔王魂</b></dd>
      </dl></div>"""
    assert parse_credits(html) == [["音声", "VOICEVOX:ずんだもん / VOICEVOX:四国めたん"], ["音楽 & 効果音", "音楽：魔王魂"]]


def test_parse_sources_reads_list_items_and_notes():
    html = '<ul class="src"><li>国連の声明（2月28日）</li><li>各社報道<small>AP・ロイター</small></li></ul><div class="note">注</div>'
    assert parse_sources(html) == [{"text": "国連の声明（2月28日）", "note": ""}, {"text": "各社報道", "note": "AP・ロイター"}]


def test_top_ending_counts_sentence_endings():
    texts = ["ずんだもんなのだ！今日はこの動画、AIが全部作ったのだ！", "すごいのだ。", "四国めたんよ。"]
    assert top_ending(texts) == ["のだ", 3]


def test_top_ending_of_nothing_is_none():
    assert top_ending([]) is None


def test_speaker_stats_sums_time_and_characters_per_speaker():
    lines = [
        {"who": "zundamon", "text": "なのだ！", "start": 1.0, "end": 2.5},
        {"who": "metan", "text": "そうね。", "start": 3.0, "end": 4.0},
        {"who": "zundamon", "text": "わかったのだ", "start": 5.0, "end": 6.0},
    ]
    st = speaker_stats(lines)
    assert st["zundamon"]["lines"] == 2
    assert st["zundamon"]["seconds"] == pytest.approx(2.5)
    assert st["zundamon"]["chars"] == 10
    assert st["zundamon"]["ending"] == ["のだ", 2]
    assert st["metan"]["lines"] == 1


def test_entry_lines_drop_subtitle_markup_but_keep_emphasis_separately():
    data = {"meta": {"title": "t"}, "total": 5.0, "cast": {},
            "scenes": [scene("opening", 0, 5, layout="title")],
            "lines": [{"who": "z", "text": "今日は**動画生成AI**の\n話なのだ", "start": 0.5, "end": 2.0, "scene": 0},
                      {"who": "z", "text": "ふつうなのだ", "start": 2.5, "end": 3.0, "scene": 0}]}
    urls = {"video": "v", "poster": "p", "preview": "pr", "thumbs": []}
    e = make_entry("x", data, {"duration": 5.0}, urls)
    assert e["lines"][0]["text"] == "今日は動画生成AIの話なのだ"
    assert e["lines"][0]["rich"] == "今日は**動画生成AI**の話なのだ"
    assert "rich" not in e["lines"][1]


def test_poster_time_is_inside_opening_after_title_appears():
    t = poster_time([scene("opening", 0.3, 10.1, layout="title"), scene("x", 10.1, 20.0, title="a")])
    assert 0.3 + 2.0 <= t <= 10.1 - 0.5


def test_poster_time_without_opening_uses_first_scene():
    assert poster_time([scene("x", 0.5, 2.0, title="a")]) == pytest.approx(1.25)


def test_preview_times_spread_over_content_scenes_and_stay_inside_them():
    toc = build_toc([scene("opening", 0, 10, layout="title")]
                    + [scene(f"s{i}", 10 + i * 20, 30 + i * 20, title=f"t{i}") for i in range(8)]
                    + [scene("ending", 170, 178)])
    ts = preview_times(toc, 178, n=5, clip=1.6)
    assert len(ts) == 5
    assert ts == sorted(ts)
    content = [e for e in toc if e["kind"] == "scene"]
    assert any(e["start"] <= ts[0] < e["end"] for e in content[:1])
    assert any(e["start"] <= ts[-1] < e["end"] for e in content[-1:])
    for t in ts:
        e = next(e for e in content if e["start"] <= t < e["end"])
        assert t + 1.6 <= e["end"]


def test_preview_times_without_content_scenes_spread_over_total():
    ts = preview_times([], 20.0, n=4, clip=1.0)
    assert len(ts) == 4 and ts[0] >= 0 and ts[-1] + 1.0 <= 20.0


def test_sprite_plan_limits_frame_count():
    p = sprite_plan(633.7, max_frames=200, cols=10)
    assert p["interval"] == 4
    assert p["count"] == 159
    assert p["rows"] == 16


def test_sprite_plan_short_video_uses_minimum_interval():
    p = sprite_plan(19.0, max_frames=200, cols=10)
    assert (p["interval"], p["count"], p["rows"]) == (2, 10, 1)


def test_asset_url_is_relative_to_the_portal_page(tmp_path):
    web = tmp_path / "portal"
    assert asset_url(tmp_path / "out" / "h3" / "h3.mp4", web, "abc") == "../out/h3/h3.mp4?v=abc"
    assert asset_url(tmp_path / "runtime" / "portal" / "catalog.js", web) == "../runtime/portal/catalog.js"


def test_asset_url_percent_encodes_spaces_and_non_ascii(tmp_path):
    url = asset_url(tmp_path / "out" / "my video" / "動画.mp4", tmp_path / "portal", "1")
    assert url == "../out/my%20video/%E5%8B%95%E7%94%BB.mp4?v=1"


def test_poster_time_can_be_set_explicitly():
    scenes = [scene("opening", 0.3, 10.1, layout="title"), scene("x", 10.1, 80.0, title="a")]
    assert poster_time(scenes, at=56.5) == pytest.approx(56.5)
