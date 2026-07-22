"""The four mandatory torque-ON preconditions, and the manifest gate that enforces them.

`PG-SAFE-001` without a PASS means this WP does not exist: `02a` §7 makes the gate's PASS
artifact hash a declared field of the startup manifest, and startup is *refused* when it is
absent. Torque-ON is admitted only when all four preconditions hold at once (`02a` §7,
acceptance ①②):

  1. `PG-SAFE-001` PASS, with its PASS artifact hash declared — else startup is refused.
  2. `PG-RID-001` PASS, and the Cat-2 hold send period under the RID-9 no-send margin
     (`12` NFR-SAF-007). A read failure is a torque-ON prohibition, not a warning
     (`16` M-2 / RID-9 read semantics).
  3. `WP-1-02` zero residual within tolerance — a torque-ON onto an unverified zero is a
     commanded jump.
  4. `WP-1-03` gateway bypass count zero — torque may flow only through the single
     enforcement point (`11` NFR-INF-008).

This module reads those facts; it never measures them. The real gate verdicts come from
`04` (PG-SAFE-001), `WP-0B-07` (PG-RID-001), `WP-1-02` (residual), and the `WP-1-03`
static bypass scan. Here they are the manifest a torque-ON session is handed, and this is
the one place that turns a missing or non-PASS precondition into a refusal to engage.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.torque_bringup.constants import (
    GATE_STATE_PASS,
    PG_RID_001,
    PG_SAFE_001,
)


class TorqueOnRefusedError(Exception):
    """Torque-ON was refused because a mandatory precondition is missing or not PASS.

    Raised instead of engaging, so a session that lost a gate, read a stale residual, or
    left a gateway bypass open fails loudly at the door rather than powering a 40 Nm
    brakeless arm on an unverified precondition.
    """


@dataclass(frozen=True)
class GatePass:
    """A gate verdict as declared to the torque-ON manifest.

    Attributes:
        gate_id: The `PG-*` id this verdict is for.
        status: The registry gate-state name (`PASS`, `FAIL_BLOCKING`, …).
        artifact_hash: The content hash of the PASS evidence artifact. Empty when the
            gate's PASS was never declared — the state acceptance ① refuses on.
    """

    gate_id: str
    status: str
    artifact_hash: str

    @property
    def is_pass_with_hash(self) -> bool:
        """Whether this verdict is PASS and carries a non-empty artifact hash.

        Returns:
            (bool) True only when both the status is PASS and a hash is declared.
        """
        return self.status == GATE_STATE_PASS and bool(self.artifact_hash)


@dataclass(frozen=True)
class ZeroResidualPrecondition:
    """The `WP-1-02` zero-residual verdict handed to a torque-ON session.

    Attributes:
        within_tolerance: Whether the 0xFE readback residual is within the per-joint
            tolerance (`02` FR-CON-065). A torque-ON onto an out-of-tolerance zero is a
            commanded jump and is refused.
    """

    within_tolerance: bool


@dataclass(frozen=True)
class GatewayBypassPrecondition:
    """The `WP-1-03` single-enforcement-point verdict handed to a torque-ON session.

    Attributes:
        bypass_count: Number of CAN-write paths found outside the action gateway by the
            `WP-1-03` static scan. Torque-ON is admitted only at zero (`11` NFR-INF-008).
    """

    bypass_count: int


@dataclass(frozen=True)
class TorqueOnManifest:
    """The startup manifest a guarded torque-ON session is admitted against.

    `02a` §7 makes the PG-SAFE-001 PASS hash a declared manifest field, so the manifest —
    not the code — is where the precondition either exists or does not. A session is
    handed one of these and refuses to engage unless every field clears.

    Attributes:
        safe_gate: The `PG-SAFE-001` verdict; its PASS hash must be present (①).
        rid_gate: The `PG-RID-001` verdict; PASS required (②, read failure = no torque-ON).
        zero_residual: The `WP-1-02` residual verdict; within tolerance required.
        gateway_bypass: The `WP-1-03` bypass verdict; zero bypass required.
        rid9_send_period_sec: The Cat-2 hold send period the loop will actually run at.
        rid9_no_send_margin_sec: The RID-9 no-send ceiling the send period must stay under
            (`12` NFR-SAF-007); sourced from the actuation spine, not fixed here.
    """

    safe_gate: GatePass
    rid_gate: GatePass
    zero_residual: ZeroResidualPrecondition
    gateway_bypass: GatewayBypassPrecondition
    rid9_send_period_sec: float
    rid9_no_send_margin_sec: float


def assert_torque_on_allowed(manifest: TorqueOnManifest) -> None:
    """Admit torque-ON only when all four mandatory preconditions hold (acceptance ①②).

    Args:
        manifest: The startup manifest declaring the four precondition verdicts.

    Raises:
        TorqueOnRefusedError: If PG-SAFE-001's PASS hash is undeclared or not PASS (①); if
            PG-RID-001 is not PASS or the Cat-2 send period is not under the RID-9 margin
            (②); if the WP-1-02 residual is out of tolerance; or if the WP-1-03 gateway
            bypass count is non-zero.
    """
    if manifest.safe_gate.gate_id != PG_SAFE_001:
        raise TorqueOnRefusedError(
            f"manifest safe_gate is {manifest.safe_gate.gate_id!r}, not {PG_SAFE_001}; "
            "this WP does not exist without a declared PG-SAFE-001 verdict (02a §7)"
        )
    if not manifest.safe_gate.artifact_hash:
        raise TorqueOnRefusedError(
            "manifest declares no PG-SAFE-001 PASS artifact hash; startup refused — "
            "without the gate's PASS hash this WP and every torque-ON descendant are "
            "blocked (02a §7 acceptance ①)"
        )
    if not manifest.safe_gate.is_pass_with_hash:
        raise TorqueOnRefusedError(
            f"PG-SAFE-001 is {manifest.safe_gate.status!r}, not {GATE_STATE_PASS}; a "
            "mismatch is FAIL_BLOCKING and refuses torque-ON (02a §8)"
        )

    if manifest.rid_gate.gate_id != PG_RID_001:
        raise TorqueOnRefusedError(
            f"manifest rid_gate is {manifest.rid_gate.gate_id!r}, not {PG_RID_001}"
        )
    if manifest.rid_gate.status != GATE_STATE_PASS:
        raise TorqueOnRefusedError(
            f"PG-RID-001 is {manifest.rid_gate.status!r}, not {GATE_STATE_PASS}; a RID read "
            "failure forbids torque-ON (16 M-2 / FR-MOT-003, acceptance ②)"
        )
    if not manifest.rid9_send_period_sec < manifest.rid9_no_send_margin_sec:
        raise TorqueOnRefusedError(
            f"Cat-2 hold send period {manifest.rid9_send_period_sec}s is not under the "
            f"RID-9 no-send margin {manifest.rid9_no_send_margin_sec}s; the hold could "
            "lapse the RID-9 timeout (12 NFR-SAF-007, acceptance ②)"
        )

    if not manifest.zero_residual.within_tolerance:
        raise TorqueOnRefusedError(
            "WP-1-02 zero residual is out of tolerance; torque-ON onto an unverified zero "
            "is a commanded jump (02 FR-CON-065)"
        )

    if manifest.gateway_bypass.bypass_count != 0:
        raise TorqueOnRefusedError(
            f"WP-1-03 gateway bypass count is {manifest.gateway_bypass.bypass_count}, not 0; "
            "torque may flow only through the single enforcement point (11 NFR-INF-008)"
        )
