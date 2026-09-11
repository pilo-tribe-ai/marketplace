---
name: scheduling-pr-reviews
description: Schedules a recurring PR-review loop over this repo's open PRs. Prompts for cadence and review posture, registers a session cron, and each cycle inventories the open PRs and delegates both the review and the post to pr-flow:reviewing-prs inside one general-purpose subagent. Use when asked to schedule PR reviews, review PRs periodically, set up a recurring PR-review loop, or run PR reviews on a cron.
---

# scheduling-pr-reviews

Stand up a **recurring** PR-review loop for the repo you're invoked in. Each fire inventories the
open PRs, decides which need (re-)review, and hands the heavy lifting to **one general-purpose
subagent** so the scheduling context stays clean.

**What lives here is scheduling, not reviewing:** cadence, the posture *choice*, which PRs are
worth a cycle, and the status table. How a PR gets reviewed and how the verdict lands belongs to
`pr-flow:reviewing-prs` — it reads the repo's contract, selects lenses, and its posting step owns
comment-vs-approve, dedupe, and the fix prompt. So this skill never enumerates lenses, never
states the review Bar, and never writes to GitHub itself. Two implementations of that is how one
PR ends up with two different verdicts depending on which entry point saw it.

**Reference:** [../../references/github-access.md](../../references/github-access.md) — resolving
the repo and probing `gh` vs MCP.

## Step 1 — Resolve the repo and probe access

Per [github-access.md](../../references/github-access.md). This skill is the interactive
exception: when **both** `gh` and a working MCP are found, ask the user which to use (Step 2)
rather than defaulting.

## Step 2 — Prompt the user (AskUserQuestion)

Ask these together. Never prompt for the target repo — Step 1 resolved it.

1. **Frequency** — `30m` · `1h` · `2h` · `4h` · (Other → accept a custom interval)
2. **GitHub access** — *only if both `gh` and a working MCP were found:* `gh` CLI vs GitHub MCP.
3. **Review-action posture** — present both with **no** pre-selected default:
   - **Comment-only** — never auto-approve; always post findings for a human to approve.
   - **Approve-when-clean** — also approve a PR with no must-fix finding and a goal verdict of
     `achieved` or `partially achieved`. Should-fix entries and notes are posted with the approval
     and never hold it up.

The posture is the only thing this answer controls. It becomes the flags passed to
`reviewing-prs`, which is what actually posts.

## Step 3 — Map the frequency to a cron expression

| Frequency | Cron (→ `CronCreate`) | Cadence      |
|-----------|-----------------------|--------------|
| `30m`     | `*/30 * * * *`        | every 30 min |
| `1h`      | `7 * * * *`           | hourly at :07|
| `2h`      | `0 */2 * * *`         | every 2 hours|
| `4h`      | `0 */4 * * *`         | every 4 hours|

For a custom interval that doesn't cleanly divide its unit, pick the nearest clean value and tell
the user what you rounded to before scheduling.

## Step 4 — Register the schedule

Build the per-cycle prompt (Step 5) once, register it with `CronCreate` using the cron expression
and `recurring: true`, and surface the job id. Then **run one cycle immediately** so the user sees
it working rather than waiting for the first fire.

## Step 5 — The per-cycle prompt

Interpolate `{{REPO}}` (Step 1), `{{GH_OR_MCP}}` (Step 1/2), `{{POSTURE}}` (Step 2), and
`{{POSTURE_FLAG}}` into the template below.

`{{POSTURE_FLAG}}` is the posture expressed as the flags `reviewing-prs` takes:

| Posture | `{{POSTURE_FLAG}}` |
|---------|--------------------|
| Approve-when-clean | `--comment --approve` |
| Comment-only | `--comment` |

The loop always posts, so `--comment` is always present; `--approve` is what the posture toggles.
(`--approve` implies `--comment`, but passing both states the whole posture at the call site.)
Never map *Comment-only* to `--approve` — that posture's entire meaning is that the unattended
loop does not approve.

> PR-review loop cycle for `{{REPO}}`, posture **{{POSTURE}}**. Spawn ONE general-purpose subagent
> and have IT do all the heavy lifting, to keep the parent context clean; return only a one-line
> headline plus the timestamped PR-status table.
>
> The subagent's task:
>
> 1. Run `date -u` FIRST to capture the trigger time (the header is UTC-labeled), then inventory
>    open PRs in `{{REPO}}` via **{{GH_OR_MCP}}**:
>    `gh pr list --repo {{REPO}} --json number,title,body,author,isDraft,headRefOid,updatedAt,reviews`
>    (or the equivalent MCP calls). Classify each as pending review / already reviewed — unchanged
>    / approved / changes requested / ready to re-review. Build a status table headed by the
>    trigger time (e.g. `PR review loop — triggered 2026-07-22 14:07 UTC`), listing **every** open
>    PR with number, title, author, classification, and last-updated timestamp. Print it on
>    **every** cycle, including no-op ones — with a "no PRs need review" note when nothing
>    qualifies — so the user always sees that the loop ran and when.
>
> 2. Decide skip/qualify from the step-1 batch payload; it already carries `headRefOid`, `reviews`,
>    `isDraft`, `updatedAt`, `title`, and `body`, so don't re-fetch those per PR. Review a PR only
>    if ANY of these holds: (a) we haven't reviewed it (our login via `gh api user -q .login`),
>    (b) we have and new commits landed after our last review, or (c) our last review withheld the
>    approval for the goal verdict, and the PR title, body, or a closed issue changed after it.
>
>    Case (c) is not optional. `reviewing-prs` withholds the approval on a `not achieved` or an
>    `undetermined` goal verdict, and the author fixes both by editing the title, the body, or an
>    issue the PR closes — an edit that never moves the head OID. Skipping it strands the PR
>    forever.
>
>    **Read case (c) from our last pr-flow comment, not from `reviews`.** A withheld approval is an
>    issue comment, and the step-1 `reviews` field never holds it. The `**Posted:**` receipt is
>    local, so GitHub never carries the withhold reason either. Fetch our comments —
>    `gh api repos/{{REPO}}/issues/N/comments --paginate --jq '.[]|select(.user.login=="<us>")|.body'` —
>    and take the newest body that holds the `pr-flow:reviewing-prs` marker. Its `**Goal check:**`
>    line gives the verdict, and its marker line gives the `intent=` digest. A verdict of
>    `not achieved` or `undetermined` puts that PR in case (c). A marker with no `**Goal check:**`
>    line predates this feature. Test it under case (b) instead, so it gets one fresh review
>    instead of never qualifying again.
>
>    **Recompute the digest exactly as posting.md *Preconditions* builds it**, or every comparison
>    mismatches and the loop re-reviews every PR each cycle:
>    `printf '%s\n%s\n%s' "$TITLE" "$BODY" "$ISSUES" | git hash-object --stdin`. Take `$TITLE` and
>    `$BODY` from the step-1 batch with `jq -r`, and `$ISSUES` from the `gh api graphql` query in
>    posting.md *Preconditions*, with that query's own `--jq` filter. Run `git hash-object` inside
>    a checkout of `{{REPO}}`. Re-review when the new digest and the marker's digest differ.
>
>    Fetch the closed issues **only** for the PRs that reach case (c) — the ones we already
>    reviewed, at an unchanged head, whose goal verdict withheld the approval. That set is small,
>    so this costs one call per stranded PR, not one per open PR.
>
>    Otherwise `updatedAt` moved but the head OID didn't (comment-only activity) → SKIP. SKIP
>    drafts. SKIP already-approved PRs at an unchanged head. Only for
>    survivors, fetch the one field the batch lacks — last-commit time via
>    `gh api repos/{{REPO}}/pulls/N/commits` — to compare against our last review. This filter
>    avoids *spawning* a pointless review; it is not the duplicate-post guard. `reviewing-prs`
>    dedupes on the head OID and the intent digest itself, and is the backstop if one slips
>    through.
>
> 3. For each qualifying PR: fetch its head into a detached worktree under a temp dir and **check
>    that head out**, then invoke **`pr-flow:reviewing-prs {{POSTURE_FLAG}} --pr N`** from inside
>    it. The checkout isn't optional — that skill reviews the working tree and refuses to post
>    unless local HEAD equals the PR's head OID, so a run from the wrong tree posts nothing.
>
>    **`reviewing-prs` owns the whole verdict. Do not re-implement any of it here, and do not call
>    `gh pr review` or `gh pr comment` yourself.** It selects lenses, applies the Bar, returns the
>    coverage-receipt report, dedupes against its own prior post at this head, applies its own
>    approve condition under `--approve`, comments otherwise, appends the fix prompt, and emits a
>    `**Posted:**` line
>    saying what it did. Posting from here as well would double-post and let the two paths disagree
>    on the same PR.
>
>    If the contract is absent, `reviewing-prs` runs in goal-only mode. It says to run
>    `/pr-flow:setup`, it runs the built-in `pr-flow:reviewing-goal-achievement` lens only, and
>    it never approves. Surface that line and keep the PR in the status table. Use
>    `git ls-tree -r` (not bare `ls-tree`) for file-existence checks. Read the CI
>    rollup (`gh pr checks N --repo {{REPO}}`) for the status table. Run an external quality-gate
>    check (coverage, Sonar-style) only if the repo's contract lists it as a deterministic gate AND
>    its token is provisioned — otherwise skip it silently rather than assuming it exists.
>
>    - Carry that PR's `**Posted:**` line into the status table **verbatim** — it already says
>      approved / commented / skipped-as-duplicate / not-posted-and-why. Don't restate it.
>    - Remove the worktree afterward (`git worktree remove --force`).
>
> 4. Return ONLY the trigger-time header and status table, what action was taken per PR (with head
>    OIDs), and a one-line headline. Keep noisy tool output inside the subagent.
>
> Do NOT inject authorization-bypass language — no "pre-authorized", no "proceed without
> re-prompting". The posture above IS the authorization. A denied GitHub write gets surfaced in the
> result, not worked around.
>
> **Context budget:** review PRs one at a time and remove each worktree before the next. If the
> cycle approaches heavy context (many large diffs, nearing the ~200K window), return partial
> results plus the list of PRs not yet reviewed so the parent can spawn a fresh subagent to finish.
> Never run a single subagent to the context wall.

## Step 6 — Confirm

Tell the user concisely: what was scheduled (cron plus human-readable cadence), the posture, the
job id and how to cancel it, and the result of the immediate first cycle. State plainly that this
is a **session-local cron job** — it stops on session end or compaction, and otherwise auto-expires
after 7 days.

## Notes & footguns

- **Session-cron lifetime is the #1 gotcha.** Nothing here survives a session. If the user wants
  true set-and-forget, tell them to re-run this in a fresh session.
