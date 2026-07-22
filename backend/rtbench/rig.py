"""The rig binding: WP-1-04's read path is the WP-1-03 follower's `connect_readonly`.

WP-1-04 consumes the `WP-1-03` gateway as its read path (`02a` WP-1-04 input). On the
rig, the measurement session's single `connect()` is the follower's `connect_readonly`
(torque-OFF bring-up, no `enable_torque`), and the torque probe reads the follower's
`is_torque_enabled`. This module is the seam that binds the session to that follower —
the concrete `connect` callable and `TorqueProbe` the rig supplies.

The follower import pulls the LeRobot stack, so it is type-only here (`TYPE_CHECKING`):
the follower is constructed by the caller on the rig and injected, so this module names
its type without importing it at runtime, and `import backend.rtbench` stays light. That
this seam runs only on the rig is why the on-hardware measurement is the deferred part
of WP-1-04 (`02a` §4.1); the binding logic itself is exercised offline with a stub.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.rtbench.session import TorqueState

if TYPE_CHECKING:
    from backend.can.lock.manager import LockManager
    from packages.lerobot_robot_openarm.openarm_follower_oa import OaOpenArmFollower


class RigReadonlyConnect:
    """The single-session, torque-OFF connect callable the rig session runs.

    Ownership: holds the caller-constructed follower and the lock manager; calling it
    opens the read-only session exactly once (the session enforces the count) and
    returns the bound follower. It never enables torque — it is `connect_readonly`,
    the `WP-1-03`/`WP-1-02` read path (`12` FR-SAF-075).

    Args:
        follower: The `WP-1-03` follower to bring up read-only.
        lock_manager: The `WP-0B-01` lock manager holding the channel locks.
    """

    def __init__(self, follower: OaOpenArmFollower, lock_manager: LockManager) -> None:
        self._follower = follower
        self._lock_manager = lock_manager

    def __call__(self) -> OaOpenArmFollower:
        """Open the read-only session and return the bound follower.

        Returns:
            (OaOpenArmFollower) The follower, now connected read-only.
        """
        self._follower.connect_readonly(self._lock_manager)
        return self._follower


class RigTorqueProbe:
    """A `TorqueProbe` that reads the follower's real enable state.

    The follower reports one aggregate `is_torque_enabled` (true when any motor is
    enabled), which is the granularity the torque-OFF assertion needs: the read-only
    measurement requires every motor OFF, so the aggregate maps to a single-entry
    `TorqueState` whose `all_off()` is the follower's `not is_torque_enabled`.

    Args:
        follower: The `WP-1-03` follower whose enable state is read.
    """

    def __init__(self, follower: OaOpenArmFollower) -> None:
        self._follower = follower

    def __call__(self) -> TorqueState:
        """Read the follower's aggregate torque-enable state.

        Returns:
            (TorqueState) A single-entry state that is `all_off` iff the follower
            reports no motor enabled.
        """
        return TorqueState(enabled={0: bool(self._follower.is_torque_enabled)})
