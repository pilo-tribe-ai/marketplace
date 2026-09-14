#!/usr/bin/env python3
"""Read-tolerant, write-strict ADR parser. Standard library only.

Reads two metadata styles (YAML frontmatter and legacy bold-key headers) and
writes exactly one (frontmatter). The filename is an ADR's identity; no `id`
field is ever read or written.
"""
import datetime as _dt
import json
import re
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
    HAVE_YAML = True
except ImportError:                     # optional, never required
    yaml = None
    HAVE_YAML = False

STATUSES = ("proposed", "accepted", "deprecated", "superseded")
REQUIRED_KEYS = ("type", "status", "date", "title")
LIST_KEYS = ("supersedes", "superseded_by", "related")
KEY_ORDER = ("type", "status", "date", "title", "area",
             "supersedes", "superseded_by", "related")

FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def split_frontmatter(text: str):
    """Return (frontmatter_text_or_None, body).

    Matches only when the opening '---' is line 1 and a closing '---' comes
    before any other content. A file whose only '---' is a horizontal rule
    further down falls through to the legacy reader; this never partial-parses
    a body it opened as frontmatter and then failed to close.
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, text
    return match.group(1), text[match.end():]


def _scalar(value: str):
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    if v in ("null", "~", ""):
        return None
    return v


def _inline(value: str):
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [_scalar(part) for part in inner.split(",")] if inner else []
    return _scalar(value)


def parse_simple_yaml(text: str) -> dict:
    """The flat subset this plugin writes: scalars, null, inline and block
    lists. Anything richer needs PyYAML, which is optional."""
    data, current = {}, None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if current is not None and (line.startswith((" ", "\t")) or line.startswith("-")):
            item = line.lstrip().lstrip("-").strip()
            if item:
                data[current].append(_scalar(item))
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value == "":
            data[key], current = [], key
        else:
            data[key], current = _inline(value), None
    return data


def _normalize(data: dict) -> dict:
    out = {}
    for key, value in (data or {}).items():
        if isinstance(value, (_dt.datetime, _dt.date)):
            value = value.isoformat()[:10]
        elif isinstance(value, list):
            value = [str(item) for item in value if item is not None]
        elif value is not None and not isinstance(value, str):
            value = str(value)
        name = str(key).strip().lower()
        if isinstance(value, list) and not value and name not in LIST_KEYS:
            value = None
        out[name] = value
    return out


def load_frontmatter(text: str) -> dict:
    data = None
    if HAVE_YAML:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            data = None
    if not isinstance(data, dict):
        data = parse_simple_yaml(text)
    return _normalize(data)


LEGACY_RE = re.compile(
    r"^\*\*(Status|Date|Supersedes|Superseded By|Type|Area|Related)\s*:\*\*\s*(.+?)\s*$",
    re.IGNORECASE,
)

# How many raw lines from the start of the file parse_legacy will scan for
# bold-key headers. Callers that need to mirror parse_legacy's own window
# (e.g. adr_migrate's fold, which must never touch a bold-key-shaped line
# outside it) import this constant rather than hardcoding 20 again.
LEGACY_HEADER_WINDOW = 20


def parse_legacy(text: str) -> dict:
    """Bold-key headers in the first 20 raw lines, blank lines counted, from
    the start of the file. Keys outside the closed set are ignored, never
    warned on. A status outside the enum is kept verbatim for the lint to
    report; it is never guessed at or split."""
    data = {}
    for raw in text.splitlines()[:LEGACY_HEADER_WINDOW]:
        match = LEGACY_RE.match(raw.strip())
        if not match:
            continue
        key = match.group(1).strip().lower().replace(" ", "_")
        value = match.group(2).strip()
        if key in LIST_KEYS:
            data[key] = [part.strip() for part in value.split(",") if part.strip()]
        elif key == "status":
            data[key] = value.lower()
        else:
            data[key] = value
    return data


HEADING_RE = re.compile(r"^#\s+(.*\S)\s*$", re.MULTILINE)
ADR_MARKER_RE = re.compile(r"^adr[-\s]?\d{3,4}\s*(?::|—|-|\s)\s*", re.IGNORECASE)
SEQ_PREFIX_RE = re.compile(r"^(\d{4})(?:[-_]|$)")
DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[-_]|$)")


def heading_title(body: str):
    match = HEADING_RE.search(body)
    if not match:
        return None
    return ADR_MARKER_RE.sub("", match.group(1).strip()).strip() or None


def prefix_of(filename: str, id_scheme: str = "sequential"):
    """The filename is the identity. Under 'sequential' the four-digit numeric
    prefix identifies the ADR; under 'date' the YYYY-MM-DD prefix does."""
    stem = str(filename).rsplit("/", 1)[-1]
    pattern = DATE_PREFIX_RE if id_scheme == "date" else SEQ_PREFIX_RE
    match = pattern.match(stem)
    return match.group(1) if match else None


@dataclass
class Adr:
    path: Path
    filename: str
    source: str          # "frontmatter" | "legacy"
    meta: dict
    body: str
    title: str = None
    status: str = None
    date: str = None
    area: str = None
    prefix: str = None


def refs(meta: dict, key: str = "related"):
    value = (meta or {}).get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(item) for item in value if str(item).strip()]


def parse_adr(path, id_scheme: str = "sequential") -> Adr:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    front, body = split_frontmatter(text)
    if front is not None:
        meta, source = load_frontmatter(front), "frontmatter"
    else:
        meta, source = parse_legacy(text), "legacy"
        body = text
    return Adr(
        path=path,
        filename=path.name,
        source=source,
        meta=meta,
        body=body,
        title=meta.get("title") or heading_title(body),
        status=meta.get("status"),
        date=meta.get("date"),
        area=meta.get("area"),
        prefix=prefix_of(path.name, id_scheme),
    )


DEFAULT_CONFIG = {
    "version": 1,
    "dir": "docs/adr",
    "register": "docs/adr/README.md",
    "id_scheme": "sequential",
    "gate": {"deterministic": False, "model": False, "proposed_verdict": "error"},
    "archive_dir": None,
}


@dataclass
class Corpus:
    root: Path
    config: dict

    @property
    def dir(self) -> Path:
        return self.root / self.config["dir"]

    @property
    def register(self) -> Path:
        return self.root / self.config["register"]

    @property
    def id_scheme(self) -> str:
        return self.config["id_scheme"]

    @property
    def archive(self):
        name = self.config.get("archive_dir")
        return (self.dir / name) if name else None


def find_repo_root(start=None) -> Path:
    start = Path(start or Path.cwd()).resolve()
    for parent in (start, *start.parents):
        if (parent / ".git").exists():
            return parent
    return start


def load_corpus(repo_root=None, config_path=None) -> Corpus:
    root = Path(repo_root).resolve() if repo_root else find_repo_root()
    path = Path(config_path) if config_path else root / ".claude" / "adr.json"
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
        gate = {**config["gate"], **(raw.get("gate") or {})}
        config.update({k: v for k, v in raw.items() if k != "gate"})
        config["gate"] = gate
    return Corpus(root=root, config=config)


def discover(corpus: Corpus):
    """{{DIR}}/*.md, non-recursive. The register, CLAUDE.md, and every
    subdirectory (archive/, and the vendored trees, which are not .md files at
    the top level) stay out."""
    if not corpus.dir.is_dir():
        return []
    skip = {"README.md", "CLAUDE.md", Path(corpus.config["register"]).name}
    return sorted((p for p in corpus.dir.glob("*.md") if p.name not in skip),
                  key=lambda p: p.name)


def discover_archived(corpus: Corpus):
    archive = corpus.archive
    if not archive or not archive.is_dir():
        return []
    return sorted(archive.glob("*.md"), key=lambda p: p.name)


_NEEDS_QUOTES = re.compile(r"^[\s>|&*!%@`\[\]{}#'\"-]|:\s|\s$|^$")


def _emit(value: str) -> str:
    if _NEEDS_QUOTES.search(value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def dump_frontmatter(meta: dict) -> str:
    """Write-strict: YAML frontmatter, fixed key order, never an `id` field.
    The filename is the identity."""
    lines = []
    for key in KEY_ORDER:
        if key == "area" and not meta.get("area"):
            continue                      # optional, omitted when empty
        value = meta.get(key)
        if key in LIST_KEYS:
            items = refs(meta, key)
            if not items:
                lines.append(f"{key}: " + ("[]" if key == "related" else "null"))
            else:
                lines.append(f"{key}:")
                lines.extend(f"  - {_emit(str(item))}" for item in items)
        elif value is None:
            lines.append(f"{key}: null")
        else:
            lines.append(f"{key}: {_emit(str(value))}")
    return "\n".join(lines) + "\n"
