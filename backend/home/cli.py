"""Show the active home profile and its target posture before execution (WP-2D-07 ①).

`02b` WP-2D-07 ① requires the active home-profile name and its target posture to be shown
before a home return runs. This CLI is that surface offline: it prints the active home, its
target driver state and resulting EE poses, the adopted FR-MAN-047 decision, and the
deferred operator visual-confirm state. Given a start posture it also prints the pre-verify
verdict and whether the return may run — never executing anything (real send is
hardware-deferred behind the dry-run hard gate).
"""

from __future__ import annotations

import argparse
import json
import sys

from backend.cartesian_jog.frames import KinematicFrames
from backend.home.constants import ARM_JOINT_COUNT
from backend.home.decision import HOME_DECISION, deferred_visual_confirm
from backend.home.homereturn import HomeReturn
from backend.home.preverify import HomePreflight
from backend.home.profile import default_registry

START_WIDTH = ARM_JOINT_COUNT * 2


def main(argv: list[str] | None = None) -> int:
    """Print the active home, the decision, and (given a start) the pre-verify verdict.

    Args:
        argv: Command-line arguments; `sys.argv[1:]` when None.

    Returns:
        (int) 0 always — this is a read-only display, not a gate.
    """
    parser = argparse.ArgumentParser(prog="oa-home", description=__doc__)
    parser.add_argument(
        "--start",
        type=float,
        nargs=START_WIDTH,
        default=None,
        metavar="Q",
        help=f"{START_WIDTH} start joint angles (right joint1..7 then left joint1..7), radians",
    )
    args = parser.parse_args(argv)

    registry = default_registry()
    home = HomeReturn(registry, HomePreflight(), KinematicFrames())

    report = {
        "active_home": home.preview().as_record(),
        "registry": registry.as_record(),
        "decision": HOME_DECISION.as_record(),
        "deferred_visual_confirm": deferred_visual_confirm().as_record(),
    }
    if args.start is not None:
        report["plan"] = home.plan_return(args.start).as_record()

    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
