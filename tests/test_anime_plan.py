import pytest

from zvideo.anime import Clip, Line, Shot, plan, ref_prompt

CHARS = {"zunko": "the older sister with long dark green hair",
         "kiri": "the small younger sister with brown twin tails"}


def test_plan_places_lines_with_gaps_and_holds_and_snaps_to_h3_length():
    c = Clip("c1", cast=["zunko", "kiri"], shots=[
        Shot("medium shot", lines=[Line("zunko", "a"), Line("kiri", "b", gap=0.5)], pre=0.4, hold=0.7)])
    p = plan(c, [2.0, 1.0])
    assert [(x["start"], x["end"]) for x in p["lines"]] == [(0.4, 2.4), (2.9, 3.9)]
    # 0.4 + 2.0 + 0.5 + 1.0 + 0.7 = 4.6 秒 → 17k+5 フレームへ切り上げ（124 フレーム）
    assert p["frames"] == 124
    assert p["seconds"] == pytest.approx(124 / 24)
    assert p["shots"][0]["start"] == 0 and p["shots"][0]["end"] == pytest.approx(124 / 24)


def test_plan_starts_each_shot_where_the_previous_one_ended():
    c = Clip("c1", cast=["zunko", "kiri"], shots=[
        Shot("wide", lines=[Line("zunko", "a")], pre=0.3, hold=0.5),
        Shot("close-up", lines=[Line("kiri", "b")], pre=0.2, hold=1.0)])
    p = plan(c, [1.0, 1.0])
    assert p["shots"][1]["start"] == pytest.approx(1.8)
    assert p["lines"][1]["start"] == pytest.approx(2.0)


def test_plan_silent_shot_uses_its_duration_and_dur_is_a_minimum_for_talking_shots():
    c = Clip("c1", cast=["kiri"], shots=[Shot("insert", dur=2.0),
                                          Shot("close-up", lines=[Line("kiri", "b")], pre=0.2, hold=0.3, dur=3.0)])
    p = plan(c, [1.0])
    assert p["shots"][1]["start"] == pytest.approx(2.0)
    assert p["lines"][0]["start"] == pytest.approx(2.2)
    assert p["shots"][1]["end"] >= 5.0


def test_plan_with_prev_speaks_at_the_same_time_as_the_previous_line():
    c = Clip("c1", cast=["zunko", "kiri"], shots=[
        Shot("two shot", lines=[Line("zunko", "あっ"), Line("kiri", "あっ", with_prev=True)], pre=0.5, hold=0.5)])
    p = plan(c, [0.4, 0.5])
    assert p["lines"][1]["start"] == p["lines"][0]["start"]
    assert p["lines"][1]["end"] == pytest.approx(1.0)


def test_plan_rejects_clips_longer_than_h3_can_make():
    c = Clip("c1", cast=["zunko"], shots=[Shot("x", lines=[Line("zunko", "a")])])
    with pytest.raises(ValueError):
        plan(c, [15.0])


def test_ref_prompt_labels_subjects_speakers_and_timed_shots():
    c = Clip("c1", cast=["zunko", "kiri"], key_desc="two sisters at a kotatsu", summary="A scolding.",
             sound="Room tone.", shots=[
                 Shot("a static medium shot", act="{zunko} wags her finger.",
                      lines=[Line("zunko", "おきなさい。", act="says sternly")]),
                 Shot("a close-up of {kiri}", lines=[Line("kiri", "いやです。", act="replies flatly")],
                      after="{zunko} sighs.")])
    p = plan(c, [1.0, 1.0])
    text = ref_prompt(c, p, CHARS, style="The target video is a 2D anime.")
    assert "<Subject 1> is the older sister with long dark green hair" in text
    assert "<Subject 2> is the small younger sister with brown twin tails" in text
    assert "<Audio 1> is the complete dialogue track spoken by <Subject 1> (S1) and <Subject 2> (S2)." in text
    assert "<Subject 1> wags her finger." in text
    assert "<Subject 1> (S1) says sternly, <d>[Japanese] おきなさい。</d>" in text
    start2 = p["shots"][1]["start"]
    assert f"[Shot 2] At 00:{start2:06.3f}, the shot cuts to a close-up of <Subject 2>." in text
    assert "<Subject 2> (S2) replies flatly, <d>[Japanese] いやです。</d> <Subject 1> sighs." in text
    for section in ("subject_definitions:", "summary:", "retention_analysis:", "detailed_description:",
                    "overall_soundscape:", "non_diegetic_music:"):
        assert section in text
    assert text.index("subject_definitions:") < text.index("summary:") < text.index("detailed_description:")


def test_ref_prompt_without_lines_has_no_audio_reference():
    c = Clip("c1", cast=[], key_desc="a snowy house", summary="Snow falls.", shots=[Shot("a wide shot", dur=4.0)])
    text = ref_prompt(c, plan(c, []), CHARS, style="Anime.")
    assert "<Audio 1>" not in text and "(S1)" not in text
    assert "[reference generation" not in text and "[keyframe completion]" in text


def test_ref_prompt_lists_only_the_shots_a_character_is_visible_in():
    c = Clip("c1", cast=["zunko", "kiri"], key_desc="x", shots=[
        Shot("wide", dur=2.0), Shot("close-up of {kiri}", dur=2.0, visible=["kiri"])])
    text = ref_prompt(c, plan(c, []), CHARS, style="Anime.")
    assert "<Subject 1> (appears in [Shot 1]):" in text
    assert "<Subject 2> (appears in [Shot 1], [Shot 2]):" in text


def test_ref_prompt_takes_characters_missing_from_the_first_frame_from_reference_pictures():
    c = Clip("c1", cast=["kiri", "zunko"], in_key=["kiri"], refs={"zunko": "a portrait"}, key_desc="x",
             shots=[Shot("close-up of {kiri}", dur=2.0, visible=["kiri"]),
                    Shot("close-up of {zunko}", dur=2.0, visible=["zunko"])])
    text = ref_prompt(c, plan(c, []), CHARS, style="Anime.")
    assert "<Subject 1> is the small younger sister with brown twin tails in <Picture 1>." in text
    assert ("<Subject 2> is the older sister with long dark green hair, whose appearance comes from <Picture 2>"
            " (a portrait).") in text


def test_ref_prompt_rejects_a_character_with_no_picture():
    c = Clip("c1", cast=["kiri", "zunko"], in_key=["kiri"], key_desc="x", shots=[Shot("x", dur=2.0)])
    with pytest.raises(ValueError):
        ref_prompt(c, plan(c, []), CHARS, style="Anime.")


def test_ref_prompt_states_that_nobody_appears_when_the_cast_is_empty():
    c = Clip("c1", cast=[], key_desc="a window", summary="Snow falls.", shots=[Shot("a static shot", dur=3.0)])
    text = ref_prompt(c, plan(c, []), CHARS, style="Anime.")
    assert "No people appear anywhere in the target video" in text


def test_ref_prompt_does_not_add_the_empty_room_note_when_someone_appears():
    c = Clip("c1", cast=["kiri"], key_desc="x", shots=[Shot("a shot", dur=2.0)])
    assert "No people appear" not in ref_prompt(c, plan(c, []), CHARS, style="Anime.")


def test_ref_prompt_states_the_setting_for_every_shot():
    c = Clip("c1", cast=["kiri"], key_desc="x", setting="at night on a moonlit veranda",
             shots=[Shot("a wide shot", dur=2.0), Shot("a close-up of {kiri}", dur=2.0)])
    text = ref_prompt(c, plan(c, []), CHARS, style="Anime.")
    assert "takes place at night on a moonlit veranda" in text
    assert text.index("takes place") < text.index("[Shot 1] The shot begins")


def test_plan_gives_inner_voice_lines_time_and_marks_them():
    c = Clip("c1", cast=["kiri"], shots=[
        Shot("close-up", lines=[Line("kiri", "（ねむい）", vo=True), Line("kiri", "おはよう。")], pre=0.5, hold=0.5)])
    p = plan(c, [2.0, 1.0])
    assert [(x["start"], x["end"], x["vo"]) for x in p["lines"]] == [(0.5, 2.5, True), (2.85, 3.85, False)]


def test_ref_prompt_keeps_inner_voice_out_of_the_dialogue_track_and_the_mouth_closed():
    c = Clip("c1", cast=["zunko", "kiri"], key_desc="two sisters", summary="Morning.", shots=[
        Shot("a close-up of {kiri}", lines=[
            Line("kiri", "（ねむい……）", act="rubs her eyes and yawns silently", vo=True),
            Line("zunko", "おきなさい。", act="says sternly")])])
    text = ref_prompt(c, plan(c, [2.0, 1.0]), CHARS, style="2D anime.")
    assert "ねむい" not in text                       # 心の声は H3 に読ませない（声を作らせない）
    assert "<Subject 2> rubs her eyes and yawns silently with her mouth closed" in text
    assert "<Subject 1> (S1) says sternly, <d>[Japanese] おきなさい。</d>" in text
    assert "(S2)" not in text                         # 話者は声のある人だけ


def test_ref_prompt_without_spoken_lines_has_no_audio_even_with_inner_voice():
    c = Clip("c1", cast=["kiri"], key_desc="a girl", summary="Thinking.", shots=[
        Shot("a close-up", lines=[Line("kiri", "（どうしよう）", act="stares at her phone", vo=True)])])
    text = ref_prompt(c, plan(c, [2.0]), CHARS, style="2D anime.")
    assert "<Audio 1>" not in text
