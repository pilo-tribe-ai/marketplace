---
description: "Regenerate the ADR register and lint the corpus."
argument-hint: "[config path]"
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, Skill, Edit
---

# /adr:index

Invoke the `adr:indexing-adrs` Skill and pass `$ARGUMENTS` through as an optional config path.

The skill owns the write step, the receipt review, and the lint. This command holds no gate
commands of its own.
