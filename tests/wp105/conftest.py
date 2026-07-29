"""Shared fixtures for the WP-1-05 guarded torque-ON tests.

A recording bus that captures the order, the addressed motor ids and the payloads of its
calls (what the ordering and fitted-motor acceptances read), the present pose of a fitted
arm, and the two authorizations with everything cleared so each test perturbs exactly one.

The preflight report is assembled from `CheckResult` values rather than run through
`JogSessionPreflight`: the engage's contract is with the report, and gathering the evidence
that produces one belongs to WP-2A-09's own tree.
"""

from __future__ import annotations

import pytest

from backend.actuation.config import RID9_NO_SEND_MARGIN_SEC, TICK_INTERVAL_SEC
from backend.endeffector import EndEffectorProfile, gripper_build, spatula_build
from backend.preflight import CheckResult, PreflightCheck, PreflightReport
from backend.torque_bringup import (
    GatePass,
    GatewayBypassPrecondition,
    TorqueOnManifest,
    ZeroResidualPrecondition,
)
from backend.torque_bringup.constants import PG_RID_001, PG_SAFE_001
from contracts.action import ExecutedMitCommand
from contracts.units import Rad

SAFE_HASH = "sha256:pg-safe-001-pass"
RID_HASH = "sha256:pg-rid-001-pass"

# Angle step between adjacent joints in the synthetic present pose. Any non-zero value
# works; a distinct angle per joint is what makes a mis-ordered or truncated frame visible.
POSE_STEP_RAD = 0.05


class RecordingEngageBus:
    """A `TorqueEngageBus` that records the order, ids and payloads of its calls.

    Attributes:
        calls: The method names in call order — used to assert the present-pose read
            precedes 0xFC (acceptance ③).
        addressed_ids: The motor ids passed to each call, in call order.
        engaged_batch: The MIT frame passed to the last `enable_torque`, or None.
    """

    def __init__(self, present: tuple[Rad, ...]) -> None:
        """Bind the bus to the present pose it will report.

        Args:
            present: The joint angles `read_present_pose` returns, one per fitted motor.
        """
        self._present = present
        self.calls: list[str] = []
        self.addressed_ids: list[tuple[int, ...]] = []
        self.engaged_batch: tuple[ExecutedMitCommand, ...] | None = None

    def read_present_pose(self, send_ids: tuple[int, ...]) -> tuple[Rad, ...]:
        """Record the read and return the present pose."""
        self.calls.append("read_present_pose")
        self.addressed_ids.append(send_ids)
        return self._present

    def enable_torque(
        self, send_ids: tuple[int, ...], hold_batch: tuple[ExecutedMitCommand, ...]
    ) -> None:
        """Record the 0xFC engage, the ids it addressed and the frame it carried."""
        self.calls.append("enable_torque")
        self.addressed_ids.append(send_ids)
        self.engaged_batch = hold_batch

    def drop_torque(self, send_ids: tuple[int, ...]) -> None:
        """Record the 0xFD drop and the ids it addressed."""
        self.calls.append("drop_torque")
        self.addressed_ids.append(send_ids)


def pose_for(profile: EndEffectorProfile) -> tuple[Rad, ...]:
    """Build a distinct-per-joint present pose one angle wide per fitted motor.

    Args:
        profile: The fitted tool whose motor count sets the width.

    Returns:
        (tuple[Rad, ...]) The synthetic present pose.
    """
    return tuple(Rad(POSE_STEP_RAD * index) for index in range(profile.motor_count))


def passing_check_results() -> tuple[CheckResult, ...]:
    """One passed result per preflight precondition.

    Returns:
        (tuple[CheckResult, ...]) A complete, all-passed result set.
    """
    return tuple(
        CheckResult(check=check, passed=True, detail=f"{check.value} satisfied")
        for check in PreflightCheck
    )


def report_with_failure(failed: PreflightCheck, detail: str) -> PreflightReport:
    """Build a preflight report in which exactly one named precondition failed.

    Args:
        failed: The precondition to mark blocked.
        detail: The evidence the block must carry into the refusal message.

    Returns:
        (PreflightReport) A report whose `may_enable_torque` is false for one reason.
    """
    results = tuple(
        CheckResult(check=result.check, passed=False, detail=detail)
        if result.check is failed
        else result
        for result in passing_check_results()
    )
    return PreflightReport(results=results)


@pytest.fixture
def fitted_profile() -> EndEffectorProfile:
    """The build fitted to this bench: a rigid spatula, no motor on 0x08."""
    return spatula_build()


@pytest.fixture
def gripper_profile() -> EndEffectorProfile:
    """The pinch-gripper build, for showing the addressed set follows the tool."""
    return gripper_build()


@pytest.fixture
def present_pose(fitted_profile: EndEffectorProfile) -> tuple[Rad, ...]:
    """A non-trivial present pose, one distinct angle per fitted motor."""
    return pose_for(fitted_profile)


@pytest.fixture
def recording_bus(present_pose: tuple[Rad, ...]) -> RecordingEngageBus:
    """A recording engage bus reporting the fitted arm's present pose."""
    return RecordingEngageBus(present_pose)


@pytest.fixture
def passing_preflight() -> PreflightReport:
    """A preflight report with all five torque-ON preconditions passed."""
    return PreflightReport(results=passing_check_results())


@pytest.fixture
def passing_manifest() -> TorqueOnManifest:
    """A startup manifest with all four torque-ON gate preconditions cleared."""
    return TorqueOnManifest(
        safe_gate=GatePass(gate_id=PG_SAFE_001, status="PASS", artifact_hash=SAFE_HASH),
        rid_gate=GatePass(gate_id=PG_RID_001, status="PASS", artifact_hash=RID_HASH),
        zero_residual=ZeroResidualPrecondition(within_tolerance=True),
        gateway_bypass=GatewayBypassPrecondition(bypass_count=0),
        rid9_send_period_sec=TICK_INTERVAL_SEC,
        rid9_no_send_margin_sec=RID9_NO_SEND_MARGIN_SEC,
    )
