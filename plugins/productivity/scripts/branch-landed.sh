#!/usr/bin/env bash
# Answer one question: are this branch's changes already in the upstream ref,
# even though the commits themselves are not?
#
#   branch-landed.sh <upstream-ref> <branch>       e.g. branch-landed.sh origin/main feature/x
#
# `git branch -d` refuses a squash-merged branch, because a squash rewrites the
# commits and none of them stays an ancestor of the default branch. The refusal
# looks the same for a branch that never merged at all. This script tells the two
# apart by CONTENT instead of by ancestry.
#
# Two arms, in order:
#   1. per-commit — `git cherry` marks every branch commit `-` when an equivalent
#      patch is already upstream. This catches a rebase merge and a cherry-pick.
#   2. squash — build a throw-away commit that holds the branch's whole tree on top
#      of the merge base, then ask `git cherry` whether THAT single patch is
#      upstream. This catches a squash merge.
#
# Exit code IS the verdict. Always read it, never parse the text:
#   0  CONTAINED     — the changes are upstream. Safe to `git branch -D`.
#   1  NOT-CONTAINED — no content match. Do NOT delete without asking the user.
#   2  INCONCLUSIVE  — a git call failed or there is no merge base. Same as 1: ask.
#  64  usage error
#
# Stdout is one line of evidence, naming the upstream commit when it can find it.
#
# Run this against a FRESHLY FETCHED remote ref (`git fetch origin <default>` first).
# A stale local default branch has not seen the squash commit and reads NOT-CONTAINED.
#
# Limit, by design: patch-id hashes the diff INCLUDING its context lines. If the
# default branch edited the same lines before the squash landed, the context shifted
# and the ids differ, so a genuinely merged branch reads NOT-CONTAINED. The verdict
# is one-way — CONTAINED is proof the work landed, NOT-CONTAINED is not proof it did
# not.
set -uo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: branch-landed.sh <upstream-ref> <branch>" >&2
  exit 64
fi

up="$1"
br="$2"

git rev-parse --verify --quiet "$up^{commit}" >/dev/null || {
  echo "INCONCLUSIVE: cannot resolve upstream ref '$up'"; exit 2; }
git rev-parse --verify --quiet "$br^{commit}" >/dev/null || {
  echo "INCONCLUSIVE: cannot resolve branch '$br'"; exit 2; }

base=$(git merge-base "$up" "$br" 2>/dev/null) || {
  echo "INCONCLUSIVE: git merge-base failed for '$up' and '$br'"; exit 2; }
[ -n "$base" ] || {
  echo "INCONCLUSIVE: no merge base between '$up' and '$br' (unrelated histories)"; exit 2; }

# --- arm 1: is every commit already upstream, patch by patch? ---
per=$(git cherry "$up" "$br" 2>/dev/null) || {
  echo "INCONCLUSIVE: git cherry failed for '$up' and '$br'"; exit 2; }

total=$(printf '%s\n' "$per" | grep -c '^[+-]')
missing=$(printf '%s\n' "$per" | grep -c '^+')

if [ "$total" -eq 0 ]; then
  echo "CONTAINED: '$br' has no commits beyond the merge base with '$up'"
  exit 0
fi

if [ "$missing" -eq 0 ]; then
  echo "CONTAINED: all $total commit(s) of '$br' already have an equivalent patch on '$up' (rebase or cherry-pick merge)"
  exit 0
fi

# --- arm 2: is the branch's WHOLE diff upstream as one squashed patch? ---
synth=$(git commit-tree "$br^{tree}" -p "$base" -m "branch-landed probe" 2>/dev/null) || {
  echo "INCONCLUSIVE: git commit-tree failed while building the squash probe"; exit 2; }

squash=$(git cherry "$up" "$synth" "$base" 2>/dev/null) || {
  echo "INCONCLUSIVE: git cherry failed on the squash probe"; exit 2; }

case "$squash" in
  -*)
    # Name the upstream commit that carries the patch, so the report cites a sha
    # and not only a verdict. Bounded: a squash lands soon after the merge base.
    synth_id=$(git diff-tree -p "$synth" | git patch-id --stable | awk '{print $1}')
    match=""
    if [ -n "$synth_id" ]; then
      while read -r c; do
        id=$(git diff-tree -p "$c" | git patch-id --stable | awk '{print $1}')
        if [ "$id" = "$synth_id" ]; then match="$c"; break; fi
      done < <(git rev-list --no-merges --max-count=300 "$base..$up" 2>/dev/null)
    fi
    if [ -n "$match" ]; then
      echo "CONTAINED: the $total commit(s) of '$br' landed on '$up' as squash commit $(git log -1 --format='%h %s' "$match")"
    else
      echo "CONTAINED: the combined diff of '$br' ($total commit(s)) is already on '$up' as one squashed patch"
    fi
    exit 0
    ;;
esac

echo "NOT-CONTAINED: $missing of $total commit(s) of '$br' have no equivalent patch on '$up', and the combined diff does not match a squash commit there"
exit 1
