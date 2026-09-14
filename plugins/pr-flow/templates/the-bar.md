<!-- pr-flow generator template — the contract archetype. /pr-flow:setup (bootstrapping-pr-flow) fills the <PLACEHOLDER> spans from mined repo evidence and writes the result to .claude/pr-flow/contract.md. Not an active contract itself. -->

# PR review contract

The single source of truth for PR review in this repo. Human-editable. Both the executor
skills (`reviewing-prs` and the lifecycle skills) and every generated `reviewing-<concern>`
lens read this file. Four sections: **the Bar**, **Deterministic gates**, **Repo invariants**,
and the **Lens registry**.

---

## 1. The Bar — what a finding must clear, and which findings hold up approval

A finding is reportable only if it clears **both** tests:

1. **Real** — concretely true in *this* diff, with evidence. Not speculative, not "could be
   cleaner," not future-hypothetical.

2. **Impactful if left unattended** — it would cause one or more of:
   - broken or incorrect behavior that ships,
   - a security, data-exposure, or compliance breach,
   - a violated **repo invariant** that section 3 marks `[blocking]` (see section 3). Section 3
     marks each invariant `[blocking]` or `[advisory]`. An invariant marked `[advisory]` is still
     reportable, at SHOULD FIX or NOTE, but not at MUST FIX,
   - a **costly-to-reverse** decision baked into a hard-to-change layer,
   - a **broken contract** with existing consumers (API/schema/SDK surface),
   - a deterministic check defeated by a lie (e.g. mis-labeling a change to dodge a gate).

   <!-- The bullets above are generic. bootstrapping-pr-flow should replace the last four
        with this repo's real impact categories, mined from review history and docs. Example
        rows from a healthcare monorepo (drop or replace for your repo):
          - PHI / compliance exposure in any environment,
          - gateway-only-persistence invariant violated,
          - GraphQL breaking change to a published contract. -->

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

<!-- bootstrapping-pr-flow records the exact commands discovered at setup time, one per line,
     each with a scope note. The scope note is load-bearing: at review time the executor
     decides "is this finding gate-owned?" and cannot infer coverage from a command string. -->

- `<GATE_COMMAND_1>` — <what it owns>   <!-- e.g. `npm run lint` — formatting, style, unused vars, import order -->
- `<GATE_COMMAND_2>` — <what it owns>   <!-- e.g. `npm run typecheck` — type errors, incompatible signatures -->
- `<GATE_COMMAND_3>` — <what it owns>   <!-- e.g. `npm test` — failing/missing assertions in existing suites -->
- `<GATE_COMMAND_N>` — <what it owns>   <!-- e.g. secret-scan — committed credentials; schema-validate — schema syntax -->

---

## 3. Repo invariants

The mined, repo-specific rules that must always hold. They feed the `flag:` lines the lenses
generate. Keep them concrete and falsifiable.

Each invariant bullet starts with `[blocking]` or `[advisory]`. A `[blocking]` invariant is
damage class 6 in section 1: a diff that breaks it can be a MUST FIX. An `[advisory]` invariant
can reach SHOULD FIX at most. An invariant with no marker reads as `[advisory]`.

<!-- bootstrapping-pr-flow fills these from CLAUDE.md, CONTRIBUTING.md, ADRs, and recurring
     review objections. One short rule per bullet, with a pointer to the authoritative doc.
     Write the `[blocking]` or `[advisory]` marker first on every bullet — see Step 4 of
     bootstrapping-pr-flow/SKILL.md. -->

- `[blocking]` `<INVARIANT_1>`   <!-- e.g. "All persistence goes through the gateway; no browser-direct data access." -->
- `[blocking]` `<INVARIANT_2>`   <!-- e.g. "No PHI in any environment, including dev." -->
- `[advisory]` `<INVARIANT_N>`   <!-- e.g. "Use canonical component names everywhere; never invent an alias." -->

---

## 4. Lens registry

This table lists this repo's lenses. One plugin lens, `pr-flow:reviewing-goal-achievement`, runs
on every review. `reviewing-prs` selects it whether this table lists it or not, and it needs no
row here.

The authoritative list of active lenses. `reviewing-prs` reads this table to decide which
lenses to fan out for a given diff. Each row:

| name | when | skill path |
|------|------|------------|

- **name** — the lens identifier. It **must** equal `basename(skill path)` and equal the
  Skill-tool invocation token, i.e. `reviewing-<concern>`.
- **when** — either **file-glob patterns** (comma-separated, matched against the diff's changed
  paths) **or** named **change-type keywords** (e.g. `touches-data-model`, `renames-component`,
  `adds-endpoint`). Grammar: a `when` cell is a comma-separated list; each entry is a glob if it
  contains `*`, `/`, or a file extension, otherwise it is a change-type keyword. `reviewing-prs`
  triages globs by path-match; a change-type keyword is **always considered** (the orchestrator
  cannot reliably detect it from paths alone) and the lens **self-filters** against its own list —
  so concern-driven lenses (PHI, naming) are never silently dropped by a glob miss.
- **skill path** — `.claude/skills/reviewing-<concern>` (a bare-name repo skill in the target
  repo, human-editable, discovered by Claude Code).

<!-- bootstrapping-pr-flow writes one row per confirmed concern. Example rows (replace with
     this repo's concerns; note name == basename(skill path)): -->

| name | when | skill path |
|------|------|------------|
| reviewing-naming   | `touches-data-model`, `renames-component`   | `.claude/skills/reviewing-naming` |
| reviewing-security | `auth/**`, `gateway/**`                      | `.claude/skills/reviewing-security` |
| reviewing-graphql-contract | `**/*.graphql`, `**/schema.ts`      | `.claude/skills/reviewing-graphql-contract` |
