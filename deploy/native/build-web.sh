#!/usr/bin/env bash
# Build the web app and swap it into place only if the build succeeds.
#   ./deploy/native/build-web.sh http://10.1.75.53:3501 ./web
# The first argument is the public base URL; the app calls <url>/v1. Needs Node 20+ and npm.
set -euo pipefail
URL="${1:?usage: build-web.sh <public-url> <out-dir>}"
OUT="${2:?usage: build-web.sh <public-url> <out-dir>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
case "$OUT" in /* | [A-Za-z]:/*) ;; *) OUT="$PWD/$OUT" ;; esac  # absolute (also C:/ under Git Bash)
mkdir -p "$(dirname "$OUT")"

cd "$ROOT/mobile"
npm ci --include=dev --no-audit --no-fund --loglevel=error  # codegen and export are dev tools, even if NODE_ENV=production
npm run --silent gen:api >/dev/null
rm -rf dist
EXPO_PUBLIC_API_URL="${URL%/}/v1" npx expo export --platform web >/dev/null
test -s dist/index.html

# Swap: the old site keeps serving until the new one is complete.
rm -rf "$OUT.new" "$OUT.old"
cp -r dist "$OUT.new"
[ -d "$OUT" ] && mv "$OUT" "$OUT.old"
mv "$OUT.new" "$OUT"
rm -rf "$OUT.old"
echo "web app built for ${URL%/}/v1 -> $OUT"
