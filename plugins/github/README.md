# GitHub Plugin

Complete GitHub integration with interactive workflows for PRs, issues, and milestones. Uses a GitHub MCP server when one is available in your environment, and falls back to the `gh` CLI otherwise — **no MCP server is bundled**.

## What's New in v3.0.0

- **Removed the bundled GitHub MCP server** (`.mcp.json`). The plugin no longer packs or auto-starts an MCP server, so it adds no GitHub MCP tools to your context by default.
- **Adaptive tooling**: each command now prefers GitHub MCP tools **if a GitHub MCP server is already configured** in your environment, and otherwise uses the `gh` CLI (`gh pr`, `gh issue`, `gh label`, `gh project`, and `gh api` for milestones).
- **Auth**: when falling back to the CLI, authentication is handled by `gh auth login` — no `GITHUB_PERSONAL_ACCESS_TOKEN` env var required.

## Features

- 🔀 **Pull Requests**: Create PRs with intelligent title/description generation, draft mode, automerge, and merge strategy selection
- 📋 **Issues**: Create issues with smart label matching, project assignment, and worktree integration
- 🎯 **Milestones**: Create milestones with due dates and issue assignment
- 🔌 **Adaptive backend**: Prefers a GitHub MCP server if available, falls back to the `gh` CLI — no bundled MCP server, no forced context overhead
- 💬 **Interactive**: User-friendly prompts with emoji guidance

## Installation

```bash
claude plugin install github@404pilo
```

> **Requirement**: This plugin needs either a GitHub MCP server configured in your environment **or** the [GitHub CLI](https://cli.github.com/) installed and authenticated (`gh auth login`).

## Commands

### `/github:pr:create` - Create Pull Request

Interactive PR creation with:
- Automatic title and description generation
- Draft/ready for review selection
- Automerge configuration
- Merge strategy choice (squash/merge/rebase)

**Example:**
```bash
/github:pr:create
```

The command will:
1. ✅ Validate git state (clean working directory, feature branch)
2. 🔍 Check for existing PRs
3. 📊 Analyze changes since base branch
4. 📝 Generate human-readable title and description
5. ❓ Ask for your preferences (draft, automerge, merge strategy)
6. 🚀 Push and create the PR
7. ✅ Display PR URL and summary

### `/github:issue:create` - Create GitHub Issue

Interactive issue creation with:
- Auto-detected repository from git remote
- Smart label matching and creation
- Optional project assignment
- Acceptance criteria checklist
- Git worktree integration

**Example:**
```bash
/github:issue:create
# or with title hint
/github:issue:create Fix authentication timeout
```

The command will:
1. 🔧 Auto-detect or cache repository configuration
2. 📝 Guide you through issue type, title, description, and acceptance criteria
3. 🏷️ Smart match existing labels or offer to create new ones
4. 📋 Preview issue before creation
5. ✅ Create issue via the GitHub MCP server (if available) or the `gh` CLI
6. 📊 Optionally add to project board
7. 🌳 Offer to create worktree for immediate work

**Configuration:**
- First run: Auto-detects repo and optionally configures project
- Cached in `.claude/github-issues.json` for subsequent runs
- Reset by deleting the config file

### `/github:milestone:create` - Create GitHub Milestone

Interactive milestone creation with:
- Auto-detected repository from git remote
- Optional due date (ISO 8601 format)
- Initial state selection (open/closed)
- Issue assignment from existing issues
- Preview before creation

**Example:**
```bash
/github:milestone:create
# or with title hint
/github:milestone:create v1.0
```

The command will:
1. 🔧 Auto-detect or cache repository configuration
2. 📊 Show existing milestones for context
3. 📝 Guide you through title, description, due date, and state
4. 📋 Optionally select existing issues to assign
5. ✅ Preview milestone before creation
6. 🎯 Create milestone via GitHub REST API
7. 📌 Assign selected issues to milestone

**Configuration:**
- First run: Auto-detects repo from git remote
- Cached in `.claude/github-milestones.json` for subsequent runs
- Reset by deleting the config file

**Note**: Uses `gh api` for milestone operations, since neither the `gh` CLI nor the GitHub MCP server exposes a dedicated milestone tool.

## Requirements

- **Either** a GitHub MCP server configured in your environment, **or** the [GitHub CLI](https://cli.github.com/) (`gh`) installed and authenticated (`gh auth login`)
- Git repository with GitHub remote
- Clean working directory for PR creation

## Tool Strategy

This plugin **does not bundle an MCP server**. It adapts to whatever your environment provides:

1. **Prefer GitHub MCP tools** when a GitHub MCP server is configured (tools matching `mcp__github__*` or `mcp__plugin_github_github__*` are available)
2. **Fall back to the `gh` CLI** otherwise — `gh` subcommands (`gh pr`, `gh issue`, `gh label`, `gh project`) for first-class operations and `gh api` for REST endpoints without a subcommand (e.g. milestones)
3. Clear error messages if neither backend is available or a call fails

Milestone operations always use `gh api` because no MCP tool exposes them. This keeps your context lean when no MCP server is present, while still taking advantage of one when it is.

## Configuration

**Pull Requests:**
No configuration needed. The plugin automatically detects:
- Repository owner and name from git remote
- Base branch (main/master/develop)
- Current branch name

**Issues:**
Configuration cached in `.claude/github-issues.json` after first run:
- Repository owner and name (auto-detected from git remote)
- Project number and name (optional, user-selected)
- Reset by deleting the config file

**Milestones:**
Configuration cached in `.claude/github-milestones.json` after first run:
- Repository owner and name (auto-detected from git remote)
- Reset by deleting the config file

## Contributing

See the main [marketplace repository](https://github.com/404pilo/claude-code.marketplace) for contribution guidelines.

## License

MIT
