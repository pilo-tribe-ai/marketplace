# Changelog

## 0.1.0

- Deterministic spine: `adr_lib.py` (read-tolerant frontmatter and legacy bold-key parser,
  write-strict frontmatter writer, filename-derived identity, config plus Discovery), `adr_new.py`
  (sequential/date ID allocation, collision refusal), `adr_index.py` (register generation grouped
  by area, hand-authored-summary preservation across regeneration, `--write`/`--check`), and
  `adr_lint.py` (required fields, status enum, date parse, duplicate identity, cross-reference
  resolution, supersede pairing, register staleness, scoped `--changed proposed` check).
- `/adr:setup` and the `scaffolding-adr-corpora` skill: detect or create a corpus, offer
  greenfield/adopt/migrate, write the corpus, `.claude/adr.json`, the vendored tooling, and both
  CLAUDE.md rule blocks. Ends only when the register and lint gates are green.
- `plugins/adr/scripts/scaffold.py`, the deterministic write step behind setup, plus `--refresh`
  and `--adopt` modes.
- `plugins/adr/templates/`: both CLAUDE.md blocks, the ADR template bound to `adr_new.py`'s writer,
  and the register seed bound to `adr_index.py`'s markers.
- `/adr:new` and the `authoring-adrs` skill: writes one ADR with `status: proposed` for a decision
  that is expensive to undo, then keeps working -- it never stops to ask. Carries the bar's
  IN/OUT examples and the distillation standard (`skills/authoring-adrs/distillation.md`) with its
  four append tells.
- `/adr:ask` and the `consulting-decisions` skill: read-only recall (`Read, Grep, Glob` only) that
  reads the register first, cites `path:line`, and states plainly what the corpus does not cover.
- `amending-adrs`: rewrites a changed ADR in place, deprecates, or supersedes with both back-links
  set on a supersede, never a one-sided link.
- `/adr:index` and the `indexing-adrs` skill: regenerates the register, reports dropped and
  unparsed rows from the receipt, and never reports success on a red lint.
- `adr_migrate.py` and `/adr:migrate`: folds legacy bold-key headers into frontmatter
  (`--frontmatter`, the default), leaving every filename untouched, or additionally normalises
  `ADR-002-slug.md` to `0002-slug.md` (`--rename`) and carries the register's hand-authored
  summary to the new key. A supersede reference it cannot resolve to a real file is left for the
  lint to report, never guessed. Stages every change for review; commits nothing. Vendored through
  `scaffold.py`, and wired into `scaffolding-adr-corpora`'s migrate path (adopt, then convert).
- `reviewing-adr-adherence` and `/adr:check`: the gate's model tier. Reads the diff between the
  current branch and its default branch, reports whether it contradicts an accepted ADR or ships a
  hard-to-reverse change with no ADR, and always exits 0 -- findings are advisory, and the
  deterministic tier is what the gate blocks on.
- `templates/gate/adr-gate.yml`: an optional two-tier GitHub Actions gate, offered at `/adr:setup`
  and written by `scaffold.py` only when asked for. The deterministic job (`adr_lint.py`,
  `adr_index.py --check`) runs with no install step and no key, scoping the "still `proposed`"
  check to the pull request's own changed files. The model job runs `claude -p "/adr:check"` only
  when `secrets.ANTHROPIC_API_KEY` is present, and never fails the check on its own.
- `grooming-adrs` and `/adr:groom`: merges overlapping ADRs, retires what reality outgrew,
  compresses prose in place to the distillation standard, and archives the dead into
  `{{DIR}}/archive/`, setting `archive_dir` and repairing every inbound link -- including the
  register's own keys -- before the next regeneration. Always proposes a plan and shows a diff
  first; never rewrites silently.
- Registered in the marketplace.
