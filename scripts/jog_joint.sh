#!/usr/bin/env bash
# Move ONE motor a relative angle, slowly, and bring it back. This energizes the arm.
#
# `cd` first and invoke with `-m`: the repository root has to be sys.path[0] for `backend`, `ops`
# and `contracts` to import, and running the file by path would put scripts/ there.
#
#   ./scripts/jog_joint.sh --arm left --id 0x07 --delta 5
#                                     wrist J7, 5 degrees and back. The smallest real move.
#   ./scripts/jog_joint.sh --arm left --id 0x07 --delta 5 --kp 30 --seconds 4
#                                     stiffer and slower — the position error column shrinks.
#   ./scripts/jog_joint.sh --arm left --id 0x07 --delta 5 --no-return
#                                     leave it where it arrived.
#
# Exit codes, which is what a caller should read rather than the text:
#   0  the joint moved and came back
#   1  refused before anything opened, or the motor never answered
#   2  usage error — nothing was opened and nothing ran
#   3  the move started and was aborted; the reason is the finding, the motor is disabled
#
# Run ./scripts/can_node_watch.sh --run first. That one is torque-free and answers whether every
# node keeps answering; this one puts force on the joint and cannot find a flaky harness, because
# a node that drops out while energized cannot be handled at all — a stop removes force, and a
# brakeless arm holding itself up falls when the force goes.
#
# An abort disables, so an abort on a joint carrying weight is a fall. Start on a wrist joint, keep
# a hand near the arm, and watch the joint rather than the terminal.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
[ -d .venv ] && source .venv/bin/activate

exec python3 -m scripts.jog_joint "$@"
