---
name: revising-prompts
description: Applies the August 2026 prompt engineering principles to a prompt, skill, command, agent or plugin, deleting before rewriting, and proves the revision moved the instruction count or the finding count. Backs /prompt-fit:revise.
---

# Revising prompts

Apply `${CLAUDE_PLUGIN_ROOT}/reference/principles.md` to a target, and measure
what the change did.

**Announce at start:** "I'm using the revising-prompts skill to shrink this
prompt and measure the result."

## The order of work

Delete, then rewrite, then move. Deleting comes first because additions degrade
quality on current models, so the cheapest fix available in 2026 is a deletion
(L2).

1. **Delete.** Personas (L3), politeness and pressure (L4), anti-laziness
   scaffolding (L5), prescribed reasoning (L7), and any instruction that
   repairs an older model's behaviour.
2. **Rewrite.** Emphasis into plain words (L1), judgment words into numbers
   (P3), bare prohibitions into a prohibition with its reason (P7), and a
   numbered method into the outcome it was aiming at (P1).
3. **Move.** Hard content rules into a classifier or a code hook (P8), and long
   reference material below the instructions (P5) or out into its own file.

## Before editing

Run `/prompt-fit:review` on the target, or run its two scripts, so that the
before-measurement exists. Keep the before copy:

```bash
cp <file> "${TMPDIR:-/tmp}/prompt-fit-before-$(basename <file>)"
```

The git state comes from `resolve_target.py`. It decides where the revision is
written:

| Git state | Write to |
| --- | --- |
| tracked-clean | the file, in place |
| tracked-dirty, untracked, not-in-git | `<name>.revised.md`, beside the file |

An in-place edit is safe on a clean tracked file because git holds the undo. On
any other state there is no undo, so the revision goes in a new file and the
report names it.

## While editing

Record every deletion as you make it: the text removed, and the behaviour it
was there to protect. A deletion with no record cannot be reversed by a reader
who later finds a regression.

Keep these, and say in the report that you kept them:

- an instruction that names an output contract, such as a format or a length;
- an instruction that a deterministic gate depends on;
- scaffolding on a prompt that runs on a small or unpinned model (U2).

## Proof

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/compare_prompts.py" <before> <after>
```

Exit code 1 says the revision moved no count down: the same instructions, and
the same findings. Report that plainly as "no measurable change", and say what
was rewritten instead. A revision loop that reports success on an unmoved
measurement teaches the reader to trust a number that means nothing.

## The report

Four parts, in this order:

1. The before-and-after table from `compare_prompts.py`.
2. The deletions, one line each: what went, and what it protected.
3. What was kept, and why.
4. A re-test note: the model this prompt is now tuned against, and the
   sentence that a model swap is a breaking change (P9).

```
instructions        34 → 11   (-23)
reference lines    120 → 260  (+140)
all-rules estimate 50% → 80%  (+30pp)
findings             9 → 1    (-8)
```

## Evaluations

This skill measures the shape of a prompt. It does not measure whether the
prompt still does its job. Close the report by naming the evaluation the reader
should run, and by saying that the numbers above are shape and not behaviour.
