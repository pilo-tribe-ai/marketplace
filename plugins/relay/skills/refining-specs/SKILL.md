---
name: refining-specs
description: Use when a spec needs pressure-testing before plan generation, or when a spec has known gaps that need systematic discovery. Thin shim over relay:refining with the spec adapter.
user-invocable: false
---

# Refining Specs

Announce at start: "I'm using the refining-specs skill to pressure-test this spec."

Invoke `relay:refining` via the Skill tool with adapter slug `spec` and this inline config:

```yaml
# The Workflow supplies resolved literals, for example engine: acpx / agent: opencode.
# If the fields are absent, relay:refining uses in-session / claude.
engine: ${RELAY_ENGINE}
agent: ${RELAY_AGENT}
subject: spec document (markdown)
subject_adapter: adapters/spec.md
critics:
  - role: roles/spec-simulator.md  # reader role → dispatched via relay:leaf-reader
    leaf: relay:leaf-reader
    model: claude
fixer:
  role: roles/spec-fixer.md        # writer role → dispatched via relay:leaf-worker
  leaf: relay:leaf-worker
```

No invariant overrides — all inherited.
