#!/usr/bin/env bash
# Fixture matrix for branch-landed.sh.
#
#   branch-landed-test.sh
#
# Each case builds a throw-away repository, does one thing to `main`, and checks the
# exit code of branch-landed.sh. Every case also prints whether `git branch -d`
# refused, because that refusal is the ONLY door into the script — a case where
# `-d` succeeds never reaches it and proves nothing.
#
# Exit 0 when every case matches, 1 otherwise.
set -uo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/branch-landed.sh"
ROOT="${TMPDIR:-/tmp}/branch-landed-test.$$"
rm -rf "$ROOT"; mkdir -p "$ROOT"
trap 'rm -rf "$ROOT"' EXIT

fails=0

mkrepo() {
  rm -rf "$1"; mkdir -p "$1"; cd "$1" || exit 1
  git init -q -b main
  git config user.email test@example.com
  git config user.name test
  printf 'l1\nl2\nl3\nl4\nl5\n' > a.txt; git add .; git commit -qm base
  git checkout -qb feat
  printf 'l1\nl2\nl3\nl4\nl5\nBRANCH\n' > a.txt; git commit -qam c1
  echo two > b.txt; git add .; git commit -qm c2
  git checkout -q main
}

# label, setup commands run on main, expected exit code
t() {
  local label="$1" setup="$2" want="$3" dir refused got
  dir="$ROOT/$(echo "$label" | tr -cd 'a-z0-9')"
  mkrepo "$dir" >/dev/null 2>&1
  cd "$dir" || exit 1
  eval "$setup" >/dev/null 2>&1
  if git branch -d feat >/dev/null 2>&1; then refused=no; else refused=yes; fi
  "$SCRIPT" main feat >/dev/null 2>&1
  got=$?
  if [ "$got" = "$want" ]; then
    printf 'ok    %-44s branch-d-refused=%-3s exit=%s\n' "$label" "$refused" "$got"
  else
    printf 'FAIL  %-44s branch-d-refused=%-3s exit=%s want=%s\n' "$label" "$refused" "$got" "$want"
    fails=$((fails + 1))
  fi
}

echo "branch-landed.sh — git $(git --version | awk '{print $3}')"
echo
echo "--- landed: must read CONTAINED (exit 0) ---"
t "squash merged" \
  'git merge --squash feat; git commit -qm "feat (#42)"' 0
t "squash merged, then main advanced" \
  'git merge --squash feat; git commit -qm sq; echo u>c.txt; git add .; git commit -qm o' 0
t "squash merged, then main edits the same file" \
  'git merge --squash feat; git commit -qm sq; echo three>>b.txt; git commit -qam edit' 0
t "main advances first, then squash merged" \
  'echo u>c.txt; git add .; git commit -qm o; git merge --squash feat; git commit -qm sq' 0
t "rebase merged (new shas)" \
  'GIT_COMMITTER_DATE="2030-01-01T00:00:00" git cherry-pick feat~1 feat' 0
t "squash merged, then reverted on main" \
  'git merge --squash feat; git commit -qm sq; git revert --no-edit HEAD' 0

echo
echo "--- not landed: must read NOT-CONTAINED (exit 1) ---"
t "never merged" \
  'true' 1
t "never merged, main advanced" \
  'echo u>c.txt; git add .; git commit -qm o' 1
t "only 1 of 2 commits landed" \
  'GIT_COMMITTER_DATE="2030-01-01T00:00:00" git cherry-pick feat~1' 1
t "squash carried an extra edit" \
  'git merge --squash feat; echo x>>b.txt; git add .; git commit -qm sq' 1

echo
echo "--- known limit: same-line edit before the squash shifts the diff context ---"
t "main edits the same lines, then squash merged" \
  'printf "l1\nl2\nCHANGED\nl4\nl5\n" > a.txt; git commit -qam o; git merge --squash feat; git commit -qm sq' 1

echo
echo "--- inconclusive: must read INCONCLUSIVE (exit 2) ---"
d="$ROOT/nobase"; rm -rf "$d"; mkdir -p "$d"; cd "$d" || exit 1
git init -q -b main >/dev/null 2>&1
git config user.email test@example.com; git config user.name test
echo a > a.txt; git add .; git commit -qm a >/dev/null 2>&1
git checkout -q --orphan feat >/dev/null 2>&1
git rm -rqf . >/dev/null 2>&1
echo z > z.txt; git add .; git commit -qm z >/dev/null 2>&1
git checkout -q main >/dev/null 2>&1
"$SCRIPT" main feat >/dev/null 2>&1; got=$?
if [ "$got" = 2 ]; then
  printf 'ok    %-44s exit=%s\n' "unrelated histories, no merge base" "$got"
else
  printf 'FAIL  %-44s exit=%s want=2\n' "unrelated histories, no merge base" "$got"
  fails=$((fails + 1))
fi
"$SCRIPT" main no-such-branch >/dev/null 2>&1; got=$?
if [ "$got" = 2 ]; then
  printf 'ok    %-44s exit=%s\n' "branch does not exist" "$got"
else
  printf 'FAIL  %-44s exit=%s want=2\n' "branch does not exist" "$got"
  fails=$((fails + 1))
fi

echo
if [ "$fails" -eq 0 ]; then
  echo "all cases pass"
  exit 0
fi
echo "$fails case(s) failed"
exit 1
