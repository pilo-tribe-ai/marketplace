---
name: reviewing-plugin-manifest
description: Reviews changed marketplace.json and plugin.json for registration and authority errors — a new plugin missing from the plugins array, fields duplicated from the authoritative manifest, and inert settings that mislead the next contributor.
allowed-tools: Read, Glob
---

# reviewing-plugin-manifest

You are reviewing changes in this repo for **plugin manifest correctness**. This lens exists
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

## Your lens: plugin manifests

**The rule** (from `.claude/pr-flow/contract.md` section 3, fourth `[blocking]` invariant and the
`[advisory]` single-source-of-truth invariant, both restating `README.md` step 2):

> A new plugin has an entry in the `plugins` array of `.claude-plugin/marketplace.json`. A new
> *skill* inside an existing plugin needs no manifest change: Claude Code discovers skills from
> `plugins/<plugin>/skills/`. `plugin.json` is the authority for `description` and `version`; do
> not repeat them in `marketplace.json`.

Commit `0de7df5` removed an inert `metadata.pluginRoot` for this reason: every entry already spelled
out its `./plugins/...` source, so the setting did nothing, but a contributor who trusted it and
shortened a future entry to a bare name would break that plugin's install.

Read before you judge: `.claude-plugin/marketplace.json`, the `plugin.json` of each plugin the diff
touches, and `README.md` step 2, which is this repo's stated procedure.

**Flag if:** the diff adds a plugin directory but no matching entry in the `plugins` array, so the
plugin cannot be installed. The diff adds an entry whose `source` does not resolve to a real
directory, or whose `name` does not match that plugin's `plugin.json` `name`. The diff repeats
`description` or `version` in a `marketplace.json` entry when `plugin.json` is the authority, so the
copy loses silently on divergence. The diff adds a manifest field that has no effect as written, or
whose declared value contradicts what every entry actually does — an inert setting is a trap for the
next contributor. The diff tells an author to add a manifest entry for a new *skill*, which is not a
real step.

**Do not flag:** JSON schema errors, required-field omissions, and source-resolution failures that
`claude plugin validate .` or `claude plugin validate ./plugins/<plugin>` already reports — read the
contract's section 2 first. A missing optional field. The human-readable plugin table in `README.md`
carrying different wording than the manifest, which is a different register for a different reader.
Skill frontmatter, which `reviewing-skill-frontmatter` owns. Version-number policy, since this repo
states none.

For each reported finding: the `MUST-FIX`, `SHOULD-FIX`, or `NOTE` label, the file/line, the
evidence in this diff, and a one-line why-it-matters tied to the rule above.

Report no finding at all when the rule holds. Say `concern not present` or show what you
attacked and what held. An empty result is the correct result for most diffs.

Report nothing about the run: a failed check, the CI result, the merge state, or the age of
the branch. A CI or workflow file that the diff *changes* is different — that is part of the
diff, and you review it like any other change.
Read the diff only.
