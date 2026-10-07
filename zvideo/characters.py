"""立ち絵素材を HTML で重ねられるパーツ PNG と char.json に書き出す。

重ね順は base → poses（腕など）→ faces（表情）→ top（前髪など）。
faces は「表情名 → 重ね順どおりのスロット列」。
スロットは static（常に表示）/ eyes（open/smile/closed）/ mouth（n/a/i/u/e/o）のいずれか。
各パーツは {src, x, y, w, h}（キャンバス座標）で、乗算レイヤーは blend: "multiply" を持つ。
"""
import json
import math
import re
import shutil

from PIL import Image, ImageDraw, ImageFilter

from .paths import CHARACTERS, SOZAI_SRC

# ---- 共通 -----------------------------------------------------------------


def _resize(img, scale):
    """透過の縁が黒ずまないよう、乗算済みアルファで縮小する。"""
    w, h = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    return img.convert("RGBa").resize((w, h), Image.LANCZOS).convert("RGBA")


class _Exporter:
    """元画像座標の (x, y) にある画像を、原点 origin・倍率 scale で書き出す。

    scale = 1/denom のとき、切り出し位置を denom の倍数に揃えて縮小後の座標を整数にする。
    """

    def __init__(self, out_dir, origin, scale, denom):
        self.out_dir, self.origin, self.scale, self.denom = out_dir, origin, scale, denom
        if out_dir.exists():
            shutil.rmtree(out_dir)  # 前回の書き出しの残骸を残さない
        out_dir.mkdir(parents=True)

    def save(self, img, x, y, name):
        d = self.denom
        rx, ry = x - self.origin[0], y - self.origin[1]
        pl, pt = rx % d, ry % d
        w = math.ceil((img.width + pl) / d) * d
        h = math.ceil((img.height + pt) / d) * d
        padded = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        padded.paste(img, (pl, pt))
        small = _resize(padded, self.scale)
        small.save(self.out_dir / name)
        return {"src": name, "x": round((rx - pl) * self.scale), "y": round((ry - pt) * self.scale),
                "w": small.width, "h": small.height}


def _write_char(name, info):
    path = CHARACTERS / name / "char.json"
    path.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return info


# ---- ずんだもん公式版（公式 PSD zunmon008.psd → zundamon_official） -------------

ZUNDAMON_FACES = {
    "ノーマル": "normal", "煽り": "smug", "実況": "excited", "つんつん": "angry",
    "あまあま": "happy", "ささやき": "whisper", "セクシー": "sexy",
    "顔涙目 のコピー": "cry", "顔へろへろ のコピー": "tired", "顔ひそひそ のコピー": "hush",
}
MOUTH_PREFIX = [("あ", "a"), ("い", "i"), ("う", "u"), ("え", "e"), ("お", "o"), ("ん", "n"), ("とじ", "n")]


def _dec(s):
    """psd-tools が Mac Roman として読んだ Shift_JIS のレイヤー名を戻す。"""
    for enc in ("macroman", "latin-1", "cp1252"):
        try:
            return s.encode(enc).decode("cp932")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return s


def _eye_kind(name):
    if name.startswith("開"):
        return "open"
    m = re.match(r"^(?:閉じ|とじ)?([12])", name)
    if m:
        # 閉じ1 は笑い目（^ ^）、閉じ2 が普通の閉じ目
        return "smile" if m.group(1) == "1" else "closed"
    return None


def _layer_image(layer):
    img = layer.composite(layer_filter=lambda _l: True)
    if img is None:
        return None
    return img.convert("RGBA")


def prepare_zundamon_official(scale=0.2):
    from psd_tools import PSDImage

    psd = PSDImage.open(SOZAI_SRC / "zunmon008.psd")
    base = psd[0]
    x0, y0, x1, y1 = base.bbox
    out = CHARACTERS / "zundamon_official"
    ex = _Exporter(out / "parts", (x0, y0), scale, round(1 / scale))

    def save(layer, fname):
        img = _layer_image(layer)
        if img is None:
            return None
        part = ex.save(img, layer.offset[0], layer.offset[1], fname)
        part["src"] = "parts/" + part["src"]
        return part

    faces = {}
    for group in psd:
        if not group.is_group():
            continue
        face = ZUNDAMON_FACES.get(_dec(group.name))
        if face is None:
            continue
        slots, eyes_slot = [], None
        for i, layer in enumerate(group):
            lname = _dec(layer.name)
            if layer.is_group():
                parts = {}
                for m in layer:
                    shape = next((s for p, s in MOUTH_PREFIX if _dec(m.name).startswith(p)), None)
                    if shape and shape not in parts:
                        parts[shape] = save(m, f"{face}_mouth_{shape}.png")
                slots.append({"type": "mouth", "parts": parts})
                continue
            kind = _eye_kind(lname)
            if kind:
                if eyes_slot is None:
                    eyes_slot = {"type": "eyes", "parts": {}}
                    slots.append(eyes_slot)
                eyes_slot["parts"][kind] = save(layer, f"{face}_eye_{kind}.png")
            else:
                part = save(layer, f"{face}_static{i}.png")
                if part:
                    slots.append({"type": "static", "part": part})
        faces[face] = slots

    base_part = save(base, "base.png")
    info = {
        "name": "ずんだもん",
        "color": "#2f9a3a",
        "size": [round((x1 - x0) * scale), round((y1 - y0) * scale)],
        "base": base_part,
        "faces": faces,
        "default_face": "normal",
        "voice": {"speaker": 3, "speed": 1.15, "pitch": 0.0, "intonation": 1.15,
                  "styles": {"normal": 3, "happy": 1, "angry": 7, "sexy": 5, "whisper": 22,
                             "hush": 38, "tired": 75, "cry": 76}},
        "credit": "立ち絵：東北ずん子・ずんだもんプロジェクト公式素材",
        "voice_credit": "VOICEVOX:ずんだもん",
    }
    return _write_char("zundamon_official", info)


# ---- 四国めたん公式版（公式 PNG met004.png + 描いた口パーツ → metan_official） ---

METAN_MOUTH_CENTER = (1752, 1676)   # 元画像での口（上唇線）の中心
# 口形ごとの開き（元画像 px）: 幅, 高さ
METAN_MOUTHS = {"a": (58, 42), "i": (62, 16), "u": (28, 26), "e": (56, 26), "o": (36, 40)}


def _metan_mouth(src, shape, ss=4):
    """口元パッチ（肌色で元の口を覆い、その上に開いた口を描く）を元画像の座標系で返す。"""
    cx, top = METAN_MOUTH_CENTER
    pw, ph = 140, 90
    px, py = cx - pw // 2, top - 26
    skin = src.crop((cx - 6, top + 40, cx + 6, top + 52)).convert("RGB").resize((1, 1), Image.BOX).getpixel((0, 0))

    # 透明部分も肌色にしておく（黒と混ざって縁が灰色になるのを防ぐ）
    big = Image.new("RGBA", (pw * ss, ph * ss), skin + (0,))
    # 元の閉じ口を覆う肌色パッチ（ぼかして周囲と馴染ませる）
    cover = Image.new("L", big.size, 0)
    ImageDraw.Draw(cover).ellipse([(cx - 48 - px) * ss, (top - 14 - py) * ss,
                                   (cx + 48 - px) * ss, (top + 26 - py) * ss], fill=255)
    cover = cover.filter(ImageFilter.GaussianBlur(7 * ss))
    big.paste(Image.new("RGBA", big.size, skin + (255,)), (0, 0), cover)

    w, h = METAN_MOUTHS[shape]
    box = [(cx - w / 2 - px) * ss, (top - 2 - py) * ss, (cx + w / 2 - px) * ss, (top - 2 + h - py) * ss]
    mask = Image.new("L", big.size, 0)
    ImageDraw.Draw(mask).ellipse(box, fill=255)
    inner = Image.new("RGBA", big.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(inner)
    d.rectangle([0, 0, big.width, big.height], fill=(112, 38, 52, 255))
    # 舌
    tw, th = (box[2] - box[0]) * 0.62, (box[3] - box[1]) * 0.5
    tcx = (box[0] + box[2]) / 2
    d.ellipse([tcx - tw / 2, box[3] - th * 0.9, tcx + tw / 2, box[3] + th * 0.6], fill=(222, 112, 128, 255))
    big.paste(inner, (0, 0), mask)
    # 輪郭線
    ImageDraw.Draw(big).ellipse(box, outline=(84, 26, 38, 230), width=int(2.5 * ss))
    patch = _resize(big, 1 / ss)
    return patch, px, py


def prepare_metan_official(scale=0.3):
    src = Image.open(SOZAI_SRC / "met004.png").convert("RGBA")
    x0, y0, x1, y1 = src.getbbox()
    out = CHARACTERS / "metan_official"
    ex = _Exporter(out / "parts", (x0, y0), scale, 10)  # 0.3 = 3/10
    base = ex.save(src.crop((x0, y0, x1, y1)), x0, y0, "base.png")
    base["src"] = "parts/base.png"
    mouth = {"n": None}
    for shape in METAN_MOUTHS:
        patch, px, py = _metan_mouth(src, shape)
        part = ex.save(patch, px, py, f"mouth_{shape}.png")
        part["src"] = "parts/" + part["src"]
        mouth[shape] = part
    info = {
        "name": "四国めたん",
        "color": "#d43a86",
        "size": [round((x1 - x0) * scale), round((y1 - y0) * scale)],
        "base": base,
        "faces": {"normal": [{"type": "mouth", "parts": mouth}]},
        "default_face": "normal",
        "voice": {"speaker": 2, "speed": 1.1, "pitch": 0.0, "intonation": 1.1,
                  "styles": {"normal": 2, "happy": 0, "angry": 6, "sexy": 4, "whisper": 36, "hush": 37}},
        "credit": "立ち絵：東北ずん子・ずんだもんプロジェクト公式素材",
        "voice_credit": "VOICEVOX:四国めたん",
    }
    return _write_char("metan_official", info)


# ---- PSDTool 形式の立ち絵（坂本アヒル氏の立ち絵素材など） ----------------------
#
# PSDTool の慣習: 名前が * の層は同じフォルダ内で1つだけ選ぶ候補、! の層は常に表示。
# 下の SPEC で「どのレイヤーをどの役割（土台・腕ポーズ・表情の各スロット・前髪）に使うか」を
# レイヤーのパス（例 "!口/*むふ"）で指定する。パスのリストは先頭を下にして1枚に重ねる。

AHIRU = SOZAI_SRC / "ahiru"
AHIRU_ZIPS = {
    "zundamon": {"zip": AHIRU / "zundamon_v3.2.zip", "url": "https://uu.getuploader.com/s_ahiru/download/59",
                 "page": "https://seiga.nicovideo.jp/seiga/im11206626", "md5": "cb6f503f901043b1c6edc4de274587c3"},
    "metan": {"zip": AHIRU / "metan_2.1.zip", "url": "https://uu.getuploader.com/s_ahiru/download/35",
              "page": "https://seiga.nicovideo.jp/seiga/im10791276", "md5": "4e3e01748a1dcca64b9da786011bca94"},
}


def _psd_index(psd):
    index = {}

    def walk(group, prefix):
        for layer in group:
            path = f"{prefix}/{_dec(layer.name)}" if prefix else _dec(layer.name)
            index[path] = layer
            if layer.is_group():
                walk(layer, path)

    walk(psd, "")
    return index


def _layer_rgba(layer):
    """レイヤー単体（グループなら中の表示中の層を含む）を、親の表示状態に関係なく合成する。"""
    img = layer.composite(layer_filter=lambda l: l is layer or l.visible)
    return None if img is None else img.convert("RGBA")


class _PsdParts:
    def __init__(self, psd, out_dir):
        self.psd, self.index, self.cache = psd, _psd_index(psd), {}
        self.ex = _Exporter(out_dir / "parts", (0, 0), 1.0, 1)
        self.n = 0

    def part(self, spec):
        """spec: レイヤーパス、またはパスのリスト（先頭が下）。"""
        paths = [spec] if isinstance(spec, str) else list(spec)
        key = "|".join(paths)
        if key in self.cache:
            return self.cache[key]
        layers = []
        for p in paths:
            if p not in self.index:
                raise KeyError(f"PSD にレイヤー '{p}' がありません")
            layers.append(self.index[p])
        self.n += 1
        name = f"p{self.n:03d}.png"
        if len(layers) == 1:
            layer = layers[0]
            part = self.ex.save(_layer_rgba(layer), layer.offset[0], layer.offset[1], name)
            if "MULTIPLY" in str(layer.blend_mode):
                part["blend"] = "multiply"
        else:
            canvas = Image.new("RGBA", self.psd.size, (0, 0, 0, 0))
            for layer in layers:
                img = _layer_rgba(layer)
                if img is not None:
                    canvas.alpha_composite(img, (max(0, layer.offset[0]), max(0, layer.offset[1])))
            box = canvas.getbbox()
            part = self.ex.save(canvas.crop(box), box[0], box[1], name)
        part["src"] = "parts/" + part["src"]
        part["layers"] = paths
        self.cache[key] = part
        return part


def _face_slots(parts, face, order):
    slots = []
    for key in order:
        v = face.get(key)
        if not v:
            continue
        if key == "eyes":
            slots.append({"type": "eyes", "parts": {k: parts.part(p) for k, p in v.items() if p}})
        elif key == "mouth":
            slots.append({"type": "mouth", "parts": {k: parts.part(p) for k, p in v.items()}})
        else:
            for p in ([v] if isinstance(v, str) else v):
                slots.append({"type": "static", "part": parts.part(p)})
    return slots


def prepare_psdtool(spec):
    from psd_tools import PSDImage

    out = CHARACTERS / spec["name"]
    psd = PSDImage.open(spec["psd"])
    parts = _PsdParts(psd, out)
    info = {
        "name": spec["display_name"],
        "color": spec["color"],
        "size": list(psd.size),
        "base": parts.part(spec["base"]),
        "poses": {k: [parts.part(p) for p in v] for k, v in spec["poses"].items()},
        "default_pose": "normal",
        "faces": {k: _face_slots(parts, f, spec["face_order"]) for k, f in spec["faces"].items()},
        "default_face": "normal",
        "voice": spec["voice"],
        "credit": spec["credit"],
        "voice_credit": spec["voice_credit"],
    }
    if spec.get("top"):
        info["top"] = parts.part(spec["top"])
    return _write_char(spec["name"], info)


# ずんだもん立ち絵素材 V3.2（基本版）

ZUNDA_MOUTH = {"n": "むふ", "a": "ほあ", "i": "えへ", "u": "お", "e": "あは", "o": "ほう"}


def _zface(brow, eye, n=None, cheek="ほっぺ基本", eda="枝豆通常", extra=(), mouth=None,
           closed="閉じ目", smile="にっこり"):
    m = {**ZUNDA_MOUTH, **({"n": n} if n else {}), **(mouth or {})}
    return {"edamame": f"!枝豆/*{eda}", "cheek": f"!顔色/*{cheek}",
            "mouth": {k: f"!口/*{v}" for k, v in m.items()},
            "eyes": {"open": f"!目/*{eye}", "closed": closed and f"!目/*{closed}", "smile": smile and f"!目/*{smile}"},
            "brow": f"!眉/*{brow}", "extra": [f"!記号など/{x}" for x in extra]}


def _zpose(left, right):
    # PSD の重ね順は 体 → 右腕 → 左腕（右腕＝画面の左側の腕）
    return [p for p in (right and f"!右腕/*{right}", left and f"!左腕/*{left}") if p]


ZUNDAMON_AHIRU = {
    "name": "zundamon", "display_name": "ずんだもん", "color": "#2f9a3a",
    "psd": AHIRU / "zundamon_v3.2" / "ずんだもん立ち絵素材V3.2" / "ずんだもん立ち絵素材V3.2_基本版.psd",
    "base": "!体",
    "poses": {
        "normal": _zpose("腰", "腰"), "down": _zpose("基本", "基本"),
        "point": _zpose("腰", "指差し横"), "point_up": _zpose("腰", "指差し上"),
        "raise": _zpose("手を挙げる", "手を挙げる"), "think": _zpose("あごに指", "腰"),
        "mouth": _zpose("口元", "口元"), "chop": _zpose("腰", "チョップ"),
        "fold": _zpose("腕組み(右腕は非表示に)", None), "side": _zpose("横", "横"),
    },
    "face_order": ["edamame", "cheek", "mouth", "eyes", "brow", "extra"],
    "faces": {
        "normal": _zface("基本眉", "基本目"),
        "happy": _zface("基本眉2", "基本目", n="ほほえみ", cheek="ほっぺ赤め", eda="枝豆立ち"),
        "excited": _zface("上がり眉", "基本目2", cheek="ほっぺ赤め", eda="枝豆立ち", mouth={"a": "ほあー"}),
        "smug": _zface("上がり眉", "ジト目", n="にやり", eda="枝豆立ち片折れ"),
        "angry": _zface("怒り眉", "ジト目2", n="むくー", eda="枝豆立ち"),
        "cry": _zface("困り眉", "基本目", n="うへえ", eda="枝豆萎え", extra=["涙"]),
        "tired": _zface("困り眉", "ジト目", n="んー", eda="枝豆萎え", extra=["汗"]),
        "hush": _zface("基本眉2", "細め目", n="ん", cheek="ほっぺ赤め"),
        "whisper": _zface("基本眉2", "細め目", n="ん", cheek="ほっぺ赤め"),
        "sexy": _zface("基本眉2", "細め目ハート", n="ほほえみ", cheek="赤面"),
        "surprised": _zface("上がり眉", "〇〇", n="ほう", eda="枝豆立ち", mouth={"a": "うわー"}, closed=None, smile=None),
        "panic": _zface("困り眉", "><", n="うわー", cheek="青ざめ", extra=["汗多め"], closed=None, smile=None),
        "think": _zface("困り眉", "基本目↑", n="んー"),
    },
    "voice": {"speaker": 3, "speed": 1.15, "pitch": 0.0, "intonation": 1.15,
              "styles": {"normal": 3, "happy": 1, "angry": 7, "sexy": 5, "whisper": 22,
                         "hush": 38, "tired": 75, "cry": 76}},
    "credit": "立ち絵：坂本アヒル",
    "voice_credit": "VOICEVOX:ずんだもん",
}


# 四国めたん立ち絵素材 2.1（通常服＝白ロリ服のみ使う）

METAN_MOUTH = {"n": "ほほえみ", "a": "わあー", "i": "いー", "u": "ゆ", "e": "▽", "o": "お"}
METAN_EYE_SET = "!目/*目セット"
METAN_IRIS = ("カメラ目線", "カメラ目線2", "普通目", "普通目2", "目そらし", "目そらし2")


def _mface(brow, eye="カメラ目線", n=None, cheek="普通2", extra=(), mouth=None, closed="目閉じ2", smile="目閉じ"):
    m = {**METAN_MOUTH, **({"n": n} if n else {}), **(mouth or {})}
    # 目セット＝白目＋黒目の組み合わせ。それ以外（見上げ、○○ など）は1枚の層
    open_eye = ([f"{METAN_EYE_SET}/*普通白目", f"{METAN_EYE_SET}/!黒目/*{eye}"] if eye in METAN_IRIS
                else f"!目/*{eye}")
    return {"cheek": f"!顔色/*{cheek}", "mouth": {k: f"!口/*{v}" for k, v in m.items()},
            "eyes": {"open": open_eye, "closed": closed and f"!目/*{closed}", "smile": smile and f"!目/*{smile}"},
            "brow": f"!眉/*{brow}", "extra": [f"記号など/{x}" for x in extra]}


def _mpose(left, right):
    return [p for p in (right and f"*白ロリ服/!右腕/*{right}", left and f"*白ロリ服/!左腕/*{left}") if p]


METAN_AHIRU = {
    "name": "metan", "display_name": "四国めたん", "color": "#d43a86",
    "psd": AHIRU / "metan_2.1" / "四国めたん立ち絵素材2.1" / "四国めたん立ち絵素材2.1.psd",
    "base": ["ツインドリル右", "ツインドリル左", "*白ロリ服/!体"],
    "top": ["頭部アクセサリ/ヘッドドレス", "頭部アクセサリ/髪留めハート", "!前髪もみあげ"],
    "poses": {
        "normal": _mpose("普通", "普通"), "point": _mpose("普通", "指差す"), "present": _mpose("普通", "手をかざす"),
        "think": _mpose("口元に指", "普通"), "whisper": _mpose("ひそひそ", "普通"), "mic": _mpose("マイク", "普通"),
        "hold": _mpose("抱える", "普通"),
    },
    "face_order": ["cheek", "mouth", "eyes", "brow", "extra"],
    "faces": {
        "normal": _mface("太眉ごきげん"),
        "happy": _mface("ごきげん", cheek="赤面"),
        "excited": _mface("太眉ごきげん", "見上げ"),
        "smug": _mface("太眉ごきげん", "目そらし", n="にやり"),
        "angry": _mface("太眉おこ", n="んー"),
        "cry": _mface("太眉こまり", n="もむー", extra=["涙"]),
        "tired": _mface("太眉こまり", "目そらし", n="もむー", extra=["汗"]),
        "hush": _mface("ごきげん", "目そらし", n="ゆ"),
        "whisper": _mface("ごきげん", "目そらし", n="ゆ"),
        "surprised": _mface("ごきげん", "○○", n="お", closed=None, smile=None),
        "panic": _mface("こまり", "><", n="うえー", extra=["汗"], closed=None, smile=None),
        "think": _mface("太眉こまり", "見上げ", n="んー"),
    },
    "voice": {"speaker": 2, "speed": 1.1, "pitch": 0.0, "intonation": 1.1,
              "styles": {"normal": 2, "happy": 0, "angry": 6, "sexy": 4, "whisper": 36, "hush": 37}},
    "credit": "立ち絵：坂本アヒル",
    "voice_credit": "VOICEVOX:四国めたん",
}


def ensure_ahiru_psd(key):
    """坂本アヒル氏の立ち絵 zip を展開する。zip が無ければ入手方法を示して止まる。

    配布元のアップローダーはダウンロード時に利用規約への同意を求めるため、
    ここでは自動で取得しない（ユーザーが同意して取得した zip を置いてもらう）。
    """
    import subprocess

    z = AHIRU_ZIPS[key]
    if not z["zip"].exists():
        raise FileNotFoundError(
            f"{z['zip']} がありません。{z['page']} の説明文にあるパスワードで {z['url']} から zip を取得し、"
            f"この名前で置いてください（MD5 {z['md5']}）")
    dest = z["zip"].with_suffix("")
    if not dest.exists():
        from .setup_env import find_7z
        subprocess.run([find_7z(), "x", "-y", "-mcp=932", f"-o{dest}", str(z["zip"])], check=True,
                       stdout=subprocess.DEVNULL)


def prepare_zundamon():
    ensure_ahiru_psd("zundamon")
    return prepare_psdtool(ZUNDAMON_AHIRU)


def prepare_metan():
    ensure_ahiru_psd("metan")
    return prepare_psdtool(METAN_AHIRU)
