---
name: getting-prs-green
description: Drives one PR's checks to all-green — syncs the branch with its base, fixes each failing check from its own CI logs, gates locally, pushes, and re-checks until CI passes or a cap stops it. Use when asked to get PR N green, fix the failing checks, drive a PR to green, or make CI pass on a PR. Never merges, never approves, and never suppresses a check to make it pass.
argument-hint: "[pr-number]"
---

# getting-prs-green

Drive **one PR** to all checks green, then stop and report. Each round: sync with the base, read
what CI actually failed on, fix it, prove it locally, push, wait for CI to re-report.

**References** — read the first two before starting:
- [../../references/loop-engine.md](../../references/loop-engine.md) — the shared control loop:
  trigger-once/run-to-completion, the self-pacing wait, worker liveness, the local gate, and the
  escalation model. This skill supplies `TERMINAL`, `NEW_WORK`, the fix action, and the caps.
- [../../references/github-access.md](../../references/github-access.md) — resolving `$REPO`,
  `$N`, `$HEAD_REF`, `$BASE_REF`, `$ME`, and probing access.
- [../../references/base-sync.md](../../references/base-sync.md) — Step 2's procedure.

The local gate is contract-driven (loop-engine). Never hardcode a build or test command here.

**Scope.** This skill owns **red checks** — the job `getting-prs-merged` explicitly delegates
away. It's safe alongside `getting-prs-approved` and `getting-prs-merged` on the same PR, since
all its state lives on GitHub: the pushed commits, their `pr-flow-green:` attempt trailers
(Step 3), and the check rollup. **Two copies of *this* skill on one PR is the unsafe case** —
they share no claim marker and would race on `--force-with-lease`. Before the first fix round,
check the attempt trailers on `origin/$HEAD_REF` and stop if another run is mid-round.

## Step 0 — Resolve and check out the PR

Resolve and probe per [github-access.md](../../references/github-access.md), then stop if there's
no PR, if `state != OPEN`, or if **the PR is a draft** — a draft's checks are advisory, and fixing
them burns rounds on a moving target. Say to mark it ready first.

**Then put the working tree on the PR branch.** Every later step commits and pushes, and nothing
else here does this. Skipping it lands fixes on whatever happened to be checked out —
`getting-prs-green 123` from the default branch would commit straight to it:

```bash
git fetch origin "$HEAD_REF"
git checkout "$HEAD_REF" && git reset --hard "origin/$HEAD_REF"
```

Uncommitted local changes → **stop and report**. Never discard the user's work to take the branch.

## Step 1 — Read the PR state (the loop hooks)

One call per round; everything below reads from that payload:

```bash
gh pr view $N --repo "$REPO" \
  --json headRefOid,mergeable,mergeStateStatus,statusCheckRollup
```

**Normalize the rollup before judging it.** Two shapes burn rounds otherwise: it carries **one
entry per workflow run**, so a check that failed and was re-run green appears twice (a real PR
showed 46 entries for 20 names) — judging per entry keeps a stale `FAILURE` alive forever. And
entries are either `CheckRun` (`name`, `status`, `conclusion`, `detailsUrl`) **or** `StatusContext`
(`context`, `state`, `targetUrl` — no `conclusion`, no `detailsUrl`), so an un-normalized legacy
commit status matches neither hook and the loop sleeps forever on a red PR.

```bash
jq -r '[.statusCheckRollup[]
        | {name:   (.name // .context),
           at:     (.completedAt // .startedAt // .createdAt // ""),
           state:  (.conclusion // .state // .status),
           url:    (.detailsUrl // .targetUrl // "")}]
       | group_by(.name) | map(max_by(.at))' <<<"$PR_JSON"
```

**`TERMINAL`** — every normalized entry is `SUCCESS`/`NEUTRAL`/`SKIPPED`, none are
`QUEUED`/`IN_PROGRESS`/`PENDING`/`EXPECTED`, and `mergeStateStatus` is not `BEHIND`. Report and
stop. (`BLOCKED` on approval is fine — that's `getting-prs-approved`'s job, not a red check.)

**`NEW_WORK`**, in priority order:

1. **Base drift** — `mergeStateStatus == BEHIND` or `mergeable == CONFLICTING`. Always first:
   checks run against the merge of your branch and its base, so a stale branch's red isn't
   necessarily *your* red, and its green isn't trustworthy either.
2. **Failing checks** — every normalized entry in `FAILURE`, `TIMED_OUT`, `ACTION_REQUIRED`,
   `CANCELLED`, or `ERROR`, minus any that hit the caps in Step 4.

A state in neither list is **work, not silence** — report it rather than sleeping on it, or an
unknown state stalls the loop invisibly. Still-running checks aren't work; they're the reason to
sleep. `mergeable == UNKNOWN` means GitHub is still computing: recheck next wake.

## Step 2 — Sync the branch with its base

Follow [base-sync.md](../../references/base-sync.md), then return to Step 1 — a sync re-triggers
CI, so the failing set you had is stale.

## Step 3 — Fix the failing checks (one batched round)

Dispatch the failing checks to **one subagent each, in parallel**, to keep log volume out of the
loop's context. Each returns a **diagnosis, not a log**: the check name, the file and line the
failure names, the assertion or rule that fired, and at most ~20 lines of quoted log. That digest
is what the fix pass works from, so a subagent returning "it failed" has failed its dispatch.

- **Get the real failure, not the check name.** For GitHub Actions take the run id from the
  entry's `detailsUrl` — the URL is `…/actions/runs/<run-id>/job/<job-id>`, so match the segment
  after `/runs/`, not the trailing number — then read
  `gh run view <run-id> --repo "$REPO" --log-failed`. For an external check (a `StatusContext` has
  `targetUrl`, not `detailsUrl`) follow that URL. If the contract lists an external quality gate
  with an API, query the API for failing conditions rather than scraping a page — but only when
  the contract lists it and its token is provisioned. **No actionable output → escalate that
  check** rather than guessing.
- **Known flakes get rerun, not fixed.** If the contract or CLAUDE.md names a check flaky,
  `gh run rerun <run-id> --failed --repo "$REPO"` and move on. Don't edit code to chase a flake.
  When unsure, read the log: a real failure names a file and a line. Rerunning a genuinely broken
  check wastes a CI cycle; "fixing" a flake edits code for no reason.

Then **one fix pass for all of them together**, on the PR branch:

1. Diagnose from the digests; apply the **minimal** fix.
2. Run the contract's full gate set (loop-engine's gate) — never a filtered subset.
3. **Red gate → do not commit, do not push.** Return what's still failing.
4. Green → commit on the PR branch (no new branches), then a **single**
   `git push --force-with-lease`. Stale lease means someone else pushed: **stop and report**.
   Never `--force`, never retry over them.

**Fix the code, never the evidence.** Do not suppress, baseline, or exclude a finding to turn a
check green — no `NOSONAR`-style pragmas, no suppression annotations, no rule/exclusion or
baseline edits, no resolving findings through a quality-gate API, no deleting or skipping the
failing test. A coverage gate wants tests; a duplication gate wants the duplication refactored. If
the only way to pass is to stop the check from looking, that is an escalation.

## Step 4 — Caps (the anti-thrash rules)

- **4 attempts per check, lifetime.** A 5th is an escalation, not another try.
- **2 revisions per check within one round.** If the first fix doesn't green the gate, revise once;
  then the round ends.
- **4 rounds, then stop and report** even mid-progress. An unbounded CI-fixing loop is how a
  session burns a day on a check that needs a human.

Track attempts **by check name across the whole run** — it's the only thing that stops two checks
fighting each other from looping forever, which means the count must survive a wake. In-context
counting doesn't: loop-engine keeps no local state file, every wake re-derives from GitHub, and
this loop sleeps ~25–30 min between rounds, so a count held in reasoning resets exactly when the
cap matters. End each fix commit's message with

```
pr-flow-green: attempt <k> <check-name>
```

so `git log --grep='^pr-flow-green:' "origin/$BASE_REF..origin/$HEAD_REF"` reconstructs every
count on wake. No trailer for a check → zero attempts so far.

## Step 5 — Wait for CI, then re-assess

After a push the rollup still shows the old run, so block on the built-in watcher rather than
hand-rolling a poll loop — each manual poll costs a full turn, and a 10-minute wait would burn
~20 of them:

```bash
timeout 600 gh pr checks "$N" --repo "$REPO" --watch --interval 30; RC=$?
```

**Branch on `$RC`** — three outcomes share "non-zero". `0` all passed and `1` some check failed
both mean CI settled; they are the next round's input, not an error. `8` still pending and `124`
our own `timeout` fired mean it did **not** settle: sleep per loop-engine rather than opening a
fix round against logs that don't exist yet. Then loop back to Step 1.

## Step 6 — Report

Terminal or escalated, report **in this session**: the PR number, the head sha, what each round
changed (sha + one line), which checks are green now, and for anything unresolved the check name
plus its specific blocker. Name the escalation; don't summarize it as "some checks failed."

Re-read the head sha after the last push (`gh pr view "$N" --repo "$REPO" --json headRefOid`)
rather than carrying over the round's opening payload, which predates the fix commit.

## Notes & footguns

- **A stale branch makes every other signal a lie.** That's why base sync is first: fixing a
  failure main already fixed, or trusting a green that predates a breaking change on main, both
  come from skipping it.
- **Local green ≠ CI green.** The gate filters bad pushes; it isn't proof. The terminal state is
  always read from GitHub, never from local tool output.
- **Never merges, never approves.** Green is the terminal state. Merging is `getting-prs-merged`;
  approval is a human's call, or `reviewing-prs --approve`.
- **Clean up after a failed conflict rebase.** base-sync destroys its worktree on the paths it
  names, but if the gate goes red mid-rebase the shell is still inside it — `cd -` and
  `git worktree remove --force "$WT"` before reporting.
