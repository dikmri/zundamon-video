"""セリフの長さから、シーン・セリフ・ボード段階表示の時刻を決める。"""
import random
from dataclasses import dataclass


@dataclass
class Timing:
    lead_in: float = 0.5     # 動画冒頭から最初のシーンまで
    scene_lead: float = 0.4  # シーン（ボード）表示から最初のセリフまで
    gap: float = 0.3         # セリフ間の既定の間
    scene_tail: float = 0.6  # 最後のセリフからシーン終わりまで
    outro: float = 2.0       # 最後のシーンから動画終わりまで


def build_timeline(scenes, timing=Timing()):
    """scenes: [{"lines": [{"duration": 秒, "pause"?: 秒, "step"?: int}], "duration"?: 秒}]

    返り値は入力の各要素に start/end（秒）を足したものと、
    シーンごとの steps {段階番号: 表示開始秒}、動画全体の total。
    """
    cursor = timing.lead_in
    placed_scenes = []
    for i, scene in enumerate(scenes):
        lines = scene.get("lines") or []
        start = cursor
        steps = {0: start}
        steps_end = {0: start}  # その段階を最初に出したセリフが終わる時刻（動画をセリフの後に流す用）
        if not lines:
            if scene.get("duration") is None:
                raise ValueError(f"scenes[{i}]: セリフが無いシーンには duration が必要です")
            end = start + scene["duration"]
            placed_scenes.append({**scene, "start": start, "end": end, "lines": [], "steps": steps,
                                  "steps_end": steps_end})
            cursor = end
            continue

        t = start + timing.scene_lead
        placed = []
        for line in lines:
            line_start, line_end = t, t + line["duration"]
            placed.append({**line, "start": line_start, "end": line_end})
            step = line.get("step")
            if step is not None and step not in steps:
                steps[step] = line_start
                steps_end[step] = line_end
            pause = line.get("pause")
            t = line_end + (timing.gap if pause is None else pause)

        last = placed[-1]
        end = last["end"] + max(timing.scene_tail, last.get("pause") or 0.0)
        if scene.get("duration") is not None:
            end = max(end, start + scene["duration"])
        placed_scenes.append({**scene, "start": start, "end": end, "lines": placed, "steps": steps,
                              "steps_end": steps_end})
        cursor = end

    return {"scenes": placed_scenes, "total": cursor + timing.outro}


def blink_times(total, seed, min_gap=2.5, max_gap=5.5):
    """まばたきの開始時刻。キャラクターごとに seed を変えて同時に瞬かないようにする。"""
    rng = random.Random(f"blink:{seed}")
    times, t = [], 0.0
    while True:
        t += rng.uniform(min_gap, max_gap)
        if t >= total:
            return times
        times.append(round(t, 3))
