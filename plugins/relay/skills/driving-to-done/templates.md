# driving-to-done — state-file templates

Copy-and-fill skeletons for the durable state files the loop runs on (see `SKILL.md` → "Set up the
workspace"). Replace `<…>` placeholders. Keep them under a state dir, e.g. `.<process>-prep/`.

## `loop-state.md` (the resumability anchor — **overwrite** as it changes, it is a snapshot not a log)

```markdown
# Loop State (resumability anchor — overwrite as it changes)
_Last updated: <date>, after <last event>._

## Orchestration model
- MAIN owns only <the one long-lived process> (background task <id>). All heavy work → subagents.
- Task spine: #1 <…> (DONE) ; #2 <…> (in progress) ; … ; #N closeout (blocked by prior).

## Done criterion
- <the single binary condition>. clean_streak = <k>/<N>.

## Environment
- <branch / servers / endpoints / flags>. RESET SEED = <command>.

## Per-step status
- Step 0 … PASS/FAIL/UNPROVEN (evidence).
- …

## Selectors / IDs for automation
- <testids, op names, routes the subagents need>

## Next actions
1. …

## Position
- clean_streak=<k>. <what remains>.
```

## `decision-log.md` entry (**append-only**, newest at the bottom)

```markdown
## <UTC timestamp> — <short title>
- Context: <what triggered it>
- Options: <choices considered>
- Decision: <what was chosen>
- Why: <tied to oracle / constraints / ADR>
- Effect: <files/steps touched, child agent used>
```

## `blocked-items.md` entry (mark RESOLVED with a SHA rather than deleting)

```markdown
## Step <n> — <title>   [OPEN | RESOLVED <sha> | KNOWN LIMITATION]
- Symptom: <what fails the pass condition>
- Tried: <the capped cycles>
- Root cause (best guess): <…>
- Fallback: <what the operator does instead of the live path>
- Unblock path (future): <what would make it real>
```

## Subagent return envelope (the compact contract — adapt the keys to the step)

```
PHASE_A:  <preconditions / gates, with real numbers>
SEED:     <reset done + pristine-verified, with the queries that prove it>
STEP<N>:  PASS|FAIL <one line of real evidence — a 200, a count, an artifact path>
RESULT:   ALL_CLEAN | FAILED@STEP<N>
EVIDENCE: <absolute paths>
NOTES:    <anything the orchestrator must know, or "none">
```
