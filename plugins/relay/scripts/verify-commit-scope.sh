#!/usr/bin/env bash
# Commit whatever one verify-loop step just changed, under a conventional-commit
# message whose scope is derived from the branch.
#
#   verify-commit-scope.sh <worktree> <simplify|review|fix>
#
# Prints exactly one line on stdout: the new commit sha, `commit-failed` when the
# commit exited non-zero, or `no changes` when the tree was clean. A failed commit is
# never folded into a normal commit result.
#
# The scope is the dominant conventional-commit scope on the branch, most recent wins
# on ties. `origin/HEAD` is unset in many checkouts (it is written by `git clone`, not
# by `git fetch`), and `--max-parents=0` can print several roots on a grafted history,
# so the base falls back through the tracked default branch and takes a single root.
# `RELAY_BASE_REF` overrides the base when set.
#
# Every git call is scoped with `-C "$worktree"`: the caller's working directory is not
# guaranteed to be the worktree.
set -uo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: verify-commit-scope.sh <worktree> <simplify|review|fix>" >&2
  exit 64
fi

worktree="$1"
step="$2"

case "$step" in
  simplify|review|fix) ;;
  *)
    echo "verify-commit-scope.sh: unknown step: $step" >&2
    exit 64
    ;;
esac

if [ ! -d "$worktree" ]; then
  echo "verify-commit-scope.sh: worktree not found: $worktree" >&2
  exit 66
fi

derive_scope() {
  local base_ref
  base_ref="${RELAY_BASE_REF:-}"
  if [ -z "$base_ref" ]; then
    base_ref="$(git -C "$worktree" merge-base HEAD \
      "$(git -C "$worktree" symbolic-ref -q --short refs/remotes/origin/HEAD || echo origin/main)" 2>/dev/null)"
  fi
  if [ -z "$base_ref" ]; then
    base_ref="$(git -C "$worktree" rev-list --max-parents=0 HEAD | tail -n 1)"
  fi
  git -C "$worktree" log --format=%s "$base_ref..HEAD" 2>/dev/null |
    sed -nE 's/^[a-z]+\(([^)]+)\)!?:.*/\1/p' |
    awk 'NF {
           count[$0] += 1
           if (!($0 in first_seen)) first_seen[$0] = NR
         }
         END {
           best = ""; bc = 0; bf = 999999
           for (s in count) {
             if (count[s] > bc || (count[s] == bc && first_seen[s] < bf)) {
               best = s; bc = count[s]; bf = first_seen[s]
             }
           }
           print best
         }'
}

scope="$(derive_scope)"
case "$step" in
  simplify) msg="refactor: simplify implementation"
            [ -n "$scope" ] && msg="refactor($scope): simplify implementation" ;;
  review)   msg="fix: apply code-review findings"
            [ -n "$scope" ] && msg="fix($scope): apply code-review findings" ;;
  fix)      msg="fix: fix problems named by /verify"
            [ -n "$scope" ] && msg="fix($scope): fix problems named by /verify" ;;
esac

if [ -n "$(git -C "$worktree" status --short)" ]; then
  git -C "$worktree" add -A
  if git -C "$worktree" commit -m "$msg" >/dev/null 2>&1; then
    git -C "$worktree" rev-parse HEAD
  else
    echo "commit-failed"
  fi
else
  echo "no changes"
fi
