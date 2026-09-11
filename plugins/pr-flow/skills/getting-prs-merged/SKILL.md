---
name: getting-prs-merged
description: Drives an approvable PR to merged via GitHub squash auto-merge, keeping its branch fresh with its base until GitHub fires the merge. Use when asked to get PR N merged, turn on auto-merge and babysit it until it lands, or keep a PR's branch fresh with main. Handles base freshness only — approval and red checks belong to the sibling pr-flow skills.
argument-hint: "[pr-number]"
---

# getting-prs-merged

Drive **one PR** to **merged**: turn on GitHub native squash auto-merge, then keep the branch
fresh with its base until GitHub fires the merge — then stop and report.

**References** — read the first two before starting:
- [../../references/loop-engine.md](../../references/loop-engine.md) — the shared control loop:
  trigger-once/run-to-completion, the self-pacing wait, worker liveness, the local gate, and the
  escalation model. This skill supplies `TERMINAL`, `NEW_WORK`, and the base-sync action.
- [../../references/github-access.md](../../references/github-access.md) — resolving `$REPO`,
  `$N`, `$HEAD_REF`, `$BASE_REF`, and probing access.
- [../../references/base-sync.md](../../references/base-sync.md) — Step 3's procedure.

**Scope.** This skill handles **auto-merge and base freshness only**. It delegates waiting for
approval to `getting-prs-approved` and red checks to `getting-prs-green`, and re-implements
neither. The `getting-prs-*` skills are safe to run concurrently on one PR — their state lives on
GitHub (loop-engine).

## Step 0 — Resolve the PR

Per [github-access.md](../../references/github-access.md).

## Step 1 — Enable auto-merge (once, up front)

```bash
gh pr merge $N --repo "$REPO" --auto --squash
```

GitHub now merges on its own the moment required approvals **and** required checks are satisfied.
Always squash; don't switch merge methods. Auto-merge disabled on the repo, or blocked by a policy
this skill can't satisfy → **escalate**.

## Step 2 — The loop hooks

**`TERMINAL`** — the PR is merged:
```bash
gh pr view $N --repo "$REPO" --json state,mergedAt -q '.state'   # == "MERGED"
```

**`NEW_WORK`** — the branch is behind or conflicted:
```bash
gh pr view $N --repo "$REPO" --json mergeStateStatus,mergeable
# mergeStateStatus: BEHIND | DIRTY (conflicts) | BLOCKED (needs approval/checks) | CLEAN
# mergeable:        MERGEABLE | CONFLICTING | UNKNOWN
```

`BEHIND` or `CONFLICTING` → sync (Step 3). `BLOCKED` or `CLEAN` with no drift → nothing to do;
approval and checks are other skills' jobs, so sleep. `UNKNOWN` → recheck next wake.

## Step 3 — Keep the branch fresh (per round)

Follow [base-sync.md](../../references/base-sync.md). Keep auto-merge enabled throughout — GitHub
lands the merge as soon as its own gates pass.

## Step 4 — Sleep or finish

Not merged, no escalation → schedule the next poll (`ScheduleWakeup` ~1500–1800s) and end the
turn. Merged → report the PR number, the merged sha, and that it landed via squash auto-merge.

## Notes & footguns

- **This skill doesn't make a PR mergeable — it keeps it mergeable.** `BLOCKED` on approval or
  checks is not our work. We enable auto-merge and keep the base fresh so GitHub can fire the
  moment those clear.
- **The base can move again after a clean sync.** Expected; the loop just re-syncs next wake.
