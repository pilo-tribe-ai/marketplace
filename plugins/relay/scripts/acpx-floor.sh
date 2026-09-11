#!/usr/bin/env bash
# acpx version floor — the single site that states the minimum acpx relay needs.
#
# Every other floor mention in this plugin is prose that points here. Before this
# script existed the floor lived in five files that disagreed (0.7.0 in
# check-readiness and flows/package.json, 0.12.0 in the two setup skills) and no
# code ever checked it, so a machine on a stale acpx failed later, deep inside a
# dispatch, with an error that named neither acpx nor the version.
#
# Usage:
#   source acpx-floor.sh && relay_acpx_floor_check || exit 1   # from another script
#   bash acpx-floor.sh                                         # from a skill/doc step
#
# On success it prints `RELAY_ACPX_VERSION=<version>` on stdout and returns 0.
# On failure it prints one `[relay] error:` line on stderr and returns 1.

RELAY_ACPX_MIN=0.13.2

# Why 0.13.2 and not 0.12.0:
#   0.12.1 refreshed acpx's own adapter pins — codex ^0.0.44 -> ^1.1.5. The
#          ^0.0.44 pin was broken, and relay carried an `--agent` override to
#          work around it (relay 4.6.1). At this floor the override is gone.
#   0.13.1 re-applies the pinned model on reconnect and keeps messageId/_meta on
#          message chunks, which is what acpx-envelope.sh groups by.
#   0.13.2 restores the saved model and config options after a reconnect and
#          REPORTS a replay failure instead of silently running on defaults.
#          delegate-and-watch routes that report to its `errored` bucket.

# Compare two dotted versions. Returns 0 when $1 >= $2.
relay_acpx_version_ge() {
    [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]
}

relay_acpx_floor_check() {
    local found
    if ! found=$(acpx --version 2>/dev/null); then
        printf '[relay] error: acpx is not on PATH. Run: npm install -g acpx@latest\n' >&2
        return 1
    fi
    # `acpx --version` prints a bare semver; extract the first dotted-number token
    # defensively so a future `name X.Y.Z` banner cannot be concatenated into a
    # string that sorts ABOVE the floor and silently bypasses the gate.
    found=$(printf '%s' "$found" | head -1 | grep -oE '[0-9]+(\.[0-9]+)+' | head -1)
    if [ -z "$found" ]; then
        printf '[relay] error: acpx --version printed no version. Run: npm install -g acpx@latest\n' >&2
        return 1
    fi
    if ! relay_acpx_version_ge "$found" "$RELAY_ACPX_MIN"; then
        printf '[relay] error: acpx %s is below the floor %s. Run: npm install -g acpx@latest\n' \
            "$found" "$RELAY_ACPX_MIN" >&2
        return 1
    fi
    printf 'RELAY_ACPX_VERSION=%s\n' "$found"
    return 0
}

# Executed directly (not sourced): run the check and exit on its result.
# ${BASH_SOURCE[0]} != $0 when this file is sourced.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    relay_acpx_floor_check || exit 1
fi
