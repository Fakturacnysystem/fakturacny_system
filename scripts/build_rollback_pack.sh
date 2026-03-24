#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
out_dir="${1:-$repo_root/runs/rollback_pack}"
mkdir -p "$out_dir"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
pack_dir="$out_dir/$timestamp"
mkdir -p "$pack_dir"

git -C "$repo_root" rev-parse HEAD > "$pack_dir/git_head.txt"
git -C "$repo_root" status --short > "$pack_dir/git_status.txt" || true
git -C "$repo_root" diff -- src tests scripts .github/workflows > "$pack_dir/tracked_diff.patch" || true
find "$repo_root" -maxdepth 1 -name 'config*.yaml' -print0 | while IFS= read -r -d '' cfg; do
  cp "$cfg" "$pack_dir/"
done

echo "$pack_dir"
