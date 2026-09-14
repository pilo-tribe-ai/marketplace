---
description: "Groom the ADR corpus: merge overlapping ADRs, retire what reality outgrew, compress prose, or archive the dead."
argument-hint: "[merge|retire|compress|archive]"
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, Skill, AskUserQuestion, Write, Edit
---

# /adr:groom

Invoke the `adr:grooming-adrs` Skill and pass `$ARGUMENTS` through verbatim as the job selector
(`merge`, `retire`, `compress`, or `archive`; ask which job when no argument is given).

The skill owns all four jobs, the plan-then-diff discipline, and the register/link repair that
follows a move. **It always proposes a plan and shows a diff first, and never rewrites silently.**
This command holds no grooming procedure of its own.
