---
name: reviewing-prs
description: Reviews the current branch's PR diff against this repo's own pr-flow contract — its bar for what counts as a finding, deterministic-gate exclusions, repo invariants, and a registry of lens skills — then emits a local advisory report, optionally posting it to the PR (--comment) or approving a PR that has no must-fix finding and a goal verdict of achieved or partially achieved (--approve). Every run always includes the plugin's built-in pr-flow:reviewing-goal-achievement lens. Use when asked to review a PR or the current branch, run the pr-flow review, or post or approve a review on a PR. Repo-agnostic, reading the contract written by /pr-flow:setup. Reviews the diff only, never the checks or the merge state. Advisory only, never blocking.
argument-hint: "[--pr <number>] [--comment | --approve]"
allowed-tools:
  - Bash(git diff:*)
  - Bash(git merge-base:*)
  - Bash(git log:*)
  - Bash(git rev-parse:*)
  - Bash(git symbolic-ref:*)
  - Bash(git hash-object:*)
  - Bash(gh auth status:*)
  - Bash(gh pr view:*)
  - Bash(gh pr comment:*)
  - Bash(gh pr review:*)
  - Bash(gh repo view:*)
  - Bash(gh api user:*)
  - Bash(gh api graphql:*)
  - Bash(gh api repos/*/issues/*/comments:*)
  - Bash(gh api repos/*/pulls/*/reviews:*)
  - Bash(grep:*)
  - Bash(jq:*)
  - Bash(cat:*)
  - Bash(test:*)
  - Bash(mktemp:*)
  - Read
  - Glob
  - Workflow
  - Skill
---

# reviewing-prs

Check a PR's changes against **this repo's own review contract** — the concerns, invariants, and
lenses the generic `code-review` plugin can't know about. You are **advisory only**: surface real
concerns loudly, never block a merge. Even `--approve` only ever *adds* an approval.

**Review the changes, and only the changes.** The diff is the whole subject. Never report — in
the session or on the PR — that a check failed, that CI is red, that the branch is behind its
base, that it needs a rebase, or that it has a conflict. Other skills own all of that. An author
who reads that here reads the rest of the review with less attention.

**Withhold approval for important problems only.** Step 5 sorts every finding into **must-fix**,
**should-fix**, and **note**, and only must-fix holds up approval. Step 5 runs the Bar's
four-part must-fix test itself on every proposed must-fix and every unlabelled finding, and it
never adopts a proposed must-fix without running that test.

Hardcode nothing repo-specific and no fixed lens list. Everything you enforce comes from the
contract that `/pr-flow:setup` generated for this repo.

**References** — read a file when its step says to, not upfront:
- [references/posting.md](references/posting.md) — Step 7, when a posting flag was passed.
- [../../references/github-access.md](../../references/github-access.md) — the shared `gh`/MCP probe.

## Step 0 — Parse arguments

Local and read-only by default. Two flags opt into writing, a third names the target. Parse them
out of the invocation text first, binding `--pr`'s value to `$PR`.

| Flag | Effect |
|------|--------|
| *(none)* | Step 6 report in-session. **No GitHub writes.** The default. |
| `--comment` | Also post the report to the PR as a comment. |
| `--approve` | Post **and** approve when the report has no must-fix finding — the scheduled loop's *Approve-when-clean* posture for one PR. Should-fix findings and notes do not withhold it. A must-fix finding, or we authored it → degrades to a comment. Implies `--comment`. `--approve` approves only when the goal verdict is `achieved` or `partially achieved`. A `not achieved` verdict and an `undetermined` verdict each degrade it to a comment. |
| `--pr <number>` | Names which PR the posting flags target, when the branch doesn't resolve to one — e.g. a loop reviewing someone else's PR from a temp worktree. Writes nothing on its own, and does **not** fetch that PR: the diff still comes from the working tree, so its head must already be checked out. Step 7 verifies that. |

- `--comment --approve` together is the normal scheduled invocation, not a conflict. Treat the
  pair as `--approve`.
- **With a posting flag, read [references/posting.md](references/posting.md) now** and run its
  *Preconditions* and *Dedupe* **before Step 1**. Local HEAD is already known, so both answer
  there — and a dedupe hit stops the run before the contract read, the diff, and the lens fan-out,
  which is this skill's whole cost. A dedupe hit is the **only** early stop: a failed precondition
  disables posting alone, so the review still runs and the report still ships with its
  `**Posted:** not posted — …` line.
- Echo the parsed flags in the report header so the reader knows what the run was allowed to do.

## Step 1 — Read the contract

Read `.claude/pr-flow/contract.md`. If it does not exist, run in **goal-only mode**. Say this
first, then continue:

> No pr-flow contract found at `.claude/pr-flow/contract.md`. Run `/pr-flow:setup` first to
> generate this repo's review contract and lens skills.

**Goal-only mode.** Follow this short list instead of the rest of Step 1:

- Run Step 2 (obtain the diff) as normal.
- Treat the missing contract as an empty registry. Step 3 already states what to do with an
  empty registry: it selects the built-in lens only, and it never stops the run.
- Emit the Step 6 report.
- There is no Bar, no gate list, and no invariant list in this mode. Apply the four-part
  MUST FIX test that Step 5 states in full, and the Voice rule that Step 6 states in full.
- The coverage receipt reads `triaged 0 registry rows → selected 0`, plus the built-in lens's
  row. The dedupe marker's `lenses` count (posting.md) is `0`.
- Write `goal-only mode — no contract` on the report's `**Mode:**` line. No reader may take a
  goal-only report as a full review.
- Never approve in this mode. `--approve` degrades to a comment. posting.md owns the receipt
  wording for that case.

With a contract present, hold all four sections for the whole session:

1. **The Bar** — a finding must be *real* (concretely true in this diff, with evidence) **and**
   *impactful if left unattended*. Report or drop, silently. Each reported finding is then
   **must-fix**, **should-fix**, or **note** by the Bar's four-part must-fix test; that label
   decides approval only. A current contract also carries the **ASD-STE100 voice rule**. Step 6
   states that rule in full, so this review reads the same whether the contract carries it or not.
2. **Deterministic gates** — the repo's own lint/typecheck/CI/secret-scan commands. Never surface
   what a listed gate already owns.
3. **Repo invariants** — the repo-specific rules the lenses defend.
4. **Lens registry** — the active lenses (Step 3).

An older contract may predate the three severities and say "no severity ladder". Do not re-read
that as "every finding withholds approval". It also predates the four-part must-fix test, and its
section 3 invariants carry no `[blocking]` or `[advisory]` marker. Step 5 states the four-part
test in full, so apply it anyway. When section 3 carries no marker, treat every invariant as
`[advisory]`: a broken invariant alone is then should-fix or note, not must-fix, unless it also
hits one of the other five damage classes. This skill never needs the contract to carry the newer policy —
it needs only the impact categories, which every contract has. Say once, under the report, that
`/pr-flow:setup` refreshes the Bar; do not repeat it on every run, and never put it on the PR.

## Step 2 — Obtain the diff

```bash
BASE=""
for c in refs/remotes/origin/HEAD refs/remotes/origin/main refs/remotes/origin/master \
         refs/heads/main refs/heads/master; do
  git rev-parse --verify --quiet "$c" >/dev/null 2>&1 && { BASE="$c"; break; }
done
[ -z "$BASE" ] && { echo "pr-flow: cannot resolve a base branch — aborting review"; exit 1; }
MB="$(git merge-base HEAD "$BASE")" || { echo "pr-flow: no merge-base with $BASE — aborting"; exit 1; }
DISP="${BASE#refs/*/}"          # refs/remotes/origin/main -> origin/main
WARN=""
case "$BASE" in refs/remotes/*) ;; *) WARN=" (WARNING: local branch, not remote-tracking — may be stale)" ;; esac
echo "pr-flow: base=$DISP merge-base=$MB$WARN"
git --no-pager diff --no-ext-diff "$MB"..HEAD || { echo "pr-flow: git diff failed — aborting"; exit 1; }
```

Three details there are load-bearing, because each one fails as an **empty diff that looks exactly
like a clean PR**:

- **Fully-qualified refs.** A bare `main` can resolve a *tag* named main; a bare `origin/main` can
  resolve a local branch literally named `origin/main` shadowing the remote-tracking ref.
- **No `sed` pipeline** to derive the base from `git symbolic-ref`. `sed` succeeds on empty stdin,
  so the pipeline always exits 0, any `|| fallback` never fires, and it degrades to
  `git diff ..HEAD` — which exits 0 with an empty diff.
- **`--no-ext-diff`.** A configured `diff.external` (difftastic, delta) otherwise makes `git diff`
  die with "external diff died". It does not disable `textconv`, so the `|| … aborting` guards
  remain the backstop.

**Aborted → stop the whole review** and report it; never continue to Step 3 with no diff. **Empty
diff → report "no changes against `<base>`" and stop** — never emit "PR looks ok" from one.

Carry the printed `base=… merge-base=…` values into the report's **Base** line. Also read the
branch name, `git log --oneline "$MB"..HEAD`, and the changed-file list.

If Step 2 printed the WARNING, put it on its own **Run caveat** line in the report, verbatim, and
nowhere else. It describes *how this review ran*: a stale base yields a wrong-but-non-empty diff
that no emptiness check catches, so the local reader must see it. It says nothing about the PR, so
Step 7 removes it before posting; posting.md holds that rule and the reason for it.

`**Run caveat:**` is the exact label Step 7 greps for, with `grep -v`, in posting.md's *Post*
section. It is the one local-only line that sits inside the report fence — everything else
local-only goes *under* the report, outside the fence, where no strip rule is needed. Do not rename
the label in one file alone.

**A Run caveat also withholds approval.** A base that may be wrong means the diff may not be the
PR's changes, so "no must-fix" proves nothing; posting.md degrades the run to a comment. This is
one of two things in the report that change what Step 7 does without being a finding. The Goal
check line is the other.

## Step 3 — Triage from the lens registry

The registry is a Markdown table, one row per lens (canonical grammar in
`${CLAUDE_PLUGIN_ROOT}/templates/the-bar.md` §4):

```
| name | when | skill path |
|------|------|------------|
| reviewing-<concern> | `<glob>`, `<change-type>` | `.claude/skills/reviewing-<concern>` |
```

Decide per row whether it applies to **this** diff by its `when` clause, which has two forms and
may mix them:

- **File globs** (`**/*.ts`, `auth/**`) — applies if any changed file matches.
- **Change-type keywords** (`touches-data-model`, `adds-migration`) — not path matches. Treat
  every one as **always-considered**: fan it out whenever the diff touches at least one file that
  isn't purely generated or mechanical (lock files, vendored dirs, generated clients, pure
  formatting), and let the lens self-filter — it returns clean if its change type is absent. When
  in doubt, fan out. A clean lens is cheap; silently dropping a concern that isn't expressible as
  a path pattern (a naming convention, a compliance rule that can touch any file) is not.

The registry drives the selection of repo lenses — never a hardcoded list. A docs-only PR may
select only docs/naming lenses; an infra PR skips UI lenses. The built-in lens below is the one
exception, and it is not a repo lens. Empty registry → select the built-in lens only, say so in
the receipt, and continue. An empty registry never stops the run.

Invoke each lens by the **bare basename of its registry skill path** (`reviewing-<concern>`).
Generated lenses are native repo skills, so they are **not** `pr-flow:`-namespaced: registry path
`.claude/skills/reviewing-naming` → invoke `reviewing-naming`.

### The built-in lens (always selected)

One lens is built into this plugin. Add `pr-flow:reviewing-goal-achievement` to the selected set
on every review. Add it when the registry lists it. Add it when the registry does not list it.
Add it when the registry is empty.

This lens is a plugin skill, so invoke it as `pr-flow:reviewing-goal-achievement`. Never invoke
it as a bare `reviewing-goal-achievement`. The bare-basename rule above covers generated repo
lenses only.

A contract written before this version may carry a registry row for a repo lens that also compares
the PR body with the diff — `reviewing-goal-achievement`, `reviewing-pr-intent`, or a like name.
Drop that row from the selected set and run the built-in lens alone. Two goal lenses give two
verdicts, and the report holds one `**Goal check:**` line. Count the dropped row as triaged, and
write `not selected (the built-in lens owns this concern)` on its receipt row.

The coverage receipt carries one row for this lens, marked `built-in`.

## Step 4 — Fan the lenses out

Author a Workflow in-context (never written to disk) that gives each selected lens its own
subagent, invoked by the Skill tool, run in parallel. The one-level nesting limit doesn't bite:
skills consume no nesting level, so the fan-out is flat.

**Run every lens subagent on Sonnet.** Set `model: 'sonnet'` on each lens `agent()` call — always,
whatever model this session runs. A lens reads one diff against one written rule, so Sonnet does
that work, and the fan-out is the whole cost of this skill. Do not let a lens inherit the session
model.

```js
await parallel(SELECTED.map(lens => () =>
  agent(lensPrompt(lens), {
    label: lens.name,
    model: 'sonnet',
    schema: lens.builtIn ? GOAL_SCHEMA : FINDINGS_SCHEMA,
  })))
```

`GOAL_SCHEMA` carries the verdict word, the one-sentence rationale, **and** a `findings` array in
the same shape `FINDINGS_SCHEMA` uses — label, file, text. `FINDINGS_SCHEMA` carries only the
finding list. Give the built-in lens `GOAL_SCHEMA`. Give every other lens `FINDINGS_SCHEMA`. Never
give the built-in lens a schema with no `findings` field: its own Findings section proposes
should-fix and note entries, and a schema with nowhere to put them drops them silently.

**Hand the built-in lens the Step 2 diff, the PR title, body, commits, and closed issues.** The
built-in lens rides in `SELECTED` like every other lens, and it takes the same `model: 'sonnet'`
pin. Its dispatch prompt carries the same diff text every other lens gets — the one Step 2
already obtained, with its merge-base and stale-ref guards. **Never let the built-in lens compute
its own diff.** It is exempt from Step 4's adversarial-attack framing below (it does not attack
an invariant), but it is not exempt from the diff handoff every lens gets: that instruction is
general, not scoped to attack lenses. With a posting flag, posting.md already fetched the other
four before Step 1 — pass `$TITLE`, `$BODY`, `$COMMITS`, and `$ISSUES` from it, and fetch nothing
again.

Fetch the four values yourself when no posting flag was passed, **and** when a posting flag was
passed but posting.md's fetch returned an empty `$PR_JSON`. **Run this call only when `gh` is
authenticated and the branch resolves to an open PR.** One call gets the first three:
`gh pr view "${PR:-$(git rev-parse --abbrev-ref HEAD)}" --json title,body,commits`. It reads the
`--pr` target when one was passed, and the current branch otherwise.

**The closed issues need a second call, and it is not optional.** A PR body that only says
`Fixes #7` states no goal by itself; issue 7 holds the whole goal. Without this call the lens
compares the diff against a bare issue link, and it can neither pass nor fail the PR on evidence.
`gh pr view --json` has no field for these issues, in any version, so run the `gh api graphql`
query in posting.md *Preconditions* and pass its output as `$ISSUES`. Keep its two failure
answers apart: `[]` means the PR closes no issue, and an empty string means the call failed.

**Bind `$REPO` and `$N` before you run that query.** The query reads both, and posting.md binds
them in its own *Preconditions* block, which does not run on this path. Bind them here:

```bash
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
N="$(gh pr view "${PR:-$(git rev-parse --abbrev-ref HEAD)}" --repo "$REPO" --json number -q .number)"
```

An unbound `$REPO` or an unbound `$N` makes the query fail, and the lens then reads the empty
`$ISSUES` as a failed call. A PR whose body says only `Fixes #7` then gets `undetermined` on
every no-flag run.

The lens never calls `gh` itself. When neither path yields a title and a body, tell the lens
which path failed: an absent PR, or a `gh` call that failed. The lens then uses the other
sources, and it may return `undetermined` — and its one sentence then names that failure, so the
reader does not read a `gh` error as an empty PR body.

**The built-in lens returns a verdict, and it may also return findings.** Give its `agent()` call
a schema that carries the one verdict word and the one-sentence rationale that Step 6 of the lens
returns, **plus** a `findings` array. Do not force it through the finding-only `FINDINGS_SCHEMA`
the attack lenses use; that schema has no field for the verdict. Step 5 and Step 6 read the built-in
lens's `findings` array exactly like any other lens's — same filter pass, same buckets.

The pin covers the Step 4 fan-out and the Step 5 single-lens re-dispatch. It covers nothing else:
Step 5's filter pass and Step 6's report stay inline, in this session, on this session's model.

Frame every subagent **adversarially — refutation, not "read it and find issues."** Each gets one
lens and is told to attack: break the invariant that lens defends, disprove a claim, construct a
concrete failing case. A "clean" verdict with no shown break-attempt is itself a failure, so
require an `ATTEMPTED-BUT-HELD` list where **each entry names the exact target attacked**
(function, route, schema, symbol) **and the input that should have broken it**. If the concern is
genuinely absent, the lens says so explicitly (`concern not present: no <X> in this diff`) instead
of listing attacks. "Looked for issues, found none" is a failed dispatch, not a clean verdict.

**The built-in lens is the one exception to this paragraph.** `pr-flow:reviewing-goal-achievement`
compares a stated goal with a diff; it does not attack an invariant, and it carries no
`ATTEMPTED-BUT-HELD` list. Its evidence is the verdict word and the one-sentence rationale that
Step 6 already requires from it.

**Don't prime the reviewer.** Hand over the diff and let it read — no summary of the change, no
mention of prior "approved" verdicts, no note that gates are green. A primed reviewer ratifies.
Scope it to the *whole* PR, not the slice just written, and require a failure scenario per finding.

**Put these rules in the dispatch prompt itself.** A lens file is a `flag:` / `do not flag:`
list and nothing else; it carries no policy text, so the dispatch prompt is the only place a lens
subagent reads them:

- **Read the Bar first.** Read section 1 of `.claude/pr-flow/contract.md` and drop any finding
  that does not clear both of its tests. Apply its note cap to every SHOULD-FIX and NOTE.
- **Report the diff only.** Say nothing about a failed check, the CI result, the merge state, or
  the age of the branch. A CI or workflow file the diff changes is part of the diff.

- **Report important findings only.** Report what breaks the rule. Report nothing else. Silence is
  the correct answer for most diffs.
- **Propose one of three labels: `MUST-FIX`, `SHOULD-FIX`, or `NOTE`.** For a `MUST-FIX`, write
  part 1 of the Bar's must-fix test in full: "After this merge, <who or what> gets <the wrong
  result> at <file>:<symbol>." Step 5 re-runs the full must-fix test on every proposal, so an
  over-strict proposal gains the lens nothing.
- **Write every finding in ASD-STE100**, per the Bar's Voice rule (Step 6 restates it).

The adversarial framing above and these rules do not fight. The `ATTEMPTED-BUT-HELD` list is how a
lens proves it worked. It is **not** a quota to fill with small findings. A lens that reports
nothing and names what it attacked did its job.

## Step 5 — Filter and verify

One inline pass over everything the subagents returned:

- **Clears the Bar?** Real — concretely present in this diff, with evidence — **and** impactful.
  Drop what fails either test.
- **Gate-owned?** Drop anything a listed deterministic gate already covers. Never re-flag it.
- **In the diff?** Drop anything about the *run*: a check that failed, a red CI result, the merge
  state, the base being behind, a conflict. A lens that returns one of those returned an
  out-of-scope finding, not a finding.
  **A CI file the diff edits is in scope, and this is not the exception to that rule — it is the
  rule.** The subject is the change, so a diff that deletes a test step, weakens a gate, or drops a
  required job is reviewable like any other change, and it gets the same four-part must-fix test
  as any other change. Damage class 5 usually carries it, but run the test. What you never report
  is the *state* of a run you did not read.
  **The goal verdict is not a finding. Do not drop it under this rule.** The built-in lens reads
  the PR title and the PR body for the verdict only, and it reports no opinion about them.
- **Duplicated?** Two lenses on one file/line → keep the clearest, drop the rest.
- **Important?** The strict pass, and the one that does the most work. Name the damage in one
  sentence, or drop the finding. Drop preferences, restatements of the diff, and anything the author
  sees without you. Five small remarks from one lens are noise: keep the one that matters. Dropping
  everything is a correct outcome.
- **Must-fix, should-fix, or note?** A lens only **proposes** a label. Run the four-part test
  yourself on every proposed `MUST-FIX` and on every unlabelled finding. Do not adopt a proposal
  without running the test, and do not ask the lens again.

  The four-part test, in full: write must-fix only when all four parts are true.

  1. You can complete this sentence from the diff: "After this merge, <who or what> gets <the
     wrong result> at <file>:<symbol>."
  2. You can name a trigger that reaches it today — a caller, a command, a user step, or a
     released artifact. A trigger that needs code nobody has written does not count.
  3. You can name the line in this diff that causes it. Evidence outside the diff does not count.
  4. The failure is one of these six: the software gives a wrong result or it stops; private data
     escapes or a security control breaks; data is destroyed or made unrecoverable; a published
     interface breaks for a caller you can name; a check stops running, or a check passes when it must fail; an invariant that the contract's section 3 marks `[blocking]` breaks.

  If any part fails, demote the proposal. Write should-fix when you can still name a real defect.
  Write note when you cannot name a defect at all. None of these reach must-fix on their own:
  wording, tone, grammar, and voice; a missing test for code that already works; naming, layout,
  duplication, and dead code; an input that no current caller sends; a risk that needs a future
  change to become real; prose that no agent and no user follows to a wrong action.

  The size of the fix is not part of the test. When you are not sure between two levels, use the
  lower one. Do not promote a finding to make the author act on it; a wrong must-fix costs a human
  round-trip. Most PRs get zero must-fix; a report with more than two is a signal to read it
  again.

  A lens writes `MUST-FIX`, `SHOULD-FIX`, or `NOTE`. These map straight onto the Step 6 buckets:
  `### Must fix`, `### Should fix`, and `### Notes`. A demotion is not a new finding — keep the
  lens's text, change only the label. Anything the bullets above already dropped stays dropped.
- **Is each should-fix and each note two sentences or fewer?** Cut it here, before Step 6 writes it.
- **Clean verdicts only — is the `ATTEMPTED-BUT-HELD` list specific?** It must name targets and
  inputs from this diff, or say "concern not present". If it's generic, re-dispatch that one lens
  **once** with the Step 4 framing, and with the same `model: 'sonnet'` pin. Still generic → mark
  it `UNVERIFIED`; never fabricate a
  digest. A lens that flagged something already showed its work; this check exists because a false
  "clean" is the ratification risk.
  **This bullet does not apply to `pr-flow:reviewing-goal-achievement`.** It never carries an
  `ATTEMPTED-BUT-HELD` list, it is never re-dispatched for lacking one, and it is never marked
  `UNVERIFIED` for lacking one. Its evidence is the Goal verdict bullet below.
- **Goal verdict?** The built-in lens returns exactly one word: `achieved`, `partially achieved`,
  `not achieved`, or `undetermined`. Copy the word and its sentence into the Step 6
  `**Goal check:**` line unchanged. An unreadable intent gives the verdict `undetermined`. Never
  write `achieved` when the lens did not read the intent. A built-in lens that returns no
  verdict — it errored, timed out, or gave no dispatch result — gives `undetermined`. Write the
  dispatch failure in the Goal check sentence, and write `undetermined (no lens result)` in the
  verdict slot of the Step 6 receipt row. A `not achieved` verdict adds no entry to
  `### Must fix`. A goal mismatch is not one of the six damage classes. Under `--approve`, a
  `not achieved` verdict and an `undetermined` verdict each withhold the approval; posting.md owns
  that gate.

## Step 6 — Report

Write the whole report in **ASD-STE100 Simplified Technical English**. These are the Bar's five
Voice bullets, repeated here word for word so this step works against a contract that predates
them. Keep the two copies identical:

- Write one idea in one sentence. Use a maximum of 20 words.
- Use the active voice and the present tense.
- Use one word for one meaning. Do not change the word for the same thing.
- Do not use idioms, metaphors, humor, or jargon.
- Name the file, the symbol, and the damage. Do not hedge.

Paths, identifiers, and quoted source keep their exact spelling.

**This step owns the voice, and it is the last step that can.** Step 4's dispatch prompt tells
every lens subagent to write its findings in this voice, so most text arrives already correct;
pass that through unchanged. Rewrite any finding that does not obey — keep the file, the symbol,
and the claim exactly, and change only the wording. Step 7 posts what you write here verbatim, so
nothing downstream repairs a sentence you leave.

The fence below is the **normative** format — match it exactly. Every report opens with **Base**
(`$DISP` plus the first 7 chars of `$MB` from Step 2, no extra git command), **Mode**,
**Coverage receipt**, and **Goal check**. **Run caveat** appears only when Step 2 printed the
WARNING. Then one row per registry lens, plus the built-in lens's row — which carries its
verdict word, never a `held:` digest, a `concern not present` note, or `UNVERIFIED`:

```
## PR Review

**Base:** `<base>` (merge-base `<short-sha>`)
**Mode:** <`local report only` when no flag was passed, else the flags verbatim, e.g. `--approve --pr 42`; in goal-only mode, prefix it with `goal-only mode — no contract`>
**Run caveat:** <the Step 2 WARNING, verbatim — omit this whole line when there was none>
**Coverage receipt:** triaged N registry rows → selected M.
- reviewing-<concern-1> — selected (matched `<glob or change-type>`) → clean; held: <one clause
  naming the target you attacked and the input that should have broken it>
- reviewing-<concern-2> — selected (matched `<glob or change-type>`) → clean; concern not present
  (<the change type this lens defends is absent from the diff>)
- reviewing-<concern-3> — selected (matched `<glob or change-type>`) → 1 must-fix, 1 should-fix, 1 note
- reviewing-<concern-4> — not selected (no changed file matched its globs / diff is purely generated)
- pr-flow:reviewing-goal-achievement — selected (built-in) → verdict `partially achieved`

**Goal check:** <achieved | partially achieved | not achieved | undetermined> — <one sentence, 20 words maximum, naming the source of the intent>
```

Nothing survived the filter → close with `---` and `PR looks ok as is.`

Otherwise `---`, then the buckets that have entries, in this order: `### Must fix`,
`### Should fix`, `### Notes`. Write a heading only for a bucket that has at least one entry —
never an empty `### Must fix` and never an empty `### Should fix`. One entry per finding:

```
### Must fix

**[lens]** `path/to/file.ext` — one-line why-it-matters.

### Should fix

**[lens]** `path/to/file.ext` — what is wrong. Why it matters.

### Notes

**[lens]** `path/to/file.ext` — what is wrong. Why it matters.
```

The should-fix and note entries above show the cap Step 5 applied: two short sentences, no code
block, no patch.

`### Should fix` and `### Notes` are the non-blocking buckets. Say so once, directly under each
heading, so no reader treats either as a change request:

```
### Should fix

These do not need a change before the merge. The author decides.

### Notes

These do not need a change before the merge. Correct them here or later.
```

Write that one sentence under each heading, and no other. Both are true in every mode. Never
write "these do not hold up the approval" under either: under `--comment` this run posts no
approval, so that sentence promises the author an approval that is not coming.

Two conditions decide whether the report *content* allows an approval. The report has no
`### Must fix` bucket. Its `**Goal check:**` line reads `achieved` or `partially achieved`. A
report that meets both conditions is approvable, whatever else it carries. Expect this outcome on
a good PR. It is not a degraded clean run. A bad `**Goal check:**` line makes a report
unapprovable, even with no must-fix bucket.

The content is not the whole gate. posting.md holds the canonical approve conditions, and they
also cover the flag, the author, and the Run caveat. Step 7 decides the approval, not this step.

**Base**, **Coverage receipt**, and **Goal check** are mandatory in every report. A silent no-op
has to be visible — that is the trust mechanism for an advisory, non-deterministic tool.
Selected zero registry lenses (a lock-file-only PR, an empty registry)? Say so in the receipt;
the built-in lens still ran. The Goal check line appears in a clean report and in a report that
carries no finding.

With no posting flag this run writes nothing to GitHub. The Goal check line stays in the
session report.

Each clean lens carries a one-clause `held:` digest **or** a `concern not present` note — the
condensation of the list you verified in Step 5, and the only evidence the lens did adversarial
work. A flagged lens needs neither; its finding is the evidence. If Step 5 got no diff-specific
attempt even after re-dispatch, write `clean; UNVERIFIED (no diff-specific attempt)` so the reader
sees the gap instead of a fabrication.

**The built-in lens is the one exception.** Its receipt row carries its verdict word, not a
`held:` digest and not a `concern not present` note, and it is never marked `UNVERIFIED`. The
row format is `pr-flow:reviewing-goal-achievement — selected (built-in) → verdict <word>`, exactly
as the fence above shows.

## Step 7 — Post to GitHub

Only when `--comment` or `--approve` was passed. Follow
[references/posting.md](references/posting.md) — preconditions, dedupe, the approve condition, the
post itself, and the `**Posted:**` receipt line.

## Reread the stale PR body

**In-session only.** Say what you find in the session, under the report, never inside it and never
on the PR. The PR body is not the diff, so a remark about it is not a finding: it goes in no
bucket, and Step 7 never posts it. The `**Goal check:**` line is the one exception, and it is not
a remark. The built-in lens reads the PR body for the verdict. Step 6 writes the verdict, Step 7
posts it, and the verdict can withhold an approval.

**Skip entirely if no PR body is reachable** — not a failure, and it must never block the report.
When Step 4 or Step 7 already fetched the body, reuse it; otherwise fetch one with
`gh pr view --json body -q .body`, only if `gh` is authenticated and the branch has an open PR.

A PR older than about a day has a body written when the work was still a plan: scope moved to
issues, deferred items shipped anyway, the base merged, and nothing re-checked the prose.
Reconcile it against `git log` and the current tree. The section most likely to be false is
**"what this does NOT do"** — its whole job is to describe absent work, so it goes false silently
the moment that work lands.

## What this skill does not cover

- Check status, CI pass/fail, merge conflicts, a branch behind its base, a needed rebase. Never
  read them, and never report them — not in the session, and above all not on the PR.
  `getting-prs-green` owns the checks; `getting-prs-merged` owns the merge state. `--approve` says
  "this diff has no must-fix finding, and its goal verdict is `achieved` or `partially achieved`,"
  not "this PR is mergeable." Branch protection still owns the gate. In goal-only mode `--approve`
  never approves — it always degrades to a comment.
- Requesting changes, blocking, or merging — `getting-prs-approved` answers review feedback,
  `getting-prs-merged` merges.
- Generic code quality, bug detection, CLAUDE.md compliance — that's `/code-review`.
- Anything a contract-listed deterministic gate owns, or anything outside the diff.
