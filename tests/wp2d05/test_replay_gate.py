"""CG-2D-05b (acceptance ②) — a zero mismatch on load blocks replay with a warning.

The gate permits a replay only when the robot's current zero identity is the one a
point was taught against. A re-zero, a method change, an un-zeroed arm, or a cross-arm
reference each block, each with an operator-facing reason.
"""

from __future__ import annotations

from backend.calibration import ZeroMethod
from backend.teaching import (
    ReplayDecision,
    TeachingPointStore,
    ZeroIdentity,
    evaluate_replay,
)

from . import (
    LEFT,
    RIGHT,
    ZEROED_AT_A,
    ZEROED_AT_B,
    identity,
    make_calibration,
    make_point,
)


def test_same_identity_allows_replay() -> None:
    point = make_point("p1", zero=identity(RIGHT, zeroed_at=ZEROED_AT_A))
    verdict = evaluate_replay(point, identity(RIGHT, zeroed_at=ZEROED_AT_A))
    assert verdict.decision is ReplayDecision.ALLOWED
    assert verdict.allowed
    assert verdict.reason == ""


def test_rezero_since_teaching_blocks_with_warning() -> None:
    point = make_point("p1", zero=identity(RIGHT, zeroed_at=ZEROED_AT_A))
    verdict = evaluate_replay(point, identity(RIGHT, zeroed_at=ZEROED_AT_B))
    assert verdict.decision is ReplayDecision.BLOCKED
    assert not verdict.allowed
    assert "re-zeroed" in verdict.reason
    assert "different pose" in verdict.reason


def test_method_change_blocks_with_warning() -> None:
    point = make_point("p1", zero=identity(RIGHT, method=ZeroMethod.LEROBOT_HANGING))
    verdict = evaluate_replay(
        point, identity(RIGHT, method=ZeroMethod.HARDSTOP_BUMP, zeroed_at=ZEROED_AT_A)
    )
    assert verdict.decision is ReplayDecision.BLOCKED
    assert "zero method changed" in verdict.reason


def test_unzeroed_robot_blocks_every_point() -> None:
    point = make_point("p1")
    verdict = evaluate_replay(point, identity(RIGHT, zeroed_at=None))
    assert verdict.decision is ReplayDecision.BLOCKED
    assert "no zero record" in verdict.reason


def test_cross_arm_reference_blocks() -> None:
    point = make_point("p1", side=RIGHT)
    verdict = evaluate_replay(point, identity(LEFT, zeroed_at=ZEROED_AT_A))
    assert verdict.decision is ReplayDecision.BLOCKED
    assert "arm" in verdict.reason


def test_store_load_time_verdicts_split_allowed_and_blocked() -> None:
    store = TeachingPointStore(RIGHT)
    store.add(make_point("stale", zero=identity(RIGHT, zeroed_at=ZEROED_AT_A)))
    store.add(make_point("fresh", zero=identity(RIGHT, zeroed_at=ZEROED_AT_B)))

    current = identity(RIGHT, zeroed_at=ZEROED_AT_B)
    verdicts = store.replay_verdicts(current)
    assert [v.point_name for v in verdicts] == ["stale", "fresh"]
    assert verdicts[0].decision is ReplayDecision.BLOCKED
    assert verdicts[1].decision is ReplayDecision.ALLOWED

    assert [p.name for p in store.replayable(current)] == ["fresh"]
    assert [p.name for p, _ in store.blocked(current)] == ["stale"]


def test_gate_reads_identity_from_the_calibration_record() -> None:
    # The current identity is derived from the frozen zero record, not a hand-built
    # copy, so the gate and the persisted zero cannot disagree.
    calibration = make_calibration(RIGHT, last_zero_at=ZEROED_AT_A)
    point = make_point("p1", zero=identity(RIGHT, zeroed_at=ZEROED_AT_A))
    allowed = evaluate_replay(point, ZeroIdentity.from_calibration(calibration))
    assert allowed.decision is ReplayDecision.ALLOWED

    rezeroed = make_calibration(RIGHT, last_zero_at=ZEROED_AT_B)
    blocked = evaluate_replay(point, ZeroIdentity.from_calibration(rezeroed))
    assert blocked.decision is ReplayDecision.BLOCKED
