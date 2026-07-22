"""Shared fixtures for the WP-1-05 guarded torque-ON tests.

A recording bus that captures the order of `read_present_pose`/`engage_hold` calls (what
the ordering acceptance ③ reads), a present pose, and a manifest with all four preconditions
cleared so each test perturbs exactly one.
"""

from __future__ import annotations

import pytest

from backend.actuation import MIT_BATCH_WIDTH
from backend.actuation.config import RID9_NO_SEND_MARGIN_SEC, TICK_INTERVAL_SEC
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


class RecordingEngageBus:
    """A `TorqueEngageBus` that records the order and payloads of its calls.

    Attributes:
        calls: The method names in call order — used to assert present-pose read precedes
            0xFC engage (acceptance ③).
        engaged_batch: The MIT frame passed to the last `engage_hold`, or None.
    """

    def __init__(self, present: tuple[Rad, ...]) -> None:
        """Bind the bus to the present pose it will report.

        Args:
            present: The joint angles `read_present_pose` returns.
        """
        self._present = present
        self.calls: list[str] = []
        self.engaged_batch: tuple[ExecutedMitCommand, ...] | None = None

    def read_present_pose(self) -> tuple[Rad, ...]:
        """Record and return the present pose."""
        self.calls.append("read_present_pose")
        return self._present

    def engage_hold(self, hold_batch: tuple[ExecutedMitCommand, ...]) -> None:
        """Record the 0xFC engage and the frame it carried."""
        self.calls.append("engage_hold")
        self.engaged_batch = hold_batch


@pytest.fixture
def present_pose() -> tuple[Rad, ...]:
    """A non-trivial present pose, one distinct angle per joint."""
    return tuple(Rad(0.05 * index) for index in range(MIT_BATCH_WIDTH))


@pytest.fixture
def recording_bus(present_pose: tuple[Rad, ...]) -> RecordingEngageBus:
    """A recording engage bus reporting the present pose."""
    return RecordingEngageBus(present_pose)


@pytest.fixture
def passing_manifest() -> TorqueOnManifest:
    """A startup manifest with all four torque-ON preconditions cleared."""
    return TorqueOnManifest(
        safe_gate=GatePass(gate_id=PG_SAFE_001, status="PASS", artifact_hash=SAFE_HASH),
        rid_gate=GatePass(gate_id=PG_RID_001, status="PASS", artifact_hash=RID_HASH),
        zero_residual=ZeroResidualPrecondition(within_tolerance=True),
        gateway_bypass=GatewayBypassPrecondition(bypass_count=0),
        rid9_send_period_sec=TICK_INTERVAL_SEC,
        rid9_no_send_margin_sec=RID9_NO_SEND_MARGIN_SEC,
    )
