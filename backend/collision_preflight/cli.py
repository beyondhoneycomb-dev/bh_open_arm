"""Emit the WP-2C-08 offline acceptance evidence bundle as JSON.

This is the entry point that exercises the whole preflight on the committed asset and prints
what runs on this host: a clean trajectory passing, a collision trajectory reporting its
first violating waypoint (①), the waypoint-density assessment (②), the self-collision
activation proof (③), the link7 URDF+MJCF verification (④), the margin policy (⑤), and the
per-target latency bench whose target numbers are deferred (`03` §5.11).

It writes nothing into any vendor tree: the link7 URDF descriptor is materialized into a
temporary directory through the reused `WP-1-06` injector, and the committed MJCF is only read.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from backend.collision_preflight.bench import build_preflight_bench_artifact
from backend.collision_preflight.constants import (
    KNOWN_ARM_ARM_COLLISION_LEFT,
    KNOWN_ARM_ARM_COLLISION_RIGHT,
)
from backend.collision_preflight.link7 import materialize_link7_urdf, verify_link7_both
from backend.collision_preflight.model import PreflightModel
from backend.collision_preflight.preflight import run_preflight
from backend.collision_preflight.selfcollision import assert_self_collision_active
from backend.safety_bringup.collision import (
    MarginConfirmationRequiredError,
    resolve_collision_margin,
)
from backend.safety_bringup.constants import COLLISION_MARGIN_DEFAULT_M

# Steps to interpolate neutral -> collision. Chosen well above the density floor so the
# collision trajectory is dense enough to be walked, not refused for sparsity (② vs ①).
_COLLISION_TRAJECTORY_STEPS = 80


def _interpolate_to_known_collision(
    model: PreflightModel, steps: int
) -> tuple[tuple[float, ...], ...]:
    """Build a dense trajectory from neutral toward the known arm-arm collision pose.

    Args:
        model: The loaded preflight model.
        steps: How many waypoints to generate.

    Returns:
        (tuple[tuple[float, ...], ...]) The trajectory, each waypoint a full configuration.
    """
    waypoints: list[tuple[float, ...]] = []
    for step in range(steps):
        fraction = step / (steps - 1)
        left = tuple(fraction * angle for angle in KNOWN_ARM_ARM_COLLISION_LEFT)
        right = tuple(fraction * angle for angle in KNOWN_ARM_ARM_COLLISION_RIGHT)
        waypoints.append(model.qpos_from_arms(left, right))
    return tuple(waypoints)


def _clean_trajectory(model: PreflightModel) -> tuple[tuple[float, ...], ...]:
    """Build a small collision-free trajectory near the neutral pose.

    Args:
        model: The loaded preflight model.

    Returns:
        (tuple[tuple[float, ...], ...]) A short, dense, collision-free trajectory.
    """
    waypoints: list[tuple[float, ...]] = []
    for step in range(6):
        angle = 0.01 * step
        left = (angle, 0.0, 0.0, angle, 0.0, 0.0, 0.0)
        right = (-angle, 0.0, 0.0, angle, 0.0, 0.0, 0.0)
        waypoints.append(model.qpos_from_arms(left, right))
    return tuple(waypoints)


def _margin_policy_evidence() -> dict[str, Any]:
    """Exercise the reused `WP-1-06` margin policy for acceptance ⑤.

    Returns:
        (dict[str, Any]) The default, the zero-without-confirmation refusal, and the
        confirmed-zero warning.
    """
    default = resolve_collision_margin(None, False)
    try:
        resolve_collision_margin(0.0, False)
        zero_refused = False
    except MarginConfirmationRequiredError:
        zero_refused = True
    confirmed = resolve_collision_margin(0.0, True)
    return {
        "default_margin_m": default.margin_m,
        "default_at_least_0_02": default.margin_m >= COLLISION_MARGIN_DEFAULT_M,
        "zero_without_confirmation_refused": zero_refused,
        "zero_with_confirmation_warning": confirmed.warning,
    }


def build_evidence() -> dict[str, Any]:
    """Assemble the full WP-2C-08 offline acceptance evidence bundle.

    Returns:
        (dict[str, Any]) One block per acceptance item, all run on the committed asset.
    """
    margin = resolve_collision_margin(None, False)
    model = PreflightModel(margin.margin_m)

    clean = run_preflight(_clean_trajectory(model))
    collision = run_preflight(_interpolate_to_known_collision(model, _COLLISION_TRAJECTORY_STEPS))

    with tempfile.TemporaryDirectory() as tmp:
        urdf = materialize_link7_urdf(Path(tmp) / "link7_collision.urdf")
        link7 = verify_link7_both(urdf)

    bench = build_preflight_bench_artifact(_clean_trajectory(model), margin_m=margin.margin_m)

    return {
        "wp_id": "WP-2C-08",
        "acceptance_1_first_violation": {
            "clean_ok": clean.ok,
            "collision_result": collision.as_record(),
        },
        "acceptance_2_density": collision.density.as_record(),
        "acceptance_3_self_collision": assert_self_collision_active(model).as_record(),
        "acceptance_4_link7": link7.as_record(),
        "acceptance_5_margin": _margin_policy_evidence(),
        "bench": bench,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Print the acceptance evidence bundle as JSON.

    Args:
        argv: Command-line arguments; None reads `sys.argv`.

    Returns:
        (int) Process exit code, always 0 — this command reports, it does not judge.
    """
    parser = argparse.ArgumentParser(description="Emit the WP-2C-08 collision-preflight evidence.")
    parser.add_argument("--indent", type=int, default=2, help="JSON indent (0 for compact)")
    args = parser.parse_args(argv)
    indent = args.indent if args.indent > 0 else None
    print(json.dumps(build_evidence(), ensure_ascii=False, indent=indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
