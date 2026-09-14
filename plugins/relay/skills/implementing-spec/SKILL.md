---
name: implementing-spec
user-invocable: false
description: "Use to run one finalized design spec to a committed branch, headless — the adapter the apk plugin's build phase calls. Gates the spec, asks nothing, keeps the branch it finds, and delegates the whole pipeline to relay:running-implement-spine. Returns {status, pr_url?}."
---

# implementing-spec

The `apk` plugin's build phase calls this skill by its exact path,
`skills/implementing-spec/SKILL.md`, and by its exact name, `implementing-spec`.
`apk/bin/check-deps.sh` probes for that path on disk and blocks the whole `apk` run when
it is absent. `apk/tests/unit/test_cross_plugin_skill_names.py` pins the name. Do not
rename either.

This skill is an adapter, not a second pipeline. It holds no spine of its own. It reads
four inputs, gates one file, and calls `relay:running-implement-spine` — the same skill
`/relay:implement` calls.

## Inputs

`skill()` is not a Workflow primitive, so `apk` cannot call this skill directly from its
build lane. It dispatches `agent(prompt, {agentType: 'general-purpose', schema})` instead,
and the prompt tells that sub-agent to invoke this skill and relay what it returns. The
four inputs therefore arrive as **plain text lines in that prompt**, one per line, in
`key: value` form — not as an object:

```
spec_path: docs/superpowers/specs/2026-08-22-example-design.md
branch_hint: feature/RM-14-example
closes_issue: 42
worktree: /abs/path/to/repo/.worktrees/apk/billing
```

- `spec_path` — the path to a finalized design spec.
- `branch_hint` — a proposed branch name. It is usually stale. See Step 4.
- `closes_issue` (optional) — an issue number to close. The line is absent when the
  spec's frontmatter carries no `gh_issue`.
- `worktree` (optional) — the literal absolute path the caller believes this skill is
  running in. The line is absent when the caller supplies nothing.

## Behaviour, in order

1. Read `spec_path`, `branch_hint`, `closes_issue`, and `worktree` from the `key: value`
   lines in the calling text. The `closes_issue` and `worktree` lines can be absent. Never
   fail because an input did not arrive as a structured argument — no caller sends one.

1.5. Step 1.5 — the worktree mismatch guard, before the spec gate. When the `worktree`
   line is present, run `worktree-preflight.sh --resolve <value>` and compare its
   `RELAY_WT_TARGET` to this skill's own `git rev-parse --show-toplevel`, both
   canonicalized.
   - Equal — continue; print `RELAY_WT_ACTIVE=<target>`, and pass that literal absolute
     path as a new `worktree` key in the `inputs` block given to
     `relay:running-implement-spine` in Step 6. Never `export WORKTREE=…`.
   - Not equal, or the resolver reports `missing` — return and stop with:
     ```
     status: blocked
     reason: worktree-mismatch
       caller declared: /repo/.worktrees/apk/billing
       skill running in: /repo
     ```
   When the `worktree` line is absent, skip this step entirely — behave as today.
   This adapter still never creates, enters, or switches worktrees.

2. Gate the spec. The file at `spec_path` must exist and its frontmatter must carry
   `lifecycle_state: specified`. If the file is missing, or the state is any other
   value, return `status: blocked` with a `reason` field that names which check failed.
   Stop here. Do not call the spine.

3. Ask nothing. This skill declares no `AskUserQuestion` and never waits for an answer.
   It runs inside a general-purpose sub-agent dispatched by an autonomous Workflow, and
   that sub-agent has no user to answer — a skill that waited here would hang the run.
   Take the engine and the
   agent from the `.claude/relay.json` pin. If the repository has no pin, use the
   headless default: `engine=in-session`, `agent=claude`. Record which branch was
   taken as `axis_source`: `relay.json` when the pin supplied the values, `default`
   when it did not.

4. Make no worktree. `apk/skills/start/SKILL.md` already made one, at
   `.worktrees/apk/<scope>` on branch `apk/<scope>`, before it called this skill. Use
   the current branch as this skill finds it. Ignore `branch_hint` when the current
   branch is not the repository's default branch — in an `apk` run this is always the
   case, because `apk` checked out `apk/<scope>` and then sent the hint
   `feature/<roadmap_id>-<slug>`, a different string. The hint is therefore always
   stale in practice. Never rename a branch and never switch a branch on the hint.

5. Set `kind` to `feature`. Set `verify` to `true`.

6. Call `relay:running-implement-spine` with: `kind=feature`, `task` set to the spec's
   text, `spec_path`, the resolved `engine`, the resolved `agent`, `verify=true`,
   `rounds` set to `$RELAY_VERIFY_ROUNDS` when the environment supplies it and to `3`
   when it does not, the `axis_source` Step 3 recorded, `command=implementing-spec`,
   `closes_issue` (when present), and `worktree` (the literal path Step 1.5 printed as
   `RELAY_WT_ACTIVE`, when present).
   Pass `command=implementing-spec`, never `implement`. The spine records that value as
   the run's command, so a run started here reads back as an `apk`-driven run and not as
   a `/relay:implement` run.
   This skill never runs `commands/implement.md`'s own Step 0 or Step 1 — it exports
   no `$RELAY_ENGINE` and takes no `session-tree` branch — so `relay:running-implement-spine`
   must read `engine` and `axis_source` only from these inputs, never from that
   command's environment.

7. Return `{status, pr_url?}`. `pr_url` stays in the returned object for compatibility
   and is **always absent** — this design does not add pull request creation to relay.
   The run stops on a branch that holds a commit. No component in this pipeline opens
   the pull request; a person must open it. The `closes_issue` value goes into the
   commit body as `Closes #<n>`, so that later pull request keeps the link.

## Status mapping

| Condition | status |
|---|---|
| The spec is missing, or its `lifecycle_state` is not `specified`. | `blocked` |
| The spine finished, its `commit` field holds a value, and the verify loop reported `clean`. | `ok` |
| The spine ran and returned `error`, or the verify loop reported `findings` or `unverified`. | `error` |

Never return `ok` for a run that made no commit. A run without a commit is not a clean
run, no matter what the spine reported. `apk` reads only `result.status !== 'ok'`; every
value other than `ok` reads to `apk` as a failure, so `blocked` and `error` are both
failures from its side, distinguished only by the `reason` field a human reads later.
