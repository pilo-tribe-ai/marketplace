---
name: reviewing-prompts
description: Measures a prompt, skill, command, agent or plugin against the August 2026 prompt engineering principles, and reports findings that cite a rule identifier. It reads and measures, and it edits nothing. Backs /prompt-fit:review.
---

# Reviewing prompts

Measure one target against `${CLAUDE_PLUGIN_ROOT}/reference/principles.md`, and
report what it costs itself.

**Announce at start:** "I'm using the reviewing-prompts skill to measure this
prompt against the August 2026 principles."

This skill edits nothing. `/prompt-fit:revise` is the command that edits.

## Scope

The target is a file, a skill folder, a plugin folder, a project folder, or
text the user pasted. For pasted text, write it to a file first, and review the
file.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_target.py" <target> --json
```

The file list this prints is the whole scope of the review. Exit code 2 ends
the review, and its message says which of the three causes applies: the path is
missing, the target holds no prompt file, or the file count is over the cap of
100. On the last of these, name a folder inside the target and start again.

## Measurement

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prompt_lint.py" <each resolved file> --json
```

The output is evidence for the review, and not the review. It gives the
instruction count, the reference-line count, the band, and every finding the
ten automatic checks raise.

## Judgement

Read each file. Eight entries hold no automatic check, and a reader decides
them: P1, P4, P9, L2, L6, L8, U1 and U2. Read
`${CLAUDE_PLUGIN_ROOT}/reference/principles.md` for what each one asks.

The two that pay most on a long file:

- **P1.** A numbered method that describes how to work is one finding, whatever
  its length. Replace it with the outcome it was aiming at, stated with a
  number.
- **L2.** An instruction that repairs an older model's behaviour is a deletion
  candidate. The instruction count is the number that shows this over time.

Report a judgement finding only with the text that raised it. A finding with no
quoted text is a guess, and a guess wastes the reader's time.

## The report

One table per file, then one headline for the target.

| Column | Holds |
| --- | --- |
| line | the line number, from the tool or from your own reading |
| rule | the identifier, such as P3 or L1 |
| cost | delete, rewrite, or move |
| instructions | how many instructions the fix removes, 0 or more |
| finding | one sentence, and the text that raised it |

Order the rows by the instructions removed, highest first. Where two rows
remove the same number, put delete above rewrite, and rewrite above move.
Deleting is the first move, because additions degrade quality (L2).

The headline names five numbers: files reviewed, instructions, band,
findings, and instructions removable.

```
4 files, 61 instructions, at-risk (30%), 12 findings, 24 instructions removable
```

A review that resolved no file reports no headline. It reports the exit-code-2
message instead, because a run that measured nothing has nothing to say.

## What to hand back

End with the one change that pays most, named as a file and a line. Offer
`/prompt-fit:revise <target>` as the next step, and say that git is the undo.
