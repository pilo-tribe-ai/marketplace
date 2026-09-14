---
description: Ask a question of the knowledge bundle named by .claude/wiki.json, per AGENTS.md "Operation: Query"
argument-hint: "<question>"
allowed-tools: Read, Grep, Glob, Skill, Edit, Write, AskUserQuestion, Bash(python3:*), Bash(test:*), Bash(ls:*)
---

# Ask the wiki

Ask the wiki this: **$ARGUMENTS**

The wiki answers from its own pages only. It never answers from outside the wiki. If no page
covers the question, it says so -- it does not guess.

## Step 0 -- resolve the container

```bash
test -f .claude/wiki.json
```

If that fails, stop: "This repository has no wiki. Run `/wiki:setup` first." Do not guess a
container path or create one by hand.

```bash
CONTAINER=$(python3 -c "import json;print(json.load(open('.claude/wiki.json'))['container'])")
test -d "$CONTAINER"
```

If the directory is missing, stop and name it:
"`.claude/wiki.json` points at `$CONTAINER`, which does not exist. Run `/wiki:setup` to re-scaffold or fix the pointer."
Every path below is written relative to `$CONTAINER`, resolved from the repository root, which is
where you are.

## Step 1 -- resolve the question

The question is `$ARGUMENTS` verbatim. If `$ARGUMENTS` is empty, stop:
"Give me a question. Run `/wiki:ask <your question>`."
Never invent a question. Never answer a question the user did not ask.

## Step 2 -- hand off

Invoke the `wiki:answering-from-okf-wikis` Skill. Pass `$CONTAINER` and the question verbatim.
The skill owns everything from here. This command holds no retrieval rule, no citation rule, and
no gate command of its own.
