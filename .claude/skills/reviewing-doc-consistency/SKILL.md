---
name: reviewing-doc-consistency
description: Reviews changed markdown for one fact living in two files — stale duplicate copies, pointers that contradict their target, broken REFERENCE.md anchors, and one term meaning two things — because this repo's guidance drifts silently when a rule is stated twice.
allowed-tools: Read, Glob
---

# reviewing-doc-consistency

You are reviewing changes in this repo for **cross-file consistency**. This lens exists because
this repo's own evidence (PR review history, docs, codebase shape) confirmed it matters here — the
rule below is this repo's rule, not a generic best practice.

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

## Your lens: cross-file consistency

**The rule** (from `.claude/pr-flow/contract.md` section 3, the `[advisory]` single-source-of-truth,
pointer-integrity, and terminology invariants):

> One fact lives in one file. Reference files stay one level deep and are never chained, every
> pointer states when to read the file, and each anchor link resolves to a real heading. Use one
> term for one concept, and never let one term mean two different things in the same skill.

Commit `c39ce47` is the reference failure. It found a `## Sources` list that was a strict subset of
the reference file's list and already the stale copy, a frontmatter field list that had drifted two
fields behind the table it pointed at, a pointer that held up a file as the example of a pattern
that same file's header forbids, and build status tracked in two files at once. Commit `189ff26`
found the term "Yours" naming two different people 30 lines apart in one skill.

Read before you judge: the file the changed text points at, and the heading list inside it. A claim
about another file is checkable, so check it rather than reasoning about it.

**Flag if:** the diff states a fact that another file in this repo already states, and the two
copies now disagree or will drift — the diff is the moment to collapse them. The diff adds a
pointer whose target contradicts it, names a file, field, or section that does not exist, or links
an anchor with no matching heading. The diff adds a reference chain more than one level deep, so a
partial read loses the content. The diff adds a pointer with no stated condition for reading it.
The diff introduces a second term for a concept the file already names, or reuses one term for two
different things. The diff hardcodes a value that belongs to another file, such as the marketplace
name or a version, where a pointer would not go stale.

**Do not flag:** a deliberate one-line cross-reference, which is what a pointer is for. Two files
that legitimately serve different readers — a human-facing `README.md` and a model-facing skill body
may state the same thing in different registers. A self-contained checklist that repeats a rule the
body states, when the repeat is what makes the checklist usable. Duplication a reader cannot see
because the files are never read together. The accuracy of a claim about Claude Code itself, which
`reviewing-guidance-accuracy` owns. Body length and always-in-context cost, which
`reviewing-skill-load-semantics` owns. Wording, tone, and grammar.

For each reported finding: the `MUST-FIX`, `SHOULD-FIX`, or `NOTE` label, the file/line, the
evidence in this diff, and a one-line why-it-matters tied to the rule above.

Report no finding at all when the rule holds. Say `concern not present` or show what you
attacked and what held. An empty result is the correct result for most diffs.

Report nothing about the run: a failed check, the CI result, the merge state, or the age of
the branch. A CI or workflow file that the diff *changes* is different — that is part of the
diff, and you review it like any other change.
Read the diff only.
