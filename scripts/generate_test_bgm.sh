#!/usr/bin/env bash
# Generate placeholder BGM tracks (sine + envelope) for each mood, via ffmpeg lavfi.
# Use until proper royalty-free assets are dropped into data/channels_assets/<channel>/bgm/<mood>/.
#
# Usage:
#   scripts/generate_test_bgm.sh [channel_id]
# (default channel_id: daily-science)

set -euo pipefail

CHANNEL_ID="${1:-daily-science}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_BASE="$REPO_ROOT/data/channels_assets/$CHANNEL_ID/bgm"

mkdir -p \
  "$OUT_BASE/calm" "$OUT_BASE/bright" "$OUT_BASE/tense" \
  "$OUT_BASE/emotional" "$OUT_BASE/funny" "$OUT_BASE/mysterious"

DUR=30           # seconds per clip
FADE=2           # fade in/out length
SR=44100

# Helper: 2-tone sine with tremolo + fade-in/out + final volume
gen() {
  local out="$1" f1="$2" f2="$3" trem="$4" vol="$5" weights="$6"
  ffmpeg -y -loglevel error \
    -f lavfi -i "sine=frequency=${f1}:duration=${DUR}" \
    -f lavfi -i "sine=frequency=${f2}:duration=${DUR}" \
    -filter_complex \
      "[0:a][1:a]amix=inputs=2:duration=longest:weights=${weights},\
tremolo=f=${trem}:d=0.25,\
afade=in:st=0:d=${FADE},\
afade=out:st=$((DUR-FADE)):d=${FADE},\
volume=${vol}" \
    -ar $SR -ac 2 -b:a 192k "$out"
  echo "  ✓ $out"
}

echo "🎵 Generating test BGM in $OUT_BASE"

# calm — soft low sine 220 Hz + 330 Hz harmonic, slow tremolo
gen "$OUT_BASE/calm/test_calm.mp3"             220 330 0.4 0.55 "1 0.5"
# bright — 440 + 550 (major third), slightly faster tremolo
gen "$OUT_BASE/bright/test_bright.mp3"         440 550 0.9 0.55 "1 0.6"
# tense — 110 drone + dissonant 165 (perfect fifth), slow throbbing tremolo
gen "$OUT_BASE/tense/test_tense.mp3"           110 165 0.3 0.50 "1 0.7"
# emotional — 196 + 247 (minor third), slow tremolo
gen "$OUT_BASE/emotional/test_emotional.mp3"   196 247 0.4 0.55 "1 0.5"
# funny — 587 + 880 (octave with fifth feel), fast tremolo
gen "$OUT_BASE/funny/test_funny.mp3"           587 880 1.6 0.50 "1 0.5"
# mysterious — 130 drone + 196 (perfect fifth), very slow tremolo
gen "$OUT_BASE/mysterious/test_mysterious.mp3" 130 196 0.2 0.45 "1 0.6"

echo "✅ Done — drop higher-quality royalty-free tracks (DOVA-SYNDROME, 甘茶の音楽工房, etc.)"
echo "   into the matching mood folder to override these placeholders."
