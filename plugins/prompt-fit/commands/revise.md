---
description: "Apply the August 2026 prompt engineering principles to a prompt, skill, command, agent or plugin. Deletes before rewriting, and proves the instruction count or the finding count went down."
argument-hint: "<file|skill-dir|plugin-dir> [--only <rules>] [--dry-run]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion, Skill
---

# /prompt-fit:revise

Shrink a prompt, and measure what the change did.

## Usage

```
/prompt-fit:revise draft.md                     apply every finding
/prompt-fit:revise draft.md --only L3,L4,L5     apply the deletions alone
/prompt-fit:revise draft.md --dry-run           show the edit, write nothing
/prompt-fit:revise plugins/relay/skills/driving-to-done
```

## Where the edit lands

| Git state of the file | Written to |
| --- | --- |
| tracked, and clean | the file, in place. Git holds the undo. |
| tracked and dirty, untracked, or outside git | `<name>.revised.md`, beside it |

## What it reports

```
instructions        34 → 11   (-23)
reference lines    120 → 260  (+140)
all-rules estimate 50% → 80%  (+30pp)
findings             9 → 1    (-8)
```

Then the deletions, one line each, with the behaviour each one protected. Then
what was kept, and why. Then the model the prompt is now tuned against.

When no count moves down, the report says "no measurable change" rather than
reporting success.

## What it does not do

It does not run your evaluations. The numbers above measure shape, and not
behaviour. Run your evaluations before you ship the revision, because a prompt
that measures 80% and answers wrong is worse than the one it replaced.

## Process

Invoke `Skill('prompt-fit:revising-prompts')` with the target and the flags.
