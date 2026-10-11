#!/usr/bin/env bash
# 魔王魂「ピアノ38」（ループ版なし・約68秒、55秒以降は余韻と無音）を、
# 余韻と次の頭を 2.5 秒重ねて 12 回つないだ長尺版にする。
# build は BGM を単純に繰り返すため、元の曲のままだと 1 分ごとに約 7 秒の無音が入る。
#
# 使い方（プロジェクト直下で）: bash projects/iran_war/tools/make_bgm.sh
# 入力: assets/bgm/maou_bgm_piano38.mp3（https://maou.audio/bgm_piano38/ 、取得時は曲ページを Referer に付ける）
# 出力: assets/bgm/maou_bgm_piano38_long.wav
set -euo pipefail
SRC=assets/bgm/maou_bgm_piano38.mp3
OUT=assets/bgm/maou_bgm_piano38_long.wav
N=12
SEG=57
XF=2.5

inputs=()
for ((i = 0; i < N; i++)); do inputs+=(-t "$SEG" -i "$SRC"); done

filter=""
prev="[0:a]"
for ((i = 1; i < N; i++)); do
  out="[a$i]"
  filter+="${prev}[$i:a]acrossfade=d=${XF}:c1=tri:c2=tri${out};"
  prev="$out"
done
filter="${filter%;}"

ffmpeg -hide_banner -loglevel error -y "${inputs[@]}" -filter_complex "$filter" -map "$prev" -ar 48000 "$OUT"
ffprobe -v error -show_entries format=duration -of default=nw=1 "$OUT"
