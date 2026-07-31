---
name: reviewing-skill-frontmatter
description: Reviews changed SKILL.md frontmatter against this repo's authoring rules — name matches its directory, kebab-case, no reserved words, third-person description under 1024 characters with real triggers — because no command in this repo checks any of it.
allowed-tools: Read, Glob
---

# reviewing-skill-frontmatter

You are reviewing changes in this repo for **skill frontmatter correctness**. This lens exists
because this repo's own evidence (PR review history, docs, codebase shape) confirmed it matters
here — the rule below is this repo's rule, not a generic best practice.

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

## Your lens: skill frontmatter

**The rule** (from `.claude/pr-flow/contract.md` section 3, third `[blocking]` invariant, plus the
`[advisory]` context-economy invariant):

> A skill's frontmatter `name` equals its directory basename, is kebab-case, and never contains the
> reserved words `claude` or `anthropic`. In a plugin skill the `name` sets the command's last
> segment.

No gate in this repo checks this. The gap is measured: a skill named `Claude_Delegation_UPPER` —
uppercase, underscores, and the reserved word `claude` at once — passes both
`claude plugin validate` commands. See the contract's section 2 before you drop anything here as
gate-owned.

The full field table and the description rules are in
`.claude/skills/writing-skills/SKILL.md` and `.claude/skills/writing-skills/REFERENCE.md`. Read the
frontmatter table there before you judge whether a field exists or what it defaults to. `name` and
`description` are the two fields every skill in this repo writes.

**Flag if:** a changed `SKILL.md` has a `name` that does not equal its directory basename, is not
kebab-case, exceeds 64 characters, or contains `claude` or `anthropic`. The frontmatter does not
parse as YAML, which silently kills automatic triggering while the slash command still works. The
`description` is missing, empty, over 1024 characters, written in the first or second person, or
states no concrete trigger — the description is the whole triggering mechanism, so a vague one
means the skill never fires. A field appears that the field table does not document, or a field
carries a value the table does not allow. An invocation default is restricted
(`disable-model-invocation`, `user-invocable`) with no stated reason, which hides the skill from
half its callers.

**Do not flag:** a `description` you would word differently, when it already states what the skill
does and a concrete trigger. A long `description` that spends its length on real triggers — the
cap is 1024 characters, not a style budget. Body content, structure, and length, which
`reviewing-skill-load-semantics` owns. A literal path-variable token in a body, which that lens
also owns. Manifest JSON, which `reviewing-plugin-manifest` owns. Anything the contract's
section 2 gate list covers.

For each reported finding: the `MUST-FIX`, `SHOULD-FIX`, or `NOTE` label, the file/line, the
evidence in this diff, and a one-line why-it-matters tied to the rule above.

Report no finding at all when the rule holds. Say `concern not present` or show what you
attacked and what held. An empty result is the correct result for most diffs.

Report nothing about the run: a failed check, the CI result, the merge state, or the age of
the branch. A CI or workflow file that the diff *changes* is different — that is part of the
diff, and you review it like any other change.
Read the diff only.
