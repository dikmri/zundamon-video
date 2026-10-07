// ずんだもん解説プレイヤー: window.ZV（build が書き出す data.js）から、時刻 t の画面を決定的に組み立てる。
// 描画（render）時は Python 側が window.__seek(t) を1フレームずつ呼んでスクリーンショットを撮る。
(function () {
  'use strict';
  const D = window.ZV;
  const RENDER = new URLSearchParams(location.search).has('render');
  if (RENDER) document.body.classList.add('render');

  const $ = (s) => document.querySelector(s);
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const easeOut = (p) => 1 - Math.pow(1 - p, 3);
  const easeBack = (p) => { const c = 1.6; return 1 + (c + 1) * Math.pow(p - 1, 3) + c * Math.pow(p - 1, 2); };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  // 字幕・ボード用の簡易記法: **強調**、改行
  const markup = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<em>$1</em>').replace(/\n/g, '<br>');
  // 描画時は Python 側が console を拾い、プレビュー時はローカルサーバーの /__log へ送ってファイルに残す
  const log = (ev, args, result) => {
    const line = `${ev} | ${JSON.stringify(args ?? null)} | ${result ?? '-'}`;
    console.log('[zv] ' + line);
    if (!RENDER && navigator.sendBeacon) navigator.sendBeacon('/__log', line);
  };

  const stage = $('#stage');
  stage.style.width = D.meta.width + 'px';
  stage.style.height = D.meta.height + 'px';
  $('#series').textContent = D.meta.series || '';

  // ---------- ボード ----------
  function stepAttr(item, i) {
    const step = item.step ?? i + 1;
    return `data-step="${step}" data-anim="${item.anim || 'up'}"`;
  }
  function renderBoard(b) {
    if (!b) return '';
    const title = b.title ? `<h2 class="board-title">${markup(b.title)}</h2>` : '';
    switch (b.layout) {
      case 'title':
        return `<div class="title-card">${b.badge ? `<div class="badge">${markup(b.badge)}</div>` : ''}` +
          `<h1>${b.heading_html || markup(b.heading || '')}</h1>${b.sub ? `<p>${markup(b.sub)}</p>` : ''}</div>`;
      case 'chapter':
        return `<div class="chapter-card"><div class="num">${esc(b.num || '')}</div>` +
          `<h2>${markup(b.heading || '')}</h2><div class="line"></div></div>`;
      case 'bullets':
        return `${title}<div class="board-body"><ul class="bullets">` +
          (b.items || []).map((it, i) => {
            const o = typeof it === 'string' ? { text: it } : it;
            return `<li ${stepAttr(o, i)}><div>${markup(o.text)}${o.sub ? `<small>${markup(o.sub)}</small>` : ''}</div></li>`;
          }).join('') + `</ul>${b.html || ''}</div>`;
      case 'credits':
        return `${title}<div class="board-body"><dl class="credits">` +
          (b.items || []).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${markup(v)}</dd>`).join('') + '</dl></div>';
      default:
        return `${title}<div class="board-body">${b.html || ''}</div>`;
    }
  }

  const boardsEl = $('#boards');
  D.scenes.forEach((sc) => {
    const el = document.createElement('section');
    el.className = 'board ' + ((sc.board && sc.board.class) || '');
    el.innerHTML = renderBoard(sc.board);
    window.zvIcons(el);
    boardsEl.appendChild(el);
    sc._el = el;
    sc._steps = [...el.querySelectorAll('[data-step]')].map((e) => ({
      el: e, step: +e.dataset.step, anim: e.dataset.anim || 'up',
      full: e.dataset.anim === 'type' ? e.textContent : null,
      dur: +(e.dataset.dur || 0),
    }));
    sc._steps.forEach((s) => { if (s.full !== null) s.el.textContent = ''; });
    // 埋め込み動画: data-step の表示時刻から再生する。音は build 側で audio.wav に混ぜるので常に消音
    sc._clips = [...el.querySelectorAll('video[data-clip]')].map((v) => {
      v.muted = true; v.preload = 'auto'; v.playsInline = true;
      // メモリへ読み込んで Blob URL で渡す。描画時のディスク直接配信もプレビューの HTTP サーバーも
      // Range 要求に応じないため、URL を直接渡すと seekable が [0,0] になり再生位置を動かせない。
      const loading = fetch(v.dataset.clip)
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.blob(); })
        .then((b) => { v.src = URL.createObjectURL(b); })
        .catch((e) => log('clip.fetch', v.dataset.clip, 'ERROR ' + e));
      return { el: v, step: +(v.dataset.step || 0), after: v.dataset.start === 'after', loading };
    });
  });

  function stepTime(sc, step) {
    const v = sc.steps[String(step)];
    return v === undefined ? Infinity : v;
  }

  function applyStep(s, t, sc) {
    const t0 = stepTime(sc, s.step);
    const el = s.el;
    if (s.anim === 'type') {
      const n = s.full.length;
      const dur = s.dur || Math.min(4, n * 0.02);
      const k = t < t0 ? 0 : Math.round(n * clamp((t - t0) / dur));
      if (el._k !== k) { el.textContent = s.full.slice(0, k); el._k = k; }
      el.style.opacity = t < t0 ? 0 : 1;
      return;
    }
    if (s.anim === 'count') {
      const to = +el.dataset.to, dec = +(el.dataset.decimals || 0), dur = s.dur || 0.8;
      const p = easeOut(clamp((t - t0) / dur));
      el.textContent = (to * p).toFixed(dec);
      el.style.opacity = t < t0 ? 0 : 1;
      return;
    }
    const p = clamp((t - t0) / 0.35);
    const e = easeOut(p);
    el.style.opacity = p;
    switch (s.anim) {
      case 'pop': el.style.transform = `scale(${0.6 + 0.4 * easeBack(p)})`; break;
      case 'left': el.style.transform = `translateX(${(1 - e) * -60}px)`; break;
      case 'right': el.style.transform = `translateX(${(1 - e) * 60}px)`; break;
      case 'fade': el.style.transform = ''; break;
      case 'mark': // 文中の語に蛍光ペンを引く
        el.style.opacity = 1;
        el.style.backgroundColor = `rgba(255, 214, 64, ${0.55 * e})`;
        el.style.boxShadow = `0 0 0 4px rgba(255, 214, 64, ${0.55 * e})`;
        el.style.borderRadius = '6px';
        break;
      case 'stamp': el.style.transform = `scale(${1 + 0.8 * (1 - e)}) rotate(${(1 - e) * -8}deg)`; break;
      case 'kenburns': { // 写真をゆっくり寄せる（.kb の枠の中の img に付ける）。data-dir で寄る方向、data-dur で秒数
        const dur = s.dur || 12;
        const q = clamp((t - t0) / dur);
        const [dx, dy] = ({ left: [1, 0], right: [-1, 0], up: [0, 1], down: [0, -1] })[el.dataset.dir] || [0, 0];
        el.style.transform = `scale(${1.02 + 0.1 * q}) translate(${dx * 2.5 * q}%, ${dy * 2.5 * q}%)`;
        break;
      }
      default: el.style.transform = `translateY(${(1 - e) * 36}px)`;
    }
  }

  // ---------- キャラクター ----------
  const chars = {};
  for (const [key, c] of Object.entries(D.cast)) {
    const info = c.info;
    const el = document.createElement('div');
    el.className = `char char-${key}`;
    el.style.width = info.size[0] + 'px';
    el.style.height = info.size[1] + 'px';
    el.style.left = c.x + 'px';
    el.style.top = c.y + 'px';
    const body = document.createElement('div');
    body.className = 'body';
    el.appendChild(body);
    const img = (part, cls) => {
      const i = document.createElement('img');
      i.src = c.base_url + part.src;
      i.style.left = part.x + 'px'; i.style.top = part.y + 'px';
      i.style.width = part.w + 'px'; i.style.height = part.h + 'px';
      if (cls) i.className = cls;
      if (part.blend) i.style.mixBlendMode = part.blend;
      return i;
    };
    body.appendChild(img(info.base));
    // 腕などのポーズ差分（base と表情の間に重ねる）
    const poses = {};
    for (const [pname, parts] of Object.entries(info.poses || {})) {
      const p = document.createElement('div');
      p.className = 'pose';
      for (const part of parts) p.appendChild(img(part));
      body.appendChild(p);
      poses[pname] = p;
    }
    const faces = {};
    for (const [fname, slots] of Object.entries(info.faces)) {
      const f = document.createElement('div');
      f.className = 'face';
      const eyes = {}, mouth = {};
      for (const slot of slots) {
        if (slot.type === 'static') f.appendChild(img(slot.part));
        else if (slot.type === 'eyes') {
          for (const [k, p] of Object.entries(slot.parts)) { const i = img(p, 'v'); eyes[k] = i; f.appendChild(i); }
        } else if (slot.type === 'mouth') {
          for (const [k, p] of Object.entries(slot.parts)) { if (!p) continue; const i = img(p, 'v'); mouth[k] = i; f.appendChild(i); }
        }
      }
      body.appendChild(f);
      faces[fname] = { el: f, eyes, mouth };
    }
    // 表情より上に重なる層（前髪・髪飾りなど）
    if (info.top) body.appendChild(img(info.top));
    $('#chars').appendChild(el);
    const lines = D.lines.filter((l) => l.who === key);
    chars[key] = { key, c, el, body, faces, poses, lines, cur: {} };
  }

  function shapeAt(track, t) {
    let lo = 0, hi = track.length - 1, ans = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (track[m][0] <= t) { ans = m; lo = m + 1; } else hi = m - 1; }
    return ans < 0 ? 'n' : track[ans][1];
  }

  function setOn(map, key) {
    for (const [k, el] of Object.entries(map)) el.classList.toggle('on', k === key);
  }

  function updateChar(ch, t, scene) {
    const { c, faces, lines } = ch;
    // 直近の自分のセリフ（表情はそのセリフから次のセリフまで持続）
    let last = null, speaking = null;
    for (const l of lines) {
      if (l.start <= t) last = l; else break;
    }
    if (last && t < last.end) speaking = last;
    const faceName = (last && faces[last.face]) ? last.face : (faces[c.face] ? c.face : c.info.default_face);
    const face = faces[faceName];
    if (ch.cur.face !== faceName) {
      for (const [k, f] of Object.entries(faces)) f.el.classList.toggle('on', k === faceName);
      ch.cur.face = faceName;
    }
    // ポーズも表情と同じく、そのセリフから次の自分のセリフまで続く（指定なしは既定のポーズ）
    if (Object.keys(ch.poses).length) {
      const fallback = ch.poses[c.pose] ? c.pose : (c.info.default_pose || 'normal');
      const poseName = (last && last.pose && ch.poses[last.pose]) ? last.pose : fallback;
      if (ch.cur.pose !== poseName) {
        for (const [k, p] of Object.entries(ch.poses)) p.classList.toggle('on', k === poseName);
        ch.cur.pose = poseName;
      }
    }
    // 口
    const mouth = speaking ? shapeAt(speaking.mouth, t - speaking.start) : 'n';
    setOn(face.mouth, face.mouth[mouth] ? mouth : (face.mouth.n ? 'n' : null));
    // 目: 笑い目指定 > まばたき > 開き目
    let eye = 'open';
    if (last && last.eyes && t < last.end + 0.6 && face.eyes[last.eyes]) eye = last.eyes;
    else if (c.blinks.some((b) => t >= b && t < b + 0.11)) eye = 'closed';
    if (!face.eyes[eye]) eye = 'open';
    setOn(face.eyes, eye);

    // 動き: 登場・呼吸・しゃべり始めの跳ね・モーション指定
    let x = 0, y = 0, rot = 0, sx = 1, sy = 1;
    const enter = clamp((t - (c.enter_at || 0)) / 0.6);
    x += (1 - easeOut(enter)) * (c.position === 'left' ? -500 : 500);
    sy *= 1 + 0.006 * Math.sin((t / 3.4) * Math.PI * 2 + (c.position === 'left' ? 1.3 : 0));
    if (last) {
      const dt = t - last.start;
      const motion = last.motion || 'hop';
      if (motion === 'hop' && dt < 0.28) y -= 12 * Math.sin(Math.PI * dt / 0.28);
      if (motion === 'jump' && dt < 0.5) { y -= 70 * Math.sin(Math.PI * dt / 0.5); }
      if (motion === 'shake' && dt < 0.6) x += 14 * Math.sin(dt * 60) * (1 - dt / 0.6);
      if (motion === 'nod' && dt < 0.6) { y += 14 * Math.sin(Math.PI * dt / 0.3) * (dt < 0.3 ? 1 : 0.6); }
      if (motion === 'lean' && dt < 99) rot = (c.position === 'left' ? 3 : -3) * easeOut(clamp(dt / 0.3)) * (t < last.end + 0.4 ? 1 : 0);
      if (motion === 'shrink' && t < last.end + 0.4) { const p = easeOut(clamp(dt / 0.25)); sy *= 1 - 0.06 * p; sx *= 1 + 0.03 * p; }
    }
    const hide = scene && scene.hide_chars ? 1 : 0;
    const flip = c.flip ? -1 : 1;
    ch.body.style.transform = `translate(${x}px, ${y + hide * 900}px) rotate(${rot}deg) scale(${sx * flip}, ${sy})`;
    ch.el.style.transform = `scale(${c.scale || 1})`;
  }

  // ---------- 字幕 ----------
  const subEl = $('#subtext');
  let curSub = null;
  function updateSubtitle(t) {
    let line = null;
    for (let i = 0; i < D.lines.length; i++) {
      const l = D.lines[i], next = D.lines[i + 1];
      const until = Math.min(next ? next.start : Infinity, l.end + 1.0);
      if (t >= l.start && t < until) { line = l; break; }
    }
    if (line !== curSub) {
      curSub = line;
      subEl.innerHTML = line ? markup(line.text) : '';
      if (line) subEl.style.setProperty('--outline', D.cast[line.who].color);
      // 2行に収まらない字幕は文字を段階的に縮める
      let fs = 60;
      subEl.style.fontSize = fs + 'px';
      while (line && fs > 44 && subEl.offsetHeight > fs * 1.3 * 2 + 4) { fs -= 4; subEl.style.fontSize = fs + 'px'; }
      if (line && subEl.offsetHeight > fs * 1.3 * 2 + 4) log('subtitle.overflow', { text: line.text }, `${fs}px`);
    }
  }

  // ---------- 章ラベル ----------
  const chapEl = $('#chapter');
  let curChap = null;
  function updateHeader(t, si) {
    let chap = '', since = 0;
    for (let i = 0; i <= si; i++) if (D.scenes[i].chapter !== undefined) { chap = D.scenes[i].chapter; since = D.scenes[i].start; }
    const sc = D.scenes[si];
    if (sc && sc.hide_header) chap = '';
    if (chap !== curChap) { chapEl.textContent = chap; curChap = chap; }
    const p = easeOut(clamp((t - since) / 0.4));
    chapEl.style.transform = `translateX(${(1 - p) * -420}px)`;
    $('#series').style.opacity = sc && sc.hide_header ? 0 : 1;
  }

  // ---------- 全体 ----------
  function sceneIndexAt(t) {
    let si = 0;
    for (let i = 0; i < D.scenes.length; i++) if (D.scenes[i].start <= t) si = i;
    return si;
  }

  function update(t) {
    const si = sceneIndexAt(t);
    D.scenes.forEach((sc, i) => {
      const inP = clamp((t - sc.start) / 0.4);
      const outP = i + 1 < D.scenes.length ? clamp((t - sc.end) / 0.3) : 0;
      const op = (sc.start <= t ? inP : 0) * (1 - outP);
      const el = sc._el;
      if (op <= 0) { if (el.style.display !== 'none') el.style.display = 'none'; return; }
      el.style.display = 'flex';
      el.style.opacity = op;
      const k = sc.board && sc.board.enter === 'zoom' ? 0.85 + 0.15 * easeBack(inP) : 1;
      el.style.transform = `translateY(${(1 - easeOut(inP)) * 40 + outP * -30}px) scale(${k})`;
      sc._steps.forEach((s) => applyStep(s, t, sc));
    });
    for (const ch of Object.values(chars)) updateChar(ch, t, D.scenes[si]);
    updateSubtitle(t);
    updateHeader(t, si);
    // 章カード等の白フラッシュ
    let fl = 0;
    for (const sc of D.scenes) if (sc.flash && t >= sc.start) fl = Math.max(fl, 1 - clamp((t - sc.start) / 0.35));
    $('#flash').style.opacity = fl * 0.85;
  }

  // 素材の読み込み完了（フォント・画像のデコード）を待つ
  async function ready() {
    await document.fonts.ready;
    const fams = ['800 60px Rounded', '900 50px Rounded', '700 38px Rounded', '500 30px Rounded', '96px Dela'];
    for (const f of fams) {
      for (let i = 0; ; i++) {
        try { await document.fonts.load(f, 'あ亜A1'); break; } catch (e) {
          log('font.load', f, `ERROR ${e} (try ${i + 1})`);
          if (i >= 4) throw e;
          await new Promise((r) => setTimeout(r, 300));
        }
      }
    }
    const imgs = [...document.images];
    await Promise.all(imgs.map((i) => i.decode().catch((e) => log('image.decode', i.src, 'ERROR ' + e))));
    log('player.ready', { images: imgs.length, scenes: D.scenes.length, lines: D.lines.length, total: D.total }, 'ok');
  }

  // ---------- 埋め込み動画 ----------
  // 再生開始時刻。data-start="after" はその段階を出したセリフの終了後（build.py の CLIP_AFTER_DELAY と同じ 0.3 秒後）
  function clipStart(sc, c) {
    if (c.after) { const e = sc.steps_end && sc.steps_end[String(c.step)]; if (e !== undefined) return e + 0.3; }
    return stepTime(sc, c.step);
  }
  function clipLocal(sc, c, t) {
    const v = c.el;
    return Math.min(Math.max(t - clipStart(sc, c), 0), Math.max(0, (v.duration || 0) - 0.04));
  }
  function nearScene(sc, t) { return t >= sc.start - 0.5 && t <= sc.end + 0.5; }
  // 描画時: 1コマごとに再生位置を合わせ、シークの完了と再描画を待つ
  async function seekClips(t) {
    const waits = [];
    for (const sc of D.scenes) {
      if (!nearScene(sc, t)) continue;
      for (const c of sc._clips) {
        const lt = clipLocal(sc, c, t);
        if (Math.abs(c.el.currentTime - lt) > 0.001) {
          waits.push(new Promise((r) => c.el.addEventListener('seeked', r, { once: true })));
          c.el.currentTime = lt;
        }
      }
    }
    if (waits.length) {
      await Promise.all(waits);
      await new Promise((r) => requestAnimationFrame(() => r()));
    }
  }
  // プレビュー時: 再生中はそのまま流し、ずれたときだけ合わせる
  function syncClips(t, playing) {
    for (const sc of D.scenes) {
      for (const c of sc._clips) {
        const v = c.el, t0 = clipStart(sc, c);
        const inRange = nearScene(sc, t) && t >= t0 && t < t0 + (v.duration || 0);
        const lt = clipLocal(sc, c, t);
        if (playing && inRange) {
          if (v.paused) { v.currentTime = lt; v.play().catch(() => {}); }
          else if (Math.abs(v.currentTime - lt) > 0.25) v.currentTime = lt;
        } else {
          if (!v.paused) v.pause();
          if (Math.abs(v.currentTime - lt) > 0.05) v.currentTime = lt;
        }
      }
    }
  }
  async function clipsReady() {
    await Promise.all(D.scenes.flatMap((sc) => sc._clips.map((c) => c.loading)));
    const all = D.scenes.flatMap((sc) => sc._clips.map((c) => c.el));
    await Promise.all(all.map((v) => (v.readyState >= 2 ? null : new Promise((res) => {
      v.addEventListener('loadeddata', res, { once: true });
      v.addEventListener('error', () => { log('clip.error', v.dataset.clip, String(v.error && v.error.code)); res(); }, { once: true });
    }))));
    if (all.length) log('clip.ready', { clips: all.map((v) => [v.dataset.clip, v.duration]) }, 'ok');
  }

  window.__seek = async (t) => { update(t); if (RENDER) await seekClips(t); return true; };
  window.__ready = ready().then(clipsReady).then(() => { update(0); return true; });
  window.__total = D.total;

  if (RENDER) return;

  // ---------- プレビュー（ブラウザで音声つき再生） ----------
  const audio = $('#audio'), seek = $('#seek'), timeEl = $('#time'), playBtn = $('#play');
  audio.src = 'audio.wav'; // 描画時は読み込まない（大きな wav の先読みが他の読み込みを妨げるため）
  seek.max = D.total;
  const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  function fit() {
    const vp = $('#viewport').getBoundingClientRect();
    const k = Math.min(vp.width / D.meta.width, vp.height / D.meta.height);
    stage.style.transform = `scale(${k})`;
  }
  window.addEventListener('resize', fit); fit();
  let playing = false;
  function tick() {
    const t = audio.currentTime;
    update(t); syncClips(t, playing); seek.value = t; timeEl.textContent = `${fmt(t)} / ${fmt(D.total)}`;
    if (playing) requestAnimationFrame(tick);
  }
  playBtn.onclick = () => {
    if (playing) { audio.pause(); playing = false; playBtn.textContent = '▶ 再生'; log('preview.pause', audio.currentTime); }
    else { audio.play(); playing = true; playBtn.textContent = '❚❚ 停止'; log('preview.play', audio.currentTime); tick(); }
  };
  seek.oninput = () => { audio.currentTime = +seek.value; update(+seek.value); syncClips(+seek.value, false); timeEl.textContent = `${fmt(+seek.value)} / ${fmt(D.total)}`; };
  audio.onended = () => { playing = false; playBtn.textContent = '▶ 再生'; log('preview.ended', D.total); };
  window.addEventListener('error', (e) => log('window.error', e.message, `${e.filename}:${e.lineno}`));
})();
