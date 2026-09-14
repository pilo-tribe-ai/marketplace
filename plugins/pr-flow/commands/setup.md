---
description: "Bootstrap a repo-specific PR-review system into this repository. Interrogates the repo and its review history, proposes a checklist of review concerns, confirms them with you, then writes .claude/pr-flow/contract.md and generates one .claude/skills/reviewing-<concern> lens per confirmed concern. Idempotent — safe to re-run to fold in new signal."
argument-hint: "[concerns to emphasise]"
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, Skill, AskUserQuestion, Write, Edit
---

# /pr-flow:setup

This command is a thin entry point. It provisions the review system, so it must NOT gate on
the system already existing — running it is how the system gets created (or refreshed).

## Step 1 — Invoke the bootstrap coordinator

Invoke the `pr-flow:bootstrapping-pr-flow` Skill. It runs the full 5-step setup flow:

1. Detect any prior `.claude/pr-flow/contract.md` / `.claude/skills/reviewing-*` and offer
   update vs. fresh.
2. Mine four signal sources (GitHub PR review history, repo docs, git/codebase shape, prior
   artifacts).
3. Reason about the repo and draft a candidate checklist of review concerns with evidence.
4. Interrogate you (confirm / add / drop concerns, capture invariants and deterministic gates).
5. Generate the contract and per-concern lens skills, then print a receipt.

Pass along any arguments verbatim as free-form hints (e.g. a concern to emphasise). The skill
owns all interaction from here.
