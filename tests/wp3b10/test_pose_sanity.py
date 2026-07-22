"""RUNS-HERE ⑤ — a `det ≈ 0` or non-finite pose is discarded, not passed (`FR-TEL-038`).

A degenerate rotation (determinant within `1e-6` of zero) or any non-finite element is
a corrupt frame that, driven through IK, produces a wild command. The sanity filter
discards it and retains the last valid pose; through the gate the command never lurches
to the bad frame.
"""

from __future__ import annotations

import math

from backend.teleop.safety_gate.pose import IDENTITY_ROTATION, EEPose
from backend.teleop.safety_gate.sanity import PoseSanityFilter, is_pose_sane
from backend.teleop.safety_gate.states import TeleopLinkState
from tests.wp3b10.conftest import TICK_NS, make_gate, make_sample, pose_at

# A collapsed rotation: determinant exactly zero (two identical rows, rank-deficient).
_DEGENERATE_ROTATION = ((1.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
# A non-finite rotation: a NaN has leaked into an element.
_NAN_ROTATION = ((math.nan, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

_GOOD = EEPose(rotation=IDENTITY_ROTATION, translation=(0.1, 0.2, 0.3))


def test_proper_rotation_is_sane() -> None:
    """A proper rotation (det = +1) with finite elements passes."""
    assert is_pose_sane(_GOOD) is True


def test_degenerate_rotation_is_insane() -> None:
    """A determinant-zero rotation fails the sanity check (⑤)."""
    assert is_pose_sane(EEPose(rotation=_DEGENERATE_ROTATION, translation=(0.0, 0.0, 0.0))) is False


def test_non_finite_pose_is_insane() -> None:
    """A NaN in the rotation fails the sanity check (⑤)."""
    assert is_pose_sane(EEPose(rotation=_NAN_ROTATION, translation=(0.0, 0.0, 0.0))) is False
    inf_translation = EEPose(rotation=IDENTITY_ROTATION, translation=(math.inf, 0.0, 0.0))
    assert is_pose_sane(inf_translation) is False


def test_filter_retains_last_valid_pose_on_discard() -> None:
    """A discarded frame yields the retained last-valid pose, not the bad one (⑤)."""
    filt = PoseSanityFilter()
    accepted = filt.accept(_GOOD)
    assert accepted.accepted is True
    assert accepted.pose == _GOOD

    bad = filt.accept(EEPose(rotation=_DEGENERATE_ROTATION, translation=(9.0, 9.0, 9.0)))
    assert bad.accepted is False
    assert bad.pose == _GOOD  # previous valid pose retained
    assert filt.last_valid == _GOOD


def test_gate_does_not_lurch_to_a_degenerate_pose() -> None:
    """Through the gate, a degenerate follow target is discarded and the command held (⑤)."""
    seed = pose_at((0.0, 0.0, 0.0))
    gate = make_gate(seed_pose=seed)
    now = 1_000
    gate.step(now, seed, sample=make_sample(now))
    gate.notify_alignment_converged(now)

    # Follow one good target so there is a clear "last valid" that is not the seed.
    now += TICK_NS
    good_target = pose_at((0.01, 0.0, 0.0))
    gate.step(now, good_target, sample=make_sample(now))
    held = gate.command

    now += TICK_NS
    out = gate.step(
        now,
        EEPose(rotation=_DEGENERATE_ROTATION, translation=(9.0, 9.0, 9.0)),
        sample=make_sample(now),
    )
    assert out.pose_accepted is False
    assert out.state is TeleopLinkState.FOLLOWING
    # The command did not jump to the (9,9,9) degenerate target; it held the last valid.
    assert gate.command.translation == held.translation
