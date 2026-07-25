#!/usr/bin/env bash
# Build the README highlights GIF from the finished promo.
#
# Why a GIF at all: GitHub strips <video> tags from README files, and a release
# asset URL downloads rather than plays. An animated GIF is the only thing that
# reliably plays inline in a README with zero clicks, so it carries the story
# while the full MP4 (with sound) lives on the release page.
#
# Usage: tools/make-readme-gif.sh PROMO.mp4 OUT.gif [WIDTH] [FPS]
set -euo pipefail

SRC="${1:?promo mp4}"
OUT="${2:?output gif}"
WIDTH="${3:-700}"
FPS="${4:-10}"

# start,duration pairs - one short excerpt per story beat
SEGMENTS=(
  "2.6,2.0"    # hero: light streams through the portal
  "11.2,1.8"   # the problem: context window at 95%
  "16.6,3.4"   # /to-codex typing out
  "25.6,2.4"   # model picker landing on the recommendation
  "35.2,3.4"   # transfer verified + SUCCESS
  "43.2,3.4"   # Codex opens on the same conversation
  "51.2,2.4"   # what travels
  "58.0,3.0"   # the install command
  "63.0,1.7"   # title card
)

# Work beside the output file. On Windows the ffmpeg binary is native, so paths
# written into the concat list must be Windows-style - cygpath -m handles that
# when running under Git Bash and is a harmless no-op elsewhere.
TMP="$(dirname "$OUT")/.gifwork"
mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT
winpath() { command -v cygpath >/dev/null 2>&1 && cygpath -m "$1" || printf '%s' "$1"; }

LIST="$TMP/list.txt"
: > "$LIST"
i=0
for seg in "${SEGMENTS[@]}"; do
  ss="${seg%%,*}"; dur="${seg##*,}"
  part="$TMP/p$(printf '%02d' $i).mp4"
  ffmpeg -v error -y -ss "$ss" -t "$dur" -i "$SRC" \
    -an -vf "scale=${WIDTH}:-2:flags=lanczos,fps=${FPS}" \
    -c:v libx264 -preset fast -crf 20 "$part"
  echo "file '$(winpath "$part")'" >> "$LIST"
  i=$((i+1))
done

ffmpeg -v error -y -f concat -safe 0 -i "$(winpath "$LIST")" -c copy "$TMP/joined.mp4"
ffmpeg -v error -y -i "$TMP/joined.mp4" \
  -vf "fps=${FPS},scale=${WIDTH}:-1:flags=lanczos,palettegen=stats_mode=diff" "$TMP/pal.png"
ffmpeg -v error -y -i "$TMP/joined.mp4" -i "$TMP/pal.png" \
  -lavfi "fps=${FPS},scale=${WIDTH}:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle" \
  "$OUT"

SIZE=$(ffprobe -v error -show_entries format=size -of csv=p=0 "$OUT" 2>/dev/null || stat -c %s "$OUT")
echo "wrote $OUT (${WIDTH}px, ${FPS}fps, $(awk "BEGIN{printf \"%.2f\", $SIZE/1000000}") MB)"
