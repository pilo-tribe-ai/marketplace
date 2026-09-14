#!/usr/bin/env bash
#
# self-teardown-test.sh — prove the claims step 4 path A depends on.
#
# wrapping-up-sessions removes the worktree it is standing in. Until v0.10.0 the skill said that
# was impossible and told the model to `cd` to the main checkout first. A worktree-isolated
# session cannot do that: its shell guard refuses any git command aimed at another checkout. So
# the skill could never finish from inside a worktree, which is the only place it normally runs.
#
# Every case below is a real git repository built from scratch. The assertions are the four facts
# the new step 4 rests on:
#
#   1. `git branch -d` REFUSES while the branch is checked out in this worktree.
#   2. `git checkout --detach` frees the branch, and `git branch -d` then ALWAYS succeeds —
#      with an upstream or without one. That is why step 3 must run its landed-ness check BEFORE
#      the detach: after it, a `-d` that exits 0 is an artifact of detaching and proves nothing.
#   3. `git worktree remove <own path>` SUCCEEDS from inside that worktree and deletes it.
#   4. A locked worktree refuses `remove` AND `remove --force`; `git worktree unlock` clears it.
#
# It also proves the main checkout is untouched — it keeps its branch and its dirty files.
#
# A second group covers the traps that an adversarial review found in the first draft of the new
# step 4, each of which ended with a branch deleted and the teardown stuck:
#
#   5. `--git-dir` vs `--git-common-dir` is NOT a valid worktree test. Below the repository root
#      git prints the first absolute and the second relative, so they differ as text in a MAIN
#      checkout. `git rev-parse --path-format=absolute --git-dir --git-common-dir` is the test that
#      holds from any directory.
#   6. `git worktree remove` accepts only a worktree's TOP level, so the path must come from
#      `git rev-parse --show-toplevel` and never from `pwd`.
#   7. `git rev-parse @{u}` fails with the SAME exit code whether the branch never had an upstream
#      or was pushed and then had its remote-tracking ref pruned. `git config --get
#      branch.<b>.merge` separates them; only the first case means the work is local-only.
#   8. A lock on a SIBLING worktree never blocks removing your own, so the lock rule must read only
#      its own worktree's block.
#   9. A worktree can be checked out on the default branch, and there the branch must NOT be
#      deleted — refs are shared, so it would break every other checkout in the repository.
#
# Exit 0 when every case passes, 1 otherwise.

set -uo pipefail

fails=0
pass() { printf 'ok    %s\n' "$1"; }
fail() { printf 'FAIL  %s\n     %s\n' "$1" "$2"; fails=$((fails + 1)); }
check() { # check <name> <expected> <actual>
  if [ "$2" = "$3" ]; then pass "$1"; else fail "$1" "expected '$2', got '$3'"; fi
}

root=$(mktemp -d "${TMPDIR:-/tmp}/self-teardown-test.XXXXXX") || exit 2
trap 'rm -rf "$root"' EXIT

# --- build a repo with a remote, a main checkout, and a feature worktree ---
mkdir -p "$root/repo"
cd "$root/repo" || exit 2
git init -q -b main .
git config user.email test@example.com
git config user.name test
echo one > f.txt
git add -A && git commit -qm init
git init -q --bare "$root/remote.git"
git remote add origin "$root/remote.git"
git push -q -u origin main

git worktree add -q "$root/wt" -b feat >/dev/null 2>&1
cd "$root/wt" || exit 2
echo two >> f.txt && git commit -qam c1
echo three >> f.txt && git commit -qam c2
git push -q -u origin feat

# squash-merge feat onto main, exactly as a GitHub squash merge lands it
cd "$root/repo" || exit 2
git merge -q --squash feat >/dev/null 2>&1
git commit -qm "squashed feat (#1)"
git push -q origin main
# leave the main checkout on a DIFFERENT branch with a dirty file, so that any stray
# `checkout`/`pull` aimed at it would be visible in the final assertions
git checkout -q -b someone-elses-work
echo scratch > untracked-scratch.txt

cd "$root/wt" || exit 2
git fetch -q origin
git worktree lock --reason "claude session wt (pid 999999 start Mon Jan 1 00:00:00 2030)" "$root/wt"

echo "--- the worktree must be removable from inside, with the branch deleted first ---"

# 1. the branch cannot be deleted while this worktree holds it
git branch -d feat >/dev/null 2>&1
check "branch -d refuses while the branch is checked out here" "1" "$?"

# 4a. a locked worktree refuses remove, and refuses a single --force too
git worktree remove "$root/wt" >/dev/null 2>&1
check "remove refuses a locked worktree" "128" "$?"
git worktree remove --force "$root/wt" >/dev/null 2>&1
check "remove --force also refuses a locked worktree" "128" "$?"

# 4b. unlock clears it
git worktree unlock "$root/wt" >/dev/null 2>&1
rc=$?
if [ "$rc" -eq 0 ] && [ ! -e "$root/repo/.git/worktrees/wt/locked" ]; then
  pass "worktree unlock clears the lock from inside the worktree"
else
  fail "worktree unlock clears the lock from inside the worktree" "rc=$rc, lock file still present"
fi

# 2a. detaching frees the branch
git checkout -q --detach
check "checkout --detach leaves HEAD detached" "HEAD" "$(git rev-parse --abbrev-ref HEAD)"

# 2b. -d now succeeds even though the branch was SQUASH-merged and is not an ancestor of main
git branch -d feat >/dev/null 2>&1
check "branch -d succeeds after detach (upstream set)" "0" "$?"
check "the branch is gone" "" "$(git branch --list feat)"

# 3. remove the worktree from inside it
git fetch -q --prune origin
git worktree remove "$root/wt" >/dev/null 2>&1
check "worktree remove succeeds from inside that worktree" "0" "$?"
if [ -d "$root/wt" ]; then
  fail "the worktree directory is gone" "$root/wt still exists"
else
  pass "the worktree directory is gone"
fi

echo
echo "--- the main checkout must be untouched ---"
cd "$root/repo" || exit 2
check "main checkout kept its branch" "someone-elses-work" "$(git rev-parse --abbrev-ref HEAD)"
check "main checkout kept its untracked file" "?? untracked-scratch.txt" "$(git status --porcelain)"
check "only the main checkout is left" "1" "$(git worktree list | wc -l | tr -d ' ')"

echo
echo "--- branch -d after detach also succeeds with NO upstream ---"
# The no-upstream variant matters: it shows the success comes from the detach, not from the
# upstream comparison, so no configuration makes `-d` a landed-ness signal again.
git branch -q feat2 "$(git rev-list -n1 origin/feat)"
git worktree add -q "$root/wt2" feat2 >/dev/null 2>&1
cd "$root/wt2" || exit 2
git branch --unset-upstream >/dev/null 2>&1
git checkout -q --detach
git branch -d feat2 >/dev/null 2>&1
check "branch -d succeeds after detach (no upstream)" "0" "$?"
git worktree remove "$root/wt2" >/dev/null 2>&1

echo
echo "--- the worktree test must hold from a subdirectory ---"
# 5. the naive test misreads a MAIN checkout as a worktree once the cwd is below the root
mkdir -p "$root/repo/sub"
cd "$root/repo/sub" || exit 2
naive_dir=$(git rev-parse --git-dir)
naive_common=$(git rev-parse --git-common-dir)
if [ "$naive_dir" != "$naive_common" ]; then
  pass "the naive --git-dir/--git-common-dir test misreads a main checkout from a subdirectory"
else
  fail "the naive --git-dir/--git-common-dir test misreads a main checkout from a subdirectory" \
       "they matched ('$naive_dir'), so this git build does not reproduce the trap"
fi
abs_dir=$(git rev-parse --path-format=absolute --git-dir)
abs_common=$(git rev-parse --path-format=absolute --git-common-dir)
check "--path-format=absolute reads a main checkout correctly from a subdirectory" "same" \
      "$([ "$abs_dir" = "$abs_common" ] && echo same || echo different)"

git worktree add -q "$root/wt3" -b feat3 >/dev/null 2>&1
mkdir -p "$root/wt3/pkg/app"
cd "$root/wt3/pkg/app" || exit 2
abs_dir=$(git rev-parse --path-format=absolute --git-dir)
abs_common=$(git rev-parse --path-format=absolute --git-common-dir)
check "--path-format=absolute reads a worktree correctly from a subdirectory" "different" \
      "$([ "$abs_dir" = "$abs_common" ] && echo same || echo different)"

# 6. remove needs the TOP level, not the cwd
git worktree remove "$root/wt3/pkg/app" >/dev/null 2>&1
check "worktree remove refuses a subdirectory path (so pwd is the wrong source)" "128" "$?"
top=$(git rev-parse --show-toplevel)
# compare real paths: on macOS $TMPDIR is /var/... while git prints /private/var/...
want=$(cd "$root/wt3" && pwd -P)
check "show-toplevel gives the worktree root" "$want" "$top"
git checkout -q --detach
git worktree remove "$top" >/dev/null 2>&1
check "worktree remove accepts the show-toplevel path" "0" "$?"
cd "$root/repo" || exit 2
git branch -q -D feat3 >/dev/null 2>&1

echo
echo "--- a pruned upstream must not read as \"never pushed\" ---"
# 7. both states fail @{u} identically; branch.<b>.merge separates them
git branch -q never-pushed main
git worktree add -q "$root/wt4" never-pushed >/dev/null 2>&1
cd "$root/wt4" || exit 2
git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1
rc_never=$?
cfg_never=$(git config --get branch.never-pushed.merge)
cd "$root/repo" || exit 2
git worktree remove --force "$root/wt4" >/dev/null 2>&1
git branch -q -D never-pushed >/dev/null 2>&1

git branch -q pushed-then-pruned main
git push -q -u origin pushed-then-pruned
git push -q origin --delete pushed-then-pruned
git fetch -q --prune origin
git worktree add -q "$root/wt5" pushed-then-pruned >/dev/null 2>&1
cd "$root/wt5" || exit 2
git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1
rc_pruned=$?
cfg_pruned=$(git config --get branch.pushed-then-pruned.merge)
check "@{u} fails the same way in both states" "$rc_never" "$rc_pruned"
check "a branch that never had an upstream has no branch.<b>.merge" "" "$cfg_never"
check "a pushed-then-pruned branch still has branch.<b>.merge" "refs/heads/pushed-then-pruned" \
      "$cfg_pruned"
cd "$root/repo" || exit 2
git worktree remove --force "$root/wt5" >/dev/null 2>&1
git branch -q -D pushed-then-pruned >/dev/null 2>&1

echo
echo "--- a sibling worktree's lock must not block your own removal ---"
# 8. porcelain shows every lock; only your own matters
git worktree add -q "$root/wtA" -b featA >/dev/null 2>&1
git worktree add -q "$root/wtB" -b featB >/dev/null 2>&1
git worktree lock --reason "claude session B (pid 999999 start Mon Jan 1 00:00:00 2030)" "$root/wtB"
cd "$root/wtA" || exit 2
if git worktree list --porcelain | grep -q "^locked claude session B"; then
  pass "porcelain shows a sibling worktree's lock, so the rule must read only its own block"
else
  fail "porcelain shows a sibling worktree's lock, so the rule must read only its own block" \
       "no sibling lock line found"
fi
git checkout -q --detach
git branch -D featA >/dev/null 2>&1
git worktree remove "$root/wtA" >/dev/null 2>&1
check "your own worktree removes while a sibling stays locked" "0" "$?"
cd "$root/repo" || exit 2
git worktree unlock "$root/wtB" >/dev/null 2>&1
git worktree remove --force "$root/wtB" >/dev/null 2>&1
git branch -q -D featB >/dev/null 2>&1

echo
echo "--- a worktree checked out on the default branch must keep it ---"
# 9. deleting the default branch here would break every other checkout
git worktree add -q "$root/wtmain" main >/dev/null 2>&1
cd "$root/wtmain" || exit 2
check "a worktree can sit on the default branch" "main" "$(git rev-parse --abbrev-ref HEAD)"
git checkout -q --detach
git branch -d main >/dev/null 2>&1
rc_del=$?
check "nothing in git stops you deleting the default branch from a worktree" "0" "$rc_del"
# restore it and show the damage a delete would do to the OTHER checkout
git branch -q main "$(git rev-list -n1 origin/main)"
cd "$root/repo" || exit 2
git worktree remove --force "$root/wtmain" >/dev/null 2>&1

echo
if [ "$fails" -eq 0 ]; then
  echo "all cases pass"
  exit 0
fi
echo "$fails case(s) failed"
exit 1
