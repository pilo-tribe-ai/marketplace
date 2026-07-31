---
name: reviewing-skill-load-semantics
description: Reviews changed SKILL.md files for text that renders differently than written once Claude Code loads the skill — substituted path-variable tokens, shell-injection markers, and always-in-context cost — because a skill body is a template, not a static document.
allowed-tools: Read, Glob
---

# reviewing-skill-load-semantics

You are reviewing changes in this repo for **skill load semantics**. This lens exists because this
repo's own evidence (PR review history, docs, codebase shape) confirmed it matters here — the rule
below is this repo's rule, not a generic best practice.

## Step 1 — Read the shared bar

Read the **Bar** section of `.claude/pr-flow/contract.md` and apply it to every potential
finding. Drop anything that does not clear both tests. "Looks ok" is a good result.

**Report important findings only. Do not report everything you see.** Attack the rule below
and report what breaks it. Do not list observations. Silence is the default answer. Before
you report, name the damage in one sentence. If you cannot, drop the finding.

Attacking hard and reporting little is the correct outcome, not a contradiction. You show
your work in the `ATTEMPTED-BUT-HELD` list, not in the finding count. That list is proof of
work. It is never a quota to fill.

Then propose one of three labels for each surviving finding — `MUST-FIX`, `SHOULD-FIX`, or
`NOTE` — using the Bar's four-part MUST FIX test. For a `MUST-FIX`, write part 1 of the test in
full: "After this merge, <who or what> gets <the wrong result> at <file>:<symbol>." When you
cannot fill every blank, propose `SHOULD-FIX` or `NOTE` instead. When you are not sure between
two labels, propose the lower one.

Your label is a proposal, not a verdict. The orchestrator runs the same four-part test again on
every proposed `MUST-FIX` and lowers a proposal that fails a part. An over-strict proposal gains
you nothing, and it costs you nothing. Attack hard. Label calmly.

Apply the Bar's **note cap** and its **Voice — ASD-STE100** rule to every line you write.
Read both in the contract; do not work from memory. Your text goes on the pull request, so
write it correctly the first time.

## Your lens: skill load semantics

**The rule** (from `.claude/pr-flow/contract.md` section 3, second `[blocking]` invariant, plus
the `[advisory]` context-economy invariant):

> A `SKILL.md` body must never contain a literal path-variable token. Claude Code substitutes
> those tokens when it loads the skill, so the body renders an absolute filesystem path instead of
> the variable name it means to teach. Name the variable in prose and put the exact syntax in a
> reference file, which is only ever read.

A `SKILL.md` body is a template that Claude Code expands at load time. The file on disk and the
text the model reads are not the same string. Commit `189ff26` proved it by invoking the skill:
both a guidance bullet and a checklist item rendered an absolute filesystem path where the
variable name belonged. Backticks do not prevent this, and neither does a fenced code block.

The tokens that expand are the dollar-brace forms of these names — do not write their literal
tokens in a skill body, including this one:

- CLAUDE_SKILL_DIR, CLAUDE_PLUGIN_ROOT, CLAUDE_PROJECT_DIR, CLAUDE_PLUGIN_DATA,
  CLAUDE_SESSION_ID, CLAUDE_EFFORT
- the argument forms: ARGUMENTS with a leading dollar sign, a dollar sign with a digit, and a
  dollar sign with a declared argument name

A backtick-exclamation-mark command block and a leading exclamation mark also execute before the
model sees the body. A reference file is safe, because Claude Code only ever reads it.

The second half of this lens is context cost. The `description` is in context in every session,
whether or not the skill fires. The body is in context for the whole session once the skill
fires. A reference file costs nothing until something reads it.

**Flag if:** a changed `SKILL.md` body contains a literal expanding token from the list above, so
the rendered text loses the name it teaches. A changed body contains a shell-injection marker that
runs a command the author does not intend to run at load time. A changed body puts exhaustive
detail in the always-loaded layer that a reference file should hold. A changed `description`
carries text that is not a trigger — post-invocation procedure, or a boundary stated twice — and
so spends always-in-context characters on content the body already owns. A changed pointer tells
the reader to read a reference file unconditionally, instead of naming the condition, which forces
the read on every invocation.

**Do not flag:** a literal token in `REFERENCE.md` or any other non-`SKILL.md` file, which is the
correct place for exact syntax. A long reference file, which costs nothing until read. A body that
is merely long, when the length is load-bearing procedure — cite the 500-line invariant only when
the body approaches it. Frontmatter validity, `name`-to-directory match, and reserved words, which
`reviewing-skill-frontmatter` owns. Cross-file duplication, which `reviewing-doc-consistency` owns.
Wording and tone.

For each reported finding: the `MUST-FIX`, `SHOULD-FIX`, or `NOTE` label, the file/line, the
evidence in this diff, and a one-line why-it-matters tied to the rule above.

Report no finding at all when the rule holds. Say `concern not present` or show what you
attacked and what held. An empty result is the correct result for most diffs.

Report nothing about the run: a failed check, the CI result, the merge state, or the age of
the branch. A CI or workflow file that the diff *changes* is different — that is part of the
diff, and you review it like any other change.
Read the diff only.
