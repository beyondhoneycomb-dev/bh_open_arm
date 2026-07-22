"""The extended safety bring-up presupposes the WP-1-05 guarded torque-ON (`12` FR-SAF-069).

Residual-based collision detection has no torque residual to observe on a torque-OFF arm, so
the extension reuses WP-1-05's four-precondition torque-ON gate rather than restating it.
"""

from __future__ import annotations

import pytest

from backend.safety_bringup import (
    ExtendedSafetyPreconditionError,
    assert_extended_safety_preconditions,
)
from backend.torque_bringup import (
    GatePass,
    GatewayBypassPrecondition,
    TorqueOnManifest,
    ZeroResidualPrecondition,
)
from backend.torque_bringup.constants import PG_RID_001, PG_SAFE_001


def _passing_manifest() -> TorqueOnManifest:
    return TorqueOnManifest(
        safe_gate=GatePass(gate_id=PG_SAFE_001, status="PASS", artifact_hash="sha256:safe"),
        rid_gate=GatePass(gate_id=PG_RID_001, status="PASS", artifact_hash="sha256:rid"),
        zero_residual=ZeroResidualPrecondition(within_tolerance=True),
        gateway_bypass=GatewayBypassPrecondition(bypass_count=0),
        rid9_send_period_sec=0.001,
        rid9_no_send_margin_sec=0.05,
    )


def test_extension_admitted_when_torque_on_is_allowed() -> None:
    # FR-SAF-069: with the four torque-ON preconditions cleared, the extension is admitted.
    assert_extended_safety_preconditions(_passing_manifest())


def test_extension_refused_when_torque_on_is_not_allowed() -> None:
    # FR-SAF-069: a missing PG-SAFE-001 hash blocks torque-ON, so it blocks the extension too.
    import dataclasses

    manifest = dataclasses.replace(
        _passing_manifest(),
        safe_gate=GatePass(gate_id=PG_SAFE_001, status="PASS", artifact_hash=""),
    )
    with pytest.raises(ExtendedSafetyPreconditionError, match="guarded torque-ON"):
        assert_extended_safety_preconditions(manifest)
