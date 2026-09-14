---
name: routing-work-to-agents
description: Use to apply relay's smart-routing policy when assigning a task to a provider — maps task kind to the correct engine/agent pair (claude for reasoning/design/scouting, codex for coding/plan-writing) before any dispatch is attempted.
user-invocable: false
---

# routing-work-to-agents

routing-work-to-agents owns the smart-routing policy that maps a classified task to its canonical provider. It is the resolution node between `classifying-task-kind` (which names the kind) and any dispatch skill (which executes the assignment). No dispatch occurs here; this skill resolves the binding only.

## Policy

Relay routes on two axes: **task class** and **required capability**.

### Claude — reasoning, design, scouting

Assign to `claude` (in-session or acpx-claude) when the task class is any of:

- `reasoning` — multi-step inference, root-cause diagnosis, design trade-off analysis
- `design` — architectural decisions, spec authoring, brainstorm synthesis
- `scouting` — codebase orientation, context gathering, dependency mapping
- `review` — code or spec adversarial critique (skeptic/advocate/pragmatist mandates)
- `docs` — prose, reference documentation, language-reference updates

Claude is the default provider for every task class not explicitly assigned to codex below.

### Codex — coding, plan-writing

Assign to `codex` (acpx-codex or codex-session) when the task class is any of:

- `coding` — implementing features, writing tests, applying fixes to the working tree
- `feature` — the classifier's kind for end-to-end feature implementation; routes as `coding`
- `bugfix` — the classifier's kind for defect fixes; routes as `coding`
- `plan-writing` — authoring step-by-step implementation plans in the relay plan format
- `script` — one-off runnable scripts (bash, python, etc.) that must be written to disk
- `config-artifact` — generated config/manifest files that must be written to disk

Codex is preferred when the deliverable is a durable file artifact produced by a deterministic code-generation pass.

### Hybrid — parallel fan-out

When a pipeline phase contains independent subtasks of mixed class (e.g. a brainstorm subtask for claude AND a plan-writing subtask for codex running concurrently), resolve each subtask independently via this policy and let the orchestrating `parallel-gather` or `staged-run` skill manage the fan-out. Do not coerce a mixed phase to a single provider.

## When not to dispatch

Do the work in the orchestrator, with no dispatch, when any of these hold:

- The answer needs one file read or one command.
- The deliverable is smaller than the dispatch prompt (preamble + role body + envelope).
- The task is a decision about routing or classification itself.

Dispatch overhead must be smaller than the work it moves. When it is not, return
`provider: "none"` in the routing result and let the caller do the work inline.
When `provider` is `"none"`, `engine` stays `"in-session"`: no dispatch happens, and the caller works inline.

## Override

A caller may pass an explicit `--agent` override (`claude` | `codex` | `hybrid` | `opencode`). When present, validate it is one of the four known agents and use it directly — skip policy evaluation above. Record the override source in the routing result so a downstream auditor can distinguish policy-driven from caller-overridden assignments.

## Output

Emit a `typed-output` routing result:

```
{
  "provider": "claude" | "codex" | "opencode" | "hybrid" | "none",
  "engine":   "in-session" | "acpx",
  "reason":   "<one-line policy rationale or 'caller override'>",
  "task_class": "<the input task class>"
}
```

The result is consumed directly by the caller's dispatch node. It carries no leaf constraint — the dispatch skill enforces that.

## Invariant

`engine=in-session` requires `provider=claude`. If the policy would assign `codex` or `opencode` to the in-session engine, escalate to the caller with an error rather than silently coercing; the mismatch signals a misconfigured pipeline phase (spec §2 invariant).

Calm imperatives only.
