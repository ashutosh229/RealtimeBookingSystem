#!/usr/bin/env bash
# Run on your laptop when the VM has no Node: build the web app here and replace ~/rtbs/web on the VM.
#   ./deploy/native/push-web.sh                      # defaults below
#   VM="ssh -p 2501 student@10.1.75.53" ./deploy/native/push-web.sh http://10.1.75.53:3501
set -euo pipefail
URL="${1:-http://10.1.75.53:3501}"
VM="${VM:-ssh -p 2501 student@10.1.75.53}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$ROOT/deploy/native/build-web.sh" "$URL" "$TMP/web"
tar -C "$TMP/web" -czf - . | $VM 'set -e; cd ~/rtbs; rm -rf web.new web.old; mkdir web.new
  tar -xzf - -C web.new; [ -d web ] && mv web web.old; mv web.new web; rm -rf web.old; echo "web replaced on the VM"'
