# PRD Schema

This document defines the canonical format of the living PRD. All PRD skills MUST follow this schema exactly.

## File locations

| File | Path | Created by |
|------|------|-----------|
| PRD | `docs/product/prd.md` | `/prd:explore` (skeleton), `/prd:save` (content) |
| Roadmap | `docs/product/roadmap.md` | `/prd:plan` or `/prd:themes-identify` |

There is one PRD and one roadmap per repository. When a skill's path argument is unset, it uses these defaults. Create the `docs/product/` directory when it does not exist.

## Frontmatter

The PRD starts with YAML frontmatter that tracks per-lens coverage. `/prd:save` maintains it. `/prd:explore` and `/prd:plan` read it.

```yaml
---
product: Acme Scheduler
description: One-line description of the product.
created: 2026-08-14
updated: 2026-08-14
lenses:
  problem:         { status: complete,    updated: 2026-08-14 }
  personas:        { status: in-progress, updated: 2026-08-14 }
  journeys:        { status: not-started }
  capabilities:    { status: not-started }
  scope:           { status: not-started }
  success-metrics: { status: not-started }
  business-model:  { status: not-started }
  go-to-market:    { status: not-started }
  risks:           { status: not-started }
---
```

Valid lens statuses: `not-started`, `in-progress`, `complete`.

**Repair rule**: if the frontmatter is missing or does not parse, re-derive it — a lens whose section exists with content is `in-progress`; ask the user which of those are `complete`.

## Lens catalog

The **spine** is the ordered core. Each lens builds on the ones before it. The **satellites** are optional and unlock when their prerequisites are met.

| Lens | Kind | Section heading | ID prefix | Prerequisites |
|------|------|-----------------|-----------|---------------|
| Problem | Spine 1 | `## Problem` | `PRB` | none |
| Personas | Spine 2 | `## Personas` | `PER` | Problem |
| Journeys | Spine 3 | `## Journeys` | `JRN` | Personas |
| Capabilities | Spine 4 | `## Capabilities` | `CAP` | Personas (Journeys recommended) |
| Scope | Spine 5 | `## Scope` | `SCP` | Capabilities |
| Success Metrics | Spine 6 | `## Success Metrics` | `MET` | Problem, Scope |
| Business Model | Satellite | `## Business Model` | `BIZ` | Problem, Personas |
| Go-to-Market | Satellite | `## Go-to-Market` | `GTM` | Personas, Scope |
| Risks & Assumptions | Satellite | `## Risks & Assumptions` | `RSK` | Problem |

A prerequisite is met when the lens status is `in-progress` or `complete`.

## Fixed sections

The PRD body contains, in this order:

1. `# [Product Name] PRD` — title, one-paragraph product summary
2. One `## <Lens>` section per explored lens, in catalog order
3. `## Product Constraints` — `CON-n` entries captured by the deflection procedure (see `product-hat.md`)
4. `## Decisions Log` — table: Decision, Rationale, Alternatives, Date
5. `## Open Questions` — unresolved items

Sections for unexplored lenses are absent, not empty.

## Requirement IDs

- Every requirement is one top-level bullet: `- **CAP-3**: [requirement text]`, with optional indented child bullets (details, acceptance notes).
- `/prd:save` assigns IDs: scan the whole file for the highest number per prefix, then use the next number.
- IDs are permanent. Never renumber, never reuse a deleted ID. Editing a requirement keeps its ID.
- Every statement the roadmap must trace to gets an ID: personas, journey outcomes, capabilities, scope boundaries, metrics, constraints.

## Requirement hashes

Roadmap items store a short hash of each requirement they trace to. The hash detects requirement drift.

**Normalization**: take the requirement's full block (the bullet line plus its indented child lines). Remove the leading `- **ID**: ` marker. Replace every run of whitespace (spaces, tabs, newlines) with a single space. Trim both ends.

**Hash**: first 6 hex characters of the SHA-256 of the normalized text.

```bash
printf '%s' "$NORMALIZED_TEXT" | sha256sum | cut -c1-6
```

**Batch recipe** — when several requirements need hashing (planning a slice, running a drift check), compute them all in one invocation instead of one shell call per requirement:

```bash
python3 - <<'EOF'
import hashlib, re
text = open('docs/product/prd.md').read()
for m in re.finditer(r'^- \*\*([A-Z]{3}-\d+)\*\*: (.*(?:\n(?: {2,}|\t).*)*)', text, re.M):
    norm = ' '.join(m.group(2).split())
    print(m.group(1), hashlib.sha256(norm.encode()).hexdigest()[:6])
EOF
```

**Trace format** (in roadmap item bodies): `**Trace**: CAP-3 @a1b2c3, PER-1 @9f8e7d` — always the bold `**Trace**:` marker; consumers match on it exactly. A story carries its own Trace line only when it narrows its parent feature's trace to a more specific requirement; otherwise it inherits the feature's trace implicitly and has no Trace line.

## Drift check procedure

The single procedure for detecting requirement drift. `/prd:save` and `/prd:roadmap-sync` both run it; only the parameters differ.

**Scope** — which traces to check:
- *changed-IDs* (used by save): only traces referencing requirement IDs edited or removed in this session
- *all* (used by sync): every trace in the roadmap. Short-circuit first: skip the check only when all three hold — the PRD is tracked by git, `git status --porcelain <prd-path>` is empty, and the date from `git log -1 --format=%cs -- <prd-path>` is **strictly older** than the table's "Last synced" date. `%cs` has day granularity, so an equal date means the PRD may have changed after the last sync on the same day: run the check. When git is unavailable or the PRD is untracked, run the check.

**Check**: recompute each traced requirement's hash (batch recipe above) and compare with the stored `@hash`. A mismatch, or a trace ID that no longer exists in the PRD, marks the item drifted.

**Mode** — what to do with a drifted item:
- *automatic* (used by save): set the item's status to `Needs Review`, append `⚠` to the drifted ID in the table's Trace column, and report it. Do not resolve.
- *interactive* (used by sync): ask the user per item, showing the requirement's current text and both hashes (when the old text matters, recover it with `git show` at the last-synced date). **Still valid** → update the stored `@hash`, status stays as calculated. **Needs rework** → flag as in automatic mode. For a removed requirement, offer: flag / remove the trace entry.

**Clearing**: only a human clears a flag — by confirming the item still satisfies the changed requirement (the stored hash is then updated) or by reworking the item. Progress signals never clear it.

## Legacy migration

Repositories that used PRD plugin v2 have `docs/prd/[product]-[focus].md` files and co-located roadmaps.

When `docs/product/prd.md` does not exist and legacy files do:

1. List the legacy files found and offer to merge them (AskUserQuestion: merge / start fresh).
2. On merge: map each legacy file's content into the matching lens sections (Users → Personas, Features → Capabilities, Scope → Scope, and so on). Move architecture or implementation content into `## Product Constraints` when it passes the constraint test in `product-hat.md`; otherwise drop it and tell the user what was dropped and why.
3. Assign requirement IDs to every merged requirement.
4. Set frontmatter lens statuses to `in-progress` for merged sections.
5. Leave the legacy files untouched. Tell the user they can delete them after review.

On decline: create the fresh skeleton and ignore legacy files.
