---
name: refining-plans
description: Use when a plan has been written and needs pressure-testing before execution, or when a plan has known gaps that need systematic discovery. Thin shim over relay:refining with the plan adapter.
user-invocable: false
---

# Refining Plans

Announce at start: "I'm using the refining-plans skill to pressure-test this plan."

Invoke `relay:refining` via the Skill tool with adapter slug `plan` and this inline config:

```yaml
# The Workflow supplies resolved literals, for example engine: acpx / agent: opencode.
# If the fields are absent, relay:refining uses in-session / claude.
engine: ${RELAY_ENGINE}
agent: ${RELAY_AGENT}
subject: plan document (markdown)
subject_adapter: adapters/plan.md
critics:
  - role: roles/plan-simulator.md  # reader role → dispatched via relay:leaf-reader
    leaf: relay:leaf-reader
    model: claude
fixer:
  role: roles/plan-fixer.md        # writer role → dispatched via relay:leaf-worker
  leaf: relay:leaf-worker
```

No invariant overrides — all inherited.
