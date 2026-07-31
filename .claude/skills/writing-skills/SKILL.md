---
name: writing-skills
description: Authoring guidance for Claude Code Skills in this marketplace repo — frontmatter schema, description-writing rules, progressive disclosure, and a pre-ship checklist. Use whenever creating, editing, or reviewing a SKILL.md, adding a skill to a plugin under plugins/, splitting an over-long skill into reference files, or debugging a skill that won't trigger. Applies even to a "quick" single-file skill.
---

# Writing skills

Distilled from Anthropic's official guidance (sources at the bottom; full detail
in [REFERENCE.md](REFERENCE.md)). Apply it to skills in this marketplace —
`plugins/<plugin>/skills/<name>/SKILL.md` — and to repo-local ones in
`.claude/skills/`.

## First decide whether it should be a skill

- **Skill** — a procedure, checklist, or body of reference knowledge that should
  load *only when relevant*. This is the default for anything reusable.
- **CLAUDE.md** — short, always-true facts about the repo. If a CLAUDE.md section
  has grown into a procedure, move it into a skill.
- **Subagent** — you need an isolated context and a different tool set, not
  instructions. A skill can borrow one with `context: fork` + `agent:`.

## Where it goes, and how it gets invoked

| Placement | Command | Invocable by |
|---|---|---|
| `plugins/<plugin>/skills/<name>/SKILL.md` | `/<plugin>:<name>` | you and Claude |
| `.claude/skills/<name>/SKILL.md` | `/<name>` | you and Claude |

**Both are model- and user-invocable by default — no frontmatter needed for
that.** Only restrict deliberately:

- `disable-model-invocation: true` — user-only. For side-effecting workflows
  (deploy, commit, send) where *you* choose the timing.
- `user-invocable: false` — model-only. For background knowledge that isn't a
  meaningful action to type.

New plugin skills also need a `plugins/` entry in `.claude-plugin/marketplace.json`
(see the repo README) and a `claude plugin validate .` run.

## Frontmatter

Minimum viable, and what most skills should ship:

```yaml
---
name: reviewing-migrations          # lowercase/digits/hyphens, ≤64 chars, no "claude"/"anthropic"
description: <what it does>. Use when <concrete triggers>.   # ≤1024 chars
---
```

Everything is technically optional in Claude Code (`name` defaults to the
directory name), but write both: `description` drives triggering, and `name`
keeps the skill valid under the Agent Skills standard. In a **plugin** skill
`name` sets the last command segment, so keep it equal to the directory name.

Other fields worth knowing — `allowed-tools`, `disallowed-tools`, `when_to_use`,
`argument-hint`, `arguments`, `model`, `effort`, `context`, `agent`,
`background`, `paths`, `hooks` — are tabulated in
[REFERENCE.md](REFERENCE.md#frontmatter-fields). Don't add one without a reason.

## The description is the whole triggering mechanism

It is the only part always in context. Get it right first.

- **Third person, always.** "Extracts tables from PDFs" — never "I can help you…"
  or "You can use this to…". Mixed point-of-view degrades discovery.
- **What it does AND when to use it**, in that order. Put the key use case first;
  the listing truncates long entries.
- **Name the triggers users would actually say** — file extensions, tool names,
  the phrases from real requests. All "when to use" info lives here, not in the body.
- **Be a little pushy.** Claude under-triggers skills. `Use when working with X,
  or when the user mentions Y or Z, even if they don't say "<skill name>".`
- **Say when *not* to trigger** if a neighbouring skill could claim the request.

Vague descriptions (`Helps with documents`) are the top reason a skill never fires.

## Body: keep it short, imperative, and load-on-demand

Once invoked, the body sits in context for the rest of the session — every line
is a recurring cost.

- **Assume Claude is smart.** Only add what it doesn't already know. Delete any
  paragraph that explains a well-known concept or restates the description.
- **Imperative voice, no persona preamble.** No "You are an expert…". State what
  to do, not how it feels to do it.
- **Explain *why*, don't stack MUSTs.** All-caps ALWAYS/NEVER is a yellow flag —
  reframe as the reason the constraint exists. Reserve hard directives for
  genuinely fragile steps.
- **Match freedom to fragility.** Prose for judgment calls; an exact command for
  error-prone sequences. See [REFERENCE.md](REFERENCE.md#degrees-of-freedom).
- **Under 500 lines.** Approaching it means splitting, not trimming prose.
- **Progressive disclosure, one level deep.** SKILL.md is a table of contents:
  point to `REFERENCE.md`, `references/<domain>.md`, `scripts/`, `assets/` and
  say *when* to read each. Never chain SKILL.md → a.md → b.md; Claude partially
  reads nested files. Give any reference file over ~100 lines a table of contents.
- **One term per concept.** Don't alternate field/box/element.
- **No dates or "as of now".** Put superseded material under an `## Old patterns`
  `<details>` block instead.
- **Reference bundled files with `${CLAUDE_PLUGIN_ROOT}`** (plugin-wide files) or
  `${CLAUDE_SKILL_DIR}` (the skill's own directory) so paths resolve wherever the
  skill is installed. Forward slashes only.
- **Give multi-step work a copyable checklist** and a validate → fix → re-check
  loop. Patterns in [REFERENCE.md](REFERENCE.md#workflow-and-feedback-loop-patterns).

## Authoring workflow

1. **Find the real gap.** Do the task once without a skill and note what you had
   to supply repeatedly. Write the skill for *that*, not for imagined needs.
2. **Draft frontmatter first** — name, then description with explicit triggers.
3. **Write the minimum body** that closes the gap. Push exhaustive material into
   sibling files as you go.
4. **Re-read with fresh eyes and cut.** Ask of each paragraph: does Claude
   already know this? Does it earn its tokens?
5. **Test in a fresh session** — leftover authoring context hides gaps. Check two
   things separately: does it trigger on realistic prompts, and is the output
   right when it does? Compare against a run with the skill disabled.
6. **Iterate on observed behaviour**, not assumptions. If it triggers on the
   wrong requests, tighten the description; if it's ignored mid-task, make the
   rule more prominent or enforce it with a hook.

## Pre-ship checklist

```
- [ ] Directory name is kebab-case; gerund form preferred (reviewing-migrations)
- [ ] name matches the directory; description is third-person, ≤1024 chars
- [ ] Description states what it does AND concrete triggers, key use case first
- [ ] Invocation defaults left alone unless there's a reason to restrict
- [ ] Body under 500 lines, imperative, no persona preamble, no restated description
- [ ] References are one level deep, each with a stated "read this when…"
- [ ] Bundled paths use ${CLAUDE_PLUGIN_ROOT} / ${CLAUDE_SKILL_DIR}, forward slashes
- [ ] Consistent terminology; no dates or time-sensitive claims
- [ ] Examples concrete; one default recommended rather than a menu of options
- [ ] Multi-step work has a checklist and a verification loop
- [ ] Tested in a fresh session; triggering and output checked separately
- [ ] Plugin skills: marketplace.json updated, `claude plugin validate .` passes
```

## Sources

- [Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) — the canonical writing guide
- [Extend Claude with skills](https://code.claude.com/docs/en/skills) — Claude Code frontmatter, invocation, lifecycle
- [Plugins reference](https://code.claude.com/docs/en/plugins-reference) — plugin skill layout and path variables
- [anthropics/skills](https://github.com/anthropics/skills) — Anthropic's own skills, incl. the `skill-creator` meta-skill
- [Evaluating skills](https://agentskills.io/skill-creation/evaluating-skills) — eval format and iteration loop
