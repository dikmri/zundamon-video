# zundamon-video

ずんだもん解説動画のツールキットと Claude Code スキル。公開リポジトリ: https://github.com/dikmri/zundamon-video （public・MIT）

## 変更したら GitHub にも反映する

このプロジェクトを更新したときは、作業の区切りで GitHub へ反映する（ユーザーの指示: 2026-10-07）。

1. `uv run pytest -q` が通ることを確かめる。
2. スキル（`skill/zundamon-video/`）を変えたら `uv run python -m zvideo.install_skill` で手元の `~/.claude/skills/zundamon-video` にも入れ直す。手元のスキルを直接編集した場合は、同じ変更を `skill/` に戻す（手元とリポジトリを食い違わせない）。
3. コミットして `git push`。作者は noreply アドレス（リポジトリの `git config user.email` に設定済み）。
4. 作例動画を作り直したときは、リリースの添付も差し替える:
   `gh release upload v0.1.0 <file> --clobber --repo dikmri/zundamon-video`
   （添付名は README のリンクと同じ `zundamon-video-promo.mp4` / `example-minimax-h3.mp4` / `example-kiritan-pv.mp4`）。
   機能が大きく増えたときは、新しいタグでリリースを作り、README のリンク先も更新する。
5. README 冒頭の紹介動画は GitHub の動画添付（`https://github.com/user-attachments/assets/...` を1行で置くと再生プレイヤーになる）。
   紹介動画を作り直したら、10MB 以内の 720p 版（`-vf scale=1280:-2 -crf 26 -preset slow`、約8.4MB）を作り、
   ユーザーの Chrome で新規 Issue の入力欄へ添付して URL を取り、README の URL を差し替える（Issue は投稿しない）。
   添付ボタンは押すと OS のファイル選択が開くので使わない。ページに一時的な `<input type=file>` を作ってファイルを渡し、
   入力欄（textarea）に drop イベントを送るとアップロードされる。
   添付は外部への公開にあたるので、その都度ユーザーに確認してから行う。

## 公開してはいけないもの

- 素材（立ち絵とそのパーツ、BGM、効果音、フォント、VOICEVOX）。各規約で再配布できない。`.gitignore` で除外している。
- 個人情報と手元のパス（メールアドレス、`C:\Users\<名前>`、`H:\soft`、`D:\ai` など）。スキル文書ではツールキットの場所を `{{ZVIDEO_HOME}}` と書き、install_skill が置き換える。
- push 前に確認する: `git ls-files -z | xargs -0 grep -l -I -F "<文字列>"` で該当なしになること。

## 作例は全年齢に限る

生成 AI の作例（画像・動画）は全年齢の内容だけを作る。東北きりたん等、子どもの設定のキャラクターは特に、服装・しぐさ・構図まで健全なものにし、出力は1枚ずつ目で確認してから使う。
