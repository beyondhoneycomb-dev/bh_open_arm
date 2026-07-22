"""Acceptance ③: hardware sync = one master, the rest slaves, one fps forced.

`02b` §6.1 WP-3B-04: a RealSense hardware-sync group has exactly one trigger source
(master) and drives the rest as slaves via `inter_cam_sync_mode`, and hardware sync
forces every stream to the same fps. These tests pin the master/slave shape, the
forced-fps rule, and the device option codes.
"""

from __future__ import annotations

import pytest

from backend.sensing.timesync.constants import (
    INTER_CAM_SYNC_MODE_MASTER,
    INTER_CAM_SYNC_MODE_SLAVE,
)
from backend.sensing.timesync.hwsync import (
    HardwareSyncError,
    HardwareSyncGroup,
    HardwareSyncMember,
    SyncRole,
    enforce_same_fps,
    inter_cam_sync_mode_value,
)
from contracts.camera_registry import CameraSpec
from tests.wp3b04.conftest import configured_spec, reconfigured_fps, spec_fps

_LEFT = configured_spec(0)
_RIGHT = configured_spec(1)


def _mismatched_fps_spec() -> CameraSpec:
    """A copy of the right camera reconfigured to a different fps (no literal rate)."""
    return reconfigured_fps(_RIGHT, spec_fps(_RIGHT) * 2)


def test_option_codes_are_the_librealsense_integers() -> None:
    """Master and slave map to the driver's own inter_cam_sync_mode codes."""
    assert inter_cam_sync_mode_value(SyncRole.MASTER) == INTER_CAM_SYNC_MODE_MASTER
    assert inter_cam_sync_mode_value(SyncRole.SLAVE) == INTER_CAM_SYNC_MODE_SLAVE


def test_a_master_slave_group_forces_one_fps_and_programs_the_codes() -> None:
    """A one-master/one-slave group at a shared fps yields the per-slot codes (③)."""
    group = HardwareSyncGroup(
        members=(
            HardwareSyncMember(spec=_LEFT, role=SyncRole.MASTER),
            HardwareSyncMember(spec=_RIGHT, role=SyncRole.SLAVE),
        )
    )
    assert group.fps() == _LEFT.fps
    assert group.master().slot == _LEFT.slot
    assert group.mode_values() == {
        _LEFT.slot: INTER_CAM_SYNC_MODE_MASTER,
        _RIGHT.slot: INTER_CAM_SYNC_MODE_SLAVE,
    }


def test_a_group_with_mixed_fps_is_refused() -> None:
    """Hardware sync cannot span cameras configured to different fps (③)."""
    with pytest.raises(HardwareSyncError, match="one fps"):
        HardwareSyncGroup(
            members=(
                HardwareSyncMember(spec=_LEFT, role=SyncRole.MASTER),
                HardwareSyncMember(spec=_mismatched_fps_spec(), role=SyncRole.SLAVE),
            )
        )


def test_enforce_same_fps_returns_the_common_rate() -> None:
    """A group at one fps reports that fps; a mixed group raises."""
    assert enforce_same_fps((_LEFT, _RIGHT)) == _LEFT.fps
    with pytest.raises(HardwareSyncError, match="one fps"):
        enforce_same_fps((_LEFT, _mismatched_fps_spec()))


def test_a_group_needs_exactly_one_master() -> None:
    """Two masters (or none) is not a valid trigger chain."""
    with pytest.raises(HardwareSyncError, match="exactly one master"):
        HardwareSyncGroup(
            members=(
                HardwareSyncMember(spec=_LEFT, role=SyncRole.MASTER),
                HardwareSyncMember(spec=_RIGHT, role=SyncRole.MASTER),
            )
        )


def test_a_hardware_group_has_no_free_running_member() -> None:
    """A DEFAULT (free-running) camera cannot sit inside a hardware-sync group."""
    with pytest.raises(HardwareSyncError, match="slave"):
        HardwareSyncGroup(
            members=(
                HardwareSyncMember(spec=_LEFT, role=SyncRole.MASTER),
                HardwareSyncMember(spec=_RIGHT, role=SyncRole.DEFAULT),
            )
        )


def test_a_group_needs_at_least_two_cameras() -> None:
    """A single camera is not a sync group."""
    with pytest.raises(HardwareSyncError, match="at least two"):
        HardwareSyncGroup(members=(HardwareSyncMember(spec=_LEFT, role=SyncRole.MASTER),))
