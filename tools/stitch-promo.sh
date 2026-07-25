#!/usr/bin/env bash
# Stitch the claude-codex-bridge promo from its sources:
#
#   [ AI hero shot + lower-third title ] -> [ motion-graphics core ] -> [ AI end card ]
#
# The bookends are generative-video clips (abstract light / large title text -
# what those models do well). The core is tools/make-promo.py output, where
# every command string is rendered from source so it is always exact.
#
# Audio is deliberately staged in two parts:
#   * The opening plays the hero clip's OWN native audio, alone - no music over it.
#   * The music bed starts as the opening crossfades into the product scenes and
#     carries the rest of the piece.
# The bed runs through dynaudnorm because generated music tends to ramp up or dip
# mid-track; normalising guarantees a steady level instead of "kicking in later".
#
# Usage:
#   tools/stitch-promo.sh HERO.mp4 CORE.mp4 ENDCARD.mp4 OVERLAY.png BED.wav OUT.mp4
set -euo pipefail

HERO="${1:?hero clip}"
CORE="${2:?core clip}"
END="${3:?end card clip}"
OVERLAY="${4:?lower-third png}"
BED="${5:?music bed}"
OUT="${6:?output path}"

HERO_LEN=6.5      # seconds of the hero shot to keep
END_IN=12.4       # in-point of the clean end card
END_OUT=15.0      # out-point
XF1=0.6           # hero -> core crossfade
XF2=0.5           # core -> end card crossfade
TITLE_IN=0.9      # lower-third fade in
TITLE_OUT=4.9     # lower-third fade out (clears before the crossfade)
HERO_VOL=1.00     # native hero audio - it owns the opening on its own
BED_VOL=0.92      # trim after loudnorm has already set the bed's loudness

# awk for arithmetic - bc is not present in Git Bash / minimal images
calc() { awk "BEGIN{printf \"%.3f\", $1}"; }

CORE_LEN=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$CORE")
OFF1=$(calc "$HERO_LEN - $XF1")
MID_LEN=$(calc "$HERO_LEN + $CORE_LEN - $XF1")
OFF2=$(calc "$MID_LEN - $XF2")
TOTAL=$(calc "$MID_LEN + ($END_OUT - $END_IN) - $XF2")
MUSIC_START="$OFF1"   # bed enters exactly as the opening starts crossfading out

echo "core=${CORE_LEN}s  xfade1@${OFF1}s  xfade2@${OFF2}s  music@${MUSIC_START}s  total=${TOTAL}s"

ffmpeg -y -i "$HERO" -i "$CORE" -i "$END" -loop 1 -i "$OVERLAY" -i "$BED" -filter_complex "
[0:v]trim=0:${HERO_LEN},setpts=PTS-STARTPTS,scale=1920:1080,fps=24,format=yuva420p[hv];
[3:v]trim=0:${HERO_LEN},setpts=PTS-STARTPTS,scale=1920:1080,fps=24,format=yuva420p,
     fade=t=in:st=${TITLE_IN}:d=0.7:alpha=1,fade=t=out:st=${TITLE_OUT}:d=0.7:alpha=1[ov];
[hv][ov]overlay=0:0:format=auto,format=yuv420p[v0];
[1:v]scale=1920:1080,fps=24,format=yuv420p[v1];
[2:v]trim=${END_IN}:${END_OUT},setpts=PTS-STARTPTS,scale=1920:1080,fps=24,format=yuv420p[v2];
[v0][v1]xfade=transition=fade:duration=${XF1}:offset=${OFF1}[x1];
[x1][v2]xfade=transition=fade:duration=${XF2}:offset=${OFF2}[vout];
[0:a]atrim=0:${HERO_LEN},asetpts=N/SR/TB,volume=${HERO_VOL},
     afade=t=out:st=$(calc "$HERO_LEN - 0.8"):d=0.8,aresample=48000,apad[ha];
[4:a]atrim=0:$(calc "$TOTAL - $MUSIC_START"),asetpts=N/SR/TB,
     acompressor=threshold=0.15:ratio=4:attack=20:release=250:makeup=2,
     loudnorm=I=-15:TP=-1.2:LRA=6,dynaudnorm=f=200:g=13:p=0.9:m=8,
     alimiter=limit=0.95,volume=${BED_VOL},
     afade=t=in:st=0:d=1.0,afade=t=out:st=$(calc "$TOTAL - $MUSIC_START - 2.6"):d=2.6,
     aresample=48000,adelay=$(calc "$MUSIC_START * 1000")|$(calc "$MUSIC_START * 1000")[ma];
[ha][ma]amix=inputs=2:duration=longest:normalize=0,atrim=0:${TOTAL}[aout]
" -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset slow -crf 19 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart "$OUT"

echo "wrote $OUT"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT"
