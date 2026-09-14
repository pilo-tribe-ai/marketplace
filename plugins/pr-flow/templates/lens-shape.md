<!-- pr-flow generator template — /pr-flow:setup instantiates this shape once per confirmed concern as .claude/skills/reviewing-<concern>/SKILL.md in the target repo; not an active plugin skill. -->

---
name: reviewing-<concern>
description: <one-line, repo-specific: what this lens flags. Written by /pr-flow:setup from the mined evidence and the user's confirmed concern.>
allowed-tools: Read, Glob
---

# reviewing-<concern>

Read the diff against this list. Report one finding for each line that matches. Report nothing
else.

- flag: <condition with a measurable threshold, e.g. "a function with more than 20 lines">
- flag: <condition, e.g. "a block of 5 or more identical lines present in 2 or more files">
- flag: <condition, e.g. "a change under `src/api/**` with no change under `docs/adr/**`">

- do not flag: <an adjacent change the list does not govern>
- do not flag: <anything a command in the contract's Deterministic-gates section already owns>

<!-- Worked example (illustration only — /pr-flow:setup replaces the list above with the target
repo's own lines; delete this comment block in generated output):

  name: reviewing-adr-coverage
  - flag: a change under `src/**` that contradicts a statement in an accepted ADR under
    `docs/adr/**`, with no change to that ADR in the same diff.
  - flag: a change to one ADR that contradicts a statement in another accepted ADR.
  - flag: a new top-level directory under `src/`, a new dependency in the package manifest, or a new
    network boundary, with no new file under `docs/adr/` in the same diff.
  - do not flag: a change under `docs/adr/` that only fixes spelling or a link.
  - do not flag: a broken link — `npm run lint:links` owns it.
-->
