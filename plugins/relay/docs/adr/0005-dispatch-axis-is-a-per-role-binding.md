---
status: accepted
date: 2026-07-16
---

# The engine/agent axis selects a family, not a pipeline mode

`--engine` and `--agent` are resolved once per run, but they do not fork the
pipeline. They select a *family*, and each role's actual mechanism is read from its
own binding at Workflow-generation time. A single `--engine acpx --agent codex` run
therefore splits: some roles go out-of-process while others stay in-session.

## Considered options

A pipeline-wide fork is simpler to reason about and was the original shape. It cannot
express the carve-outs that turn out to be mandatory. The three browser critics must
stay in-session under any codex agent because the codex models have no vision;
`server-runner` must stay in-session because a delegated server dies with its worker
and leaves a dead `BASE_URL`. Under a whole-pipeline fork each of those is a
correctness bug the user has no way to avoid except by not using the flag.

## Consequences

Per-axis resolution is layered — flag > `.claude/relay.json` pin > default — and
invariants are enforced loudly rather than coerced: `in-session` requires
`agent=claude`, and `smart-routing` refuses to combine with a literal worker agent. A
derived agent inherits the *source* of the engine that derived it, which is what
makes "ask only when the source is `default`" correct.

The cost is that "what did this run actually use?" is no longer answerable from the
command line alone — it depends on 24 binding rows. That is what `--retro`'s axis
comparison exists to reconstruct after the fact.
