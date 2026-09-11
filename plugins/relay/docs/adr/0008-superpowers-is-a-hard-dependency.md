---
status: accepted
date: 2026-06-06
---

# superpowers is a hard dependency, not a vendored copy

Relay ships no SDLC primitive of its own. Brainstorming, plan and spec authoring,
TDD, systematic debugging, worktrees and code review are delegated to
`superpowers:*`, and every command runs `scripts/check-deps.sh` first and blocks with
an install hint if superpowers is absent.

## Considered options

Vendoring the primitives would remove the install-order requirement and the blocking
gate. It was rejected because it forks maintenance of skills relay does not own and
guarantees drift from upstream — relay is a port and extension of superpowers'
orchestration layer, and re-implementing the layer beneath it would make every
upstream improvement a merge.

## Consequences

Relay is unusable without superpowers installed, which is a real onboarding cost paid
deliberately and made loud rather than mysterious: the gate blocks with an install
hint rather than failing later inside a dispatch.

The referenced skill set is closed — only the entries in
`scripts/upstream-superpowers-skills.txt` may be cited, enforced across every
non-Python file. This stops relay accreting references to upstream skills that were
never verified to exist, which is how the previous generation of dangling references
accumulated.

The canonical install source is `obra/superpowers-marketplace`. The
`ai-advanced-futures/claude-code-dev-plugins` build satisfies the same presence gate
and ships the same delegated skills, but the in-command hint points at the canonical
source so the install path and the on-disk gate stay in lockstep.

Relay owns the orchestration layer only: dispatch, refinement loops, the command
surface, and the reliability spine. Anything that is a development *primitive* rather
than a way of *coordinating* primitives belongs upstream, and that boundary is the
practical test for where new work should live.
