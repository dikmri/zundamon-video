// ブラウザ側のイベントを1行ずつ記録する。形式は「時刻 | web.<イベント> | 引数 | 結果」。
// ・サーバーで開いたとき（http://）: POST /api/log で logs/portal.log に追記する。
// ・HTML を直接開いたとき（file://）: ブラウザからは任意のファイルへ書き込めないため、同じ形式の行を
//   ブラウザ内（localStorage）に最新 2000 行まで残し、フッターの「ログを書き出す」で portal-web.log として保存する。
(function (ZA) {
  'use strict';
  const FILE_MODE = location.protocol === 'file:';
  // 公開用サイトでは見ている人の操作を記録しない（コンソールに出すだけ）
  const PUBLIC = document.querySelector('meta[name="za-mode"]')?.content === 'public';
  // URL に ?debug=1 を付けたときは、記録を画面右下に出してコピーできるようにする（スマホでの確認用）
  const DEBUG = /[?&]debug(=1)?(&|$)/.test(location.search);
  const debugLines = [];
  const KEY = 'za:log';
  const MAX = 2000;
  const queue = [];
  let timer = 0;

  const fmt = (v) => (v == null ? '-' : typeof v === 'string' ? v : JSON.stringify(v));
  const pad = (n, w = 2) => String(n).padStart(w, '0');
  function stamp(d = new Date()) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
  }

  function readLocal() {
    try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch { return []; }
  }

  function flush(useBeacon = false) {
    clearTimeout(timer);
    timer = 0;
    if (!queue.length) return;
    const items = queue.splice(0);
    if (PUBLIC) return;
    if (FILE_MODE) {
      try { localStorage.setItem(KEY, JSON.stringify(readLocal().concat(items.map((it) => it.line)).slice(-MAX))); } catch { /* 保存できなくても画面は止めない */ }
      return;
    }
    const body = JSON.stringify(items.map(({ event, args, result }) => ({ event, args, result })));
    try {
      if (useBeacon && navigator.sendBeacon) {
        navigator.sendBeacon('/api/log', new Blob([body], { type: 'application/json' }));
        return;
      }
      fetch('/api/log', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true }).catch(() => {});
    } catch { /* 記録の失敗で画面を止めない */ }
  }

  function log(event, args = null, result = 'ok') {
    const line = `${stamp()} | web.${event} | ${fmt(args)} | ${fmt(result)}`.replace(/\n/g, '\\n');
    queue.push({ event, args, result, line });
    if (DEBUG) { debugLines.push(line); renderDebug(); }
    if (!PUBLIC) console.debug('[log]', line);
    if (!timer) timer = setTimeout(flush, FILE_MODE ? 300 : 800);
  }

  function logError(event, err, args = null) {
    const msg = err && (err.stack || err.message)
      ? `${err.name || 'Error'}: ${err.message}\n${(err.stack || '').split('\n').slice(1, 4).join('\n')}`
      : String(err);
    log(event, args, `ERROR ${msg}`);
  }

  /** file:// のときにブラウザ内に残したログを portal-web.log として保存する。 */
  function exportLog() {
    flush();
    const lines = readLocal();
    const blob = new Blob([lines.join('\n') + '\n'], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'portal-web.log';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    return lines.length;
  }

  let debugBtn = null, debugPanel = null;
  function renderDebug() {
    if (!DEBUG || !document.body) return;
    if (!debugBtn) {
      debugBtn = document.createElement('button');
      debugBtn.type = 'button';
      debugBtn.style.cssText = 'position:fixed;left:10px;bottom:10px;z-index:300;padding:8px 12px;border-radius:999px;border:0;background:#D43A86;color:#fff;font:700 12px/1 ui-monospace,monospace';
      debugPanel = document.createElement('div');
      debugPanel.style.cssText = 'position:fixed;left:10px;right:10px;bottom:52px;max-height:55vh;overflow:auto;z-index:300;background:rgba(11,15,12,.94);color:#ECEEE5;border-radius:12px;padding:10px;font:11px/1.5 ui-monospace,monospace;white-space:pre-wrap;word-break:break-all;display:none';
      const copy = document.createElement('button');
      copy.type = 'button';
      copy.textContent = '記録をコピー';
      copy.style.cssText = 'position:sticky;top:0;float:right;padding:6px 10px;border-radius:999px;border:0;background:#A5DA5B;color:#0E1510;font:700 12px/1 sans-serif';
      copy.addEventListener('click', async () => {
        const text = [...debugLines, `ua: ${navigator.userAgent}`, `screen: ${innerWidth}x${innerHeight} @${devicePixelRatio}`].join('\n');
        try { await navigator.clipboard.writeText(text); } catch {
          const t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove();
        }
        copy.textContent = 'コピーしました';
      });
      debugPanel.appendChild(copy);
      debugPanel.appendChild(document.createElement('pre'));
      debugBtn.addEventListener('click', () => { debugPanel.style.display = debugPanel.style.display === 'none' ? 'block' : 'none'; });
      document.body.append(debugPanel, debugBtn);
    }
    debugBtn.textContent = `記録 ${debugLines.length}`;
    debugPanel.querySelector('pre').textContent = debugLines.slice(-200).join('\n');
  }

  function installGlobalHandlers() {
    if (DEBUG) document.addEventListener('DOMContentLoaded', renderDebug);
    addEventListener('error', (e) => {
      if (e.target && e.target !== window && (e.target.src || e.target.href)) {
        log('resource.error', { tag: e.target.tagName, src: e.target.currentSrc || e.target.src || e.target.href }, 'ERROR load failed');
        return;
      }
      logError('window.error', e.error || e.message, { at: `${e.filename}:${e.lineno}:${e.colno}` });
    }, true);
    addEventListener('unhandledrejection', (e) => logError('window.unhandledrejection', e.reason));
    addEventListener('pagehide', () => flush(true));
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flush(true); });
  }

  ZA.log = { FILE_MODE, PUBLIC, log, logError, exportLog, installGlobalHandlers };
})(window.ZA = window.ZA || {});
