"""The PG-FRIC-001 gate that decides which Freedrive paths are offered (spec 04 §2.8).

There are three Freedrive paths (spec 04 §2.8):

* (A) pure back-drive — motors released; the arm sags and drops a payload.
* (B) low-stiffness impedance — ``kp=0``, small ``kd``, held target; no gravity term, so the
  arm still sags.
* (C) gravity-compensated hand-guiding — the ``tau_grav + tau_fric`` feed-forward path this WP
  builds. It is the goal, and it depends on a real friction model.

Path (C) is admissible only when PG-FRIC-001 has passed, because its friction term is the
identified model that gate produces. Until then Freedrive is (A)/(B) only, and FR-MAN-035
requires the "gravity uncompensated - arm sags" banner. This module reads the honest friction
status and returns exactly that offer; it is the runtime form of "path (C) cannot start when
PG-FRIC-001 is not passed" (acceptance I). The status maps fail-closed: only the explicit
hardware-pass marker opens (C); a deferred, provisional or unknown status keeps it blocked.
"""

from __future__ import annotations

from enum import Enum

from backend.freedrive.constants import FRICTION_PASSED_STATUS, GRAVITY_UNCOMPENSATED_BANNER


class FreedrivePath(Enum):
    """The three Freedrive paths (spec 04 §2.8). Only ``GRAVITY_COMPENSATED`` needs PG-FRIC-001."""

    PURE_BACKDRIVE = "A"
    LOW_STIFFNESS_IMPEDANCE = "B"
    GRAVITY_COMPENSATED = "C"


class FrictionGateStatus(Enum):
    """Whether the friction model the gravity-comp path needs has passed PG-FRIC-001."""

    PASSED = "passed"
    NOT_PASSED = "not_passed"


# The paths offered when the gravity-comp path is unavailable, and when it is. (A) and (B) are
# always available (LeRobot provides both); (C) is appended only on a friction pass.
_PATHS_WITHOUT_C = (FreedrivePath.PURE_BACKDRIVE, FreedrivePath.LOW_STIFFNESS_IMPEDANCE)
_PATHS_WITH_C = (*_PATHS_WITHOUT_C, FreedrivePath.GRAVITY_COMPENSATED)


def friction_gate_status(document_status: str) -> FrictionGateStatus:
    """Map a friction document status string to the Freedrive gate verdict, fail-closed.

    Only the explicit hardware-pass marker opens path (C). Every other value — the synthetic-log
    ``NOT_PASSED_DEFERRED_TO_HARDWARE``, a provisional stamp, or an unrecognised string — is read
    as not passed, so an ambiguous status never silently enables gravity compensation.

    Args:
        document_status: The friction model's status string, as the friction package stamps it.

    Returns:
        (FrictionGateStatus) PASSED only for the hardware-pass marker, else NOT_PASSED.
    """
    if document_status == FRICTION_PASSED_STATUS:
        return FrictionGateStatus.PASSED
    return FrictionGateStatus.NOT_PASSED


class FrictionGate:
    """The offer a friction status yields: which paths, and the sag banner when (C) is blocked."""

    def __init__(self, status: FrictionGateStatus) -> None:
        """Bind the gate to a friction status.

        Args:
            status: The PG-FRIC-001 verdict, from :func:`friction_gate_status`.
        """
        self._status = status

    @property
    def status(self) -> FrictionGateStatus:
        """The friction status this gate reflects.

        Returns:
            (FrictionGateStatus) The bound status.
        """
        return self._status

    @property
    def path_c_available(self) -> bool:
        """Whether gravity-compensated hand-guiding (path C) may start.

        Returns:
            (bool) True only when PG-FRIC-001 has passed.
        """
        return self._status is FrictionGateStatus.PASSED

    def offered_paths(self) -> tuple[FreedrivePath, ...]:
        """The Freedrive paths offered under this status.

        Returns:
            (tuple[FreedrivePath, ...]) (A)/(B) always; (C) appended only on a friction pass.
        """
        return _PATHS_WITH_C if self.path_c_available else _PATHS_WITHOUT_C

    def banner(self) -> str | None:
        """The FR-MAN-035 sag banner shown when path (C) is unavailable.

        Returns:
            (str | None) The "gravity uncompensated - arm sags" banner when (C) is blocked, else
            None — a passed gate compensates gravity and needs no sag warning.
        """
        return None if self.path_c_available else GRAVITY_UNCOMPENSATED_BANNER
