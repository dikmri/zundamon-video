# 台本 script.json とボードの仕様

## 目次

1. ファイル配置
2. script.json の全体
3. meta
4. cast
5. scenes
6. lines
7. ボード（board）
8. CSS 部品
9. 段階表示アニメーション（data-anim）
10. アイコン
11. 効果音
12. 最小の例

## 1. ファイル配置

```
{{ZVIDEO_HOME}}/
  projects/<名前>/script.json        台本（<名前> が出力フォルダ名になる）
  projects/<名前>/boards/*.html      ボードの HTML（script から html_file で参照）
  projects/<名前>/style.css          この動画だけの CSS（あれば自動で読み込む）
  projects/<名前>/img/...            画像を使うなら /projects/<名前>/img/x.png で参照
  out/<名前>/                        生成物（index.html, data.js, audio.wav, frames/, <名前>.mp4）
```

ボード内の URL はプロジェクト直下を `/` とする絶対パスで書く（例 `/projects/h3/img/chart.png`）。

## 2. script.json の全体

```json
{
  "meta": { ... },
  "cast": { "metan": { ... }, "zundamon": { ... } },
  "scenes": [ { "board": { ... }, "lines": [ { ... } ] } ]
}
```

検証は `zvideo/script.py` が行い、未定義の話者や空のセリフは `scenes[2].lines[5]: ...` の形で場所を示して止まる。

## 3. meta

| キー | 既定値 | 説明 |
|---|---|---|
| `title` | `""` | 動画タイトル（HTML の title） |
| `series` | `""` | 右上のシリーズ名ラベル |
| `fps` | 30 | フレームレート |
| `width` / `height` | 1920 / 1080 | 画面サイズ（レイアウトは 1920x1080 前提） |
| `bgm` | なし | プロジェクト直下からのパス（例 `assets/bgm/maou_loop_bgm_acoustic50.mp3`） |
| `bgm_volume` | 0.12 | BGM の音量（線形） |
| `se_volume` | 0.45 | 効果音の音量 |
| `timing` | `{}` | `lead_in` `scene_lead` `gap` `scene_tail` `outro`（秒）。既定 0.5 / 0.4 / 0.3 / 0.6 / 2.0 |
| `reading` | `{}` | 読み替え辞書。長い語から優先して1回だけ置換する。字幕には影響しない |
| `loudness` | -16.0 | 仕上がりの音量（LUFS）。ffmpeg loudnorm の2パスでそろえる。`null` で無効 |
| `name` | フォルダ名 | 出力フォルダ名を変えたいとき |

## 4. cast

キー（`zundamon` など）が `lines[].who` で使う名前になる。

| キー | 説明 |
|---|---|
| `character` | `assets/characters/` のフォルダ名。`zundamon` / `metan`（坂本アヒル氏の立ち絵、既定）、`zundamon_official` / `metan_official`（公式立ち絵） |
| `position` | `left` / `right`（既定配置: めたん左、ずんだもん右） |
| `x` `y` `scale` | 配置の上書き（キャンバス左上の画面座標と倍率） |
| `speed` `pitch` `intonation` | 声の既定値（ずんだもん 1.15 / 0 / 1.15、めたん 1.1 / 0 / 1.1） |
| `face` | 最初のセリフまでの表情 |
| `pose` | セリフで `pose` を指定しないときの腕ポーズ（既定 `normal`） |
| `color` | 字幕の縁取り色の上書き |
| `flip` | 左右反転 |
| `enter_at` | 登場（横から滑り込む）を始める秒 |

## 5. scenes

| キー | 説明 |
|---|---|
| `id` | 任意の名前（ログとデバッグ用） |
| `chapter` | 左上の章ラベル。以降のシーンにも引き継がれる |
| `hide_header` | 章ラベルとシリーズ名を隠す（タイトル・章カード・エンディング） |
| `hide_chars` | 立ち絵を隠す |
| `board` | 7 を参照 |
| `lines` | 6 を参照。空のときは `duration` が必要 |
| `duration` | シーンの最低の長さ（秒） |
| `se` | シーン開始時の効果音（文字列か配列） |
| `flash` | シーン開始時に白くフラッシュする |

## 6. lines

| キー | 説明 |
|---|---|
| `who` | cast のキー（必須） |
| `text` | 字幕（必須）。`**強調**` で黄色、`\n` で改行。どちらも読み上げには含まれない |
| `yomi` | 読み上げ文を丸ごと指定（辞書より優先） |
| `face` | 表情。次の自分のセリフまで続く |
| `pose` | 腕のポーズ。次の自分のセリフまで続き、指定がなければ cast の `pose`（既定 `normal`）に戻る |
| `eyes` | `smile`（笑い目）など。このセリフの間だけ |
| `motion` | `hop`（既定の小さな跳ね）/ `jump` / `shake` / `nod` / `lean` / `shrink` |
| `step` | このセリフの開始時に、ボードの `data-step` が同じ番号の要素を表示する |
| `se` / `se_offset` | セリフ開始時（＋オフセット秒）に鳴らす効果音 |
| `pause` | このセリフの後の間（秒）。負の値で次のセリフを食い気味にする |
| `style` | 声のスタイル名（`happy` `angry` `whisper` `hush` `sexy`、ずんだもんは `tired` `cry` も）。既定はノーマル |
| `speaker` | VOICEVOX のスタイル ID を直接指定（例 ずんだもんノーマル 3、めたんノーマル 2） |
| `speed` `pitch` `intonation` `volume` | このセリフだけ声を変える |

### 表情とポーズ（坂本アヒル氏の立ち絵）

| | ずんだもん（`zundamon`） | 四国めたん（`metan`） |
|---|---|---|
| 表情 `face` | `normal` `happy` `excited` `smug` `angry` `cry` `tired` `hush` `whisper` `sexy` `surprised`（〇〇目） `panic`（><目・汗） `think`（上目づかい） | `normal` `happy` `excited` `smug` `angry` `cry` `tired` `hush` `whisper` `surprised` `panic` `think` |
| ポーズ `pose` | `normal`（腰に手） `down`（腕を下ろす） `point`（画面左＝ボードを指す） `point_up`（人差し指を上に） `raise`（バンザイ） `think`（あごに指） `mouth`（両手を口元に） `chop`（ツッコミ） `fold`（腕組み） `side`（両手を広げる） | `normal`（腕を下ろす） `present`（手のひらを見せる） `point`（指差し） `think`（口元に指） `whisper`（内緒話） `mic`（マイクを持つ） `hold`（抱える） |

- めたんの `point` / `present` は画面の外側（左）を向く。ボードを指す動作には使わず、挨拶や紹介の身振りに使う。
- 目: `open`（既定）`smile`（笑い目）`closed`。まばたきは自動。`surprised` / `panic` は目の形が特殊なのでまばたきしない。
- 公式立ち絵版（`zundamon_official`）の表情は `normal` `happy` `excited` `smug` `angry` `cry` `tired` `hush` `whisper` `sexy`、`metan_official` は `normal` のみで、どちらもポーズはない。

## 7. ボード（board）

| キー | 説明 |
|---|---|
| `layout` | `title` / `chapter` / `bullets` / `credits` / 省略（自由 HTML） |
| `title` | ボード左上の見出し（`title` と `chapter` レイアウト以外） |
| `html` / `html_file` | 自由 HTML（`html_file` は script.json からの相対パス） |
| `class` | ボード要素に足すクラス（`bare` で枠なし透明） |
| `enter` | `zoom` で拡大しながら登場 |

レイアウト別の追加キー:

- `title`: `badge`（上の丸ラベル）、`heading` または `heading_html`（`<span class="accent">` で黄色）、`sub`
- `chapter`: `num`（例「その1」）、`heading`
- `bullets`: `items`（文字列、または `{"text", "sub", "step", "anim"}`）。step を省くと上から 1, 2, 3…
- `credits`: `items`（`[["音声", "VOICEVOX:ずんだもん"], ...]`）

ボードの中身の領域はおよそ幅 1036px × 高さ 520px（見出しあり）。はみ出した部分は表示されない。
文字の大きさの目安: 本文 30〜40px、カード見出し 36〜44px、注記 22〜26px、大きな数値 80〜100px。

## 8. CSS 部品（template/player.css）

| クラス | 用途 |
|---|---|
| `.cols` / `.rows` | 横並び / 縦並び（子は等幅） |
| `.card`（`.pink` `.blue` `.orange`） | 色付きの角丸カード。`h3` と `p` を入れる |
| `.stat`（同じ色クラス） | 大きな数値（`.v`、単位は `.v small`）とラベル（`.k`） |
| `.grid2` | 2列グリッド（stat を4つ並べる等） |
| `.chip`（色クラス） | 丸いラベル |
| `.tip` | オレンジの補足帯。`small` で下に小さな例文 |
| `.steps3` | 番号付きの手順リスト（`ol.steps3 > li`） |
| `.flow` ＋ `.arrow` | カードを矢印でつなぐ横の流れ |
| `.prompt` | コード・プロンプト表示（`.k` 緑 `.s` 黄 `.c` 青 `.d` 桃 `.label`） |
| `.big` / `.note` / `.hl` / `em` | 大きな文字 / 注記 / 蛍光ペン下線 / 桃色の強調 |
| `.credits`（dl） | クレジット表 |
| `.ending` | エンディングの中央寄せ（`h2` が縁取りの大見出し） |
| `.icon` `.icon-l` `.icon-xl` | アイコンの大きさ（1.1em / 72px / 120px） |
| `.kb` | 写真の枠（角丸・白枠・影、はみ出しを隠す）。中の `img` は枠いっぱいに切り抜いて表示し、`kenburns` で動かせる |

その動画だけの部品は `projects/<名前>/style.css` に書く。ボードは `word-break: auto-phrase` で日本語を文節単位で折り返す。

## 9. 段階表示アニメーション（data-anim）

要素に `data-step="n"` と `data-anim="..."` を付ける。表示時刻は、`"step": n` を持つ最初のセリフの開始時刻になる。`step` 0 はシーン開始と同時。

| 値 | 動き |
|---|---|
| `up`（既定） | 下からふわっと |
| `left` / `right` | 横から |
| `pop` | 弾むように拡大 |
| `fade` | フェードのみ |
| `stamp` | 大きく回転しながら押される |
| `mark` | 常に見えていて、時刻が来ると蛍光ペンが引かれる（文中の `span` に使う） |
| `count` | 0 から `data-to` まで数える（`data-decimals` で小数桁、`data-dur` で秒） |
| `type` | テキストを打ち込む（`data-dur` で秒。中身はプレーンテキストのみ） |
| `kenburns` | 写真をゆっくり寄せる（Ken Burns）。`.kb` の枠の中の `img` に付ける。`data-dir`（left / right / up / down）で寄る方向、`data-dur` で秒数（既定 12） |

写真を何枚も見せる回（キャラクター紹介、作品紹介など）は、`<div class="kb" data-step="1" data-anim="pop"><img src="..." data-step="1" data-anim="kenburns"></div>` の形で、枠ごと出してから中の写真をゆっくり動かすと、静止画でも単調にならない。1枚ずつ大きく見せたいときは、同じ位置に `position:absolute` で重ねた枠を段階ごとに `fade` で差し替える。

入れ子にもできる（外側の `pop` と内側の数字の `count` に同じ step を付けるなど）。

## 9.5 生成画像・生成動画の埋め込み

- 画像: `<img class="shot" src="/projects/<名前>/media/x.png">`（角丸・白枠・影つき）。段階表示したいときは親の要素に `data-step` を付ける。
- 動画: `<video class="clip" data-clip="/projects/<名前>/media/x.mp4" data-step="1" data-start="after" data-volume="1.0"></video>`
  - `data-step` の段階が表示された時刻から再生する。`data-start="after"` なら、その段階を出した**セリフが終わってから** 0.3 秒後に再生する（セリフと動画の音が重ならない）。
  - 動画の音は build が audio.wav に混ぜ、その間は BGM を自動で下げる。`data-volume="0"` で音を混ぜない。
  - build が描画用の WebM（VP9）に変換して `out/<名前>/clips/` に置き、パスを差し替える。元の mp4 はそのまま。
  - 再生させたいセリフに `"pause": 動画の長さ + 0.9` を付け、次のセリフが動画に重ならないようにする。

## 10. アイコン

`<i data-icon="video"></i>` と書くとインライン SVG に置き換わる（`template/icons.js`）。色は `color`、大きさは `.icon-l` などで変える。

text, image, video, audio, music, mic, clock, film, arrow, check, sparkle, camera, code, cloud, coin, key, download, warning, layers, user, unlock, globe, app, wand

## 11. 効果音（assets/se）

`title` `jean` `jajean` `doon` `pico` `switch` `chanchan` `pop`
足すときは `assets/se/<名前>.mp3` を置く（効果音ラボ等、規約を確認したもの）。

## 12. 最小の例

同じ内容が `projects/sample/script.json` にある（約19秒）。新しい動画はこれか `projects/h3/` を複製して始める。

```json
{
  "meta": {"title": "テスト", "bgm": "assets/bgm/maou_loop_bgm_acoustic50.mp3", "bgm_volume": 0.1,
           "reading": {"API": "エーピーアイ"}},
  "cast": {"metan": {"character": "metan", "position": "left", "speed": 1.15},
           "zundamon": {"character": "zundamon", "position": "right", "speed": 1.2}},
  "scenes": [
    {"hide_header": true, "se": "title",
     "board": {"layout": "title", "badge": "ずんだもん解説", "heading_html": "<span class=\"accent\">API</span>ってなに？"},
     "lines": [{"who": "zundamon", "text": "ずんだもんなのだ！今日はAPIを解説するのだ！", "face": "excited", "motion": "jump"},
               {"who": "metan", "text": "四国めたんよ。よろしくね。"}]},
    {"chapter": "① しくみ",
     "board": {"title": "APIのしくみ", "html": "<div class=\"flow\"><div class=\"card\" data-step=\"1\"><h3>アプリ</h3></div><i data-icon=\"arrow\" class=\"arrow\" data-step=\"2\"></i><div class=\"card blue\" data-step=\"2\"><h3>サーバー</h3></div></div>"},
     "lines": [{"who": "metan", "text": "アプリが、", "step": 1, "se": "pop"},
               {"who": "metan", "text": "サーバーに**お願い**を送る窓口がAPIよ。", "step": 2, "se": "pop"},
               {"who": "zundamon", "text": "お店の注文口みたいなものなのだ！", "face": "happy", "eyes": "smile"}]},
    {"hide_header": true, "board": {"layout": "credits", "title": "クレジット",
     "items": [["音声", "VOICEVOX:ずんだもん / VOICEVOX:四国めたん"], ["立ち絵", "坂本アヒル"], ["音楽", "音楽：魔王魂"]]},
     "lines": [{"who": "zundamon", "text": "ご視聴ありがとうなのだ！", "face": "happy", "motion": "jump", "se": "chanchan"}]}
  ]
}
```
