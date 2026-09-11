---
name: scaffolding-okf-wikis
description: Scaffolds an OKF v0.2 knowledge wiki into the repository this is invoked in -- a container directory (docs/wiki/ by default) holding the AGENTS.md schema, three deterministic checker scripts, a vendored pytest suite, and an empty five-type bundle, then verifies all four gates pass on the empty bundle before declaring done. Use for "/wiki:setup", "set up a wiki in this repo", "scaffold an OKF wiki", or "bootstrap a knowledge wiki".
argument-hint: "[container path]"
allowed-tools: Bash, Read, Grep, Glob, Write, Edit, AskUserQuestion
---

# scaffolding-okf-wikis

Stand up a knowledge wiki inside the repository you are invoked in. This writes files into the
**target repo**, never into the plugin. It never runs `/wiki:ingest` -- setup ends green and
empty.

## Step 0 -- resolve the repository root

```bash
git rev-parse --show-toplevel
```

If this fails, stop: "This is not a git repository. `/wiki:setup` needs one, because the vendored
test suite finds the repository root by walking up to `.git`." A git repo is a hard requirement,
not an inference -- there is no fallback.

## Step 1 -- detect prior state

```bash
test -f .claude/wiki.json && cat .claude/wiki.json
```

Read the container from `.claude/wiki.json` if it exists, then probe it:

```bash
test -d "$CONTAINER"
test -d "${CONTAINER}bundle"
```

Five cases:

1. **`.claude/wiki.json` exists and `${CONTAINER}bundle/` exists** -- a wiki is already set up.
   Report the container and stop. Point at `/wiki:ingest`; do not scaffold again.
2. **`.claude/wiki.json` exists but the container is gone** -- report the broken pointer (the
   file says one path, the filesystem holds nothing there) and ask (AskUserQuestion): re-scaffold
   at the recorded container, or abort.
3. **No `.claude/wiki.json`, but the container holds a non-empty `bundle/`** -- someone built a
   wiki-shaped tree by hand or from elsewhere. Ask: **adopt** (write `.claude/wiki.json` only,
   via `scaffold.py --adopt`) or abort. If they adopt, say plainly: adopt does not vendor the
   scripts or tests, so the four gates in Step 6 may fail, and the receipt will say so rather than
   claim success.
4. **The container exists but has no `bundle/`** -- offer to scaffold into it. `scaffold.py`
   itself refuses if any single manifest file already exists, so this is safe to attempt; report
   its refusal verbatim if it happens.
5. **Nothing exists** -- fresh scaffold. The common case.

## Step 2 -- infer every value, with a stated fallback for each

| Value | Primary source | Fallback |
|---|---|---|
| `container` | `$ARGUMENTS` if given a path; else `docs/wiki/` when `docs/` exists | `wiki/` |
| `subject` | README.md's first `#` heading and lead paragraph | CLAUDE.md's opening description, else the repo basename |
| `repo` | `basename $(git rev-parse --show-toplevel)`, or `gh repo view --json nameWithOwner -q .nameWithOwner` if a GitHub remote exists | the directory basename |
| `human-actor` | `human:<slug of git config user.name>` (lowercase, spaces to hyphens) | `human:owner` |
| `agent-actor` | `claude-code/<model running this session, lowercased>` | `claude-code/agent` |
| `today` | `date +%F` | never guessed -- this command must succeed |

```bash
git config user.name
git rev-parse --show-toplevel
date +%F
```

## Step 3 -- confirm once

One `AskUserQuestion`, showing all six inferred values, the container, and the full manifest from:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.py --dry-run \
  --target "$(git rev-parse --show-toplevel)" --container "$CONTAINER" \
  --subject "$SUBJECT" --repo "$REPO" \
  --human-actor "$HUMAN_ACTOR" --agent-actor "$AGENT_ACTOR" --today "$TODAY"
```

Options: **Proceed** / **Change container** / **Abort**. No second prompt after this -- Step 4
onward runs unattended.

## Step 4 -- write

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.py \
  --target "$(git rev-parse --show-toplevel)" --container "$CONTAINER" \
  --subject "$SUBJECT" --repo "$REPO" \
  --human-actor "$HUMAN_ACTOR" --agent-actor "$AGENT_ACTOR" --today "$TODAY"
```

Print its receipt verbatim (one line per file written, then the summary line). A non-zero exit
means it refused -- report the refusal and stop; do not retry with `--adopt` or delete files to
force it through.

## Step 5 -- generate

```bash
python3 "${CONTAINER}scripts/regen_indexes.py"
```

Expect `... generated files rewritten` and exit 0. Then confirm all five
`${CONTAINER}bundle/*/index.md` files exist. This step is what makes gate 3 (index drift) pass
even if it reports zero rewrites -- `scaffold.py` already left the five stub indexes correct, so
a clean run here is expected, not a failure.

## Step 6 -- verify and report

First check the Python dependencies so a missing one reads as a clear instruction, not a gate
crashing with exit 2:

```bash
python3 -c "import yaml, pytest"
```

If that fails, stop and say exactly: `pip install -r ${CONTAINER}requirements.txt`, then re-run
this step. Do not run the gates below until it succeeds.

Then run all four gates from the repository root, capturing each exit code:

```bash
python3 "${CONTAINER}scripts/check_okf.py" --strict
python3 "${CONTAINER}scripts/check_links.py" --strict
python3 "${CONTAINER}scripts/regen_indexes.py" --check
python3 -m pytest -q -rs "${CONTAINER}tests"
```

Also run the token sweep -- a survived `{{TOKEN}}` is a rendering bug, not a content issue:

```bash
! grep -rn '{{[A-Z_]\+}}' "$CONTAINER" .claude/wiki.json CLAUDE.md
```

Print each command, its summary line, and its exit code. Setup is done **only** when all four
gates and the token sweep are 0. On any non-zero, report **FAILED** with the failing gate's full
output -- never claim the wiki is ready with a red gate.

Close, on success, with:

```
wiki setup complete: <container>

Gates:
  check_okf.py --strict       0 errors, 0 warnings
  check_links.py --strict     0 errors, 0 warnings
  regen_indexes.py --check    0 of 5 out of date
  pytest                      N passed, M skipped, 0 failed

Next: run /wiki:ingest <path-or-URL> to add the first source.
```

Setup never ingests. Every skipped test in the pytest line is expected on an empty bundle -- if
`-rs` output shows any skip whose reason is not "empty bundle: ...", treat that as a finding, not
noise.
