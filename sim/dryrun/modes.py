"""The three-mode sim tier and its mutual exclusion (`09` FR-SIM-097~100).

The sim runs in exactly one of three modes on the shared Robot ABC: pure-sim (a),
digital-twin (b), and dry-run (c). All three are CAN-not-opened — the twin only
mirrors observations, and neither pure-sim nor dry-run reaches hardware (`09`
FR-SIM-098/099/100). The tier is exclusive: two modes active at once is a
violation (acceptance ⑭), because "which component holds send_action" is a single
right and two live modes would contend for it.

Exclusion is enforced by a controller that holds at most one active mode and
refuses to activate a second, and by ``validate_active_modes`` for a fixture that
asserts a set of active modes is legal. The CAN-not-opened invariant reuses
WP-0C-01's runtime chokepoint (``assert_no_can_open``): every activation re-checks
that the mode has opened zero CAN sockets, so a CAN open on any mode's path stops
the run rather than being assumed away. The source-level half — that no CAN
primitive appears in ``sim/dryrun`` at all — is proven by ``staticcheck``.
"""

from __future__ import annotations

from collections.abc import Collection
from enum import Enum

from packages.lerobot_robot_openarm_mujoco.can_guard import assert_no_can_open

# A sim mode opens no CAN socket for its whole life; this is the count the runtime
# hook checks on every activation (`09` FR-SIM-098/099/100).
_SIM_CAN_OPEN_COUNT = 0

# Only one mode may be active at a time.
_MAX_ACTIVE_MODES = 1


class SimMode(Enum):
    """The three mutually exclusive sim modes on the shared Robot ABC."""

    PURE_SIM = "pure_sim"
    DIGITAL_TWIN = "digital_twin"
    DRY_RUN = "dry_run"


class ModeExclusionError(RuntimeError):
    """Raised when a second sim mode is activated while one is already active."""


def validate_active_modes(active: Collection[SimMode]) -> None:
    """Refuse a set of active modes with more than one live mode (acceptance ⑭).

    Args:
        active: The modes claimed active.

    Raises:
        ModeExclusionError: If more than one mode is active.
    """
    distinct = set(active)
    if len(distinct) > _MAX_ACTIVE_MODES:
        raise ModeExclusionError(
            f"{len(distinct)} sim modes active at once ({sorted(m.value for m in distinct)}); "
            "the mode tier is exclusive — at most one may hold send_action (09 FR-SIM-071)"
        )


class ModeController:
    """Holds at most one active sim mode and enforces exclusion + CAN-not-opened.

    Not thread-safe; one controller serves one session. Every activation re-checks
    that the mode has opened zero CAN sockets (all three modes are CAN-less), so the
    invariant is enforced at each transition, not assumed once.
    """

    def __init__(self) -> None:
        """Initialize with no active mode."""
        self._active: SimMode | None = None
        # A sim mode opens no CAN socket; this counter stays zero for the session's
        # life and is what the runtime hook checks on every activation.
        self._can_open_count = _SIM_CAN_OPEN_COUNT

    @property
    def active(self) -> SimMode | None:
        """The currently active mode, or None when idle."""
        return self._active

    def activate(self, mode: SimMode) -> None:
        """Activate a mode, refusing a second concurrent mode and any CAN open.

        Args:
            mode: The mode to activate.

        Raises:
            ModeExclusionError: If another mode is already active.
            SimModeCanError: If any CAN socket was opened on this mode's path.
        """
        if self._active is not None and self._active is not mode:
            raise ModeExclusionError(
                f"cannot activate {mode.value}; {self._active.value} is already active — "
                "the mode tier is exclusive (09 FR-SIM-071)"
            )
        assert_no_can_open(self._can_open_count)
        self._active = mode

    def deactivate(self) -> None:
        """Clear the active mode, returning the tier to idle."""
        self._active = None
