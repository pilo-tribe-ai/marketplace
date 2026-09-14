---
name: getting-prs-approved
description: Drives one PR to a merge-enabling approval by answering every open review comment, human and bot alike, until reviewDecision is APPROVED. Use when asked to get PR N approved, iterate on the review comments until approved, handle the review feedback on a PR, or drive a PR to approval. Never merges and never fixes CI as its job.
argument-hint: "[pr-number]"
---

# getting-prs-approved

Drive **one PR** to a **merge-enabling approval** by answering its review feedback, round after
round, until an approval that actually satisfies branch protection lands — then stop and report.

**References** — read the first two before starting:
- [../../references/loop-engine.md](../../references/loop-engine.md) — the shared control loop:
  trigger-once/run-to-completion, the self-pacing wait, the claim/lease ledger, worker liveness,
  the local gate, and the escalation model. This skill supplies `TERMINAL`, `NEW_WORK`, and the
  per-comment triage.
- [../../references/github-access.md](../../references/github-access.md) — resolving `$REPO`,
  `$N`, `$ME`, and probing access.
- [references/codeowners.md](references/codeowners.md) — Step 1's approver parsing.

The local gate is contract-driven (loop-engine). Never hardcode it.

**Scope.** This skill **consumes and answers** review comments. It never merges, never fixes CI as
its job (`getting-prs-green`), and never resolves merge conflicts — if the branch is conflicted so
it can't push, it escalates, because that's `getting-prs-merged`'s job. Distinct from
`reviewing-prs`, which reviews a diff once and posts that single verdict without iterating, and
from `scheduling-pr-reviews`, which reviews *other* people's PRs on a cron.

## Step 0 — Resolve the PR

Per [github-access.md](../../references/github-access.md).

## Step 1 — Find an approver and request review (once, up front)

Before looping, make sure someone who can actually *unblock* the PR has been asked:

```bash
gh pr view $N --repo "$REPO" \
  --json reviewDecision,reviewRequests,latestReviews,files,mergeStateStatus
```

- `reviewDecision` (`REVIEW_REQUIRED` / `APPROVED` / `CHANGES_REQUESTED`) is the authoritative
  "does an approval unblock merge" signal.
- **Eligible approvers** = CODEOWNERS for the changed paths (parse and match per
  [references/codeowners.md](references/codeowners.md), against `files`) **plus** write-access
  collaborators:
  `gh api repos/$REPO/collaborators --jq '.[]|select(.permissions.push).login'`.
- **Request review** from eligible owners not already in `reviewRequests` or `latestReviews`:
  `gh pr edit $N --repo "$REPO" --add-reviewer <login>` for a user, `--add-reviewer <org>/<team>`
  for a team. No `@` in either form.
- **No eligible approver identifiable or requestable → escalate** (branch-protection dead-end).

## Step 2 — The loop hooks

**`TERMINAL`** — `reviewDecision == APPROVED`. An approving review from someone who doesn't
satisfy the requirement leaves `reviewDecision` at `REVIEW_REQUIRED` and does **not** end the
loop.

**`NEW_WORK`** — every open, unhandled review unit, from **humans and bots alike** (Copilot,
SonarCloud, CodeRabbit, …):

```bash
gh api repos/$REPO/pulls/$N/comments  --paginate   # inline review comments (threaded)
gh api repos/$REPO/pulls/$N/reviews   --paginate   # review summaries incl. CHANGES_REQUESTED
gh api repos/$REPO/issues/$N/comments --paginate   # issue-level PR comments
# resolved state is GraphQL-only — REST won't tell you:
gh api graphql -f query='{repository(owner:"OWNER",name:"NAME"){pullRequest(number:N){
  reviewThreads(first:100){nodes{id isResolved comments(first:20){nodes{id databaseId author{login} body}}}}}}}'
```

A unit is **unhandled** if its thread carries none of our markers (loop-engine's ledger). Skip
resolved threads and anything we already addressed or rebutted.

**A pr-flow `### Should fix` or `### Notes` entry is not `NEW_WORK`.** A body carrying the marker
`<!-- pr-flow:reviewing-prs head=… -->` is our own review, and it splits its findings into
`### Must fix`, `### Should fix`, and `### Notes`. Take the `### Must fix` entries as units. Leave
the `### Should fix` and `### Notes` entries alone: `reviewing-prs` already decided they do not
hold up approval, and it posts them without a fix prompt for that reason. Claiming them here would
re-open the round-trip the two lower buckets exist to prevent, on a PR that is often already
approved. The author may act on a should-fix or a note, but this loop never demands it, and a PR
is never blocked from `TERMINAL` by an unanswered should-fix or note.

**The Goal check line.** The built-in `pr-flow:reviewing-goal-achievement` lens writes it.
A line that reads `achieved` or `partially achieved` is not a work unit. A line that reads
`not achieved` or `undetermined` **is** a work unit, and both withhold the **pr-flow** approval.
They do not define `TERMINAL`. A human approval still sets `reviewDecision` to `APPROVED`, and
that ends the loop, as the `TERMINAL` definition above states.

Its fix is prose, not code. `not achieved` says the stated goal and the diff disagree.
`undetermined` says the lens did not read a goal. Write what this PR does into the PR title and
the PR body — `gh pr edit $N --repo "$REPO" --title '…' --body '…'` — then reply on our review
comment with the one-line summary of the edit. **Never change code to move a verdict**, and never
rebut this unit: the next pr-flow run reads the edited body and returns the new verdict itself.

**An `undetermined` verdict from a tool failure is an escalation, not a body edit.** The Goal
check sentence names the read failure — a `gh` call that failed, a lens that errored, or a lens
that timed out. No PR body edit changes any of those, so this unit never clears, and the loop
polls forever on it. Read the sentence. When it names a tool failure or a dispatch failure
instead of a missing goal, stop and report the failure per Step 3 **Escalate**.

**Never edit a closed issue to move a verdict.** The lens also reads every issue the PR closes
with a `fixes` or `closes` keyword, and it ranks that issue above the PR body. Rewriting the
issue to match the diff would move the verdict, and it would delete the requirement this lens
exists to check. A diff that does not do what its issue asks is a real result: report it and
escalate. Edit the PR body instead, and say there what the PR does and does not cover.

## Step 3 — Per unit: claim, then implement / rebut / escalate

Claim first per loop-engine — post `🔧 working — worker <id>` quoting the comment, reconciling
liveness for units already claimed. Then a dispatched subagent decides on the
implementation-vs-above-implementation line:

- **Implement** (trivial change, refactor, adjustment) → make it, run the local gate green, commit
  on the PR branch, push, reply `✅ addressed in <sha>`, then resolve the thread
  (`resolveReviewThread` mutation with the thread id).
- **Rebut** (inapplicable suggestion) → reply **quoting the comment** with a neutral, professional,
  assertive argument for why it doesn't apply. No hedging, no persona. Then resolve the thread.
  - Inline: `gh api repos/$REPO/pulls/$N/comments -f body='> …quote…\n\n…' -F in_reply_to=<comment_id>`
  - Issue-level: post a new issue comment quoting it.
- **Escalate** (loop-engine) → architecture/design/above-implementation ask; can't validate green;
  branch conflicted so we can't push. Stop and report.

**Dispatch discipline:** one subagent per unit or small batch, returning only a one-line outcome
plus the sha; keep noisy output inside the subagent. Batch the round — implement all trivial units
and draft all rebuttals, run the gate **once**, single push, then post all outcome markers.

## Step 4 — Standoff watch

A human reviewer re-opening or re-commenting against one of **our rebuttals** is the standoff
escalation: **stop and report, do not re-argue.** Detect it as a new reply, authored by a human
(not us, not a bot), on a thread we previously rebutted. A bot re-flagging is just another unit.

## Step 5 — Sleep or finish

Non-terminal with no escalation → schedule the next poll (`ScheduleWakeup` ~1500–1800s) and end
the turn. Approved → report the PR number, the approving reviewer, and that
`reviewDecision == APPROVED` unblocks merge.

## Notes & footguns

- **Merge-enabling ≠ any approval.** `reviewDecision == APPROVED` is the gate, not "a green review
  exists."
- **Bots are triaged like humans** for implement-vs-rebut, but the standoff escalation is
  human-only.
- **The `🔧 working` claim marker plus the liveness check** is what stops a slow implementation
  from being re-dispatched by the next wake. It's load-bearing, not bookkeeping.
- **Behind or conflicted branch** is `getting-prs-merged`'s job — escalate, or note that running
  it concurrently keeps the branch fresh.
