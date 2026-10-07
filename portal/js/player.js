// 自前のコントロールを持つ動画プレイヤー。
// シークバーは目次の区切りで分かれ、上に話者ごとの発話（誰がいつ話したか）を重ねて表示する。
(function (ZA) {
  'use strict';
  const { fmtTime, indexAt, clamp } = ZA.util;
  const { log, logError } = ZA.log;


  const RATES = [0.75, 1, 1.25, 1.5, 1.75, 2];
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* 保存できなくても再生は続ける */ } },
  };

  const icon = (id) => `<svg aria-hidden="true"><use href="#${id}"/></svg>`;

  function createPlayer(host, v, { startAt = 0, onTime = () => {}, onProgress = () => {}, onEnded = () => {} } = {}) {
    const total = v.duration;
    const el = document.createElement('div');
    el.className = 'player';
    el.tabIndex = -1;
    el.dataset.state = 'idle';
    const speakerKeys = Object.keys(v.cast);
    const laneOf = (who) => Math.max(0, speakerKeys.indexOf(who));
    const speech = v.lines.map((l) => `<rect x="${l.start}" y="${laneOf(l.who) * 6}" width="${Math.max(0.2, l.end - l.start)}" height="4" rx="0" fill="${v.cast[l.who]?.color || '#888'}"/>`).join('');
    const segs = v.toc.map((e, i) => {
      const left = (e.start / total) * 100, width = ((e.end - e.start) / total) * 100;
      return `<span class="pl-seg${e.kind === 'chapter' ? ' is-chapter' : ''}" data-i="${i}" style="left:${left}%;width:${width}%"><i></i></span>`;
    }).join('');

    el.innerHTML = `
      <video playsinline preload="metadata" poster="${v.poster}"></video>
      <div class="pl-shade" aria-hidden="true"></div>
      <button class="pl-big" type="button" aria-label="再生">
        <span class="pl-big-disc">${icon('i-play')}</span>
        <span class="pl-big-label">再生する<small class="mono">${fmtTime(total)}</small></span>
      </button>
      <div class="pl-osd" aria-hidden="true"></div>
      <div class="pl-spinner" aria-hidden="true"><svg><use href="#i-bean"/></svg></div>
      <div class="pl-ui">
        <div class="pl-scrub" role="slider" tabindex="0" aria-label="再生位置" aria-valuemin="0" aria-valuemax="${Math.round(total)}" aria-valuenow="0" aria-valuetext="0:00">
          <svg class="pl-speech" viewBox="0 0 ${total} 10" preserveAspectRatio="none" aria-hidden="true">${speech}</svg>
          <div class="pl-track">${segs}</div>
          <div class="pl-buffer" aria-hidden="true"></div>
          <div class="pl-head" aria-hidden="true"></div>
          <div class="pl-tip" aria-hidden="true">
            <div class="pl-tip-thumb"></div>
            <div class="pl-tip-text"><b></b><span class="mono"></span></div>
          </div>
        </div>
        <div class="pl-bar">
          <button class="pl-btn pl-play" type="button" aria-label="再生">${icon('i-play')}</button>
          <button class="pl-btn pl-back" type="button" aria-label="10秒戻る">${icon('i-back10')}</button>
          <button class="pl-btn pl-fwd" type="button" aria-label="10秒進む">${icon('i-fwd10')}</button>
          <div class="pl-vol">
            <button class="pl-btn pl-mute" type="button" aria-label="ミュート">${icon('i-vol')}</button>
            <input class="pl-volume" type="range" min="0" max="1" step="0.01" aria-label="音量">
          </div>
          <span class="pl-time mono"><span class="pl-cur">0:00</span><span class="pl-sep"> / </span><span class="pl-dur">${fmtTime(total)}</span></span>
          <span class="pl-chapter" aria-live="off"></span>
          <span class="pl-spacer"></span>
          <button class="pl-btn pl-rate mono" type="button" aria-label="再生速度">1×</button>
          <button class="pl-btn pl-pip" type="button" aria-label="ピクチャーインピクチャー">${icon('i-pip')}</button>
          <button class="pl-btn pl-fs" type="button" aria-label="全画面">${icon('i-full')}</button>
        </div>
      </div>`;
    host.appendChild(el);

    // 映像の色を背景ににじませる（小さなキャンバスに描いて CSS でぼかす）
    const ambient = document.createElement('canvas');
    ambient.className = 'pl-ambient';
    ambient.width = 48; ambient.height = 27;
    ambient.setAttribute('aria-hidden', 'true');
    host.insertBefore(ambient, el);
    const actx = ambient.getContext('2d', { willReadFrequently: false });
    const poster = new Image();
    poster.onload = () => actx.drawImage(poster, 0, 0, 48, 27);
    poster.src = v.poster;
    let ambientTimer = 0;
    const paintAmbient = () => { try { if (el.querySelector('video').readyState >= 2) actx.drawImage(el.querySelector('video'), 0, 0, 48, 27); } catch { /* 描けないフレームは飛ばす */ } };

    const $ = (s) => el.querySelector(s);
    const video = $('video');
    // iPhone・iPad・Mac の Safari（iOS の他のブラウザも中身は同じ）には HLS を渡す。
    // リリース添付の mp4 は種類不明（application/octet-stream）で返るため、Safari では再生できないことがある
    const ua = navigator.userAgent;
    const appleWebKit = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)
      || (/Safari\//.test(ua) && !/(Chrome|Chromium|CriOS|Edg|OPR|Firefox|FxiOS|Android)\//.test(ua));
    const canHls = video.canPlayType('application/vnd.apple.mpegurl');
    const useHls = !!(v.video.hls && appleWebKit && canHls);
    video.src = useHls ? v.video.hls : v.video.src;
    log('video.source', { id: v.id, kind: useHls ? 'hls' : 'mp4', appleWebKit, canHls });
    const scrub = $('.pl-scrub');
    const segEls = [...el.querySelectorAll('.pl-seg')];
    const segFill = segEls.map((s) => s.firstElementChild);
    const head = $('.pl-head');
    const tip = $('.pl-tip');
    const tipThumb = $('.pl-tip-thumb');
    const tipTitle = $('.pl-tip-text b');
    const tipTime = $('.pl-tip-text span');
    const cur = $('.pl-cur');
    const chapterEl = $('.pl-chapter');
    const buffer = $('.pl-buffer');
    const osd = $('.pl-osd');
    const volume = $('.pl-volume');
    const rateBtn = $('.pl-rate');

    if (!document.pictureInPictureEnabled) $('.pl-pip').hidden = true;
    const sp = v.sprite;
    const TIP_W = 192;
    const k = sp ? TIP_W / sp.w : 1;
    if (sp) {
      tipThumb.style.backgroundImage = `url("${sp.src}")`;
      tipThumb.style.backgroundSize = `${sp.cols * sp.w * k}px ${sp.rows * sp.h * k}px`;
      tipThumb.style.height = `${sp.h * k}px`;
    }

    // 音量と速度は前回の設定を引き継ぐ
    video.volume = clamp(store.get('za:volume', 0.9), 0, 1);
    video.muted = store.get('za:muted', false);
    video.playbackRate = store.get('za:rate', 1);
    volume.value = video.muted ? 0 : video.volume;

    let started = false, dragging = false, lastSegIdx = -2, lastTocIdx = -2, lastSaved = 0, raf = 0, idleTimer = 0;

    const setIcon = (btn, id) => { btn.querySelector('use').setAttribute('href', `#${id}`); };

    function render(t) {
      const p = clamp(t / total, 0, 1);
      head.style.left = `${p * 100}%`;
      const si = indexAt(v.toc, t);
      if (si !== lastSegIdx) {
        segFill.forEach((f, i) => { f.style.transform = i < si ? 'scaleX(1)' : 'scaleX(0)'; });
        segEls.forEach((s, i) => s.classList.toggle('is-current', i === si));
        lastSegIdx = si;
      }
      if (si >= 0) {
        const e = v.toc[si];
        segFill[si].style.transform = `scaleX(${clamp((t - e.start) / (e.end - e.start), 0, 1)})`;
      }
      cur.textContent = fmtTime(t);
      scrub.setAttribute('aria-valuenow', String(Math.round(t)));
      scrub.setAttribute('aria-valuetext', fmtTime(t));
      if (si !== lastTocIdx) {
        lastTocIdx = si;
        const e = v.toc[si];
        chapterEl.textContent = e ? (e.num ? `${e.num}　${e.title}` : e.title) : '';
      }
      onTime(t);
      if (Math.abs(t - lastSaved) > 3) { lastSaved = t; onProgress(t, total); }
    }

    function loop() {
      if (!dragging) render(video.currentTime);
      raf = video.paused ? 0 : requestAnimationFrame(loop);
    }

    function updateBuffer() {
      const b = video.buffered;
      if (!b.length) return;
      let end = 0;
      for (let i = 0; i < b.length; i++) if (b.start(i) <= video.currentTime + 0.5) end = Math.max(end, b.end(i));
      buffer.style.transform = `scaleX(${clamp(end / total, 0, 1)})`;
    }

    let osdTimer = 0;
    function flash(html) {
      osd.innerHTML = html;
      osd.classList.remove('is-on');
      void osd.offsetWidth;
      osd.classList.add('is-on');
      clearTimeout(osdTimer);
      osdTimer = setTimeout(() => osd.classList.remove('is-on'), 650);
    }

    function play() {
      const p = video.play();
      if (p) p.catch((err) => { if (err.name !== 'AbortError') logError('video.play.rejected', err, { id: v.id }); });
    }
    const toggle = () => (video.paused ? play() : video.pause());

    function seek(t, why = 'seek') {
      const to = clamp(t, 0, Math.max(0, total - 0.05));
      log('video.seek', { id: v.id, from: +video.currentTime.toFixed(2), to: +to.toFixed(2), why });
      video.currentTime = to;
      render(to);
    }

    function setRate(r) {
      video.playbackRate = r;
      store.set('za:rate', r);
      rateBtn.textContent = `${r}×`;
      flash(`<b class="mono">${r}×</b>`);
    }

    function setVolume(val) {
      video.volume = clamp(val, 0, 1);
      video.muted = video.volume === 0;
      volume.value = video.muted ? 0 : video.volume;
    }

    // --- 動画のイベント ---
    video.addEventListener('loadedmetadata', () => log('video.loadedmetadata', { id: v.id, duration: +video.duration.toFixed(2), w: video.videoWidth, h: video.videoHeight }));
    video.addEventListener('play', () => {
      started = true;
      el.dataset.state = 'playing';
      setIcon($('.pl-play'), 'i-pause');
      $('.pl-play').setAttribute('aria-label', '一時停止');
      log('video.play', { id: v.id, t: +video.currentTime.toFixed(2), rate: video.playbackRate });
      if (!raf) raf = requestAnimationFrame(loop);
      clearInterval(ambientTimer);
      ambientTimer = setInterval(paintAmbient, 200);
      armIdle();
    });
    video.addEventListener('pause', () => {
      el.dataset.state = started ? 'paused' : 'idle';
      setIcon($('.pl-play'), 'i-play');
      $('.pl-play').setAttribute('aria-label', '再生');
      clearInterval(ambientTimer);
      paintAmbient();
      log('video.pause', { id: v.id, t: +video.currentTime.toFixed(2) });
      onProgress(video.currentTime, total);
      el.classList.remove('is-idle');
    });
    video.addEventListener('seeked', () => { render(video.currentTime); updateBuffer(); if (video.paused) paintAmbient(); });
    video.addEventListener('progress', updateBuffer);
    video.addEventListener('waiting', () => { el.classList.add('is-waiting'); log('video.waiting', { id: v.id, t: +video.currentTime.toFixed(2) }); });
    video.addEventListener('playing', () => el.classList.remove('is-waiting'));
    video.addEventListener('canplay', () => el.classList.remove('is-waiting'));
    video.addEventListener('ended', () => {
      log('video.ended', { id: v.id });
      onProgress(total, total);
      onEnded();
    });
    let fellBack = false;
    video.addEventListener('error', () => {
      const e = video.error;
      log('video.error', { id: v.id, src: video.currentSrc, hls: useHls && !fellBack }, `ERROR code=${e?.code} ${e?.message || ''}`);
      // HLS で読めなかったら、今までの mp4 に切り替える（修正前より悪くならないように）
      if (useHls && !fellBack) {
        fellBack = true;
        const at = video.currentTime || startAt || 0;
        log('video.fallback', { id: v.id, from: 'hls', to: 'mp4', at: +at.toFixed(2) });
        video.src = v.video.src;
        video.load();
        if (at > 0) video.addEventListener('loadedmetadata', () => { video.currentTime = Math.min(at, total - 0.5); }, { once: true });
        if (started) play();
        return;
      }
      el.classList.add('is-error');
      // ボタンの中にリンクは置けないので、案内はボタンと差し替える
      const msg = document.createElement('div');
      msg.className = 'pl-big';
      msg.setAttribute('role', 'alert');
      msg.innerHTML = `<span class="pl-big-disc" aria-hidden="true"><b style="font:900 34px/1 var(--f-display)">!</b></span>
        <span class="pl-big-label">${ZA.log.PUBLIC ? 'この端末では動画を再生できませんでした' : '動画を読み込めませんでした'}
        <small class="mono">code ${e?.code ?? '?'}${ZA.log.PUBLIC ? ' · <a href="check.html" style="text-decoration:underline">再生の確認ページへ</a>' : ' · logs/portal.log を確認'}</small></span>`;
      $('.pl-big')?.replaceWith(msg);
    });
    let volTimer = 0;
    video.addEventListener('volumechange', () => {
      setIcon($('.pl-mute'), video.muted || video.volume === 0 ? 'i-mute' : 'i-vol');
      store.set('za:volume', video.volume);
      store.set('za:muted', video.muted);
      clearTimeout(volTimer);
      volTimer = setTimeout(() => log('video.volume', { id: v.id, volume: +video.volume.toFixed(2), muted: video.muted }), 600);
    });
    video.addEventListener('ratechange', () => log('video.rate', { id: v.id, rate: video.playbackRate }));

    // --- 操作 ---
    $('.pl-big').addEventListener('click', () => { log('ui.player.bigplay', { id: v.id }); play(); });
    $('.pl-play').addEventListener('click', toggle);
    $('.pl-back').addEventListener('click', () => { seek(video.currentTime - 10, 'button'); flash('<b class="mono">−10s</b>'); });
    $('.pl-fwd').addEventListener('click', () => { seek(video.currentTime + 10, 'button'); flash('<b class="mono">+10s</b>'); });
    $('.pl-mute').addEventListener('click', () => {
      if (video.muted || video.volume === 0) setVolume(store.get('za:volume', 0.9) || 0.9); else video.muted = true;
      volume.value = video.muted ? 0 : video.volume;
    });
    volume.addEventListener('input', () => setVolume(+volume.value));
    rateBtn.textContent = `${video.playbackRate}×`;
    rateBtn.addEventListener('click', () => setRate(RATES[(RATES.indexOf(video.playbackRate) + 1) % RATES.length] || 1));
    $('.pl-pip').addEventListener('click', async () => {
      try {
        if (document.pictureInPictureElement) await document.exitPictureInPicture();
        else await video.requestPictureInPicture();
        log('ui.player.pip', { id: v.id, on: !!document.pictureInPictureElement });
      } catch (err) { logError('ui.player.pip', err); }
    });
    // 全画面: iPhone の Safari は要素の全画面（Fullscreen API）に対応しておらず、<video> を標準のプレーヤーで
    // 全画面にする webkitEnterFullscreen だけが使える。それ以外（Android・iPad・PC）は自前のプレイヤーごと全画面にする
    const fsBtn = $('.pl-fs');
    const isIPhone = /iPhone|iPod/.test(ua);
    const requestFs = el.requestFullscreen || el.webkitRequestFullscreen;
    const canVideoFs = typeof video.webkitEnterFullscreen === 'function';
    const fsMethod = isIPhone && canVideoFs ? 'video' : requestFs ? 'element' : canVideoFs ? 'video' : 'none';
    if (fsMethod === 'none') fsBtn.hidden = true;
    const fsElement = () => document.fullscreenElement || document.webkitFullscreenElement || null;
    const coarse = matchMedia('(pointer: coarse)').matches;
    fsBtn.addEventListener('click', () => toggleFullscreen());

    function enterVideoFullscreen() {
      try {
        video.webkitEnterFullscreen();
        log('ui.player.fullscreen', { id: v.id, method: 'video', readyState: video.readyState });
      } catch (err) {
        logError('ui.player.fullscreen', err, { id: v.id, method: 'video', readyState: video.readyState });
      }
    }

    function lockLandscape() {
      // スマホは横向きで見る想定。固定できるのは Android の Chrome などで、全画面のあいだだけ
      const o = screen.orientation;
      if (!coarse || !o || typeof o.lock !== 'function') return;
      o.lock('landscape').then(
        () => log('ui.player.orientation', { id: v.id, lock: 'landscape' }),
        (err) => log('ui.player.orientation', { id: v.id, lock: 'landscape' }, `skip ${err.name}`),
      );
    }

    function toggleFullscreen() {
      if (fsElement()) {
        const exit = document.exitFullscreen || document.webkitExitFullscreen;
        Promise.resolve(exit && exit.call(document)).catch((err) => logError('ui.player.fullscreen.exit', err));
        return;
      }
      if (fsMethod === 'video') { enterVideoFullscreen(); return; }
      if (fsMethod === 'element') {
        let p;
        try { p = requestFs.call(el, { navigationUI: 'hide' }); } catch (err) { p = Promise.reject(err); }
        Promise.resolve(p).then(lockLandscape, (err) => {
          logError('ui.player.fullscreen', err, { id: v.id, method: 'element' });
          if (canVideoFs) enterVideoFullscreen();
        });
      }
    }
    const onFs = () => {
      const on = fsElement() === el;
      setIcon(fsBtn, on ? 'i-unfull' : 'i-full');
      el.classList.toggle('is-fullscreen', on);
      if (!on && screen.orientation && typeof screen.orientation.unlock === 'function') {
        try { screen.orientation.unlock(); } catch { /* 固定していなければ何もしない */ }
      }
      log('ui.player.fullscreen', { id: v.id, method: 'element', on });
    };
    document.addEventListener('fullscreenchange', onFs);
    document.addEventListener('webkitfullscreenchange', onFs);
    // iPhone の標準プレーヤーの全画面。閉じたら自前の表示を今の再生位置に合わせる
    video.addEventListener('webkitbeginfullscreen', () => log('ui.player.fullscreen', { id: v.id, method: 'video', on: true }));
    video.addEventListener('webkitendfullscreen', () => {
      render(video.currentTime);
      if (!video.paused && !raf) raf = requestAnimationFrame(loop);
      log('ui.player.fullscreen', { id: v.id, method: 'video', on: false, t: +video.currentTime.toFixed(2) });
    });

    // スマホでは、操作パネルが隠れているときのタップはパネルを出すだけにする（一時停止しない）
    let tapWhileIdle = false;
    video.addEventListener('click', () => {
      if (!started) { play(); return; }
      if (coarse && tapWhileIdle) return;
      toggle();
    });
    video.addEventListener('dblclick', toggleFullscreen);

    // シークバー: ドラッグとホバー時のサムネイル
    const timeAt = (clientX) => {
      const r = scrub.getBoundingClientRect();
      return clamp((clientX - r.left) / r.width, 0, 1) * total;
    };
    function showTip(clientX) {
      const r = scrub.getBoundingClientRect();
      const t = timeAt(clientX);
      const x = clamp(clientX - r.left, TIP_W / 2 + 6, r.width - TIP_W / 2 - 6);
      tip.style.left = `${x}px`;
      const e = v.toc[indexAt(v.toc, t)];
      tipTitle.textContent = e ? (e.num ? `${e.num} ${e.title}` : e.title) : '';
      tipTime.textContent = fmtTime(t);
      if (sp) {
        const i = Math.min(sp.count - 1, Math.floor(t / sp.interval));
        tipThumb.style.backgroundPosition = `${-(i % sp.cols) * sp.w * k}px ${-Math.floor(i / sp.cols) * sp.h * k}px`;
      }
      scrub.style.setProperty('--hover', `${(t / total) * 100}%`);
    }
    scrub.addEventListener('pointermove', (e) => { showTip(e.clientX); if (dragging) render(timeAt(e.clientX)); });
    scrub.addEventListener('pointerenter', () => scrub.classList.add('is-hover'));
    scrub.addEventListener('pointerleave', () => { if (!dragging) scrub.classList.remove('is-hover'); });
    scrub.addEventListener('pointerdown', (e) => {
      dragging = true;
      scrub.setPointerCapture(e.pointerId);
      scrub.classList.add('is-drag', 'is-hover');
      showTip(e.clientX);
      render(timeAt(e.clientX));
    });
    const endDrag = (e) => {
      if (!dragging) return;
      dragging = false;
      scrub.classList.remove('is-drag');
      if (e.type === 'pointerup') seek(timeAt(e.clientX), 'scrub');
      if (e.pointerType !== 'mouse') scrub.classList.remove('is-hover');
    };
    scrub.addEventListener('pointerup', endDrag);
    scrub.addEventListener('pointercancel', endDrag);
    scrub.addEventListener('keydown', (e) => {
      const d = { ArrowLeft: -5, ArrowRight: 5, PageDown: -30, PageUp: 30 }[e.key];
      if (d) { e.preventDefault(); e.stopPropagation(); seek(video.currentTime + d, 'key'); }
      if (e.key === 'Home') { e.preventDefault(); seek(0, 'key'); }
      if (e.key === 'End') { e.preventDefault(); seek(total - 1, 'key'); }
    });

    // 再生中に操作が止まったらコントロールを隠す
    function armIdle() {
      el.classList.remove('is-idle');
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => { if (!video.paused && !dragging) el.classList.add('is-idle'); }, 2600);
    }
    el.addEventListener('pointermove', (e) => { if (e.pointerType === 'mouse') armIdle(); });
    el.addEventListener('pointerdown', () => { tapWhileIdle = el.classList.contains('is-idle'); armIdle(); });
    el.addEventListener('focusin', armIdle);

    function chapterJump(dir) {
      const t = video.currentTime;
      const marks = v.toc.filter((e) => e.kind !== 'scene' || !v.toc.some((x) => x.kind === 'chapter')).map((e) => e.start);
      const list = marks.length > 1 ? marks : v.toc.map((e) => e.start);
      const target = dir > 0 ? list.find((s) => s > t + 0.5) : [...list].reverse().find((s) => s < t - 2);
      if (target !== undefined) seek(target, dir > 0 ? 'next-chapter' : 'prev-chapter');
      else if (dir < 0) seek(0, 'prev-chapter');
    }

    /** ページ全体のキー操作（入力欄にいるときは呼ばれない）。処理したら true。 */
    function handleKey(e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return false;
      const k = e.key;
      if (k === ' ' || k === 'k' || k === 'K') { toggle(); flash(icon(video.paused ? 'i-pause' : 'i-play')); }
      else if (k === 'j' || k === 'J') { seek(video.currentTime - 10, 'key'); flash('<b class="mono">−10s</b>'); }
      else if (k === 'l' || k === 'L') { seek(video.currentTime + 10, 'key'); flash('<b class="mono">+10s</b>'); }
      else if (k === 'ArrowLeft') { seek(video.currentTime - 5, 'key'); flash('<b class="mono">−5s</b>'); }
      else if (k === 'ArrowRight') { seek(video.currentTime + 5, 'key'); flash('<b class="mono">+5s</b>'); }
      else if (k === 'ArrowUp') { setVolume(video.volume + 0.05); flash(`<b class="mono">音量 ${Math.round(video.volume * 100)}%</b>`); }
      else if (k === 'ArrowDown') { setVolume(video.volume - 0.05); flash(`<b class="mono">音量 ${Math.round(video.volume * 100)}%</b>`); }
      else if (k === 'm' || k === 'M') { video.muted = !video.muted; flash(icon(video.muted ? 'i-mute' : 'i-vol')); }
      else if (k === 'f' || k === 'F') toggleFullscreen();
      else if (k === 'n' || k === 'N') chapterJump(1);
      else if (k === 'p' || k === 'P') chapterJump(-1);
      else if (k === '>' || k === '.' && e.shiftKey) setRate(RATES[Math.min(RATES.length - 1, RATES.indexOf(video.playbackRate) + 1)] || 1);
      else if (k === '<' || k === ',' && e.shiftKey) setRate(RATES[Math.max(0, RATES.indexOf(video.playbackRate) - 1)] || 1);
      else if (/^[0-9]$/.test(k)) seek((+k / 10) * total, 'key-percent');
      else return false;
      e.preventDefault();
      armIdle();
      return true;
    }

    if (startAt > 0) {
      video.addEventListener('loadedmetadata', () => { video.currentTime = Math.min(startAt, total - 0.5); render(video.currentTime); }, { once: true });
    }
    render(startAt || 0);

    function destroy() {
      cancelAnimationFrame(raf);
      clearTimeout(idleTimer);
      clearInterval(ambientTimer);
      ambient.remove();
      document.removeEventListener('fullscreenchange', onFs);
      document.removeEventListener('webkitfullscreenchange', onFs);
      if (!video.paused) onProgress(video.currentTime, total);
      video.pause();
      video.removeAttribute('src');
      video.load();
      el.remove();
    }

    return { el, video, play, pause: () => video.pause(), seek, handleKey, destroy, flash, get time() { return video.currentTime; } };
  }

  ZA.player = { createPlayer };
})(window.ZA = window.ZA || {});
