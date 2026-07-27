"""Acceptance ④, the part `resume()` exposes — a hold leaves no configuration residue.

``_hold`` promises to latch "without moving", and the committed pose does stay put. The
IK configuration does not: the solver integrates in place on every iteration before it
can conclude the target is inadmissible, so an abandoned solve leaves the adapter
wherever it got to. ``test_hold_no_skip`` continues after a hold with ``seed``, which
re-syncs and hides that; the operator path is ``resume()``, which does not.

The consequence is not a stale readout. The next accepted jog solves a small delta from
the drifted configuration and commits *that*, so a 5 mm request commands the whole
abandoned excursion — largest in exactly the near-singular case that caused the hold.

The assertion has to be on commanded motion, not on a pose readout: `current_pose`
derives from the committed state, which a hold never touches, so it reports the drift as
absent whether or not it is. A readout-based test here passes unconditionally.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from openarm_control.kinematics import IKParams

from backend.cartesian_jog import JogAxis, JogCommand, JogKind, build_cartesian_jog
from backend.cartesian_jog.constants import DEFAULT_TRANSLATION_STEP_M
from backend.cartesian_jog.frames import KinematicFrames

_FAST = {"dt": 0.1, "damping": 0.1, "posture_cost": 0.01, "lm_damping": 0.01}

# Far outside the reachable envelope, so the converge loop spends its whole cycle budget
# integrating toward it and then reports not-reached. A target the solver rejects on
# iteration zero would hold without integrating and prove nothing.
_UNREACHABLE_OFFSET_M = 2.0

# One differential cycle undershoots a step rather than overshooting it, so this ceiling
# is what carries the assertion. Un-synced, the same call moves ~92 mm.
_STEP_CEILING_M = DEFAULT_TRANSLATION_STEP_M * 2.0


def test_resume_then_jog_commits_the_requested_step_not_the_abandoned_excursion() -> None:
    """After resume(), one +Z step must move the TCP by one step, not by the drift."""
    jog = build_cartesian_jog(ik_params=IKParams(max_iters=5, **_FAST))
    jog.seed(KinematicFrames().home_solution())

    unreachable = jog.current_pose("right").copy()
    unreachable[2] += _UNREACHABLE_OFFSET_M
    held = jog.plan_pose("right", unreachable, commit=True)
    assert held.committed is False
    assert held.stopped is True

    jog.resume()
    before = jog.current_pose("right")[:3].copy()
    result = jog.step(JogCommand(side="right", kind=JogKind.TRANSLATION, axis=JogAxis.Z, sign=1))
    assert result.committed is True

    moved_m = float(np.linalg.norm(jog.current_pose("right")[:3] - before))
    assert moved_m <= _STEP_CEILING_M, (
        f"a {DEFAULT_TRANSLATION_STEP_M * 1000:.0f} mm jog moved {moved_m * 1000:.1f} mm"
    )
