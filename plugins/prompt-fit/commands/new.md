---
description: "Draft a new system prompt, skill, command or agent in the 2026 shape — few outcome-shaped instructions, separate reference material, hard rules left to code."
argument-hint: "<what the prompt is for> [--out <path>]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion, Skill
---

# /prompt-fit:new

Draft a prompt that starts small.

## Usage

```
/prompt-fit:new a reviewer that rules on API changelog entries
/prompt-fit:new a skill that files support tickets --out .claude/skills/filing-tickets/SKILL.md
```

## What it asks for

Four answers, before any drafting:

1. The outcome, stated so that it can be measured: a length, a count, a format,
   or an explicit test.
2. The model, and whether it is pinned. A small or unpinned model keeps
   scaffolding that a frontier model does without.
3. The reference material: how big, and how often it changes.
4. The hard rules, which become code gates and not prose.

## What it produces

A draft with the instructions last, the reference material above them, and a
line naming the model it is tuned against. The draft is measured before you
see it:

```
draft.md
  instructions 9   reference lines 240   all-rules estimate 83% (healthy)
  0 findings
```

## Process

Invoke `Skill('prompt-fit:writing-prompts')` with the description and the flags.
