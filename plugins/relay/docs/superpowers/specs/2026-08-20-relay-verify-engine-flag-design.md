# /relay:verify gets a dispatch axis, and defaults to in-session

Date: 2026-08-20
Status: approved for implementation
Target version: relay 4.32.0

## The problem

`/relay:verify` runs every step of its loop as an `acpx --approve-all` child session.
Because of that, the loop must ask the user one question before it generates any node.
The question exists to clear the Claude Code auto-mode rule `Create Unsafe Agents`.

The question is the symptom. The cause is the substrate.

### Why acpx was chosen

Version 4.22.0 gave one reason:

> Claude cannot invoke a slash command from inside its own model turn, so each step runs
> as one turn of a child Claude session over `acpx`.

### Why that reason no longer holds

Version 4.30.0 states the opposite:

> The model can now start both commands through the SlashCommand tool.

The harness also holds a `Skill` tool, and `commands/verify.md` already lists `Skill` in
`allowed-tools`. So a model turn can start `/simplify`, `/code-review medium --fix` and
`/verify`.

### What still blocks an in-session loop

Two things block it. Both are inside relay.

1. **No relay leaf can run a command.** `agents/leaf-worker.md` holds `Read`, `Write`,
   `Edit`, `Bash`, `Grep` and `Glob`. `agents/leaf-reader.md` holds less. Neither holds
   `Skill` or `SlashCommand`.

2. **The record machinery is in Bash, and Bash cannot call a tool.**
   `scripts/verify-loop-node.sh` holds the state, the records, the verdict parse, the
   commits and the deadline. Its `run_child()` function (line 191) starts the child
   itself. A node is therefore one Bash call.

The second point carries the important consequence. Today the script starts the child, so
a written record is evidence that a step ran. An in-session node cannot work that way.

## The design

### 1. The dispatch axis

`/relay:verify` accepts `--engine` and `--agent`, and it resolves them with
`scripts/parse-engine-agent.sh`, unchanged. That script already defaults the engine to
`in-session` and the agent to `claude`, and it already enforces
`in-session` requires `agent=claude`.

Supported engines:

| engine | supported | substrate |
|---|---|---|
| `in-session` | yes — the default | a Workflow node starts the command with `SlashCommand` |
| `acpx` | yes | `acpx --approve-all`, exactly as today |
| `smart-routing` | no | rejected |
| `bg-sessions` | no | rejected |
| `session-tree` | no | rejected |

An unsupported engine is rejected at Step 0, with the message shape that
`commands/execute.md:41` already uses:

```
[relay] error: engine=<name> is not supported by /relay:verify (supported: in-session | acpx)
```

The three rejected engines route work to other machines or to other processes. The loop
holds a deadline, a state directory under the git directory, and a commit per round.
None of the three carries those, so a claim of support would be prose without an
implementation.

### 2. The question becomes conditional

The question runs only when the resolved engine is `acpx`.

Under `in-session` there is no `acpx` call, no `--approve-all`, and no headless child, so
the rule `Create Unsafe Agents` has nothing to match. A question that names a danger that
is not present is not consent. It is ceremony, and the next editor deletes it.

Under `acpx` the question stays, with the same three facts and the same words. It is
stronger there than it was before: the user typed `--engine acpx`, so the user named the
approvals-off substrate. The rule states that naming the enclosing task does not name the
dangerous step. `--engine acpx` names the step.

The refusal contract does not change. A refused question generates no node and reports
`RELAY_VERIFY_RESULT=unverified`.

### 3. The in-session node shape

The Workflow, the rounds, the state directory, the session-independent records and the
three terminal states all stay. Only the way a step reaches the command changes.

An in-session step is one `agent()` node with `agentType: 'general-purpose'`. That agent
type holds the full tool set, so it holds `Skill`. The relay leaves stay as they are; this
design adds no tool to `leaf-worker` and no tool to `leaf-reader`.

`scripts/verify-loop-node.sh` gains a two-call protocol, used by the `in-session` engine
only:

| call | what it does |
|---|---|
| `--phase pre <kind> <worktree> <round> <rounds>` | reads the state, decides skip or run, and prints the exact prompt to send plus the reply path |
| `--phase post <kind> <worktree> <round> <rounds>` | reads the reply the caller wrote, parses the verdict, commits, writes the record, prints `NODE_STATUS` |

`post` takes no path argument. It derives the same canonical path `pre` printed, so a
caller cannot point it at a file of its own choosing.

The node prompt tells the agent three steps, in order:

1. Run `pre`. If it prints `NODE_SKIP=1`, return its `NODE_STATUS` line verbatim and stop.
2. Carry out the block that `pre` printed. Start the slash command it names with
   `SlashCommand`, do what that command asks for, then write your own closing answer to
   the file that `pre` named — including, for `check`, the verdict line the block asks for.
3. Run `post`. Return its `NODE_STATUS` line verbatim.

The `acpx` engine keeps the single call it uses today. `run_child()` does not change,
`scripts/run-claude-command.sh` does not change, and
`scripts/run-claude-prompt.sh` does not change. The locked contract that
`tests/unit/skill-structure/test_relay_implement_polish.py` covers is untouched.

### 4. A claimed run is weaker evidence than a started run

This is the real cost of the design, and it must be written down.

With `acpx`, the script starts the child. A record proves a step ran.

With `in-session`, the agent invokes the command and hands back text. An agent that runs
nothing can still write a reply file. That is this loop's own named failure mode: run
`wf_8ad76eec-5ac` returned invented `detail` values, one of them the literal word
`placeholder`, and reported `ran` for a step that had run nothing.

Four guards answer it. Every one is mechanical, and none needs judgement:

1. **An absent or empty reply file is `failed:no-reply`.** It is not a skip, and it is
   never a pass. `check` does not retry it either: no reply is the absence of an attempt,
   not a verdict of an unusable shape, and one record must not stand for both.
2. **`check` requires a verdict line in the raw reply.** `scripts/parse-verify-verdict.sh`
   already rejects a line that holds more than one verdict token. An agent that ran
   nothing has no verdict line to hand over. No verdict line means `no-answer`, which
   sets the run `unverified`.
3. **`simplify`, `review` and `fix` are measured against git, not against the reply.**
   `commit_step()` already reports `no changes` when the tree did not move. The existing
   fix-noop counter already reads that.
4. **`post` builds the output fence itself.** `parse-verify-verdict.sh` needs a
   `POLISH_CMD_OUTPUT_BEGIN` / `END` region, and it reads the first begin marker and the
   last end marker. Both of those are the script's, so the agent writes the reply only and
   cannot forge a fence. It also means an unfenced raw reply cannot reach the parser and
   silently read as `no-answer` on every round.

The guards do not make a claimed run equal to a started run. They make a fabricated pass
impossible to record, which is the property the loop needs.

### 5. Retry, in-session

The `check` step retries once for two reply shapes, and not for three others. The rule
stays exactly as it is. Only the mechanism moves.

For `in-session`, `post` makes the decision and prints `NODE_RETRY=1` instead of writing a
terminal record. The agent then invokes the command once more, overwrites the reply file,
and calls `post` again. `post` reads `check-1.out` to know it is on the retry, so the
agent holds no state and makes no choice.

`post` keeps the first reply in `check-1.out` before the retry overwrites `check.out`,
exactly as `run_check` does today.

### 6. The deadline, in-session

Under `acpx` the node budget wraps every child with `timeout`, because the whole node is
one Bash call under the caller's ten-minute ceiling.

Under `in-session` the long step is an agent turn, not a Bash call. `timeout` cannot wrap
it, and it does not need to: the two Bash calls are short, so the Bash ceiling is no
longer the binding limit.

**The deadline does not apply in-session, and it is not carried across the two calls.**
Each call is a separate process, so the wall clock restarts and an "already expired"
state can never be observed inside one call. Persisting a start time would only create a
worse failure: by the time `post` runs, the work is already done, so a `post` that refused
an expired deadline would discard work that really happened. `failed:timeout` therefore
never appears on an in-session round.

This is the one place where the two engines differ in what they can report, and it is a
removal, not a gap: the failure the deadline guards against is a child outliving the
node's single Bash call, and an in-session node has no such call.

This removes a live failure mode rather than moving it. The Bash default of 120000
milliseconds once lost 9 of 12 steps in one run, because the node reported that it had
moved the command to the background. An in-session node runs no long Bash call, so that
path is gone.

### 7. `/relay:implement --verify` stays equivalent

`/relay:implement` forwards its own resolved engine to the verify tail. So
`/relay:implement --engine acpx --verify` runs the loop over acpx, and a bare
`/relay:implement --verify` runs it in-session and asks nothing.

`/relay:implement` accepts three engines the loop does not support. The tail prints one
line and falls back to `in-session`:

```
[relay] verify: engine=<name> has no verify-loop substrate — the loop runs in-session
```

The fallback is printed, never silent. A hard rejection at the tail would throw away a
finished build over its last step.

The loop keeps exactly one identity. This skill still takes no parameter for the node
names, the session names or the state directory. The engine picks the substrate. It does
not rename anything. `/relay:implement --verify` and `/relay:implement` followed by
`/relay:verify` therefore still produce the same nodes and the same state directory.

## Files

| file | change |
|---|---|
| `commands/verify.md` | parse `--engine`/`--agent`, source `parse-engine-agent.sh`, reject the three engines, make the question conditional on acpx |
| `commands/implement.md` | forward the resolved engine to the verify tail, print the fallback line |
| `skills/verifying-until-clean/SKILL.md` | replace the stale "cannot invoke a slash command" claim, add the engine matrix, move Step 0 under an acpx condition, add the in-session node shape and the four guards |
| `scripts/verify-loop-node.sh` | add `--phase pre` and `--phase post`; leave the single-call acpx path unchanged |
| `.claude-plugin/plugin.json` | 4.31.0 to 4.32.0 |
| `CHANGELOG.md` | one 4.32.0 entry |

## Tests

New:

- The engine matrix: `in-session` and `acpx` pass; the other three are rejected with the
  standard message.
- The default engine is `in-session`, with no flag and with no `.claude/relay.json`.
- `pre` prints the command and the reply path, and refuses past the deadline.
- `post` records `failed:no-reply` for an absent reply file and for an empty one.
- `post` records `no-answer` for a reply that holds no verdict line.
- `post` prints `NODE_RETRY=1` for the two retried shapes, and does not for the three that
  are not retried.
- The acpx single call still runs, byte for byte.

Changed:

- `tests/unit/skill-structure/test_verify_loop.py`, class at line 1110: the consent
  assertions become conditional on acpx. The three named facts, the refusal contract, the
  rule name and the line `Do not write it to get past the check.` all stay, because the
  acpx path still needs every one of them.
- `tests/unit/skill-structure/test_plugin.py:891`: same change, same reason.

## Not doing

- No new tool for `leaf-worker` or `leaf-reader`. A leaf that can run any command is a
  wider change than this one, and nothing here needs it.
- No `session-tree` verify loop. `skills/orchestrating-session-trees/SKILL.md` already
  states that the verify loop migrates only after the implement path runs clean.
- No change to `run-claude-command.sh` or `run-claude-prompt.sh`.
- No change to the three terminal states, the verdict-to-label map, the round-1 reset, or
  the acpx session names.


## Correction — 2026-08-20, after the first live run

The first version of step 2 above said to invoke the block through the `Skill` tool and to
write back the whole reply. A live `in-session` run found that unexecutable, and the design
here now records the corrected shape.

Two things were wrong. The `Skill` tool takes a skill name, but only `simplify` holds a bare
command: `review` carries arguments, `check` adds a verdict contract under the command, and
`fix` holds no command at all. And a command started inside a turn returns its instructions,
not its result, so a node that wrote back what the tool returned wrote instruction text. For
`check` that is no verdict line at all, which `parse-verify-verdict.sh` reads as `no-answer` —
so every round would have ended `no-answer` and every run `unverified`, silently, on the engine
this spec makes the default.

The script layer needed no change. The two-call `pre`/`post` protocol, the four guards and the
records were all correct; only the node prompt that sits above them was wrong. That matches
where the risk was called out: the shipped PR said the node-prompt layer was prose the model
follows at runtime and was not covered by test, and named a live run as the way to confirm it.
`TestTheInSessionNodePromptIsExecutable` now pins the corrected contract and the reason.
