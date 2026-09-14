# Adapter: spec

Subject I/O for `relay:refining` when the subject is a **spec document (markdown)**. The
generic loop in `skills/refining/SKILL.md` calls the verbs below, each bound to spec-file
behavior.

## Interface

### `load()`
Read the spec markdown at `spec_file_path`; return its full text as the subject snapshot.

### `snapshot(subject)`
Return the spec's **pre-text** — the full markdown body captured before any fixer runs this
round. `diff()` compares against this opaque pre-state.

### `diff(snapshot, current)`
Return a structured (line/section-level) diff between the pre-text snapshot and the current
spec text, for the round report.

### `post_fix(action)`
The spec post-fix action is **`re-read`**: after `spec-fixer` patches the file, re-`load()` it
from disk so the next round's critic critiques the patched text.

### `persist(round, findings, marker)`
Write resume state in two places:
- A **sidecar findings file** alongside the spec capturing the round's structured findings.
- **Inline `[inferred]` tags** in the spec body where the fixer made inferred decisions, plus a
  `Refinement: CONVERGED round N` (or in-progress) marker in the spec's `## Refinement Status`
  section.

### `recover()`
Read the `Refinement: ... round N` marker from the spec's `## Refinement Status` section and
return the last completed round so the loop can resume rather than restart.
