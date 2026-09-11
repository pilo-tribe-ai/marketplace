#!/usr/bin/env bash
# relay: worktree isolation preflight (spec §5.1). Two modes; both read git via
# plumbing only and PRINT a parseable KEY=value block to stdout (state crosses the
# Bash->Claude boundary as printed stdout, never env vars — same convention as
# check-deps.sh / parse-engine-agent.sh). SOURCED or EXECUTED:
#   source "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --classify
#   bash   "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --create <base-ref> [slug]
#   bash   "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --branch-guard [implement|verify]
#
# --branch-guard [implement|verify] (read-only; defaults to implement). Refuses
# the default branch and a detached HEAD, printing the named variant's exact
# wording, because a loop that commits every round must not run on either.
# Calls _wt_classify itself and reads its printed block rather than
# re-deriving anything. Exit 0 when the state is worktree or stray and the
# branch is not DETACHED; exit 1 on every refusal, printing the message to
# stdout; exit 2 on an unknown variant.
#   bash   "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --create <base-ref> [--at <path>] [slug]
#   bash   "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --resolve <value>
#
# --resolve <value> (read-only). Resolves a caller-supplied `--worktree` value
# against `git worktree list --porcelain`. Emits:
#   RELAY_WT_RESOLVED=<current|path|branch|missing>
#   RELAY_WT_TARGET=<absolute path (current/path/branch) or the value verbatim (missing)>
#   RELAY_WT_TARGET_BRANCH=<branch at target, DETACHED, or empty on missing>
# Resolution order: `current` -> an existing linked-worktree path (canonicalized
# via `cd <value> && pwd -P`, matched against porcelain `worktree` lines) -> a
# branch name (matched against porcelain `branch refs/heads/<value>` lines) ->
# `missing`. A directory that both IS a linked worktree AND shares its name with
# a branch resolves as `path` (path wins). A directory that exists but is not a
# linked worktree of this repo is still tried as a branch name.
#   bash   "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-preflight.sh" --active
#
# --active (read-only). Prints RELAY_WT_ACTIVE=<absolute path of the repository
# top level this call runs in>. The commands run it after the Step 0.5 gate has
# resolved the workspace, so the printed path is the one the Step 1+ Workflow
# will use. It is a script mode and not an inline rev-parse because a session
# isolated in a git worktree refuses an inline command substitution (issue #110).
#
# --classify (read-only). Emits:
#   RELAY_WT_STATE=<worktree|main|stray|not-git>
#   RELAY_WT_BRANCH=<current branch or DETACHED>
#   RELAY_WT_DEFAULT=<default branch, e.g. main>
#   RELAY_WT_REPO_ROOT=<toplevel>
#   RELAY_WT_WORKTREE_ROOT=<path if in a linked worktree, else empty>
# State rules:
#   not-git  — `git rev-parse` fails -> returns NON-ZERO (command aborts).
#   worktree — any linked worktree of this repo (git-common-dir != git-dir).
#   main     — on the default branch in the primary checkout.
#   stray    — any other case in the primary checkout (non-default branch OR detached).
#
# --create <base-ref> [slug] (mutating; only called post-confirmation). Steps:
#   0a. read .claude/relay.json from the primary checkout; when present but invalid JSON,
#       fail fast here (no worktree is created). Absence or an empty/absent `bootstrap`
#       key is a clean no-op and execution continues to step 1 exactly as today.
#   1. git fetch origin <default>   (the "pull latest from main" requirement — only
#      reached when CREATING a worktree, never mutating the user's checked-out branch).
#   2. base = the passed <base-ref> (caller passes origin/<default> for the `main`
#      state or HEAD for the `stray` state).
#   3. generate a slug-based worktree name under .claude/worktrees/ (reuse the session
#      slug, accepted as the optional 2nd positional; suffix -N on collision).
#   4. git worktree add .claude/worktrees/<name> -b relay/<slug> <base-ref>.
#   5. read .claude/relay.json from the primary checkout; when `bootstrap` is
#      non-empty, run it in the new worktree and route all output to stderr.
#   6. print RELAY_WT_CREATED_PATH=<absolute path> and RELAY_WT_BOOTSTRAP=<ran|skipped>.
# Creation deliberately uses `git worktree add` (deterministic base ref) rather than
# EnterWorktree({name}) — EnterWorktree's base is governed by the global
# `worktree.baseRef` setting and can't be chosen per-call (spec §5.1 closing note,
# §9 risk-3). The session then enters via the path form, EnterWorktree({path: ...}).

# Default branch resolution: symbolic-ref origin/HEAD -> fallback origin/main -> main.
_wt_default_branch() {
  local d
  d="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null)"
  if [ -n "$d" ]; then
    printf '%s' "${d#origin/}"
    return 0
  fi
  if git rev-parse --verify --quiet origin/main >/dev/null 2>&1; then
    printf '%s' "main"
    return 0
  fi
  printf '%s' "main"
}

_wt_bootstrap_command() {
  local toplevel="$1" config cmd
  config="$toplevel/.claude/relay.json"
  if [ ! -f "$config" ]; then
    printf '%s' ""
    return 0
  fi
  if ! command -v jq >/dev/null 2>&1; then
    echo "[relay] error: jq is required to read .claude/relay.json" >&2
    return 1
  fi
  if ! cmd="$(jq -r '.bootstrap // ""' "$config" 2>/dev/null)"; then
    echo "[relay] error: .claude/relay.json is not valid JSON" >&2
    return 1
  fi
  printf '%s' "$cmd"
}

_wt_classify() {
  # not-git -> non-zero, abort.
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "RELAY_WT_STATE=not-git" >&2
    return 1
  fi

  local common_dir git_dir toplevel default branch worktree_root state
  common_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"
  git_dir="$(git rev-parse --path-format=absolute --git-dir 2>/dev/null)"
  toplevel="$(git rev-parse --show-toplevel 2>/dev/null)"
  default="$(_wt_default_branch)"

  # current branch (DETACHED if no symbolic HEAD).
  branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null)"
  [ -z "$branch" ] && branch="DETACHED"

  # A linked worktree has git-common-dir != git-dir. Any linked worktree of
  # this repo classifies as `worktree`, whether it lives under
  # .claude/worktrees/ or was hand-made elsewhere with `git worktree add`.
  worktree_root=""
  if [ "$common_dir" != "$git_dir" ]; then
    state="worktree"
    worktree_root="$toplevel"
  elif [ "$branch" = "$default" ]; then
    state="main"
  else
    state="stray"
  fi

  printf 'RELAY_WT_STATE=%s\n' "$state"
  printf 'RELAY_WT_BRANCH=%s\n' "$branch"
  printf 'RELAY_WT_DEFAULT=%s\n' "$default"
  printf 'RELAY_WT_REPO_ROOT=%s\n' "$toplevel"
  printf 'RELAY_WT_WORKTREE_ROOT=%s\n' "$worktree_root"
  return 0
}

_wt_branch_guard() {
  local variant="${1:-implement}"
  local msg_main msg_detached msg_notgit
  case "$variant" in
    implement)
      msg_main="implement: --verify runs a loop that edits files and commits them. It refuses the default branch. Create a branch first, or drop --verify."
      msg_detached="implement: --verify refuses a detached HEAD. The loop commits every round, and commits on a detached HEAD are not on any branch. Check out a branch first."
      msg_notgit="implement: could not read the git state. Run this command inside a git checkout."
      ;;
    verify)
      msg_main="verify: refusing to run on the default branch. This loop edits files and commits them. Create a branch first."
      msg_detached="verify: refusing to run on a detached HEAD. This loop commits every round, and commits on a detached HEAD are not on any branch. Check out a branch first."
      msg_notgit="verify: could not read the git state. Run this command inside a git checkout."
      ;;
    *)
      echo "[relay] error: usage: worktree-preflight.sh --branch-guard [implement|verify]" >&2
      return 2
      ;;
  esac

  local block
  block="$(_wt_classify 2>/dev/null)"
  if [ -z "$block" ]; then
    echo "$msg_notgit"
    return 1
  fi
  printf '%s\n' "$block"

  local state branch
  state="$(printf '%s\n' "$block" | sed -nE 's/^RELAY_WT_STATE=(.*)$/\1/p')"
  branch="$(printf '%s\n' "$block" | sed -nE 's/^RELAY_WT_BRANCH=(.*)$/\1/p')"

  case "$state" in
    worktree|stray) ;;
    main) echo "$msg_main"; return 1 ;;
    *)    echo "$msg_notgit"; return 1 ;;
  esac
  if [ "$branch" = "DETACHED" ]; then
    echo "$msg_detached"
    return 1
  fi
  return 0
}

_wt_resolve() {
  local value="$1"
  if [ -z "$value" ]; then
    echo "[relay] error: --resolve requires a value" >&2
    return 1
  fi
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "RELAY_WT_STATE=not-git" >&2
    return 1
  fi

  if [ "$value" = "current" ]; then
    local cur cur_branch
    cur="$(git rev-parse --show-toplevel 2>/dev/null)"
    cur_branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null)"
    [ -z "$cur_branch" ] && cur_branch="DETACHED"
    printf 'RELAY_WT_RESOLVED=current\n'
    printf 'RELAY_WT_TARGET=%s\n' "$cur"
    printf 'RELAY_WT_TARGET_BRANCH=%s\n' "$cur_branch"
    return 0
  fi

  local porcelain
  porcelain="$(git worktree list --porcelain 2>/dev/null)"

  # Try the value as an existing directory path, canonicalized.
  local canon=""
  if [ -d "$value" ]; then
    canon="$(cd "$value" 2>/dev/null && pwd -P)"
  fi

  if [ -n "$canon" ]; then
    # Walk the porcelain blocks looking for a `worktree` line whose
    # canonicalized form matches, then read that block's branch/detached line.
    local wpath wbranch found=0
    while IFS= read -r line; do
      case "$line" in
        worktree\ *)
          wpath="${line#worktree }"
          wbranch=""
          ;;
        branch\ *)
          wbranch="${line#branch refs/heads/}"
          ;;
        detached)
          wbranch="DETACHED"
          ;;
        "")
          if [ -n "$wpath" ]; then
            local wcanon
            wcanon="$(cd "$wpath" 2>/dev/null && pwd -P)"
            if [ "$wcanon" = "$canon" ]; then
              printf 'RELAY_WT_RESOLVED=path\n'
              # Print the canonical path, never the porcelain string. The gate and
              # implementing-spec compare this value to a toplevel from `git rev-parse`,
              # which is always canonical; a raw /tmp path would never match its
              # /private/tmp toplevel.
              printf 'RELAY_WT_TARGET=%s\n' "$wcanon"
              printf 'RELAY_WT_TARGET_BRANCH=%s\n' "$wbranch"
              found=1
              break
            fi
          fi
          wpath=""
          ;;
      esac
    done <<EOF_PORCELAIN
$porcelain

EOF_PORCELAIN
    if [ "$found" = "1" ]; then
      return 0
    fi
  fi

  # Try the value as a branch name.
  local bwpath="" bwbranch="" bfound=0
  local pwpath=""
  while IFS= read -r line; do
    case "$line" in
      worktree\ *)
        pwpath="${line#worktree }"
        ;;
      branch\ refs/heads/*)
        local br="${line#branch refs/heads/}"
        if [ "$br" = "$value" ]; then
          bwpath="$pwpath"
          bwbranch="$br"
          bfound=1
        fi
        ;;
    esac
  done <<EOF_PORCELAIN2
$porcelain
EOF_PORCELAIN2
  if [ "$bfound" = "1" ]; then
    local bwcanon
    bwcanon="$(cd "$bwpath" 2>/dev/null && pwd -P)"
    [ -z "$bwcanon" ] && bwcanon="$bwpath"
    printf 'RELAY_WT_RESOLVED=branch\n'
    # Canonical, for the same reason as the path row above.
    printf 'RELAY_WT_TARGET=%s\n' "$bwcanon"
    printf 'RELAY_WT_TARGET_BRANCH=%s\n' "$bwbranch"
    return 0
  fi

  printf 'RELAY_WT_RESOLVED=missing\n'
  printf 'RELAY_WT_TARGET=%s\n' "$value"
  printf 'RELAY_WT_TARGET_BRANCH=\n'
  return 0
}

# Print the repository top level this call runs in. A script mode, not an
# inline rev-parse, because a worktree-isolated session refuses an inline
# command substitution (issue #110).
_wt_active() {
  local top
  top="$(git rev-parse --show-toplevel 2>/dev/null)" || top=""
  if [ -z "$top" ]; then
    echo "[relay] error: could not read the git state. Run this command inside a git checkout." >&2
    return 1
  fi
  printf 'RELAY_WT_ACTIVE=%s\n' "$top"
  return 0
}

_wt_create() {
  local base_ref="" slug="" at_path=""
  base_ref="${1:-}"
  shift || true
  while [ $# -gt 0 ]; do
    case "$1" in
      --at)
        if [ -z "${2:-}" ]; then
          echo "[relay] error: --at requires a value" >&2
          return 2
        fi
        at_path="$2"
        shift 2
        ;;
      --at=*)
        at_path="${1#--at=}"
        shift
        ;;
      *)
        slug="$1"
        shift
        ;;
    esac
  done
  if [ -z "$base_ref" ]; then
    echo "[relay] error: --create requires a <base-ref>" >&2
    return 1
  fi
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "RELAY_WT_STATE=not-git" >&2
    return 1
  fi

  local default toplevel bootstrap_cmd
  default="$(_wt_default_branch)"
  toplevel="$(git rev-parse --show-toplevel 2>/dev/null)"
  if ! bootstrap_cmd="$(_wt_bootstrap_command "$toplevel")"; then
    return 1
  fi

  # 1. pull latest from the default branch (only reached when CREATING a worktree).
  #    Soft-degrade: a fetch failure (e.g. offline) must not strand the user — warn
  #    and continue to create off the locally-known base ref.
  if ! git fetch origin "$default" >/dev/null 2>&1; then
    echo "[relay] note: 'git fetch origin $default' failed; creating off local base" >&2
  fi

  # 2. base = the caller-supplied <base-ref> (origin/<default> or HEAD).
  # 3. generate a slug-based worktree name under .claude/worktrees/, OR — when
  #    --at was given — create at the exact path on branch relay/<basename>,
  #    no collision suffix.
  local candidate name
  if [ -n "$at_path" ]; then
    name="$(basename "$at_path")"
    candidate="$at_path"
    if [ -e "$candidate" ] || git show-ref --verify --quiet "refs/heads/relay/$name"; then
      echo "[relay] error: worktree-exists: $candidate or branch relay/$name already exists" >&2
      return 1
    fi
    mkdir -p "$(dirname "$candidate")"
  else
    [ -z "$slug" ] && slug="relaySession"
    local wt_dir="$toplevel/.claude/worktrees"
    mkdir -p "$wt_dir"
    # Collision predicate guards BOTH axes the subsequent `git worktree add -b` touches:
    # the worktree directory/path AND the target branch ref. A leftover `relay/<slug>`
    # branch (dir torn down via `git worktree remove`+`prune` but branch never deleted —
    # the normal post-teardown state) must also force a -N suffix; otherwise `git worktree
    # add ... -b relay/<slug>` fails with "a branch named relay/<slug> already exists".
    name="$slug"
    candidate="$wt_dir/$slug"
    local n=1
    while [ -e "$candidate" ] || \
          git worktree list --porcelain 2>/dev/null | grep -qF "worktree $candidate" || \
          git show-ref --verify --quiet "refs/heads/relay/$name"; do
      name="${slug}-${n}"
      candidate="$wt_dir/$name"
      n=$((n + 1))
    done
  fi

  # 4. create the worktree on a fresh relay/<name> branch off the chosen base ref.
  if ! git worktree add "$candidate" -b "relay/$name" "$base_ref" >/dev/null 2>&1; then
    echo "[relay] error: git worktree add failed (base-ref '$base_ref')" >&2
    return 1
  fi

  # 5. run the per-repo bootstrap command inside the new worktree when configured.
  local bootstrap_status="skipped"
  if [ -n "$bootstrap_cmd" ]; then
    bootstrap_status="ran"
    ( cd "$candidate" && bash -c "$bootstrap_cmd" ) >&2
    local bootstrap_rc=$?
    if [ "$bootstrap_rc" -ne 0 ]; then
      echo "[relay] error: bootstrap failed (exit $bootstrap_rc)" >&2
      return 1
    fi
  fi

  # 6. print the absolute created path and bootstrap status.
  local abs
  abs="$(cd "$candidate" && pwd)"
  printf 'RELAY_WT_CREATED_PATH=%s\n' "$abs"
  printf 'RELAY_WT_BOOTSTRAP=%s\n' "$bootstrap_status"
  return 0
}

# Dispatch. Works both SOURCED and EXECUTED (uses `return` so a sourced caller can
# `|| exit 1`). `return` outside a function in a sourced script is valid; when executed
# directly bash treats the top-level `return` as the script's exit status.
_wt_rc=0
case "${1:-}" in
  --classify)
    _wt_classify || _wt_rc=$?
    ;;
  --create)
    shift
    _wt_create "$@" || _wt_rc=$?
    ;;
  --resolve)
    _wt_resolve "${2:-}" || _wt_rc=$?
    ;;
  --branch-guard)
    _wt_branch_guard "${2:-implement}" || _wt_rc=$?
    ;;
  --active)
    _wt_active || _wt_rc=$?
    ;;
  *)
    echo "[relay] error: usage: worktree-preflight.sh --classify | --create <base-ref> [--at <path>] [slug] | --resolve <value> | --active | --branch-guard [implement|verify]" >&2
    _wt_rc=2
    ;;
esac
return "$_wt_rc" 2>/dev/null || exit "$_wt_rc"
