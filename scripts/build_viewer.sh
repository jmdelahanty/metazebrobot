#!/usr/bin/env bash
# Build Avivator (Viv's OME-TIFF viewer, MIT) from source and install it as
# static files served by MetaZebrobot at /viewer/.
#
#   scripts/build_viewer.sh            # build at the pinned commit
#   VIV_COMMIT=<sha> scripts/build_viewer.sh
#
# Needs Node (corepack provides the repo's pnpm) and network access once. The
# built files are committed, so the running service never needs Node.
# docs/screening_images_design.md, "Viewer".
set -euo pipefail

VIV_REPO="https://github.com/hms-dbmi/viv"
VIV_COMMIT="${VIV_COMMIT:-f7baf858f495f3c001a79e4c85fb6c92e0fe7ddf}"   # main at @hms-dbmi/viv 0.23.0
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$REPO_ROOT/src/metazebrobot/static/viewer"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git clone --quiet "$VIV_REPO" "$WORK/viv"
git -C "$WORK/viv" checkout --quiet "$VIV_COMMIT"
cd "$WORK/viv"
mkdir -p "$WORK/bin"
corepack enable --install-directory "$WORK/bin"
export PATH="$WORK/bin:$PATH"
pnpm install --frozen-lockfile
pnpm --filter "./packages/**" build
cd sites/avivator
pnpm exec vite build --base /viewer/

rm -rf "$OUT"
mkdir -p "$OUT"
cp -r dist/. "$OUT/"
cp "$WORK/viv/LICENSE" "$OUT/LICENSE"
cat > "$OUT/BUILD_INFO.txt" <<EOF
Avivator built from $VIV_REPO at commit $VIV_COMMIT
Built $(date -u +%Y-%m-%dT%H:%M:%SZ) by scripts/build_viewer.sh (base path /viewer/).
EOF
echo "Installed Avivator into $OUT"
