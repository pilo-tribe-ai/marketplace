# Prompt Fit

Measures any prompt against the August 2026 prompt engineering principles, then
shrinks it.

The field inverted over the year to August 2026. The big, prescriptive prompts
that kept older models reliable now hurt current models. Anthropic deleted over
80% of the Claude Code system prompt for its Claude-5-generation models and
lost nothing on its coding evaluations. The default flipped with it: when a
prompt misbehaves, delete instructions before you add any.

This plugin makes that measurable. It counts instructions rather than tokens,
because that is the number that predicts whether a prompt holds.

## The number

Rule following collapses geometrically. At a per-rule compliance of 0.98, the
chance that all of 40 rules hold at once is about 45%. Reference material that
the model consults degrades gently with size. So a 15k-token prompt that is
mostly reference is healthier than a 3k-token prompt that is 60 rules.

The linter counts the two separately and reports a band:

| Instructions | All-rules estimate | Band |
| --- | --- | --- |
| 0 to 11 | 80% or above | healthy |
| 12 to 25 | 60% to 79% | watch |
| 26 and above | below 60% | at-risk |

## Commands

| Command | Does |
| --- | --- |
| `/prompt-fit:review <target>` | Measures a target and reports findings that cite a rule. Edits nothing. |
| `/prompt-fit:revise <target>` | Deletes, rewrites, moves, and proves a count went down. |
| `/prompt-fit:new <description>` | Drafts a new prompt in the 2026 shape. |

A target is a file, a skill folder, a plugin folder, a project folder, or
pasted text. The plugin works on its own kind and on any other: a system
prompt, a `CLAUDE.md`, a slash command, an agent, or a whole plugin tree.

```
/prompt-fit:review plugins/relay/skills/driving-to-done/SKILL.md
/prompt-fit:review .
/prompt-fit:revise draft.md --only L3,L4,L5
```

## What it checks

Ten checks run in code, so the model does not have to judge them:

| Rule | Check | Catches |
| --- | --- | --- |
| L1 | emphasis | `CRITICAL:`, `You MUST`, shouting |
| P3 | hedge | `only high-severity issues` and other bars that set no bar |
| P7 | bare-prohibition | a `never` with no `because` |
| L3 | persona | `You are a world-class engineer` |
| L4 | pressure | politeness, tips, threats |
| L5 | anti-laziness | scaffolding written against an older model |
| L7 | prescribed-reasoning | `think step by step` |
| P8 | hard-rule-in-prose | guardrails that belong in a classifier |
| P6 | mixed-format | markdown headings and tags mixed in one file |
| P5 | instructions-before-reference | task instructions above a long corpus |

P2 is reported on every file as the instruction count and the band. Eight more
rules need a reader, and the review skill applies them: P1, P4, P9, L2, L6, L8,
U1 and U2.

All nineteen live in [`reference/principles.md`](reference/principles.md), with
a confidence label on each: `measured`, `vendor`, or `directional`.

## Scripts

The three scripts run on their own, without an agent.

```bash
python3 scripts/resolve_target.py plugins/relay          # what is in scope
python3 scripts/prompt_lint.py path/to/SKILL.md          # counts and findings
python3 scripts/prompt_lint.py draft.md --json           # for a pipeline
python3 scripts/compare_prompts.py before.md after.md    # did the revision move
```

Exit codes: `0` clean, `1` findings, `2` the run could not read what it was
given. `compare_prompts.py` exits `1` when a revision moved no count down, so a
revision loop cannot report success on a rewrite that measures the same.

## What it does not do

It measures the shape of a prompt, and not what the prompt does. Only your own
evaluations measure that. Treat every model swap as a breaking change, and run
those evaluations again.

## Staleness

The principles are dated August 2026 and are meant to be refreshed by running
the research again, roughly each season, or after any major model generation.
When the date is more than about six months old, treat the specific numbers as
stale, and the shape as the part that lasts.

## Tests

```bash
python3 -m pytest plugins/prompt-fit/tests -q
```

The suite includes a dogfood file: the plugin's own skills and commands must
raise zero findings, and its corpus must stay mostly reference material.
