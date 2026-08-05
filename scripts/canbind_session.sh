#!/usr/bin/env bash
# Which arm is on which CAN channel (05 §3-2a). Exit code is the verdict, like scripts/gates.sh.
#
# `cd` first and invoke with `-m`: the repository root has to be sys.path[0] for `backend`, `ops`,
# `packages` and `contracts` to import, and running the file by path would put scripts/ there.
#
#   ./scripts/canbind_session.sh --arm left --run --i-am-holding-the-arm
#                                             schedule one round for the left arm. Prints the
#                                             wall-clock timetable and returns at once.
#   ./scripts/canbind_session.sh --status     what the detached round recorded
#   ./scripts/canbind_session.sh --write-binding
#                                             persist both resolved rounds as the channel binding
#   ./scripts/canbind_session.sh --arm left   preconditions only, opens nothing
#
# Both arms need their own round: the record the torque session reads carries two roles, and each
# one is written only from a round in which the operator moved that arm.
#
# Exit codes, which is what a caller should read rather than the text:
#   0  the round resolved (--status: both arms resolved onto different channels)
#   1  refused, or a round the judge would not resolve
#   2  --status only: a round is still running, or an arm has no round yet
#   3  --status only: this capture tree holds no round at all
#
# The measurement runs detached on purpose. A shell shows a command's output only once the command
# has ended, so anything printed *during* a run reaches the operator too late to act on — which is
# how three E-Stop measurements were lost on this bench. The timetable is absolute wall-clock time
# for the same reason.
#
# Opening a channel energizes both arms: the bus handshake sends 0xFC to every fitted motor before
# anything else happens. Take hold of the arm first; the acknowledgement flag is refused, not
# prompted, because the process that would read a prompt is detached with its stdin closed.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
[ -d .venv ] && source .venv/bin/activate

exec python3 -m scripts.canbind_session "$@"
