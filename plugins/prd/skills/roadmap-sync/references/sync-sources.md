# Roadmap Sync Sources Reference

## GitHub Issues & PRs

### Search Patterns

When scanning GitHub for roadmap item references, use these patterns:

1. **Issue/PR title matching**: Search for item IDs (M1, F1.1, S1.1.1) in titles
2. **Issue/PR body matching**: Search for item IDs in issue/PR bodies
3. **Label matching**: Look for labels that match milestone or feature names
4. **Branch name matching**: Branches named with item IDs (e.g., `feature/F1.1-auth`)

### GitHub CLI Commands

```bash
# Search issues referencing a specific item ID
gh issue list --search "F1.1" --state all --json number,title,state,labels

# Search PRs referencing a specific item ID
gh pr list --search "F1.1" --state all --json number,title,state,mergedAt

# Get details of a specific issue
gh issue view <number> --json title,state,labels,body
```

### Status Inference from GitHub

| GitHub Signal | Inferred Status |
|---------------|----------------|
| PR merged that references item | `Completed` |
| PR open (not draft) that references item | `In Progress` |
| PR draft that references item | `In Progress` |
| Issue open + assigned | `In Progress` |
| Issue open + unassigned | `Not Started` (weak signal) |
| Issue closed as completed | `Completed` |
| Issue closed as not planned | No change |

### Conflict Resolution

When multiple signals conflict:
- PR merged > Issue open (merged PR wins)
- PR open > Issue status (active PR indicates progress)
- Most recent signal wins when same type

### Statuses Outside These Signals

- `Needs Review` is set and cleared only by the requirement drift check (trace hash mismatch against the PRD) — never by GitHub or code signals, and it overrides them until a human resolves it.
- `Not Planned` marks a placeholder milestone from `/prd:plan`; skip it during GitHub and code scans.

## Code File Existence Checks

### Verification Patterns

For each feature marked as `Completed` or `In Progress`, verify:

1. **Source files exist**: Check if expected source files/modules exist
   - Look for directories or files matching feature names
   - Check for imports/references to the feature in entry points

2. **Test files exist**: For completed features, verify test coverage
   - Look for test files matching the feature name pattern
   - Check for test directories corresponding to features

### Verification Commands

```bash
# Search for files matching a feature name
find . -name "*auth*" -not -path "*/node_modules/*" -not -path "*/.git/*"

# Check if feature-related code exists
grep -r "auth" --include="*.ts" --include="*.py" -l

# Check for test files
find . -path "*/test*" -name "*auth*"
```

### Status Inference from Code

| Code Signal | Inferred Status |
|-------------|----------------|
| Source files + test files exist | Supports `Completed` |
| Source files exist, no tests | Supports `In Progress` |
| No source files found | Supports `Not Started` |
| Feature directory exists but empty | `Not Started` |
