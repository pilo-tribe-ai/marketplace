---
description: "Scaffold an architecture-decision-record corpus into this repository. Detects any prior corpus, offers greenfield, adopt, or migrate, confirms once, writes the corpus and vendored tooling, then verifies the register and lint gates pass before declaring done."
argument-hint: "[corpus path]"
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, Skill, AskUserQuestion, Write, Edit
---

# /adr:setup

This command provisions the ADR corpus, so it must NOT gate on the corpus already existing --
running it is how the corpus gets created (or adopted, if one already exists in another shape).

## Step 1 -- Invoke the scaffolding coordinator

Invoke the `adr:scaffolding-adr-corpora` Skill. It runs the full 6-step setup flow:

1. Resolve the repository root; stop if this is not a git repository.
2. Detect a prior `.claude/adr.json`, or an existing ADR-shaped folder, and report what was found.
3. Offer the path: greenfield, adopt, migrate, or abort -- and offer the optional gate here.
4. Confirm every inferred value and the full file manifest with you, once.
5. Write the corpus, `.claude/adr.json`, the vendored scripts, and both CLAUDE.md blocks.
6. Run `adr_index.py --write` and `adr_lint.py`, and report a receipt. Setup is done only when
   both are green.

Pass `$ARGUMENTS` through verbatim as a corpus-path hint. The skill owns all interaction from here;
this command holds no paths and no gate commands of its own.
