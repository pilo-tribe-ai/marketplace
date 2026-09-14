#!/usr/bin/env bash
# Mirror the vendored plugins from the upstream monorepo into plugins/.
#
# The upstream repository is private. This script copies the plugins listed in
# scripts/vendored-plugins.txt into this repository, so that people who cannot
# read the upstream repository can still install them from this marketplace.
#
# Usage:
#   scripts/sync-upstream.sh
#
# Environment:
#   UPSTREAM_URL  Upstream repository. Default: the SSH URL below.
#                 A local path also works, which is useful for a test run.
#   UPSTREAM_REF  Branch or tag to copy from. Default: main.
#
# You need read access to the upstream repository. In CI this comes from a
# read-only deploy key. See .github/workflows/sync-upstream.yml.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_URL="${UPSTREAM_URL:-git@github.com:ai-advanced-futures/claude-code-dev-plugins.git}"
UPSTREAM_REF="${UPSTREAM_REF:-main}"

mapfile -t PLUGINS < <(sed 's/#.*//' "$ROOT/scripts/vendored-plugins.txt" | awk 'NF')
if [ "${#PLUGINS[@]}" -eq 0 ]; then
  echo "error: scripts/vendored-plugins.txt lists no plugins" >&2
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "Upstream : $UPSTREAM_URL"
echo "Ref      : $UPSTREAM_REF"
echo "Plugins  : ${#PLUGINS[@]}"
echo

# Partial clone. Only the listed plugin directories come down.
git clone --quiet --depth 1 --filter=blob:none --sparse \
  --branch "$UPSTREAM_REF" "$UPSTREAM_URL" "$WORK/upstream"

SPARSE=()
for name in "${PLUGINS[@]}"; do
  SPARSE+=("plugins/$name")
done
git -C "$WORK/upstream" sparse-checkout set "${SPARSE[@]}"

COMMIT="$(git -C "$WORK/upstream" rev-parse HEAD)"
echo "Commit   : $COMMIT"
echo

# Check every plugin before removing anything, so a bad ref cannot leave
# this repository half emptied.
missing=0
for name in "${PLUGINS[@]}"; do
  if [ ! -f "$WORK/upstream/plugins/$name/.claude-plugin/plugin.json" ]; then
    echo "error: upstream has no plugins/$name/.claude-plugin/plugin.json" >&2
    missing=1
  fi
done
[ "$missing" -eq 0 ] || exit 1

for name in "${PLUGINS[@]}"; do
  old="-"
  if [ -f "$ROOT/plugins/$name/.claude-plugin/plugin.json" ]; then
    old="$(jq -r '.version // "?"' "$ROOT/plugins/$name/.claude-plugin/plugin.json")"
  fi
  new="$(jq -r '.version // "?"' "$WORK/upstream/plugins/$name/.claude-plugin/plugin.json")"

  rm -rf "${ROOT:?}/plugins/$name"
  cp -a "$WORK/upstream/plugins/$name" "$ROOT/plugins/$name"

  if [ "$old" = "$new" ]; then
    printf '  %-14s %s\n' "$name" "$new"
  else
    printf '  %-14s %s -> %s\n' "$name" "$old" "$new"
  fi
done
echo

# Record where the copy came from.
{
  printf '{\n'
  printf '  "upstream": "%s",\n' "$UPSTREAM_URL"
  printf '  "ref": "%s",\n' "$UPSTREAM_REF"
  printf '  "commit": "%s",\n' "$COMMIT"
  printf '  "synced_at": "%s",\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '  "plugins": {\n'
  last=$(( ${#PLUGINS[@]} - 1 ))
  for i in "${!PLUGINS[@]}"; do
    name="${PLUGINS[$i]}"
    version="$(jq -r '.version // "?"' "$ROOT/plugins/$name/.claude-plugin/plugin.json")"
    comma=","
    [ "$i" -eq "$last" ] && comma=""
    printf '    "%s": "%s"%s\n' "$name" "$version" "$comma"
  done
  printf '  }\n'
  printf '}\n'
} > "$ROOT/.upstream-sync.json"

python3 "$ROOT/scripts/update-marketplace.py"
echo "Wrote .upstream-sync.json"
