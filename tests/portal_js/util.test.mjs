import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
  fmtTime, fmtDate, fmtBytes, normalize, highlight, inlineMd, searchCatalog,
  indexAt, aggregateCredits, sampleQuotes, splitGraphemes, phrases, phraseHtml,
} = require('../../portal/js/util.js');

test('fmtTime formats minutes and hours', () => {
  assert.equal(fmtTime(0), '0:00');
  assert.equal(fmtTime(65.9), '1:05');
  assert.equal(fmtTime(633.67), '10:33');
  assert.equal(fmtTime(3723), '1:02:03');
  assert.equal(fmtTime(NaN), '0:00');
  assert.equal(fmtTime(-3), '0:00');
});

test('fmtDate uses dotted local date', () => {
  assert.equal(fmtDate('2026-10-07T17:50:08'), '2026.10.07');
  assert.equal(fmtDate(null), '');
});

test('fmtBytes picks a readable unit', () => {
  assert.equal(fmtBytes(77853275), '74.2 MB');
  assert.equal(fmtBytes(1500), '1.5 KB');
});

test('normalize folds width, case and katakana', () => {
  assert.equal(normalize('ＡＩ　ズンダモン'), 'ai ずんだもん');
  assert.equal(normalize('ﾐﾆﾏｯｸｽ'), 'みにまっくす');
});

test('highlight marks matches found through normalization and escapes html', () => {
  assert.equal(highlight('ミニマックス<H3>', 'みにまっくす'), '<mark>ミニマックス</mark>&lt;H3&gt;');
  assert.equal(highlight('ＡＩの話とAI', 'ai'), '<mark>ＡＩ</mark>の話と<mark>AI</mark>');
  assert.equal(highlight('a & b', ''), 'a &amp; b');
});

test('highlight marks every token of a multi-word query', () => {
  assert.equal(highlight('停戦と封鎖', '封鎖 停戦'), '<mark>停戦</mark>と<mark>封鎖</mark>');
});

test('inlineMd turns **bold** into strong after escaping', () => {
  assert.equal(inlineMd('声も**同時に<生成>**'), '声も<strong>同時に&lt;生成&gt;</strong>');
});

const videos = [
  { id: 'a', fullTitle: 'MiniMax H3で動画を作るのだ', series: 'AIツール解説', lede: '', toc: [{ title: 'スペック' }], summary: [],
    lines: [{ who: 'z', text: 'ずんだ餅を食べるのだ', start: 1 }, { who: 'm', text: 'H3は声も作れるわ', start: 5 }] },
  { id: 'b', fullTitle: 'イラン戦争', series: 'ニュース解説', lede: '', toc: [], summary: [],
    lines: [{ who: 'm', text: 'ホルムズ海峡が封鎖されたわ', start: 3 }] },
];

test('searchCatalog finds title matches and line matches', () => {
  const r = searchCatalog(videos, 'h3');
  assert.deepEqual(r.map((x) => [x.video.id, x.meta, x.lines.map((l) => l.start)]), [['a', true, [5]]]);
  const r2 = searchCatalog(videos, 'ﾎﾙﾑｽﾞ');
  assert.deepEqual(r2.map((x) => [x.video.id, x.meta, x.lines.length]), [['b', false, 1]]);
});

test('searchCatalog requires every token', () => {
  assert.equal(searchCatalog(videos, 'ずんだ餅 封鎖').length, 0);
  assert.equal(searchCatalog(videos, '').length, 2);
});

test('indexAt returns the last item that has started', () => {
  const items = [{ start: 0 }, { start: 10 }, { start: 20 }];
  assert.equal(indexAt(items, -1), -1);
  assert.equal(indexAt(items, 0), 0);
  assert.equal(indexAt(items, 15), 1);
  assert.equal(indexAt(items, 99), 2);
});

test('aggregateCredits merges values per role without duplicates', () => {
  const r = aggregateCredits([
    { credits: [['音声', 'VOICEVOX:ずんだもん'], ['音楽', '魔王魂']] },
    { credits: [['音声', 'VOICEVOX:ずんだもん'], ['地図', 'Natural Earth']] },
  ]);
  assert.deepEqual(r, [['音声', ['VOICEVOX:ずんだもん']], ['音楽', ['魔王魂']], ['地図', ['Natural Earth']]]);
});

test('aggregateCredits splits combined roles and drops the repeated role prefix', () => {
  const r = aggregateCredits([
    { credits: [['音楽 / 効果音', '音楽：魔王魂 / 効果音ラボ'], ['音楽', '音楽：魔王魂']] },
    { credits: [['効果音', '効果音ラボ'], ['作例の生成', 'WAI-ANIMA / Anima']] },
  ]);
  assert.deepEqual(r, [['音楽', ['魔王魂']], ['効果音', ['効果音ラボ']], ['作例の生成', ['WAI-ANIMA / Anima']]]);
});

test('sampleQuotes is deterministic and filters by speaker and length', () => {
  const vs = [{ id: 'a', no: 1, lines: Array.from({ length: 30 }, (_, i) => ({ who: i % 2 ? 'm' : 'z', text: 'あ'.repeat(10 + i), start: i })) }];
  const a = sampleQuotes(vs, 'z', 4, 7, 12, 30);
  const b = sampleQuotes(vs, 'z', 4, 7, 12, 30);
  assert.deepEqual(a, b);
  assert.equal(a.length, 4);
  for (const q of a) {
    assert.equal(q.line.who, 'z');
    assert.ok(q.line.text.length >= 12 && q.line.text.length <= 30);
    assert.equal(q.video.id, 'a');
  }
});

test('phrases keeps words and their particles together', () => {
  const ps = phrases('アメリカ・イスラエル×イラン戦争 なぜ始まり、なぜ終わらないのか');
  assert.equal(ps.join(''), 'アメリカ・イスラエル×イラン戦争 なぜ始まり、なぜ終わらないのか');
  assert.ok(ps.some((p) => p.includes('終わらないのか')), ps.join('|'));
  assert.ok(ps.every((p) => !p.startsWith('、') && !p.startsWith('ぜ')), ps.join('|'));
  assert.ok(phrases('MiniMax H3で動画を作るのだ！').every((p) => !/^[をのだ！]/.test(p)));
  assert.ok(phrases('WAI-Animaとzundamon-video').some((p) => p.includes('WAI-Anima')));
});

test('phraseHtml escapes and joins phrases with wbr', () => {
  const html = phraseHtml('<b>動画を作る</b>');
  assert.ok(!html.includes('<b>'));
  assert.equal(html.replace(/<wbr>/g, ''), '&lt;b&gt;動画を作る&lt;/b&gt;');
  assert.ok(html.includes('<wbr>'));
});

test('splitGraphemes keeps surrogate pairs together', () => {
  assert.deepEqual(splitGraphemes('A😀ず'), ['A', '😀', 'ず']);
});
