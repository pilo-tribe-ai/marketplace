---
name: reviewing-adr-adherence
description: Reads the current branch's diff against the ADR corpus and reports findings -- does this change contradict an accepted ADR, and did a hard-to-reverse change ship with no ADR at all. Use for "/adr:check", "does this change contradict an ADR", "review this branch against the decisions", "does this need an ADR". Read-only, advisory, and always exits 0 -- it reports findings, it never blocks on its own judgement.
argument-hint: "[base branch]"
allowed-tools: Bash, Read, Grep, Glob
---

# reviewing-adr-adherence

This is the gate's model tier. The deterministic tier (`adr_lint.py`, `adr_index.py --check`) is
what the gate blocks on. This skill is advisory: it reports findings and **always exits 0**.

## Method

1. Read `.claude/adr.json` for the corpus `dir` and `register` paths.
2. Resolve the base branch by trying each candidate in turn. Stop at the first that resolves,
   and abort when none does -- an empty diff would silently print `no findings`. The full ref
   is kept so `refs/remotes/origin/main` never collides with a stale local `main`:

   ```bash
   BASE=""
   for c in refs/remotes/origin/HEAD refs/remotes/origin/main refs/remotes/origin/master \
            refs/heads/main refs/heads/master; do
     if git rev-parse --verify --quiet "$c" >/dev/null; then
       BASE="$c"
       break
     fi
   done
   [ -n "$BASE" ] || { echo "reviewing-adr-adherence: no base branch resolved" >&2; exit 0; }
   git merge-base "$BASE" HEAD >/dev/null 2>&1 || \
     { echo "reviewing-adr-adherence: no merge-base with $BASE" >&2; exit 0; }
   git diff "$BASE"...HEAD
   ```
3. Read the register first, then open only the ADRs the diff can plausibly touch. A corpus of 122
   ADRs costs about 122 lines to rule out, instead of 122 file reads.

## Check 1 -- the diff contradicts an accepted ADR

This needs reading intent, not syntax -- a deterministic script cannot tell that a diff moved auth
back into a service after ADR-0012 put it at the gateway. This is what makes ADRs binding instead
of decorative. Read each changed file against the ADRs whose area it touches. When a change works
against what an `accepted` ADR decided, that is a finding.

## Check 2 -- a hard-to-reverse change shipped with no ADR

A change that would be hard to reverse and shipped with no ADR at all is what this check catches --
the safety net for when autonomous capture (`authoring-adrs`) misses one. Apply the same bar the
whole plugin applies: record a decision when undoing it later would be expensive. When the
diff makes a choice that fits that bar -- a datastore, a service or trust boundary, a wire or event
contract, a deployment topology, a public interface others consume -- and no ADR in the diff or the
corpus covers it, that is a finding.

## Report

Print a findings list, one bullet per finding, each naming the file and the ADR it contradicts, or
the file and the missing decision. Print `no findings` when there are none.

**Always exit 0.** Findings are advisory by design. Both checks can be wrong -- they read intent,
not syntax, so a finding can be a false alarm. This skill reports findings; it does not block on
its own judgement. The deterministic tier is what the gate blocks on.
