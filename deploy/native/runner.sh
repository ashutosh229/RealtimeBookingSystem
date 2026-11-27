#!/usr/bin/env bash
# Register this VM as the GitHub Actions self-hosted runner that .github/workflows/deploy.yml targets.
#   1. GitHub repo -> Settings -> Actions -> Runners -> New self-hosted runner -> copy the token (valid 1 hour)
#   2. ./deploy/native/runner.sh <token>
#   3. ./deploy/native/deploy.sh      # adds the runner to supervisord so it restarts with everything else
# Then Actions -> deploy -> Run workflow deploys and smoke-tests the chosen branch.
set -euo pipefail
TOKEN="${1:?usage: runner.sh TOKEN  (from GitHub: Settings, Actions, Runners, New self-hosted runner)}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIR="$HOME/actions-runner"
REPO_URL="$(git -C "$ROOT" remote get-url origin | sed -E 's#^git@github.com:#https://github.com/#; s#\.git$##')"

mkdir -p "$DIR"; cd "$DIR"
if [ ! -x ./config.sh ]; then
  VER="$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest | sed -nE 's/.*"tag_name": *"v([^"]+)".*/\1/p')"
  echo "downloading actions runner $VER"
  curl -fsSL -o runner.tgz "https://github.com/actions/runner/releases/download/v$VER/actions-runner-linux-x64-$VER.tar.gz"
  tar -xzf runner.tgz && rm runner.tgz
fi
./config.sh --unattended --replace --url "$REPO_URL" --token "$TOKEN" \
  --name "$(hostname)" --labels rtbs-vm --work _work
echo "registered with label rtbs-vm; now run ./deploy/native/deploy.sh to start it under supervisord"
