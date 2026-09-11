# Background-session messaging — spike findings

Date: 2026-08-18
Status: spikes complete. These findings are the input to the design of two new relay
engines: `--engine session-tree` (new substrate) and `--engine bg-sessions` (per-leaf
dispatch).

All results below come from live `claude --bg` child sessions launched from an orchestrator
session named `bg-sessions-spikes`. Every child is stopped. Nothing here is code to keep.

## What was proven

| Spike | Question | Result |
|---|---|---|
| S1 | Can a child ask its parent a question and continue after the answer? | PASS |
| S2 | Does `--fork-session` really carry the parent's context? | PASS, with a hazard |
| S3 | Do messages route through a middle tier? | PASS |
| S4 | How do failures present? | Four distinct signals recorded |

## S1 — two-way parent-child messaging

A child launched with a directive to never use `AskUserQuestion` sent
`NEEDS_DECISION from spike-s1-worker: ... ALPHA or BRAVO?`, ended its turn, and stopped.
The parent replied `DECISION ... BRAVO`. The reply re-invoked the child, which finished with
`ROLE_DONE from spike-s1-worker codename=BRAVO`.

The load-bearing property: **waiting is free.** The child ends its turn to wait, and the
incoming message starts a new turn. No poll loop, no held-open watcher turn, no budget spent
while idle. This is the property acpx cannot offer, because a Workflow agent node has exactly
one turn and must block inside it (`skills/delegate-and-watch/SKILL.md`, TURN-LIFETIME RULE).

The child must be told explicitly not to use `AskUserQuestion`, and must be given the parent's
name. Both worked as plain prose in the launch prompt.

## S2 — fork inheritance

Two children were asked the same three recall questions about this conversation, with file
reads forbidden.

- Fork (`--resume <parent-id> --fork-session`): answered all three correctly, including a
  verbatim example string the user had typed and the four-item structure of this spike plan.
- Fresh control (no resume): `Q1=UNKNOWN Q2=UNKNOWN Q3=UNKNOWN`.

Inheritance is complete for decisions, verbatim examples, and plan structure. A fork needs no
briefing about the work already done.

### Hazard S2-3: a fork of a LIVE session inherits the parent's identity

The fork inherited the instruction "run the spikes" and concluded that **it** was the original
and that the real parent was a runaway clone. Acting on that, it:

1. sent stand-down orders to three of the parent's children, telling them to stop;
2. reported to the user that a clone of the parent was running loose, naming the real parent
   as a session to kill.

Neither session could tell which copy was the original from context alone. The parent settled
it only by citing the launch command it had run.

Design consequences, all mandatory for both engines:

- A forked child MUST be given an explicit identity assignment: its own name, its parent's
  name, and the statement that it is the fork and does not own the parent's mission.
- A child MUST be told it never commands its siblings and never stops another session.
- A child MUST be told it does not address the user; the orchestrator owns the user channel.
  A confused child otherwise writes false alarms into the user-facing channel.
- The role reset must be strong enough to survive inherited momentum. The fork also re-ran the
  parent's investigation habits (reading job state files) despite an explicit
  "do not read any file" line. Inheritance carries behavior, not only facts.

## S3 — three-level tree

Topology: `bg-sessions-spikes` (orchestrator) → `roi-dashboard-operator-feature-a` (operator)
→ `roi-dashboard-implementer-feature-a` + `roi-dashboard-reviewer-feature-a` (workers).

The implementer sent `NEEDS_DECISION` to the operator. The operator did not answer it; it
relayed `ESCALATION from roi-dashboard-operator-feature-a: ...` to the orchestrator. The
orchestrator answered `line chart`. The operator relayed the answer down. The tree closed with
`ROLE_DONE from roi-dashboard-operator-feature-a implementer=line chart reviewer=ok`.

Routing through a middle tier works, and the `productName-role-goal` naming was unambiguous in
practice at every hop.

### Blocker S3-1: a child under `--permission-mode dontAsk` cannot run Bash

The operator could not launch its own workers. Its Bash call was denied with
"Permission to use Bash has been denied because Claude Code is running in don't ask mode."
The orchestrator launched the two workers instead, telling each that its parent was the
operator; the tier then worked exactly as designed.

So spawn authority and message authority are separable. Either the orchestrator spawns every
session in the tree (operators coordinate but never spawn), or operators are launched with a
permission mode that allows the launch command. The first option is simpler and is the
recommended default.

## S4 — failure behavior

Four distinct signals, all typed and all distinguishable:

| Case | Signal |
|---|---|
| Name does not exist | `No agent named 'X' is reachable.` |
| Two sessions share a name | Send refused, error lists each candidate with its `[ref]`; re-send with the ref succeeds |
| Session was stopped | `Failed to send ... HTTP 409 — that Remote Control session may have ended or disconnected.` |
| Child killed mid-task | **No notification at all.** Only the state file changes, to `state=stopped` |
| Child alive but silent | No signal. Indistinguishable from working, except through the state file |

### S4-1: a dead child is silent, so liveness needs polling

Killing a child produced no message to the parent. Death is observable only in
`~/.claude/jobs/<short-id>/state.json` (`state`, `tempo`, `updatedAt`) or through
`ListAgents`. Any engine built on this substrate needs its own liveness check; it cannot wait
on a message that never comes.

### S4-2: the state file is not a success oracle

Two sessions that completed their protocol correctly — the operator that sent its final
`ROLE_DONE`, and the fresh control that sent its full report — both read `state=blocked
tempo=blocked` afterwards. Sessions that stopped cleanly read `state=done`. The state field
tracks turn posture, not task outcome.

**The message envelope is the only truth about completion.** This preserves relay's existing
envelope contract (`ROLE_DONE`, `BLOCKED:`, `NEEDS_DECISION:`) unchanged — the envelope
travels in the message body instead of on stdout.

### S4-3: names are not unique, and refs are not stable

`SendMessage` to `spike-s1-worker` was refused because a stopped local session and a Remote
Control mirror shared the name. The `[ref]` is required to disambiguate, and a ref is only
obtainable from a listing or from the error itself — refs shown at different times for the
same session differed from the id printed at launch (`60b3cbb8` at launch, `[0187e4]` in a
later listing). An engine must therefore resolve an address at send time and must never cache
a ref.

Names must also be unique per run. `productName-role-goal` needs a run-scoped element, because
a stopped session keeps its name and collides with its own replacement.

## Launch mechanics — two traps

**Trap 1: `--allowedTools <tools...>` is variadic and eats the prompt.**

```bash
# BROKEN — the prompt becomes another allowed-tool entry, and the session starts with none
claude --bg --name w --allowedTools "SendMessage,ListAgents" "$prompt"
```

Three children launched this way reported success at the shell, then sat idle forever. Their
state files showed an empty `intent` and the detail `(idle — send a prompt to start)`. The
launch looked healthy from the outside; nothing had been asked of the child. Any launcher must
put the prompt last with no variadic flag before it, and must verify that `intent` is non-empty
before it counts the launch as successful.

**Trap 2: launching from inside a session can be denied.**

One `claude --bg` launch was refused by the auto-mode classifier ("Blocked by classifier"). The
identical command succeeded when issued alone. A launcher must treat a denied launch as a
normal outcome and report it, never assume the child exists.

## Recommended shape

```bash
claude --bg --name <product>-<role>-<goal>-<runid> --model <model> \
  --permission-mode <mode> "<prompt as the last argument>"
```

Then confirm `intent` is non-empty in `~/.claude/jobs/<short-id>/state.json` before treating the
child as launched.

## What is still unknown

- Message delivery under load: every send in these spikes was one-to-one and low volume. Fan-out
  of ten workers messaging one operator at once was not tested.
- Whether a stopped session can be resumed by message. The one attempt returned HTTP 409, but
  that session had been explicitly stopped; a crashed session may behave differently.
- Cost. No token accounting was taken for any child.
- Long-run behavior. The longest child lived about eight minutes.
