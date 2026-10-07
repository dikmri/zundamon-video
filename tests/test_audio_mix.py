import wave

import numpy as np

from zvideo.audio import SR, mix


def _write_tone(path, seconds):
    t = np.arange(int(SR * seconds)) / SR
    pcm = (np.sin(2 * np.pi * 440 * t) * 0.3 * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def _duration(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def test_normalized_mix_keeps_full_length_and_leaves_no_temp_files(tmp_path):
    voice = tmp_path / "v.wav"
    _write_tone(voice, 1.0)
    out = tmp_path / "audio.wav"
    mix(5.0, [(0.5, voice, 1.0), (3.0, voice, 1.0)], [], None, out, loudness=-16.0)
    assert abs(_duration(out) - 5.0) < 0.01
    assert sorted(p.name for p in tmp_path.iterdir()) == ["audio.wav", "v.wav"]


def test_duck_envelope_lowers_inside_intervals_and_ramps_at_edges():
    from zvideo.audio import duck_envelope
    sr = 100
    env = duck_envelope(1000, [(3.0, 6.0)], level=0.25, ramp=0.5, sr=sr)
    assert env[100] == 1.0                 # 区間の前は元の音量
    assert abs(env[450] - 0.25) < 1e-6     # 区間の中は下げた音量
    assert env[900] == 1.0                 # 区間の後は元に戻る
    assert 0.25 < env[300] < 1.0           # 入り口はなめらかに下がる
    assert 0.25 < env[600] < 1.0           # 出口はなめらかに戻る


def test_duck_envelope_without_intervals_is_flat():
    from zvideo.audio import duck_envelope
    assert duck_envelope(50, [], sr=10).min() == 1.0
