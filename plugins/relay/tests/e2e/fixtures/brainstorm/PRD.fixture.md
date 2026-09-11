# PRD: personal bookmarks CLI (`bm`)

A tiny command-line tool to save and recall web bookmarks locally.

## Decided (do not violate)
- Language: Python 3, single-file script, standard library only (no pip deps).
- Single user, local machine. No sync, no server, no auth.
- Commands:
  - `bm add <url> [tag]` — save a bookmark, optionally tagged.
  - `bm list [tag]` — print saved bookmarks, optionally filtered by tag.

## Open (resolve from this PRD's spirit: YAGNI, stdlib-only, local single-user)
- Storage format and file location.
- How duplicate URLs are handled on `add`.

## Deliberately unspecified
- Whether `bm list` should support fuzzy / substring search of URLs.
  (The PRD says nothing about search beyond exact-tag filtering.)
