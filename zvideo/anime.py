"""H3 の参照モード（ref2va）でアニメのカットを作るための段取り（純粋ロジック）。

1 クリップ = H3 の 1 回の生成（最大 15 秒）。中に複数のショット（カット割り）を持てる。
セリフは VOICEVOX で合成して 1 本の wav に並べ、<Audio 1> として渡す。H3 はその音声に口の動きを合わせる。

    p = plan(clip, [セリフごとの秒数])      # 各セリフ・各ショットの開始と終了、生成の長さ
    text = ref_prompt(clip, p, chars, style)  # H3 のプロンプト（参照モードの 6 節）

ショットや動きの英文では、登場人物を {zunko} のように書く。<Subject N> に置き換わる。
"""
from dataclasses import dataclass, field

from .comfy import h3_frames

H3_FPS = 24
H3_MAX_FRAMES = h3_frames(15.0)  # 362 フレーム（約 15.08 秒）


@dataclass
class Line:
    who: str
    text: str
    act: str = "says"          # 話すときの動きと言い方（英語）。"says" / "replies flatly" など
    gap: float = 0.35          # 直前のセリフ（ショットの最初のセリフならショット頭の pre の後）からの間
    speed: float | None = None
    pitch: float = 0.0
    intonation: float = 1.0
    with_prev: bool = False    # 直前のセリフと同時に話す（「「あっ」」など）


@dataclass
class Shot:
    cam: str                   # 構図とカメラ（英語）
    act: str = ""              # セリフより前に起きること
    lines: list = field(default_factory=list)
    after: str = ""            # セリフの後に起きること
    pre: float = 0.4           # ショット頭から最初のセリフまで
    hold: float = 0.7          # 最後のセリフの後に残す
    dur: float | None = None   # セリフのないショットの長さ。セリフがあるときは最低の長さ
    visible: list | None = None  # このショットに写る人物。None なら全員


@dataclass
class Clip:
    id: str
    shots: list
    cast: list = field(default_factory=list)   # 登場人物（<Subject N> の順）
    key_desc: str = ""         # 最初のコマ（<Picture 1>）に写っているもの（英語）
    summary: str = ""          # 何が起きるかの要約（英語）
    sound: str = ""            # 環境音・効果音（英語）
    refs: dict = field(default_factory=dict)   # {人物: 追加の参照画像の説明}。cast の順に <Picture 2> 以降になる
    in_key: list | None = None  # 最初のコマに写っている人物。None なら cast 全員
    key: dict | None = None    # 最初のコマの画像生成の指定（WAI-Anima など。このモジュールは使わない）
    extra: dict = field(default_factory=dict)  # 呼び出し側が自由に使う


def plan(clip, durations):
    """セリフの長さ（秒、登場順）から、各セリフ・各ショットの時刻と生成の長さを決める。"""
    lines, shots = [], []
    t, k = 0.0, 0
    for shot in clip.shots:
        start = t
        t += shot.pre if shot.lines else 0.0
        prev = None
        for i, line in enumerate(shot.lines):
            if k >= len(durations):
                raise ValueError(f"{clip.id}: セリフの長さが足りない（{k + 1} 本目）")
            d = float(durations[k])
            if line.with_prev and prev is not None:
                s = prev["start"]
            else:
                s = t if i == 0 else t + line.gap
            item = {"shot": len(shots), "who": line.who, "text": line.text, "start": round(s, 3),
                    "end": round(s + d, 3)}
            lines.append(item)
            t = max(t, item["end"])
            prev, k = item, k + 1
        if shot.lines:
            t += shot.hold
        if shot.dur is not None:
            t = max(t, start + shot.dur)
        shots.append({"start": round(start, 3), "end": round(t, 3)})
    if k != len(durations):
        raise ValueError(f"{clip.id}: セリフは {k} 本なのに長さが {len(durations)} 個ある")
    frames = h3_frames(t)
    if frames > H3_MAX_FRAMES:
        raise ValueError(f"{clip.id}: {t:.2f} 秒は H3 の 1 回の生成（15 秒）に収まらない")
    seconds = frames / H3_FPS
    shots[-1]["end"] = seconds
    return {"frames": frames, "seconds": seconds, "shots": shots, "lines": lines}


def _ts(sec):
    m, s = divmod(sec, 60)
    return f"{int(m):02d}:{s:06.3f}"


def _labels(clip, lines):
    subject = {who: f"<Subject {i + 1}>" for i, who in enumerate(clip.cast)}
    speaker = {}
    for ln in lines:
        speaker.setdefault(ln["who"], f"(S{len(speaker) + 1})")
    return subject, speaker


def ref_prompt(clip, p, chars, style, audio="copy"):
    """参照モード（ref2va）の 6 節のプロンプトを作る。

    audio="copy" はセリフの wav（<Audio 1>）をそのまま最終音声にする前提で書く。
    "copy+sfx" はセリフを写したうえで、sound に書いた効果音を足させる。
    """
    subject, speaker = _labels(clip, p["lines"])
    fmt = {who: subject[who] for who in clip.cast}
    has_audio = bool(p["lines"])
    refs = [who for who in clip.cast if who in clip.refs]
    pic = {who: f"<Picture {i + 2}>" for i, who in enumerate(refs)}

    defs = [f"<Picture 1> is the first frame of [Shot 1], showing {clip.key_desc}."]
    in_key = clip.cast if clip.in_key is None else clip.in_key
    for who in clip.cast:
        if who not in in_key:
            if who not in pic:
                raise ValueError(f"{clip.id}: {who} は最初のコマにいないので refs に参照画像が要る")
            defs.append(f"{subject[who]} is {chars[who]}, whose appearance comes from {pic[who]} ({clip.refs[who]}).")
            continue
        extra = f", whose close-up appearance also comes from {pic[who]} ({clip.refs[who]})" if who in pic else ""
        defs.append(f"{subject[who]} is {chars[who]} in <Picture 1>{extra}.")
    if has_audio:
        talkers = [w for w in speaker]
        names = " and ".join(f"{subject[w]} {speaker[w]}" for w in talkers)
        defs.append(f"<Audio 1> is the complete dialogue track spoken by {names}.")

    kinds = ["keyframe completion"] + (["audio reuse"] if has_audio else [])
    summary = f"[{' + '.join(kinds)}] The target video starts from <Picture 1>. {clip.summary.format(**fmt)}"
    if has_audio:
        summary += (" <Audio 1> is reused unchanged as the complete dialogue, and each character's lips move only"
                    " while her own line in <Audio 1> is heard; everyone else keeps her mouth closed.")

    keep = ["<Picture 1> ([Shot 1] first frame): fully_preserved - the opening composition, setting and character"
            " positions are kept."]
    for who in clip.cast:
        shots = ", ".join(f"[Shot {i + 1}]" for i, sh in enumerate(clip.shots)
                          if sh.visible is None or who in sh.visible)
        keep.append(f"{subject[who]} (appears in {shots}): fully_preserved - her face, hair and outfit are retained.")
    if has_audio:
        if audio == "copy+sfx":
            keep.append("<Audio 1>: partially_copy - every spoken line of <Audio 1> is copied unchanged at its"
                        " original timing, and the sound effects described below are added around it.")
        else:
            keep.append("<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final audio"
                        " track.")

    body = [style]
    for i, (shot, span) in enumerate(zip(clip.shots, p["shots"])):
        cam = shot.cam.format(**fmt)
        head = (f"[Shot 1] The shot begins from <Picture 1>, {cam}." if i == 0
                else f"[Shot {i + 1}] At {_ts(span['start'])}, the shot cuts to {cam}.")
        parts = [head]
        if shot.act:
            parts.append(shot.act.format(**fmt))
        for line in shot.lines:
            parts.append(f"{subject[line.who]} {speaker[line.who]} {line.act.format(**fmt)}, "
                         f"<d>[Japanese] {line.text}</d>")
        if shot.after:
            parts.append(shot.after.format(**fmt))
        body.append(" ".join(parts))

    sound = clip.sound.format(**fmt) if clip.sound else "Quiet room tone."
    return "\n\n".join([
        "subject_definitions:\n" + "\n".join(defs),
        "summary:\n" + summary,
        "retention_analysis:\n" + "\n".join(keep),
        "detailed_description:\n" + "\n".join(body),
        "overall_soundscape:\n" + sound,
        "non_diegetic_music:\nN/A",
    ])
