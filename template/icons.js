// <i data-icon="video"></i> をインライン SVG に置き換えるための小さなアイコン集（24x24, 線画）
window.ZV_ICONS = {
  text: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M8 9h8M12 9v7"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="2"/><path d="M21 17l-5-5-9 8"/>',
  video: '<rect x="2" y="5" width="14" height="14" rx="3"/><path d="M16 10l6-3v10l-6-3z"/>',
  audio: '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9a4 4 0 0 1 0 6M19 6a8 8 0 0 1 0 12"/>',
  music: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  film: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4M3 16h4M17 8h4M17 16h4"/>',
  arrow: '<path d="M4 12h15M13 6l6 6-6 6"/>',
  check: '<path d="M4 12l5 5L20 6"/>',
  sparkle: '<path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"/>',
  camera: '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="4"/>',
  code: '<path d="M8 6l-6 6 6 6M16 6l6 6-6 6"/>',
  cloud: '<path d="M7 18a5 5 0 1 1 1-9.9A6 6 0 0 1 19 10a4 4 0 0 1 0 8z"/>',
  coin: '<circle cx="12" cy="12" r="9"/><path d="M12 6.5v11M15 9.5c0-1.4-1.3-2.4-3-2.4s-3 1-3 2.3 1.3 2 3 2.4 3 1 3 2.4-1.3 2.4-3 2.4-3-1-3-2.4"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  warning: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/>',
  layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/>',
  unlock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.5-2"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
  app: '<rect x="6" y="2" width="12" height="20" rx="3"/><path d="M11 18h2"/>',
  wand: '<path d="M4 20L16 8M14 4v3M18 8h3M17 5l2-2M19 12l1 1"/>',
};

window.zvIcons = function (root) {
  root.querySelectorAll('i[data-icon]').forEach((el) => {
    const body = window.ZV_ICONS[el.dataset.icon];
    if (!body) return;
    const cls = ['icon'].concat(el.className ? [el.className] : []).join(' ');
    // data-step / data-anim / style などの属性は引き継ぐ（アイコン単体でも段階表示できるように）
    const attrs = [...el.attributes]
      .filter((a) => a.name !== 'data-icon' && a.name !== 'class')
      .map((a) => ` ${a.name}="${a.value.replace(/"/g, '&quot;')}"`).join('');
    el.outerHTML = `<svg class="${cls}"${attrs} viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
      `stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
  });
};
