---
name: indexing-adrs
description: Regenerates the ADR register and lints the corpus. Use for "/adr:index", "regenerate the ADR register", "the register is stale", "reindex the ADRs", and fires after an ADR is added, renamed, or retitled, and whenever CI reports the index stale.
argument-hint: "[config path]"
allowed-tools: Bash, Read, Grep, Glob, Edit
---

# indexing-adrs

Regenerate the register from the corpus, then lint. Do this after any ADR is added, renamed, or
retitled, or whenever CI reports the index stale.

## Method

1. Run the write step from the repository root and print its receipt verbatim:

   ```bash
   python3 scripts/adr/adr_index.py --write
   ```

2. Read the receipt.
   - A `dropped row:` line means a hand-authored summary lost its file. Put the summary back under
     the right ADR if the file moved or was renamed, or say plainly that the ADR is gone.
   - An `unparsed row:` line means a row nobody can key. Repair it by hand into the
     `- [label](href) — status — summary` shape.

3. Replace each `<!-- TODO: summary -->` placeholder with one line of meaning. The machine keeps
   the structure honest; the human keeps the meaning.

4. **Never hand-edit between the markers.** Everything between
   `<!-- ADR-INDEX:BEGIN (generated — do not edit) -->` and `<!-- ADR-INDEX:END -->` is overwritten
   on the next run. Make your edits above the begin marker or below the end marker, never between
   the markers.

5. Run the lint and report every error and warning:

   ```bash
   python3 scripts/adr/adr_lint.py
   ```

   Never report success while the lint exits non-zero. A red lint is red -- say so plainly, and
   name what is failing.
