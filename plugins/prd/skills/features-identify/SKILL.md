---
description: Break down a roadmap milestone into features through Socratic questioning
argument-hint: "[roadmap] [milestone]"
model: opus
context: fork
agent: roadmap-analyst
allowed-tools: AskUserQuestion, Read, Edit, Grep, Bash
---

# Identify Features - Milestone Decomposition

Break down a roadmap milestone into deliverable features through collaborative Socratic exploration.

## Your Task

1. Read the roadmap.md and locate the specified milestone
2. Reference the source PRD for detailed requirements
3. Through Socratic questioning, identify features that comprise this milestone
4. Update the roadmap.md with the identified features, each traced to PRD requirement IDs

Read the shared specifications first:
- `${CLAUDE_SKILL_DIR}/../shared/prd-schema.md` — requirement IDs and hash rules
- `${CLAUDE_SKILL_DIR}/../shared/roadmap-table-schema.md` — status table format

**Caller contract**: when invoked from `/prd:plan`, the shared specs are already loaded (skip the read above) and the caller regenerates the status table once at the end (skip Step 6).

## Process

### Step 1: Read Context

1. Read the roadmap at `{{roadmap}}` (default `docs/product/roadmap.md` when no argument is given)
2. Find milestone `{{milestone}}`
3. Read the source PRD (path is in roadmap header)
4. Understand the milestone's strategic goal and success criteria

### Step 2: Present Milestone Context

Summarize:
- Milestone name and goal
- What the PRD says about this area
- Any constraints or dependencies

**Question**: "Is this the right milestone to break down now?"
- **Options**: Yes, proceed / Need to clarify scope first / Wrong milestone

### Step 3: Feature Discovery

For each potential feature area, explore through questions:

#### 3.1 Feature Identification

**Question**: "What are the key capabilities needed to achieve [milestone goal]?"
- Provide 3-4 options based on PRD analysis
- Include "Other" for custom input

#### 3.2 For Each Feature, Explore:

**Scope Definition**
- "What's the minimum viable version of this feature?"
- Options: Full implementation / Core only / MVP slice

**User Value**
- "Who benefits most from this feature?"
- Options based on user personas from PRD

**Dependencies**
- "Does this feature depend on other features?"
- Options: Standalone / Depends on [other feature] / Enables [other feature]

**Complexity Signal**
- "How complex does this feature seem?"
- Options:
  - Straightforward - well-understood, similar to past work
  - Moderate - some unknowns, but manageable
  - Complex - significant unknowns or technical challenges
  - Research needed - requires spike or exploration first

**Priority Within Milestone**
- "How critical is this feature to the milestone's success?"
- Options:
  - Must have - milestone fails without it
  - Should have - significant value, but milestone could ship without
  - Nice to have - enhances but not essential

### Step 4: Feature Consolidation

After exploring features:

**Question**: "Looking at these features, is the scope right for milestone {{milestone}}?"
- **Options**:
  - Yes, this is achievable
  - Too many features - need to defer some
  - Missing a critical feature
  - Features overlap - need to merge

### Step 5: Update roadmap.md

Update the milestone section in roadmap.md with features:

```markdown
#### Features
- [ ] F{{milestone}}.1: [Feature Name]
  - **Description**: [What it does]
  - **User Value**: [Who benefits and how]
  - **Complexity**: [Straightforward/Moderate/Complex]
  - **Priority**: [Must/Should/Nice-to-have]
  - **Dependencies**: [None / F1.2 / etc.]
  - **Trace**: CAP-2 @a1b2c3, PER-1 @9f8e7d
  - Stories: <!-- To be populated by /prd:stories-identify -->

- [ ] F{{milestone}}.2: [Feature Name]
  ...
```

**Trace is required.** For each feature, identify the PRD requirement IDs it satisfies (usually CAP entries, sometimes SCP or CON). Compute the hashes per the rules in `prd-schema.md` — use its batch recipe to hash all requirements in one invocation.

A feature that traces to nothing means either the feature is out of scope or the PRD misses a requirement — raise it with the user before writing.

### Step 6: Regenerate Status Table

> **Implementation Note:** The full calculation and regeneration rules are defined in `roadmap-table-schema.md`. Reference that file for the complete algorithm. The steps below are a summary.

After adding features to the roadmap, regenerate the status table:

1. Apply the table schema you read at the start
2. Parse the full roadmap for all milestones and features
3. For each milestone: calculate percentage based on its features' statuses
4. For each feature: determine status (all new features start as `Not Started`)
5. Add feature rows after their parent milestone row, including the Trace column (IDs only, hashes stay in the body)
6. Determine group assignments for features:
   - Features with no inter-feature dependencies can share a group letter
   - Features that depend on other features get a later group
7. Replace the content between `<!-- ROADMAP-STATUS-TABLE:START -->` and `<!-- ROADMAP-STATUS-TABLE:END -->`
8. Update "Last synced" date

## Exploration Patterns

### Feature Discovery Questions

- "What user problem does this solve?"
- "What's the simplest version that still delivers value?"
- "What happens if we don't build this?"
- "Is this one feature or actually multiple features bundled together?"

### Challenge Questions

- "Could this feature be simpler?"
- "Is this feature doing too much?"
- "What could go wrong with this feature?"
- "How will users discover and learn this feature?"

### Dependency Mapping

Help visualize:
- Which features must come first (foundations)
- Which features unlock others (enablers)
- Which features can be built in parallel (independent)

## Completion

When features are added to roadmap.md:

**Recommend**: "Milestone {{milestone}} now has [N] features defined. Next steps:
- Run `/prd:stories-identify {{roadmap}} F{{milestone}}.1` to break the first feature into stories
- Or run `/prd:features-identify {{roadmap}} [next-milestone]` to decompose another milestone"
