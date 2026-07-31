# PR review contract

The single source of truth for PR review in this repo. Human-editable. Both the executor
skills (`reviewing-prs` and the lifecycle skills) and every generated `reviewing-<concern>`
lens read this file. Four sections: **the Bar**, **Deterministic gates**, **Repo invariants**,
and the **Lens registry**.

This repo ships *instructions* — Claude Code skills and plugin manifests, not application code.
So a defect here is usually a true-sounding claim that sends an author or an agent to a wrong
action, not a crash. Review the prose as the product.

---

## 1. The Bar — what a finding must clear, and which findings hold up approval

A finding is reportable only if it clears **both** tests:

1. **Real** — concretely true in *this* diff, with evidence. Not speculative, not "could be
   cleaner," not future-hypothetical.

2. **Impactful if left unattended** — it would cause one or more of:
   - broken or incorrect behavior that ships — a skill that fails to load, renders differently
     than written, or triggers on the wrong requests,
   - a security or data-exposure breach — a skill that grants itself tool access a reader would
     not expect, or content that breaks the source license this repo attributes,
   - a violated **repo invariant** that section 3 marks `[blocking]` (see section 3). Section 3
     marks each invariant `[blocking]` or `[advisory]`. An invariant marked `[advisory]` is still
     reportable, at SHOULD FIX or NOTE, but not at MUST FIX,
   - **false guidance that an author or an agent follows to a wrong action** — this repo's product
     is instructions, so a wrong mechanical claim about Claude Code is a defect, not a wording
     preference,
   - a **broken contract with installers** — a changed skill command name, a plugin that no longer
     installs, or a marketplace entry that no longer resolves,
   - a deterministic check defeated by a lie (e.g. mis-labeling a change to dodge a gate).

**Hard exclusion — never re-flag what a deterministic gate already owns.** See section 2 for
the exact gate commands. Style, formatting, and naming *preferences* that no repo invariant
binds are dropped.

**The first decision is binary: report or drop.** The buckets below sort what you report. They
never change whether you report it. The bias is permissive — only clear, real concerns surface.
"PR looks ok as is" is a valid and good result. No reviewer must find something.

**Report important findings only. Do not report everything you see.** The default answer is
silence. Nobody counts your findings. Drop a finding when you cannot name the damage it causes.
Drop a preference. Drop what the author sees without you. Five small remarks bury the one remark
that matters.

### Three severities: MUST FIX, SHOULD FIX, NOTE

Each reported finding gets exactly one of three labels: **MUST FIX**, **SHOULD FIX**, or **NOTE**.
The label decides **only** whether the finding holds up approval. It does not change what you
report.

**Only MUST FIX holds up approval. SHOULD FIX and NOTE never do.**

#### The MUST FIX test — all four parts must pass

Write MUST FIX only when all four parts below are true.

1. **Name the wrong result.** Complete this sentence from the diff: "After this merge, <who or
   what> gets <the wrong result> at <file>:<symbol>." You must fill every blank.
2. **Name a trigger that exists today.** Name a caller, a command, a user step, or a released
   artifact that reaches the defect now. A trigger that needs code nobody has written does not
   count.
3. **Name the line in this diff.** The line that causes the failure must sit inside this diff.
   Evidence outside the diff does not count.
4. **Match one of the six damage classes below.** The failure must be one of the six.

If any part fails, write SHOULD FIX or NOTE. The size of the fix is not part of this test. Your
opinion of the code is not part of this test.

#### The six damage classes (closed list)

1. The software gives a wrong result, or it stops.
2. Private data escapes, or a security control breaks.
3. Data is destroyed, or made unrecoverable.
4. A published interface breaks for a caller you can name.
5. A check stops running, or a check passes when it must fail.
6. An invariant marked `[blocking]` in section 3 breaks.

The list is closed. Do not add a class, do not remove one, and do not reword one.

#### Do not block on these

None of these reach MUST FIX on their own:

- Wording, tone, grammar, and voice.
- A missing test for code that already works.
- Naming, layout, duplication, and dead code.
- An input that no current caller sends.
- A risk that needs a future change to become real.
- Prose that no agent and no user follows to a wrong action.

**Most pull requests get zero MUST FIX.** A report with more than two MUST FIX entries is a
signal to read them again.

#### SHOULD FIX

The finding is real. You can name a defect. But you cannot complete all four parts of the MUST
FIX test above. Typical cases:

- The failure needs a caller that does not exist yet.
- The damage is latent.
- The evidence sits outside the diff.
- The failure is real, but it is not one of the six damage classes.

The author decides whether to fix it in this pull request.

#### NOTE

The finding is real. It clears the two report-or-drop tests above. It names no defect. Typical
cases:

- An invariant marked `[advisory]` is broken.
- The prose is unclear, but no agent or user acts wrongly on it.
- A test is missing for code that already works.

**The note cap.** Write a SHOULD FIX or a NOTE in two short sentences, maximum. One sentence for
what is wrong, one for why it matters. No third sentence, no example block, no patch. A finding
that needs more space than that is a must-fix, a should-fix, or not worth reporting — decide
which, then write it as one or drop it.

#### Dropped stays dropped

Three labels sort what you report. They never turn a dropped remark into a report. This is the
obvious failure mode of adding a lower label — watch for it. A style preference that no invariant
binds stays dropped. A remark the author sees without you stays dropped.

#### When you are not sure, use the lower label

Order: MUST FIX, then SHOULD FIX, then NOTE. When you are not sure which one fits, use the lower
one. An approval that a human must chase is more expensive than a note that a human ignores. "Not
sure" means you cannot complete the four-part test. It does not mean you completed it and think
the fix is small.

### Voice — ASD-STE100

Write every finding, digest, and receipt in ASD-STE100 Simplified Technical English:

- Write one idea in one sentence. Use a maximum of 20 words.
- Use the active voice and the present tense.
- Use one word for one meaning. Do not change the word for the same thing.
- Do not use idioms, metaphors, humor, or jargon.
- Name the file, the symbol, and the damage. Do not hedge.

This applies to all review text, local and posted. Paths, identifiers, commands, and quoted
source keep their exact spelling.

---

## 2. Deterministic gates (never re-flag)

The repo's own mechanical checks. A lens must never surface what one of these already owns; the
review is advisory and complements — never duplicates — these gates. All executor skills read
this list: `reviewing-prs` uses it as the hard-exclusion set, and the lifecycle skills
(`getting-prs-approved`, `getting-prs-merged`) run these as the CI-equivalent gate before
declaring a PR green.

- `claude plugin validate .` — `.claude-plugin/marketplace.json` schema: required fields, owner
  block, and whether each `plugins[]` entry's `source` resolves.
- `claude plugin validate ./plugins/ai-fluency` — that plugin's `.claude-plugin/plugin.json`
  schema and required fields.

**Read this scope note before you drop a finding as gate-owned.** These two commands check
manifest JSON only. Their coverage is much narrower than the name suggests, and the gap is
measured, not assumed: a skill named `Claude_Delegation_UPPER` — uppercase, underscores, and the
reserved word `claude`, three violations at once — passes both commands. So **no gate in this
repo owns** any of:

- skill frontmatter: `name`, `description`, length caps, reserved words, `name`-to-directory match,
- skill body length, structure, or progressive disclosure,
- `REFERENCE.md#anchor` links resolving,
- accuracy of any prose claim,
- duplicate or drifted content across files.

This repo has no CI workflow, no package manager, no linter, no type checker, and no test runner.
Do not treat a check from another repo as present here. The frontmatter and anchor checks in PR
\#1's test plan were ad-hoc shell commands, not committed scripts, so they are not gates.

---

## 3. Repo invariants

The mined, repo-specific rules that must always hold. Each lens ties its findings back to one
of these (or to a doc the invariant points at). Keep them concrete and falsifiable.

Each invariant bullet starts with `[blocking]` or `[advisory]`. A `[blocking]` invariant is
damage class 6 in section 1: a diff that breaks it can be a MUST FIX. An `[advisory]` invariant
can reach SHOULD FIX at most. An invariant with no marker reads as `[advisory]`.

- `[blocking]` A mechanical claim about how Claude Code behaves must be true. Verify it against
  the official docs or by running the command before you ship it. Evidence: commit `0de7df5`
  shipped three false claims at once, including an `allowed-tools` substitution rule that names
  the wrong pair of variables.
- `[blocking]` A `SKILL.md` body must never contain a literal path-variable token. Claude Code
  substitutes those tokens when it loads the skill, so the body renders an absolute filesystem
  path instead of the variable name it means to teach. Name the variable in prose and put the
  exact syntax in a reference file, which is only ever read. Evidence: commit `189ff26`, confirmed
  by invoking the skill.
- `[blocking]` A skill's frontmatter `name` equals its directory basename, is kebab-case, and
  never contains the reserved words `claude` or `anthropic`. In a plugin skill the `name` sets the
  command's last segment. No gate checks this — see section 2.
- `[blocking]` A new plugin has an entry in the `plugins` array of
  `.claude-plugin/marketplace.json`, per README step 2. A new *skill* inside an existing plugin
  needs no manifest change: Claude Code discovers skills from `plugins/<plugin>/skills/`.
- `[advisory]` Context economy. A `SKILL.md` body stays under 500 lines and a `description` stays
  within 1024 characters, third person, key trigger first. The body sits in context for the whole
  session and the `description` sits there always, so exhaustive detail belongs in a reference
  file. Source: `.claude/skills/writing-skills/SKILL.md`.
- `[advisory]` Pointer integrity. Reference files stay one level deep and are never chained
  (`SKILL.md` to `a.md` to `b.md`), every pointer states when to read the file, a reference file
  over about 100 lines carries a table of contents, and each `REFERENCE.md#anchor` link resolves
  to a real heading. Source: `.claude/skills/writing-skills/SKILL.md`.
- `[advisory]` Single source of truth. One fact lives in one file. `plugin.json` is the authority
  for `description` and `version`; do not repeat them in `marketplace.json`, per README step 2.
  Build material — framework research, design notes — is never linked from a skill body, because a
  skill that reads theory during a task pays context for something that does not change what it
  does.
- `[advisory]` Terminology. Use one term for one concept, and never let one term mean two
  different things in the same skill. Evidence: commit `189ff26` found "Yours" naming two
  different people 30 lines apart. Skill bodies carry no dates and no time-sensitive claims.

---

## 4. Lens registry

The authoritative list of active lenses. `reviewing-prs` reads this table to decide which
lenses to fan out for a given diff.

| name | when | skill path |
|------|------|------------|
| reviewing-guidance-accuracy | `**/*.md`, `changes-claude-code-claim` | `.claude/skills/reviewing-guidance-accuracy` |
| reviewing-skill-load-semantics | `**/SKILL.md` | `.claude/skills/reviewing-skill-load-semantics` |
| reviewing-skill-frontmatter | `**/SKILL.md` | `.claude/skills/reviewing-skill-frontmatter` |
| reviewing-doc-consistency | `**/*.md`, `README.md` | `.claude/skills/reviewing-doc-consistency` |
| reviewing-plugin-manifest | `**/.claude-plugin/*.json`, `**/marketplace.json`, `**/plugin.json` | `.claude/skills/reviewing-plugin-manifest` |
