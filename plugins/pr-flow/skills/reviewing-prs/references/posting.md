# Posting the review to GitHub

Read this when `--comment` or `--approve` was passed. With no flag the report stays in-session and
none of this runs.

**This is the only place pr-flow writes a review verdict.** `scheduling-pr-reviews` picks the
posture and calls this skill with the matching flag rather than posting itself, so ad-hoc and
scheduled runs agree on a PR by construction and share one dedupe ledger. If a caller needs
different posting behavior, add it here behind a flag — a second `gh pr comment` anywhere else
re-opens that split.

**Findings are posted verbatim**, never re-summarized. Step 6 already wrote them in ASD-STE100, so
a rewrite here can only make them worse. A clean review posts its header and coverage receipt,
which is all there is to say. Everything below is about *whether* and *how* it lands.

**The posted body describes the diff and nothing else.** It never states that a check failed, that
CI is red, that the branch is behind its base, that it needs a rebase, or that it has a conflict.
This skill does not read any of that, so the only way such a line reaches a PR is the **Run
caveat** line — which is why *Post* removes it. Other skills own the checks and the merge state.
An author who reads them here gives less attention to the part that is ours.

## Contents
- Preconditions
- Dedupe
- Approve condition
- Post
- Receipt

## Preconditions

All of these must hold **for the post**. A failure disables *posting only*: still run the full
review, still emit the Step 6 report, and append `**Posted:** not posted — <reason>` to it. A
failed post never fails the review — including under the Step 0 hoist, where "stop" means stop
posting, never stop the run. The one exception is a dedupe hit, which does end the run.

**GitHub access works** — per [../../../references/github-access.md](../../../references/github-access.md).
Reuse the path the caller is already on rather than re-probing.

**A PR resolves** — `--pr <number>` if passed, else the current branch's. Fetch every field the
rest of this file needs in one call; nothing below re-fetches:

```bash
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
ME="$(gh api user -q .login)"
TARGET="${PR:-$(git rev-parse --abbrev-ref HEAD)}"        # --pr N, else this branch
PR_JSON="$(gh pr view "$TARGET" --repo "$REPO" \
  --json number,author,headRefOid,isDraft,body,title,commits)" || PR_JSON=""
N="$(printf '%s' "$PR_JSON"      | jq -r '.number')"
HEAD="$(printf '%s' "$PR_JSON"   | jq -r '.headRefOid')"  # full 40-char OID
AUTHOR="$(printf '%s' "$PR_JSON" | jq -r '.author.login')"
IS_DRAFT="$(printf '%s' "$PR_JSON" | jq -r '.isDraft')"
TITLE="$(printf '%s' "$PR_JSON" | jq -r '.title')"
BODY="$(printf '%s' "$PR_JSON"   | jq -r '.body')"
COMMITS="$(printf '%s' "$PR_JSON" | jq -c '.commits')"

# The issues this PR closes. `gh pr view --json` has no field for them, so GraphQL is
# the only source. GitHub computes this list from the closing keywords in the body and
# from the sidebar link, so never parse the body for `fixes #N` yourself.
# `[]` means the PR closes no issue. An empty string means the call failed. The two are
# different answers, and Step 2 of the lens treats them differently.
ISSUES="$(gh api graphql -f owner="${REPO%%/*}" -f name="${REPO##*/}" -F number="$N" -f query='
  query($owner:String!,$name:String!,$number:Int!){
    repository(owner:$owner,name:$name){ pullRequest(number:$number){
      closingIssuesReferences(first:20){
        nodes{ number title body url repository{nameWithOwner} } } } } }' \
  --jq '.data.repository.pullRequest.closingIssuesReferences.nodes')" || ISSUES=""

INTENT="$(printf '%s\n%s\n%s' "$TITLE" "$BODY" "$ISSUES" | git hash-object --stdin)"  # 40-char
```

reviewing-prs Step 4 passes `$TITLE`, `$BODY`, `$COMMITS`, and `$ISSUES` to
`pr-flow:reviewing-goal-achievement`. The calls above carry all four, so nothing below
re-fetches them, and the lens must not fetch them again. An empty `$PR_JSON` binds the first
three to an empty value; Step 4 states what to do then.

`$INTENT` is a 40-character digest of the title, the body, and the closed issues. It is the goal
verdict's input. The *Dedupe* key needs all three parts.

An author fixes a `not achieved` or an `undetermined` verdict by editing the title, the body, or
a closed issue. No such edit moves `$HEAD`. A body that only says `Fixes #7` puts the whole goal
in issue 7. A rewrite of issue 7 then changes `$INTENT` while every other key part stays the same.

`$HEAD` is the **only** name for the PR's head OID — never introduce a second variable for it. An
empty `$HEAD` counts as "no PR resolved", because it would turn the dedupe grep into a
match-anything prefix. No open PR is the normal case for a pre-PR branch, not an error:
`**Posted:** not posted — no open PR for this branch`.

**The reviewed tree IS the PR head** — `test "$(git rev-parse HEAD)" = "$HEAD"`. A mismatch means
we reviewed one tree and would post the verdict on another: the worst failure this skill can have,
and a silent one.
`**Posted:** not posted — local HEAD <a> ≠ PR #N head <b>; check out the PR head first`

**The PR is not a draft** — the scheduled loop skips drafts at inventory, and the single-PR
equivalent of "skip" is to write nothing. Applies to **both** flags, not just `--approve`.
`**Posted:** not posted — PR #N is a draft (the scheduled loop skips drafts)`

**The review actually ran** — Step 2 didn't abort and the diff was non-empty. Never post a verdict
derived from an empty or aborted diff. This is the one precondition the Step 0 hoist can't answer
early; check it at post time.

## Dedupe

Every body this skill posts ends with a marker line:

```
<!-- pr-flow:reviewing-prs head=<headRefOid> lenses=<N> intent=<INTENT> -->
```

`head` is the full 40-char OID; `lenses` is the registry row count from the coverage receipt;
`intent` is the `$INTENT` digest from *Preconditions*. `head` and `intent` are both part of the
key. A new commit moves `head`. An edit to the PR title, the PR body, or a closed issue moves
`intent`, and that edit alone can change the goal verdict from `undetermined` to `achieved` — so
a run at an unchanged head with a new `intent` is a new verdict, not a duplicate.

Refuse to run the check unless `$HEAD` is a non-empty 40-char OID. An empty one makes the pattern
a bare `head=` prefix matching **every** prior pr-flow comment, silently disabling this skill on
that PR forever:

```bash
[ ${#HEAD} -eq 40 ] || { echo "pr-flow: no head OID — skipping dedupe, not posting"; }
gh api "repos/$REPO/issues/$N/comments" --paginate --jq \
  '.[]|select(.user.login=="'"$ME"'")|.body' | grep -q "pr-flow:reviewing-prs head=$HEAD .*intent=$INTENT "
gh api "repos/$REPO/pulls/$N/reviews" --paginate --jq \
  '.[]|select(.user.login=="'"$ME"'")|.body' | grep -q "pr-flow:reviewing-prs head=$HEAD .*intent=$INTENT "
```

Run the comments check first and **skip the reviews call on a hit** — most posts are comments,
since approval needs both a clean report and `--approve`.

A hit in either store means these commits, with this stated intent, already got this review. **Do
not post again**; record `**Posted:** skipped — already reviewed at head <short-sha>`. New commits
produce a new head OID, and an edited title or body a new `intent` digest; either yields a fresh
post.

A marker written before this version carries no `intent=` field, so it never matches. The first
run after the upgrade posts once more on such a PR. One repeat post is the correct trade against
a PR that no edit can ever re-review.

This is load-bearing for any repeating caller: without it a cron re-posts the same review every
cycle on a stalled PR. The head OID is the key precisely because `updatedAt` is not — comment-only
activity moves `updatedAt` while the verdict is unchanged.

## Approve condition (`--approve` only)

**Approve when the report has no `### Must fix` entry and the `**Goal check:**` line reads
`achieved` or `partially achieved`.** Those are the two conditions. The flag was passed by a
caller that already decided approving is in scope, so an extra gate invented here would silently
override that decision.

**`### Should fix` never withholds approval.** It is a real defect that failed the Bar's
four-part must-fix test. The author decides whether to correct it in this PR.

**`### Notes` never withholds approval.** A notes-only report is approved, and the notes are
posted in the same body. That is the point of the three buckets: the author gets every real
remark, and a real-but-not-blocking remark does not cost a human round-trip. Do not re-read a
should-fix or a note here and promote it — Step 5 already made that call with the diff in front
of it.

An `UNVERIFIED` lens does **not** withhold approval. It describes how one lens ran, and the other
lenses still read the right diff.

**A Run caveat line does withhold approval — comment instead.** This is one of two gates that are
not about findings. The goal verdict below is the other. The caveat says the base may be wrong,
and a wrong base means the diff we reviewed may not be the PR's changes: lenses attack code the PR
never touched, and "no must-fix" then means nothing. Approving on that is the worst outcome this
skill has, because Step 7 strips the caveat, so the PR would carry a confident approval with no
trace of the doubt. Post the comment and record
`**Posted:** commented, approval withheld — review scope uncertain (stale base)`. Say nothing about
rebasing; the receipt is local, and the comment body carries only the diff findings.

**A goal verdict of `not achieved` or `undetermined` withholds approval — comment instead.**
`--approve` approves only when the goal verdict reads `achieved` or `partially achieved`. This
table gives the result for each verdict:

| `**Goal check:**` verdict | `--approve` result | Receipt |
|---|---|---|
| `achieved` or `partially achieved` | approves, when no must-fix entry | `approved with notes` |
| `not achieved` | comments | `commented, approval withheld — goal not achieved` |
| `undetermined` | comments | `commented, approval withheld — goal undetermined` |
| goal-only mode, any verdict | comments, always | `commented, approval withheld — no contract, goal-only review` |

The Goal check sentence names the missing source, so the author knows the fix is to write the
PR body. The verdict never adds an entry to `### Must fix`.

**We authored the PR** (`$AUTHOR == $ME`) → comment instead. Not a policy choice: GitHub rejects
self-approval outright, so detect it rather than eating an API error. Since the common interactive
use is "review my own branch", this is the case you will hit most. Name it in the receipt — a
silent degrade is worse than no flag. (The scheduled loop never reaches it; it only reviews other
people's PRs.)

Drafts are handled in Preconditions, not here.

## Post

**Build the body in a file, never inline it into `--body "…"`.** The report is markdown full of
backticks and `$`, and bash runs command substitution on both inside double quotes — inlining
would execute finding text as shell. Use a **quoted** heredoc and `--body-file`:

```bash
BODYFILE="$(mktemp)"
cat >"$BODYFILE.raw" <<'PRFLOW_EOF'
…the Step 6 report, verbatim, then the marker line…
PRFLOW_EOF
grep -v '^\*\*Run caveat:\*\*' "$BODYFILE.raw" >"$BODYFILE"    # strip the one local-only line
```

**That `grep -v` is the strip. Run it; do not do it by eye.** It removes the `**Run caveat:**`
line, and only that line. The caveat is written for the local reader: on the PR, "base may be
stale" reads as "rebase this branch", which is another skill's verdict and not ours. Everything
else goes in verbatim. Step 6 defines the label, this command consumes it, and a rename in one
place without the other posts the caveat — so keep the two spellings identical. It never removes
the `**Goal check:**` line. The `**Goal check:**` line goes to the pull request verbatim, in an
approval body and in a comment body alike.

**The approve conditions.** This list is canonical. Every other statement of the rule in this
plugin points here. Approve only when every condition below holds:

- the report has no `### Must fix` entry
- `--approve` applies
- we did not author the PR
- the run is not in goal-only mode
- the report carries no `**Run caveat:**` line
- the `**Goal check:**` line reads `achieved` or `partially achieved`

Carry the body as it stands: a clean report has only its coverage receipt, and a report with
only should-fix entries and notes carries them into the approval, where they belong.

```bash
gh pr review "$N" --repo "$REPO" --approve --body-file "$BODYFILE"
```

**Everything else** — any condition in that list fails: a must-fix finding, we authored it,
`--comment` alone, a `**Run caveat:**` line, the run is in goal-only mode, or a `**Goal check:**`
line that reads `not achieved` or `undetermined`:

```bash
gh pr comment "$N" --repo "$REPO" --body-file "$BODYFILE"
```

**Append the fix prompt only when there is a `### Must fix` entry.** `### Should fix` and
`### Notes` do not get one. A fix prompt asks for a round-trip, and the two lower buckets exist
to prevent that round-trip.

```
<details><summary>Fix prompt</summary>

Validate each must-fix finding above against the current diff. Fix the ones that hold and
explain the ones that do not. The should-fix entries and the notes are optional. Run this repo's
gates before you push.

</details>
```

**No duplicates at a *new* head:** if our previous comment raised the same findings and the new
commits didn't address them, reply briefly that the prior findings still stand instead of
reposting the whole report. Unaddressed **notes alone** need no reply at all — the author already
read them and chose. A fresh full comment is only for findings that changed or resolved.
(The unchanged-head, unchanged-intent case never gets here — dedupe already skipped it.)

**Every body this skill posts ends with the marker line**, and a short reply is a body. Write the
marker on the brief reply too. A body with no marker cannot dedupe, so the next cycle posts it
again.

**This rule suppresses the full report. It never suppresses the write itself. It never suppresses
an approval. It never overrides the goal gate.** A write always goes to the pull request at a new
head.

Approve at the new head when the approve conditions above hold — the one canonical list. Approve
even though every remaining entry is a repeat: that head has no must-fix finding and has not been
approved yet. The
author fixing the must-fix and leaving the lower entries is the exact case the three severities
exist for, and staying silent there strands a PR the posture was configured to approve. Put the
lower buckets in the approval body and record `approved with notes`.

Do not approve when the run is in goal-only mode, or when the `**Goal check:**` line reads
`not achieved` or `undetermined`. Post one comment at the new head instead. Its body is the brief
`prior findings still stand` reply, then the `**Goal check:**` line verbatim, then the marker
line. Do not put the full report in that body. Record the receipt
`**Posted:** commented, approval withheld — <reason>` and take `<reason>` from the Approve
condition section above. One write reached the pull request, so that receipt is true.

Never `gh pr review --request-changes`. If a write is denied, surface the denial in the receipt;
do not retry through another path.

## Receipt

Append exactly one `**Posted:**` line to the Step 6 report. Having reached the post step, it is
one of:

```
**Posted:** approved (head 1a2b3c4)
**Posted:** approved with notes — 2 note(s) (head 1a2b3c4)
**Posted:** approved with notes — 1 should-fix, 2 note(s) (head 1a2b3c4)
**Posted:** commented — 2 must-fix, 1 note (head 1a2b3c4)
**Posted:** commented — 2 must-fix, 1 should-fix, 1 note (head 1a2b3c4)
**Posted:** commented — 2 note(s), no must-fix (head 1a2b3c4)
**Posted:** commented — 1 should-fix, 2 note(s), no must-fix (head 1a2b3c4)
**Posted:** commented — prior findings still stand (head 1a2b3c4)
**Posted:** commented, approval withheld — we authored this PR (head 1a2b3c4)
**Posted:** commented, approval withheld — review scope uncertain (stale base) (head 1a2b3c4)
**Posted:** commented, approval withheld — goal not achieved (head 1a2b3c4)
**Posted:** commented, approval withheld — goal undetermined (head 1a2b3c4)
**Posted:** commented, approval withheld — no contract, goal-only review (head 1a2b3c4)
**Posted:** skipped — already reviewed at head 1a2b3c4
**Posted:** write denied — <the denial, verbatim> (head 1a2b3c4)
```

`approval withheld` names the *reason* approval did not happen, and a should-fix or a note is
never that reason. Under `--approve`, outside goal-only mode, on a PR we did not author, with no
Run caveat, a report with no `### Must fix` entry and with a `**Goal check:**` line that reads
`achieved` or `partially achieved` ends in `approved with notes`. Anything else there is a bug in
this run. `--comment` alone, a self-authored PR, a stale base, goal-only mode, and a goal verdict
of `not achieved` or `undetermined` each end in a comment for reasons that have nothing to do with
the should-fix entries or the notes.

When a precondition failed instead, the line is `**Posted:** not posted — <reason>` in that
precondition's own words. Quote it from above rather than restating it — two copies of one string
is how the two ends drift apart.
