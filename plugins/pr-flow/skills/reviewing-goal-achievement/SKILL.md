---
name: reviewing-goal-achievement
description: Compares a PR's stated goal with its diff and returns one verdict — achieved, partially achieved, not achieved, or undetermined. Reads the goal from the PR title and body, from every issue the PR closes with a fixes/closes/resolves keyword, from any plan or spec the diff changes, and from the commit bodies. Built into pr-flow. Runs on every review, with a contract or without one. /pr-flow:setup never generates this lens.
allowed-tools:
  - Read
  - Glob
---

# reviewing-goal-achievement

This lens is part of the pr-flow plugin. `reviewing-prs` selects it on every review. It runs
with a repo contract, and it runs without one.

## Step 1 — The bar for this lens

Read the **Bar** section of `.claude/pr-flow/contract.md` and apply it to every finding. Read
`${CLAUDE_PLUGIN_ROOT}/templates/the-bar.md` §1 when that contract file does not exist. The
plugin ships that template, so this lens always has a bar.

Never restate the bar here. The four-part MUST FIX test, the six damage classes, the note cap,
and the ASD-STE100 voice rules all come from the source you just read. One copy keeps every
lens on the same rule.

A finding must be real — concretely true in this diff, with evidence — and impactful if left
unattended. Report or drop, silently.

## Step 2 — Read the stated intent

Read the intent from four sources, in this order.

**Source 1 — the PR title and the PR body.** The orchestrator hands you both. Use them. When
the orchestrator hands you neither, source 1 states no intent; go to source 2. Never fetch the
title or the body yourself.

**Source 2 — every issue this PR closes.** The orchestrator hands you the list as `$ISSUES`,
with the number, title, body, and repository of each issue. GitHub builds that list from the
closing keywords — `fixes`, `closes`, `resolves`, and their variants — and from the sidebar
link. Read the title and the body of every issue in the list. Never fetch an issue yourself.
Never build this list yourself from the body text, and never add an issue to it: GitHub already
resolved the references, and your own parse would give a different list.

Step 3 and Step 5 do look at the body for the *shape* of a closing reference. That is a test of
the body, not a way to resolve an issue. It never adds an entry to `$ISSUES`.

A closed issue states the goal with more authority than the PR body does. The PR claims to
close that issue, so the issue's stated problem and its acceptance criteria are goal items you
must check one by one.

`$ISSUES` has two empty answers, and they differ. `[]` means this PR closes no issue: source 2
states no intent, and you go to source 3. An empty `$ISSUES` means the call failed: you do not
know whether this PR closes an issue. Read Step 5 for the second case.

A `#7` that appears in the PR body without a closing keyword is a mention, not a goal. GitHub
leaves it out of the list, and so do you.

**Source 3 — every plan, spec, design document, ADR, or task list this diff adds or edits.** The
orchestrator hands you the diff — the same text every lens reads, already resolved against the
right base. Never run `git diff` yourself; you hold no `git` tool for it. Take the changed-file
list from the diff you were handed. Keep the entries that match one of these patterns:
`*.md`, `docs/**`, `specs/**`, `plans/**`, `**/PLAN.md`, `**/SPEC.md`, `**/DESIGN.md`,
`**/TASKS.md`, `docs/adr/**`, `docs/decisions/**`. Read the post-merge content of the entries
you kept. Also keep a changed file that holds a Markdown checkbox list.

The patterns filter the diff's changed-file list. Never search the working tree with them. A
file the diff does not touch states no intent for this PR.

**Source 4 — the commit subjects and bodies.** The orchestrator hands you the commits. Source 4
states intent only when a commit body names a goal. A bare conventional-commit subject states
no goal. When the orchestrator hands you no commits, skip source 4; never fetch them yourself.

**Tie rules.** Two sources conflict when they name different goals, not when one says more than
the other. Apply these rules in order:

- A closed issue outranks the PR body. The PR asserts that it closes that issue, so the issue
  states the requirement and the body only describes the attempt.
- A plan or spec that this diff changes outranks the PR body — a PR body goes stale.
- A closed issue and a plan that this diff changes do not compete. The issue states the problem
  and the plan states the agreed approach, so check the diff against both.

When you are not sure between two verdicts, write `partially achieved`.

## Step 3 — The empty-or-template-only test

The PR body is template-only when every line of it is one of these: a heading, an HTML
comment, a horizontal rule, an unchecked checkbox, or text that also appears in
`.github/PULL_REQUEST_TEMPLATE*`.

Find the template file with Glob, not with Read. GitHub accepts more than one name and more than
one case — `.github/pull_request_template.md`, `.github/PULL_REQUEST_TEMPLATE.md`, and
`.github/PULL_REQUEST_TEMPLATE/*.md` all work. Glob these three patterns, plus the same three at
the repository root and under `docs/`. No match means this repo has no template: the body is then
template-only only when every line is furniture.

An empty body carries no stated intent. A template-only body carries no stated intent.

**A link-only body carries no stated intent of its own.** The body is link-only when every line
that is not template furniture is a closing reference, such as `Fixes #7` or
`Closes owner/repo#12`. Such a body names the goal but does not state it. Never judge the diff
against the words `Fixes #7`; every diff matches them. The goal is in issue 7, and source 2
carries it. A link-only body with a readable source 2 is a good body, not a defect.

When source 1 carries no stated intent, and source 2 lists no issue, and source 3 finds no plan,
spec, design document, or task list in the diff, and source 4 names no goal, the verdict is
`undetermined`.

## Step 4 — Choose one verdict

Choose exactly one verdict from this closed list of four.

- `achieved` — the diff implements every goal item the intent states.
- `partially achieved` — the diff implements at least one goal item, it leaves at least one
  goal item unimplemented, and it contradicts no goal item.
- `not achieved` — the diff implements no goal item, or the diff does the opposite of a goal
  item, or the diff does work the intent states it does not do.
- `undetermined` — you cannot read the intent (Step 3), or this PR closes an issue you could not
  read (Step 5), or you cannot read the diff or a named document.

## Step 5 — Never write achieved without the intent

An unreadable intent gives the verdict `undetermined`. Never write `achieved` when you did not
read the intent.

No title and no body from the orchestrator gives `undetermined`, when source 2, source 3, and
source 4 also give no intent. An unreadable file gives `undetermined`. A missing diff gives
`undetermined`. Name the failure in the verdict sentence.

**A claimed issue you could not read gives `undetermined`.** The orchestrator hands you an empty
`$ISSUES` when its call failed. Look at the PR body. When the body holds a closing reference,
this PR states its goal in an issue that you did not read, so you cannot judge the diff against
it: write `undetermined` and name the unread issue. When the body holds no closing reference,
judge the diff on the sources you did read, and name the failed issue call in your sentence.

An issue in the list with an empty body still states intent through its title. Use the title.

## Step 6 — Return the verdict

Return exactly one verdict word from the four in Step 4, plus one sentence of 20 words maximum
that names the source of the intent, or names the read failure.

The orchestrator copies both, unchanged, into the report's `**Goal check:**` line.

## Findings

The verdict alone is never a must-fix. A mismatch between a PR body and a diff is not one of
the six damage classes.

Propose should-fix or note when you can name a concrete defect — for example, a document the
diff edits that now states behavior the diff does not implement. Propose must-fix only when all
four parts of the Step 1 test pass on that finding's own evidence. Never promote a finding
because the verdict is `not achieved`. Obey the two-sentence note cap.

## What this lens does not do

It reports nothing about a check, the CI result, the merge state, or the age of the branch. It
never approves. It adds no entry to `### Must fix` because of the verdict alone.

It never returns an `ATTEMPTED-BUT-HELD` list. This lens compares a stated goal with a diff; it
does not attack an invariant. Its evidence is the verdict word and the one-sentence rationale
from Step 6, not a list of attacked targets.
