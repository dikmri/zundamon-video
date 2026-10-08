import pytest

from zvideo.comfy import anima_graph, compose_prompt


def test_prompt_puts_quality_and_rating_before_character_and_tags():
    p = compose_prompt(["tohoku kiritan"], ["smile", "holding food"], series=["voiceroid"])
    assert p == "masterpiece, best quality, score_7, safe, tohoku kiritan, voiceroid, smile, holding food"


def test_prompt_rejects_non_safe_rating():
    with pytest.raises(ValueError):
        compose_prompt(["x"], ["y"], rating="nsfw")


def test_graph_wires_anima_loaders_and_sampler():
    g = anima_graph("pos", "neg", unet="waiANIMA_v10Base10.safetensors",
                    text_encoder="waiANIMA_v10Base10_txt.safetensors", vae="qwen_image_vae.safetensors",
                    width=1344, height=768, seed=7, steps=28, cfg=4.5, prefix="zv/key")
    by_type = {n["class_type"]: n for n in g.values()}
    assert by_type["UNETLoader"]["inputs"]["unet_name"] == "waiANIMA_v10Base10.safetensors"
    assert by_type["CLIPLoader"]["inputs"] == {"clip_name": "waiANIMA_v10Base10_txt.safetensors",
                                              "type": "stable_diffusion", "device": "default"}
    ks = by_type["KSampler"]["inputs"]
    assert (ks["seed"], ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"]) == \
        (7, 28, 4.5, "euler_ancestral", "normal")
    assert by_type["EmptyLatentImage"]["inputs"]["width"] == 1344
    assert by_type["SaveImage"]["inputs"]["filename_prefix"] == "zv/key"


def test_negative_prompt_always_blocks_adult_ratings():
    g = anima_graph("pos", "lowres", unet="u", text_encoder="t", vae="v", width=1024, height=1024, seed=1)
    texts = [n["inputs"]["text"] for n in g.values() if n["class_type"] == "CLIPTextEncode"]
    neg = [t for t in texts if t != "pos"][0]
    for word in ("nsfw", "explicit", "sensitive"):
        assert word in neg


def test_h3_frames_snap_to_17k_plus_5_grid():
    from zvideo.comfy import h3_frames
    assert h3_frames(5.0) == 124      # 120 フレーム → 17*7+5
    assert h3_frames(2.0) == 56       # 48 → 17*3+5
    assert h3_frames(0.0) == 5


def test_h3_canvas_is_multiple_of_32_and_close_to_megapixels():
    from zvideo.comfy import h3_canvas
    assert h3_canvas("16:9", 0.4) == (832, 480)
    w, h = h3_canvas("9:16", 0.4)
    assert (w % 32, h % 32) == (0, 0) and h > w


def test_h3_graph_uses_first_frame_turbo_lora_and_saves_video_with_audio():
    from zvideo.comfy import h3_graph
    g = h3_graph("prompt text", first_frame="zvideo/key.png", seconds=5.0, seed=3,
                 unet="u.safetensors", text_encoder="t.safetensors", video_vae="vv.safetensors",
                 audio_vae="av.safetensors", lora="l.safetensors", lora_strength=0.6, steps=10)
    types = {n["class_type"] for n in g.values()}
    assert {"MiniMaxH3ImageToVideo", "LoraLoaderModelOnly", "VAEDecodeAudio", "CreateVideo", "SaveVideo"} <= types
    cond = next(n for n in g.values() if n["class_type"] == "MiniMaxH3ImageToVideo")["inputs"]
    assert (cond["width"], cond["height"], cond["length"]) == (832, 480, 124)
    assert g[cond["first_frame"][0]]["inputs"]["image"] == "zvideo/key.png"
    clip = next(n for n in g.values() if n["class_type"] == "CLIPLoader")["inputs"]
    assert clip["type"] == "minimax"
    sampler = next(n for n in g.values() if n["class_type"] == "KSamplerSelect")["inputs"]
    assert sampler["sampler_name"] == "er_sde"


def test_h3_graph_can_switch_to_turbo_sampler_node():
    from zvideo.comfy import h3_graph
    g = h3_graph("p", first_frame=None, seconds=2, seed=1, unet="u", text_encoder="t", video_vae="v",
                 audio_vae="a", lora=None, turbo_sampler=True)
    types = {n["class_type"] for n in g.values()}
    assert "MiniMaxH3TurboSampler" in types and "KSamplerSelect" not in types
    assert "LoraLoaderModelOnly" not in types and "LoadImage" not in types


def _ref(**kw):
    from zvideo.comfy import h3_ref_graph
    args = dict(prompt="p", ref_images=["zvideo/key.png", "zvideo/kiri.png"], ref_audio="zvideo/line.wav",
                seconds=5.0, seed=1, unet="r", text_encoder="t", video_vae="v", audio_vae="a")
    args.update(kw)
    return h3_ref_graph(**args)


def _one(g, class_type):
    return next(n for n in g.values() if n["class_type"] == class_type)["inputs"]


def test_h3_ref_graph_feeds_images_and_audio_trimmed_to_clip_length():
    g = _ref()
    cond = _one(g, "MiniMaxH3ReferenceToVideo")
    assert (cond["width"], cond["height"], cond["length"]) == (832, 480, 124)
    assert g[cond["ref_images.ref_image_0"][0]]["inputs"]["image"] == "zvideo/key.png"
    assert g[cond["ref_images.ref_image_1"][0]]["inputs"]["image"] == "zvideo/kiri.png"
    trim = g[cond["ref_audios.ref_audio_0"][0]]
    assert trim["class_type"] == "TrimAudioDuration"
    assert trim["inputs"]["duration"] == pytest.approx(124 / 24)
    assert g[trim["inputs"]["audio"][0]]["inputs"]["audio"] == "zvideo/line.wav"


def test_h3_ref_graph_reference_audio_goes_straight_to_the_video():
    g = _ref(audio_source="reference")
    cond = _one(g, "MiniMaxH3ReferenceToVideo")
    assert _one(g, "CreateVideo")["audio"] == cond["ref_audios.ref_audio_0"]
    assert "VAEDecodeAudio" not in {n["class_type"] for n in g.values()}


def test_h3_ref_graph_generated_audio_is_decoded():
    g = _ref(audio_source="generated")
    audio = _one(g, "CreateVideo")["audio"]
    assert g[audio[0]]["class_type"] == "VAEDecodeAudio"


def test_h3_ref_graph_without_audio_has_no_audio_reference():
    g = _ref(ref_audio=None)
    cond = _one(g, "MiniMaxH3ReferenceToVideo")
    assert not [k for k in cond if k.startswith("ref_audios.")]
    assert "LoadAudio" not in {n["class_type"] for n in g.values()}


def test_h3_ref_graph_rejects_bad_requests():
    with pytest.raises(ValueError):
        _ref(ref_images=[], ref_audio=None)                      # 参照が1つもない
    with pytest.raises(ValueError):
        _ref(ref_audio=None, audio_source="reference")           # 載せる音がない
    with pytest.raises(ValueError):
        _ref(ref_images=[f"i{i}.png" for i in range(10)])        # 画像は9枚まで


def test_music3_graph_makes_an_instrumental_track_with_the_model_deciding_the_length():
    from zvideo.comfy import music3_graph
    g = music3_graph("Global Metadata: warm lo-fi piano.", seconds=95.0, seed=7)
    enc = _one(g, "MiniMaxMusic3TextEncode")
    assert enc["caption"] == "Global Metadata: warm lo-fi piano."
    assert enc["lyrics"] == "[Intro]\n[Instrumental]\n[Outro]"
    assert (enc["max_duration"], enc["seed"]) == (95.0, 7)
    # 曲の長さは文章エンコードが決める（max_duration は上限）。その値で空の潜在を作る
    assert _one(g, "EmptyMiniMaxMusic3LatentAudio")["seconds"][1] == 1
    sampler = _one(g, "KSampler")
    assert (sampler["seed"], sampler["steps"], sampler["cfg"]) == (7, 30, 1.7)
    assert g[sampler["negative"][0]]["class_type"] == "ConditioningZeroOut"
    assert _one(g, "CLIPLoader")["type"] == "minimax"
    assert _one(g, "UNETLoader")["unet_name"] == "minimax_music3_dit_int8_convrot.safetensors"
    assert "SaveAudio" in {n["class_type"] for n in g.values()}


def test_music3_graph_can_decode_in_tiles_to_save_vram():
    from zvideo.comfy import music3_graph
    g = music3_graph("x", seconds=30, seed=1, tiled=True)
    types = {n["class_type"] for n in g.values()}
    assert "VAEDecodeAudioTiled" in types and "VAEDecodeAudio" not in types

