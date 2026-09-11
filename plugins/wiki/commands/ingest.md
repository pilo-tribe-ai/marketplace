---
description: Ingest a document into the knowledge bundle named by .claude/wiki.json, per AGENTS.md
argument-hint: "[path | URL] (blank = ingest every raw file with no Source page)"
allowed-tools: Read, Write, Edit, Glob, Grep, WebFetch, Bash(python3:*), Bash(git status:*), Bash(git mv:*), Bash(git add:*), Bash(ls:*), Bash(cp:*), Bash(mkdir:*), Bash(test:*)
---

# Ingest into the wiki

Ingest this into the wiki: **$ARGUMENTS**

## Step 0 -- resolve the container

```bash
test -f .claude/wiki.json
```

If that fails, stop: "This repository has no wiki. Run `/wiki:setup` first." Do not guess a
container path or create one by hand.

```bash
CONTAINER=$(python3 -c "import json;print(json.load(open('.claude/wiki.json'))['container'])")
test -d "$CONTAINER"
```

If the directory is missing, stop and name it: "`.claude/wiki.json` points at `$CONTAINER`, which
does not exist. Run `/wiki:setup` to re-scaffold or fix the pointer." Every path below is written
relative to `$CONTAINER`, resolved from the repository root, which is where you are.

`${CONTAINER}AGENTS.md` is the schema and the procedure. Read it before you touch anything, and
follow its "Operation: Ingest" exactly. This command does not restate that procedure -- it
resolves the input, then holds you to the closing gates.

## Step 1 -- resolve the input

Work out which of these you were given, then produce a file in `${CONTAINER}raw/`.

| `$ARGUMENTS` | What to do |
|---|---|
| empty | List `${CONTAINER}raw/` and `${CONTAINER}bundle/sources/`. Ingest every raw file with no matching `${CONTAINER}bundle/sources/<same-basename>.md`. If there are none, say so and stop -- do not invent work. |
| a URL | Fetch it. Save the text verbatim to `${CONTAINER}raw/<YYYY-MM-DD>-<kebab-slug>.<ext>`. |
| a path already inside `${CONTAINER}raw/` | Ingest it in place. |
| a path outside `${CONTAINER}raw/` | Move it in: `git mv` if git tracks it, otherwise copy. Name it `${CONTAINER}raw/<YYYY-MM-DD>-<kebab-slug>.<ext>`. |

Two rules that are not negotiable:

- **Never edit a raw file.** It is the immutable record. If the content
  is wrong, that is a fact about the source, and it belongs in the wiki page
  as a caveat.
- **The slug must describe the content.** A raw filename that no longer
  matches what the file holds is how provenance rots -- a page ends up citing
  a source that does not say what the page claims. If you are ingesting a
  changed version of an existing raw file, check whether the slug still fits,
  and rename both the raw file and its Source page if it does not.

Use today's date for `<YYYY-MM-DD>`. Get it from the environment, do not guess.

## Step 2 -- ingest

Follow `${CONTAINER}AGENTS.md` "Operation: Ingest", steps 2 through 6. Read
the raw file in full first -- all of it, not a skim. You cannot extract
entities and concepts you have not read.

Carry the source's own trust signals into the pages. If it records vote
counts, confidence labels, or a refuted-claims table, that belongs in
`verified` and in a `## Refuted or unverified claims` section. A refuted
claim never gets its own page, and never gets silently dropped -- recording
it is what stops it creeping back in later.

If the source contradicts a claim already in the wiki, say so on the page
with both sides footnoted. Do not overwrite the old claim.

**If the source yields more than about ten pages**, write them in parallel
groups by type (entities, concepts, open questions, synthesis) rather than
one at a time. Give each group the frontmatter template verbatim and the
exact list of pages to create, or they will drift apart in style and field
names. Keep the indexes, the log, and the Source page for yourself -- those
are cross-cutting and a parallel writer will clobber them.

## Step 3 -- close out

1. `python3 ${CONTAINER}scripts/regen_indexes.py` -- rewrites every
   subdirectory `index.md` and each Source page's fed-pages list from
   frontmatter. Never hand-edit those files; this script owns them.
2. Append the `${CONTAINER}bundle/log.md` entry by hand. The log is a record of
   what happened, not derived data, so nothing generates it for you. Newest
   date heading first; within a date, append below what is already there.
3. Run all four gates:

   ```
   python3 ${CONTAINER}scripts/check_okf.py --strict
   python3 ${CONTAINER}scripts/check_links.py --strict
   python3 ${CONTAINER}scripts/regen_indexes.py --check
   python3 -m pytest -q ${CONTAINER}tests
   ```

Every gate must pass. When one fails, fix the cause. Do not drop `--strict`,
do not weaken a test, and do not delete a page to make an orphan warning go
away -- an orphan means you created a page and never linked it from prose,
which is a real gap in the ingest.

## Step 4 -- report

State plainly:

- the raw file added, and its slug
- how many pages you created and updated, by type
- any claim the source contradicts in the existing wiki
- any open question the source raises that you could not answer
- the output of the four gates

Do not commit unless asked. Leave the diff for review.
