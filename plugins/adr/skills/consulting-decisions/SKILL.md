---
name: consulting-decisions
description: Answers questions about past architectural decisions from the ADR corpus, read-only. Use for "/adr:ask", "why did we choose X over Y", "remind me why we did X", "is this still true", "did we ever decide X", "what's our stance on X", and fires before an architectural boundary changes so past decisions are read before new ones are made.
allowed-tools: Read, Grep, Glob
---

# consulting-decisions

Answer a question from what the ADR corpus already records. This skill is read-only: it never
edits, writes, or runs a shell command.

## Method

1. Read `.claude/adr.json` for the corpus `dir` and `register` paths.
2. **Read the register first.** It holds one line per ADR. Use it to rule out what does not apply,
   before opening any single ADR. This is the whole reason the register exists: a corpus of 122
   ADRs costs about 122 lines to rule out, instead of 122 file reads.
3. Open only the two or three ADRs that apply, in full. Open only the ones the register pointed at.
4. Answer with `path:line` citations for every claim. A claim with no citation is a guess, not an
   answer.
5. Say plainly what the corpus does not cover. An unrecorded decision is a gap, not a "no" --
   never imply a decision was made when the corpus is silent on it.
6. Report what was recorded, not what the code now does. This skill answers from the corpus, not
   from reading the implementation. When a decision looks stale against current code, say so, and
   point at `/adr:groom` -- do not fix it here.
