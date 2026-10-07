"""ポータルのカタログを組み立てる純粋な変換。

入力は out/<名前>/data.js（タイムライン）と mp4 の情報、出力はサイトが読む JSON の1件分。
ファイルや ffmpeg には触らない（それは media.py）。
"""
import html as _html
import json
import math
import os
import re
import urllib.parse
from collections import Counter
from html.parser import HTMLParser

from ..script import strip_markup

_KICKER = re.compile(r"^\s*【([^】]+)】\s*")
_END_PUNCT = "。．.！!？?…、,」』）)♪☆★ 　\n"
_SENTENCE = re.compile(r"[。！!？?]+")


def asset_url(target, web_dir, version=None):
    """ポータルの HTML（web_dir）から見た target の相対 URL。file:// で開いても読めるようにする。"""
    rel = os.path.relpath(target, web_dir).replace(os.sep, "/")
    url = urllib.parse.quote(rel, safe="/.-_~")
    return f"{url}?v={version}" if version else url


def parse_data_js(text):
    """`window.ZV = {...};` から JSON を取り出す。"""
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


def split_title(title):
    """「【ずんだもん解説】本題」を ("ずんだもん解説", "本題") に分ける。"""
    m = _KICKER.match(title or "")
    if not m:
        return "", (title or "").strip()
    return m.group(1).strip(), title[m.end():].strip()


class _TitleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.stack = [[]], []

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.lines.append([])
            return
        cls = dict(attrs).get("class") or ""
        self.stack.append("accent" in cls.split())

    def handle_endtag(self, tag):
        if tag != "br" and self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if not data:
            return
        accent = any(self.stack)
        line = self.lines[-1]
        if line and line[-1]["accent"] == accent:
            line[-1]["t"] += data
        else:
            line.append({"t": data, "accent": accent})


def display_title(heading_html):
    """タイトルボードの見出し HTML を、行ごとの [{t, accent}] に直す（強調の span だけ残す）。"""
    p = _TitleParser()
    p.feed(heading_html or "")
    lines = []
    for line in p.lines:
        segs = [{"t": s["t"].strip() if len(line) == 1 else s["t"], "accent": s["accent"]} for s in line]
        segs = [s for s in segs if s["t"].strip()]
        if segs:
            lines.append(segs)
    return lines


def _label(sc, is_last):
    b = sc.get("board") or {}
    layout = b.get("layout")
    if layout == "chapter":
        return "chapter", b.get("num"), b.get("heading") or b.get("title") or ""
    if layout == "title":
        return "opening", None, "オープニング"
    if layout == "credits" or sc.get("id") == "ending":
        return "ending", None, "エンディング"
    if b.get("title"):
        return "scene", None, b["title"]
    if is_last:
        return "ending", None, "エンディング"
    return None


def build_toc(scenes):
    """シーンから目次を作る。見出しのないシーンは直前の項目に含める。"""
    toc, chapter = [], None
    for i, sc in enumerate(scenes):
        lab = _label(sc, i == len(scenes) - 1)
        start, end = round(sc["start"], 2), round(sc["end"], 2)
        if lab is None:
            if toc:
                toc[-1]["end"] = end
                continue
            lab = ("opening", None, "オープニング")
        kind, num, title = lab
        if kind == "chapter":
            chapter = len(toc)
        toc.append({"kind": kind, "num": num, "title": title, "start": start, "end": end,
                    "scene": i, "chapter": chapter})
    return toc


def summary_items(scenes):
    """まとめ（bullets レイアウト）の項目。"""
    for sc in scenes:
        b = sc.get("board") or {}
        if b.get("layout") == "bullets" and b.get("items"):
            return [{"text": it.get("text", ""), "sub": it.get("sub", "")} if isinstance(it, dict)
                    else {"text": str(it), "sub": ""} for it in b["items"]]
    return []


class _PairParser(HTMLParser):
    """指定クラスの要素の中で、指定タグの文字列を集める。"""

    def __init__(self, container, container_class, tags):
        super().__init__(convert_charrefs=True)
        self.container, self.container_class, self.tags = container, container_class, tags
        self.depth, self.items, self.cur, self.sub = 0, [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == self.container:
            if self.depth or self.container_class in (dict(attrs).get("class") or "").split():
                self.depth += 1
            return
        if not self.depth:
            return
        if tag in self.tags:
            self.cur = {"tag": tag, "text": "", "note": ""}
            self.sub = None
        elif tag == "small" and self.cur is not None:
            self.sub = True

    def handle_endtag(self, tag):
        if tag == self.container and self.depth:
            self.depth -= 1
        elif tag == "small":
            self.sub = None
        elif tag in self.tags and self.cur is not None:
            self.items.append(self.cur)
            self.cur = None

    def handle_data(self, data):
        if self.cur is not None:
            self.cur["note" if self.sub else "text"] += data


def _clean(s):
    return re.sub(r"\s+", " ", _html.unescape(s)).strip()


def parse_credits(html):
    """エンディングの <dl class="credits"> を [[項目, 内容], ...] にする。"""
    p = _PairParser("dl", "credits", ("dt", "dd"))
    p.feed(html or "")
    out, key = [], None
    for it in p.items:
        text = _clean(it["text"] + it["note"])
        if it["tag"] == "dt":
            key = text
        elif key is not None:
            out.append([key, text])
            key = None
    return out


def parse_sources(html):
    """参考資料の <ul class="src"><li>本文<small>補足</small></li> を読む。"""
    p = _PairParser("ul", "src", ("li",))
    p.feed(html or "")
    return [{"text": _clean(it["text"]), "note": _clean(it["note"])} for it in p.items]


def top_ending(texts):
    """文末2文字のうち最も多いもの（口ぐせ）を [語尾, 回数] で返す。"""
    c = Counter()
    for text in texts:
        for sentence in _SENTENCE.split(text or ""):
            s = sentence.rstrip(_END_PUNCT)
            if len(s) >= 2:
                c[s[-2:]] += 1
    if not c:
        return None
    word, n = c.most_common(1)[0]
    return [word, n]


def speaker_stats(lines):
    """話者ごとのセリフ数・話した秒数・文字数・口ぐせ。"""
    st = {}
    for ln in lines:
        s = st.setdefault(ln["who"], {"lines": 0, "seconds": 0.0, "chars": 0, "_texts": []})
        s["lines"] += 1
        s["seconds"] += max(0.0, ln["end"] - ln["start"])
        s["chars"] += len(re.sub(r"\s", "", ln.get("text") or ""))
        s["_texts"].append(ln.get("text") or "")
    for s in st.values():
        s["ending"] = top_ending(s.pop("_texts"))
        s["seconds"] = round(s["seconds"], 2)
    return st


def poster_time(scenes):
    """サムネイルに使う時刻。タイトルの登場アニメーションが終わったころ。"""
    if not scenes:
        return 0.0
    first = scenes[0]
    s, e = first["start"], first["end"]
    if (first.get("board") or {}).get("layout") == "title":
        return round(min(s + 3.5, e - 0.5, max(s + 2.0, (s + e) / 2)), 2)
    return round((s + e) / 2, 2)


def preview_times(toc, total, n=5, clip=1.6):
    """ホバー時に流す短いダイジェストの切り出し位置。内容のシーンから均等に n 個選ぶ。"""
    content = [e for e in toc if e["kind"] == "scene" and e["end"] - e["start"] >= clip + 1.0]
    if not content:
        span = max(0.0, total - clip)
        return [round(span * (i + 0.5) / n, 2) for i in range(n)]
    if len(content) > n:
        idx = sorted({round(i * (len(content) - 1) / (n - 1)) for i in range(n)}) if n > 1 else [0]
        content = [content[i] for i in idx]
    out = []
    for e in content:
        t = e["start"] + (e["end"] - e["start"]) * 0.55
        t = min(max(t, e["start"] + 1.0), e["end"] - clip - 0.3)
        out.append(round(max(t, e["start"]), 2))
    return out


def sprite_plan(total, max_frames=200, cols=10, w=160, h=90):
    """シークバーのホバー用サムネイル（一定間隔で撮ってタイル状に並べた1枚）の計画。"""
    interval = max(2, math.ceil(total / max_frames))
    count = int(total // interval) + 1
    return {"interval": interval, "count": count, "cols": cols, "rows": math.ceil(count / cols), "w": w, "h": h}


def thumb_time(entry):
    """目次の各項目のサムネイル時刻。ボードの要素が出そろったあたり。"""
    s, e = entry["start"], entry["end"]
    if entry["kind"] == "chapter":
        return round(min(s + 2.0, (s + e) / 2), 2)
    return round(max(s, min(s + (e - s) * 0.7, e - 1.0)), 2)


def make_entry(name, data, file_info, urls):
    """カタログの1件分。file_info は mp4 の情報、urls はサイトから見た各ファイルの URL。"""
    scenes = data["scenes"]
    meta = data["meta"]
    kicker, title = split_title(meta.get("title") or name)
    opening = (scenes[0].get("board") or {}) if scenes else {}
    toc = build_toc(scenes)
    for i, e in enumerate(toc):
        e["thumb"] = urls["thumbs"][i] if i < len(urls.get("thumbs", [])) else None
    lines = []
    for ln in data["lines"]:
        item = {"who": ln["who"], "text": strip_markup(ln["text"]), "start": round(ln["start"], 2),
                "end": round(ln["end"], 2), "scene": ln.get("scene")}
        if "**" in ln["text"]:
            item["rich"] = ln["text"].replace("\n", "")
        lines.append(item)
    stats = speaker_stats(lines)
    cast = {}
    for key, c in data.get("cast", {}).items():
        info = c.get("info") or {}
        cast[key] = {"name": info.get("name", key), "color": c.get("color") or info.get("color", "#888"),
                     "position": c.get("position"), "voice": info.get("voice_credit") or "",
                     "stats": stats.get(key, {"lines": 0, "seconds": 0.0, "chars": 0, "ending": None})}
    ending_html = next((sc["board"].get("html", "") for sc in reversed(scenes)
                        if "credits" in ((sc.get("board") or {}).get("html") or "")), "")
    sources_html = next((sc["board"].get("html", "") for sc in scenes
                         if 'class="src"' in ((sc.get("board") or {}).get("html") or "")), "")
    return {
        "id": name,
        "title": title,
        "kicker": kicker,
        "fullTitle": meta.get("title") or name,
        "display": display_title(opening.get("heading_html") or ""),
        "badge": opening.get("badge") or kicker,
        "lede": opening.get("sub") or "",
        "series": meta.get("series") or "",
        "duration": round(file_info.get("duration") or data.get("total") or 0, 2),
        "date": file_info.get("date"),
        "video": {"src": urls["video"], "width": file_info.get("width") or meta.get("width"),
                  "height": file_info.get("height") or meta.get("height"), "fps": meta.get("fps"),
                  "size": file_info.get("size")},
        "poster": urls["poster"],
        "preview": urls["preview"],
        "sprite": urls.get("sprite"),
        "toc": toc,
        "lines": lines,
        "cast": cast,
        "summary": summary_items(scenes),
        "sources": parse_sources(sources_html),
        "credits": parse_credits(ending_html),
    }
