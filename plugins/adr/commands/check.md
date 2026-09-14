---
description: "Check the current branch's diff against the ADR corpus for contradictions and missing decisions."
argument-hint: "[base branch]"
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, Skill
---

# /adr:check

Invoke the `adr:reviewing-adr-adherence` Skill and pass `$ARGUMENTS` through verbatim as an
optional base-branch override.

This is the gate's model tier: it reads the diff, reports findings, and always exits 0. It never
blocks on its own judgement -- the deterministic tier (`adr_lint.py`, `adr_index.py --check`) is
what the gate blocks on. This command holds no review procedure of its own.
