# Changelog

## 0.1.0

First release.

- `/prompt-fit:review` measures a file, a skill, a command, an agent, a plugin,
  or a whole project against the August 2026 prompt engineering principles, and
  reports findings that cite a rule identifier. It edits nothing.
- `/prompt-fit:revise` applies the findings in the order delete, rewrite, move,
  and proves that the instruction count or the finding count went down.
- `/prompt-fit:new` drafts a prompt in the 2026 shape: few outcome-shaped
  instructions, reference material held apart, hard rules left to code.
- `scripts/prompt_lint.py` counts instructions and reference lines separately,
  and raises ten checks. It reports the all-rules estimate over three bands,
  from the 0.98 per-rule figure that `--per-rule` can change.
- `scripts/compare_prompts.py` exits 1 when a revision moved no count down, so
  a revision loop cannot report success on a rewrite that measures the same.
- `scripts/resolve_target.py` prints the scope of a review, with each file's
  role and git state. It ends the run on a target that holds no prompt file, or
  that holds more than 100, rather than reviewing a part of it in silence.
- `reference/principles.md` holds all 19 rules, each with its check or a note
  that it is judgement only, its confidence label, and a broken-and-fixed pair.
  A finding cites one of them, so a reader can find what it means.
