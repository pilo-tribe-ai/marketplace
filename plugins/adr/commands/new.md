---
description: "Write one ADR for a decision that is expensive to undo."
argument-hint: "[decision]"
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, Skill, Write, Edit
---

# /adr:new

Invoke the `adr:authoring-adrs` Skill and pass `$ARGUMENTS` through verbatim as the decision to
record.

The skill owns the bar for what earns an ADR, the write itself, and running the index and lint
gates afterward. This command holds no write procedure of its own.
