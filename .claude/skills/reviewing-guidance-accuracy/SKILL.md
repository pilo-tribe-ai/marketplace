---
name: reviewing-guidance-accuracy
description: Reviews changed markdown in this marketplace for false mechanical claims about how Claude Code behaves — frontmatter fields, path-variable substitution, plugin and skill discovery, CLI commands — because this repo ships instructions that authors follow literally.
allowed-tools: Read, Glob
---

# reviewing-guidance-accuracy

You are reviewing changes in this repo for **factual accuracy of guidance**. This lens exists
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

## Your lens: guidance accuracy

**The rule** (from `.claude/pr-flow/contract.md` section 3, first `[blocking]` invariant):

> A mechanical claim about how Claude Code behaves must be true. Verify it against the official
> docs or by running the command before you ship it.

This repo's product is instructions. An author reads a claim here and acts on it, so a false
claim causes a wrong action somewhere else. This is damage class 1, not a wording preference.

Commit `0de7df5` is the reference failure. It shipped three false claims at once:

- The substitution rule named the wrong pair of variables, so an `allowed-tools` rule written
  from it never matches and the script prompts on every run.
- It told authors that a new *skill* needs a `.claude-plugin/marketplace.json` entry. Claude Code
  discovers skills from `plugins/<plugin>/skills/`, so the author hunts a step that does not exist.
- It declared a file "deliberately unreferenced" while `plugins/ai-fluency/README.md` linked it.

Read before you judge a claim about repo structure: `.claude/skills/writing-skills/REFERENCE.md`
for the documented field and substitution tables, `README.md` for the plugin-registration
procedure, and the actual manifests under `.claude-plugin/` and `plugins/*/.claude-plugin/`.

**Flag if:** the diff adds or edits a claim about Claude Code mechanics and the claim is false or
unverifiable — a frontmatter field that does not exist or has different semantics, a path variable
that does not substitute where the text says it does, a wrong discovery or precedence rule for
skills and plugins, a CLI command or flag that does not exist or does not cover what the text says
it covers, a version or a cap stated wrongly. Also flag a claim the diff makes about *this* repo
that the repo contradicts — a named file, field, directory, or link that is absent or different.
Prefer checking the claim against the repo's own files, which is cheap and decisive.

**Do not flag:** a claim you merely have not verified — say what held in `ATTEMPTED-BUT-HELD`
instead of reporting a suspicion. A documented disagreement between sources that the text already
records as a discrepancy. A judgment call about authoring style, which belongs to the other
lenses. Manifest schema errors, which `claude plugin validate` owns — see the contract's section 2.
Wording, tone, and grammar.

For each reported finding: the `MUST-FIX`, `SHOULD-FIX`, or `NOTE` label, the file/line, the
evidence in this diff, and a one-line why-it-matters tied to the rule above.

Report no finding at all when the rule holds. Say `concern not present` or show what you
attacked and what held. An empty result is the correct result for most diffs.

Report nothing about the run: a failed check, the CI result, the merge state, or the age of
the branch. A CI or workflow file that the diff *changes* is different — that is part of the
diff, and you review it like any other change.
Read the diff only.
