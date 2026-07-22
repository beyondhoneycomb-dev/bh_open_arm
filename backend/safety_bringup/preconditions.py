"""The extended safety bring-up presupposes the WP-1-05 guarded torque-ON (`12` FR-SAF-069).

FR-SAF-069 makes this extension *precede* the gravity/friction (GMO) compensation delivery,
and the plan makes its input `WP-1-05 PASS`: the extension has no arm to protect, and no
motor torque against which a momentum-observer residual could exist, until the guarded
torque-ON of WP-1-05 has been admitted. So the residual-based collision detection this WP
configures is admitted only once WP-1-05's four torque-ON preconditions clear — this module
reuses that gate rather than restating it, so there is exactly one definition of "torque-ON
is allowed" (`11` NFR-INF-008 single-enforcement spirit).
"""

from __future__ import annotations

from backend.torque_bringup import (
    TorqueOnManifest,
    TorqueOnRefusedError,
    assert_torque_on_allowed,
)


class ExtendedSafetyPreconditionError(Exception):
    """Raised when the extended safety bring-up runs before the guarded torque-ON is admitted.

    Configuring residual-based collision detection presupposes torque-ON (`12` FR-SAF-069);
    there is no torque residual to observe on a torque-OFF arm, so the extension is refused
    until WP-1-05's preconditions clear.
    """


def assert_extended_safety_preconditions(manifest: TorqueOnManifest) -> None:
    """Admit the extended safety bring-up only after the WP-1-05 torque-ON is allowed.

    Args:
        manifest: The WP-1-05 startup manifest declaring the four torque-ON preconditions.

    Raises:
        ExtendedSafetyPreconditionError: If the guarded torque-ON is not admissible — the
            extension must precede GMO delivery but follow torque-ON (`12` FR-SAF-069).
    """
    try:
        assert_torque_on_allowed(manifest)
    except TorqueOnRefusedError as refusal:
        raise ExtendedSafetyPreconditionError(
            "extended safety bring-up presupposes the WP-1-05 guarded torque-ON; it must "
            f"precede GMO delivery but follow torque-ON (12 FR-SAF-069): {refusal}"
        ) from refusal
