---
name: amending-adrs
description: Changes a recorded decision when it changes -- rewrites the ADR in place, deprecates it, or supersedes it with correct back-links on both sides. Use for "the decision changed", "deprecate this ADR", "supersede ADR N", "we no longer do X", and fires on its own when a session changes a decision an existing ADR records.
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

# amending-adrs

A recorded decision just changed. Update the corpus to match. There is no command for this skill
-- it is reached by the model on its own, or from `authoring-adrs` when writing a new ADR requires
retiring an old one.

**Rewrite in place. Never append an `## Update` block.** Git holds the history; the ADR only needs
to say what is true now. Apply
`${CLAUDE_PLUGIN_ROOT}/skills/authoring-adrs/distillation.md` to every rewrite.

## Three cases

1. **The decision stands, the wording is stale.** Rewrite the ADR in place. Do not add an
   `## Update` block and do not keep the old wording alongside the new -- replace it.

2. **The decision is withdrawn and nothing replaces it.** Set `status: deprecated`. State in
   Consequences what now applies instead.

3. **The decision is replaced by a new one.** Write the new ADR first, with `authoring-adrs`. Then
   set on the old ADR: `status: superseded` and `superseded_by: [<new filename>]`. Set on the new
   ADR: `supersedes: [<old filename>]`.

   **Set both sides, every time.** A one-sided supersede -- one ADR naming the other, but not the
   reverse -- is a lint error. Cross-references hold filenames; a cross-reference is never a number.
   The filename is the identity.

## Close every amend

Run both gates and report their output:

```bash
python3 scripts/adr/adr_index.py --write
python3 scripts/adr/adr_lint.py
```

Report the result plainly. Never claim the amend landed while the lint is red.
