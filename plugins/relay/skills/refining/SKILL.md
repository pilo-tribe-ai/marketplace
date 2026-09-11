---
name: refining
description: Generic adversarial refinement loop. Invoked explicitly by the refining-specs / refining-plans / refining-prs shims with an adapter slug + inline config — NOT auto-triggered. Drives critics → aggregator → fixer → convergence/persistence over a subject until CONVERGED or ESCALATE.
user-invocable: false
---

# refining

The single, target-agnostic refinement engine. The shims (`relay:refining-specs`,
`relay:refining-plans`, `relay:refining-prs`, `relay:refining-ui`) invoke this skill via the
Skill tool, passing an adapter slug (`spec` | `plan` | `pr` | `ui`) plus an inline config block
filling the 7-field contract below. This skill owns the loop; the shims own per-target config;
the adapters own subject I/O. It is invoked explicitly by a shim, not discovery-triggered.

The shipped contract is `${CLAUDE_PLUGIN_ROOT}/docs/refinement-contract.md`. The table and
algorithm below are the operative copy.

## The 7-field refinement contract

| Field | Description | Example values |
|---|---|---|
| `subject` | What's being refined | spec document, plan document, PR diff, code files |
| `subject_adapter` | Module that loads / diffs / patches the subject | `adapters/spec.md` (file I/O), `adapters/pr.md` (git refs + checkpoint commits) |
| `critics[]` | Ordered critic roles: `{role, model, parallel?, debate_enabled?}` | `[spec-simulator]`, `[pr-reviewer, pr-validator, pr-runner]` |
| `aggregator` | Optional dedupe/prioritize step between critics and fixer | `none`, `severity-merge`, `debate-confirm`, `scored` |
| `fixer` | Single fixer role + post-fix action | `{role: spec-fixer, post: re-read}`, `{role: pr-fixer, post: verify-tests + revert-on-fail}` |
| `convergence_predicate` | Terminal condition in plain English + machine signal (binary mode only) | `"no critical/important findings → CONVERGED"`, `"all confirmed findings resolved + tests pass → CONVERGED"` |
| `max_rounds` | Hard cap before ESCALATE | default `5`, override per skill |
| `persistence_marker` | Where loop state is written for resume-after-crash | inline body (`Refinement: CONVERGED round N`), sidecar file, git checkpoint commit |
| `convergence_mode` | *(optional)* `binary` (default) or `scored` | `binary` — uses `convergence_predicate` + `critical_or_important` short-circuit; `scored` — uses threshold-AND across dimensions with plateau→pivot |
| `engine` / `agent` | *(optional)* dispatch axis supplied by the Workflow | absent → `in-session` / `claude`; delegated example → `acpx` / `opencode` |
| `worktree` | *(optional)* literal absolute path to the active workspace; forwarded verbatim to every critic/fixer dispatch as `WORKTREE_PATH` | absent → no injection; present → e.g. `/repo/.claude/worktrees/relay-worktree-arg` |

`convergence_mode`, `engine`, `agent`, and `worktree` are optional and not part of the
required 7-field contract. A shim that omits them inherits `binary` mode, `in-session` /
`claude`, and no worktree injection.

`subject_adapter` names a file under `skills/refining/adapters/<slug>.md`. The adapter declares
the I/O verbs (`load`, `snapshot`, `diff`, `post_fix`, `persist`, `recover`) the loop calls.

## Shared loop defaults (authoritative — this skill owns them)

A shim that omits any of these inherits the value below; a shim restates a value only when it
overrides it. Do not re-print these defaults in the shims.

| Invariant | Default | Notes |
|---|---|---|
| `max_rounds` | `5` | Hard cap before ESCALATE. A shim may override (e.g. a cheaper target may set a lower cap). |
| `aggregator` | `none` | The coordinator aggregates findings inline; single-critic targets pass findings through. Multi-critic targets override with `severity-merge` or `debate-confirm`. |
| post-fix action | `re-read` | After the fixer patches the subject, re-`load()` it so the next round critiques the patched text. Targets with test signals override with `verify-tests + revert-on-fail`. |
| `convergence_predicate` | `"no critical/important findings → CONVERGED"` | The generic short-circuit `not critical_or_important(findings)` marks CONVERGED. Targets with extra terminal conditions (e.g. tests-pass) extend the predicate. |
| `persistence_marker` | inline `Refinement: CONVERGED round N` (+ sidecar findings file) | Where loop state is written for `recover()`. Targets that operate on git override with checkpoint commits. |

A shim therefore declares only: the `subject` description, `subject_adapter` slug, the
target-specific `critics[]`, the `fixer` role, plus any invariant it overrides.

### Scored mode config block

When `convergence_mode: scored`, the shim supplies a `scored:` block:

```yaml
convergence_mode: scored        # binary (default) | scored
scored:
  dimensions:                   # critic-dimension → threshold (score is 1–10 integer)
    design_quality: 7
    originality: 7
    craft: 7
    functionality: 7
    accessibility: 7
  max_findings_per_cycle: 5     # cap sent to fixer; criticals always included
  plateau_window: 3             # consecutive low-delta rounds before pivot
  plateau_epsilon: 0.5          # |avg signed score delta| below this counts as "no progress"
```

In `binary` mode the `scored` block is absent. `convergence_predicate` is evaluated only in
binary mode and ignored when `convergence_mode == "scored"`.

## Reading the adapter

Before the loop runs, read `${CLAUDE_PLUGIN_ROOT}/skills/refining/adapters/<slug>.md`. Its verbs:

- `load()` → current subject snapshot, or `SUBJECT_MISSING` when the adapter finds no subject
  at the path it was given. A missing subject is not an empty subject; never read an absent
  file as acceptable content.
- `snapshot(subject)` → opaque pre-state for diffing
- `diff(snapshot, current)` → structured diff for reporting
- `post_fix(action)` → run the post-fix action (`re-read` | `verify-tests` | `revert-on-fail`)
- `persist(round, findings, marker)` → write resume state
- `recover()` → read resume state, return last completed round

On entry call `recover()` first: if a marker reports a completed round, resume from
`round = recovered + 1` instead of restarting at 0.

### Durable dispatch-axis state

At loop initialization, before the first dispatch, write `refine-loop-state.md` beside the
round-findings sidecar. It is a runtime sidecar outside every subject worktree, under a
deterministic recovery directory keyed by the target plus canonical subject identity. The
Workflow computes and passes that `state_key` and sidecar path to the shim on every invocation;
the file records the key, canonical subject identity, target, incomplete/terminal status, and
the dispatch axis. For example:

```text
state_key=<target-and-canonical-subject-identity>
canonical_subject_identity=<canonical subject identity>
target=pr
status=incomplete
engine=acpx
agent=opencode
mechanism=acpx-opencode
```

For parser-permitted `--engine smart-routing --agent smart-routing`, record
`mechanism=smart-routing`; it is a routing sentinel, never an ACPX mechanism override.

The sidecar is the only source of the dispatch axis. Re-read it before every critic and fixer
dispatch; never read `RELAY_ENGINE` or `RELAY_AGENT` from the process environment at that
point, because a resumed loop may run in a process whose environment carries a different or
absent axis.

`recover()` loads this sidecar before applying shim omission defaults. Accept recovery only if
all recomputed values match its `state_key`, canonical subject identity, and target. A matching
incomplete sidecar wins over a later flagless invocation. A missing, terminal, or mismatched
sidecar — including an unrelated flagless invocation — uses `in-session` / `claude`. The sidecar
is never an input to landing-verify or `persist()`, is never staged by checkpoint commits, and
is removed only after terminal convergence or escalation; a crash leaves it for resume.

## The generic loop algorithm

Operative algorithm (verbatim from `docs/refinement-contract.md`):

```
# landing-verify: confirm edits landed before any post_fix side-effects.
# Shared by both convergence modes; see "Landing Verify Contract" below.
def landing_verify(adapter, round):
  if adapter in ("pr", "ui"):
    # git-backed: git status --short + git diff in the real worktree.
    # Edits present → commit (message: refine(cycle-N): landing-verify, N=round).
    # Edits absent + no valid no-change signal → "failed".
    return landing_verify_git(worktree_path, round)
  else:  # spec or plan adapter (disk-backed)
    # confirm expected file exists and is non-empty on disk; no git commit.
    return landing_verify_disk(expected_file_path)

init:
  subject = adapter.load()
  if subject == SUBJECT_MISSING: halt, report SUBJECT_MISSING
  pre_snapshot = adapter.snapshot(subject)
  round = 0
  prev_scores = null; plateau_count = 0          # scored mode only

while round < max_rounds:
  round += 1
  findings = []
  # Walk critics; contiguous `parallel: true` critics dispatch in one batch,
  # then advance past the batch. Others dispatch sequentially.
  i = 0
  while i < len(critics):
    if critics[i].parallel:
      batch = collect_contiguous_parallel(critics, start=i)
      findings += dispatch_parallel(batch)
      i += len(batch)
    else:
      findings += dispatch(critics[i], subject)
      i += 1

  # aggregation step — branches on convergence_mode
  if convergence_mode == "scored":
      scores   = aggregator.merge_scores(critic_results)
      findings = aggregator.cap(all_findings, max_findings_per_cycle)
  else:                                          # binary (default/absent)
      if aggregator: findings = aggregator(findings)

  # convergence block — branches on convergence_mode
  if convergence_mode == "scored":
      if all(scores[d] >= thresholds[d] for d in dimensions):
          mark CONVERGED, break
      # plateau/pivot detection
      if prev_scores is not null:
          delta = avg(scores[d] - prev_scores[d] for d in dimensions)
          if abs(delta) < plateau_epsilon: plateau_count += 1
          else:                            plateau_count = 0
      fix_mode = "pivot" if plateau_count >= plateau_window else "refine"
      if fix_mode == "pivot": plateau_count = 0     # reset after a pivot
      fixer.apply(subject, findings, mode=fix_mode)

      if landing_verify(adapter, round) == "failed":
        record_failure("landing_verify_failed")
        continue  # next round; do not run post_fix

      adapter.post_fix("re-read")
      persist(round, {scores, findings, fix_mode}, persistence_marker)   # score-commit
      prev_scores = scores
  else:                                          # binary (default/absent)
      if convergence_predicate(findings): mark CONVERGED, break
      if not critical_or_important(findings): mark CONVERGED, break

      fixer.apply(subject, findings)

      if landing_verify(adapter, round) == "failed":
        record_failure("landing_verify_failed")
        continue  # next round; do not run post_fix

      adapter.post_fix(fixer.post_action)   # re-read / verify-tests / revert-on-fail

      persist(round, findings, persistence_marker)

if round >= max_rounds: mark ESCALATE
report(rounds_summary, findings_table)
```

Scored mode ESCALATE reports the best-scoring round (highest average dimension score) and the
surviving sub-threshold dimensions, not just a findings list. The `max_rounds` default is `10`
in scored mode (shim may override).

## How the loop dispatches

### Critics

Each critic names a `role` (a role file or agent path) and a `model`. Role resolution order
(§5): `RELAY_ROLE_PATH` override → `roles/<slug>.md` → `agents/<slug>.md` (kept agents only;
error `ROLE_FILE_MISSING` otherwise). agentType derivation: `role-class: registered` → use
binding `agentType` verbatim (e.g. `relay:code-reviewer`); `role-class: reader` →
`relay:leaf-reader`; `role-class: writer` → `relay:leaf-worker`.

Before every critic dispatch, re-read `refine-loop-state.md` for the axis (not `RELAY_ENGINE`
/ `RELAY_AGENT`). If engine is `acpx` or `smart-routing` and the role's `presets.yaml` binding
has `delegate_eligible: true`, dispatch `relay:delegate-and-watch`. Select the worker from
agent and pass the resolved mechanism as `ACPX_MECHANISM_OVERRIDE`, never a bare modality:
`claude` → `acpx-claude`; `codex` → `codex-session`; `opencode` → `acpx-opencode`; `hybrid` →
that role's `modalities.hybrid.engine`, normalized through the same mapping. The
`smart-routing` sentinel is not passed to that override: the watcher selects
`modalities.hybrid.engine` when present, otherwise the role's concrete mechanism, and reports
the selected worker and mechanism.

When the loop config carries `worktree`, fill the dispatched role's `WORKTREE_PATH` slot with
that literal and capture `EXPECTED_HEAD` via `git -C <worktree> rev-parse HEAD` before slot
substitution, whichever dispatch path (delegate-and-watch or the Agent tool) runs below.

Otherwise use the Agent tool procedure: derive the agentType per the table above; resolve the
role's tier with `"${CLAUDE_PLUGIN_ROOT}/scripts/resolve-tier.sh" <slug>` and set
`opts.model`/`opts.effort` from its output (`model=inherit` means omit `opts.model`, keep
`opts.effort`; when tiers are off set neither — adapter `model:` hints defer to this
resolution, since the binding wins); then build the prompt by reading `roles/<slug>.md` (or
`agents/<slug>.md` for kept agents), strip frontmatter, substitute `{{SLOT}}` inputs, and
prepend the standard autonomous preamble. Capture each critic's terminal envelope tokens from
the return value (e.g. `FINDINGS_PATH`, `REVIEW`, `SERVER_READY`/`BASE_URL`). After capturing
`FINDINGS_PATH`, Read that file; its parsed structured block IS the `findings` list the loop
operates on. A missing or empty file is a critic failure for the round (`record_failure`),
never zero findings.

A watched result of `done` is consumed normally. `errored`, `blocked`, or `not-done` gets
exactly one fresh-session re-dispatch; a second non-done result calls
`record_failure("delegated_dispatch_failed")` and continues to the next round. `max_rounds`
remains the loop cap, not a retry budget. `needs-decision` still surfaces to the user. One
opencode dispatch is one fresh session because its model binds on the first prompt; never reuse
a session across roles.

A refining retry is two separate `relay:delegate-and-watch` calls with identical inputs
(unchanged role body, typed-output schema, subject context, role binding, requested agent,
resolved mechanism), `fresh_session=true`, `max_turns=1`, and `retry_attempt=0` then
`retry_attempt=1` on distinct fresh session identities. Each call performs watcher cleanup
before returning any non-done bucket. Internal worker turns never consume the refining retry.

Walk `critics[]` in order:

- A critic without `parallel: true` dispatches sequentially — wait for its terminal token
  before advancing.
- A run of contiguous critics each carrying `parallel: true` dispatches as one parallel batch
  (one message, multiple Agent calls), then advance past the batch.

### Aggregator

The aggregator always runs inline in the coordinator: it owns loop coordination and is never a
delegated leaf. The engine branches on `convergence_mode` before calling it.

Binary mode (default) — the aggregator is a single callable over a flat findings list:

- `none` — pass findings through (single-critic targets like specs/plans).
- `severity-merge` — dedupe overlapping findings, keep highest severity per item.
- `debate-confirm` — only findings surviving the validator critic's challenge advance. The
  validator critic (`debate_enabled: true`) gets a stance prefix instructing it to challenge
  the reviewer's findings; knocked-down findings are dropped, the rest are "confirmed".

Scored mode — the aggregator is an object with two named operations:

- `aggregator.merge_scores(critic_results)` → `scores` dict (dimension → latest score). Each critic returns `{dimension, scores{…}, findings[]}`. `merge_scores` maps each critic's returned scoring keys to the config dimension keys.
- `aggregator.cap(all_findings, max_findings_per_cycle)` → `findings` list. Sort by severity (critical > major > minor), keep all criticals, then fill up to `max_findings_per_cycle`. `all_findings` is the flat union of every `findings[]` array from all critic result objects.

The plateau delta is the dimension-averaged signed delta shown in the algorithm. When it stays
under `plateau_epsilon` for `plateau_window` consecutive rounds, the next fixer call uses
`mode="pivot"` (holistic aesthetic redirection) instead of `mode="refine"` (targeted edits),
and the counter resets.

### Fixer + post-fix action

When findings remain after aggregation and the convergence predicate is unmet, dispatch the
single `fixer.role` (resolved via the same §5 order; agentType derived as above) with the
surviving findings. Populate `{{FINDINGS}}` with those surviving findings; `{{FINDINGS_PATH}}`
stays as the file-path fallback.

Before every fixer dispatch, re-read `refine-loop-state.md` for the axis (not `RELAY_ENGINE`
/ `RELAY_AGENT`). If engine is `acpx` or `smart-routing` and the fixer's `presets.yaml`
binding has `delegate_eligible: true`, dispatch `relay:delegate-and-watch` with the same
worker selection, `ACPX_MECHANISM_OVERRIDE` mapping, outcome handling, and one-retry contract
as for critics. When the loop config carries `worktree`, fill the fixer's `WORKTREE_PATH`
slot with that literal and capture `EXPECTED_HEAD` via `git -C <worktree> rev-parse HEAD`
before slot substitution, the same as for critics above. Otherwise use the in-session
Agent-tool procedure. The PR fixer's `verify-tests + revert-on-fail` post-gate remains
unchanged.

Then run `adapter.post_fix(fixer.post)`:

- `re-read` — re-`load()` the subject so the next round critiques the patched text.
- `verify-tests` — run the project's test command; a passing run is required to advance.
- `revert-on-fail` — if `verify-tests` fails, revert the fixer's change (adapter restores the
  prior checkpoint) and record the failure as a finding for the next round.

### Convergence / max-rounds / persistence

- After each round, evaluate `convergence_predicate` AND the generic
  `not critical_or_important(findings)` short-circuit. Either firing marks CONVERGED and
  breaks.
- At `round >= max_rounds` without converging, mark ESCALATE and report surviving findings
  rather than looping forever.
- After every fixing round, call `persist(round, findings, persistence_marker)` so a crashed
  loop can `recover()` and resume. The marker is target-specific (inline
  `Refinement: CONVERGED round N`, sidecar findings file, or git checkpoint commit).

### Reporting

On exit (CONVERGED or ESCALATE), emit a rounds summary and a findings table so the caller sees
what changed and why the loop stopped.

## Landing Verify Contract

A landing-verify step runs between `fixer.apply` and `adapter.post_fix` in every fixing round.
Its purpose: confirm the fixer's edits actually landed in the real branch before any downstream
step (post_fix, persist, convergence check) trusts the result. It branches on adapter backing
type:

- `pr` adapter — run `git status --short` + `git diff` in the absolute worktree path (the same
  path passed to the fixer as `WORKTREE_PATH`). If the tree is dirty, commit with message
  `refine(cycle-N): landing-verify` (N = current round number). This commit IS the checkpoint
  commit for that round; `persist()` runs `git status --short` and no-ops on a clean tree
  (clean-tree check, not message parsing). Duplicate commits per round are a defect. The
  `refine(cycle-N): ...` pattern is intentionally matched by `recover()` so that after a crash
  the recovered N reflects that cycle N's landing-verify succeeded.

- `ui` adapter — also git-backed (`git commit` for score-commits, `git rev-parse HEAD` for
  snapshots). Apply the same git-status landing-verify as `pr`. Do not use
  `landing_verify_disk` — a live-website target has no single `SPEC_FILE_PATH` or `PLAN_PATH`
  sentinel file.

- `spec` adapter — confirm `SPEC_FILE_PATH` exists on disk and is non-empty. No git commit.

- `plan` adapter — confirm `PLAN_PATH` exists on disk and is non-empty. No git commit.

If landing-verify fails (edits absent, no valid no-change signal), record the round as a
failure finding, skip `adapter.post_fix` and `persist()`, and continue to the next round
within the existing `max_rounds` cap. No new retry machinery beyond the round cap.
