// Zunda Archive — 一覧と視聴ページの描画、ルーティング、各種操作。
(function (ZA) {
  'use strict';
  const {
    fmtTime, fmtDate, fmtBytes, escapeHtml: h, highlight, inlineMd, searchCatalog, indexAt, aggregateCredits, sampleQuotes, clamp,
    splitCredit, phraseHtml: ph,
  } = ZA.util;
  const { log, logError, installGlobalHandlers } = ZA.log;
  const { createPlayer } = ZA.player;
  const {
    splitChars, observeReveals, initCursor, resetCursor, magnetize, startClock, countUp, autoplayInView, reduced, finePointer, lerp,
  } = ZA.fx;

  installGlobalHandlers();

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const icon = (id, cls = '') => `<svg class="${cls}" aria-hidden="true"><use href="#${id}"/></svg>`;
  const pad = (n) => String(n).padStart(2, '0');

  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* 保存できない環境でも表示は続ける */ } },
  };

  const state = {
    catalog: null,
    videos: [],          // no の昇順
    route: null,
    player: null,
    cleanup: [],
    indexScroll: 0,
    q: '',
    series: store.get('za:series', 'all'),
    sort: store.get('za:sort', 'new'),
    layout: store.get('za:layout', 'list'),
    theater: store.get('za:theater', false),
  };

  function setTheater(on) {
    state.theater = on;
    store.set('za:theater', on);
    $('.watch')?.classList.toggle('is-theater', on);
    $$('[data-theater]').forEach((b) => b.setAttribute('aria-pressed', String(on)));
    log('ui.theater', { on });
  }

  const progress = {
    all() { return store.get('za:progress', {}); },
    get(id) { return this.all()[id]; },
    set(id, t, d) {
      const all = this.all();
      const prev = all[id] || {};
      all[id] = { t: Math.round(t * 10) / 10, d, at: Date.now(), done: prev.done || t >= d * 0.95 };
      store.set('za:progress', all);
    },
  };

  const view = $('#view');
  /** ダイジェスト等の再生。自動再生の制限による失敗はログに残す（中断による AbortError は正常）。 */
  function tryPlay(video, where) {
    const p = video.play();
    if (p) p.catch((err) => { if (err.name !== 'AbortError') logError('preview.play', err, { where, src: video.currentSrc }); });
  }

  const viewTransition = (fn) => {
    if (document.startViewTransition && !reduced.matches && document.visibilityState === 'visible') {
      const vt = document.startViewTransition(fn);
      // 別の遷移が始まった・タブが隠れた等で中断されると reject される。表示の更新自体は済んでいる
      vt.ready.catch((err) => log('viewtransition.skipped', null, `${err.name}: ${err.message}`));
      vt.finished.catch(() => {});
      return vt;
    }
    fn();
    return null;
  };

  // ---------------------------------------------------------------- 共通の部品

  function displayTitle(v, cls = '') {
    if (!v.display?.length) return `<span class="${cls}">${ph(v.title)}</span>`;
    return v.display.map((line) => `<span class="dt-line ${cls}">${line.map((s) => (s.accent ? `<span class="accent">${ph(s.t)}</span>` : ph(s.t))).join('<wbr>')}</span>`).join('');
  }

  function barcode(v, cls = 'barcode') {
    const keys = Object.keys(v.cast);
    const lanes = Math.max(1, keys.length);
    const lh = 10 / lanes;
    const rects = v.lines.map((l) => {
      const lane = Math.max(0, keys.indexOf(l.who));
      return `<rect x="${l.start.toFixed(2)}" y="${(lane * lh + lh * 0.12).toFixed(2)}" width="${Math.max(0.35, l.end - l.start).toFixed(2)}" height="${(lh * 0.76).toFixed(2)}" fill="${v.cast[l.who]?.color || '#888'}"/>`;
    }).join('');
    const ticks = v.toc.filter((e) => e.kind === 'chapter').map((e) => `<rect x="${e.start.toFixed(2)}" y="0" width="${(v.duration / 500).toFixed(2)}" height="10" class="bc-tick"/>`).join('');
    return `<svg class="${cls}" viewBox="0 0 ${v.duration.toFixed(2)} 10" preserveAspectRatio="none" role="img" aria-label="会話の流れ（上下の段が話者、横が時間）">${ticks}${rects}</svg>`;
  }

  function castLegend(v) {
    return Object.values(v.cast).map((c) => `<span class="legend-item"><i style="--c:${c.color}"></i>${h(c.name)}</span>`).join('');
  }

  function chapterEntries(v) {
    const ch = v.toc.filter((e) => e.kind === 'chapter');
    return ch.length ? ch : v.toc.filter((e) => e.kind === 'scene');
  }

  const INITIALS = { zundamon: 'ず', metan: 'め' };
  const initial = (key, c) => INITIALS[key] || (c?.name || key || '?').slice(0, 1);

  const watchHref = (v, t) => `#/watch/${encodeURIComponent(v.id)}${t ? `?t=${Math.floor(t)}` : ''}`;

  let toastTimer = 0;
  function toast(msg) {
    const el = $('.toast');
    el.textContent = msg;
    el.classList.add('is-on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('is-on'), 2600);
  }

  function totals() {
    const vs = state.videos;
    const cast = state.catalog.cast || {};
    const z = cast.zundamon;
    return {
      videos: vs.length,
      runtime: vs.reduce((a, v) => a + v.duration, 0),
      lines: vs.reduce((a, v) => a + v.lines.length, 0),
      noda: z?.ending?.[0] === 'のだ' ? z.ending[1] : vs.reduce((a, v) => a + v.lines.filter((l) => l.text.includes('のだ')).length, 0),
    };
  }

  // ---------------------------------------------------------------- 一覧ページ

  function heroHTML(latest, t) {
    return `
    <section class="hero" aria-labelledby="hero-title">
      <div class="hero-meta mono">
        <span>(${PUBLIC ? 'Archive' : 'Personal Archive'})</span>
        <span class="hide-sm">ずんだもん解説動画のアーカイブ</span>
        <span>Vol.${pad(t.videos)} — ${new Date().getFullYear()}</span>
      </div>
      <h1 class="wordmark" id="hero-title" aria-label="Zunda Archive">
        <span class="wm-line wm-1">
          <span class="wm-word" data-split>Zunda</span>
          ${latest ? `<a class="wm-pill" href="${watchHref(latest)}" data-cursor="再生" data-vt aria-label="最新の動画「${h(latest.title)}」を見る">
            <video muted loop playsinline preload="auto" poster="${latest.poster}" src="${latest.preview}"></video>
            <span class="wm-pill-tag mono"><i></i>Now showing · No.${pad(latest.no)}</span>
          </a>` : ''}
        </span>
        <span class="wm-line wm-2">
          <span class="wm-note">ずんだもんと四国めたんが、<br>なんでも解説するのだ。</span>
          <span class="wm-word wm-serif" data-split>Archive</span><span class="wm-star" aria-hidden="true">✳</span>
        </span>
      </h1>
      <div class="hero-foot">
        <dl class="stats">
          <div class="stat"><dt class="mono">Videos</dt><dd data-count="${t.videos}" data-fmt="pad">${pad(t.videos)}</dd></div>
          <div class="stat"><dt class="mono">Runtime</dt><dd data-count="${Math.round(t.runtime)}" data-fmt="time">${fmtTime(t.runtime)}</dd></div>
          <div class="stat"><dt class="mono">Lines</dt><dd data-count="${t.lines}">${t.lines}</dd></div>
          <div class="stat"><dt class="mono">「のだ」</dt><dd data-count="${t.noda}">${t.noda}</dd></div>
        </dl>
        <a class="hero-scroll mono" href="#/" data-jump="latest"><span>Scroll</span><i></i></a>
      </div>
    </section>`;
  }

  function tapesHTML() {
    const vs = state.videos;
    const seed = Math.floor(Date.now() / 86400000);
    const tape = (who) => {
      const c = state.catalog.cast?.[who];
      if (!c) return '';
      const qs = sampleQuotes(vs, who, 14, seed + who.length);
      if (!qs.length) return '';
      const items = qs.map(({ video, line }) => `
        <a class="tape-item" href="${watchHref(video, line.start)}" data-quote="${h(video.id)}" data-cursor="聞く">
          <span class="tape-who">${h(initial(who, c))}</span>「${h(line.text)}」<span class="tape-at mono">No.${pad(video.no)} · ${fmtTime(line.start)}</span>
        </a><span class="tape-sep" aria-hidden="true">✳</span>`).join('');
      return `<div class="tape tape-${h(who)}" style="--tc:${c.color}"><div class="tape-inner"><div class="tape-run">${items}</div><div class="tape-run" aria-hidden="true">${items}</div></div></div>`;
    };
    return `<section class="tapes" aria-label="セリフの抜粋（押すとその場面から再生）">${tape('zundamon')}${tape('metan')}</section>`;
  }

  function latestHTML(v) {
    if (!v) return '';
    const chapters = chapterEntries(v).slice(0, 7);
    return `
    <section class="sec latest" id="latest" aria-labelledby="latest-title">
      <header class="sec-head reveal"><span class="sec-no mono">(01)</span><h2 class="sec-title" id="latest-title">Latest</h2><p class="sec-note">いちばん新しい動画</p></header>
      <article class="feature">
        <a class="feature-media reveal" href="${watchHref(v)}" data-cursor="再生" data-vt aria-label="「${h(v.title)}」を見る">
          <img src="${v.poster}" alt="" loading="lazy" decoding="async" width="1280" height="720">
          <video muted loop playsinline preload="none" src="${v.preview}"></video>
          <span class="feature-badge mono">New · No.${pad(v.no)}</span>
          <span class="feature-dur mono">${fmtTime(v.duration)}</span>
          <span class="feature-play" aria-hidden="true">${icon('i-play')}</span>
        </a>
        <div class="feature-body">
          <p class="eyebrow mono reveal">${h(v.series || v.kicker)}</p>
          <h3 class="feature-title ph reveal">${displayTitle(v)}</h3>
          ${v.lede ? `<p class="feature-lede reveal">${h(v.lede).replace(/\n/g, '<br>')}</p>` : ''}
          <ol class="feature-toc reveal">
            ${chapters.map((e) => `<li><a href="${watchHref(v, e.start)}"><span class="ft-num mono">${h(e.num || '—')}</span><span class="ft-title ph">${ph(e.title)}</span><span class="ft-time mono">${fmtTime(e.start)}</span></a></li>`).join('')}
          </ol>
          <div class="convo reveal">
            ${barcode(v)}
            <div class="convo-legend mono">${castLegend(v)}<span class="legend-note">会話の流れ</span></div>
          </div>
          <a class="btn btn-primary magnetic reveal" href="${watchHref(v)}" data-vt-from=".feature-media"><span class="magnetic-inner">${icon('i-play')}再生する<small class="mono">${fmtTime(v.duration)}</small></span></a>
        </div>
      </article>
    </section>`;
  }

  function archiveHTML() {
    const series = [...new Set(state.videos.map((v) => v.series).filter(Boolean))];
    const count = (s) => state.videos.filter((v) => v.series === s).length;
    if (state.series !== 'all' && !series.includes(state.series)) state.series = 'all';
    return `
    <section class="sec archive" id="index" aria-labelledby="index-title">
      <header class="sec-head reveal"><span class="sec-no mono">(02)</span><h2 class="sec-title" id="index-title">Index</h2><p class="sec-note">すべての動画</p></header>
      <div class="toolbar reveal">
        <label class="search">
          ${icon('i-search')}
          <span class="sr-only">タイトルやセリフで検索</span>
          <input type="search" id="q" placeholder="タイトルやセリフで探す（例: 停戦、プロンプト）" value="${h(state.q)}" autocomplete="off" enterkeyhint="search">
          <kbd class="mono" aria-hidden="true">/</kbd>
        </label>
        <div class="chips" role="group" aria-label="シリーズで絞り込む">
          <button type="button" class="chip" data-series="all" aria-pressed="${state.series === 'all'}">すべて<sup class="mono">${state.videos.length}</sup></button>
          ${series.map((s) => `<button type="button" class="chip" data-series="${h(s)}" aria-pressed="${state.series === s}">${h(s.replace(/（.*?）/g, ''))}<sup class="mono">${count(s)}</sup></button>`).join('')}
        </div>
        <div class="toolbar-right">
          <div class="seg" role="group" aria-label="並び順">
            ${[['new', '新しい順'], ['old', '古い順'], ['long', '長い順']].map(([k, l]) => `<button type="button" data-sort="${k}" aria-pressed="${state.sort === k}">${l}</button>`).join('')}
          </div>
          <div class="seg seg-icons" role="group" aria-label="表示">
            <button type="button" data-layout="list" aria-pressed="${state.layout === 'list'}" aria-label="リスト">${icon('i-list')}</button>
            <button type="button" data-layout="grid" aria-pressed="${state.layout === 'grid'}" aria-label="グリッド">${icon('i-grid')}</button>
          </div>
        </div>
      </div>
      <p class="result-note mono" aria-live="polite"></p>
      <ol class="rows" data-layout="${state.layout}"></ol>
    </section>`;
  }

  function rowHTML(r, q) {
    const v = r.video;
    const p = progress.get(v.id);
    const pct = p ? clamp(p.t / v.duration, 0, 1) : 0;
    const hits = r.lines.slice(0, 3).map((l) => `
      <li><a class="hit" href="${watchHref(v, l.start)}"><span class="hit-who" style="--c:${v.cast[l.who]?.color}">${h(initial(l.who, v.cast[l.who]))}</span><span class="hit-text">${highlight(l.text, q)}</span><span class="hit-time mono">${fmtTime(l.start)}</span></a></li>`).join('');
    const more = r.lines.length > 3 ? `<li class="hit-more mono">ほか ${r.lines.length - 3} 件のセリフ</li>` : '';
    return `
    <li class="row" data-id="${h(v.id)}" style="--pct:${pct}">
      <a class="row-link" href="${watchHref(v)}" data-cursor="再生" data-preview="${v.preview}" data-vt>
        <span class="row-no mono">${pad(v.no)}</span>
        <span class="row-thumb"><img src="${v.poster}" alt="" loading="lazy" decoding="async" width="1280" height="720"><video muted loop playsinline preload="none"></video></span>
        <span class="row-main">
          <span class="row-kicker mono">${h(v.series || v.kicker)}</span>
          <span class="row-title ph">${q ? highlight(v.title, q) : ph(v.title)}</span>
          <span class="row-bar">${barcode(v, 'barcode row-barcode')}</span>
        </span>
        <span class="row-meta mono">
          <span class="row-dur">${fmtTime(v.duration)}</span>
          <span class="row-date">${fmtDate(v.date)}</span>
          ${p?.done ? '<span class="row-state is-done">視聴済み</span>' : p && p.t > 5 ? `<span class="row-state">続き ${fmtTime(p.t)}</span>` : ''}
          ${!PUBLIC && v.published !== undefined ? `<span class="row-pub ${v.published ? 'is-on' : ''}">${v.published ? '公開中' : '未公開'}</span>` : ''}
        </span>
        <span class="row-arrow" aria-hidden="true">${icon('i-arrow')}</span>
        <span class="row-progress" aria-hidden="true"></span>
      </a>
      ${hits ? `<ul class="hits">${hits}${more}</ul>` : ''}
    </li>`;
  }

  function renderRows() {
    const list = $('.rows');
    if (!list) return;
    hideFloating();
    const q = state.q.trim();
    let rs = searchCatalog(state.videos, q);
    if (state.series !== 'all') rs = rs.filter((r) => r.video.series === state.series);
    const by = { new: (a, b) => b.video.no - a.video.no, old: (a, b) => a.video.no - b.video.no, long: (a, b) => b.video.duration - a.video.duration }[state.sort];
    rs.sort(by);
    list.dataset.layout = state.layout;
    list.innerHTML = rs.length ? rs.map((r) => rowHTML(r, q)).join('') : `<li class="empty"><p>「${h(q)}」は見つからなかったのだ…</p><button type="button" class="btn-ghost" data-clear>検索をクリア</button></li>`;
    const lineHits = rs.reduce((a, r) => a + r.lines.length, 0);
    $('.result-note').textContent = q ? `${rs.length} 本 · セリフ ${lineHits} 件` : `${rs.length} 本`;
    bindRowPreviews(list);
    return { videos: rs.length, lines: lineHits };
  }

  function voicesHTML() {
    const cast = state.catalog.cast || {};
    const order = ['zundamon', 'metan'].filter((k) => cast[k]).concat(Object.keys(cast).filter((k) => !['zundamon', 'metan'].includes(k)));
    if (!order.length) return '';
    const total = order.reduce((a, k) => a + cast[k].seconds, 0) || 1;
    const card = (k, i) => {
      const c = cast[k];
      const p = c.portrait || {};
      const en = { zundamon: 'Zundamon', metan: 'Shikoku Metan', zunko: 'Tohoku Zunko', kiritan: 'Tohoku Kiritan',
                   itako: 'Tohoku Itako' }[k] || k;
      return `
      <article class="voice voice-${h(k)}" style="--vc:${c.color}" data-who="${h(k)}">
        <div class="voice-stage">
          <span class="voice-bg-name" aria-hidden="true">${h(en)}</span>
          ${p.idle ? `<button type="button" class="voice-figure" data-cursor="しゃべる" aria-label="${h(c.name)}にしゃべってもらう">
            <img class="vf vf-idle" src="${p.idle}" alt="" decoding="async">
            <img class="vf vf-blink" src="${p.blink}" alt="" decoding="async">
            <img class="vf vf-talk" src="${p.talk}" alt="" decoding="async">
            <img class="vf vf-joy" src="${p.joy}" alt="" decoding="async">
          </button>` : ''}
          <figure class="voice-bubble" aria-live="polite"><blockquote></blockquote><figcaption class="mono"></figcaption></figure>
        </div>
        <div class="voice-body">
          <p class="voice-en mono">(${pad(i + 1)}) ${h(en)}</p>
          <h3 class="voice-name">${h(c.name)}</h3>
          <dl class="voice-stats">
            <div><dt class="mono">セリフ</dt><dd>${c.lines.toLocaleString()}</dd></div>
            <div><dt class="mono">話した時間</dt><dd>${fmtTime(c.seconds)}</dd></div>
            <div><dt class="mono">文字数</dt><dd>${c.chars.toLocaleString()}</dd></div>
            ${c.ending ? `<div><dt class="mono">口ぐせ</dt><dd>「${h(c.ending[0])}」<small>×${c.ending[1]}</small></dd></div>` : ''}
          </dl>
          <p class="voice-credit mono">${h(c.voice || '')}</p>
        </div>
      </article>`;
    };
    return `
    <section class="sec voices" id="voices" aria-labelledby="voices-title">
      <header class="sec-head reveal"><span class="sec-no mono">(03)</span><h2 class="sec-title" id="voices-title">Voices</h2><p class="sec-note">しゃべっている二人</p></header>
      <div class="voices-grid">${order.map(card).join('')}</div>
      <div class="share reveal">
        <p class="share-label mono">話した時間の割合（全${state.videos.length}本）</p>
        <div class="share-bar">${order.map((k) => {
          const pct = (cast[k].seconds / total) * 100;
          return `<span style="--vc:${cast[k].color};flex-basis:${pct}%"><b>${h(cast[k].name)}</b><em class="mono">${pct.toFixed(0)}%</em></span>`;
        }).join('')}</div>
      </div>
    </section>`;
  }

  function footerHTML() {
    const credits = aggregateCredits(state.videos).filter(([k]) => !/^(情報|出典)$/.test(k));
    return `
    <footer class="footer" id="credits" aria-labelledby="credits-title">
      <div class="footer-inner">
        <header class="sec-head reveal"><span class="sec-no mono">(04)</span><h2 class="sec-title" id="credits-title">Credits</h2><p class="sec-note">素材と声</p></header>
        <dl class="credits">
          ${credits.map(([k, vals]) => `<div><dt class="mono">${h(k)}</dt><dd>${vals.map((x) => h(x.replace(/^音楽：/, ''))).join('<br>')}</dd></div>`).join('')}
          <div><dt class="mono">制作</dt><dd><a href="https://github.com/dikmri/zundamon-video" target="_blank" rel="noopener">zundamon-video</a>（Claude Code スキル）</dd></div>
        </dl>
        <div class="footer-actions">
          ${PUBLIC ? '' : `<button type="button" class="btn-ghost" data-rescan>${icon('i-refresh')}カタログを読み直す</button>`}
          ${ZA.log.FILE_MODE && !PUBLIC ? `<button type="button" class="btn-ghost" data-export-log>${icon('i-download')}ログを書き出す</button>` : ''}
          ${!PUBLIC && state.catalog.site?.url ? `<a class="btn-ghost" href="${h(state.catalog.site.url)}" target="_blank" rel="noopener">${icon('i-link')}公開サイトを開く</a>` : ''}
          <button type="button" class="btn-ghost" data-keys><kbd class="mono">?</kbd>キーボード操作</button>
        </div>
      </div>
      <div class="footer-bottom mono">
        <span>© ${new Date().getFullYear()} Zunda Archive${PUBLIC ? '' : ' — 手元のポータル'}</span>
        <span>${PUBLIC ? '更新' : 'カタログ更新'} ${h((state.catalog.generated || '').replace('T', ' ').slice(0, 16))}</span>
      </div>
      <div class="footer-giant" aria-hidden="true"><span>なのだ。</span></div>
    </footer>`;
  }

  function renderIndex(route) {
    const latest = state.videos[state.videos.length - 1];
    const t = totals();
    document.title = 'Zunda Archive — ずんだもん解説動画アーカイブ';
    if (!state.videos.length) {
      view.innerHTML = `${heroHTML(null, t)}<section class="sec empty-all"><p>まだ動画がないのだ。</p><p class="mono">uv run python -m zvideo render projects/&lt;名前&gt;/script.json</p><p>で書き出してから、下の「カタログを更新」を押してほしいのだ。</p></section>${footerHTML()}`;
    } else {
      view.innerHTML = heroHTML(latest, t) + tapesHTML() + latestHTML(latest) + archiveHTML() + voicesHTML() + footerHTML();
    }
    $$('[data-split], .sec-title', view).forEach(splitChars);
    renderRows();
    bindIndex();
    observeReveals(view);
    magnetize(view);
    $$('.wm-pill video', view).forEach((v) => {
      v.addEventListener('za-play-error', (e) => logError('preview.play', e.detail, { where: 'hero', src: v.currentSrc }));
      autoplayInView(v);
    });
    // 数字は画面に入ったときに数え上げる
    const statIO = new IntersectionObserver((es) => es.forEach((e) => {
      if (!e.isIntersecting) return;
      statIO.unobserve(e.target);
      const to = +e.target.dataset.count;
      const f = e.target.dataset.fmt;
      countUp(e.target, to, { format: f === 'time' ? fmtTime : f === 'pad' ? (x) => pad(Math.round(x)) : (x) => Math.round(x).toLocaleString() });
    }), { threshold: 0.6 });
    $$('[data-count]', view).forEach((el) => statIO.observe(el));
    state.cleanup.push(() => statIO.disconnect());

    if (route.restore) requestAnimationFrame(() => scrollTo({ top: state.indexScroll, behavior: 'instant' }));
    else scrollTo({ top: 0, behavior: 'instant' });
  }

  // 行にカーソルを乗せると、カーソルの横にダイジェストが浮かぶ
  const fp = { el: $('.floating-preview'), video: $('.floating-preview video'), time: $('.fp-time'), x: 0, y: 0, cx: 0, cy: 0, vx: 0, on: false, raf: 0 };
  function fpLoop() {
    fp.cx = lerp(fp.cx, fp.x, 0.16);
    fp.cy = lerp(fp.cy, fp.y, 0.16);
    const rot = clamp((fp.x - fp.cx) * 0.04, -8, 8);
    fp.el.style.transform = `translate3d(${fp.cx}px, ${fp.cy}px, 0) rotate(${rot}deg)`;
    fp.raf = fp.on || Math.abs(fp.cx - fp.x) > 0.5 ? requestAnimationFrame(fpLoop) : 0;
  }
  function bindRowPreviews(list) {
    if (!finePointer.matches) return;
    list.querySelectorAll('.row-link').forEach((a) => {
      a.addEventListener('pointerenter', (e) => {
        if (list.dataset.layout === 'grid') {
          const v = a.querySelector('.row-thumb video');
          if (!v.src) v.src = a.dataset.preview;
          tryPlay(v, 'grid');
          return;
        }
        fp.on = true;
        fp.x = fp.cx = e.clientX; fp.y = fp.cy = e.clientY;
        if (fp.video.dataset.src !== a.dataset.preview) {
          fp.video.dataset.src = a.dataset.preview;
          fp.video.src = a.dataset.preview;
        }
        tryPlay(fp.video, 'floating');
        fp.time.textContent = a.querySelector('.row-dur').textContent;
        fp.el.classList.add('is-on');
        if (!fp.raf) fp.raf = requestAnimationFrame(fpLoop);
      });
      a.addEventListener('pointermove', (e) => { fp.x = e.clientX; fp.y = e.clientY; });
      a.addEventListener('pointerleave', () => {
        if (list.dataset.layout === 'grid') { a.querySelector('.row-thumb video').pause(); return; }
        fp.on = false;
        fp.el.classList.remove('is-on');
        fp.video.pause();
      });
    });
  }
  function hideFloating() { fp.on = false; fp.el.classList.remove('is-on'); fp.video.pause(); }

  let searchTimer = 0;
  function bindIndex() {
    const q = $('#q');
    q?.addEventListener('input', () => {
      state.q = q.value;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        const r = renderRows();
        if (state.q.trim()) log('ui.search', { q: state.q.trim() }, r);
      }, 140);
    });
    q?.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { q.value = ''; state.q = ''; renderRows(); q.blur(); }
      if (e.key === 'Enter') { const first = $('.rows .row-link'); if (first) first.focus(); }
    });
    view.addEventListener('click', onIndexClick);
    state.cleanup.push(() => view.removeEventListener('click', onIndexClick));

    // しゃべる立ち絵
    $$('.voice', view).forEach((card) => {
      const who = card.dataset.who;
      const actor = makeActor(card, who);
      state.cleanup.push(actor.stop);
    });

    // feature のホバーでダイジェスト
    const fm = $('.feature-media', view);
    if (fm) {
      const v = fm.querySelector('video');
      fm.addEventListener('pointerenter', () => { v.preload = 'auto'; tryPlay(v, 'feature'); fm.classList.add('is-playing'); });
      fm.addEventListener('pointerleave', () => { v.pause(); fm.classList.remove('is-playing'); });
    }

    // 帯は横幅に応じて速さをそろえる
    $$('.tape', view).forEach((t) => {
      const run = t.querySelector('.tape-run');
      const set = () => t.style.setProperty('--dur', `${Math.max(30, run.scrollWidth / 70)}s`);
      set();
      document.fonts?.ready.then(set);
    });
  }

  function onIndexClick(e) {
    const t = e.target;
    const chip = t.closest('[data-series]');
    if (chip) {
      state.series = chip.dataset.series;
      store.set('za:series', state.series);
      $$('[data-series]').forEach((b) => b.setAttribute('aria-pressed', String(b === chip)));
      log('ui.filter', { series: state.series }, renderRows());
      return;
    }
    const sort = t.closest('[data-sort]');
    if (sort) {
      state.sort = sort.dataset.sort;
      store.set('za:sort', state.sort);
      $$('[data-sort]').forEach((b) => b.setAttribute('aria-pressed', String(b === sort)));
      log('ui.sort', { sort: state.sort }, renderRows());
      return;
    }
    const lay = t.closest('[data-layout]');
    if (lay && lay.tagName === 'BUTTON') {
      state.layout = lay.dataset.layout;
      store.set('za:layout', state.layout);
      $$('[data-layout]').forEach((b) => b.tagName === 'BUTTON' && b.setAttribute('aria-pressed', String(b === lay)));
      hideFloating();
      renderRows();
      log('ui.layout', { layout: state.layout });
      return;
    }
    if (t.closest('[data-clear]')) { state.q = ''; $('#q').value = ''; renderRows(); $('#q').focus(); return; }
    if (t.closest('[data-rescan]')) { rescan(t.closest('[data-rescan]')); return; }
    if (t.closest('[data-export-log]')) { const n = ZA.log.exportLog(); log('ui.log.export', null, { lines: n }); toast(`ログを ${n} 行書き出したのだ（portal-web.log）`); return; }
    if (t.closest('[data-keys]')) { openKeys(); return; }
    const quote = t.closest('[data-quote]');
    if (quote) log('ui.quote.click', { href: quote.getAttribute('href') });
  }

  /** 立ち絵: ときどきまばたきし、押すとセリフを口パクしながら吹き出しに表示する。 */
  function makeActor(card, who) {
    const fig = card.querySelector('.voice-figure');
    const bubble = card.querySelector('.voice-bubble');
    if (!fig) return { stop() {} };
    const quote = bubble.querySelector('blockquote');
    const cap = bubble.querySelector('figcaption');
    const set = (pose) => { fig.dataset.pose = pose; };
    set('idle');
    let blinkT = 0, talkT = 0, typeT = 0, alive = true, talking = false;
    const blink = () => {
      if (!alive) return;
      if (!talking && !reduced.matches) {
        set('blink');
        setTimeout(() => { if (!talking) set('idle'); }, 120);
      }
      blinkT = setTimeout(blink, 2200 + Math.random() * 3200);
    };
    blinkT = setTimeout(blink, 1200 + Math.random() * 2000);
    const qs = sampleQuotes(state.videos, who, 24, Math.floor(Math.random() * 1e6), 8, 46);
    let qi = 0;
    const say = (source) => {
      if (!qs.length) return;
      const { video, line } = qs[qi++ % qs.length];
      talking = true;
      card.classList.add('is-talking');
      quote.textContent = '';
      cap.innerHTML = `<a href="${watchHref(video, line.start)}" data-cursor="聞く">No.${pad(video.no)} · ${fmtTime(line.start)} から聞く →</a>`;
      bubble.classList.add('is-on');
      const chars = Array.from(`「${line.text}」`);
      let i = 0;
      clearInterval(typeT); clearInterval(talkT);
      let open = false;
      talkT = setInterval(() => { open = !open; set(open ? 'talk' : 'idle'); }, 110);
      typeT = setInterval(() => {
        quote.textContent += chars[i++] || '';
        if (i >= chars.length) {
          clearInterval(typeT); clearInterval(talkT);
          set('joy');
          setTimeout(() => { talking = false; card.classList.remove('is-talking'); set('idle'); }, 1400);
        }
      }, reduced.matches ? 0 : 55);
      log('ui.voice.say', { who, source, video: video.id, t: line.start });
    };
    fig.addEventListener('click', () => say('click'));
    fig.addEventListener('pointerenter', () => { if (!talking) set('joy'); });
    fig.addEventListener('pointerleave', () => { if (!talking) set('idle'); });
    // 最初のひと言は画面に入ったときに
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) { io.disconnect(); setTimeout(() => say('auto'), who === 'zundamon' ? 300 : 1900); }
    }, { threshold: 0.5 });
    io.observe(card);
    return { stop() { alive = false; clearTimeout(blinkT); clearInterval(talkT); clearInterval(typeT); io.disconnect(); } };
  }

  async function rescan(btn) {
    btn.disabled = true;
    btn.classList.add('is-busy');
    try {
      // サーバーで開いているときはサーバー側でカタログを作り直してから読む
      if (!ZA.log.FILE_MODE) {
        toast('カタログを作り直しているのだ…');
        const r = await fetch('/api/rescan', { method: 'POST' });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || r.status);
        log('ui.rescan', null, j);
      }
      const res = await refreshCatalog('button');
      if (!res) throw new Error('catalog.js を読めませんでした');
      if (!res.changed) toast(`変わりはなかったのだ（${state.videos.length} 本）`);
      else if (!res.added.length) toast('カタログを読み直したのだ');
    } catch (err) {
      logError('ui.rescan', err);
      toast('読み直しに失敗したのだ（ログを見てほしいのだ）');
    } finally {
      btn.disabled = false;
      btn.classList.remove('is-busy');
    }
  }

  function openKeys() {
    const d = $('dialog.keys');
    if (!d.open) { d.showModal(); log('ui.keys.open'); }
  }

  // ---------------------------------------------------------------- 視聴ページ

  function watchHTML(v) {
    const i = state.videos.indexOf(v);
    const prev = state.videos[i - 1], next = state.videos[i + 1] || state.videos[0];
    const speakers = Object.entries(v.cast);
    const talkTotal = speakers.reduce((a, [, c]) => a + c.stats.seconds, 0) || 1;
    return `
    <article class="watch${state.theater ? ' is-theater' : ''}" data-id="${h(v.id)}">
      <div class="watch-bar">
        <a class="back" href="#/" data-back>${icon('i-arrow', 'flip')}<span>Index</span></a>
        <p class="watch-crumb mono"><span>No.${pad(v.no)}</span><span class="sep">/</span><span>${pad(state.videos.length)}</span><span class="sep hide-sm">—</span><span class="hide-sm">${h(v.series || v.kicker)}</span></p>
        <nav class="watch-pager mono" aria-label="前後の動画">
          ${prev ? `<a href="${watchHref(prev)}" title="${h(prev.title)}">${icon('i-arrow', 'flip')}<span>Prev</span></a>` : '<span class="is-off">Prev</span>'}
          ${state.videos[i + 1] ? `<a href="${watchHref(state.videos[i + 1])}" title="${h(state.videos[i + 1].title)}"><span>Next</span>${icon('i-arrow')}</a>` : '<span class="is-off">Next</span>'}
        </nav>
      </div>
      <div class="watch-layout">
        <div class="watch-main">
          <div class="stage"></div>
          <div class="resume" hidden></div>
          <header class="watch-head">
            <p class="eyebrow mono">${h(v.kicker || v.badge || '')}</p>
            <h1 class="watch-title ph">${ph(v.title)}</h1>
            ${v.lede ? `<p class="watch-lede">${h(v.lede).replace(/\n/g, '<br>')}</p>` : ''}
            <ul class="watch-facts mono">
              <li><b>${fmtTime(v.duration)}</b><span>長さ</span></li>
              <li><b>${fmtDate(v.date)}</b><span>書き出し</span></li>
              <li><b>${v.lines.length}</b><span>セリフ</span></li>
              <li><b>${chapterEntries(v).length}</b><span>${v.toc.some((e) => e.kind === 'chapter') ? '章' : '場面'}</span></li>
              <li><b>${v.video.width}×${v.video.height}</b><span>${v.video.fps || 30}fps</span></li>
              <li><b>${v.video.size ? fmtBytes(v.video.size) : '—'}</b><span>mp4</span></li>
            </ul>
            <div class="watch-actions">
              <button type="button" class="btn-pill" data-theater aria-pressed="${state.theater}">${icon('i-theater')}シアターモード</button>
              <button type="button" class="btn-pill" data-copy>${icon('i-link')}この場面のリンクをコピー</button>
              <a class="btn-pill" href="${v.video.src}" ${ZA.log.FILE_MODE && !PUBLIC ? 'target="_blank" rel="noopener">' : `download="${h(v.id)}.mp4">`}${icon('i-download')}${PUBLIC ? 'mp4 をダウンロード' : ZA.log.FILE_MODE ? 'mp4 を開く' : 'mp4 を保存'}</a>
              ${!PUBLIC && v.published && state.catalog.site?.url ? `<a class="btn-pill" href="${h(state.catalog.site.url)}#/watch/${encodeURIComponent(v.id)}" target="_blank" rel="noopener">${icon('i-link')}公開ページで開く</a>` : ''}
              <button type="button" class="btn-pill" data-keys><kbd class="mono">?</kbd>キー操作</button>
            </div>
          </header>
          <div class="watch-blocks">
            ${v.summary.length ? `<section class="block block-summary"><h2 class="block-title mono">まとめ</h2><ol class="summary" style="--n:${v.summary.length}">${v.summary.map((s, k) => `<li><span class="sum-no mono">${pad(k + 1)}</span><p>${inlineMd(s.text)}${s.sub ? `<small>${inlineMd(s.sub)}</small>` : ''}</p></li>`).join('')}</ol></section>` : ''}
            <section class="block block-speakers">
              <h2 class="block-title mono">話した時間</h2>
              <div class="share-bar small">${speakers.map(([k, c]) => {
                const pct = (c.stats.seconds / talkTotal) * 100;
                return `<span style="--vc:${c.color};flex-basis:${pct}%" title="${h(c.name)} ${pct.toFixed(0)}%"><b>${h(pct >= 30 ? c.name : initial(k, c))}</b><em class="mono">${pct.toFixed(0)}%</em></span>`;
              }).join('')}</div>
              <div class="convo">${barcode(v)}<div class="convo-legend mono">${castLegend(v)}<span class="legend-note">会話の流れ（縦線は章の区切り）</span></div></div>
              <dl class="speaker-stats">${speakers.map(([, c]) => `<div style="--vc:${c.color}"><dt>${h(c.name)}</dt><dd class="mono">${c.stats.lines} セリフ · ${fmtTime(c.stats.seconds)}${c.stats.ending ? ` · 口ぐせ「${h(c.stats.ending[0])}」×${c.stats.ending[1]}` : ''}</dd></div>`).join('')}</dl>
            </section>
            ${v.credits.length ? `<section class="block block-credits"><h2 class="block-title mono">クレジット</h2><dl class="credits">${v.credits.flatMap(([k, x]) => splitCredit(k, x)).map(([k, x]) => `<div><dt class="mono">${h(k)}</dt><dd>${h(x)}</dd></div>`).join('')}</dl></section>` : ''}
            ${v.sources.length ? `<section class="block block-sources"><h2 class="block-title mono">参考にした資料</h2><ol class="sources">${v.sources.map((s) => `<li>${h(s.text)}${s.note ? `<small>${h(s.note)}</small>` : ''}</li>`).join('')}</ol></section>` : ''}
          </div>
        </div>
        <aside class="watch-side" aria-label="目次とセリフ">
          <div class="side-tabs" role="tablist">
            <button type="button" role="tab" id="tab-toc" aria-controls="panel-toc" aria-selected="true">目次<sup class="mono">${v.toc.length}</sup></button>
            <button type="button" role="tab" id="tab-lines" aria-controls="panel-lines" aria-selected="false">セリフ<sup class="mono">${v.lines.length}</sup></button>
            <span class="side-tabs-ink" aria-hidden="true"></span>
          </div>
          <div class="side-panel" role="tabpanel" id="panel-toc" aria-labelledby="tab-toc">
            <ol class="toc">${v.toc.map((e, k) => `
              <li class="toc-item kind-${e.kind}" data-i="${k}">
                <button type="button" data-t="${e.start}">
                  ${e.thumb ? `<img src="${e.thumb}" alt="" loading="lazy" decoding="async" width="480" height="270">` : ''}
                  <span class="toc-text">
                    ${e.num ? `<span class="toc-num mono">${h(e.num)}</span>` : ''}
                    <span class="toc-title ph">${ph(e.title)}</span>
                    <span class="toc-time mono">${fmtTime(e.start)} · ${fmtTime(e.end - e.start)}</span>
                  </span>
                  <i class="toc-prog" aria-hidden="true"></i>
                </button>
              </li>`).join('')}
            </ol>
          </div>
          <div class="side-panel" role="tabpanel" id="panel-lines" aria-labelledby="tab-lines" hidden>
            <div class="lines-tools">
              <label class="lines-filter">${icon('i-search')}<span class="sr-only">セリフを絞り込む</span><input type="search" placeholder="セリフを絞り込む" autocomplete="off"></label>
              <label class="follow"><input type="checkbox" checked><span>自動で追う</span></label>
            </div>
            <ol class="lines">${v.lines.map((l, k) => `
              <li data-i="${k}" data-who="${h(l.who)}" style="--c:${v.cast[l.who]?.color || '#888'}">
                <button type="button" class="line" data-t="${l.start}">
                  <span class="line-who" title="${h(v.cast[l.who]?.name || l.who)}">${h(initial(l.who, v.cast[l.who]))}</span>
                  <span class="line-text">${l.rich ? inlineMd(l.rich) : h(l.text)}</span>
                  <span class="line-time mono">${fmtTime(l.start)}</span>
                </button>
              </li>`).join('')}
            </ol>
          </div>
        </aside>
      </div>
      ${next && next !== v ? `
      <a class="next-up" href="${watchHref(next)}" data-cursor="次へ" data-vt>
        <span class="next-label mono">Next up — No.${pad(next.no)}</span>
        <span class="next-title ph">${ph(next.title)}</span>
        <span class="next-meta mono">${h(next.series)} · ${fmtTime(next.duration)}</span>
        <span class="next-media"><img src="${next.poster}" alt="" loading="lazy" width="1280" height="720"><video muted loop playsinline preload="none" src="${next.preview}"></video></span>
        <span class="next-arrow">${icon('i-arrow')}</span>
      </a>` : ''}
    </article>`;
  }

  function renderWatch(route) {
    const v = route.id === 'latest' ? state.videos[state.videos.length - 1] : state.videos.find((x) => x.id === route.id);
    if (!v) {
      view.innerHTML = `<section class="sec notfound"><p class="mono">404</p><h1>その動画は見つからなかったのだ。</h1><a class="btn btn-primary" href="#/">一覧へ戻る</a></section>`;
      log('route.notfound', { id: route.id }, 'ERROR');
      return;
    }
    document.title = `${v.title} — Zunda Archive`;
    view.innerHTML = watchHTML(v);
    scrollTo({ top: 0, behavior: 'instant' });

    const saved = progress.get(v.id);
    const startAt = route.t || 0;
    const tocItems = $$('.toc-item', view);
    const tocProg = tocItems.map((li) => li.querySelector('.toc-prog'));
    const lineItems = $$('.lines li', view);
    const linesPanel = $('#panel-lines', view);
    const tocPanel = $('#panel-toc', view);
    const follow = $('.follow input', view);
    let lastLine = -2, lastToc = -2, userScrollAt = 0;

    const onTime = (t) => {
      const ti = indexAt(v.toc, t);
      if (ti !== lastToc) {
        tocItems.forEach((li, k) => { li.classList.toggle('is-now', k === ti); li.classList.toggle('is-past', k < ti); });
        if (tocItems[ti] && !tocPanel.hidden && Date.now() - userScrollAt > 4000) scrollIntoPanel(tocPanel, tocItems[ti]);
        lastToc = ti;
      }
      if (ti >= 0) tocProg[ti].style.transform = `scaleX(${clamp((t - v.toc[ti].start) / (v.toc[ti].end - v.toc[ti].start), 0, 1)})`;
      const li = indexAt(v.lines, t);
      if (li !== lastLine) {
        lineItems[lastLine]?.classList.remove('is-now');
        lineItems.forEach((el, k) => el.classList.toggle('is-past', k < li));
        lineItems[li]?.classList.add('is-now');
        lastLine = li;
        if (lineItems[li] && follow.checked && !linesPanel.hidden && Date.now() - userScrollAt > 4000) scrollIntoPanel(linesPanel, lineItems[li]);
      }
    };

    const player = createPlayer($('.stage', view), v, {
      startAt,
      onTime,
      onProgress: (t, d) => progress.set(v.id, t, d),
      onEnded: () => showEndCard(v, player),
    });
    state.player = player;
    state.cleanup.push(() => { player.destroy(); state.player = null; });
    log('watch.open', { id: v.id, t: startAt, resume: saved?.t ?? null });

    // 続きから
    if (!startAt && saved && saved.t > 15 && saved.t < v.duration - 15) {
      const box = $('.resume', view);
      box.hidden = false;
      box.innerHTML = `<p>前回は <b class="mono">${fmtTime(saved.t)}</b> まで見たのだ。</p><button type="button" class="btn-pill is-solid" data-resume>${icon('i-play')}続きから再生</button><button type="button" class="btn-pill" data-dismiss>最初から</button>`;
      box.addEventListener('click', (e) => {
        if (e.target.closest('[data-resume]')) { player.seek(saved.t, 'resume'); player.play(); log('ui.resume', { id: v.id, t: saved.t }); }
        if (e.target.closest('[data-resume], [data-dismiss]')) { box.classList.add('is-out'); setTimeout(() => { box.hidden = true; }, 300); }
      });
    }
    if (startAt) player.play();

    // タブ
    const tabs = $$('[role="tab"]', view);
    const ink = $('.side-tabs-ink', view);
    const moveInk = (tab) => { ink.style.width = `${tab.offsetWidth}px`; ink.style.transform = `translateX(${tab.offsetLeft}px)`; };
    const select = (tab) => {
      tabs.forEach((t) => {
        const on = t === tab;
        t.setAttribute('aria-selected', String(on));
        t.tabIndex = on ? 0 : -1;
        $(`#${t.getAttribute('aria-controls')}`, view).hidden = !on;
      });
      moveInk(tab);
      lastLine = -2; lastToc = -2;
      onTime(player.time);
      log('ui.tab', { id: v.id, tab: tab.id });
    };
    tabs.forEach((t) => t.addEventListener('click', () => select(t)));
    tabs.forEach((t) => t.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        e.preventDefault(); e.stopPropagation();
        const n = tabs[(tabs.indexOf(t) + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
        n.focus(); select(n);
      }
    }));
    requestAnimationFrame(() => moveInk(tabs[0]));
    document.fonts?.ready.then(() => moveInk(tabs.find((t) => t.getAttribute('aria-selected') === 'true')));

    // 目次・セリフを押すとその時刻へ
    view.querySelector('.watch-side').addEventListener('click', (e) => {
      const b = e.target.closest('[data-t]');
      if (!b) return;
      const t = +b.dataset.t;
      log(b.classList.contains('line') ? 'ui.line.click' : 'ui.toc.click', { id: v.id, t });
      userScrollAt = 0;
      player.seek(t, 'side');
      player.play();
      if (matchMedia('(max-width: 1100px)').matches) player.el.scrollIntoView({ behavior: reduced.matches ? 'instant' : 'smooth', block: 'center' });
    });
    [linesPanel, tocPanel].forEach((p) => p.addEventListener('wheel', () => { userScrollAt = Date.now(); }, { passive: true }));
    [linesPanel, tocPanel].forEach((p) => p.addEventListener('touchmove', () => { userScrollAt = Date.now(); }, { passive: true }));

    // セリフの絞り込み
    const filter = $('.lines-filter input', view);
    const texts = v.lines.map((l) => l.text);
    filter.addEventListener('input', () => {
      const q = filter.value.trim();
      let n = 0;
      lineItems.forEach((li, k) => {
        const hit = !q || highlight(texts[k], q).includes('<mark>');
        li.hidden = !hit;
        if (hit) n++;
        const rich = v.lines[k].rich;
        li.querySelector('.line-text').innerHTML = q ? highlight(texts[k], q) : (rich ? inlineMd(rich) : h(texts[k]));
      });
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => q && log('ui.lines.filter', { id: v.id, q }, { hits: n }), 400);
    });

    // リンクのコピー
    $$('[data-copy]', view).forEach((b) => b.addEventListener('click', async () => {
      const url = `${location.href.split('#')[0]}${watchHref(v, player.time)}`;
      try {
        await navigator.clipboard.writeText(url);
        toast(`${fmtTime(player.time)} からのリンクをコピーしたのだ`);
        log('ui.copylink', { id: v.id, t: Math.floor(player.time) });
      } catch (err) {
        logError('ui.copylink', err);
        toast(url);
      }
    }));
    $$('[data-keys]', view).forEach((b) => b.addEventListener('click', openKeys));
    $$('[data-theater]', view).forEach((b) => b.addEventListener('click', () => setTheater(!state.theater)));
    $('[data-back]', view)?.addEventListener('click', () => { state.backRestore = true; });

    // スマホを横向きにしたら、画面いっぱいに広がったプレイヤーの位置へ移動する
    const landscape = matchMedia('(orientation: landscape) and (max-height: 540px) and (pointer: coarse)');
    const onOrientation = () => {
      log('ui.orientation', { id: v.id, landscape: landscape.matches, w: innerWidth, h: innerHeight });
      if (landscape.matches) setTimeout(() => $('.stage', view)?.scrollIntoView({ block: 'start', behavior: 'instant' }), 250);
    };
    landscape.addEventListener('change', onOrientation);
    state.cleanup.push(() => landscape.removeEventListener('change', onOrientation));
    if (landscape.matches) onOrientation();

    const nu = $('.next-up', view);
    if (nu) {
      const nv = nu.querySelector('video');
      nu.addEventListener('pointerenter', () => { nv.preload = 'auto'; tryPlay(nv, 'next-up'); });
      nu.addEventListener('pointerleave', () => nv.pause());
    }
    observeReveals(view);
  }

  function scrollIntoPanel(panel, el) {
    const top = el.offsetTop - panel.clientHeight * 0.3;
    panel.scrollTo({ top: Math.max(0, top), behavior: reduced.matches ? 'instant' : 'smooth' });
  }

  function showEndCard(v, player) {
    const i = state.videos.indexOf(v);
    const next = state.videos[i + 1] || state.videos[0];
    const card = document.createElement('div');
    card.className = 'endcard';
    card.innerHTML = `
      <p class="mono">おしまい — ご視聴ありがとうなのだ！</p>
      ${next && next !== v ? `<a class="endcard-next" href="${watchHref(next)}"><img src="${next.poster}" alt=""><span class="ph"><small class="mono">Next · No.${pad(next.no)}</small>${ph(next.title)}</span></a>` : ''}
      <button type="button" class="btn-pill" data-replay>もう一度見る</button>`;
    player.el.appendChild(card);
    card.querySelector('[data-replay]').addEventListener('click', () => { card.remove(); player.seek(0, 'replay'); player.play(); });
    player.video.addEventListener('play', () => card.remove(), { once: true });
  }

  // ---------------------------------------------------------------- ルーティング

  function parseHash() {
    const raw = location.hash.replace(/^#/, '') || '/';
    const [path, qs] = raw.split('?');
    const params = new URLSearchParams(qs || '');
    const m = /^\/watch\/([^/]+)/.exec(path);
    if (m) return { name: 'watch', id: decodeURIComponent(m[1]), t: Math.max(0, +params.get('t') || 0) };
    return { name: 'index' };
  }

  function teardown() {
    hideFloating();
    for (const fn of state.cleanup.splice(0)) { try { fn(); } catch (err) { logError('teardown', err); } }
  }

  let navSource = null;
  function route(opts = {}) {
    const next = parseHash();
    const prev = state.route;
    if (prev?.name === 'index') state.indexScroll = scrollY;
    const same = prev && prev.name === next.name && prev.id === next.id;
    // 同じ動画内で時刻だけ変わったときはシークだけ
    if (same && next.name === 'watch' && state.player && !opts.force) {
      state.route = next;
      state.player.seek(next.t, 'hash');
      state.player.play();
      return;
    }
    log('route', { from: prev ? `${prev.name}:${prev.id || ''}` : null, to: `${next.name}:${next.id || ''}`, t: next.t || 0 });
    const src = navSource;
    navSource = null;
    const doRender = () => {
      teardown();
      resetCursor();
      state.route = next;
      document.body.dataset.view = next.name;
      document.querySelector('meta[name="theme-color"]').content = next.name === 'watch' ? '#0B0F0C' : '#F2F1EA';
      if (src) src.style.viewTransitionName = '';
      try {
        if (next.name === 'watch') renderWatch(next);
        else renderIndex({ restore: opts.restore || state.backRestore || prev?.name === 'watch' });
      } catch (err) {
        logError('render', err, { route: next });
        view.innerHTML = `<section class="sec notfound"><h1>表示中にエラーが起きたのだ。</h1><p class="mono">logs/portal.log を確認してほしいのだ。</p></section>`;
      }
      state.backRestore = false;
      if (next.name === 'watch') {
        const stage = $('.stage', view);
        if (stage && src) stage.style.viewTransitionName = 'media';
      }
    };
    if (src && !opts.instant) src.style.viewTransitionName = 'media';
    const vt = prev && !opts.instant ? viewTransition(doRender) : (doRender(), null);
    vt?.finished.catch(() => {}).finally(() => { const s = $('.stage', view); if (s) s.style.viewTransitionName = ''; });
    if (!vt) { const s = $('.stage', view); if (s) s.style.viewTransitionName = ''; }
    $('#main').focus({ preventScroll: true });
  }

  // クリックした要素（ポスター等）から視聴ページのプレイヤーへ形が移るように
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[href^="#/watch/"]');
    if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey) return;
    let src = null;
    if (a.matches('.row-link')) src = state.layout === 'grid' ? a.querySelector('.row-thumb') : (fp.on ? fp.el : a.querySelector('.row-thumb'));
    else if (a.dataset.vtFrom) src = $(a.dataset.vtFrom);
    else if (a.hasAttribute('data-vt')) src = a.querySelector('.next-media') || a;
    navSource = src && src.getBoundingClientRect().width > 0 ? src : null;
    if (fp.on && src === fp.el) { fp.el.classList.add('is-leaving'); setTimeout(() => fp.el.classList.remove('is-leaving'), 600); }
  }, true);

  // 一覧を表示中にロゴを押したら先頭へ
  document.querySelector('.brand').addEventListener('click', (e) => {
    if (state.route?.name !== 'index') return;
    e.preventDefault();
    scrollTo({ top: 0, behavior: reduced.matches ? 'instant' : 'smooth' });
    log('ui.brand.top');
  });

  // ページ内の移動（ヘッダーのリンク）
  document.addEventListener('click', (e) => {
    const j = e.target.closest('[data-jump]');
    if (!j) return;
    e.preventDefault();
    const go = () => {
      const target = document.getElementById(j.dataset.jump) || (j.dataset.jump === 'index' ? $('#index') : null);
      if (target) target.scrollIntoView({ behavior: reduced.matches ? 'instant' : 'smooth', block: 'start' });
      log('ui.jump', { to: j.dataset.jump });
    };
    if (state.route?.name !== 'index') { location.hash = '#/'; setTimeout(go, 450); } else go();
  });

  // キーボード
  document.addEventListener('keydown', (e) => {
    const tag = (e.target.tagName || '').toLowerCase();
    const typing = tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable;
    if (e.key === '?' && !typing) { e.preventDefault(); openKeys(); return; }
    if (e.key === '/' && !typing) {
      const input = state.route?.name === 'watch' ? $('.lines-filter input') : $('#q');
      if (input) {
        e.preventDefault();
        if (state.route?.name === 'watch') $('#tab-lines')?.click();
        input.focus({ preventScroll: state.route?.name === 'watch' });
        if (state.route?.name !== 'watch') input.scrollIntoView({ behavior: reduced.matches ? 'instant' : 'smooth', block: 'center' });
      }
      return;
    }
    if (typing || e.target.closest?.('[role="tab"], .pl-scrub')) return;
    // ボタンやリンクの上の Space / Enter はそのボタン自身の操作にする（二重に切り替わらないように）
    if ((e.key === ' ' || e.key === 'Enter') && e.target.closest?.('button, a, [role="button"], summary')) return;
    if (state.route?.name === 'watch' && state.player && !$('dialog.keys').open) {
      if (e.key === 'Escape' && !document.fullscreenElement) return;
      if ((e.key === 't' || e.key === 'T') && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); setTheater(!state.theater); return; }
      state.player.handleKey(e);
    }
  });

  // スクロールでヘッダーの見た目を変える
  let ticking = false;
  addEventListener('scroll', () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      document.body.classList.toggle('is-scrolled', scrollY > 24);
      const dark = $('.footer, .next-up');
      document.body.classList.toggle('topbar-on-dark', !!dark && dark.classList.contains('footer') && dark.getBoundingClientRect().top < 40);
      ticking = false;
    });
  }, { passive: true });

  // ---------------------------------------------------------------- 起動

  // カタログは <script> で読む（file:// で開いたページからは fetch で JSON を読めないため）。
  // 中身は zvideo render の最後と `uv run python -m zvideo.portal` で作り直される。
  const CATALOG_SRC = document.querySelector('meta[name="za-catalog"]')?.content || '../runtime/portal/catalog.js';
  const PUBLIC = ZA.log.PUBLIC;

  function readCatalogScript() {
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = `${CATALOG_SRC}?t=${Date.now()}`;
      s.onload = () => { s.remove(); window.ZA_CATALOG ? resolve(window.ZA_CATALOG) : reject(new Error('catalog.js に ZA_CATALOG がありません')); };
      s.onerror = () => { s.remove(); reject(new Error(`${CATALOG_SRC} を読み込めません`)); };
      document.head.appendChild(s);
    });
  }

  function applyCatalog(cat) {
    state.catalog = cat;
    state.videos = [...cat.videos].sort((a, b) => a.no - b.no);
    $('.topbar .count').textContent = `${pad(state.videos.length)} videos`;
  }

  async function loadCatalog() {
    const t0 = performance.now();
    applyCatalog(await readCatalogScript());
    log('catalog.load', { videos: state.videos.length, generated: state.catalog.generated, mode: ZA.log.FILE_MODE ? 'file' : 'server' }, `ok ${Math.round(performance.now() - t0)}ms`);
  }

  /** カタログを読み直し、変わっていれば一覧に反映する（新しく書き出した動画が増える）。 */
  let refreshing = false;
  async function refreshCatalog(reason) {
    if (refreshing || !state.catalog) return null;
    refreshing = true;
    try {
      const cat = await readCatalogScript();
      if (cat.generated === state.catalog.generated) return { changed: false, added: [] };
      const before = new Set(state.videos.map((v) => v.id));
      applyCatalog(cat);
      const added = state.videos.filter((v) => !before.has(v.id));
      log('catalog.refresh', { reason, generated: cat.generated }, { videos: state.videos.length, added: added.map((v) => v.id) });
      if (state.route?.name === 'index') route({ force: true, restore: true, instant: true });
      if (added.length) toast(added.length === 1 ? `新しい動画「${added[0].title}」が増えたのだ` : `新しい動画が ${added.length} 本増えたのだ`);
      return { changed: true, added };
    } catch (err) {
      logError('catalog.refresh', err, { reason });
      return null;
    } finally {
      refreshing = false;
    }
  }

  async function boot() {
    log('app.start', { ua: navigator.userAgent, w: innerWidth, h: innerHeight, dpr: devicePixelRatio, reducedMotion: reduced.matches, hash: location.hash });
    startClock($('.clock'));
    initCursor();
    try {
      await loadCatalog();
    } catch (err) {
      logError('catalog.load', err);
      document.body.classList.remove('is-loading');
      view.innerHTML = `<section class="sec notfound"><h1>カタログがまだないのだ。</h1><p>ターミナルで次を一度実行してから、このページを開き直してほしいのだ。</p><p class="mono">uv run python -m zvideo.portal</p></section>`;
      return;
    }
    route({ instant: true });
    addEventListener('hashchange', () => route());
    // タブに戻ってきたときと、表示中は1分ごとに読み直す
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') refreshCatalog('visible'); });
    addEventListener('focus', () => refreshCatalog('focus'));
    if (!PUBLIC) setInterval(() => { if (document.visibilityState === 'visible') refreshCatalog('interval'); }, 60000);
    await Promise.race([document.fonts?.ready, new Promise((r) => setTimeout(r, 1500))]);
    document.body.classList.remove('is-loading');
    document.body.classList.add('is-ready');
  }

  boot();
})(window.ZA = window.ZA || {});
