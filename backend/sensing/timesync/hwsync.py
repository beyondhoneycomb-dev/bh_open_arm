"""RealSense hardware sync: one master triggers the slaves, and fps is forced equal.

`02b` §6.1 WP-3B-04: when cameras are hardware-synced, one is the trigger source
(master) and the rest are triggered (slave) via librealsense `inter_cam_sync_mode`,
and hardware sync **forces every stream to the same fps** — a triggered camera cannot
run a rate its trigger does not (`06` §2.6, FR-CAM-017/018). This module is the model
of that group: it admits exactly one master, refuses a mixed-fps group, and emits the
device option code per slot.

The fps it enforces is read from each `CTR-CAM@v1` `CameraSpec`, the single place
resolution and fps are declared; nothing here restates a rate as a literal.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from backend.sensing.timesync.constants import (
    INTER_CAM_SYNC_MODE_DEFAULT,
    INTER_CAM_SYNC_MODE_MASTER,
    INTER_CAM_SYNC_MODE_SLAVE,
)
from contracts.camera_registry import CameraSpec
from contracts.prim import CameraSlotKey


class HardwareSyncError(ValueError):
    """Raised when a hardware-sync group violates the WP-3B-04 master/slave contract."""


class SyncRole(StrEnum):
    """A camera's role in a hardware-sync group (`06` §2.6).

    `DEFAULT` is a free-running camera outside any trigger chain; `MASTER` is the one
    trigger source; `SLAVE` is a camera driven by the master's trigger.
    """

    DEFAULT = "default"
    MASTER = "master"
    SLAVE = "slave"


# The device option code each role maps to. Named through `constants` so the value
# handed to the driver is the librealsense integer, not one invented here.
_MODE_VALUE = {
    SyncRole.DEFAULT: INTER_CAM_SYNC_MODE_DEFAULT,
    SyncRole.MASTER: INTER_CAM_SYNC_MODE_MASTER,
    SyncRole.SLAVE: INTER_CAM_SYNC_MODE_SLAVE,
}


def inter_cam_sync_mode_value(role: SyncRole) -> int:
    """The librealsense `inter_cam_sync_mode` code for a role.

    Args:
        role: The camera's sync role.

    Returns:
        (int) 0 for default, 1 for master, 2 for slave.
    """
    return _MODE_VALUE[role]


def enforce_same_fps(specs: Iterable[CameraSpec]) -> int:
    """Return the one fps a hardware-sync group shares, or refuse a mismatch.

    Hardware sync forces every stream to the master's rate, so a group whose cameras
    were configured to different fps cannot be hardware-synced at all — that is a
    configuration error, caught here rather than at a triggered camera that silently
    free-runs.

    Args:
        specs: The camera specs in the group; each must be configured (fps set).

    Returns:
        (int) The common frames-per-second.

    Raises:
        HardwareSyncError: If a spec is unconfigured or the group mixes fps.
    """
    rates = [spec.fps for spec in specs]
    if not rates:
        raise HardwareSyncError("a hardware-sync group needs at least one camera")
    if any(rate is None for rate in rates):
        raise HardwareSyncError(
            "every hardware-synced camera must be configured; an unset fps cannot be forced equal"
        )
    distinct = sorted({rate for rate in rates if rate is not None})
    if len(distinct) != 1:
        raise HardwareSyncError(
            f"hardware sync forces one fps across all streams, but the group declares {distinct}"
        )
    return distinct[0]


@dataclass(frozen=True)
class HardwareSyncMember:
    """One camera's membership in a hardware-sync group: its spec and role.

    Attributes:
        spec: The camera's `CTR-CAM@v1` spec (carries the slot and fps).
        role: The camera's role in the group.
    """

    spec: CameraSpec
    role: SyncRole

    @property
    def slot(self) -> CameraSlotKey:
        """The camera slot this member occupies."""
        return self.spec.slot


@dataclass(frozen=True)
class HardwareSyncGroup:
    """A validated hardware-sync group: exactly one master, all at one fps.

    Attributes:
        members: The cameras in the group and their roles.
    """

    members: tuple[HardwareSyncMember, ...]

    def __post_init__(self) -> None:
        """Enforce the master/slave shape and the single forced fps."""
        if len(self.members) < 2:
            raise HardwareSyncError("a hardware-sync group needs at least two cameras")
        masters = [member for member in self.members if member.role is SyncRole.MASTER]
        if len(masters) != 1:
            raise HardwareSyncError(
                f"a hardware-sync group needs exactly one master, got {len(masters)}"
            )
        if any(member.role is SyncRole.DEFAULT for member in self.members):
            raise HardwareSyncError(
                "a hardware-sync group has no free-running members; every non-master is a slave"
            )
        # Reading the group's fps validates it is single and configured — the same-fps
        # force is asserted at construction, so a mixed-fps group cannot exist.
        enforce_same_fps(member.spec for member in self.members)

    def master(self) -> HardwareSyncMember:
        """The single trigger-source member.

        Returns:
            (HardwareSyncMember) The master camera.
        """
        return next(member for member in self.members if member.role is SyncRole.MASTER)

    def fps(self) -> int:
        """The one frames-per-second every stream in the group is forced to.

        Returns:
            (int) The common fps.
        """
        return enforce_same_fps(member.spec for member in self.members)

    def mode_values(self) -> dict[CameraSlotKey, int]:
        """The `inter_cam_sync_mode` code to program into each camera.

        Returns:
            (dict[CameraSlotKey, int]) Slot to its device option code (master 1,
                slaves 2).
        """
        return {member.slot: inter_cam_sync_mode_value(member.role) for member in self.members}
