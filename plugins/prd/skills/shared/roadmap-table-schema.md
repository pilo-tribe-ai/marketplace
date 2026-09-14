# Roadmap Status Table Schema

This document defines the canonical format for the roadmap summary table. All roadmap-modifying skills MUST follow this schema exactly.

## Table Template

The table MUST be wrapped in sentinel comments for programmatic replacement:

```markdown
<!-- ROADMAP-STATUS-TABLE:START -->
# Roadmap Status

> Last synced: [YYYY-MM-DD]

| # | Group | Item | Type | Status | Progress | Deps | Trace |
|---|-------|------|------|--------|----------|------|-------|

<!-- ROADMAP-STATUS-TABLE:END -->
```

## Column Definitions

| Column | Description | Format |
|--------|-------------|--------|
| **#** | Sequential row number | Integer starting at 1 |
| **Group** | Parallel execution group | `-` for sequential, letter (`A`, `B`, `C`...) for parallel tracks |
| **Item** | ID and name | `M1: Name` for milestones, `F1.1: Name` for features |
| **Type** | Item type | `Milestone` or `Feature` |
| **Status** | Current status | One of: `Not Planned`, `Not Started`, `In Progress`, `Completed`, `Needs Review` |
| **Progress** | Visual progress bar + percentage | 10-char bar using `█` and `░` + space + `N%` |
| **Deps** | Dependencies | Comma-separated IDs or `-` for none |
| **Trace** | PRD requirement IDs the item satisfies | Comma-separated IDs (`CAP-3, PER-1`); append `⚠` to a drifted ID (`CAP-3 ⚠`); `-` if untraced |

## Status Values

Only these five values are valid:
- `Not Planned` — Placeholder milestone; the phase exists in the skeleton but has not been broken down
- `Not Started` — No work has begun
- `In Progress` — At least one child item has activity
- `Completed` — All child items are done
- `Needs Review` — A PRD requirement this item traces to changed after the item was planned (hash mismatch); a human must revisit the item

### Status Precedence (applies to every level)

These two rules outrank the per-level calculation rules below:

1. **`Needs Review` outranks every calculated status.** An item with a drifted trace — or, for a milestone, any child with one — shows `Needs Review` regardless of progress. A story with a drifted trace flags its parent feature. Keep the last computed Progress value. Only a human clears the flag (see the drift check procedure in `prd-schema.md`).
2. **`Not Planned` is milestone-only and derivable from the body**: a milestone with no `#### Features` heading is a placeholder → `Not Planned`. Once a breakdown adds the heading, the milestone leaves `Not Planned` and the normal rules apply.

## Traceability

Every milestone and feature records the PRD requirements it satisfies in its body with the bold `**Trace**:` marker (stories only when they narrow the feature's trace — see `prd-schema.md`):

```markdown
**Trace**: CAP-3 @a1b2c3, PER-1 @9f8e7d
```

`@a1b2c3` is the requirement's content hash at link time. Normalization, hashing, the trace format, and the full drift check procedure (scopes, modes, flag clearing) are defined in `prd-schema.md`. In this table, a drifted ID gets a `⚠` suffix in the Trace column.

## Progress Bar Format

The progress bar uses exactly 10 characters:
- `█` (U+2588) for filled portion
- `░` (U+2591) for empty portion
- Followed by a space and the percentage with `%` suffix

Examples:
- `██████████ 100%` — fully complete
- `████████░░ 80%` — 80% complete
- `█████░░░░░ 50%` — half complete
- `░░░░░░░░░░ 0%` — not started

Calculate filled characters: `round(percentage / 10)`

## Calculation Rules

### Story Status
- Checkbox checked (`- [x]`) → `Completed` (100%)
- Checkbox unchecked (`- [ ]`) with "In Progress" in notes → `In Progress` (50%)
- Checkbox unchecked (`- [ ]`) → `Not Started` (0%)

### Feature Percentage
- **If has stories:** `count(completed_stories) / count(total_stories) * 100`
- **If no stories yet:** Derive from status — `Not Started` = 0%, `In Progress` = 50%, `Completed` = 100%

### Feature Status
- All stories completed → `Completed`
- Any story in progress or completed → `In Progress`
- No stories or all not started → `Not Started`

### Milestone Percentage
- `average(feature_percentages)` across all child features
- If no features yet: same rule as feature with no stories

### Milestone Status
- All features completed → `Completed`
- Any feature in progress or completed → `In Progress`
- No features or all not started → `Not Started`
- (Status precedence above governs `Not Planned` and `Needs Review`)

## Ordering Rules

1. Items are ordered by **execution dependency** — items with no unmet dependencies first
2. Within the same dependency level, items are ordered by their ID (M1 before M2, F1.1 before F1.2)
3. **Parallel groups:** Items that can execute simultaneously share the same group letter
4. Items in different groups at the same level are adjacent in the table
5. Features are listed immediately after their parent milestone

## Group Assignment Rules

- A milestone with no dependencies on other milestones: Group `-`
- Multiple milestones that can run in parallel: Same group letter (A, B, etc.)
- Features within a milestone that can run in parallel: Same group letter
- Features with dependencies on other features: Different group or `-`

## Example

```markdown
<!-- ROADMAP-STATUS-TABLE:START -->
# Roadmap Status

> Last synced: 2026-03-08

| # | Group | Item | Type | Status | Progress | Deps | Trace |
|---|-------|------|------|--------|----------|------|-------|
| 1 | - | M1: Foundation | Milestone | Needs Review | ██████░░░░ 55% | - | SCP-1 |
| 2 | A | F1.1: Onboarding | Feature | Completed | ██████████ 100% | - | JRN-1, PER-1 |
| 3 | A | F1.2: Scheduling | Feature | Needs Review | ██████████ 100% | - | CAP-1 ⚠ |
| 4 | B | F1.3: Reminders | Feature | In Progress | ██░░░░░░░░ 20% | F1.1 | CAP-2 |
| 5 | - | F1.4: Sharing | Feature | Not Started | ░░░░░░░░░░ 0% | F1.2, F1.3 | CAP-4 |
| 6 | - | M2: Teams | Milestone | Not Started | ░░░░░░░░░░ 0% | M1 | SCP-2 |
| 7 | - | M3: Insights | Milestone | Not Planned | ░░░░░░░░░░ 0% | M2 | SCP-3 |

<!-- ROADMAP-STATUS-TABLE:END -->
```

In this example M1 shows `Needs Review` because its child F1.2 has a drifted trace (precedence rule 1), and its Progress stays at the calculated `average(100, 100, 20, 0)` = 55%.

## Regeneration Instructions

When any roadmap-modifying skill completes its edit:

1. Parse the full roadmap document for all milestones (### M*), features (- [ ] F* or - [x] F*), and stories (- [ ] S* or - [x] S*)
2. Calculate status and percentage for each feature and milestone per the rules above
3. Determine ordering and group assignments
4. Generate the table rows
5. Replace everything between `<!-- ROADMAP-STATUS-TABLE:START -->` and `<!-- ROADMAP-STATUS-TABLE:END -->` with the new table
6. Update the "Last synced" date to today
