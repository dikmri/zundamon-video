---
name: zundamon-video
description: ずんだもん（＋四国めたん）の掛け合い解説動画を、VOICEVOX音声・坂本アヒル氏の立ち絵（口パク・目パチ・表情・腕ポーズ）・HTMLボードで作り mp4 に書き出す。「ずんだもん解説動画を作って」「ずんだもんとめたんで〇〇を解説する動画」「VOICEVOXで解説動画」「ゆっくり解説風の動画」「この記事/ツール/ニュースを解説動画にして」など、キャラクターが話して図解する解説・紹介・まとめ動画の依頼では、ずんだもんの名前が出なくても必ずこのスキルを使う。台本作成、ボード（スライド）作成、音声合成、口パク、字幕、BGM・効果音、動画書き出しまで一式を扱う。AIで実写風の映像そのものを生成する依頼（MiniMax H3 等のプロンプト作成）や既存動画の編集だけの依頼には使わない。
---

# ずんだもん解説 HTML 動画生成

台本 JSON から、ずんだもん・四国めたんが掛け合いで解説する 1920x1080 / 30fps の mp4 を作る。
画面は HTML で組み、時刻 t を指定すると同じ絵が必ず出る（決定的な）プレイヤーを Playwright で1コマずつ撮影する。

```
script.json + boards/*.html
  → VOICEVOX で各セリフを合成（キャッシュあり）
  → モーラ時刻から口パク、セリフ長からタイムライン
  → out/<名前>/index.html + data.js + audio.wav
  → Playwright で全フレーム撮影 → ffmpeg で mp4
```

## ツールキットの場所

- 本体: `{{ZVIDEO_HOME}}`（zundamon-video リポジトリ。uv の Python プロジェクト）。コマンドはすべてこのフォルダで実行する。
- 見つからない、または壊れているときは、ユーザーに場所を確認する。素材の取得と立ち絵パーツの生成は `uv run python -m zvideo.setup_env` でできる（VOICEVOX エンジン約1.8GB、公式立ち絵、フォント、BGM、効果音、Playwright 用 Chromium をすべてプロジェクト内に置く）。素材は規約上リポジトリに同梱していないので、初回は必ずこれを実行する。
- 立ち絵の既定は坂本アヒル氏の PSDTool 対応素材（`character: "zundamon"` / `"metan"`）。zip は `runtime/sozai_src/ahiru/` に置く。配布元のアップローダーはダウンロード時に利用規約への同意を求めるので、ユーザー自身に取得してもらう（setup_env は自動取得せず、入手先とパスワードの所在を表示して止まる）。公式立ち絵版は `zundamon_official` / `metan_official`。
- VOICEVOX エンジンは build 時に自動で起動する（`runtime/voicevox/windows-cpu/run.exe`、ポート 50021）。
- ログ: `logs/zvideo.log`。1行1イベントで、`時刻 | イベント | 引数 | 結果` の形式。失敗したときはまずここを読む。

| コマンド | 用途 |
|---|---|
| `uv run python -m zvideo build projects/<名前>/script.json` | 音声合成・タイムライン・audio.wav まで作る（尺が分かる） |
| `uv run python -m zvideo frames projects/<名前>/script.json --at 5 30 61.5` | 指定した秒のフレームを `out/<名前>/frames/*.png` に保存する |
| `uv run python -m zvideo render projects/<名前>/script.json --workers 4` | mp4 を `out/<名前>/<名前>.mp4` に書き出す（5分の動画で数分）。書き出し後、ポータル（`portal/index.html`）にも自動で加わる |
| `uv run python -m zvideo preview projects/<名前>/script.json` | ブラウザで音声つき再生する（ユーザーの確認用。Ctrl+C で終了） |
| `uv run python -m zvideo.portal` | 書き出した動画の一覧・視聴ページ（`portal/index.html`）のカタログを更新してブラウザで開く。HTML は直接開いても動く |
| `uv run python -m zvideo.portal.publish <名前>` | 公開サイト（GitHub Pages）に動画を公開する。**ユーザーが「公開して」と言ったときだけ**使う（後述） |
| `uv run pytest -q` | 口パク・タイムライン・台本検証のテスト |

作例は `projects/h3/`（MiniMax H3 の解説、約4分40秒）、`projects/kiritan/`（生成 AI の作例入り、約5分）、`projects/promo/`（このスキル自体の紹介）、最小のサンプルは `projects/sample/`（約19秒）にある。新しい動画を作るときは、まずこれらの script.json とボードを読んで書き方をそろえると早い。

## 手順

### 1. 題材を調べる

解説動画の価値は内容の正確さで決まる。公式発表・公式ドキュメントなどの一次情報を優先し、日付・数値・固有名詞を確認する。
二次情報にしか載っていない数値は、出典をボードに書くか、使わない。古くなる情報（価格・提供状況など）は「2026年10月時点」のように時点を添える。
調べた出典はエンディングのクレジットに「出典」として書く。

### 2. 構成を決める

`references/format.md` を読む。ずんだもん解説動画の定番の流れ（つかみ→自己紹介→本題の章立て→まとめ→締め）、役割分担、口調、テンポ、演出の慣習をまとめてある。
目安は 1章あたり 30〜45 秒、全体 3〜6 分、セリフは 1 本 40 字以内（字幕 2 行に収まる長さ）。

### 3. 台本とボードを書く

`references/script-schema.md` を読む。台本の全フィールド、ボードのレイアウト、使える CSS 部品とアイコン、段階表示のアニメーション、効果音の一覧がある。

- `projects/<名前>/script.json`: メタ情報、出演者、シーン（ボード＋セリフ列）。
- `projects/<名前>/boards/*.html`: 図解ボードの HTML。台本から `"html_file"` で読み込む。
- `projects/<名前>/style.css`: その動画だけで使う部品の CSS（任意）。
- 英字・略語・数字の読みは `meta.reading` 辞書で指定する（例: `"H3": "エイチスリー"`）。字幕は元の表記のまま、読み上げだけが変わる。
- ボードの要素に `data-step="n"` を付け、その要素を説明するセリフに `"step": n` を付ける。セリフに合わせて図が1つずつ出るのが解説動画らしさの中心になる。

### 4. ビルドしてフレームで確認する

`build` で尺を確かめ、各シーンの終わり近く（全段階が表示された時点）を `frames` で撮って Read で目で見る。シーン時刻は `out/<名前>/data.js` の `scenes[].start/end` にある。

撮ったフレームで確かめること:
- ボードの下端で文字や部品が切れていない（`overflow: hidden` なので、はみ出しは黙って消える）
- 立ち絵（左右の端）がボード内の文字を隠していない
- 字幕が2行以内（超えると自動で縮小し、ログに `subtitle.overflow` が出る）
- 単語の途中で改行されていない（`word-break: auto-phrase` が効く書き方か）
- 表情と口パクが場面に合っている

直したら再ビルドする。音声はキャッシュされるので、セリフを変えない限り速い。

### 5. 書き出して検証する

`render --workers 4` で mp4 にする。書き出し後に次を確認する。
- `ffprobe` で映像・音声の両ストリームがあり、尺が `build` の total と一致する
- 音量が約 -16 LUFS（`ffmpeg -i <mp4> -vn -af ebur128 -f null -` の Summary の I）
- `logs/zvideo.log` に `ERROR`、`render.not_found`、`render.pageerror` が出ていない
- 冒頭・中盤・終盤から数フレームを切り出して目視する（`ffmpeg -ss <秒> -i <mp4> -frames:v 1 x.png`）

### 6. 渡す

mp4 のパス、尺、使った素材のクレジット、ユーザーが確認する手順（再生して見る点）を伝える。
ポータル（`{{ZVIDEO_HOME}}/portal/index.html`）に新しい動画が加わったことも伝える（render の出力の最後に `portal:` の行が出る）。この時点ではまだ公開されていない（ポータルの一覧に「未公開」と出る）。

### 7. 公開する（ユーザーが求めたときだけ）

書き出した動画は自動では公開しない。ユーザーが動画を確認し、「公開して」と伝えたときに初めて公開する。公開はインターネット上に出す操作なので、頼まれていない動画は公開しない。

- `uv run python -m zvideo.portal.publish <名前> --co-author "<コミットに付ける Co-Authored-By>"`
  - mp4 を公開サイトのリポジトリのリリース（タグ `videos`）に上げ、サイト（`runtime/site` の作業コピー）を組み立てて push する。書き出し直した動画は差し替える。
  - 公開状況は `--status`、公開をやめるのは `--remove <名前>`（ユーザーが求めたときだけ）。
- 出力の最後に出るサイトの URL と、その動画のページの URL（`…#/watch/<名前>`）を伝える。反映には1〜2分かかる。
- 失敗したら `logs/portal.log` の `publish.*` の行を読む。
プレビュー（`preview`）は音声つきでシーク再生できるので、修正点を時刻で指摘してもらうのに向いている。

## 生成 AI の作例を動画に入れる

画像生成・動画生成ツールの解説では、実際に生成した画像や動画をボードに載せると伝わり方が大きく変わる（埋め込み方は `references/script-schema.md` の 9.5）。作例 `projects/kiritan/` がその形になっている。

- **画像（WAI-Anima / Anima 系）**: `uv run python tools/anima_gen.py projects/<名前>/media/anima_spec.json --comfy-root <ポータブル版 ComfyUI>`。`--url`（既定 8190 番）の ComfyUI が応答しなければポータブル版を裏で起動し、spec の各画像を `media/<名前>.png` に保存して、自分で起こしたサーバーだけ止める。レーティングは safe 以外を受け付けず、否定プロンプトへ成人向けタグを必ず足す。
- **動画（MiniMax H3）**: H3 が入った ComfyUI（0.30 以降）を起動しておき、`uv run python tools/h3_gen.py --image <最初のコマ> --prompt-file <txt> --out <mp4> --seconds 5 --url <ComfyUI の URL>`。モデル名の既定は Hugging Face「Comfy-Org/MiniMax-H3」のファイル名で、違う名前なら `--unet` `--text-encoder` `--lora` などで渡す。MiniMaxH3TurboSampler（カスタムノード）があれば `--turbo-sampler` で声や効果音がきれいになる。プロンプトは「最初のコマの指定 → 映像とセリフ → 環境音 → BGM」の順に英語で書く（セリフは `<d>[Japanese] …</d>` で日本語のまま）。RTX 5060 Ti 16GB で 480p・5 秒が約 4 分（2本目以降はモデルを載せたままなので約 3 分）。何本も続けて作るときは最後の1本以外に `--no-free` を付けると、毎回のモデルの読み直しを省ける。
- 画像生成と H3 は同じ GPU を奪い合うので、順番に動かす（どちらのツールも、自分で起こした ComfyUI は終わると止める）。
- 作例の内容は全年齢に限る。とくに子どもの設定のキャラクター（東北きりたん等）は、服装・しぐさ・構図まで健全なものだけを作り、出力は1枚ずつ目で確認してから使う。

## クレジットと規約

エンディングのボードに必ず入れる。抜けると素材の利用条件を満たさない。

- 音声: `VOICEVOX:ずんだもん`、`VOICEVOX:四国めたん`（この表記どおり。使ったキャラだけ）
- 立ち絵: `立ち絵：坂本アヒル`（readme では表記は任意だが入れる）。公式立ち絵版を使った場合は「東北ずん子・ずんだもんプロジェクト公式素材」。どちらも東北ずん子・ずんだもんプロジェクトのキャラクター利用ガイドラインに従う（非商用は無料。企業案件など商用は要確認。イメージを著しく損なう内容は禁止）。めたんの PSD には水着・バニー服・素体も入っているが、通常服以外は使わない
- 音楽: `音楽：魔王魂`（BGM を使うときは表記が必須）
- 効果音: 効果音ラボ（表記は任意だが入れておく。効果音が主役の動画は規約上の再配布扱いになるので不可）
- フォント: M PLUS Rounded 1c / Dela Gothic One（SIL OFL）

## うまくいかないとき

- **音声合成で止まる**: `logs/voicevox_engine.log` を読む。ポート 50021 を別の VOICEVOX が使っていても動く（そちらに接続する）。
- **書き出しで `NetworkError` / `ERR_NO_BUFFER_SPACE`**: 描画用ブラウザは HTTP を使わず、`page.route` でディスクから直接読む作りになっている。ローカル HTTP サーバー経由に戻すと、並列描画で Windows のソケットバッファが尽きて再発する。
- **表情を切り替えたら前の口や目が残る**: 子要素の `visibility: visible` は親の `hidden` を上書きする。非アクティブな表情の中の画像は `.face:not(.on) img` で隠している。CSS を触るときはこの規則を消さない。
- **立ち絵パーツの縁が灰色・黒くにじむ**: 透過 PNG の縮小は乗算済みアルファ（PIL の `RGBa`）で行う。透明部分の RGB を黒のままマスク合成しない。
- **新しいキャラクター・表情・ポーズを足したい**: PSDTool 対応の PSD なら、`zvideo/characters.py` の `ZUNDAMON_AHIRU` / `METAN_AHIRU` と同じ形の SPEC を書いて `prepare_psdtool()` に渡す。SPEC はレイヤーのパス（例 `"!口/*むふ"`）で、土台・腕ポーズ・表情（眉/目/口/頬/記号）・前髪を割り当てるだけでよい。口パクは口レイヤーを母音（n/a/i/u/e/o）に割り当てる。候補の見た目は、レイヤーごとに合成した一覧画像を作って選ぶ。1枚絵しかないキャラは、`metan_official` と同じく口の形を描いて重ねる方式を使う。
- **埋め込み動画が最初のコマのまま動かない**: 動画を URL のまま `<video src>` に渡すと、描画時のディスク直接配信もプレビューの HTTP サーバーも Range 要求に応じないため `seekable` が `[0,0]` になり、再生位置を変えられない。player.js は `fetch` → Blob URL で読み込んでいる。この経路を戻さない。
- **ツールが ComfyUI を起動したまま固まる**: 起動した ComfyUI の出力をパイプで受けると、子プロセスがパイプのハンドルを持ち続けて閉じず、呼び出し側が永久に待つ。出力はファイルへ出す（`zvideo/comfy.py` の `start_portable()`）。
- **立ち絵がボードの文字を隠す**: 立ち絵の横幅は髪型で大きく変わる（めたんはドリルヘアが広い）。`zvideo/build.py` の `DEFAULT_PLACEMENT` か cast の `x` / `scale` で外側へ寄せる。ボードの文字は x=442 から始まるので、髪や腕がそこを越えないようにする。
