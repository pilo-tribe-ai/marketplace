---
name: verifying-until-clean
user-invocable: false
description: "Use to repeat simplify, code-review, and /verify over the current branch until the branch verifies clean or the round cap is spent — the caller passes the engine (`in-session` starts each command in this session with SlashCommand; `acpx` runs each step as a headless child turn and asks for agreement first), each round maps the /verify verdict onto the closed three-label set (`clean`, `findings`, `no-answer`), and the run ends in one of three terminal states: clean, findings, or unverified."
---

# verifying-until-clean

This skill drives one round, reads the verdict `/verify` reports, and decides whether to
stop or run another round. `/relay:verify` calls it, and so does the `--verify` tail of
`/relay:implement`. Both callers get the same nodes, the same session names, and the same state
directory, because the two paths must stay exactly equivalent. The caller passes one
engine, and the engine picks the node shape only.

## The round

Each round runs four steps, in this fixed order:

1. `/simplify` — reduce and clean up the code the branch already holds.
2. `/code-review medium --fix` — find and fix review-level problems.
3. `/verify` — check the branch and report a verdict.
4. A fix step — runs only when `/verify` reported a problem.

## The engine picks how a step reaches its command

The caller passes one engine. Two carry a substrate for this loop:

| engine | how a step reaches its command | asks for agreement |
|---|---|---|
| `in-session` | the node starts the command with `SlashCommand`, then does the work | no |
| `acpx` | the node runs one turn of a headless child Claude session | yes |

The caller rejects every other engine, and owns the default. `/relay:verify` defaults to
`acpx`, so the agreement step below runs on the common path.

Earlier versions of this skill stated that Claude cannot start a slash command from inside
its own model turn. That is no longer true: the harness holds a `SlashCommand` tool, and
relay 4.30.0 already relies on it.

The engine changes the node shape and nothing else. It does not rename a node, a session or
the state directory, and it does not change the round, the verdict map, or the three terminal
states.

## Step 0 — get agreement for the approval gate

This step runs only when the engine is `acpx`. Under `in-session` there is no child
process, no `--approve-all` and nothing unattended, so the rule below has nothing to match.
Ask nothing, and generate the nodes. A question that names a danger which is not present is
not consent; it is ceremony, and the next editor deletes it.

Under `acpx`, every step of this loop opens a child Claude session with `acpx --approve-all`.
The child changes files, runs commands, and commits. No person answers a prompt while it
works. The child runs on the host machine, and no sandbox holds it.

The caller must ask the user to agree to this before it generates any node. Use
`AskUserQuestion`. The question must name these three things:

1. The loop starts headless Claude sessions with the approval gate off (`acpx --approve-all`).
2. These sessions change files, run commands, and commit, and no person approves each step.
3. The agreement applies to every round of this run, not only to the first step.

When the user agrees, generate the nodes. When the user does not agree, generate no node, and
report `RELAY_VERIFY_RESULT=unverified`. A run without agreement verified nothing, so it must
not report a clean result.

### Why this question is necessary

Claude Code has an auto-mode safety rule with the name `Create Unsafe Agents`. It stops an
agent that starts a coding-agent loop with the approvals off and no sandbox. The rule is a
soft block: it clears when the user names the agent that runs with approvals off. A bare
slash command names the task, not the dangerous step. `--engine acpx` names the substrate,
not the approvals, so the question still runs.

Without this question the rule stops single nodes in the middle of a run. In a live run it
stopped two nodes of thirteen, and the nodes after them found no state to read.

Write the question to state what the loop does. Do not write it to get past the check. If the
user says no, the answer is no, and the loop does not run.

## Generating the loop nodes

The loop has exactly one identity. This skill takes the engine and nothing else, and no
caller may rename a node, a session, or the state directory. The nodes below are `agent()`
wrapper nodes appended to the caller's single Workflow — this skill never calls the
`Workflow` tool itself, so exactly one Workflow still runs.

Generate one `verify-init` node first, then `R` round groups, where `R` is
`$RELAY_VERIFY_ROUNDS`, then one terminal report node after the last round, named
`verify-loop-report`.
These are pinned-tier wrapper nodes deliberately exempt from `resolve-tier.sh --all`.
Set `phase: 'Verify'`, `opts.model: 'sonnet'`, `opts.effort: 'low'`
on every node. No new tier-inventory row belongs to either engine.

Under `acpx` every node is a Bash wrapper leaf that runs one helper call and reads its
output. The child Claude session that each helper opens runs at its own defaults, so this
wrapper tier never sets the tier of the real work.

Under `in-session` every round node runs two Bash calls and, between them, starts the command
it was given. It needs `agentType: 'general-purpose'` to start that command. The wrapper tier
above is the tier of the node that reads the lines, not of the command it starts.

`scripts/run-claude-command.sh` is used unchanged by the acpx engine: its contract is locked
by `tests/unit/skill-structure/test_relay_implement_polish.py`, and every acpx wrapper leaf
depends on its slash-only guard, which keeps a leaf from sending prose where a slash command
is required. The in-session engine calls neither helper.

`verify-init` runs first, before round 1. It starts no child agent in either engine, so it
uses no helper, opens no session, and takes no `--phase`.

Each round `N` then holds four nodes, in this fixed order. Every node runs
`scripts/verify-loop-node.sh` with the kind in the first column. The helper and session
columns describe the `acpx` engine: they name the script that the node body calls in turn,
and the session that script opens. Under `in-session` the node invokes the prompt column
itself, and no helper runs and no session opens. Every other column is the same in both
engines.

| node | kind | helper | prompt | session |
|---|---|---|---|---|
| `verify-simplify-rN` | `simplify` | `scripts/run-claude-command.sh` | `"/simplify"` | `relay-verify-simplify-r<N>` |
| `verify-review-rN` | `review` | `scripts/run-claude-command.sh` | `"/code-review medium --fix"` | `relay-verify-review-r<N>` |
| `verify-check-rN` | `check` | `scripts/run-claude-command.sh` | `/verify` and the verdict contract below | `relay-verify-check-r<N>` |
| `verify-fix-rN` | `fix` | `scripts/run-claude-prompt.sh` | free-form, built from the round's report | `relay-verify-fix-r<N>` |

Session names are literals built from the round index, which is known when the script text is
written — `relay-verify-simplify-r1`, `relay-verify-review-r1`, `relay-verify-check-r1`,
`relay-verify-fix-r1`, and so on for every round. acpx scopes a session by
`(agentCommand, absolute cwd, name)`, so embed no run id: `Date.now()` and `Math.random()` throw
inside a Workflow script, and the harness `runId` arrives only in the `Workflow` tool result,
after the script text has already been submitted.

### The node command

Under `acpx`, every node runs exactly one command. The node bodies live in
`scripts/verify-loop-node.sh`, never inline in the generated Workflow script:

```bash
bash "<PLUGIN>/scripts/verify-loop-node.sh" <kind> "<WORKTREE>" [<round>] <rounds>
```

`<kind>` is `init`, `simplify`, `review`, `check`, `fix`, or `report`. `<WORKTREE>` is an
absolute path, written into the script text as a literal. Read it from the
`RELAY_WT_WORKTREE_ROOT` line that `worktree-preflight.sh --classify` prints. A node's
working directory is not guaranteed to be the worktree, so this path is always an
argument, and it is never derived from the node's own directory.

The script derives the state root with `rev-parse --absolute-git-dir`, and it holds
`STATE_ROOT` and `ROUND_DIR` internally. The sections below state what the script does.
They are the specification; `scripts/verify-loop-node.sh` is the implementation, and
`tests/unit/skill-structure/test_verify_loop_node.py` runs it.

#### The in-session node runs the same script in two calls

Bash cannot make a tool call, so an in-session node cannot reach its command from inside
the script. The script therefore splits the step, and keeps every decision:

```bash
bash "<PLUGIN>/scripts/verify-loop-node.sh" --phase pre  <kind> "<WORKTREE>" <round> <rounds>
bash "<PLUGIN>/scripts/verify-loop-node.sh" --phase post <kind> "<WORKTREE>" <round> <rounds>
```

`init` and `report` start no child in either engine, so they take no `--phase`. Passing one
is an error, not a value that is quietly ignored.

Set `agentType: 'general-purpose'` on an in-session node. That agent type holds the full tool
set, so it holds `SlashCommand`. `relay:leaf-worker` and `relay:leaf-reader` do not, and this loop does not change them:
a leaf that can run any command is a wider change than this loop needs.

The block between the two markers is a prompt to carry out. It is not a name to pass to a
tool. Only `simplify` holds a bare command: `review` carries arguments, `check` adds a verdict
contract under the command, and `fix` holds no command at all. A node that passed the block to
a tool as a name would fail on three of the four kinds.

A started command returns its instructions, not its result. The work then happens in the
node's own turns. So the step is not done when the tool returns; it is done when the work is
done.

Write three steps into the node prompt, in this order:

1. Run the `pre` call. It prints `PRE_REPLY_FILE=<path>`, then the block between
   `PRE_COMMAND_BEGIN` and `PRE_COMMAND_END`. When it prints `NODE_STATUS=skipped` or any
   other terminal status, return that line verbatim and stop. Do nothing else.
2. Carry out the block. When it starts with a slash command, start that command through the
   `SlashCommand` tool, then do what the command asks for. Then write your own closing answer
   to the file that `PRE_REPLY_FILE` named: what you did, and — for `check` — the verdict line
   the block asks for. Write that answer only. Do not add a fence.
3. Run the `post` call. When it prints `NODE_RETRY=1`, do step 2 once more against the same
   path, then run `post` again. Return the final `NODE_STATUS` line verbatim.

The sequence has no entry condition by design. The script enforces re-entry safety, not the
node: a step that already holds its claim answers `NODE_STATUS=already-done` and changes
nothing. The retry decision stays in the script too; the node reads one line and holds no
state. The reply is the same artifact an acpx child leaves as its final text, which is what
lets one verdict map read both engines.

#### A claimed run is weaker evidence than a started run

Under `acpx` the script starts the child, so a written record proves the step ran. In-session
the node invokes the command and hands the reply back, so a record is a claim. That gap is the
real cost of this engine, and it is this loop's own named failure mode: run `wf_8ad76eec-5ac`
reported `ran` for a step that had run nothing.

Five guards answer it. Every one is mechanical:

1. `pre` deletes the reply file, so a file present at `post` time was written after `pre` ran.
2. `pre` writes a marker only on the path where a command must be invoked. `post` refuses
   without it and reports `failed:no-pre`, so a `post` that follows a skipped `pre` cannot
   overwrite the skip with a failure.
3. An absent or empty reply is `failed:no-reply`. It is not a skip, and it is never a pass.
   The `check` step does not retry it either: no reply is the absence of an attempt, not a
   verdict of an unusable shape, and one record must not stand for both.
4. `post` builds the output fence itself, around text it treats as opaque. The node never
   writes the fence, so the node cannot forge one.
5. One terminal record line per round and step. Each step claims its record key with
   `mkdir`, which either makes the directory or fails. A caller that finds the claim held
   is a re-entry, not a new attempt: it prints `NODE_STATUS=already-done`, keeps the reply
   on disk, writes no second record line, and does not move the loop state. The `check`
   step takes its claim only after the retry decision, so the documented retry cycle still
   records a verdict.

`simplify`, `review` and `fix` are measured against git, not against the reply: `commit_step`
already reports `no changes` when the tree did not move, and the fix-noop counter already
reads that.

State the limit plainly. These guards stop a fabricated pass from being recorded. They do not
make a claimed run equal to a started run. A node that invents a verdict line still yields a
clean result, and only `--engine acpx` removes that possibility. One more gap is accepted: a
duplicate `pre` that arrives before the first `post` still deletes the reply, because no claim
exists yet, and the next `post` records `failed:no-reply` and ends the run `unverified`. That
is a safe failure, not a false clean. Do not add locking to chase it.

#### The node deadline belongs to acpx

`RELAY_VERIFY_NODE_TIMEOUT` guards one thing: a child that outlives the node's single Bash
call and is killed before the script writes its record. In-session the long step is a model
turn, and the two Bash calls take milliseconds, so the deadline does not apply and
`failed:timeout` never appears on an in-session round.

Do not try to carry the deadline across the two calls. Each call is a separate process, so the
clock restarts; and by the time `post` runs, the work is already done, so a `post` that refused
an expired deadline would discard work that really happened.

#### What a node returns

The script prints `NODE_STATUS=` as the last line of every exit path, and prints it once.
A node returns that line verbatim. It does not summarise it, shorten it, or replace
any field with a value of its own.

If the command printed no such line, the node returns exactly:

```
NODE_STATUS=absent
```

and nothing else. A backgrounded command, a command still running, and a command that was
killed all end here. None of them is `ran`.

The reason is in a real run. When the status line sat above 25 to 40 lines of child output,
the nodes in run `wf_8ad76eec-5ac` summarised the block instead of relaying the line: several
returned invented `detail` values, one of them the literal word `placeholder`, and two
reported `ran` for a step that had run nothing. That is the loop's own failure mode, living
one layer above the records that were built to prevent it.

#### Give the node the longest Bash timeout there is

This applies to `acpx` nodes, where the whole step is one Bash call. An in-session node runs
two short Bash calls, so the default is enough.

Every acpx node prompt must tell the node to run the command with the Bash tool's maximum
timeout, `600000` milliseconds. Write that instruction into the prompt. Do not leave it
to the default. The default is 120000 milliseconds, and no step of a round finishes in two
minutes: a child session runs `/simplify`, `/code-review medium --fix`, or `/verify` over a
whole branch. At the default, the Bash call gives up, the child is killed when the run
ends, and the script never writes the record. One live run lost 9 of its 12 steps this
way. The loop still reported `unverified`, because a step with no record is counted as
missing, but the report named no cause.

The script holds a matching budget of its own, `RELAY_VERIFY_NODE_TIMEOUT`, which defaults
to 540 seconds. The budget is a deadline for the whole node, not a limit for each child.
The script reads the clock once when it starts, and every child it runs gets only the time
that is left, so the script's own timeout fires before the caller's ceiling and the node
writes `failed:timeout` instead of being killed without a word. `0` turns the budget off. A
value that is not a whole number of seconds falls back to 540.

A per-child limit broke that promise: the `check` node's retry could run two children of
540 seconds against a ceiling of 600. Run `wf_918a4deb-aba` took that path in all three
rounds, and every round reported `CHECK=missing`.

A step that ends this way records `<KEY>=failed:timeout` and sets the run `unverified`.
It is not a skip, and it is never a pass. The `check` node does not retry after one: a
retry that would start after the deadline reports `failed:timeout` at once, without
spending a child. A `fix` node that times out commits whatever landed on disk first, so
the next round reads the tree that really exists.

#### Why the node bodies live in a script

Three faults, and the move removes all three.

Inline bash in a generated script cannot be tested. The shape this skill documents and
the shape a run executes could differ, and nothing would find it.

Each inline body was restated in full in every node prompt: about 35000 tokens for each
node, and about 474000 tokens in one live run, on wrappers that did no work.

A Claude Code session that is isolated in a git worktree refuses a Bash command that it
cannot verify as safe. The command does not need to contain `git`: a command that only
sets a variable from a command substitution is refused. Every inline body was refused
this way, and one live run lost 13 of its 14 nodes. A short command is not refused.

The L3 Step 0 blocks took the same remedy: `scripts/l3-preflight.sh`.

Be honest about the last one. A static check reads the command a node runs, and it does
not read this script, so the move puts the `git` calls where that check does not see them.
The calls did not change, and every one is scoped with `-C` to the worktree the session
already owns. Do not use this file as a place to put work that you would not put in a node.

### The `verify-init` node

One node runs before round 1. Its name is `verify-init`. It clears the state of the run before
it, and it writes the first state line:

```bash
mkdir -p "$STATE_ROOT"
rm -rf "$STATE_ROOT"/round-*
printf 'LABEL= ROUND=1 NOOPS=0 EXIT=continue\n' > "$STATE_ROOT/state"
```

This node starts no child agent. It calls neither helper script, and it runs no `acpx` command.
That is the point of the node, and it is the reason the reset is here and not in the simplify
leaf of round 1.

Why the reset is its own node. The reset used to run inside the round-1 simplify leaf. Under
acpx that leaf also starts a child Claude session with the approvals off, so the auto-mode
safety rule in Step 0 can stop it. A stopped node writes nothing. The state file then does not exist, every
later node reads no `EXIT`, and all of them record themselves as skipped. One stopped node
therefore ended a whole thirteen-node run in a live case. The reset now runs in a node that the
rule cannot match, so a stopped simplify leaf costs one step and not the run.

The `rm -rf` names the round directories with a literal pattern and does not delete
`$STATE_ROOT` itself, which also holds files this loop does not own.

Without this reset, a second loop run in the same worktree reads the first run's state file.
`EXIT` already holds a terminal value there, so every node of the second run records itself
`skipped` and the run does nothing. The report node has the matching fault: it reads every
`record` under `$STATE_ROOT`, so a short second run would report rounds that belong to the
first run. Both faults are silent — the run looks finished and reports a stale result.

The reset makes every run independent of every run before it. Do not move it into a later
node: a reset that runs after round 1 destroys the evidence of the round that just ran.

### A missing state file is not a skip

Each node reads `EXIT` from `$STATE_ROOT/state`. Two different conditions must not look the
same:

- The file exists and `EXIT` holds a terminal value. The round already ended. The node records
  itself as `skipped`.
- The file does not exist. `verify-init` did not run, so the loop never started. The node
  records `failed:no-state` and prints `NODE_STATUS=failed:no-state`.

```bash
if [ ! -f "$STATE_ROOT/state" ]; then
  echo "<KEY>=failed:no-state" >> "$ROUND_DIR/record"
  echo "NODE_STATUS=failed:no-state reason=verify-init-did-not-run"
  exit 0
fi
```

A node that records `skipped` states that the loop decided to stop. A node that finds no state
file states that the loop never began. The report reads the two differently, so neither one can
hide the other.

State lives under the git directory, not in the working tree. Git never tracks anything there,
so `git add -A` cannot sweep the run's own logs into a commit, and `git status --short` stays
honest. A scratch directory inside the working tree would make every round look as if it
changed files, which would silently defeat the fix-noop check below.

### Reading a helper result

```bash
out="$("${CLAUDE_PLUGIN_ROOT}/scripts/run-claude-command.sh" "$WORKTREE" "relay-verify-check-r<N>" "$check_command")"
rc=$?
printf '%s\n' "$out" > "$ROUND_DIR/check.out"
```

`$check_command` is the text in **The verdict contract** below.

`$?` from the command substitution is the authoritative rc. The child's own reply can itself
contain the text `POLISH_CMD_RC=0`, so a first-match grep would read the child's text as the
helper's status; a leaf that re-reads a saved file takes the last line matching
`^POLISH_CMD_RC=`. A non-zero rc fails the leaf: 64, 66, and 69 all mean the step did not
run, and the round records `no-answer`.

### The verdict contract

`/verify` is not relay's command. It resolves to whatever the repository defines. The
built-in command prints a verdict line, but a repository that holds its own `verify` skill
can prescribe no report format at all. The loop must not assume the report format of a
command it does not own.

So the check node sends the contract with the command. The command text is:

```text
/verify

End your reply with a verdict line. Use this shape:

**Verdict:** PASS | FAIL | BLOCKED | SKIP

Write one word in the place of the four words: PASS, FAIL, BLOCKED, or SKIP. Do not copy the four words. Put the verdict line last, and write nothing after it.
```

The text starts with `/`, so the slash-only guard in `scripts/run-claude-command.sh` accepts
it.

The shape is the enum template on purpose, and the template line is also the parser trap.
The same literal line lives in the `/verify` prompt, in this skill, in the command doc, and
in the tests. A reader that takes the first line naming "Verdict" reads the template itself
as the answer. So the parser accepts only a line carrying exactly one verdict token, and
takes the last such line, because the report is the child's final message. A child that
copies the contract into its reply writes four tokens on one line, and the one-token rule
in `scripts/parse-verify-verdict.sh` rejects it. An example that holds one token, such as
`**Verdict:** PASS`, would be read as a real pass when a child copies it. That is the one
error this loop must never make. Keep the verdict-to-label map inside
`scripts/parse-verify-verdict.sh` and nowhere else, so every caller reads the same map.

Run `wf_918a4deb-aba` shows what the assumption costs. The child answered
`## Verify result: productivity v0.7.0 — PASS`. That heading holds no verdict token, so the
parser read `no-answer`, the round retried, and all three rounds reported `unverified`.

### Mapping the verdict to a label

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/parse-verify-verdict.sh" "$ROUND_DIR/check.out" > "$ROUND_DIR/verdict"
```

Read `VERIFY_VERDICT` and `VERIFY_LABEL` from that file. The verdict table:

| Verdict | Label | Route |
|---|---|---|
| `PASS` | `clean` | Exit the loop. |
| `FAIL` | `findings` | Run the fix step, then start the next round. |
| `BLOCKED` | `no-answer` | Retry the verify step once in the same round, using the same session name, then let the second result stand. |
| `SKIP` | `no-answer` | Exit as explicitly unverified. Do not retry — a second run sees the same empty diff. |
| no reply, or no output fence | `no-answer` | Same treatment as `BLOCKED`. A second child can still answer. |
| a fenced reply that holds no verdict line | `no-answer` | Do not retry. Record `REASON=no-verdict-line`. The same command in the same repository answers in the same format, so a second child can only spend the budget. |

A `PASS` normally carries findings, because the built-in `/verify` prompt asks for a line per
probe even when the probe held. The findings count is never read as an exit predicate — only the
verdict decides.

A `SKIP` verdict is not a pass. A live run on a clean tree returned `Verdict: SKIP — no diff to
verify`, which means there was nothing to verify.

A `BLOCKED` verdict is not a pass. It means the verification could not be performed.

The parser tells the two `no-answer` shapes apart on stderr. It prints
`VERIFY_REASON=no-output-fence` when it finds no usable fenced region, and
`VERIFY_REASON=no-verdict-line` when the region is there but holds no verdict line. Its two
stdout lines and its exit code do not change. The check node reads that line, writes it into
the record as `REASON=`, and retries only the first shape. When it retries, it keeps the
first reply as `check-1.out`, so a silent second child cannot erase the evidence of the
first.

### Round state

`$STATE_ROOT/state` holds one line, rewritten at the end of each round:

    LABEL=<clean|findings|no-answer> ROUND=<N> NOOPS=<n> EXIT=<continue|clean|findings|unverified>

`$ROUND_DIR/record` holds one `KEY=value` line per node: `SIMPLIFY`, `SIMPLIFY_COMMIT`,
`REVIEW`, `REVIEW_COMMIT`, `CHECK`, `VERDICT`, `LABEL`, `REASON`, `RETRIED`, `FIX`,
`FIX_TRUNCATED`, `FIX_COMMIT`. Node values are `ran`, `skipped`, `failed:<rc>`, or
`failed:no-state`; commit values are a sha, `no changes`, or `commit-failed`; `FIX` may also
be `fix-noop`.

`verify-init` writes this file. Every other node reads it. When `EXIT` is anything but
`continue`, the node records itself as `skipped`, never as passed. When the file is absent,
the node records `failed:no-state` instead, because a missing file means the loop never
started.

### The fix leaf

Runs only when the round's label is `findings`. Build one prompt in a shell variable from the
fenced body of `check.out`, truncated to 16000 characters. When truncation happens, append one
line saying the report was truncated, and set `FIX_TRUNCATED=1` in the record, so a partial
report stays visible rather than silent. Append one instruction block: fix the problems this
report names; change the code, not the report; keep the existing tests as they are. Then call:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/run-claude-prompt.sh" "$WORKTREE" "relay-verify-fix-r<N>" "$prompt"
```

After the fix turn, read `git -C "$WORKTREE" status --short` and the commit result. A fix that
produced no change is recorded as `FIX=fix-noop`, and increments `NOOPS`. A fix that committed
resets `NOOPS` to 0. Two consecutive `fix-noop` rounds mean `NOOPS` reaches 2: when it does, set
`EXIT=findings` and stop, rather than burning the remaining cap on rounds that cannot move.

### Commits

After each node's turn, inspect `git -C "$WORKTREE" status --short`. When it is non-empty,
commit all changes before the next node runs. Derive `<scope>` as the dominant conventional-commit scope on the branch, most recent wins on ties, omitted when none is derivable. The
simplify commit message is `refactor(<scope>): simplify implementation`; the review commit
message is `fix(<scope>): apply code-review findings`; the fix commit message is
`fix(<scope>): fix problems named by /verify`. When no scope is derivable, omit it and use
`refactor: simplify implementation` or `fix: apply code-review findings`.

The scope derivation and the commit live in one script, `scripts/verify-commit-scope.sh`,
which `commit_step` in `scripts/verify-loop-node.sh` calls with the worktree and the step
name. `tests/unit/skill-structure/test_verify_commit_scope.py` runs it:

```bash
commit_sha="$(bash "<PLUGIN>/scripts/verify-commit-scope.sh" "$WORKTREE" "$loop_step")"
```

`loop_step` is `simplify`, `review`, or `fix`. The script prints one line, which the node
writes into the record as the step's `_COMMIT` value: the new sha, `no changes` when the tree
did not move, or `commit-failed` when the commit exited non-zero. A failed commit is never
recorded as a clean commit. `RELAY_BASE_REF` overrides the base of the scope scan; without it
the script uses the merge-base with the tracked default branch, and falls back to the root
commit.

### The report node

One node after the last round. It reads every `record` and the `state` line, prints one summary
line per round naming each node's recorded value, and prints the result line last.

A node that the safety rule in Step 0 stopped never runs, so it writes no line into the round
`record`. The report must print `missing` for every key it expects and does not find, and it
must count those keys. A key that is simply absent from the printout reads as a node that did
not exist, and the reader then counts a short round as a complete one. Print the count on its
own line as `RELAY_VERIFY_MISSING=<n>`, before the result line. `RELAY_VERIFY_FAILED=<n>` is
printed on its own line right after it, also before the result line.

`missing` is never read as a pass, and neither is a bad value. State the rule as a gate,
because a rule that only says what `missing` is not gets satisfied by never reading it at all:
a run that holds any missing key cannot print `clean`. The same gate also blocks a key
whose value is not an approved success value. The approved values are `ran`, `skipped`, and,
for the `FIX` key only, `fix-noop`. This is a positive allow-list, not a list of bad values to
watch for: a value the script has not yet invented is blocked too, the same as a known failure
value. It never turns a `findings` result into `clean` either.

The gate also counts lines, not only values. Under a correct writer there is exactly one
terminal line per key per round. Two or more lines for one key mean the step was entered
more than once, so the record cannot say which value is the truth. The report prints
`<KEY>=conflict:<value>/<value>` and counts it as a failed step. It never keeps the last
write as the answer.

When a clean label is blocked this way, print a reason line before the result line. A missing
step prints `RELAY_VERIFY_REASON=incomplete-round steps=<n>`. A step that recorded a value
outside the approved set prints `RELAY_VERIFY_REASON=failed-step steps=<n>`. When both causes
fire in the same run, one line prints both, space-joined, `incomplete-round` first. Exactly one
reason line is ever printed, so a bare `unverified` under a passing verdict never reads as a
loop that broke for no reason.

Before 4.33.0 this counter was computed, printed, and then dropped. Run `wf_6f6f4d1a-4d3`
reported `RELAY_VERIFY_RESULT=clean` next to `RELAY_VERIFY_MISSING=1`: its review node ended
its turn between `pre` and `post`, so `/code-review medium --fix` never ran, and the branch was
still reported verified. The report printed the count on the line above and did not read it.

The loop ends in exactly one of three terminal states, `RELAY_VERIFY_RESULT=clean|findings|unverified`:

    RELAY_VERIFY_RESULT=clean
    RELAY_VERIFY_RESULT=findings
    RELAY_VERIFY_RESULT=unverified

`clean` is printed only when the last recorded label is `clean` and every round that
started recorded every one of its four steps and every one of those records holds an
approved success value. When the cap was spent with `EXIT=continue`, map the last label:
`findings` → the run still carries findings; `no-answer` → the run is explicitly unverified.
Never report either of those two as clean. When the last verdict was `SKIP`, the report says
plainly that there was nothing to verify, so a user reads it as an honest empty-diff result
rather than a failure.

## What contains the child

This section describes the `acpx` engine, which is the only one that starts a child. The
`in-session` engine runs every step under this session's own permission mode, exactly as any
other relay in-session leaf does, and it turns no approval gate off.

Each helper runs the child with `--approve-all`: the child edits files and runs commands without
asking, because nobody is present to answer a prompt and three of the four steps exist to
change code. `--cwd "$worktree"` is positional containment, not a sandbox: it decides where the
child starts, and nothing stops the child writing an absolute path or running `git -C` against
another checkout. Nothing here is a security boundary. Do not add steps to this loop that touch
credentials, publish anything, or work outside the worktree on the assumption that `--cwd`
stops them.

Step 0 tells the user this same fact in one question, before an acpx run starts. This section
states it for the person who edits the loop. The question states it for the person who owns the
branch. Neither one replaces the other.

## Evidence rules

Each round is a chain of turns run without a human present. Every step in that
chain must record what actually happened, never a guess. The rules above state this at
each point of use; two of them are stated here because they hold across every step:

- A step that found no state file is recorded as `failed:no-state`, never as
  skipped. The first tells the reader that the loop never started; the second
  tells the reader that the loop chose to stop. A step that the safety rule
  stopped writes no line at all, and the report prints that key as `missing`.
- A round node's returned text is narration, never evidence. The verdict is read
  only from `verify-loop-report`, whose every value comes from the `record` and `state`
  files on disk. A node's return is one model's account of a command; the records are
  what the command did. Where the two disagree, the records are right. Build the run's
  result from the report node's output alone, and never from a round node's return.

## Ownership of the shape

This skill realizes the `loop-until-clean` L1 shape. `skills/improve-loop/SKILL.md`
owns that shape and carries its `relay-vocab` block. This skill carries no vocab
block of its own, on purpose: two skills declaring the same L1 shape would make the
block stop identifying which one actually owns the pattern. Read the absence as
deliberate, not as an omission.
