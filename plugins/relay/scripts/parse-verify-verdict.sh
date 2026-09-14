#!/usr/bin/env bash
# Read one run-claude-command.sh / run-claude-prompt.sh reply (file argument or
# stdin) and print the /verify verdict and its mapped label.
#
# Output is exactly two lines:
#   VERIFY_VERDICT=PASS|FAIL|BLOCKED|SKIP|NONE
#   VERIFY_LABEL=clean|findings|no-answer
#
# Exit 0 when a verdict was found, exit 65 with NONE/no-answer when none was
# found. The verdict-to-label map lives here and nowhere else, so every
# caller reads the same map and SKIP can never be re-read as a pass by a
# caller that reasons about it freshly.
#
# Output on STDOUT is exactly two lines. Nothing else is ever printed there.
#
# On every NONE path one more line goes to STDERR:
#   VERIFY_REASON=no-output-fence   no usable fenced region was found
#   VERIFY_REASON=no-verdict-line   the region is there, but it holds no verdict line
#   VERIFY_REASON=bad-arguments     this script was called wrongly; nothing was read
# The caller needs that difference. A missing fence is temporary: a second child can
# answer. A reply that holds no verdict line is deterministic: the same command in the
# same repository answers in the same format, so a retry only spends a child. The
# reason stays off stdout, so the two-line contract and the exit codes do not change.
set -uo pipefail

usage() {
  echo "usage: parse-verify-verdict.sh [file]" >&2
}

if [ "$#" -gt 1 ]; then
  usage
  echo "VERIFY_VERDICT=NONE"
  echo "VERIFY_LABEL=no-answer"
  echo "VERIFY_REASON=bad-arguments" >&2
  exit 65
fi

# One POSIX awk program. It buffers every input line into an array and
# decides only in the END block, because the fenced region runs from the
# FIRST begin marker to the LAST end marker: a /verify run over this repo
# echoes both markers back in its own reply, so a reader that stops at the
# first end marker truncates the region and drops the real verdict. The
# helper that produced this input prints exactly one real begin marker first
# and one real end marker last, so first-begin / last-end is correct here.
AWK_PROGRAM='
{
  line[NR] = $0
  if ($0 == "POLISH_CMD_OUTPUT_BEGIN" && begin_idx == 0) begin_idx = NR
  if ($0 == "POLISH_CMD_OUTPUT_END") end_idx = NR
}
END {
  # No usable fenced region: either marker is missing, or the last end marker
  # is not after the first begin marker. The rc sentinel lives after the last
  # end marker, so text inside the region is never mistaken for an rc, and
  # text outside the region (including a trailing echoed verdict) is never
  # read as a verdict either.
  if (begin_idx == 0 || end_idx == 0 || end_idx <= begin_idx) {
    print "VERIFY_VERDICT=NONE"
    print "VERIFY_LABEL=no-answer"
    exit 65
  }

  verdict = ""
  for (i = begin_idx + 1; i < end_idx; i++) {
    l = line[i]

    # The report template holds the literal line
    # "**Verdict:** PASS | FAIL | BLOCKED | SKIP" — that line is in the
    # built-in /verify prompt, and it appears in this feature'"'"'s own files
    # (the command doc, the skill, these tests). A first-match search on
    # "Verdict:" reads the enum template as the verdict, so the label
    # pattern alone is not enough: it only anchors *where* a verdict word
    # would start.
    # The leading class allows the markdown a child may wrap the verdict
    # line in: bullet (-), heading (#), blockquote (>), emphasis (*_), and
    # any leading blank (space or tab). Narrowing it back drops a genuine
    # verdict rendered that way to NONE, which reads a real PASS as
    # no-answer and makes the loop burn every round. The one-token count
    # below still rejects the enum template even when it is bulleted.
    if (l ~ /^[-*_>#[:blank:]]*Verdict:?[*_: ]*(PASS|FAIL|BLOCKED|SKIP)([^A-Za-z]|$)/) {
      # Count whole-word verdict tokens on the line. Accept only a line
      # holding exactly one. This is a count, not an end-of-line anchor,
      # because a live run returned "Verdict: SKIP — no diff to verify" and
      # a real pass can read "**Verdict:** PASS — everything checks out".
      # An end-anchored pattern rejects both of those, which would turn a
      # genuine pass into NONE and make the loop burn every round without
      # ever reporting clean. A two-token line such as
      # "**Verdict:** PASS (not a FAIL)" is ambiguous and is rejected too,
      # which yields no-answer, never a pass — that bias is deliberate.
      tmp = l
      gsub(/[^A-Za-z]/, " ", tmp)
      n = split(tmp, w, " ")
      hits = 0
      tok = ""
      for (j = 1; j <= n; j++) {
        if (w[j] == "PASS" || w[j] == "FAIL" || w[j] == "BLOCKED" || w[j] == "SKIP") {
          hits++
          tok = w[j]
        }
      }
      # PASSED is one word and is not PASS, so it is never counted.
      if (hits == 1) verdict = tok
    }
  }

  # 66, not 65: a fenced region was found and it held no verdict line. That is
  # deterministic — the same command in the same repository answers in the same
  # format — while a missing fence is temporary. The wrapper below turns this code
  # back into 65 and names the difference on stderr, so the exit contract stays
  # two-valued.
  if (verdict == "") {
    print "VERIFY_VERDICT=NONE"
    print "VERIFY_LABEL=no-answer"
    exit 66
  }

  # The map: PASS -> clean, FAIL -> findings, BLOCKED -> no-answer,
  # SKIP -> no-answer. Kept in this one place so no caller can reason about
  # SKIP or BLOCKED freshly and read either as a pass.
  if (verdict == "PASS") label = "clean"
  else if (verdict == "FAIL") label = "findings"
  else label = "no-answer"

  print "VERIFY_VERDICT=" verdict
  print "VERIFY_LABEL=" label
  exit 0
}
'

# $# is 0 or 1 here (>1 is rejected above). With one arg awk reads the file; with
# none, "$@" expands to nothing and awk reads stdin. The awk program exits 66 for a
# fenced region that holds no verdict line. That code is internal: it is mapped back
# to 65 here, and the difference is named on stderr instead.
awk "$AWK_PROGRAM" "$@"
awk_rc=$?
case "$awk_rc" in
  65) echo "VERIFY_REASON=no-output-fence" >&2 ;;
  66) echo "VERIFY_REASON=no-verdict-line" >&2; awk_rc=65 ;;
esac
exit "$awk_rc"
