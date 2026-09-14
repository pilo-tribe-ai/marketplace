# engineering

A local plugin bundling Matt Pocock's engineering skills from
[mattpocock/skills](https://github.com/mattpocock/skills) (`skills/engineering/`).

**Upstream commit:** `3cca18b368ae95cdbdebbff572ccafa662551015` (2026-09-04)

## Skills

- **codebase-design** — shared vocabulary for deep modules: small interfaces, clean seams, testable through the interface
- **diagnosing-bugs** — disciplined diagnosis loop for hard bugs and performance regressions
- **domain-modeling** — build and sharpen the domain model, updating `CONTEXT.md` and ADRs inline
- **grill-with-docs** — grilling session that also builds the project's domain model
- **improve-codebase-architecture** — scan for deepening opportunities, report them as HTML, then grill the one you pick
- **prototype** — throwaway prototype that answers a design question, for state/logic or UI
- **research** — investigate a question against primary sources, as a background agent, and cite the findings
- **tdd** — red/green/refactor loop, one vertical slice at a time
- **to-spec** — turn the current conversation into a spec on the issue tracker
- **to-tickets** — break a plan or spec into tracer-bullet tickets that declare their blocking edges
- **triage** — issue triage state machine
- **wayfinder** — chart work too big for one session as decision tickets, resolved one at a time
- **zoom-out** — context-expansion guide (local only, see below)

## Deviations from upstream

The skill bodies are otherwise verbatim. Three changes are made on import:

1. **Namespaced cross-skill references.** The harness registers a plugin skill as
   `engineering:<name>`, so a bare name does not resolve. Every reference to a skill
   that ships in this plugin is rewritten, for example
   `Skill tool with "codebase-design"` → `Skill tool with "engineering:codebase-design"`.
2. **Dropped `agents/openai.yaml`.** Each upstream skill carries a Codex agent config.
   It has no effect in Claude Code.
3. **Kept `zoom-out`.** Upstream deleted it. The local copy stays, unchanged and frozen,
   because nothing replaced it.

## Omitted

- `setup-matt-pocock-skills` — a per-repo bootstrap flow specific to Matt's setup, not portable.
  Skills that reference `/setup-matt-pocock-skills` still name it; read that as "set the repo up
  by hand" (issue tracker, triage labels, domain doc layout).
- `grilling` — lives in the upstream `productivity/` bucket, not `engineering/`.
  `improve-codebase-architecture` calls it. That one reference does not resolve here.

## Re-syncing with upstream

There is no automatic tracking. To refresh:

```bash
git clone --depth 50 https://github.com/mattpocock/skills /tmp/skills-up
# copy skills/engineering/<skill>/ over plugins/engineering/skills/<skill>/
# re-apply the three deviations above, then bump the version in this plugin
```

Record the new upstream commit in this README and in `NOTICE`.

## Attribution

All skill content under `skills/` is © Matt Pocock, MIT-licensed. See `NOTICE`.
Upstream: https://github.com/mattpocock/skills
