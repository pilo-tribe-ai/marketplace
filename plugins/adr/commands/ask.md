---
description: "Answer a question from what was decided, with path:line citations."
argument-hint: "[question]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Skill
---

# /adr:ask

Invoke the `adr:consulting-decisions` Skill and pass `$ARGUMENTS` through verbatim as the
question.

This command never edits and never writes. The skill it invokes is read-only by construction --
its own tool list holds nothing that can change the repo.
