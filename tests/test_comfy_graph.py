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
