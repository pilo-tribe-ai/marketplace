# Relay Agents

**7 agents total:** 2 user-facing primitives (`code-reviewer`, `scout`), 2 generic
execution leaves (`leaf-worker`, `leaf-reader`), 3 Workflow-only diagnosis agents
(`gatherer`, `strategist`, `analyst`).

## User-facing primitives

| agent | tools | description |
|-------|-------|-------------|
| `relay:code-reviewer` | Read, Bash, Grep, Glob | PR review primitive; referenced externally |
| `relay:scout` | Read, Bash, Grep, Glob, WebFetch, WebSearch | Context-gathering primitive |

## Generic execution leaves

The leaves execute injected role bodies from `roles/<slug>.md`. Do not invoke directly.

| agent | tools | role-class |
|-------|-------|-----------|
| `relay:leaf-worker` | Read, Write, Edit, Bash, Grep, Glob | writer |
| `relay:leaf-reader` | Read, Grep, Glob, Bash | reader |

**Leaf enforcement:** neither leaf lists `Agent` or `Skill` in its `tools:`. Tools not
listed are **absent** from the session at session initialization (S2 spike). This is the
depth-1 invariant — subagents cannot spawn subagents.

## Diagnosis (Workflow substrate)

Three specialized agents for `/relay:diagnose`'s inline Workflow. Kept registered because
Workflow `agent()` requires registered agentTypes and they carry distinct tool grants.

| agent | tools | model |
|-------|-------|-------|
| `relay:gatherer` | Bash, Grep, Read, WebFetch, WebSearch | haiku |
| `relay:strategist` | Read, Grep | opus |
| `relay:analyst` | Read, Grep, WebSearch, WebFetch | opus |

They carry **no** `relay:` block and are **absent** from `bindings/presets.yaml`.

## Session-tree topology roles

These name a session's place in a session tree (`--engine session-tree`, spec
§Deliverable 3). They are not dispatchable roles and they have no file under
`roles/`. They are part of the closed roster the §1.2 naming grammar validates
against — `scripts/bg-launch.sh --check-name` reads this table the same way it
reads the agent tables above.

| role | meaning |
|-------|---------|
| `relay:orchestrator` | MAIN. Spawns every session. Owns the user channel. |
| `relay:operator` | Coordinates one goal's subtree. Never spawns. |
| `relay:worker` | A leaf under an operator. |

## Not ported

`brainstormer` and `codex-session-driver` were never ported (deprecated roles from
earlier relay versions).

## Roles

22 roles live in `roles/*.md`, dispatched through the leaves. See `roles/README.md`.
