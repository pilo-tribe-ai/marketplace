# PR lifecycle loop engine (shared)

The common control loop behind `getting-prs-approved`, `getting-prs-green`, and
`getting-prs-merged`. All three are the *same* loop over one PR; only the `NEW_WORK` predicate and
the work action differ. Read this once; each skill supplies the two hooks.

## Contents
- The loop
- Self-pacing wait
- GitHub thread = the ledger (claim / lease)
- Worker liveness and completion
- Local CI-equivalent gate before every push
- Escalation model
- No authorization-bypass language

## The loop

```
invoked once on a PR →
loop:
  read PR state                                    # cheap gh reads only
  if TERMINAL(pr): report in this session; STOP    # skill-specific success
  work = NEW_WORK(pr)                              # skill-specific
  if work empty: schedule next poll; end turn      # self-pacing wait
  for unit in work:
     claim-or-skip via the GitHub ledger
     drive the claimed worker to completion, gating on the local CI check
  if an ESCALATE condition fired: report the blocker; STOP
  schedule next poll; end turn
```

**Trigger-once / run-to-completion.** One invocation runs autonomously to a terminal state or an
escalation. It is never handed back mid-round and never asks a question inside the loop — success
and every escalation **stop and report in this session**.

## Self-pacing wait

Between rounds you are waiting on a human or on CI — minutes to days. Sleep long, and do only
cheap reads on wake.

- `ScheduleWakeup` with `delaySeconds` ~1500–1800 (≈25–30 min), re-firing this same skill
  invocation. Tight polling burns tokens and cache while nothing has changed. Spin up workers only
  when `NEW_WORK` is non-empty.
- On any terminal state or escalation, **do not reschedule** — report and stop.
- Switch to a recurring session cron (`CronCreate`, self-deleting on the terminal state) only when
  the user wants a **fixed wall-clock cadence** or an **independently listable job**. Not for
  durability — the cron is session-bound too. Not the default; offer it only if asked.

Because all state lives on GitHub, a fresh cycle re-derives everything. Nothing is lost across a
wake, a `/compact`, or a restarted session.

## GitHub thread = the ledger (claim / lease)

**There is no local state file.** Cross-cycle memory lives in the PR as marker replies, so
overlapping wakes and restarted sessions stay consistent. Resolve `$ME` once per cycle.

| Marker on the unit | Meaning | Action |
|---|---|---|
| `✅ addressed in <sha>` or a posted rebuttal | done | skip |
| `🔧 working — worker <id>` | claimed, in flight | worker alive → leave it; stalled/dead → re-drive to completion |
| none | unclaimed | **claim** by posting `🔧 working` (quoting the comment) **first**, then dispatch |

Each marker is a threaded reply quoting its target, so every action traces to what prompted it,
and it records the worker handle for the next cycle's liveness check.

**Reply-then-act:** post the claim marker before dispatching; post the outcome marker after the
worker returns.

A small check-then-claim race exists between scanning and posting. For a single-operator ~25-min
loop that is acceptable — the liveness reconciliation below is the backstop that stops a duplicate
worker from running to completion.

## Worker liveness and completion

Do the heavy lifting in dispatched subagents so the loop's own context stays lean. Every wake
reconciles marker against live worker:

- marker working **and** worker live → leave it; never spawn a duplicate.
- marker working **but** no live worker (session restarted, task died) → the unit is orphaned;
  re-dispatch and drive it to completion. The loop owns *finishing* claimed work, not just
  starting it.

## Local CI-equivalent gate before every push

Before any push, replicate locally the exact checks that block the PR in CI. The gate commands are
**repo-specific and never hardcoded** — run the repo's discovered gates from the **Deterministic
gates** section of `.claude/pr-flow/contract.md`. If that file is absent, tell the user to run
`/pr-flow:setup` and fall back to the repo's own CI config for this run.

Run the **full** gate set, never a filtered subset — a partial run passes on stale artifacts.

**Red = no push.** A red push wastes an entire re-review cycle. Commits land directly on the PR
branch; never open a new branch.

## Escalation model

The line is **implementation vs. above-implementation**.

**Autonomous:** trivial code changes, refactors, implementation adjustments — do them, validate
green, push, mark addressed.

**Escalate (stop and report in session):**

- a reviewer asks for an **architecture or design decision**, or anything above the implementation
  layer (scope, contract, "should this exist?");
- a **rebuttal standoff** — a human pushes back on one of our autonomous rebuttals. Never argue
  with a human twice;
- a change **cannot be validated green locally** and can't be resolved;
- **no eligible approver** can be identified or requested (branch-protection dead-end);
- *if the skill syncs the base:* a **semantic** rebase conflict, as opposed to the
  trivial/mechanical ones it resolves autonomously;
- *if the skill retries a unit:* the unit exhausted its **attempt cap**, or the only way to pass
  is to stop the check from looking (suppress, baseline, exclude, delete).

The last two are conditional on what a skill *does*, not on which skill it is — a new skill that
syncs the base or retries inherits them without editing this file.

## No authorization-bypass language

Never inject "pre-authorized" or "proceed without prompting" text into dispatched worker prompts.
If a GitHub write or a push is denied, **surface it in the report** — don't work around it.
