# Adapter: ui

Subject I/O for `relay:refining` when the subject is a **live website** (rendered, via a running
dev server) **plus its source tree**. Unlike the spec/plan adapters (which patch a markdown file
in place), this adapter operates on a running web application and persists via score-commits.
The generic loop in `skills/refining/SKILL.md` calls the verbs below.

## Interface

### `load()`

Receive the pre-warmed `{base_url, source_root, dev_command}` handle that the
`relay:refining-ui` shim obtained by calling `relay:running-web-apps` **before** invoking the
engine. The adapter's `load()` does **not** itself call the skill — it accepts the handle as
input and:

1. Records a `PRE_LOOP_SHA` (HEAD SHA before any generator runs) in the sidecar at
   `<source_root>/.relay/ui-refine-findings.json` as a safe revert anchor. If the generator
   breaks the site, the user can recover with:
   ```
   git reset --hard $PRE_LOOP_SHA
   ```
2. Performs a smoke check — confirms the site still loads at `base_url` (HTTP 200 or equivalent).
   If the smoke check fails (server not responding), `load()` aborts with an `engine_error` so
   no rounds run. This propagates as `SERVER_FAILED` to `/relay:refine`.

Critics screenshot the URL and read source files under `source_root`.

**Error handling:** If the server fails to start (`SERVER_FAILED`) the loop aborts immediately.
If the site fails to load on a later round (generator broke the site), the failure is recorded as
a critical finding; v1 does not auto-revert, but the `PRE_LOOP_SHA` anchor gives the user a
known safe target.

### `snapshot(subject)`

Capture the current `git` tree state of `source_root` as the opaque pre-state:

- `HEAD` SHA (`git rev-parse HEAD`)
- Working-tree hash (`git diff --stat HEAD` fingerprint)

Returns `{head_sha, working_hash}` as the pre-state for this round. `diff()` compares against
this snapshot.

### `diff(snapshot, current)`

Return the structured `git diff` of `source_root` between the snapshot's `head_sha` and the
current HEAD, for the round report. Equivalent to:

```
git diff <snapshot.head_sha> HEAD -- <source_root>
```

### `post_fix(action)`

The UI post-fix action is **`re-read`**: after `ui-generator` edits the source files, the
running dev server picks up the changes (hot-reload or similar). On the next round, critics
re-screenshot the live URL and re-read source under `source_root` — no explicit server restart is
needed unless the dev server crashed. No `verify-tests` action in v1; the site-still-loads smoke
check is part of `load()` at the start of each round.

### `persist(round, payload, marker)`

Write resume state in two places:

1. **Score-commit** — `git commit` the generator's edits with a structured subject line:
   ```
   refine(ui): round N design_quality=D originality=O craft=C functionality=F accessibility=A mode=refine|pivot
   ```
   Flat space-separated `key=value` tokens mirror website's proven commit convention. The commit
   captures the generator's source edits and the per-dimension scores for that round.

2. **Sidecar file** — write/update `<source_root>/.relay/ui-refine-findings.json` with the full
   `payload` (scores, findings, fix_mode, round number) as a secondary record for tooling.

The score-commit doubles as relay's standard git-checkpoint persistence (same family as the `pr`
adapter) and as the website-style scored history.

### `recover()`

Resume after a crash by reading the git log for the most recent score-commit:

1. Grep git log for the latest commit whose subject matches the regex
   `/^refine\(ui\): round \d+/`.
2. Parse its `key=value` tokens with the regex `(\w+)=([^\s]+)` to extract the round number and
   per-dimension scores (`design_quality`, `originality`, `craft`, `functionality`,
   `accessibility`).
3. If no matching commit exists, **fall back** to reading the sidecar
   `<source_root>/.relay/ui-refine-findings.json`.
4. Return `{last_round, scores}` so the loop resumes at the next round with prior scores seeded
   (used by the plateau counter and threshold check).

If neither a matching commit nor a sidecar file exists, `recover()` returns `null` and the loop
starts fresh from round 0.
