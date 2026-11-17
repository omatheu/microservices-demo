#!/usr/bin/env bash

set -euo pipefail

repo_root=${1:-}
treeish=${2:-}
gitleaks_image=${3:-}

if [[ -z "${repo_root}" || -z "${treeish}" || -z "${gitleaks_image}" ]]; then
  echo "Usage: scan-sealed-candidate-tree.sh REPO_ROOT TREEISH GITLEAKS_IMAGE" >&2
  exit 2
fi

for command_name in docker git mktemp rm tar; do
  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "Required command not found: ${command_name}" >&2
    exit 2
  }
done

git -C "${repo_root}" rev-parse --verify "${treeish}^{tree}" >/dev/null

scan_root=$(mktemp -d /tmp/tcc-sealed-secret-scan.XXXXXX)
cleanup() {
  rm -rf -- "${scan_root}"
}
trap cleanup EXIT

git -C "${repo_root}" archive --format=tar "${treeish}^{tree}" |
  tar -xf - -C "${scan_root}"

config_path="${scan_root}/experiment/ci/gitleaks.toml"
[[ -f "${config_path}" ]] || {
  echo "The sealed candidate tree does not contain the Gitleaks policy." >&2
  exit 2
}

docker run --rm \
  -v "${scan_root}:/candidate:ro" \
  "${gitleaks_image}" dir \
  --config /candidate/experiment/ci/gitleaks.toml \
  --no-banner \
  --no-color \
  --redact \
  /candidate
