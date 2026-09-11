#!/usr/bin/env python3
"""Keep .claude-plugin/marketplace.json in step with the mirrored plugins.

Makes sure every name in scripts/vendored-plugins.txt has a local-path entry,
removes entries for plugins that are no longer on the list and no longer on
disk, and sorts the array by name. Entries this repository owns, and entries
that point at a remote source, are left as they are.

Entries hold only "name" and "source". The plugin's own plugin.json is the
authority for the description and the version.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / ".claude-plugin" / "marketplace.json"
VENDORED = ROOT / "scripts" / "vendored-plugins.txt"


def read_vendored():
    names = []
    for line in VENDORED.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(line)
    return names


def main():
    vendored = read_vendored()
    manifest = json.loads(MANIFEST.read_text())
    entries = {p["name"]: p for p in manifest.get("plugins", [])}

    for name in vendored:
        if not (ROOT / "plugins" / name / ".claude-plugin" / "plugin.json").is_file():
            print(f"error: plugins/{name} has no plugin.json", file=sys.stderr)
            return 1
        entries[name] = {"name": name, "source": f"./plugins/{name}"}

    # Drop a mirrored entry whose directory the sync has removed.
    for name, entry in list(entries.items()):
        source = entry.get("source")
        if isinstance(source, str) and source.startswith("./plugins/"):
            if not (ROOT / source[2:]).is_dir():
                del entries[name]
                print(f"removed entry: {name}")

    manifest["plugins"] = [entries[name] for name in sorted(entries)]
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"marketplace.json: {len(manifest['plugins'])} plugins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
