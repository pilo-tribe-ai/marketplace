#!/usr/bin/env bash
# acpx-dispatch.sh — dispatcher entrypoint for /implement:agents role layer.
# Contract: see spec §5.1.
# Inputs (env-passed):
#   ACPX_ROLE_SLUG          — role slug, e.g. acpx-spec-simulator
#   ACPX_BINDING_PRESET     — preset name (or empty if inline)
#   ACPX_BINDING_JSON       — inline binding JSON (when no preset)
#   ACPX_INPUTS_JSON        — JSON object of slot-name → value
#   ACPX_RUN_ID             — unique run id (orchestrator-allocated)
#   ACPX_EXPECTED_MAJOR     — expected role-version major (default 1)
#   WORKTREE                — absolute path to active worktree
#   ACPX_DRY_RUN            — optional; "1" exits after binding validation
#   ACPX_FAKE_CHILD_OUTPUT  — optional test hook; bypass real child invocation
# Output (stdout): single-line JSON conforming to dispatch result.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# --- Pre-flight: require yq and jq on PATH (spec §5 implementation language) ---
command -v yq >/dev/null 2>&1 || {
    echo "acpx-dispatch: yq not on PATH. Install: brew install yq (mikefarah/yq v4)." >&2
    exit 64
}
command -v jq >/dev/null 2>&1 || {
    echo "acpx-dispatch: jq not on PATH. Install: brew install jq (>= 1.6)." >&2
    exit 64
}

# --- --validate-only mode (spec §5.2 step 2 — capability validation only) ---
# CLI: acpx-dispatch.sh --validate-only --role <path-to-role.md> --binding <preset-slug> [--presets-path <path>]
# Exit codes:
#   0 = pass
#   2 = capability mismatch (stderr names every missing capability one per line, prefixed MISSING_CAPABILITY=)
#   3 = role-file parse error (frontmatter unparseable or required keys absent)
if [ "${1:-}" = "--validate-only" ]; then
    shift
    VO_ROLE_PATH=""
    VO_BINDING=""
    VO_PRESETS_PATH="${REPO_ROOT}/bindings/presets.yaml"
    while [ $# -gt 0 ]; do
        case "$1" in
            --role) VO_ROLE_PATH="$2"; shift 2 ;;
            --binding) VO_BINDING="$2"; shift 2 ;;
            --presets-path) VO_PRESETS_PATH="$2"; shift 2 ;;
            *) echo "acpx-dispatch --validate-only: unknown arg: $1" >&2; exit 3 ;;
        esac
    done
    if [ -z "$VO_ROLE_PATH" ] || [ -z "$VO_BINDING" ]; then
        echo "acpx-dispatch --validate-only: --role and --binding required" >&2
        exit 3
    fi
    if [ ! -f "$VO_ROLE_PATH" ]; then
        echo "acpx-dispatch --validate-only: role file not found: $VO_ROLE_PATH" >&2
        exit 3
    fi
    # Native agents carry no slug/role-version frontmatter (those were fork-only
    # keys); role-file existence above is the only role-side precondition.
    if [ ! -f "$VO_PRESETS_PATH" ]; then
        echo "acpx-dispatch --validate-only: presets file not found: $VO_PRESETS_PATH" >&2
        exit 3
    fi
    VO_BINDING_JSON=$(yq -o=json ".roles.\"${VO_BINDING}\"" "$VO_PRESETS_PATH" 2>/dev/null || echo "null")
    if [ "$VO_BINDING_JSON" = "null" ] || [ -z "$VO_BINDING_JSON" ]; then
        echo "acpx-dispatch --validate-only: binding preset not found: $VO_BINDING" >&2
        exit 3
    fi
    # Role files (role-class present) declare `requires:` in the CAPABILITY
    # namespace (read_files, run_bash, write_files), which is DISJOINT from the
    # binding's `provides:` envelope-token namespace — intersecting them rejects
    # every role (see delegate-leaf/SKILL.md and the 4.20.0 capability-gate work).
    # The requires ⊆ provides intersection below is meaningful only for legacy
    # native-agent files (no role-class). Role-file capability satisfaction is
    # enforced statically by tests/unit/skill-structure/test_capability_gate.py,
    # exactly as the mechanism-dispatch Step 5b gate does further down this file.
    VO_ROLE_CLASS="$(yq --front-matter=extract '.["role-class"] // ""' "$VO_ROLE_PATH" 2>/dev/null || echo "")"
    if [ -n "$VO_ROLE_CLASS" ]; then
        exit 0
    fi
    # Capability intersection (legacy native-agent files only): role.requires ⊆ binding.provides.
    VO_REQUIRES="$(yq --front-matter=extract -o=json '.requires // []' "$VO_ROLE_PATH" 2>/dev/null || echo "[]")"
    VO_PROVIDES="$(jq -c '.provides // []' <<<"$VO_BINDING_JSON")"
    VO_MISSING="$(jq -r --argjson req "$VO_REQUIRES" --argjson prov "$VO_PROVIDES" -n '$req - $prov | .[]' 2>/dev/null || true)"
    if [ -n "$VO_MISSING" ]; then
        while IFS= read -r cap; do
            [ -z "$cap" ] && continue
            echo "MISSING_CAPABILITY=$cap" >&2
        done <<<"$VO_MISSING"
        exit 2
    fi
    exit 0
fi

# --- Env defaults ---
: "${ACPX_ROLE_SLUG:=}"
: "${ACPX_BINDING_PRESET:=}"
: "${ACPX_BINDING_JSON:=}"
# Written long-hand on purpose: bash ends `${ACPX_INPUTS_JSON:={}}` at the first `}` and
# assigns the single character `{`, which no JSON parser accepts. The slot pass below
# hid that, because its `jq ... 2>/dev/null || true` turned the parse error into an empty
# slot list. Behavior is unchanged for a caller that passes real inputs.
[ -n "${ACPX_INPUTS_JSON:-}" ] || ACPX_INPUTS_JSON='{}'
: "${ACPX_RUN_ID:=run-unknown}"
: "${ACPX_EXPECTED_MAJOR:=1}"
: "${WORKTREE:=}"
: "${ACPX_DRY_RUN:=0}"
: "${ACPX_FAKE_CHILD_OUTPUT:=}"
: "${RELAY_MAX_TURNS:=10}"
: "${ACPX_SESSION_NAME_OVERRIDE:=}"
: "${RELAY_ROLE_PATH:=}"
# The codex `--agent` override is gone (relay 4.51.0). acpx 0.12.1 moved its own
# codex adapter pin from the broken @agentclientprotocol/codex-acp@^0.0.44 to
# ^1.1.5, which resolves to the same adapter the override used to fetch by hand.
# relay's floor is now 0.13.2 (scripts/acpx-floor.sh), so every codex path passes
# the plain `codex` positional and lets acpx resolve the adapter. Removing the
# override also unblocks the codex session driver: `--agent` could not be combined
# with a positional engine, which is why that driver could never use it and could
# not set effort through session config. See
# docs/superpowers/specs/2026-09-05-relay-acpx-0.13.2-upgrade-design.md.

# --- Permission grant (single site) ---
# Every acpx turn relay runs gets the widest grant acpx exposes: `--approve-all`
# answers each ACP permission request, and the policy file sets the same default
# for acpx's per-tool rule engine. Both are unconditional. Before 4.51.0 the flag
# was gated on `permissions: approve-all`, so the three roles bound to
# `approve-reads` ran with acpx's non-TTY fallback of `deny` and had every write
# request refused with nothing reporting it. `permissions` in bindings/presets.yaml
# now records role intent only; read-only is enforced by the role body.
ACPX_POLICY_FILE_DEFAULT="${REPO_ROOT}/bindings/acpx-policy.json"
: "${ACPX_POLICY_FILE:=$ACPX_POLICY_FILE_DEFAULT}"

# --- Step 1: load role file ---
# §5 resolution order:
#   1. RELAY_ROLE_PATH override (documented external API; typed error on missing file)
#   2. roles/<slug>.md (collapsed role files)
#   3. agents/<slug>.md (kept registered agents only: code-reviewer, scout, leaf-worker, leaf-reader, gatherer, strategist, analyst)
#   Typed error ROLE_FILE_MISSING on all-miss.
# Honor pre-set ROLE_PATH env (used by the codex-session recursion path which
# pivots ROLE_PATH to the driver role on re-entry without renaming the slug).
if [ -n "${RELAY_ROLE_PATH:-}" ]; then
    ROLE_PATH="$RELAY_ROLE_PATH"
fi
if [ -z "${ROLE_PATH:-}" ]; then
    if [ -f "${REPO_ROOT}/roles/${ACPX_ROLE_SLUG}.md" ]; then
        ROLE_PATH="${REPO_ROOT}/roles/${ACPX_ROLE_SLUG}.md"
    elif [ -f "${REPO_ROOT}/agents/${ACPX_ROLE_SLUG}.md" ]; then
        ROLE_PATH="${REPO_ROOT}/agents/${ACPX_ROLE_SLUG}.md"
    else
        ROLE_PATH=""
    fi
fi
if [ -z "${ROLE_PATH:-}" ] || [ ! -f "${ROLE_PATH}" ]; then
    if [ -n "${RELAY_ROLE_PATH:-}" ]; then
        echo "ROLE_FILE_MISSING: ${ACPX_ROLE_SLUG} (RELAY_ROLE_PATH=$RELAY_ROLE_PATH not found)" >&2
    else
        echo "ROLE_FILE_MISSING: ${ACPX_ROLE_SLUG} (checked roles/ then agents/)" >&2
    fi
    exit 65
fi

# Native agents carry no role-version frontmatter (fork-only key, dropped in the
# native transform); ACPX_EXPECTED_MAJOR is now vestigial and gates nothing.

# --- Step 2/3: substitution ---
# Native agents declare no `input-slots`; slot names are the KEYS of the
# supplied ACPX_INPUTS_JSON. There is no required-slot enforcement (the native
# shape carries no `required` marker) — unsupplied placeholders simply remain.
# Honor pre-set PROMPT_DIR / PROMPT_FILE env (codex-session recursion path).
# [inferred]
: "${PROMPT_DIR:=${WORKTREE}/.acpx-prompts/${ACPX_RUN_ID}}"
mkdir -p "$PROMPT_DIR"
: "${PROMPT_FILE:=$PROMPT_DIR/${ACPX_ROLE_SLUG}.md}"

# Extract role body (everything after the second `---`).
# On codex-session recursion, $PROMPT_FILE is already the fully-materialized
# driver-prompt.md with prepended frontmatter; do NOT overwrite it.
# [inferred]
if [ -z "${ACPX_CODEX_SESSION_RECURSION:-}" ]; then
    awk '/^---[[:space:]]*$/{c++; next} c>=2' "$ROLE_PATH" > "$PROMPT_FILE"
fi

# Build placeholder→value mapping (single-pass; per-slot rewrite forbidden).
# Slot names = keys of ACPX_INPUTS_JSON. Each value is substituted as a plain
# string into {{UPPER_SNAKE}} (lowercase + `-`→`_`, uppercased).
# Skipped on codex-session recursion (driver consumes prepended frontmatter, not
# placeholder substitution). [inferred]
ACPX_SUBST_JSON='{}'
ALL_SLOTS=""
if [ -z "${ACPX_CODEX_SESSION_RECURSION:-}" ]; then
    ALL_SLOTS="$(jq -r 'keys[]' <<<"$ACPX_INPUTS_JSON" 2>/dev/null || true)"
fi
if [ -n "$ALL_SLOTS" ]; then
    while IFS= read -r slot; do
        [ -z "$slot" ] && continue
        # Native agents declare no slot types; every input value is a string.
        value=$(jq -r --arg k "$slot" '.[$k] // empty' <<<"$ACPX_INPUTS_JSON")
        upper=$(printf '%s' "$slot" | tr '[:lower:]-' '[:upper:]_')
        placeholder="{{${upper}}}"
        ACPX_SUBST_JSON=$(jq --arg k "$placeholder" --arg v "$value" '. + {($k): $v}' <<<"$ACPX_SUBST_JSON")
    done <<<"$ALL_SLOTS"
fi
export ACPX_SUBST_JSON

# Single-pass python substitution OUTSIDE the loop
python3 - "$PROMPT_FILE" <<'PY'
import json, re, sys, os
path = sys.argv[1]
mapping = json.loads(os.environ.get("ACPX_SUBST_JSON", "{}"))
if not mapping:
    sys.exit(0)
pattern = re.compile("|".join(re.escape(k) for k in mapping.keys()))
with open(path) as f: text = f.read()
out = pattern.sub(lambda m: mapping[m.group(0)], text)
with open(path, "w") as f: f.write(out)
PY

# --- Step 4: binding resolution ---
BINDING_JSON=""
if [ -n "$ACPX_BINDING_PRESET" ]; then
    PRESETS_PATH="${REPO_ROOT}/bindings/presets.yaml"
    BINDING_JSON=$(yq -o=json ".roles.\"${ACPX_BINDING_PRESET}\"" "$PRESETS_PATH" 2>/dev/null || echo "null")
    if [ "$BINDING_JSON" = "null" ] || [ -z "$BINDING_JSON" ]; then
        echo "acpx-dispatch: binding preset not found: $ACPX_BINDING_PRESET" >&2
        exit 68
    fi
elif [ -n "$ACPX_BINDING_JSON" ]; then
    BINDING_JSON="$ACPX_BINDING_JSON"
else
    echo "acpx-dispatch: ACPX_BINDING_PRESET or ACPX_BINDING_JSON required" >&2
    exit 68
fi

MECHANISM=$(jq -r '.mechanism // ""' <<<"$BINDING_JSON")
# Optional override: a caller may pass an effective mechanism via
# ACPX_MECHANISM_OVERRIDE (per-role binding resolution at Workflow-generation
# time). Absent override falls back to the static presets `mechanism`. [inferred]
if [ -n "${ACPX_MECHANISM_OVERRIDE:-}" ]; then
    MECHANISM="$ACPX_MECHANISM_OVERRIDE"
fi
SESSION=$(jq -r '.session // ""' <<<"$BINDING_JSON")
ISOLATION=$(jq -r '.isolation // ""' <<<"$BINDING_JSON")
COMP_THRESHOLD=$(jq -r '.compaction.threshold' <<<"$BINDING_JSON")
TIMEOUT_SECONDS=$(jq -r '.timeout_seconds // 1800' <<<"$BINDING_JSON")
RETRIES=$(jq -r '.retries // 0' <<<"$BINDING_JSON")
PERMISSIONS=$(jq -r '.permissions // ""' <<<"$BINDING_JSON")
# Model + reasoning effort come from the per-engine `modalities` block, selected
# by the effective mechanism (acpx-claude -> modalities.claude; codex-session ->
# modalities.codex; acpx-opencode -> modalities.opencode). Flat .model/.effort
# remain the back-compat fallback for inline bindings.
case "$MECHANISM" in
    acpx-claude)
        MODEL=$(jq -r '.modalities.claude.model // .model // ""' <<<"$BINDING_JSON")
        EFFORT=$(jq -r '.modalities.claude.effort // .effort // ""' <<<"$BINDING_JSON")
        ;;
    codex-session|acpx-codex)
        MODEL=$(jq -r '.modalities.codex.model // .model // ""' <<<"$BINDING_JSON")
        EFFORT=$(jq -r '.modalities.codex.effort // .effort // ""' <<<"$BINDING_JSON")
        ;;
    acpx-opencode)
        # Opencode model ids are provider-qualified (opencode-go/<model>) — the
        # prefix pins the serving provider. Effort is typically absent: open-weight
        # models define no acpx effort values; the driver soft-degrades on set.
        MODEL=$(jq -r '.modalities.opencode.model // .model // ""' <<<"$BINDING_JSON")
        EFFORT=$(jq -r '.modalities.opencode.effort // .effort // ""' <<<"$BINDING_JSON")
        ;;
    *)
        MODEL=$(jq -r '.model // .modalities.claude.model // ""' <<<"$BINDING_JSON")
        EFFORT=$(jq -r '.effort // .modalities.claude.effort // ""' <<<"$BINDING_JSON")
        ;;
esac

# 4.46.0 — the two category overrides. `--fixes-model` / `--verification-model`
# name a Claude tier, so they apply on the Claude legs only: `sonnet` and `opus` are
# not ids that the codex or opencode adapters serve, and forwarding one there would
# fail engine-side with an unknown-model error. On those two legs the modality pin
# stands, and the command body prints which legs an override reached.
# The flag enum is sonnet | opus | fable — every one a concrete Claude id — so the
# `inherit` sentinel refused further down cannot arrive through this path.
RELAY_CATEGORY=$(jq -r '.category // ""' <<<"$BINDING_JSON")
case "$RELAY_CATEGORY" in
    fixes)        CATEGORY_MODEL="${RELAY_FIXES_MODEL:-}" ;;
    verification) CATEGORY_MODEL="${RELAY_VERIFICATION_MODEL:-}" ;;
    *)            CATEGORY_MODEL="" ;;
esac
if [ -n "$CATEGORY_MODEL" ]; then
    case "$MECHANISM" in
        acpx-claude)
            echo "acpx-dispatch: [info] ${RELAY_CATEGORY}-model=$CATEGORY_MODEL replaces modalities.claude.model=$MODEL for role ${ACPX_ROLE_SLUG}" >&2
            MODEL="$CATEGORY_MODEL"
            ;;
        *)
            echo "acpx-dispatch: [warn] ${RELAY_CATEGORY}-model=$CATEGORY_MODEL names a Claude tier and mechanism $MECHANISM is not a Claude leg; role ${ACPX_ROLE_SLUG} keeps model=$MODEL" >&2
            ;;
    esac
fi

# --- Step 5: binding schema validation ---
if [ "$MECHANISM" = "acpx-codex" ] && [ "$SESSION" = "named" ]; then
    echo "acpx-dispatch: binding schema invalid (mechanism=acpx-codex with session=named)" >&2
    exit 68
fi
if [ "$MECHANISM" = "in-session" ] && [ -n "$COMP_THRESHOLD" ] && [ "$COMP_THRESHOLD" != "null" ]; then
    echo "acpx-dispatch: binding schema invalid (mechanism=in-session with non-null compaction.threshold)" >&2
    exit 68
fi
if [ "$ISOLATION" = "worktree" ] && [ -z "$WORKTREE" ]; then
    echo "acpx-dispatch: binding schema invalid (isolation=worktree but WORKTREE empty)" >&2
    exit 68
fi
# max_turns binding schema validation removed — multi-turn management moved to
# delegate-and-watch watcher (L2 skill); thin drivers are single-turn only.

# --- Step 5b: capability validation (spec §5.2 step 2) ---
# Intersect role.requires with binding.provides. Treat absent/empty as trivially satisfied.
# Role files (PR3 §4): skip runtime capability intersection — role `requires:` declares
# capability namespaces for --validate-only mode, not envelope-token namespaces.
# Only apply the intersection for legacy native-agent files (no role-class: frontmatter key).
IS_ROLE_FILE="$(yq --front-matter=extract '.["role-class"] // ""' "$ROLE_PATH" 2>/dev/null || echo "")"
if [ -z "$IS_ROLE_FILE" ]; then
    ROLE_REQUIRES_JSON="$(yq --front-matter=extract -o=json '.requires // []' "$ROLE_PATH" 2>/dev/null || echo "[]")"
    BINDING_PROVIDES_JSON="$(jq -c '.provides // []' <<<"$BINDING_JSON")"
    MISSING_CAPS="$(jq -r --argjson req "$ROLE_REQUIRES_JSON" --argjson prov "$BINDING_PROVIDES_JSON" -n '$req - $prov | .[]' 2>/dev/null || true)"
    if [ -n "$MISSING_CAPS" ]; then
        while IFS= read -r cap; do
            [ -z "$cap" ] && continue
            echo "MISSING_CAPABILITY=$cap" >&2
        done <<<"$MISSING_CAPS"
        exit 68
    fi
fi

# --- DRY_RUN gate (load-bearing): after substitution + binding validation, before mechanism dispatch ---
if [ "$ACPX_DRY_RUN" = "1" ]; then
    echo '{"status":"completed","output":"DRY_RUN","tokens":{},"sidecars":{},"elapsed_seconds":0,"attempt_count":0}'
    exit 0
fi

# --- Step 6: mechanism dispatch ---
if [ "$MECHANISM" = "in-session" ]; then
    echo "verification_failed: in-session mechanism not supported by acpx-dispatch — handled by orchestrator via dispatching-parallel-agents" >&2
    exit 69
fi

case "$MECHANISM" in
    acpx-claude|acpx-codex|acpx-opencode|codex-session) ;;
    *)
        echo "acpx-dispatch: unknown mechanism: $MECHANISM" >&2
        exit 68
        ;;
esac

# 4.14.0: `inherit` is the in-session never-downshift sentinel in the flat model
# field. It is meaningless cross-process (no session model to inherit) and must
# never be forwarded to an engine as a literal model id — reachable only via an
# inline binding (or incomplete modalities block) whose fallback read landed on
# the flat field. Fail here, naming the real misconfiguration, instead of dying
# engine-side with an unknown-model error.
if [ "$MODEL" = "inherit" ]; then
    echo "acpx-dispatch: model 'inherit' is in-session-only — binding for mechanism $MECHANISM must carry a concrete model id in modalities.* (or flat model)" >&2
    exit 68
fi

# Resolve session sentinel
RESOLVED_SESSION="$SESSION"
if [ "$SESSION" = "named" ]; then
    RESOLVED_SESSION="${ACPX_RUN_ID}-${ACPX_ROLE_SLUG}"
fi

# --- Preamble assembly (shared by every acpx mechanism) ---
# The child receives two blocks, in order:
#   1. <<DO_NOT_LOAD_SKILLS>> — context isolation, inline because it is about how this
#      process is invoked rather than about the role contract.
#   2. preamble.md — the agents-autonomous contract (spec §5.5): one-shot posture,
#      do-not-commit, the AUTONOMY modes, and the licence to emit `NEEDS_DECISION:`.
#
# 4.20.0: block 2 was documented as part of this skill (SKILL.md) and as being
# prepended (docs/dispatch-contract.md) but no code ever read the file — the child
# only ever received block 1. That mattered because `NEEDS_DECISION:` is a frozen
# public sentinel with a full receiving path (driver classification, the
# delegate-and-watch needs-decision bucket, `sessions detach`), and nothing had ever
# told a child it was allowed to emit one. The receiving half was unreachable.
#
# preamble.md defaults to fire-and-forget when AUTONOMY is unset, so delivering it
# does not change behaviour for callers that never set it.
build_preamble() {
    local pre="${SCRIPT_DIR}/preamble.md"
    if [ ! -f "$pre" ]; then
        echo "acpx-dispatch: missing required preamble at ${pre}" >&2
        exit 66
    fi
    printf '%s\n' '<<DO_NOT_LOAD_SKILLS>>'
    printf '%s\n' 'You are a primitive role running under acpx. Do not invoke'
    printf '%s\n' '`Skill` or load `superpowers:*` skill instructions. Read the'
    printf '%s\n' 'task below and act on it directly.'
    printf '%s\n\n' '<<END_DO_NOT_LOAD_SKILLS>>'
    cat "$pre"
    printf '\n\n'
}

# --- CODEX_CONFIG assembly (shared by every codex path) ---
# The codex-acp adapter takes reasoning effort as a JSON object merged into the
# session config, not as a model-id suffix (acpx >= 0.12.0 rejects the bracket
# form). This is the single site that encodes it, used by the fast path, the
# driver path, and the generic acpx-codex loop.
#
# It also carries the codex half of the wide permission grant. `--approve-all` and
# the acpx policy file answer acpx's own permission requests, but codex-cli keeps a
# second gate of its own (approval policy + sandbox), and the one-shot `exec` path
# has no `set` subcommand to widen it. These two keys widen it through the same
# adapter config. The multi-turn driver does it with `set mode agent-full-access`.
# Both keys are emitted even when effort is unset, so the grant never depends on
# the role having an effort pinned.
build_codex_config() {
    if [ -n "${1:-}" ]; then
        printf '{"model_reasoning_effort":"%s","approval_policy":"never","sandbox_mode":"danger-full-access"}' "$1"
    else
        printf '{"approval_policy":"never","sandbox_mode":"danger-full-access"}'
    fi
}

# --- Step 5c: codex-session dispatch (spec §4 thin-driver redesign) ---
# Two paths based on per-role turn-protocol:
#   Fast-path:  no verify_artifact → acpx codex exec -f directly (single-turn, no driver).
#   Driver:     otherwise → spawn codex-session-driver.sh as a child subprocess.
# Both paths prepend the same assembled preamble and apply the same
# extract_envelope filter to captured stdout (spec §4.5 fast-path parity).
if [ "$MECHANISM" = "codex-session" ]; then
    : "${ACPX_RUN_ID:?codex-session requires ACPX_RUN_ID}"
    : "${ACPX_ROLE_SLUG:?codex-session requires ACPX_ROLE_SLUG}"
    if [ -z "${EFFORT:-}" ]; then
        echo "acpx-dispatch: codex-session requires effort (got empty)" >&2
        exit 68
    fi

    # Resolve turn-protocol: read TP_* env first (test harness override), then
    # parse-turn-protocol.sh for verify_artifact. [inferred]
    if [ -z "${TP_VERIFY_ARTIFACT:-}" ] && [ -f "${SCRIPT_DIR}/parse-turn-protocol.sh" ]; then
        # Export SLOT_* env from the dispatcher's resolved slot values so the
        # parser's {{NAME}} substitution can resolve them. [inferred]
        if [ -n "$ALL_SLOTS" ]; then
            while IFS= read -r _slot; do
                [ -z "$_slot" ] && continue
                _upper=$(printf '%s' "$_slot" | tr '[:lower:]-' '[:upper:]_')
                _raw=$(jq -r --arg k "$_slot" '.[$k] // empty' <<<"$ACPX_INPUTS_JSON")
                _existing="SLOT_${_upper}"
                [ -z "${!_existing-}" ] && export "SLOT_${_upper}=${_raw}"
            done <<<"$ALL_SLOTS"
        fi
        # shellcheck disable=SC1091
        source "${SCRIPT_DIR}/parse-turn-protocol.sh"
        parse_turn_protocol "$ROLE_PATH" || {
            echo "acpx-dispatch: parse-turn-protocol failed" >&2
            exit 68
        }
    fi

    TP_TERMINAL_TOKEN_RESOLVED="${TP_TERMINAL_TOKEN:-ROLE_DONE}"
    TP_VERIFY_ARTIFACT_RESOLVED="${TP_VERIFY_ARTIFACT:-}"

    # Unresolved {{...}} in verify_artifact → downgrade to empty (skip freshness).
    case "${TP_VERIFY_ARTIFACT_RESOLVED}" in
        *'{{'*) TP_VERIFY_ARTIFACT_RESOLVED="" ;;
    esac

    # acpx >= 0.12.0 strictly validates --model against the adapter-advertised
    # ids, which are plain (`gpt-5.6-terra`); the pre-0.12 bracket notation
    # (`gpt-5.6-terra[high]`) is rejected at exec time. Reasoning effort
    # therefore rides CODEX_CONFIG — codex-acp adapter env, a JSON object
    # merged into the Codex session config — instead of the model id.
    # Verified 2026-07-13: codex rollout turn_context records the requested
    # effort; `-c model_reasoning_effort=...` on the adapter argv does NOT.
    CODEX_EXEC_CONFIG="$(build_codex_config "$EFFORT")"

    # Plain positional engine: acpx >= 0.12.1 resolves a working codex adapter on
    # its own (see the note at the top of this file).
    CODEX_ENGINE_ARGS=(codex)

    # Prepend the assembled preamble (isolation block + agents-autonomous contract).
    tmp_prompt=$(mktemp)
    trap "rm -f \"$tmp_prompt\"" EXIT
    { build_preamble; cat "$PROMPT_FILE"; } > "$tmp_prompt"

    # extract_envelope filter (shared with driver script).
    extract_envelope() {
        grep -E "^([A-Z][A-Z0-9_]*=.*|${TP_TERMINAL_TOKEN_RESOLVED})$" || true
    }

    # Test hook for ACPX_PRINT_CMD_ONLY parity (used by existing cli-shape tests). [inferred]
    if [ -n "${ACPX_PRINT_CMD_ONLY:-}" ]; then
        if [ -z "$TP_VERIFY_ARTIFACT_RESOLVED" ]; then
            FP_CMD=(env "CODEX_CONFIG=${CODEX_EXEC_CONFIG}" acpx --format json --json-strict --approve-all --permission-policy "$ACPX_POLICY_FILE" --cwd "${WORKTREE:-$REPO_ROOT}" --model "$MODEL" --timeout "$TIMEOUT_SECONDS" "${CODEX_ENGINE_ARGS[@]}" exec -f "$tmp_prompt")
            printf '%s\n' "${FP_CMD[@]}" >&2
        else
            printf 'codex-session-driver.sh\n' >&2
            printf 'ACPX_SESSION_NAME=%s\n' "${ACPX_RUN_ID}-${ACPX_ROLE_SLUG}" >&2
        fi
        jq -n --arg engine codex \
              '{status:"completed",output:"",tokens:{},sidecars:{},elapsed_seconds:0,attempt_count:1,_cli_engine:$engine}'
        rm -f "$tmp_prompt"
        exit 0
    fi

    # Fast-path: no verify_artifact → direct exec (single-turn, no session driver).
    if [ -z "$TP_VERIFY_ARTIFACT_RESOLVED" ]; then
        tmp_out=$(mktemp)
        FP_CMD=(env "CODEX_CONFIG=${CODEX_EXEC_CONFIG}" acpx --format json --json-strict --approve-all --permission-policy "$ACPX_POLICY_FILE" --cwd "${WORKTREE:-$REPO_ROOT}" --model "$MODEL" --timeout "$TIMEOUT_SECONDS" "${CODEX_ENGINE_ARGS[@]}" exec -f "$tmp_prompt")
        if [ -n "${ACPX_FAKE_CHILD_OUTPUT:-}" ]; then
            # The fake is already envelope text, not NDJSON — it stands in for the
            # converted stream, so it bypasses acpx-envelope.sh.
            printf '%b' "$ACPX_FAKE_CHILD_OUTPUT" > "$tmp_out"
            acpx_rc=0
        else
            # --format json --json-strict emits raw ACP JSON-RPC, one object per line.
            # The raw stream is kept beside the extracted text for forensics; every
            # reader below ($tmp_out) still sees plain envelope text.
            "${FP_CMD[@]}" > "$tmp_out.ndjson" 2>&1 && acpx_rc=0 || acpx_rc=$?
            "${SCRIPT_DIR}/acpx-envelope.sh" < "$tmp_out.ndjson" > "$tmp_out"
        fi
        envelope_out=$(extract_envelope < "$tmp_out")
        # NEEDS_DECISION: full-output scan (fast-path has no named session to detach).
        # Frozen first-line sentinels: BLOCKED: and NEEDS_DECISION:
        # Capture regex (frozen public envelope contract): ^([A-Z][A-Z0-9_]*=.*|ROLE_DONE)$
        # Misframed-output guard: co-presence with ROLE_DONE or multiple ND lines → BLOCKED.
        _nd_count=$(grep -c '^NEEDS_DECISION:' "$tmp_out" || true)
        _has_done=$(grep -c "^${TP_TERMINAL_TOKEN_RESOLVED}$" "$tmp_out" || true)
        if [ "${_nd_count:-0}" -gt 1 ] || { [ "${_nd_count:-0}" -eq 1 ] && [ "${_has_done:-0}" -gt 0 ]; }; then
            printf 'ROLE_RESULT=BLOCKED\nBLOCKED_REASON=misframed_output\n%s\n' "$TP_TERMINAL_TOKEN_RESOLVED"
            rm -f "$tmp_prompt" "$tmp_out" "$tmp_out.ndjson"
            exit 0
        fi
        if [ "${_nd_count:-0}" -eq 1 ]; then
            _nd_question=$(grep '^NEEDS_DECISION:' "$tmp_out" | head -1 | sed -E 's/^NEEDS_DECISION:[[:space:]]*//')
            printf 'ROLE_RESULT=NEEDS_DECISION\nQUESTION_TEXT=%s\n%s\n' "$_nd_question" "$TP_TERMINAL_TOKEN_RESOLVED"
            rm -f "$tmp_prompt" "$tmp_out" "$tmp_out.ndjson"
            exit 0
        fi
        # Unparseable-envelope guard (spec §9 PR1 item 1): if the output contains neither a
        # terminal token nor any KEY=VALUE envelope line, it cannot be routed — emit a typed
        # terminal error rather than letting the watcher classify it as not-done. [inferred]
        _kv_count=$(grep -cE '^[A-Z][A-Z0-9_]*=' "$tmp_out" || true)
        _term_count=$(grep -c "^${TP_TERMINAL_TOKEN_RESOLVED}$" "$tmp_out" || true)
        if [ "${_kv_count:-0}" -eq 0 ] && [ "${_term_count:-0}" -eq 0 ]; then
            printf 'ROLE_RESULT=ERRORED\nERRORED_REASON=unparseable_envelope\n%s\n' "$TP_TERMINAL_TOKEN_RESOLVED"
            rm -f "$tmp_prompt" "$tmp_out" "$tmp_out.ndjson"
            exit 0
        fi
        printf '%s\n' "$envelope_out"
        if [ "$acpx_rc" -ne 0 ] && [ -z "$envelope_out" ]; then
            printf 'ROLE_RESULT=BLOCKED\nBLOCKED_REASON=fast-path acpx exec failed (rc=%s)\n%s\n' \
                "$acpx_rc" "$TP_TERMINAL_TOKEN_RESOLVED"
        fi
        rm -f "$tmp_prompt" "$tmp_out" "$tmp_out.ndjson"
        exit "$acpx_rc"
    fi

    # Driver path (verify_artifact present — freshness gate required).
    #
    # 4.20.0: this used to set EFFECTIVE_MODEL="${MODEL}[${EFFORT}]". acpx >= 0.12.0
    # validates --model against adapter-advertised plain ids and rejects the pre-0.12
    # bracket form, so every dispatch down this path failed at the adapter — and this
    # is the path taken by exactly the four roles that declare verify_artifact
    # (implementer, test-writer, fix-coder, plan-writer), i.e. the entire codex
    # implementation pipeline. The comment here previously acknowledged the path was
    # non-functional rather than fixing it.
    #
    # Now uses the same encoding as the fast path and the acpx-codex loop: a plain
    # model id, with effort riding CODEX_CONFIG for the codex-acp adapter to merge
    # into the session config. CODEX_EXEC_CONFIG (built once above via
    # build_codex_config) is reused here and threaded through the sidecar as well,
    # so a delegate-and-watch re-invocation resolves the same effort.
    EFFECTIVE_MODEL="$MODEL"
    driver="${SCRIPT_DIR}/codex-session-driver.sh"
    [ -n "${DRIVER_OVERRIDE:-}" ] && driver="$DRIVER_OVERRIDE"
    session_name="${ACPX_SESSION_NAME_OVERRIDE:-${ACPX_RUN_ID}-${ACPX_ROLE_SLUG}}"

    # Write env sidecar for the delegate-and-watch watcher (10 vars: codex session-driver
    # contract — the 8 shared vars, plus RELAY_MAX_TURNS and CODEX_CONFIG).
    # Values are written shell-quoted (printf %q) so source mis-parses paths with spaces/
    # special chars silently — any value containing unusual chars stays correctly bounded.
    sidecar_file="${HOME}/.acpx/sessions/${session_name}.env"
    mkdir -p "${HOME}/.acpx/sessions"
    {
        printf 'ACPX_ENGINE=%q\n' "codex"
        printf 'ACPX_MODEL=%q\n' "${EFFECTIVE_MODEL}"
        printf 'ACPX_CWD=%q\n' "${WORKTREE:-$REPO_ROOT}"
        printf 'ACPX_TIMEOUT=%q\n' "${TIMEOUT_SECONDS}"
        printf 'ACPX_SESSION_NAME=%q\n' "${session_name}"
        printf 'ACPX_PROMPT_FILE=%q\n' "${tmp_prompt}"
        printf 'ACPX_TERMINAL_TOKEN=%q\n' "${TP_TERMINAL_TOKEN_RESOLVED}"
        printf 'ACPX_VERIFY_ARTIFACT=%q\n' "${TP_VERIFY_ARTIFACT_RESOLVED}"
        printf 'RELAY_MAX_TURNS=%q\n' "${RELAY_MAX_TURNS:-10}"
        printf 'ACPX_EFFORT=%q\n' "${EFFORT}"
        printf 'ACPX_POLICY_FILE=%q\n' "${ACPX_POLICY_FILE}"
        # CODEX_CONFIG is no longer read by codex-session-driver.sh, which now sets
        # effort and sandbox mode through session config. It stays in the sidecar for
        # one release so a delegate-and-watch watcher still running the 4.50.0
        # contract sources this file cleanly. Remove it in 4.52.0.
        printf 'CODEX_CONFIG=%q\n' "${CODEX_EXEC_CONFIG}"
    } > "$sidecar_file"

    ACPX_ENGINE=codex \
    ACPX_MODEL="$EFFECTIVE_MODEL" \
    ACPX_EFFORT="$EFFORT" \
    ACPX_POLICY_FILE="$ACPX_POLICY_FILE" \
    CODEX_CONFIG="$CODEX_EXEC_CONFIG" \
    ACPX_CWD="${WORKTREE:-$REPO_ROOT}" \
    ACPX_TIMEOUT="$TIMEOUT_SECONDS" \
    ACPX_SESSION_NAME="$session_name" \
    ACPX_PROMPT_FILE="$tmp_prompt" \
    ACPX_TERMINAL_TOKEN="$TP_TERMINAL_TOKEN_RESOLVED" \
    ACPX_VERIFY_ARTIFACT="$TP_VERIFY_ARTIFACT_RESOLVED" \
    bash "$driver"
    driver_rc=$?
    rm -f "$tmp_prompt"
    exit "$driver_rc"
fi

# --- Step 6b: acpx-claude / acpx-opencode driver dispatch ---
# Mirrors the codex-session block. Routes to a per-engine
# session driver rather than one-shot exec. Exits before the shared
# STDOUT_FILE/ATTEMPT loop (steps 7-9 are driver responsibilities).
if [ "$MECHANISM" = "acpx-claude" ] || [ "$MECHANISM" = "acpx-opencode" ]; then
    : "${ACPX_RUN_ID:?acpx-claude/opencode requires ACPX_RUN_ID}"
    : "${ACPX_ROLE_SLUG:?acpx-claude/opencode requires ACPX_ROLE_SLUG}"

    # Resolve turn-protocol: read TP_* env first (test harness override), then
    # parse-turn-protocol.sh for verify_artifact. [inferred]
    if [ -z "${TP_VERIFY_ARTIFACT:-}" ] && [ -f "${SCRIPT_DIR}/parse-turn-protocol.sh" ]; then
        if [ -n "$ALL_SLOTS" ]; then
            while IFS= read -r _slot; do
                [ -z "$_slot" ] && continue
                _upper=$(printf '%s' "$_slot" | tr '[:lower:]-' '[:upper:]_')
                _raw=$(jq -r --arg k "$_slot" '.[$k] // empty' <<<"$ACPX_INPUTS_JSON")
                _existing="SLOT_${_upper}"
                [ -z "${!_existing-}" ] && export "SLOT_${_upper}=${_raw}"
            done <<<"$ALL_SLOTS"
        fi
        # shellcheck disable=SC1091
        source "${SCRIPT_DIR}/parse-turn-protocol.sh"
        parse_turn_protocol "$ROLE_PATH" || {
            echo "acpx-dispatch: parse-turn-protocol failed" >&2
            exit 68
        }
    fi

    TP_TERMINAL_TOKEN_RESOLVED="${TP_TERMINAL_TOKEN:-ROLE_DONE}"
    TP_VERIFY_ARTIFACT_RESOLVED="${TP_VERIFY_ARTIFACT:-}"

    case "${TP_VERIFY_ARTIFACT_RESOLVED}" in
        *'{{'*) TP_VERIFY_ARTIFACT_RESOLVED="" ;;
    esac

    # Prepend the assembled preamble (identical to the codex-session block).
    tmp_prompt=$(mktemp)
    trap "rm -f \"$tmp_prompt\"" EXIT
    { build_preamble; cat "$PROMPT_FILE"; } > "$tmp_prompt"

    # Derive engine name (strip acpx- prefix: acpx-claude → claude, acpx-opencode → opencode).
    ENGINE="${MECHANISM#acpx-}"

    # Compute session name here so the test hook below reports the same value
    # that the real dispatch path uses (ACPX_SESSION_NAME_OVERRIDE honoured on both paths).
    session_name="${ACPX_SESSION_NAME_OVERRIDE:-${ACPX_RUN_ID}-${ACPX_ROLE_SLUG}}"

    # Test hook: print driver name + session name to stderr; emit minimal JSON envelope; exit 0.
    if [ -n "${ACPX_PRINT_CMD_ONLY:-}" ]; then
        printf '%s-session-driver.sh\n' "$ENGINE" >&2
        printf 'ACPX_SESSION_NAME=%s\n' "$session_name" >&2
        jq -n --arg engine "$ENGINE" \
              '{status:"completed",output:"",tokens:{},sidecars:{},elapsed_seconds:0,attempt_count:1,_cli_engine:$engine}'
        rm -f "$tmp_prompt"
        exit 0
    fi

    # Driver dispatch (11-var env contract for claude/opencode, spec §5.4).
    driver="${SCRIPT_DIR}/${ENGINE}-session-driver.sh"
    [ -n "${DRIVER_OVERRIDE:-}" ] && driver="$DRIVER_OVERRIDE"

    # Write env sidecar for the delegate-and-watch watcher (11 vars: claude/opencode
    # contract — the 8 shared vars, plus ACPX_EFFORT, ACPX_PERMISSIONS, RELAY_MAX_TURNS).
    # Values are written shell-quoted (printf %q) so source mis-parses paths with spaces/
    # special chars silently — any value containing unusual chars stays correctly bounded.
    sidecar_file="${HOME}/.acpx/sessions/${session_name}.env"
    mkdir -p "${HOME}/.acpx/sessions"
    {
        printf 'ACPX_ENGINE=%q\n' "${ENGINE}"
        printf 'ACPX_MODEL=%q\n' "${MODEL}"
        printf 'ACPX_CWD=%q\n' "${WORKTREE:-$REPO_ROOT}"
        printf 'ACPX_TIMEOUT=%q\n' "${TIMEOUT_SECONDS}"
        printf 'ACPX_SESSION_NAME=%q\n' "${session_name}"
        printf 'ACPX_PROMPT_FILE=%q\n' "${tmp_prompt}"
        printf 'ACPX_TERMINAL_TOKEN=%q\n' "${TP_TERMINAL_TOKEN_RESOLVED}"
        printf 'ACPX_VERIFY_ARTIFACT=%q\n' "${TP_VERIFY_ARTIFACT_RESOLVED}"
        printf 'ACPX_EFFORT=%q\n' "${EFFORT}"
        printf 'ACPX_PERMISSIONS=%q\n' "${PERMISSIONS}"
        printf 'ACPX_POLICY_FILE=%q\n' "${ACPX_POLICY_FILE}"
        printf 'RELAY_MAX_TURNS=%q\n' "${RELAY_MAX_TURNS:-10}"
    } > "$sidecar_file"

    ACPX_ENGINE="$ENGINE" \
    ACPX_MODEL="$MODEL" \
    ACPX_CWD="${WORKTREE:-$REPO_ROOT}" \
    ACPX_TIMEOUT="$TIMEOUT_SECONDS" \
    ACPX_SESSION_NAME="$session_name" \
    ACPX_PROMPT_FILE="$tmp_prompt" \
    ACPX_EFFORT="$EFFORT" \
    ACPX_PERMISSIONS="$PERMISSIONS" \
    ACPX_POLICY_FILE="$ACPX_POLICY_FILE" \
    ACPX_TERMINAL_TOKEN="$TP_TERMINAL_TOKEN_RESOLVED" \
    ACPX_VERIFY_ARTIFACT="$TP_VERIFY_ARTIFACT_RESOLVED" \
    bash "$driver"
    driver_rc=$?
    rm -f "$tmp_prompt"
    exit "$driver_rc"
fi

STDOUT_FILE="$PROMPT_DIR/${ACPX_ROLE_SLUG}.stdout"
ATTEMPT=0
MAX_ATTEMPTS=$((RETRIES + 1))
START_SECONDS=$SECONDS
STATUS="completed"
TOKENS_JSON='{}'

# Extract required output tokens from the resolved binding's `provides`
# (native model: provides == the agent's relay.envelope_tokens).
REQ_TOKENS="$(jq -r '.provides[]?' <<<"$BINDING_JSON" 2>/dev/null || true)"

# 4.20.0: this mechanism passed $PROMPT_FILE raw, so its children received neither
# the isolation block nor the autonomy contract that both other paths prepend.
# Built once, outside the retry loop — every attempt reuses the same file.
GENERIC_PROMPT=$(mktemp)
trap 'rm -f "$GENERIC_PROMPT"' EXIT
{ build_preamble; cat "$PROMPT_FILE"; } > "$GENERIC_PROMPT"

while [ "$ATTEMPT" -lt "$MAX_ATTEMPTS" ]; do
    ATTEMPT=$((ATTEMPT + 1))

    # --- Step 6.4: invoke child (or fake) ---
    # Build child command per spec Appendix A:
    #   acpx [--cwd D] [--model M] [--approve-all] --timeout T <engine> exec -f <prompt-file>
    # `effort` is a binding-contract field with no standalone acpx CLI flag —
    # for codex it rides the CODEX_CONFIG adapter env (see below).
    # `session` does not apply to one-shot `exec`; RESOLVED_SESSION is still
    # computed above for future Pattern A wiring. [inferred]
    ENGINE="${MECHANISM#acpx-}"
    # acpx >= 0.12.0 validates --model against adapter-advertised plain ids —
    # the pre-0.12 codex bracket encoding (`gpt-5.6-terra[high]`) is rejected.
    # Codex effort rides CODEX_CONFIG (JSON merged into the Codex session
    # config by the codex-acp adapter); other engines take the bare model.
    EFFECTIVE_MODEL="$MODEL"
    CHILD_CMD=()
    # CODEX_CONFIG now carries the sandbox grant as well as effort, so it is set on
    # every codex turn, not only when the role pins an effort.
    if [ "$ENGINE" = "codex" ]; then
        CHILD_CMD+=("env" "CODEX_CONFIG=$(build_codex_config "$EFFORT")")
    fi
    CHILD_CMD+=("acpx" "--format" "json" "--json-strict")
    [ "$ISOLATION" = "worktree" ] && CHILD_CMD+=("--cwd" "$WORKTREE")
    [ -n "$EFFECTIVE_MODEL" ] && CHILD_CMD+=("--model" "$EFFECTIVE_MODEL")
    CHILD_CMD+=("--approve-all" "--permission-policy" "$ACPX_POLICY_FILE")
    CHILD_CMD+=("--timeout" "$TIMEOUT_SECONDS")
    CHILD_CMD+=("$ENGINE")
    CHILD_CMD+=("exec" "-f" "$GENERIC_PROMPT")

    if [ -n "${ACPX_PRINT_CMD_ONLY:-}" ]; then
        # Test hook: print assembled CHILD_CMD (one arg per line) to stderr
        # and emit a minimal valid result envelope on stdout, then stop.
        printf '%s\n' "${CHILD_CMD[@]}" >&2
        jq -n --arg engine "$ENGINE" \
              '{status:"completed",output:"",tokens:{},sidecars:{},elapsed_seconds:0,attempt_count:1,_cli_engine:$engine}'
        exit 0
    fi

    if [ -n "$ACPX_FAKE_CHILD_OUTPUT" ]; then
        printf '%b' "$ACPX_FAKE_CHILD_OUTPUT" > "$STDOUT_FILE"
    else
        # Single foreground invocation. The per-turn --timeout passed to acpx
        # is the only timeout knob (watchdog removed under spec 2026-05-13).
        RC=0
        # --format json --json-strict (added to CHILD_CMD above) emits raw ACP
        # JSON-RPC. Keep the raw stream, hand the readers below plain envelope text.
        "${CHILD_CMD[@]}" > "$STDOUT_FILE.ndjson" 2>&1 || RC=$?
        "${SCRIPT_DIR}/acpx-envelope.sh" < "$STDOUT_FILE.ndjson" > "$STDOUT_FILE"
        if [ "$RC" -ne 0 ]; then
            STATUS="engine_error"
        fi
    fi

    # --- Step 7: token capture ---
    TOKENS_JSON='{}'
    MISSING_TOKEN=""
    if [ -n "$REQ_TOKENS" ]; then
        TAIL_OUT=$(tail -200 "$STDOUT_FILE" 2>/dev/null || echo "")
        while IFS= read -r token; do
            [ -z "$token" ] && continue
            match=$(printf '%s\n' "$TAIL_OUT" | grep -E "^${token}(=.*)?$" | tail -1 || true)
            if [ -z "$match" ]; then
                MISSING_TOKEN="$token"
                break
            fi
            # Extract value if present after =
            if [[ "$match" == *=* ]]; then
                tval="${match#*=}"
            else
                tval=""
            fi
            TOKENS_JSON=$(jq --arg k "$token" --arg v "$tval" '. + {($k): $v}' <<<"$TOKENS_JSON")
        done <<<"$REQ_TOKENS"
    fi

    if [ -z "$MISSING_TOKEN" ]; then
        STATUS="completed"
        break
    else
        STATUS="verification_failed"
    fi
done

# --- Step 8: sidecar validation ---
SIDECARS_JSON='{}'
REQ_SIDECARS="$(yq --front-matter=extract -r '.sidecars[]? | select(.required == true) | .name' "$ROLE_PATH" 2>/dev/null || true)"
if [ -n "$REQ_SIDECARS" ] && [ "$STATUS" = "completed" ]; then
    while IFS= read -r sname; do
        [ -z "$sname" ] && continue
        slot_key="${sname}_output_path"
        spath=$(jq -r --arg k "$slot_key" '.[$k] // ""' <<<"$ACPX_INPUTS_JSON")
        if [ -z "$spath" ] || [ ! -s "$spath" ]; then
            STATUS="verification_failed"
        else
            SIDECARS_JSON=$(jq --arg k "$sname" --arg v "$spath" '. + {($k): $v}' <<<"$SIDECARS_JSON")
        fi
    done <<<"$REQ_SIDECARS"
fi

ELAPSED=$((SECONDS - START_SECONDS))

# --- Step 9: emit final result JSON ---
jq -nc \
    --arg s "$STATUS" \
    --arg o "" \
    --argjson t "$TOKENS_JSON" \
    --argjson sc "$SIDECARS_JSON" \
    --argjson el "$ELAPSED" \
    --argjson att "$ATTEMPT" \
    '{status:$s,output:$o,tokens:$t,sidecars:$sc,elapsed_seconds:$el,attempt_count:$att}'

case "$STATUS" in
    completed|verification_failed) exit 0 ;;
    engine_error|timeout) exit 1 ;;
    *) exit 1 ;;
esac
