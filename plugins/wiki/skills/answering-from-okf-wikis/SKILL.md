---
name: answering-from-okf-wikis
description: Answers a question from the OKF v0.2 knowledge bundle named by .claude/wiki.json, and never from outside it -- reads bundle/index.md, ranks candidate pages, reads the top ones, cites every claim, and offers to file a durable answer back as a Synthesis page. Use for "/wiki:ask", "ask the wiki", or "what does the wiki say about X".
allowed-tools: Read, Grep, Glob, Edit, Write, AskUserQuestion, Bash(python3:*), Bash(test:*), Bash(ls:*)
---

# answering-from-okf-wikis

This skill runs `Operation: Query` as `${CONTAINER}AGENTS.md` defines it. AGENTS.md is the
contract. If this file and AGENTS.md disagree, AGENTS.md wins.

The no-fabrication rule: I do not answer from outside the wiki. An answer comes from wiki pages
only, or the skill says plainly that no page covers it.

## Step 1 -- accept or resolve inputs

Use the container and the question the caller passed. If no container was passed, resolve it the
same way `/wiki:ask` does:

```bash
test -f .claude/wiki.json
```

If that fails, stop: "This repository has no wiki. Run `/wiki:setup` first."

```bash
CONTAINER=$(python3 -c "import json;print(json.load(open('.claude/wiki.json'))['container'])")
test -d "$CONTAINER"
```

If the directory is missing, stop: "`.claude/wiki.json` points at `$CONTAINER`, which does not
exist. Run `/wiki:setup` to re-scaffold or fix the pointer." Never fall back to model knowledge
just because a question triggered this skill directly.

## Step 2 -- detect an empty bundle

Do this before any grep. Count every `*.md` under `${CONTAINER}bundle/` whose basename is not
`index.md` and not `log.md`. If the count is zero, print exactly:

"The wiki at `$CONTAINER` holds no pages yet. I cannot answer from it. Run `/wiki:ingest <path-or-URL>` to add the first source."

Then append the empty-bundle log line from Step 10, report per Step 12, and stop. Do not grep. Do not answer.
Do not offer a Synthesis page.

## Step 3 -- read the index first

This is `Operation: Query` step 1. Read `${CONTAINER}bundle/index.md` in full. Then skim the
subdirectory `index.md` files the question makes relevant. The index is the map. Never grep
before you read it.

## Step 4 -- grep and rank

This is `Operation: Query` step 2. Grep `${CONTAINER}bundle/**/*.md` bodies and the frontmatter
fields `title`, `description`, and `tags`. Run at least three keyword variants of the question.
One wording can miss a page that uses a different word.

Rank the candidates. A `title` or `tags` match ranks above a `description` match. A `description`
match ranks above a body match. More distinct matched terms rank higher.

## Step 5 -- read the top candidates

This is `Operation: Query` step 3. Read the top five candidate pages in full. Follow each page's
footnotes to its `bundle/sources/` page when the question needs source-level detail, such as who
reported a number or when. Stop reading when the candidates add no more facts.

## Step 6 -- judge coverage

Do this before you write one word of the answer. Split the question into its parts. A part is
COVERED only when a page you read states it. A part is NOT covered when you must join a wiki
fact to outside knowledge. Outside knowledge is anything not stated on a wiki page.

Classify the whole question as full, partial, or none. `none` goes to Step 7. `partial` and
`full` go to Step 8.

## Step 7 -- the no-answer branch

Print exactly:

"The wiki holds no page that answers this question. I do not answer from outside the wiki. The closest pages are: <list>. Run `/wiki:ingest <path-or-URL>` to add a source that covers it."

`<list>` holds up to three cited page links, or the word `none`. Write no answer body. Skip the
Synthesis offer. Go to Step 10.

## Step 8 -- write the answer

This is `Operation: Query` step 4. Every sentence in the answer body carries at least one wiki
page link. A sentence with no link is forbidden.

Cite in two forms, and use the right one:

- A terminal answer lands in no file, so it has no anchor to be relative to. Cite
  repo-root-relative: `[<page title>](<CONTAINER>bundle/<type-dir>/<slug>.md)`. No leading slash.
  No `./` prefix.
- A filed Synthesis page cites relative to itself. Step 9 states that form.

On partial coverage, close the body with the heading `## What the wiki does not cover` and one
bullet per uncovered part, each reading: "The wiki holds no page about <part>. I do not answer
that part from outside the wiki."

Outside knowledge appears nowhere in the body. It is allowed only as one closing line that makes
no claim: "The wiki does not cover <topic>. Ask me directly if you want an answer from outside
the wiki."

If two pages state facts that disagree, report both, each cited. Say the wiki disagrees with
itself. Name `Operation: Lint` as the way to reconcile them. Never pick a winner from outside
knowledge.

## Step 9 -- offer to file, and write only on agreement

This is `Operation: Query` steps 5 and 6. Offer a Synthesis page only when the answer is
non-trivial and durably useful. Never offer for a one-off lookup. Never offer after Step 7.

Ask once with AskUserQuestion. Header: "File this answer into the wiki?" Options: "File it" and
"Do not file". State in the question that filing writes `${CONTAINER}bundle/synthesis/<slug>.md`
with `status: draft`. Filing also adds one inbound link from a Concept, Entity, Synthesis, or
OpenQuestion page. Filing appends a log line and regenerates the synthesis index.

On "Do not file", write nothing and go to Step 10.

On "File it":

1. Pick a kebab-case `<slug>`. If `bundle/synthesis/<slug>.md` already exists, update that page's
   body and `generated.at` instead of writing a duplicate -- the same rule `Operation: Ingest`
   step 3 uses. Say in the report that a page was updated, not created.
2. Write frontmatter per `${CONTAINER}schema.md` section 4.4. Include `type: Synthesis`, `title`,
   `description`, `tags`, `sources[]`, `status: draft`, and `generated`. The `generated` field
   holds `by` and `at`. `by` is the agent actor string from the Conventions recap in
   `${CONTAINER}AGENTS.md`. `at` is an ISO-8601 datetime.
3. Body links are relative to the filed page: `../concepts/<slug>.md`, `../entities/<slug>.md`,
   `../sources/<slug>.md`, or a bare `<slug>.md` for a sibling Synthesis page. Never a leading
   slash. Frontmatter `sources[].resource` keeps its `/sources/<file>.md` form per schema.md
   section 5.
4. Add one inbound link to the new page from a page the answer cites. Use a Concept, Entity,
   Synthesis, or OpenQuestion page as the source of the link. Never use an index.md page or a
   Source page for this link. `check_links.py` ignores inbound links from those two page kinds.
   A link from them does not clear the orphan check. If the answer cites no page of an allowed
   kind, do not invent one. Say so plainly in the Step 12 report. Note that the new page may show
   as an orphan.
5. Run `python3 ${CONTAINER}scripts/regen_indexes.py`. This is what updates
   `bundle/synthesis/index.md`. A subdirectory `index.md` is derived data. Never hand-edit one.
   Leave `bundle/index.md` alone -- it already lists Synthesis, and a hand edit there is reserved
   for a whole new page type.
6. Run the blocking gate AGENTS.md names: `python3 ${CONTAINER}scripts/check_okf.py`. Fix what it
   reports. Never report success on a non-zero exit. If it exits 2 because PyYAML is missing,
   report the exact instruction `pip install -r ${CONTAINER}requirements.txt` and report the gate
   as not run.

## Step 10 -- always append one log line

This is `Operation: Query` step 7. Append to `${CONTAINER}bundle/log.md` on every branch that
resolved a container, including the empty-bundle branch and the no-answer branch.

Put the bullet under today's `## YYYY-MM-DD` heading. Create the heading if today has none.
Newest date first. Append below whatever bullets that date already holds. Take today's date from
the environment. Never guess it. Never write frontmatter into `log.md`. Log links are relative to
`bundle/log.md`, which sits at the bundle root, so a synthesis link reads `synthesis/<slug>.md`.

The four forms:

- `* **Query**: "<question>" -- filed [<Title>](synthesis/<slug>.md).`
- `* **Query**: "<question>" -- answered from <N> pages; no new page written.`
- `* **Query**: "<question>" -- no page in the bundle answers it; no new page written.`
- `* **Query**: "<question>" -- the bundle holds no pages; no answer given.`

This append makes a read-only operation change one file. It is never silent -- Step 12 always
names the exact line.

## Step 11 -- advisory link check

After a write only, run `python3 ${CONTAINER}scripts/check_links.py --strict`. Report its
result. This check is advisory, not blocking, because `Operation: Query` step 6 names
`check_okf.py` alone. If it reports the new page as an orphan, say so plainly and name the page.
Never delete the page to clear the warning.

## Step 12 -- report

State plainly:

- how many pages you read
- every page you cited
- whether coverage was full, partial, or none
- whether a Synthesis page was written or updated, and its path
- the exact line appended to `bundle/log.md`, and that file's path
- the name and exit code of every gate that ran

Do not commit. Leave the diff for review.
