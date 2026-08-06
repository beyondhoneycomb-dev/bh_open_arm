#!/usr/bin/env bash
# Does every fitted motor keep answering, over time and across postures — with torque OFF.
# Exit code is the verdict, like scripts/gates.sh.
#
# `cd` first and invoke with `-m`: the repository root has to be sys.path[0] for `backend`, `ops`
# and `contracts` to import, and running the file by path would put scripts/ there.
#
#   ./scripts/can_node_watch.sh --run          schedule a 120 s watch. Prints the wall-clock
#                                              timetable and returns at once.
#   ./scripts/can_node_watch.sh --run --seconds 300
#                                              longer window, for a harness you have to walk the
#                                              arm around to provoke.
#   ./scripts/can_node_watch.sh --status       what the detached watch recorded
#   ./scripts/can_node_watch.sh                preconditions only, opens nothing
#
# Exit codes, which is what a caller should read rather than the text:
#   0  every fitted motor answered every attempt, with no fault nibble
#   1  refused, or a node was silent, intermittent or faulted — do not put torque on
#   2  --status only: the watch is still running
#   3  --status only: this capture tree holds no watch at all
#
# This is the check that must pass BEFORE a torque-ON session, and it is the only reader here that
# needs no hand on the arm: it sends 0xFD (Disable) and nothing else, so no motor is energized by
# it. The motors answer that frame with position, temperature and a state nibble, which is what
# makes a torque-free read possible at all.
#
# Run it while moving both arms by hand. Harness contact faults depend on bending, so a watch held
# at one posture is a watch that cannot find them.
#
# The measurement runs detached on purpose. A terminal shows a command's output only once the
# command has ended, so anything printed *during* a run reaches the operator too late to act on —
# which is how three E-Stop measurements were lost on this bench. The timetable is absolute
# wall-clock time for the same reason.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
[ -d .venv ] && source .venv/bin/activate

exec python3 -m scripts.can_node_watch "$@"
