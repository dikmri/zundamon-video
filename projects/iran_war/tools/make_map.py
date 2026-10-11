"""中東の地図 SVG を Natural Earth（パブリックドメイン）の国境データから作る。

使い方（プロジェクト直下で）:
    uv run python projects/iran_war/tools/make_map.py

入力: runtime/natural_earth/ne_50m_admin_0_countries.geojson
  （https://github.com/nvkelso/natural-earth-vector の geojson/ne_50m_admin_0_countries.geojson）
出力: projects/iran_war/img/map_<variant>_base.svg            全体（海・陸・国境）
      projects/iran_war/img/map_<variant>_<ISO3>_<color>.svg   1か国だけ塗った重ね用レイヤー
      projects/iran_war/img/map_<variant>_points.json          地名の画面座標（ボードに重ねるラベル用）
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "runtime" / "natural_earth" / "ne_50m_admin_0_countries.geojson"
OUT = ROOT / "projects" / "iran_war" / "img"

SEA = "#cfe6f5"
LAND = "#f3efe4"
BORDER = "#ffffff"
COLORS = {
    "red": "#e8665a",     # イラン
    "blue": "#5b8fe0",    # イスラエル
    "orange": "#f2a14a",  # 親イラン勢力の拠点
    "gray": "#c9c3b4",    # 攻撃を受けた周辺国
    "green": "#8cc97a",   # 仲介国
}

# 地図の範囲（経度・緯度）と出力サイズ（px）
VARIANTS = {
    "region": {"lon": (31.5, 66.5), "lat": (11.6, 38.0), "width": 560},
    "gulf": {"lon": (46.5, 60.5), "lat": (22.5, 31.0), "width": 640},
}

LAYERS = {
    "region": [
        ("IRN", "red"), ("ISR", "blue"), ("LBN", "orange"), ("YEM", "orange"), ("IRQ", "orange"),
        ("SAU", "gray"), ("ARE", "gray"), ("QAT", "gray"), ("KWT", "gray"), ("BHR", "gray"),
        ("OMN", "green"), ("QAT", "green"), ("PAK", "green"), ("JOR", "gray"), ("AFG", "gray"),
    ],
    "gulf": [("IRN", "red"), ("OMN", "gray"), ("ARE", "gray")],
}

POINTS = {
    "tehran": (51.39, 35.69), "hormuz": (56.45, 26.55), "bab": (43.35, 12.6),
    "israel": (34.85, 31.4), "lebanon": (35.85, 33.95), "yemen": (45.5, 15.6), "iraq": (43.6, 33.0),
    "saudi": (45.0, 24.0), "qatar": (51.2, 25.3), "bahrain": (50.55, 26.05), "uae": (54.3, 23.8),
    "kuwait": (47.6, 29.3), "oman": (57.0, 21.0), "iran": (54.5, 32.5), "jordan": (36.8, 30.9),
    "pakistan": (64.8, 27.6), "syria": (38.6, 35.0), "egypt": (31.9, 26.5), "turkey": (38.0, 38.3),
    "kharg": (50.32, 29.25), "redsea": (38.6, 20.0), "gulf_sea": (51.6, 27.5), "oman_sea": (59.0, 24.6),
    "abbas": (56.27, 27.18), "musandam": (56.25, 26.2),
}


class Proj:
    def __init__(self, lon: tuple[float, float], lat: tuple[float, float], width: int):
        self.lon0, self.lon1 = lon
        self.lat0, self.lat1 = lat
        self.k = math.cos(math.radians((self.lat0 + self.lat1) / 2))
        self.width = width
        self.scale = width / ((self.lon1 - self.lon0) * self.k)
        self.height = round((self.lat1 - self.lat0) * self.scale)

    def xy(self, lon: float, lat: float) -> tuple[float, float]:
        return (lon - self.lon0) * self.k * self.scale, (self.lat1 - lat) * self.scale


def rings(geom: dict) -> list[list[list[float]]]:
    if geom["type"] == "Polygon":
        return geom["coordinates"]
    if geom["type"] == "MultiPolygon":
        return [r for poly in geom["coordinates"] for r in poly]
    return []


def bbox_hits(rs: list, pr: Proj, margin: float = 3.0) -> bool:
    for r in rs:
        for lon, lat in r:
            if pr.lon0 - margin <= lon <= pr.lon1 + margin and pr.lat0 - margin <= lat <= pr.lat1 + margin:
                return True
    return False


def path_d(rs: list, pr: Proj) -> str:
    parts = []
    for r in rs:
        pts = [pr.xy(lon, lat) for lon, lat in r]
        # 画面上で 0.6px 未満しか動かない点は省いてファイルを小さくする
        kept = [pts[0]]
        for p in pts[1:]:
            q = kept[-1]
            if abs(p[0] - q[0]) + abs(p[1] - q[1]) >= 0.6:
                kept.append(p)
        if len(kept) < 3:
            continue
        parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in kept) + "Z")
    return "".join(parts)


def svg(pr: Proj, body: str, background: str | None) -> str:
    bg = f'<rect width="{pr.width}" height="{pr.height}" fill="{background}"/>' if background else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {pr.width} {pr.height}" '
        f'width="{pr.width}" height="{pr.height}">{bg}{body}</svg>\n'
    )


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    feats = {}
    for f in data["features"]:
        code = f["properties"].get("ADM0_A3")
        feats.setdefault(code, []).extend(rings(f["geometry"]))
    OUT.mkdir(parents=True, exist_ok=True)

    for name, v in VARIANTS.items():
        pr = Proj(v["lon"], v["lat"], v["width"])
        land = []
        for code, rs in feats.items():
            if bbox_hits(rs, pr):
                land.append(f'<path id="c-{code}" d="{path_d(rs, pr)}"/>')
        body = f'<g fill="{LAND}" stroke="{BORDER}" stroke-width="1.6" stroke-linejoin="round">{"".join(land)}</g>'
        (OUT / f"map_{name}_base.svg").write_text(svg(pr, body, SEA), encoding="utf-8")

        for code, color in LAYERS[name]:
            d = path_d(feats[code], pr)
            layer = (f'<path d="{d}" fill="{COLORS[color]}" stroke="{BORDER}" '
                     f'stroke-width="1.6" stroke-linejoin="round"/>')
            (OUT / f"map_{name}_{code}_{color}.svg").write_text(svg(pr, layer, None), encoding="utf-8")

        pts = {k: [round(c, 1) for c in pr.xy(*ll)] for k, ll in POINTS.items()}
        pts["_size"] = [pr.width, pr.height]
        (OUT / f"map_{name}_points.json").write_text(json.dumps(pts, ensure_ascii=False, indent=1), encoding="utf-8")
        print(name, pr.width, pr.height, len(land), "countries")


if __name__ == "__main__":
    main()
