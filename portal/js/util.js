// DOM に触れない純粋な関数（tests/portal_js/util.test.mjs で確認）
// ブラウザでは <script> で読むと window.ZA.util に、node では require で読める。
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else (root.ZA = root.ZA || {}).util = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const pad2 = (n) => String(n).padStart(2, '0');

  function fmtTime(sec) {
    if (!Number.isFinite(sec) || sec < 0) sec = 0;
    const s = Math.floor(sec);
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    return h ? `${h}:${pad2(m)}:${pad2(r)}` : `${m}:${pad2(r)}`;
  }

  function fmtDate(iso) {
    if (!iso) return '';
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    return m ? `${m[1]}.${m[2]}.${m[3]}` : '';
  }

  function fmtBytes(n) {
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return `${i ? n.toFixed(1) : n} ${units[i]}`;
  }

  const splitGraphemes = (s) => Array.from(s);

  // カタカナ → ひらがな（ヴ・ヵ・ヶ以外の通常の範囲）
  const kataToHira = (s) => s.replace(/[ァ-ヶ]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0x60));

  function normalize(s) {
    return kataToHira(String(s ?? '').normalize('NFKC').toLowerCase()).replace(/\s+/g, ' ').trim();
  }

  const tokensOf = (q) => normalize(q).split(' ').filter(Boolean);

  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  /** 検索語に当たる部分を <mark> で囲む。全角・半角やカタカナ・ひらがなの違いは無視して照合する。 */
  function highlight(text, query) {
    const chars = splitGraphemes(String(text ?? ''));
    const tokens = tokensOf(query);
    if (!tokens.length) return escapeHtml(text);
    // 正規化後の各文字が、元の何文字目から来たか
    let norm = '';
    const from = [];
    chars.forEach((c, i) => {
      const n = kataToHira(c.normalize('NFKC').toLowerCase());
      for (const u of n) { norm += u; from.push(i); }
    });
    const hit = new Array(chars.length).fill(false);
    for (const t of tokens) {
      let at = norm.indexOf(t);
      while (at !== -1) {
        for (let k = at; k < at + t.length; k++) hit[from[k]] = true;
        at = norm.indexOf(t, at + Math.max(1, t.length));
      }
    }
    let out = '', open = false;
    chars.forEach((c, i) => {
      if (hit[i] && !open) { out += '<mark>'; open = true; }
      if (!hit[i] && open) { out += '</mark>'; open = false; }
      out += escapeHtml(c);
    });
    return open ? out + '</mark>' : out;
  }

  // 文節での改行用。句読点・閉じ括弧・ひらがなだけの語（助詞など）は前の語につなげる
  const ATTACH = /^[、。，．,.!！?？）)」』】〕〉》・×…‥〜～:：;；ー]+$/;
  const OPENING = /^[（(「『【〔〈《]+$/;
  const HIRAGANA = /^[ぁ-ゟ]+$/;
  const segmenter = typeof Intl !== 'undefined' && Intl.Segmenter ? new Intl.Segmenter('ja', { granularity: 'word' }) : null;

  /** 見出しを文節に分ける（この区切りでだけ改行させる）。 */
  function phrases(text) {
    const s = String(text ?? '');
    if (!segmenter) return [s];
    const out = [];
    let afterOpening = false;
    for (const { segment } of segmenter.segment(s)) {
      const last = out[out.length - 1];
      const join = last !== undefined && !/\s$/.test(last) && !/^\s/.test(segment)
        && (afterOpening || ATTACH.test(segment) || (HIRAGANA.test(segment) && !/[、。，．,.!！?？]$/.test(last))
          || (/[\w\-.]$/.test(last) && /^[\w\-.]/.test(segment)));
      if (join) out[out.length - 1] += segment; else out.push(segment);
      afterOpening = OPENING.test(segment);
    }
    return out;
  }

  const phraseHtml = (text) => phrases(text).map(escapeHtml).join('<wbr>');

  function inlineMd(text) {
    return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  }

  function metaText(v) {
    return normalize([v.fullTitle, v.series, v.lede, ...(v.toc || []).map((e) => e.title),
      ...(v.summary || []).map((s) => `${s.text} ${s.sub || ''}`)].join(' '));
  }

  /** タイトル・目次・まとめ（meta）とセリフ（lines）から探す。すべての語を含むものだけ返す。 */
  function searchCatalog(videos, query) {
    const tokens = tokensOf(query);
    if (!tokens.length) return videos.map((video) => ({ video, meta: true, lines: [] }));
    const out = [];
    for (const video of videos) {
      const meta = tokens.every((t) => metaText(video).includes(t));
      const lines = (video.lines || []).filter((l) => { const n = normalize(l.text); return tokens.every((t) => n.includes(t)); });
      if (meta || lines.length) out.push({ video, meta, lines });
    }
    return out;
  }

  /** start の昇順に並んだ items のうち、時刻 t までに始まった最後のものの位置（なければ -1）。 */
  function indexAt(items, t) {
    let lo = 0, hi = items.length - 1, ans = -1;
    while (lo <= hi) {
      const m = (lo + hi) >> 1;
      if (items[m].start <= t) { ans = m; lo = m + 1; } else hi = m - 1;
    }
    return ans;
  }

  /** 「音楽 / 効果音」「音楽：魔王魂 / 効果音ラボ」のような複合の項目を分け、値の先頭の「項目名：」を外す。 */
  function splitCredit(key, value) {
    const keys = key.split(/\s*\/\s*/);
    const vals = value.split(/\s*\/\s*/);
    const pairs = keys.length > 1 && keys.length === vals.length ? keys.map((k, i) => [k, vals[i]]) : [[key, value]];
    return pairs.map(([k, v]) => [k, v.startsWith(`${k}：`) || v.startsWith(`${k}:`) ? v.slice(k.length + 1).trim() : v]);
  }

  function aggregateCredits(videos) {
    const map = new Map();
    for (const v of videos) {
      for (const [k, val] of (v.credits || []).flatMap(([a, b]) => splitCredit(a, b))) {
        if (!map.has(k)) map.set(k, []);
        const arr = map.get(k);
        if (!arr.includes(val)) arr.push(val);
      }
    }
    return [...map.entries()];
  }

  function rng(seed) {
    let s = seed >>> 0 || 1;
    return () => { s ^= s << 13; s >>>= 0; s ^= s >> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; };
  }

  /** 帯に流すセリフを選ぶ。同じ seed なら同じ結果。 */
  function sampleQuotes(videos, who, n, seed = 1, minLen = 10, maxLen = 34) {
    const pool = [];
    for (const video of videos) {
      for (const line of video.lines || []) {
        const len = splitGraphemes(line.text).length;
        if (line.who === who && len >= minLen && len <= maxLen) pool.push({ video, line });
      }
    }
    const r = rng(seed);
    for (let i = pool.length - 1; i > 0; i--) {
      const j = Math.floor(r() * (i + 1));
      [pool[i], pool[j]] = [pool[j], pool[i]];
    }
    return pool.slice(0, n);
  }

  function clamp(v, a, b) { return Math.min(b, Math.max(a, v)); }

  return { fmtTime, fmtDate, fmtBytes, splitGraphemes, normalize, escapeHtml, highlight, phrases, phraseHtml, inlineMd, searchCatalog, indexAt, splitCredit, aggregateCredits, sampleQuotes, clamp };
});
