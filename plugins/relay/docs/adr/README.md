# Architecture Decision Records

Standing decisions about how relay is built — the ones that are hard to reverse,
surprising without context, and the result of a real trade-off. Format follows
[`ADR-FORMAT.md`](../../../engineering/skills/grill-with-docs/ADR-FORMAT.md).

These record *decisions*, which is a different job from the three things relay
already had:

| Record | Answers |
|---|---|
| `docs/superpowers/specs/` | what we planned to build, at a date |
| `CHANGELOG.md` | what changed, in order, and why |
| the contract docs | how it works today |
| **`docs/adr/`** | **what is decided, whether it still holds, and what would supersede it** |

None of the first three answers the last question, which is how a design spec came to
sit at `Status: design (approved in substance)` describing a feature that shipped in
v4.5.0 and was removed two releases later.

## The records

| # | Decision | Status |
|---|---|---|
| [0001](0001-single-orchestration-substrate.md) | One orchestration substrate: the native Workflow tool | accepted |
| [0002](0002-agent-role-split.md) | Split behavior from capability: roles execute inside two generic leaves | accepted |
| [0003](0003-depth-1-by-tool-omission.md) | Enforce depth-1 by omitting tools, not by instructing the agent | accepted |
| [0004](0004-model-tiers-by-failure-mode.md) | Select model tiers by failure mode, not by task difficulty | accepted |
| [0005](0005-dispatch-axis-is-a-per-role-binding.md) | The engine/agent axis selects a family, not a pipeline mode | accepted |
| [0006](0006-fail-to-indeterminate.md) | Fail to indeterminate, never to a pass — and make the gate always-on | accepted |
| [0007](0007-frozen-envelope-tokens.md) | Four envelope tokens are frozen and byte-pinned | accepted |
| [0008](0008-superpowers-is-a-hard-dependency.md) | superpowers is a hard dependency, not a vendored copy | accepted |

## Adding one

Scan for the highest number and increment. All three of these must hold, or skip it:
the decision is **hard to reverse**, it is **surprising without context**, and it is
**the result of a real trade-off**. An easy-to-reverse decision will simply be
reversed; an unsurprising one leaves nobody wondering why.

Keep it short. The house format says an ADR can be a single paragraph, and the value
is in recording *that* a decision was made and *why* — not in filling out sections.
Add **Considered options** only when the rejected alternatives are worth remembering,
and **Consequences** only when the downstream effects are non-obvious.

## Status lifecycle

`status:` frontmatter is required and must be one of `proposed`, `accepted`,
`deprecated`, or `superseded`. A `superseded` record must name its replacement with
`superseded-by: NNNN`, and that record must exist.

Superseding is a new record plus a status change on the old one — never an edit in
place. The point of these files is that a past decision stays readable after it stops
being true; rewriting history defeats the purpose.

`tests/unit/skill-structure/test_docs_freshness.py` enforces the numbering, the
status vocabulary, the supersession link, and that this index lists every record.
