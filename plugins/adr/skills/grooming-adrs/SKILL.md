---
name: grooming-adrs
description: Grooms the ADR corpus -- merges overlapping records, retires ADRs reality has outgrown, compresses bloated prose in place, and archives the dead. Use for "/adr:groom", "the ADR corpus is rotting", "merge these ADRs", "these two ADRs say the same thing", "archive the dead ADRs", "clean up the ADR corpus". Invoked by a human. Always proposes a plan and shows a diff first; never rewrites silently.
argument-hint: "[job]"
allowed-tools: Bash, Read, Grep, Glob, Write, Edit, AskUserQuestion
---

# grooming-adrs

Grooming is invoked by a human -- it rewrites a corpus, so it does not fire on its own the way
capture and recall do. It **always proposes a plan and shows a diff first**, and it never rewrites
in silence. `$ARGUMENTS` selects a job by name (`merge`, `retire`, `compress`, `archive`); with no
argument, ask which job to run.

## Job 1 -- merge overlapping ADRs

Several records circling one decision collapse into one. Read the corpus, find ADRs that make the
same decision or two halves of one decision, and propose which one survives. Show the merged text
as a diff before writing it. The originals become `status: superseded` and set `superseded_by` to
point at the survivor; the survivor sets `supersedes` to list them -- so old links still resolve
and no supersede is one-sided.

## Job 2 -- retire what reality outgrew

This job reads code, not just the corpus. Flag ADRs the code no longer reflects, and `accepted`
ADRs that contradict each other. Propose `status: deprecated` (nothing replaces the decision) or
`status: superseded` (something does, and a new ADR names it) for each one, and show the diff
before writing it.

## Job 3 -- compress prose in place

Rewrite bloated ADRs to the distillation standard. Read
`${CLAUDE_PLUGIN_ROOT}/skills/authoring-adrs/distillation.md` and apply it: drop the design-journal
voice, fold appended `## Update:` blocks into the decision, and lose no meaning. Show the diff
before writing it -- this job never rewrites silently.

## Job 4 -- archive the dead

Move `superseded` and `deprecated` records into `{{DIR}}/archive/` (the corpus's own `archive/`
subdirectory) and set `archive_dir` in `.claude/adr.json` the first time this job archives
anything. **On-disk layout is flat by default and nothing moves unless this job is invoked.**

Archiving changes the file's path, so it must repair every inbound link before the next
regeneration, in this order:

1. Move the file to `{{DIR}}/archive/<filename>`.
2. Repair every inbound link across the corpus: any `supersedes`, `superseded_by`, or `related`
   value elsewhere in the corpus that names this file, and any hand-written markdown link that
   points at it.
3. Rewrite the moved row's href in the register from `(./<file>)` to `(./archive/<file>)`, **before**
   the next `adr_index.py --write` -- because the register keys the hand-authored summary by the
   href, and rewriting the key here is what carries that summary across the move instead of losing
   it to a fresh `<!-- TODO: summary -->`.
4. Run `python3 scripts/adr/adr_index.py --write` and `python3 scripts/adr/adr_lint.py` after every
   move, and report their output. Never claim the archive landed while the lint is red.

## Close every groom job

Show the plan and the diff, get confirmation, then write. After any move or rewrite, run:

```bash
python3 scripts/adr/adr_index.py --write
python3 scripts/adr/adr_lint.py
```

Report the result plainly. Never claim grooming landed while the lint is red.
