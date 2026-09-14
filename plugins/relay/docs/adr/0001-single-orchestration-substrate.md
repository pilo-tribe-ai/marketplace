---
status: accepted
date: 2026-06-18
---

# One orchestration substrate: the native Workflow tool

Every L3 command generates exactly one dynamic Workflow inline, and nothing else
orchestrates. In-session versus out-of-process execution is demoted to a per-role
binding resolved at Workflow-generation time, rather than being a second substrate a
command could choose between.

## Considered options

Earlier versions carried more than one orchestration path — a Workflow spine for some
commands and direct skill-driven dispatch for others — with the choice made at the
command level. That meant two code paths for resume, two for phasing, and a standing
question at every new command about which one it belonged to.

## Consequences

Resume and deterministic phasing come from the substrate rather than being
reimplemented, and a role's execution mechanism becomes a data question
(`bindings/presets.yaml`) instead of a control-flow question.

The cost is a hard dependency on dynamic Workflows being enabled. If they are turned
off — `/config`, `"disableWorkflows": true`, or `CLAUDE_CODE_DISABLE_WORKFLOWS=1` —
the `Workflow` tool is absent and the commands cannot run as designed. There is no
fallback path, deliberately: a fallback would be the second substrate this decision
exists to remove.

One documented exception. `/relay:drive` may have MAIN own a single long-lived
process before generating its Workflow, because a process launched inside an
ephemeral Workflow leaf dies with that leaf. It still generates exactly one Workflow,
so the doctrine holds.
