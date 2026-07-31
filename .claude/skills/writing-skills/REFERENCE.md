# Skill authoring reference

Exhaustive companion to [SKILL.md](SKILL.md). Read the section you need.

## Contents

- [Frontmatter fields](#frontmatter-fields) — every field, semantics, defaults
- [Invocation and visibility](#invocation-and-visibility) — who can call a skill, settings-level overrides
- [Naming](#naming) — conventions and names to avoid
- [Description patterns](#description-patterns) — worked good/bad examples
- [Degrees of freedom](#degrees-of-freedom) — how prescriptive to be
- [Progressive disclosure patterns](#progressive-disclosure-patterns) — three layouts
- [Workflow and feedback loop patterns](#workflow-and-feedback-loop-patterns)
- [Output format and example patterns](#output-format-and-example-patterns)
- [Skills that bundle scripts](#skills-that-bundle-scripts)
- [Context lifecycle and cost](#context-lifecycle-and-cost)
- [String substitutions](#string-substitutions)
- [Anti-patterns](#anti-patterns) — the explicit list
- [Evaluating a skill](#evaluating-a-skill)
- [Marketplace mechanics](#marketplace-mechanics) — this repo specifically
- [Doc discrepancies to be aware of](#doc-discrepancies-to-be-aware-of)
- [Sources](#sources)

## Frontmatter fields

Every field is optional in Claude Code; write `name` and `description` anyway
([why](#doc-discrepancies-to-be-aware-of)). Booleans accept
`true/false/yes/no/on/off/1/0`.

| Field | Semantics |
|---|---|
| `name` | Display name in listings. Max 64 chars, lowercase letters/digits/hyphens, no XML tags, may not contain the reserved words `anthropic` or `claude`. For personal/project skills the *command* still comes from the directory name; for **plugin** skills `name` sets the last command segment after the plugin prefix. |
| `description` | What the skill does and when to use it. Non-empty, max 1024 chars, no XML tags. Falls back to the first paragraph of the body if omitted. Combined `description` + `when_to_use` is truncated at 1536 chars in the listing. |
| `when_to_use` | Extra trigger phrases / example requests, appended to `description` in the listing; counts toward the 1536-char cap. |
| `argument-hint` | Autocomplete hint, e.g. `[issue-number]`. |
| `arguments` | Named positional arguments for `$name` substitution. Space-separated string or YAML list; names map to positions in order. |
| `disable-model-invocation` | `true` = only you can invoke it, and the description is kept out of context entirely. Also blocks preloading into subagents and scheduled-task firing. Default `false`. |
| `user-invocable` | `false` = hidden from the `/` menu; Claude can still invoke it. Controls menu visibility only, not Skill-tool access. Default `true`. |
| `allowed-tools` | Tools pre-approved for the turn that invokes the skill; the grant clears on your next message. Does *not* restrict anything. Space/comma-separated or YAML list. In a project's `.claude/skills/`, takes effect only after the workspace trust dialog — review project skills before trusting a repo, since a skill can grant itself broad access. |
| `disallowed-tools` | Tools removed from the pool while the skill is active; clears on your next message. Can't remove `EndConversation` while other tools remain. |
| `model` | Model for the rest of the turn; accepts `/model` values or `inherit`. Not persisted. |
| `effort` | `low`/`medium`/`high`/`xhigh`/`max` while active; overrides session effort. |
| `context` | `fork` runs the skill in an isolated subagent whose prompt *is* the skill body. Only meaningful for skills with an actionable task — a pure guidelines skill forked this way returns nothing useful. |
| `agent` | Subagent type used when `context: fork` (`Explore`, `Plan`, `general-purpose`, or a custom `.claude/agents/` type). Defaults to `general-purpose`. `Explore`/`Plan` skip CLAUDE.md. |
| `background` | With `context: fork`, `false` waits for the result in the invoking turn instead of backgrounding it. Default `true`. Backgrounded forks get the narrower background-subagent tool set and their edits fall outside `/rewind`. |
| `paths` | Glob patterns limiting automatic activation to work on matching files. |
| `hooks` | Hooks scoped to this skill's lifecycle. |
| `shell` | `bash` (default) or `powershell` for `` !`cmd` `` blocks. |
| `license` | Free text; Anthropic's own skills use `license: Complete terms in LICENSE.txt`. Not interpreted by Claude Code. |

Malformed YAML doesn't break the skill: Claude Code loads the body with empty
metadata, so `/name` still works but automatic triggering silently dies. Run
`claude --debug` to see the parse error.

## Invocation and visibility

| Frontmatter | You can invoke | Claude can invoke | Loaded when |
|---|---|---|---|
| (default) | yes | yes | description always in context; body on invoke |
| `disable-model-invocation: true` | yes | no | description **not** in context; body on your invoke |
| `user-invocable: false` | no | yes | description always in context; body on invoke |

Permission rules give a second lever: `Skill(commit)`, `Skill(review-pr *)` in
allow/deny lists, or denying `Skill` outright. The `skillOverrides` setting
(`on` / `name-only` / `user-invocable-only` / `off`) changes visibility without
editing a shared repo's SKILL.md — useful for checked-in project skills, but it
does not apply to plugin skills (manage those with `/plugin`).

## Naming

Directory name = command name, so it must be kebab-case. Prefer **gerund form**,
which reads as the activity the skill provides:

- Good: `processing-pdfs`, `analyzing-spreadsheets`, `writing-documentation`,
  `reviewing-migrations`
- Acceptable: noun phrases (`pdf-processing`), action form (`process-pdfs`)
- Avoid: `helper`, `utils`, `tools`, `documents`, `data`, `files`; anything
  containing `anthropic` or `claude`; inconsistent patterns inside one plugin

Name reference files for their content too — `form_validation_rules.md`, not
`doc2.md`; `reference/finance.md`, not `docs/file1.md`.

## Description patterns

Effective:

```yaml
description: Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction.
```

```yaml
description: Generate descriptive commit messages by analyzing git diffs. Use when the user asks for help writing commit messages or reviewing staged changes.
```

Pushy, to counter under-triggering (skill-creator's own advice):

> Instead of "How to build a fast dashboard for internal data.", write "How to
> build a fast dashboard for internal data. Make sure to use this skill whenever
> the user mentions dashboards, data visualization, internal metrics, or wants to
> display any kind of company data, even if they don't explicitly ask for a
> 'dashboard.'"

With an explicit negative boundary (pattern used by Anthropic's `xlsx` and `docx`
skills, where sibling skills compete):

```yaml
description: >-
  Use this skill any time a spreadsheet file is the primary input or output …
  Do NOT trigger when the primary deliverable is a Word document, HTML report,
  standalone Python script, or database pipeline, even if tabular data is involved.
```

Ineffective: `Helps with documents`, `Processes data`, `Does stuff with files`,
`I can help you process Excel files` (first person), `You can use this to…`
(second person).

## Degrees of freedom

Match specificity to how fragile and variable the task is. The analogy from the
official guide: a narrow bridge with cliffs needs exact guardrails; an open field
needs a direction and trust.

- **High freedom** — prose steps. Use when multiple approaches are valid and
  context decides. Example: code review process.
- **Medium freedom** — pseudocode or a parameterised script. Use when a preferred
  pattern exists but variation is fine.
- **Low freedom** — an exact command, few or no parameters, "do not modify this
  command". Use when operations are fragile, order matters, or consistency is
  critical. Example: database migrations.

## Progressive disclosure patterns

Three loading levels: metadata always in context → SKILL.md body on trigger →
bundled files and scripts on demand (zero cost until read; scripts cost only
their output). Anthropic's own layout convention:

```
skill-name/
├── SKILL.md          # required: overview + navigation
├── scripts/          # executable code for deterministic/repetitive work
├── references/       # docs loaded into context as needed
└── assets/           # files used in output (templates, icons, fonts)
```

**Pattern 1 — high-level guide with references.** Quick-start inline; advanced
topics as one-line pointers (`**Form filling**: See FORMS.md`).

**Pattern 2 — domain-specific organisation.** For multi-domain skills, one file
per domain so irrelevant context never loads:

```
bigquery-skill/
├── SKILL.md              # overview + which file for which question
└── reference/
    ├── finance.md
    ├── sales.md
    └── marketing.md
```

Suggesting `grep -i "revenue" reference/finance.md` in SKILL.md lets Claude
target a section instead of a whole file.

**Pattern 3 — conditional details.** Basic content inline, links for the edge
cases (`**For tracked changes**: See REDLINING.md`).

Hard rules: **one level deep** (Claude may `head -100` a file it reached through
another reference, getting partial information), and a **table of contents** on
any reference file over ~100 lines so a partial read still reveals the scope.

## Workflow and feedback loop patterns

Give complex work a checklist Claude can copy into its response and tick off:

```
Research Progress:
- [ ] Step 1: Read all source documents
- [ ] Step 2: Identify key themes
- [ ] Step 3: Cross-reference claims
- [ ] Step 4: Create structured summary
- [ ] Step 5: Verify citations
```

Then one short section per step. Clear steps stop Claude skipping validation.

Pair it with a feedback loop — run validator → fix → repeat — and state the gate
explicitly ("only proceed when validation passes"). The validator can be a script
*or* a document: "review against STYLE_GUIDE.md, note each issue, revise, re-check".

For open-ended batch or destructive work use **plan-validate-execute**: Claude
writes a structured plan file, a script validates it, only then does it execute.
Catches errors before anything is touched and makes the plan iterable.

If a workflow grows large, move it to its own file and tell Claude which file to
read for which situation.

Conditional workflows should route at a decision point:

```markdown
1. Determine the modification type:
   **Creating new content?** → follow "Creation workflow"
   **Editing existing content?** → follow "Editing workflow"
```

## Output format and example patterns

For strict formats, give the exact template and say so ("ALWAYS use this exact
template structure"). For flexible ones, label it: "here is a sensible default
format, but use your best judgment".

Where quality depends on style, give input/output pairs rather than adjectives —
examples convey level of detail better than descriptions. Keep examples concrete;
abstract placeholders teach nothing.

## Skills that bundle scripts

- **Solve, don't defer.** Handle `FileNotFoundError`/`PermissionError` in the
  script instead of letting it fail for Claude to debug.
- **No voodoo constants.** Justify every value in a comment (`# Three retries
  balances reliability vs speed`), never `TIMEOUT = 47`.
- **Prefer a bundled script over generated code** for deterministic work: more
  reliable, fewer tokens, no generation time, consistent across uses. A strong
  signal to bundle one is noticing several test runs independently writing the
  same helper.
- **State execution intent.** "Run `analyze_form.py` to extract fields" (execute)
  vs "See `analyze_form.py` for the algorithm" (read). Execution is preferred.
- **Declare dependencies.** Don't assume a package is installed; give the install
  command. Note the environment: claude.ai can install from npm/PyPI; the Claude
  API code-execution environment has no network access.
- **Verbose validation errors** ("Field 'signature_date' not found. Available
  fields: …") so Claude can self-correct.
- **Forward slashes always**, even on Windows.
- **Fully qualify MCP tool names** as `ServerName:tool_name` (`BigQuery:bigquery_schema`)
  or Claude may not find the tool when several servers are loaded.
- Pre-approve a bundled script without prompting by matching the body's command
  in frontmatter: `allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/render.sh *)`.

## Context lifecycle and cost

The rendered body enters the conversation once and **stays for the session**;
Claude Code does not re-read the file on later turns. Write standing instructions
("throughout this task, …"), not one-time steps. Re-invoking with identical
rendered content adds a short "already loaded" note rather than a second copy.

`allowed-tools` grants clear on your next message even though the body persists.

Auto-compaction re-attaches the most recent invocation of each skill, keeping the
first 5,000 tokens each within a combined 25,000-token budget, filled from the
most recent — so older skills can be dropped after compaction. Re-invoke a large
skill after compaction if its guidance still matters.

The listing of names+descriptions has its own budget, 1% of the context window
(`skillListingBudgetFraction`, or `SLASH_COMMAND_TOOL_CHAR_BUDGET`). On overflow,
descriptions are dropped starting with the least-used skills — another reason to
front-load the key use case. `/doctor` estimates the listing's cost;
`/context` reports its post-budget size.

If a skill "stops working" mid-session, the content is usually still there and
the model is choosing something else: strengthen the description and the
instruction, or enforce it deterministically with a hook.

## String substitutions

Available in skill body content. Only `${CLAUDE_SKILL_DIR}` and
`${CLAUDE_PROJECT_DIR}` are *also* substituted in `allowed-tools` Bash rules;
`${CLAUDE_PLUGIN_ROOT}` is not, so a rule written with it stays a literal string,
never matches, and the command prompts every time.

| Variable | Meaning |
|---|---|
| `$ARGUMENTS` | Everything passed after the command. If absent from the body, arguments are appended as `ARGUMENTS: <value>`. |
| `$ARGUMENTS[N]` / `$N` | Positional argument, 0-based. Shell-style quoting; an unmatched index stays literal. |
| `$name` | Named argument declared in `arguments`. Unmatched → empty string. |
| `${CLAUDE_SESSION_ID}` | Current session id. |
| `${CLAUDE_EFFORT}` | Active effort level. |
| `${CLAUDE_SKILL_DIR}` | Directory holding this `SKILL.md` (for a plugin skill, the skill subdirectory — not the plugin root). |
| `${CLAUDE_PROJECT_DIR}` | Project root. |
| `${CLAUDE_PLUGIN_ROOT}` | Plugin install directory. Resolves anywhere in skill and agent content. Use it for files shared across a plugin's skills. |
| `${CLAUDE_PLUGIN_DATA}` | Plugin directory that survives updates — for installed deps and caches, not for bundled files. |

Escape a literal `$` before a digit or `ARGUMENTS` with a backslash: `\$1.00`.

**Dynamic context injection**: `` !`command` `` runs *before* Claude sees the
content and is replaced by its output; a fenced ```` ```! ```` block does the same
for multi-line commands. It's preprocessing, not something Claude executes, and
output is not re-scanned for further placeholders. The `!` must start a line or
follow whitespace. `disableSkillShellExecution: true` disables it by policy.

Including the word `ultrathink` anywhere in the body requests deeper reasoning
for that run.

## Anti-patterns

Explicitly called out by Anthropic:

- **Verbose explanation of things Claude knows** — the single most common bloat.
  "PDF (Portable Document Format) files are a common file format…" earns nothing.
- **Vague descriptions** — the top cause of a skill never triggering.
- **First/second person in the description** — degrades discovery.
- **Bodies over 500 lines** — split instead.
- **Nested references** (SKILL.md → advanced.md → details.md) — leads to partial reads.
- **Time-sensitive information** ("before August 2025, use the old API") — use an
  `## Old patterns` `<details>` block for superseded material.
- **Inconsistent terminology** — pick one of endpoint/URL/route and stay with it.
- **Too many options** — "you can use pypdf, or pdfplumber, or PyMuPDF, or…".
  Give one default plus an escape hatch for the known exception.
- **Windows-style paths** — `scripts\helper.py` breaks on Unix.
- **Rigid ALL-CAPS MUST/ALWAYS/NEVER walls** — a yellow flag. Explain the reason
  instead; models have good theory of mind and follow understood constraints
  better than shouted ones. Reserve hard directives for genuinely fragile steps.
- **Overfitting to your test cases** — a skill is used many times across many
  prompts. When a stubborn issue appears, try a different framing rather than
  adding another narrow rule.
- **Deferring errors from scripts to Claude**, magic constants, assuming packages
  are installed.
- **`context: fork` on a guidelines-only skill** — the subagent gets rules and no task.
- **Content that would surprise the user given the skill's stated purpose** —
  skills must not contain malware, exfiltration, or misleading behaviour.

## Evaluating a skill

Build evaluations *before* writing extensive documentation, so the skill solves a
real gap: run the task with no skill, record the specific failures, write three
scenarios covering them, measure the baseline, write the minimum instructions that
pass, iterate.

Triggering and output quality are separate measurements. Test both in a **fresh
session** — authoring context masks gaps — and compare against a run with the
skill disabled (`skillOverrides: {"<name>": "off"}`).

Eval record shape:

```json
{
  "skills": ["pdf-processing"],
  "query": "Extract all text from this PDF file and save it to output.txt",
  "files": ["test-files/document.pdf"],
  "expected_behavior": [
    "Reads the PDF using an appropriate library or CLI tool",
    "Extracts text from all pages without missing any",
    "Saves output to output.txt in readable form"
  ]
}
```

Trigger-tuning queries should be realistic and hard: 8–10 should-trigger
(varied phrasing, some not naming the file type), 8–10 should-**not**-trigger
that are genuine near-misses sharing keywords. `"Write a fibonacci function"` as
a negative for a PDF skill tests nothing. Note that Claude only consults skills
for work it can't trivially do itself, so trivial queries are poor tests.

Test across the models you'll actually use: Haiku may need more guidance, Opus
punishes over-explanation.

The `skill-creator` plugin (`/plugin install skill-creator@claude-plugins-official`)
automates the loop — `evals/evals.json`, per-case subagents, grading, with/without
benchmark, blind A/B between versions, and description tuning.

Iterate with two Claudes: one helps you write and refine the skill, a fresh one
uses it on real tasks. Bring observations from the second back to the first.
Watch for unexpected exploration order, references never followed, a file read
every single time (promote it into SKILL.md), and files never read at all (cut
them or signal them better).

## Marketplace mechanics

For this repo (`pilo-tribe-ai/marketplace`):

- Plugin skills live at `plugins/<plugin>/skills/<name>/SKILL.md` and are namespaced
  `/<plugin>:<name>`, so they can't collide with personal or project skills. The
  bare `/<name>` also works unless another command claims it.
- A plugin with a root `SKILL.md`, no `skills/` directory and no `skills` manifest
  field loads as a single-skill plugin.
- Material several of a plugin's skills genuinely need *at runtime* is reached
  from a skill body as `${CLAUDE_PLUGIN_ROOT}/<file>.md`. Build material —
  framework notes, research, design rationale — is not that, and should stay
  unlinked: a skill that reads theory mid-task pays context for something that
  doesn't change what it does. `plugins/ai-fluency/REFERENCE.md` is deliberately
  linked only from the plugin README, for humans — never from a skill body.
- `claude plugin validate .` checks the manifests — `marketplace.json`, or
  `plugin.json` when pointed at a plugin directory — **not** skill frontmatter. A
  skill `name` with uppercase, underscores, or the reserved word `claude` still
  passes.
- Registering, validating and locally testing a plugin: the repo README's
  "Adding a plugin" is the source of truth for that sequence.
- `skillOverrides` does not affect plugin skills. Live change detection covers
  `SKILL.md` text; changes to a plugin's `hooks/`, `agents/`, `.mcp.json` need
  `/reload-plugins`.

Precedence for non-plugin skills: enterprise > personal > project, and any of
those overrides a bundled skill of the same name.

## Doc discrepancies to be aware of

- **Required frontmatter.** The Claude Code docs say every field is optional and
  only `description` is recommended; the platform authoring guide and the Agent
  Skills standard say `name` and `description` are both required. Writing both
  satisfies either reading. Anthropic's own skills in `anthropics/skills` all set
  `name` + `description`.
- **`compatibility`.** `skill-creator` lists a `compatibility` field ("required
  tools, dependencies — optional, rarely needed"); it does not appear in the
  Claude Code frontmatter table. Treat it as unsupported here.
- **The 500-line limit.** The platform guide states it as a rule ("keep under 500
  lines for optimal performance"); `skill-creator` softens the associated word
  counts to "approximate … feel free to go longer if needed". Anthropic's own
  skills mostly land at 30–250 lines, with `skill-creator` (485) and `claude-api`
  (546) as the outliers. Treat 500 as the point at which you split, not a hard cap.
- **"You don't need a skill for writing skills."** The platform guide notes Claude
  natively understands the skill format. That is about the mechanics; this skill
  exists to enforce the *quality bar and repo conventions*, which aren't in the
  format.

## Sources

- Skill authoring best practices — https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Extend Claude with skills (Claude Code) — https://code.claude.com/docs/en/skills
- Agent Skills overview — https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- Plugins reference — https://code.claude.com/docs/en/plugins-reference
- Plugin marketplaces — https://code.claude.com/docs/en/plugin-marketplaces
- `anthropics/skills` (incl. `skills/skill-creator/SKILL.md`) — https://github.com/anthropics/skills
- `skill-creator` plugin — https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator
- Evaluating skill output quality — https://agentskills.io/skill-creation/evaluating-skills
- Agent Skills open standard — https://agentskills.io
