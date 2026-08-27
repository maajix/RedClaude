#!/usr/bin/env bash
# Run one Program until it stops, and keep the terminal record of why.
#
# `rk run` works one Task per invocation, so a hunt is this loop. What the
# database already records is every failed run and its reason; what it cannot
# record is a traceback out of `rk` itself, which is why every lap is tee'd to
# a log an operator can go back to.
#
#   tools/hunt-loop.sh program.toml [hunt.log]
#
# Reads $DATABASE_URL, $STATE_URL and $RK_ARTIFACT_ROOT like `rk run` does.
# Stops when a pass attempts nothing -- an empty queue, or a queue holding only
# work parked on a question -- and after three consecutive faults so a broken
# harness cannot spin through the token budget.

set -u -o pipefail

CONFIG="${1:?usage: hunt-loop.sh <config.toml> [logfile]}"
LOG="${2:-hunt.log}"
MAX_CONSECUTIVE_FAULTS=3

# The two stop words of a pass that attempted no Task. Read out of the pass's
# own report and not out of its exit code: neither is a fault, so `rk run`
# exits 0 for both, and a loop watching only the code spins for as long as it
# is left running. Ticket 206 is what makes `awaiting_decision` a reliable one
# to stop on -- before it, a pass that had worked a Task said it too, whenever
# any question anywhere in the Program was open.
IDLE='"stop_reason": "nothing_to_execute"|"stop_reason": "awaiting_decision"'

lap=0
faults=0

while :; do
    lap=$((lap + 1))
    printf '=== lap %d %s ===\n' "$lap" "$(date -Is)" | tee -a "$LOG"

    # Retire the questions whose deadline passed, before the pass that would
    # refuse over them. `check_control_surface` rule 3 reports a past-deadline
    # question as `decision_past_deadline_unswept`, the standing check turns that
    # into `integrity_failed`, and every `rk run` refuses while it holds -- so a
    # campaign nobody swept stops dead four hours after its last question, which
    # is what happened to `rk2here` at 00:49 on 2026-08-27. The sweeper is a
    # companion the harness has always assumed and no driver ever started.
    # Inline rather than a daemon: it is one statement, it wants no second
    # process to reap, and a sweep is only ever needed where a pass is about to
    # be made. Its exit code is not the lap's -- a sweeper that cannot reach the
    # database is a fault `rk run` reports for itself a line later.
    rk decision sweep 2>&1 | tee -a "$LOG" || true

    pass_log="$(mktemp)"
    rk run --config "$CONFIG" 2>&1 | tee -a "$LOG" "$pass_log"
    rc="${PIPESTATUS[0]}"
    printf 'exit %d\n' "$rc" | tee -a "$LOG"
    idle="$(grep -cE "$IDLE" "$pass_log" || true)"
    rm -f "$pass_log"

    if [ "$idle" -gt 0 ]; then
        printf 'the pass attempted nothing; `rk questions` lists what is open\n' \
            | tee -a "$LOG"
        break
    fi

    if [ "$rc" -eq 0 ]; then
        faults=0
        continue
    fi

    faults=$((faults + 1))
    if [ "$faults" -ge "$MAX_CONSECUTIVE_FAULTS" ]; then
        printf 'stopped after %d consecutive faults\n' "$faults" | tee -a "$LOG"
        break
    fi
done

printf '=== faults %s ===\n' "$(date -Is)" | tee -a "$LOG"
rk ui read --config "$CONFIG" --panel faults 2>&1 | tee -a "$LOG"
