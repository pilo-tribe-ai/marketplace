---
name: scaffolding-adr-corpora
description: Scaffolds an architecture-decision-record corpus into the repository this is invoked in -- a corpus directory (docs/adr/ by default) holding a CLAUDE.md rule file, a generated register, and a vendored standard-library-only pytest suite for creating, indexing, and linting ADRs. Detects a prior corpus and offers greenfield, adopt, or migrate. Use for "/adr:setup", "set up ADRs in this repo", "scaffold an ADR corpus", "adopt an existing ADR folder", or "migrate legacy ADRs to frontmatter".
argument-hint: "[corpus path]"
allowed-tools: Bash, Read, Grep, Glob, Write, Edit, AskUserQuestion
---

# scaffolding-adr-corpora

Stand up an ADR corpus inside the repository you are invoked in. This writes files into the
**target repo**, never into the plugin. Setup ends green: the register indexes clean and the lint
reports zero errors.

**The bar for what earns an ADR:** record a decision when undoing it later would be expensive.
Cheap to change your mind, no ADR. State this bar plainly during step 3 so the person confirming
the plan sees it.

## Step 1 -- resolve the repository root

```bash
git rev-parse --show-toplevel
```

If this fails, stop: "This is not a git repository. `/adr:setup` needs one, because the vendored
test suite finds the repository root by walking up to `.git`." A git repo is a hard requirement,
not an inference -- there is no fallback.

## Step 2 -- detect prior state

```bash
test -f .claude/adr.json && cat .claude/adr.json
```

If `.claude/adr.json` exists, a corpus is already configured -- read `dir` from it and skip to
reporting the existing setup (offer `--refresh` if the person wants the vendored tooling and
CLAUDE.md rules brought current).

Otherwise, probe for an ADR-shaped folder. Check the corpus-path hint from `$ARGUMENTS` first,
then the common shapes: `docs/adr`, `docs/architecture/adrs`, `doc/adr`, `adr`.

```bash
ls docs/adr 2>/dev/null
ls docs/architecture/adrs 2>/dev/null
```

For any folder found holding `.md` files, report:

- **Folder** -- the path.
- **Naming scheme** -- `NNNN-slug.md` (sequential), `ADR-NNN-slug.md` (legacy sequential, folds to
  sequential), or `YYYY-MM-DD-slug.md` (date). Sample two or three filenames to tell.
- **Metadata style** -- open one file. YAML frontmatter (`---` fences) or legacy bold-key headers
  (`**Status:** Accepted`)?
- **Count** -- how many `.md` files, excluding `README.md` and `CLAUDE.md`.

Finding nothing means greenfield.

## Step 3 -- offer the path

Ask with `AskUserQuestion`, once:

- **Greenfield** -- no existing corpus, or start fresh at a new path. Writes a new corpus at
  `docs/adr/` (or the given path) with an empty register.
- **Adopt** -- a corpus was found. Writes `.claude/adr.json` matching what is already there and
  vendors the tooling. **Modifies no existing ADR.**
- **Migrate** -- adopts, then converts legacy bold-key metadata to frontmatter with
  `scripts/adr/adr_migrate.py`. Two levers: `--frontmatter` (the default) folds bold keys and
  touches no filename; `--rename` also normalises `ADR-002-slug.md` to `0002-slug.md`, which
  changes every link that points at the file, so confirm it separately before running it. The
  script stages every change for review and commits nothing -- it never runs `git commit`.
- **Abort** -- stop, no files written.

Also offer the optional PR/CI gate here, whichever path was chosen: ask whether to write
`.github/workflows/adr-gate.yml` -- deterministic only (`--gate-deterministic`), deterministic +
model (`--gate-deterministic --gate-model`), or skip (neither flag; the default). The deterministic
tier runs `adr_lint.py` and `adr_index.py --check` with no install step; the model tier runs
`/adr:check` in CI, only when `secrets.ANTHROPIC_API_KEY` is present, and never fails the check.

## Step 4 -- confirm the manifest, once

Run the dry run and show the exact file list before writing anything:

```bash
python3 <plugin-root>/scripts/scaffold.py --target "$(git rev-parse --show-toplevel)" \
  --dir <dir> --dry-run
```

Confirm every inferred value (corpus path, id scheme, register path) and the full manifest with
the person in the same turn as this dry run. No second prompt after this.

## Step 5 -- write the corpus

Run `scaffold.py` with the chosen mode and print its receipt verbatim. Append
`--gate-deterministic` and/or `--gate-model` (and `--proposed-verdict <error|warning|off>` if the
person wants a non-default verdict) to any of these when step 3 asked for the gate:

- Greenfield: `scaffold.py --target <root> --dir <dir> --today <YYYY-MM-DD>`
- Adopt: `scaffold.py --target <root> --dir <dir> --id-scheme <sequential|date> --adopt --today <YYYY-MM-DD>`
- A prior corpus already scaffolded and the person wants it brought current:
  `scaffold.py --target <root> --refresh --today <YYYY-MM-DD>` (the gate, if any, is re-read from
  the existing `.claude/adr.json` and refreshed to match -- `--refresh` takes no gate flags of its
  own)
- Migrate: run the Adopt command above first, so the vendored tooling exists, then run
  `python3 scripts/adr/adr_migrate.py [--rename]` from the repository root. Show the staged diff
  (`git diff -- <dir>`) before saying the migration is done. Migration commits nothing -- it never
  runs `git commit` -- so the diff is what the person reviews and commits themselves.

A non-zero exit means it refused (a manifest target already existed, or `--refresh` ran with no
`.claude/adr.json`). Report the refusal and stop. **Never delete files to force it through.**

## Step 6 -- run the gates and report the receipt

```bash
python3 scripts/adr/adr_index.py --write --repo-root "$(git rev-parse --show-toplevel)"
python3 scripts/adr/adr_lint.py --repo-root "$(git rev-parse --show-toplevel)"
```

Print each command with its exit code. **Setup is done only when both are green.** On any non-zero
exit, report FAILED with the full output -- do not declare success with a red gate.

If `python3` is not on `PATH`, say so plainly: this repo cannot run the deterministic gate, so
skip writing a CI workflow that would only fail. Do not write `adr-gate.yml` in that case.

Close with a receipt: what was written, the corpus path, the id scheme, and the two commands' exit
codes.
