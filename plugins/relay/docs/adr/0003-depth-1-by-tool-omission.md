---
status: accepted
date: 2026-06-11
---

# Enforce depth-1 by omitting tools, not by instructing the agent

Neither execution leaf lists `Agent` or `Skill` in its `tools:`. Tools that are not
listed are absent from the session at initialization, so a dispatched role
structurally cannot spawn a subagent or load a skill — there is no tool to call.

## Considered options

The alternative is a prompt-level instruction: "do not invoke agents or skills." The
leaves carry that line too, but only as documentation of intent. An instruction is
advisory — a sufficiently confused model can ignore it, and nothing observes the
violation until a runaway fan-out has already happened. Omission is unforgeable.

## Consequences

Recursion depth is bounded by construction rather than by behavior, which is what
makes fan-out cost predictable.

It also means a leaf cannot reach shared guidance, so rubrics are vendored into role
bodies (see [ADR-0002](0002-agent-role-split.md)).

The guarantee is only as strong as the registration that produces it, which is not
obvious and was violated for seventeen releases: `agents/README.md` carried no
frontmatter, registered as `relay:README`, and an agent with no `tools:` key receives
*every* tool — so the file documenting this invariant held both withheld tools. Fixed
in 4.18.0 by moving it to `docs/`, with `test_agent_registration.py` asserting that
`agents/` contains only real agents and that every one of them declares `tools:`.
