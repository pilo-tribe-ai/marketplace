# Contributing to Relay

> How a change lands. Read [`architecture.md`](architecture.md) first if you have not
> — most review comments on relay PRs are really "you didn't know about the split".
>
> Paths and commands here are asserted by
> `tests/unit/skill-structure/test_docs_freshness.py`.

## There is no CI — the local run is the entire gate

This repository has no GitHub Actions workflows, no git hooks, and no branch
protection. Nothing is enforced server-side. "Never commit directly to `main`" is
discipline, not a rule the remote can apply, and **if you do not run the suite, no
one does.**

Some test files carry comments describing themselves as "CI validators". That is
aspirational naming, not an existing pipeline.

## Run everything before you push

```bash
cd plugins/relay

pytest tests/ -q                                         # 1800+ tests
bash tests/unit/skill-structure/test_parse_engine_agent.sh   # not collected by pytest
bash tests/unit/skill-structure/test_resolve_tier.sh         # not collected by pytest
bash tools/fidelity-check.sh --smoke
python3 scripts/doc_reference_scan.py --repo-root . --run-gate   # stale-reference scan
bash scripts/check-deps.sh
```

`doc_reference_scan.py` is the repo's one mechanical documentation gate: it walks the
references your diff *introduced* and reports any that do not resolve.

**It is advisory and it is noisy — read the findings, do not expect `CLEAN`.** It
resolves bare paths against the repo and plugin roots, so ordinary prose shorthand
reads as unresolved: `test_plugin.py` rather than
`tests/unit/skill-structure/test_plugin.py`, a `relay:leaf-worker` agentType parsed as
a skill name, `.claude/relay.json` (created by the user, never committed), or a
deliberate `NNNN-slug.md` placeholder. A docs-heavy PR routinely reports dozens of
these. What you are scanning for is the one entry that names a file you actually
renamed or removed.

It exits `0` on findings by design, so nothing fails if you skip it — which is the
reason it is on this list. And treat a `CLEAN` with suspicion for the usual reason: a
scan that could not read a diff returns exactly the same verdict as a scan that found
nothing. Check `diff_source` and `base_ref` in its JSON before believing a clean run.

There is no `pytest.ini`, `pyproject.toml`, `Makefile`, or `package.json`. The
harness is pytest rootdir auto-discovery plus `tests/conftest.py`. Node is a hard
dependency of the Python suite — `test_capability_validate.py` shells out to
`node --test`.

### A green run can be hollow

Install `yq` and `jq` before touching anything under
`skills/dispatching-acpx-agents/`:

```bash
brew install yq jq
```

Without `yq`, **more than thirty acpx-dispatch tests skip silently** and a passing
suite proves nothing about the dispatch path or the session drivers. Check what
skipped and why with:

```bash
pytest tests/ -q -rs | grep SKIPPED
```

The legitimate skips are the thin-L3 commands opting out of the positional parser
convention, the generic leaves having no `relay:` block, and the three in
`test_flows.py` — `acpx not on PATH`, `flows/ deps not installed`, and
`live flow smoke disabled`. The second of those clears with
`npm install` in `plugins/relay/flows`; the third needs `RELAY_RUN_LIVE_FLOW=1`
and network egress.

Anything mentioning `yq` means you are not testing what you think you are testing.
If a skip reason appears that is not on this list, treat it as uncovered code
rather than as a fourth legitimate category.

## The version dance — the most common first-PR failure

`CLAUDE.md` requires every user-facing change to bump
`.claude-plugin/plugin.json`, because that version is the plugin-distribution cache
key. The non-obvious part is that **the current version is exact-pinned in a test**:

```python
# tests/unit/skill-structure/test_plugin.py
assert manifest["version"] == "4.52.0"
```

Bumping fails the suite until you do the ratchet:

1. Relax the previous version class's exact pin to `>=`, keeping the in-tree comment
   style: `# Superseded exact pin: 4.22.0 carries this line forward (TestVersion4220 …)`.
2. Add a `class TestVersion4220` with a fresh exact pin, a
   `test_changelog_has_4220_entry` that greps the new CHANGELOG section for its
   distinguishing tokens, and executability assertions for any new scripts.

This is deliberate. An exact pin forces a reviewed touch of the test file on every
release, which makes "bumped the version, forgot the CHANGELOG" structurally
impossible.

### CHANGELOG style

Newest first, semver headings, no `[Unreleased]` section:

```markdown
## 4.22.0 — 2026-08-03

**Minor — one-line thesis of the change.**

- **Bolded lead-in.** Prose explaining what changed and *why*, including rejected
  alternatives and the failure modes it closes.
```

Entries are long and rationale-heavy — recent ones run well over a hundred lines and
document designs that were considered and dropped. Terse bullets read as out of
place. Write down what did *not* work; that is the part future readers need.

## What the tests actually enforce

Roughly 1800 assertions across 50-odd files, and almost none of them execute the
product. They assert frontmatter keys, closed set memberships, verbatim body
strings, and prose counts in documentation. For a plugin whose deliverable is
markdown consumed by a model, **the prose is the source code**, and pinning exact
strings is the only available type system.

### Closed inventories

Adding a file without editing the matching constant fails the suite. This is
intentional friction — it forces a deliberate decision rather than a silent
addition.

| Inventory | Where the count lives |
|---|---|
| Agents | exact set equality, `test_roles.py` + `test_agent_registration.py` |
| Roles | `EXPECTED_ROLE_SLUGS` in `test_roles.py` |
| Skills | split across two files: `EXPECTED_SKILLS` (19) in `test_plugin.py`, and `L2_NAMES` (7) + `RESOLUTION_POLICY_SKILLS` (2) in `test_l2_skills_present.py`, plus the classifier |
| Presets | `assert len(roles) == …` in `test_plugin.py` |

### Role files

Required: `role-version`, `description`, `role-class` (`writer` or `reader` only),
`output-tokens` (non-empty list), `terminal_token` (a member of that list),
`requires`.

**Forbidden:** `name`, `tools`, `model`, and any `relay:` block — those are agent and
binding concerns. Body must exceed 50 characters. `verify_artifact` is an exact
four-role allow-list, required on those and asserted *absent* everywhere else. The
bijection between `roles/*.md` and `bindings/presets.yaml` keys is checked in both
directions.

### Agent files

`name:` must be the bare slug — the loader adds the `relay:` namespace. Any `*.md`
in `agents/` registers as an agent, including one with no frontmatter, which
receives every tool. Documentation goes in `docs/`. See
`test_agent_registration.py` for the full rule set and the two bugs that motivated
it.

### Cross-cutting bans

- **`park` is banned in every skill body.** A leaf has exactly one turn and cannot
  resume, so the word itself is forbidden to stop the doctrine drifting back in.
- `superpowers:*` references are a closed set; dropped skill names are banned
  tree-wide.
- Inside a bash fence, executable lines must not read positional parameters —
  no `$#`, `$@`, `$*`, `${1..9}`, `set --`, `shift`.
- New scripts must be `chmod +x`; executability is asserted.

## Checklist by change type

Every type also needs the version bump, the CHANGELOG entry, and the ratchet above.

### Bugfix
The fix, plus a regression test in `tests/unit/skill-structure/`. Retroactive TDD is
the house style — verify the test fails before the fix and passes after, and say so
in the PR.

### New role — the most test-coupled change in the plugin
1. `roles/<slug>.md`
2. `bindings/presets.yaml` entry — bijection, enums, all four `modalities`
3. `test_roles.py` — `EXPECTED_ROLE_SLUGS`, one of `WRITER_`/`READER_ROLE_SLUGS`, `COLLAPSED_SLUGS`
4. `test_presets_eligibility.py` — one of `ELIGIBLE_ROLES`/`INELIGIBLE_ROLES`
5. `test_plugin.py` — the presets length assertion
6. Prose counts in `roles/README.md` and the plugin `README.md`
7. Wire it into a consuming skill — an unreferenced role is dead weight

### New skill
`skills/<name>/SKILL.md`, registered in its class constant. Pick the class *first*:
a `relay-vocab` block is **required** for L2 pattern skills and **forbidden** for
policy and classifier skills. Add to `_KNOWN` in `scripts/validate_l3_command.py` if
an L3 command cites it.

### New command
Copy an existing L3 command verbatim and edit — hand-authoring fails a dozen
assertions on verbatim body strings and their ordering. Register it in the
`COMMANDS` structure and in the validator's `CMD_NAMES` tuple, or enforcement
silently skips your command.

### New agent
Effectively closed — the roster is pinned by set equality. **Prefer adding a role**;
that is precisely what the v4.0.0 migration existed to enable.

### Design and plan documents
These go at **repo root**, not inside the plugin:
`docs/superpowers/specs/YYYY-MM-DD-<slug>-design.md` and
`docs/superpowers/plans/YYYY-MM-DD-<slug>-plan.md`.

### An architectural decision
If your change settles something **hard to reverse, surprising without context, and
the result of a real trade-off**, add a record in [`adr/`](adr/README.md). All three
must hold — an easy-to-reverse decision will simply be reversed, and an unsurprising
one leaves nobody wondering why.

Keep it short; the house format allows a single paragraph. Record the rejected
alternatives only where they are worth remembering — which, for the decisions that
meet the bar, they usually are.

Superseding an existing decision is a *new* record plus a `status: superseded` and
`superseded-by: NNNN` on the old one. Never edit a decision in place: these files
exist so a past decision stays readable after it stops being true.

Note the division of labour. A design spec records what you planned at a date and
goes stale by design. The CHANGELOG records what changed, in order. An ADR records
what is *currently decided* and whether it still holds — which is the question the
other two cannot answer, and the reason a spec in this repo still describes a feature
that shipped and was removed two releases later.

## Traps

**Positional parameters are always empty in command bash blocks.** The harness runs
each block as a standalone script with no positional parameters *and* textually
substitutes `$1`/`$2` before the shell runs, so a `while [ $# -gt 0 ]` loop never
iterates. Parse from the interpolated `$ARGUMENTS` string. This shipped once as four
stacked defects where `--engine acpx` silently ran in-session while reporting
success.

**`git diff` needs `--no-ext-diff`.** With `diff.external` configured (difftastic,
delta), git emits a non-unified patch, a parser sees zero added lines, and a critic
reports CLEAN while checking nothing.

**`grep -q` on a pipe causes false failures.** It exits at first match and closes the
pipe; the writer dies of SIGPIPE and `pipefail` promotes 141 into the pipeline
status. Grep the file directly.

## Git workflow

Branch naming is inconsistent in history; `feature/relay-<slug>` or
`fix/relay-<slug>` is the safe default. Conventional commits, scoped, with the
version in the title:

```
feat(relay): in-session tiers ON by default + `inherit` rung (v4.14.0)
```

PR bodies are substantial: a `## Problem` section with a defect table and evidence,
then `## What changed` with rationale. Describe what you rejected, not only what you
built.
