---
description: "Measure a prompt, skill, command, agent or plugin against the August 2026 prompt engineering principles. Reports findings that cite a rule identifier, and edits nothing."
argument-hint: "<file|skill-dir|plugin-dir|project-dir>"
allowed-tools: Read, Bash, Glob, Grep, Skill
---

# /prompt-fit:review

Measure one target, and report what it costs itself.

## Usage

```
/prompt-fit:review plugins/relay/skills/driving-to-done/SKILL.md
/prompt-fit:review plugins/relay              a whole plugin
/prompt-fit:review .                          this project's CLAUDE.md and .claude tree
/prompt-fit:review draft.md                   a plain system prompt
```

With no argument, the target is the current folder.

## What it reports

A table per file, and a headline over the target:

```
4 files, 61 instructions, at-risk (30%), 12 findings, 24 instructions removable

  line  rule  cost     instructions  finding
    31  L5    delete              3  anti-laziness scaffolding: "do not stop until"
    52  P1    rewrite             6  a 6-step method where an outcome would do
    14  P3    rewrite             0  "only high-severity issues" sets no bar
```

The rule identifiers are entries in `${CLAUDE_PLUGIN_ROOT}/reference/principles.md`.

## What it does not do

It edits nothing. Use `/prompt-fit:revise` to apply the findings.

It measures the shape of a prompt, and not what the prompt does. Only your own
evaluations measure that.

## Process

Invoke `Skill('prompt-fit:reviewing-prompts')` with the target.
