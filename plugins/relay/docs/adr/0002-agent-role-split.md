---
status: accepted
date: 2026-06-11
---

# Split behavior from capability: roles execute inside two generic leaves

An agent is a capability container; a role is a behavior payload. `agents/*.md` are
Claude Code subagent registrations carrying `tools:` and nothing task-specific;
`roles/*.md` are engine-neutral prompt bodies carrying a typed I/O contract and
explicitly forbidden from declaring `name`, `tools`, or `model`. `role-class`
mechanically derives the container — `writer` → `relay:leaf-worker`, `reader` →
`relay:leaf-reader`.

## Considered options

The obvious shape is one registered agent per behavior, which is what relay had
before v4.0.0: 22 agents, each with its own tool grant. That was rejected and
migrated away from in `2f9cbd1`.

Three forces drove the split. Tool grants are fixed at registration while behavior is
not, so 22 agents meant 22 tool surfaces to audit and 22 descriptions in every
session's inventory. Role bodies must run off Claude Code entirely — the same
`roles/implementer.md` ships to a codex or opencode process, which has no concept of
a Claude Code agent, so anything Claude-Code-specific in a role file is a portability
bug. And collapsing the tool axis to two values is what makes the depth-1 guarantee
in [ADR-0003](0003-depth-1-by-tool-omission.md) auditable at all.

## Consequences

Adding a behavior costs a markdown file and a YAML row rather than a new registered
agent, and the tool surface stops growing with the role count.

The price is indirection: reading a role file alone does not tell you what it can do.
Capability lives in `bindings/presets.yaml` and the leaf's `tools:`, so three files
must be read together. The bijection between `roles/*.md` and presets keys is
enforced in both directions to stop that spreading further.

Because roles cannot call `Skill()` (see ADR-0003), role bodies vendor their rubrics
inline. That duplicates guidance that would otherwise live in a shared skill, and is
accepted as the cost of the isolation.
