# Findings — 2026-07-06-relay-worktree-bootstrap-plan.md

## Round 1 (plan-simulator)

FINDINGS: critical=0 important=2 minor=1

critical:
  (none)

important:
  - task: Task 2/Task 3 — `scripts/worktree-preflight.sh` header comment update
    step: Task 2 Step 3, "Update the `--create` header comment to describe the new steps."
    concern: >
      The updated header comment only renumbers the tail of the `--create` step list
      (new steps 5 "run bootstrap" / 6 "print"). It never documents the config
      read-and-validate step that Task 3 places BEFORE step 1 (`git fetch`) — i.e. the
      fail-fast-on-invalid-JSON behavior that must happen before any worktree mutation
      (per spec §3 step "0a" and the `test_create_invalid_json_hard_fails_before_worktree_creation`
      test). After Task 3 lands, the header's numbered list 1–6 no longer matches actual
      execution order: a reader would conclude config parsing happens at step 5/6 (after
      `git worktree add`), when in fact invalid JSON aborts before step 1 ever runs. This
      is exactly the kind of doc/code drift the spec's own round-1 refinement flagged as
      worth calling out explicitly.
    recommendation: >
      Add a "0a." bullet to the header comment (mirroring spec §3), inserted before the
      existing step 1 line, stating that `.claude/relay.json` is read from the primary
      checkout and validated before any git mutation, and that invalid JSON fails fast
      here. Keep the existing steps 5/6 wording for the bootstrap-run/print part.

  - task: Task 4 — Document Bootstrap Behavior in the Worktree Gate Skill
    step: Step 3, first sub-instruction ("updating the printed block ... to include
      `RELAY_WT_BOOTSTRAP`")
    concern: >
      The instruction implies there is an existing standalone "printed block" for
      `--create`'s output (analogous to the fenced `--classify` block at SKILL.md
      lines 42–48) that should be edited to add the 2-line
      `RELAY_WT_CREATED_PATH=<absolute path>` / `RELAY_WT_BOOTSTRAP=<ran|skipped>`
      snippet. No such fenced block exists today — `RELAY_WT_CREATED_PATH` currently
      appears only as inline backtick mentions inside each Create branch's prose
      (lines 82 and 105), which the very NEXT sub-instruction in the same step already
      rewrites wholesale. It is unclear whether this first sub-instruction is a separate,
      unanchored insertion (and if so, where) or is simply narrating what the second
      sub-instruction already accomplishes. An implementer could end up inserting a
      stray/duplicate fenced snippet that doesn't fit the surrounding prose structure.
    recommendation: >
      Either drop this sub-instruction as redundant (the subsequent "replace the
      single-line `--create` description ... in both Create branches" edit already
      lands the literal text `RELAY_WT_CREATED_PATH=<absolute path>` plus
      `RELAY_WT_BOOTSTRAP=<ran|skipped>` in prose, satisfying the test's substring
      checks), or give it an explicit anchor if a standalone fenced block is genuinely
      intended.

minor:
  - task: Task 3 — `_wt_bootstrap_command()`
    step: Step 3, the `jq -r '.bootstrap // ""' "$config"` invocation
    concern: >
      Neither the plan nor `scripts/check-deps.sh` verifies `jq` is on PATH before this
      new code path runs. `check-deps.sh` only probes for the `superpowers` plugin /
      codex skills, never `jq` — the spec's claim that "jq is already a relay dependency
      (check-deps.sh)" does not hold; `jq` is currently only exercised by
      `skills/dispatching-acpx-agents/acpx-dispatch.sh`, a different code path not every
      Step-0.5 worktree-creating session touches. If `jq` is missing from PATH, the shell
      reports "command not found" (exit 127), which `_wt_bootstrap_command()` currently
      cannot distinguish from genuinely invalid JSON, so it prints the misleading
      "[relay] error: .claude/relay.json is not valid JSON" for a missing-binary
      condition.
    recommendation: >
      Nice-to-have only (won't block test-passing in a `jq`-equipped dev/CI environment):
      note the `jq` dependency in the Task 5 repo-config reference doc, or add a
      `command -v jq` pre-check with a distinguishing error message.

## Round 1 fixer (plan-fixer)

FIXED: addressed=2 skipped=1

changes:
  - severity: important
    task: Task 2/Task 3 — header comment
    concern: header comment never documented the pre-step-1 config fail-fast
    applied_change: >
      added a `0a.` header-comment bullet + paragraph to Task 3 (after the checked
      run-block, before Step 4) documenting the early read/validate-before-fetch ordering
  - severity: important
    task: Task 4 — printed block instruction
    concern: instruction implied a non-existent standalone fenced `--create` output block
    applied_change: >
      reworded Task 4 Step 3's opening sentence to state no such block exists today and
      that the two-line snippet lands inline via the following Create-branch rewrite
skipped:
  - severity: minor
    task: Task 3 — `_wt_bootstrap_command()`
    concern: missing `jq` on PATH would be misreported as invalid JSON rather than "not found"
    reason: minor severity; recorded in the plan's Refinement Status as an accepted residual

## Round 2 (plan-simulator)

FINDINGS: critical=0 important=0 minor=1 (carried forward, unchanged, accepted as residual)

Convergence predicate met: no critical/important findings remain.

Refinement: CONVERGED round 2

FINDINGS_PATH=/Users/jazz/dev/github.com/ai-advanced-futures/claude-code-dev-plugins/.claude/worktrees/relay-worktree-bootstrap/plugins/relay/docs/superpowers/plans/2026-07-06-relay-worktree-bootstrap-plan.findings.md
ROLE_DONE
