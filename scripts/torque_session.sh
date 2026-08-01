#!/usr/bin/env bash
# The torque-ON stage as one operator session. Exit code is the verdict, like scripts/gates.sh.
#
# `cd` first and invoke with `-m`: the repository root has to be sys.path[0] for `backend`,
# `ops`, `packages` and `contracts` to import, and running the file by path would put
# scripts/ there instead.
#
#   ./scripts/torque_session.sh                 preconditions only, immediate verdict
#   ./scripts/torque_session.sh --plan          what every step asks of you, runs nothing
#   ./scripts/torque_session.sh --run           schedule the session; prints the wall-clock
#                                               timetable and returns at once
#   ./scripts/torque_session.sh --run --step 3  schedule one step; earlier captures survive
#   ./scripts/torque_session.sh --status        what the detached worker has recorded
#   ./scripts/torque_session.sh --check         self-check: the capture layouts and the refusals
#
# Exit codes, which is what a caller should read rather than the text:
#   0  everything asked for passed
#   1  something refused
#   2  --status only: the session is still running, steps remain unreached
#   3  --status only: this capture tree holds no session. "Not finished" and "never started"
#      are separate codes because they want opposite responses — wait, or schedule.
#
# The measurement runs detached on purpose. A shell shows a command's output only once the
# command has ended, so anything printed *during* a run reaches the operator too late to act on
# — which is how three E-Stop measurements were lost on this bench. The timetable is absolute
# wall-clock time for the same reason.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
[ -d .venv ] && source .venv/bin/activate

exec python3 -m scripts.torque_session "$@"
