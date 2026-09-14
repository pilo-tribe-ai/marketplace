#!/usr/bin/env bash
# One node of the relay verify-until-clean loop.
#
# The loop's node bodies live here, not inline in the Workflow script, for three
# reasons. Inline bash in a generated script cannot be unit-tested, so the shape the
# skill documents and the shape the run executes could drift apart. Each inline body
# also had to be restated in every node prompt, which cost about 35000 tokens per node
# to run a single command. And a Claude Code session that is isolated in a git worktree
# refuses a Bash command it judges too complex to verify, which every inline body was.
#
# Read the containment note in skills/verifying-until-clean/SKILL.md before adding a
# step here. Every git call is scoped with `-C "$worktree"` on purpose: a node's working
# directory is not guaranteed to be the worktree, which is why the path is an argument
# and never derived from the caller's cwd.
#
# Every exit path prints `NODE_STATUS=` as the LAST line, and prints it exactly once.
# The node that runs this script is a model, and it relays what it reads. When the status
# line sat above 25 to 40 lines of child output, nodes summarised the whole block instead
# of relaying the line: run wf_8ad76eec-5ac returned invented detail values, one of them
# the literal word `placeholder`, and reported `ran` for a step that had run nothing.
# Last means "read the last line" is a mechanical rule that needs no judgement. Keep it
# last when you add a path.
set -uo pipefail

usage() {
  cat >&2 <<'EOF'
usage: verify-loop-node.sh [--phase pre|post] <kind> ...
       verify-loop-node.sh init     <worktree> <rounds>
       verify-loop-node.sh simplify <worktree> <round> <rounds>
       verify-loop-node.sh review   <worktree> <round> <rounds>
       verify-loop-node.sh check    <worktree> <round> <rounds>
       verify-loop-node.sh fix      <worktree> <round> <rounds>
       verify-loop-node.sh report   <worktree> <rounds>

--phase splits one step into two calls, for the in-session engine only:
  pre   read the state, hold the deadline, print the command to invoke
  post  read the reply the caller wrote, parse it, record it
Without --phase the script runs the whole step itself over acpx, which is
what the acpx engine does and what every earlier version did.
EOF
}

# PHASE=all is the acpx engine: this script starts the child itself, so one Bash
# call is one whole step. `pre` and `post` exist because the in-session engine
# cannot work that way — a slash command is reached through a tool call, and Bash
# cannot make one. The state, the deadline, the verdict parse, the commits and the
# records stay here in both engines. Only the way the step reaches the command moves.
PHASE="all"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --phase)
      PHASE="${2:-}"
      case "$PHASE" in
        pre|post) ;;
        *)
          usage
          echo "NODE_STATUS=failed:64 reason=bad-phase:${PHASE:-<empty>}"
          exit 64
          ;;
      esac
      shift 2
      ;;
    --phase=*)
      PHASE="${1#--phase=}"
      case "$PHASE" in
        pre|post) ;;
        *)
          usage
          echo "NODE_STATUS=failed:64 reason=bad-phase:${PHASE:-<empty>}"
          exit 64
          ;;
      esac
      shift
      ;;
    *) break ;;
  esac
done

if [ "$#" -lt 3 ]; then
  usage
  echo "NODE_STATUS=failed:64 reason=bad-arguments"
  exit 64
fi

kind="$1"
worktree="$2"

# init and report start no child, so there is no command for `pre` to print and no
# reply for `post` to read. Accepting the flag and ignoring it would let a caller
# believe it had split a step that was never split.
if [ "$PHASE" != "all" ]; then
  case "$kind" in
    init|report)
      usage
      echo "NODE_STATUS=failed:64 reason=phase-not-supported-for-kind:$kind"
      exit 64
      ;;
  esac
fi

if [ ! -d "$worktree" ]; then
  echo "verify-loop-node.sh: worktree not found: $worktree" >&2
  echo "NODE_STATUS=failed:66 reason=worktree-not-found"
  exit 66
fi

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

git_dir="$(git -C "$worktree" rev-parse --absolute-git-dir 2>/dev/null)"
if [ -z "$git_dir" ]; then
  echo "verify-loop-node.sh: not a git checkout: $worktree" >&2
  echo "NODE_STATUS=failed:66 reason=not-a-git-checkout"
  exit 66
fi

# State lives under the git directory, never in the working tree. Git tracks nothing
# there, so `git add -A` cannot sweep the run's own logs into a commit and
# `git status --short` stays honest. A scratch directory inside the working tree would
# make every round look as if it changed files, which silently defeats the fix-noop
# check below.
STATE_ROOT="$git_dir/relay-verify"

read_state() {
  [ -f "$STATE_ROOT/state" ] || return 0
  sed -nE "s/.*$1=([A-Za-z0-9_-]*).*/\1/p" "$STATE_ROOT/state" 2>/dev/null | tail -1
}

write_state() {
  printf 'LABEL=%s ROUND=%s NOOPS=%s EXIT=%s\n' "$1" "$2" "$3" "$4" > "$STATE_ROOT/state"
}

# Commit whatever the step just changed. The scope derivation and the commit live in
# scripts/verify-commit-scope.sh, which prints one line: a sha, `commit-failed`, or
# `no changes`. A commit that exits non-zero is never folded into a normal commit result.
commit_step() {
  bash "$here/verify-commit-scope.sh" "$worktree" "$1"
}

# A missing state file means the init node never ran, so the loop never started. That is
# not a skip: a skipped node says the loop decided to stop, and recording both the same
# way hides a refused init node behind an orderly-looking record.
require_state() {
  local key="$1" round_dir="$2"
  if [ ! -f "$STATE_ROOT/state" ]; then
    if claim_step "$round_dir" "$key"; then
      echo "$key=failed:no-state" >> "$round_dir/record"
    fi
    echo "NODE_STATUS=failed:no-state reason=verify-init-did-not-run"
    exit 0
  fi
}

# Every child session runs under a wall-clock budget, because the caller has one too.
# A node runs as a single Bash call, and that call is cut off after ten minutes. A child
# that outlives the cut is killed with the node that started it, before this script
# reaches the line that writes the record — so the round leaves no trace at all and the
# report reads it as a node that never ran. A run whose rounds all end that way still
# reports `unverified`, which is honest, but it names no cause.
#
# The budget is a DEADLINE for the whole node, not a limit for each child. The clock is
# read once, here, and every child gets only the time that is left. A per-child limit made
# that promise false on the one path that runs two children: the `check` node retries, so
# two children of 540 seconds could run for 1080 against a ceiling of 600. Run
# wf_918a4deb-aba took that path in all three rounds — the caller cut the node off, this
# script never reached the line that writes the record, and every round read CHECK=missing.
NODE_TIMEOUT="${RELAY_VERIFY_NODE_TIMEOUT:-540}"

# A value that is not a whole number of seconds breaks the arithmetic below, and under
# `set -u` that ends the node with no NODE_STATUS line at all — the very failure this
# budget exists to stop. Fall back to the default, and say so.
case "$NODE_TIMEOUT" in
  ''|*[!0-9]*)
    echo "verify-loop-node.sh: RELAY_VERIFY_NODE_TIMEOUT is not a whole number of seconds: $NODE_TIMEOUT (using 540)" >&2
    NODE_TIMEOUT=540
    ;;
esac

# Digits alone are not enough. Bash reads a leading zero as octal.
#   0600 becomes 384 seconds — a budget cut by a third with nothing said.
#   0900 is not a legal octal number at all. The arithmetic below fails (a warning, not a
#        fatal error), NODE_DEADLINE is never set, and `set -u` then ends run_child on its
#        first read of it. run_child runs inside a command substitution, so the subshell
#        dies and the node reports `failed:1` without ever starting a child. Measured, not
#        assumed: a 900-second budget turns into an immediate hard failure.
#   00   passes the digit test but is not the string `0`, so the off-switch below misses
#        it and the deadline lands on the current second, which refuses every child.
# Force base 10 once, here, after the digit test has run.
NODE_TIMEOUT=$(( 10#$NODE_TIMEOUT ))

NODE_DEADLINE=$(( $(date +%s) + NODE_TIMEOUT ))

# A run_child call happens inside a command substitution, so a shell variable it sets
# cannot reach the caller. The flag is a file for that reason. It says whether the last
# 124 came from a child that ran out of time or from a child that was never started.
NOT_STARTED_FLAG="$STATE_ROOT/.child-not-started"

# `timeout` reports 124 when it fires. That is a failure, never a skip: the step did not
# run to a verdict, so nothing downstream may read it as one. A child that would start
# after the deadline is not started at all, and reports the same 124.
run_child() {
  local helper="$1"; shift
  rm -f "$NOT_STARTED_FLAG" 2>/dev/null || true
  if [ "$NODE_TIMEOUT" = "0" ] || ! command -v timeout >/dev/null 2>&1; then
    "$here/$helper" "$@"
    return $?
  fi
  local remaining=$(( NODE_DEADLINE - $(date +%s) ))
  if [ "$remaining" -le 0 ]; then
    : > "$NOT_STARTED_FLAG" 2>/dev/null || true
    return 124
  fi
  timeout -k 10 "$remaining" "$here/$helper" "$@"
  return $?
}

# --- the two-call protocol, for the in-session engine only ---------------------
#
# With acpx this script starts the child, so a written record is EVIDENCE that a step
# ran. In-session the caller invokes the command through a tool and hands the reply
# back, so a record is only a CLAIM. That difference is the whole risk of the
# in-session engine, and it is this loop's own named failure mode: run wf_8ad76eec-5ac
# reported `ran` for a step that had run nothing.
#
# Five mechanical guards answer it. None of them needs judgement:
#   1. `pre` deletes the reply file, so a file present at `post` time was written
#      after `pre` ran. A leftover file from an earlier attempt cannot stand in.
#   2. `pre` writes a `.go` marker only on the path where a command must be invoked.
#      `post` refuses without it, so a `post` that follows a SKIPPED `pre` cannot
#      overwrite the skip record with a failure.
#   3. An absent or empty reply is `failed:no-reply`. It is not a skip, and it is
#      never a pass.
#   4. `post` builds the output fence itself, around text it treats as opaque. The
#      caller never writes the fence, so the caller cannot forge one. The parser
#      reads the FIRST begin marker and the LAST end marker, and both of those are
#      this script's, so marker text inside the reply cannot move the region.
#   5. One terminal record line per round and step, claimed with `mkdir`. `mkdir` either
#      makes the directory or fails; it cannot half-succeed, so exactly one caller wins
#      even when two chains of one forked session run the same step at the same time. A
#      caller that finds the claim held is a re-entry, not a new attempt: it must not
#      delete the reply, must not re-arm the marker, must not overwrite the `.out` file,
#      must not append a second value the report would have to guess at, and must not
#      move the loop state.
reply_file() { printf '%s/%s.reply' "$1" "$2"; }
go_marker()  { printf '%s/%s.go' "$1" "$2"; }
done_marker() { printf '%s/%s.done' "$1" "$2"; }
# Guard 5. The marker is keyed on the RECORD KEY (SIMPLIFY, REVIEW, CHECK, FIX), not on
# the lowercase kind, so it cannot collide with `<kind>.go` or `<kind>.reply`, and so
# `simplify` and `review` cannot share one claim through their shared branch. The `init`
# node deletes each round directory, so a new run starts with no claim held.
claim_step()      { mkdir "$(done_marker "$1" "$2")" 2>/dev/null; }
step_done()       { [ -d "$(done_marker "$1" "$2")" ]; }
recorded_status() { sed -nE "s/^$2=(.*)$/\1/p" "$1/record" 2>/dev/null | tail -1; }

# Print the command the caller must invoke, then stop the step. The caller writes the
# whole reply to the named file and calls `post`.
emit_pre() {
  local round_dir="$1" tag="$2" command_text="$3"
  rm -f "$(reply_file "$round_dir" "$tag")" 2>/dev/null || true
  : > "$(go_marker "$round_dir" "$tag")"
  echo "PRE_REPLY_FILE=$(reply_file "$round_dir" "$tag")"
  echo "PRE_COMMAND_BEGIN"
  printf '%s\n' "$command_text"
  echo "PRE_COMMAND_END"
  echo "NODE_STATUS=pre kind=$tag reply=$(reply_file "$round_dir" "$tag")"
  exit 0
}

# Stand in for run_child on the in-session path: read what the caller wrote and shape
# it like an acpx reply, so every consumer below — the verdict parser, the fix body,
# the tail — reads one format and needs no engine of its own.
#
# 65 is "no usable reply". It is deliberately not 0: a caller that invoked nothing
# still leaves an empty file behind on some shells, and an empty reply read as a
# success is exactly the fabricated pass this loop must never record.
read_caller_reply() {
  local round_dir="$1" tag="$2" file body
  file="$(reply_file "$round_dir" "$tag")"
  [ -f "$file" ] || return 65
  # A reply of only whitespace is no reply. `tr -d` collapses the test to "did the
  # caller write any visible character at all".
  body="$(tr -d '[:space:]' < "$file" 2>/dev/null)"
  [ -n "$body" ] || return 65
  printf 'POLISH_CMD_OUTPUT_BEGIN\n'
  cat "$file"
  printf '\nPOLISH_CMD_OUTPUT_END\n'
  printf 'POLISH_CMD_RC=0\n'
  return 0
}

# One seam for both engines. PHASE=all starts a child; PHASE=post reads the reply the
# caller already produced. Every branch below calls this instead of run_child, so the
# record, commit and state code after it is shared by both engines and cannot drift.
obtain_reply() {
  local round_dir="$1" tag="$2"; shift 2
  if [ "$PHASE" = "post" ]; then
    if [ ! -f "$(go_marker "$round_dir" "$tag")" ]; then
      return 70
    fi
    rm -f "$(go_marker "$round_dir" "$tag")" 2>/dev/null || true
    read_caller_reply "$round_dir" "$tag"
    return $?
  fi
  run_child "$@"
  return $?
}

# Name the real cause of a 124. A status line that says the child exceeded the budget
# when no child ever started is narration, not evidence.
#
# Usually the refused child is the check node's retry. It is not always: this node does
# its own work — git calls, state reads — before it starts a child, and at a tight budget
# that work can spend the whole budget, so the FIRST child is refused too.
timeout_reason() {
  if [ -f "$NOT_STARTED_FLAG" ]; then
    echo "node-budget-spent-before-child-started"
  else
    echo "child-exceeded-${NODE_TIMEOUT}s"
  fi
}

case "$kind" in
  init)
    mkdir -p "$STATE_ROOT"
    # Clear only the round directories this loop owns. Deleting the whole state root
    # also removes files this loop did not create.
    rm -rf "${STATE_ROOT:?}"/round-*
    mkdir -p "$STATE_ROOT/round-1"
    write_state "" 1 0 continue
    cat "$STATE_ROOT/state"
    echo "NODE_STATUS=ran detail=state-seeded"
    exit 0
    ;;

  simplify|review)
    round="$3"
    round_dir="$STATE_ROOT/round-$round"
    mkdir -p "$round_dir"
    if [ "$kind" = "simplify" ]; then key="SIMPLIFY"; slash="/simplify"
    else key="REVIEW"; slash="/code-review medium --fix"; fi
    require_state "$key" "$round_dir"
    if step_done "$round_dir" "$key"; then
      echo "NODE_STATUS=already-done key=$key value=$(recorded_status "$round_dir" "$key")"
      exit 0
    fi
    if [ "$(read_state EXIT)" != "continue" ]; then
      claim_step "$round_dir" "$key" && echo "$key=skipped" >> "$round_dir/record"
      echo "NODE_STATUS=skipped reason=round-already-ended"
      exit 0
    fi
    [ "$PHASE" = "pre" ] && emit_pre "$round_dir" "$kind" "$slash"
    out="$(obtain_reply "$round_dir" "$kind" run-claude-command.sh "$worktree" "relay-verify-$kind-r$round" "$slash")"
    rc=$?
    # Before the write: a post with no `pre` behind it must not overwrite the file that
    # the real attempt left, and must not add a record line of its own. The step keeps
    # whatever record it already had, which for a skipped step is the skip.
    if [ "$rc" -eq 70 ]; then
      echo "NODE_STATUS=failed:no-pre reason=post-ran-without-a-pre-that-asked-for-a-command"
      exit 0
    fi
    if ! claim_step "$round_dir" "$key"; then
      echo "NODE_STATUS=already-done key=$key value=$(recorded_status "$round_dir" "$key")"
      exit 0
    fi
    printf '%s\n' "$out" > "$round_dir/$kind.out"
    if [ "$rc" -eq 65 ]; then
      echo "$key=failed:no-reply" >> "$round_dir/record"
      write_state no-answer "$round" "$(read_state NOOPS)" unverified
      echo "NODE_STATUS=failed:no-reply reason=caller-wrote-no-reply"
      exit 0
    fi
    if [ "$rc" -eq 69 ]; then
      echo "$key=failed:69" >> "$round_dir/record"
      write_state no-answer "$round" "$(read_state NOOPS)" unverified
      echo "NODE_STATUS=failed:69 reason=acpx-unavailable"
      exit 0
    fi
    if [ "$rc" -eq 124 ]; then
      echo "$key=failed:timeout" >> "$round_dir/record"
      write_state no-answer "$round" "$(read_state NOOPS)" unverified
      echo "NODE_STATUS=failed:timeout reason=$(timeout_reason)"
      exit 0
    fi
    if [ "$rc" -ne 0 ]; then
      echo "$key=failed:$rc" >> "$round_dir/record"
      write_state no-answer "$round" "$(read_state NOOPS)" unverified
      echo "NODE_STATUS=failed:$rc"
      exit 0
    fi
    echo "$key=ran" >> "$round_dir/record"
    sha="$(commit_step "$kind")"
    echo "${key}_COMMIT=$sha" >> "$round_dir/record"
    tail -25 "$round_dir/$kind.out"
    echo "NODE_STATUS=ran commit=$sha"
    exit 0
    ;;

  check)
    round="$3"
    rounds="$4"
    round_dir="$STATE_ROOT/round-$round"
    mkdir -p "$round_dir"
    require_state CHECK "$round_dir"
    if step_done "$round_dir" CHECK; then
      echo "NODE_STATUS=already-done key=CHECK value=$(recorded_status "$round_dir" CHECK)"
      exit 0
    fi
    if [ "$(read_state EXIT)" != "continue" ]; then
      claim_step "$round_dir" CHECK && echo "CHECK=skipped" >> "$round_dir/record"
      echo "NODE_STATUS=skipped reason=round-already-ended"
      exit 0
    fi
    noops="$(read_state NOOPS)"
    [ -z "$noops" ] && noops=0
    retried=0
    reason=""
    # /verify is not relay's command. It resolves to whatever the repository defines, and a
    # repository that holds its own verify skill can prescribe no report format at all. In
    # run wf_918a4deb-aba the child answered "## Verify result: productivity v0.7.0 — PASS",
    # which holds no verdict token, so the parser read no-answer and all three rounds bought
    # nothing. State the line the loop needs here. Do not assume the child prints it.
    #
    # The shape below is the enum template on purpose. A child that copies the contract into
    # its reply writes four verdict tokens on one line, and the one-token rule in
    # parse-verify-verdict.sh rejects that line. An example that holds one token, such as
    # "**Verdict:** PASS", is read as a real pass when a child copies it — the one error this
    # loop must never make.
    #
    # The text starts with "/", so the slash-only guard in run-claude-command.sh accepts it:
    # that guard reads the first character only. Keep this text free of apostrophes. It is a
    # single-quoted shell string, and skills/verifying-until-clean/SKILL.md holds a copy that
    # a test compares with this one.
    check_command='/verify

End your reply with a verdict line. Use this shape:

**Verdict:** PASS | FAIL | BLOCKED | SKIP

Write one word in the place of the four words: PASS, FAIL, BLOCKED, or SKIP. Do not copy the four words. Put the verdict line last, and write nothing after it.'
    [ "$PHASE" = "pre" ] && emit_pre "$round_dir" check "$check_command"
    run_check() {
      out="$(obtain_reply "$round_dir" check run-claude-command.sh "$worktree" "relay-verify-check-r$round" "$check_command")"
      rc=$?
      # Keep the file that the real attempt left. See the simplify branch.
      [ "$rc" -eq 70 ] && return 70
      printf '%s\n' "$out" > "$round_dir/check.out"
      return $rc
    }
    read_verdict() {
      "$here/parse-verify-verdict.sh" "$round_dir/check.out" \
        > "$round_dir/verdict" 2> "$round_dir/verdict-reason"
      verdict="$(sed -nE 's/^VERIFY_VERDICT=(.*)$/\1/p' "$round_dir/verdict" | tail -1)"
      label="$(sed -nE 's/^VERIFY_LABEL=(.*)$/\1/p' "$round_dir/verdict" | tail -1)"
      reason="$(sed -nE 's/^VERIFY_REASON=(.*)$/\1/p' "$round_dir/verdict-reason" | tail -1)"
      [ -z "$label" ] && label="no-answer"
    }
    run_check
    rc=$?
    if [ "$rc" -eq 70 ]; then
      echo "NODE_STATUS=failed:no-pre reason=post-ran-without-a-pre-that-asked-for-a-command"
      exit 0
    fi
    verdict=""
    label="no-answer"
    [ "$rc" -eq 0 ] && read_verdict
    # `retried` has to be true on the second `post` too, and a shell variable cannot
    # cross two separate script invocations. check-1.out is the only durable evidence
    # that a first reply existed, so it is what the second call reads.
    if [ "$PHASE" = "post" ] && [ -f "$round_dir/check-1.out" ]; then retried=1; fi
    # Two shapes are retried once, in the same session, because a second child can change
    # them: a BLOCKED verdict, and a reply with no usable output fence. Three shapes are
    # not, because a second child cannot:
    #   SKIP            — a second run sees the same empty diff.
    #   no reply at all — the caller invoked nothing, or wrote an empty file. That is not
    #                     a verdict of an unusable shape, it is the absence of an attempt.
    #                     Recording it as one more retried shape would leave a record that
    #                     cannot tell "answered badly" from "never answered".
    #   a timeout       — the second child starts with the budget already spent.
    #   no verdict line — the reply parsed; its format holds no verdict. The same command
    #                     in the same repository answers in the same format, so the retry
    #                     only spends a child. That retry is what pushed this node past the
    #                     caller's ceiling in run wf_918a4deb-aba.
    if [ "$label" = "no-answer" ] && [ "$verdict" != "SKIP" ] \
       && [ "$reason" != "no-verdict-line" ] \
       && [ "$rc" -ne 69 ] && [ "$rc" -ne 124 ] && [ "$rc" -ne 65 ] \
       && [ "$retried" -eq 0 ]; then
      # Keep the first reply. The retry overwrites check.out, and a silent second reply
      # would otherwise erase the only evidence of what the first one answered.
      cp "$round_dir/check.out" "$round_dir/check-1.out" 2>/dev/null || true
      # In-session cannot start the second attempt from here: only the caller can invoke
      # the command. Re-arm and ask for one more reply. The decision stays in this
      # script, so the caller holds no state and makes no choice — it reads one line.
      if [ "$PHASE" = "post" ]; then
        rm -f "$(reply_file "$round_dir" check)" 2>/dev/null || true
        : > "$(go_marker "$round_dir" check)"
        echo "PRE_REPLY_FILE=$(reply_file "$round_dir" check)"
        echo "NODE_RETRY=1"
        echo "NODE_STATUS=retry reason=${reason:-no-usable-verdict}"
        exit 0
      fi
      retried=1
      reason=""
      run_check
      rc=$?
      [ "$rc" -eq 0 ] && read_verdict
    fi
    if ! claim_step "$round_dir" CHECK; then
      echo "NODE_STATUS=already-done key=CHECK value=$(recorded_status "$round_dir" CHECK)"
      exit 0
    fi
    if [ "$rc" -eq 124 ]; then
      echo "CHECK=failed:timeout" >> "$round_dir/record"
      write_state no-answer "$round" "$noops" unverified
      echo "NODE_STATUS=failed:timeout reason=$(timeout_reason)"
      exit 0
    fi
    if [ "$rc" -eq 65 ]; then
      # Name it, rather than leaving a bare 65 that reads like an acpx exit code. The
      # caller invoked nothing, or wrote an empty file. Either way no verdict exists,
      # so the label below stays no-answer and the run ends unverified.
      echo "CHECK=failed:no-reply" >> "$round_dir/record"
    elif [ "$rc" -ne 0 ]; then
      echo "CHECK=failed:$rc" >> "$round_dir/record"
    else
      echo "CHECK=ran" >> "$round_dir/record"
    fi
    {
      echo "VERDICT=$verdict"
      echo "LABEL=$label"
      echo "REASON=$reason"
      echo "RETRIED=$retried"
    } >> "$round_dir/record"
    newexit="continue"
    [ "$label" = "clean" ] && newexit="clean"
    [ "$label" = "no-answer" ] && newexit="unverified"
    if [ "$round" -ge "$rounds" ] && [ "$label" = "findings" ]; then newexit="findings"; fi
    write_state "$label" "$round" "$noops" "$newexit"
    tail -40 "$round_dir/check.out"
    status_reason=""
    [ -n "$reason" ] && status_reason=" reason=$reason"
    echo "NODE_STATUS=done verdict=$verdict label=$label exit=$newexit retried=$retried$status_reason"
    exit 0
    ;;

  fix)
    round="$3"
    rounds="$4"
    round_dir="$STATE_ROOT/round-$round"
    mkdir -p "$round_dir"
    require_state FIX "$round_dir"
    if step_done "$round_dir" FIX; then
      echo "NODE_STATUS=already-done key=FIX value=$(recorded_status "$round_dir" FIX)"
      exit 0
    fi
    label="$(read_state LABEL)"
    noops="$(read_state NOOPS)"
    [ -z "$noops" ] && noops=0
    if [ "$(read_state EXIT)" != "continue" ] || [ "$label" != "findings" ]; then
      claim_step "$round_dir" FIX && echo "FIX=skipped" >> "$round_dir/record"
      echo "NODE_STATUS=skipped reason=label=$label"
      exit 0
    fi
    head -c 16000 "$round_dir/check.out" > "$round_dir/fix-body.txt"
    trunc=0
    # A partial report must stay visible rather than silently standing in for the whole.
    if ! cmp -s "$round_dir/check.out" "$round_dir/fix-body.txt"; then trunc=1; fi
    instr="Fix the problems this report names. Change the code, not the report. Keep the existing tests as they are."
    if [ "$trunc" = "1" ]; then
      instr="(The report above was truncated to fit.)

$instr"
    fi
    prompt="$(cat "$round_dir/fix-body.txt")

$instr"
    # The fix step sends prose, not a slash command. In-session the caller does this work
    # with its own tools, so `pre` prints the instruction and the caller answers with a
    # summary. The reply is not the evidence here: the git checks below are.
    [ "$PHASE" = "pre" ] && emit_pre "$round_dir" fix "$prompt"
    out="$(obtain_reply "$round_dir" fix run-claude-prompt.sh "$worktree" "relay-verify-fix-r$round" "$prompt")"
    rc=$?
    if [ "$rc" -eq 70 ]; then
      echo "NODE_STATUS=failed:no-pre reason=post-ran-without-a-pre-that-asked-for-a-command"
      exit 0
    fi
    if ! claim_step "$round_dir" FIX; then
      echo "NODE_STATUS=already-done key=FIX value=$(recorded_status "$round_dir" FIX)"
      exit 0
    fi
    printf '%s\n' "$out" > "$round_dir/fix.out"
    echo "FIX_TRUNCATED=$trunc" >> "$round_dir/record"
    # A fix that reported nothing may still have changed the tree. Commit what landed, so
    # the next round reads the tree that really exists, and never count it as a pass.
    if [ "$rc" -eq 65 ]; then
      echo "FIX=failed:no-reply" >> "$round_dir/record"
      echo "FIX_COMMIT=$(commit_step fix)" >> "$round_dir/record"
      write_state no-answer "$round" "$noops" unverified
      echo "NODE_STATUS=failed:no-reply reason=caller-wrote-no-reply"
      exit 0
    fi
    if [ "$rc" -eq 69 ]; then
      echo "FIX=failed:69" >> "$round_dir/record"
      write_state "$label" "$round" "$noops" unverified
      echo "NODE_STATUS=failed:69 reason=acpx-unavailable"
      exit 0
    fi
    # A half-applied fix is still on disk. Commit it, so the next round sees the real
    # tree rather than a clean one, and never count a killed step as a no-op.
    if [ "$rc" -eq 124 ]; then
      echo "FIX=failed:timeout" >> "$round_dir/record"
      echo "FIX_COMMIT=$(commit_step fix)" >> "$round_dir/record"
      write_state no-answer "$round" "$noops" unverified
      echo "NODE_STATUS=failed:timeout reason=$(timeout_reason)"
      exit 0
    fi
    dirty="$(git -C "$worktree" status --short)"
    sha="$(commit_step fix)"
    if [ -z "$dirty" ]; then
      echo "FIX=fix-noop" >> "$round_dir/record"
      noops=$((noops + 1))
    else
      echo "FIX=ran" >> "$round_dir/record"
      noops=0
    fi
    echo "FIX_COMMIT=$sha" >> "$round_dir/record"
    newexit="continue"
    # Two fix rounds that changed nothing cannot be moved by a third.
    [ "$noops" -ge 2 ] && newexit="findings"
    [ "$round" -ge "$rounds" ] && newexit="findings"
    write_state "$label" "$round" "$noops" "$newexit"
    echo "NODE_STATUS=done noops=$noops commit=$sha exit=$newexit"
    exit 0
    ;;

  report)
    rounds="$3"
    if [ ! -f "$STATE_ROOT/state" ]; then
      echo "NO STATE - the init node did not run"
      echo "RELAY_VERIFY_MISSING=unknown"
      echo "RELAY_VERIFY_RESULT=unverified"
      exit 0
    fi
    missing=0
    failed=0
    n=1
    while [ "$n" -le "$rounds" ]; do
      d="$STATE_ROOT/round-$n"
      if [ -d "$d" ]; then
        line="round $n:"
        # A node that never ran writes no line at all. Printing only the keys that are
        # present shows a short round as a complete one, so name the absent ones.
        for k in SIMPLIFY REVIEW CHECK FIX; do
          nlines="$(grep -cE "^$k=" "$d/record" 2>/dev/null)"
          v="$(sed -nE "s/^$k=(.*)$/\1/p" "$d/record" 2>/dev/null | tail -1)"
          if [ -z "$v" ]; then
            v="missing"
            missing=$((missing + 1))
          elif [ "${nlines:-0}" -gt 1 ]; then
            # More than one terminal line for one step in one round means the step was
            # entered more than once. The record cannot say which value is the truth, so
            # it proves nothing, and it must not be resolved by keeping the last write.
            v="conflict:$(sed -nE "s/^$k=(.*)$/\1/p" "$d/record" | paste -sd'/' -)"
            failed=$((failed + 1))
          else
            case "$v" in
              ran|skipped) ;;
              fix-noop) [ "$k" = "FIX" ] || failed=$((failed + 1)) ;;
              *) failed=$((failed + 1)) ;;
            esac
          fi
          line="$line $k=$v"
        done
        for k in VERDICT LABEL REASON RETRIED SIMPLIFY_COMMIT REVIEW_COMMIT FIX_COMMIT FIX_TRUNCATED; do
          v="$(sed -nE "s/^$k=(.*)$/\1/p" "$d/record" 2>/dev/null | tail -1)"
          [ -n "$v" ] && line="$line $k=$v"
        done
        echo "$line"
      fi
      n=$((n + 1))
    done
    cat "$STATE_ROOT/state"
    exitv="$(read_state EXIT)"
    labelv="$(read_state LABEL)"
    echo "RELAY_VERIFY_MISSING=$missing"
    echo "RELAY_VERIFY_FAILED=$failed"
    # `clean` needs two things: the last recorded label is clean, AND every step of every
    # round that started wrote a record. `missing` is a gate here, not a note printed beside
    # the result. A step that wrote no record proved nothing, so a run that holds one has not
    # earned a clean result.
    #
    # Before 4.33.0 this counter was computed, printed, and then dropped. Run wf_6f6f4d1a-4d3
    # reported `RELAY_VERIFY_RESULT=clean` next to `RELAY_VERIFY_MISSING=1`: its review step
    # ended its turn between `pre` and `post`, so `/code-review medium --fix` never ran, and
    # the branch was still reported verified. The report was not short of evidence. It had the
    # count on the line above and did not read it.
    passed_verdict=false
    if [ "$exitv" = "clean" ] && [ "$labelv" = "clean" ]; then passed_verdict=true; fi
    result="unverified"
    if [ "$passed_verdict" = true ] && [ "$missing" -eq 0 ] && [ "$failed" -eq 0 ]; then result="clean"; fi
    if [ "$exitv" = "findings" ]; then result="findings"; fi
    if [ "$exitv" = "continue" ] && [ "$labelv" = "findings" ]; then result="findings"; fi
    # Name the cause. A bare `unverified` under a passing verdict reads as a loop that broke,
    # when what happened is that a step is unaccounted for, or a step recorded its own failure.
    # The reason line prints only on the path this gate blocks, so it never appears next to a
    # result it does not explain.
    if [ "$passed_verdict" = true ]; then
      why=""
      [ "$missing" -gt 0 ] && why="incomplete-round steps=$missing"
      if [ "$failed" -gt 0 ]; then
        [ -n "$why" ] && why="$why "
        why="${why}failed-step steps=$failed"
      fi
      [ -n "$why" ] && echo "RELAY_VERIFY_REASON=$why"
    fi
    echo "RELAY_VERIFY_RESULT=$result"
    exit 0
    ;;

  *)
    usage
    echo "NODE_STATUS=failed:64 reason=unknown-kind:$kind"
    exit 64
    ;;
esac
