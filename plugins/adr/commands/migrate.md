---
description: "Convert a legacy bold-key ADR corpus to frontmatter."
argument-hint: "[--rename]"
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, Skill, AskUserQuestion, Edit
---

# /adr:migrate

Invoke the `adr:scaffolding-adr-corpora` Skill in its migrate path and pass `$ARGUMENTS` through
verbatim.

Two levers, because one of them breaks links:

- **`--frontmatter`** (the default) folds recognised bold-key headers into YAML frontmatter.
  Filenames are untouched.
- **`--rename`** (opt-in) also normalises `ADR-002-slug.md` to `0002-slug.md`. Renaming a file
  changes every link that points at it, inside and outside this corpus, so it is opt-in and
  confirmed before it runs.

The skill adopts the corpus first, then converts. It stages every change for review and commits
nothing. This command holds no conversion procedure of its own.
