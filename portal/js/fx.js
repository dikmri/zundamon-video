// 見た目の動き（カーソル、スクロールでの出現、磁石ボタン、文字分割、時計）。
(function (ZA) {
  'use strict';

  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = matchMedia('(hover: hover) and (pointer: fine)');

  const lerp = (a, b, t) => a + (b - a) * t;

  /** 文字ごとに span で包む（見出しの登場アニメーション用）。 */
  function splitChars(el) {
    if (!el || el.dataset.split) return;
    const text = el.textContent;
    el.dataset.split = '1';
    el.setAttribute('aria-label', text);
    el.textContent = '';
    let i = 0;
    for (const ch of Array.from(text)) {
      const s = document.createElement('span');
      s.className = 'ch';
      s.setAttribute('aria-hidden', 'true');
      s.style.setProperty('--i', i++);
      s.textContent = ch === ' ' ? ' ' : ch;
      el.appendChild(s);
    }
  }

  let io;
  /** .reveal が画面に入ったら .is-in を付ける。 */
  function observeReveals(root = document) {
    if (!io) {
      io = new IntersectionObserver((entries) => {
        for (const e of entries) {
          if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); }
        }
      }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    }
    root.querySelectorAll('.reveal:not(.is-in)').forEach((el) => io.observe(el));
  }

  /** カーソルの後を追う輪。data-cursor="ラベル" の要素の上で広がる。 */
  function initCursor() {
    const el = document.querySelector('.cursor');
    if (!el || !finePointer.matches) return;
    const ring = el.querySelector('.cursor-ring');
    const label = el.querySelector('.cursor-label');
    let x = innerWidth / 2, y = innerHeight / 2, cx = x, cy = y, shown = false;
    addEventListener('pointermove', (e) => {
      x = e.clientX; y = e.clientY;
      if (!shown) { cx = x; cy = y; shown = true; el.classList.add('is-on'); }
      const t = e.target.closest?.('[data-cursor]');
      const mode = t ? t.dataset.cursor : '';
      if (el.dataset.mode !== mode) {
        el.dataset.mode = mode;
        label.textContent = mode;
      }
      el.classList.toggle('is-link', !t && !!e.target.closest?.('a, button, [role="button"], input, label, select, summary'));
    }, { passive: true });
    document.addEventListener('pointerleave', () => { el.classList.remove('is-on'); shown = false; });
    addEventListener('pointerdown', () => el.classList.add('is-down'));
    addEventListener('pointerup', () => el.classList.remove('is-down'));
    const tick = () => {
      const k = reduced.matches ? 1 : 0.2;
      cx = lerp(cx, x, k); cy = lerp(cy, y, k);
      ring.style.transform = `translate3d(${cx}px, ${cy}px, 0)`;
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  /** 画面を切り替えたときにカーソルの表示を戻す（要素が消えると pointer イベントが来ないため）。 */
  function resetCursor() {
    const el = document.querySelector('.cursor');
    if (!el) return;
    el.dataset.mode = '';
    el.classList.remove('is-link', 'is-down');
    const label = el.querySelector('.cursor-label');
    if (label) label.textContent = '';
  }

  /** 磁石のようにカーソルへ少し寄るボタン。 */
  function magnetize(root = document) {
    if (!finePointer.matches || reduced.matches) return;
    root.querySelectorAll('.magnetic:not([data-mag])').forEach((el) => {
      el.dataset.mag = '1';
      const inner = el.querySelector('.magnetic-inner') || el;
      el.addEventListener('pointermove', (e) => {
        const r = el.getBoundingClientRect();
        const dx = (e.clientX - (r.left + r.width / 2)) / r.width;
        const dy = (e.clientY - (r.top + r.height / 2)) / r.height;
        el.style.transform = `translate(${dx * 14}px, ${dy * 12}px)`;
        if (inner !== el) inner.style.transform = `translate(${dx * 8}px, ${dy * 6}px)`;
      });
      el.addEventListener('pointerleave', () => {
        el.style.transform = '';
        if (inner !== el) inner.style.transform = '';
      });
    });
  }

  function startClock(el) {
    if (!el) return;
    const fmt = new Intl.DateTimeFormat('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: 'Asia/Tokyo' });
    const tick = () => { el.textContent = `JST ${fmt.format(new Date())}`; };
    tick();
    setInterval(tick, 1000);
  }

  /** 数字を 0 から数え上げる。 */
  function countUp(el, to, { duration = 1400, format = (v) => String(Math.round(v)) } = {}) {
    if (reduced.matches) { el.textContent = format(to); return; }
    const t0 = performance.now();
    const step = (now) => {
      const p = Math.min(1, (now - t0) / duration);
      const e = 1 - Math.pow(1 - p, 4);
      el.textContent = format(to * e);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  /** 画面内にいる間だけ動画を再生する（ダイジェストのループ用）。 */
  let vio;
  function autoplayInView(video) {
    if (!vio) {
      vio = new IntersectionObserver((entries) => {
        for (const e of entries) {
          const v = e.target;
          if (e.isIntersecting && !reduced.matches) {
            if (v.preload === 'none') v.preload = 'auto';
            v.play().catch((err) => { if (err.name !== 'AbortError') v.dispatchEvent(new CustomEvent('za-play-error', { detail: err })); });
          } else v.pause();
        }
      }, { threshold: 0.15 });
    }
    vio.observe(video);
  }

  ZA.fx = { reduced, finePointer, lerp, splitChars, observeReveals, initCursor, resetCursor, magnetize, startClock, countUp, autoplayInView };
})(window.ZA = window.ZA || {});
