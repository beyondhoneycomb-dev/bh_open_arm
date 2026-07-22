"""WP-3B-03 acceptance ① — the LeRobot depth-API gate blocks collection start.

The gate is judged by API presence, never a parsed version string (FR-CAM-083). This
host has LeRobot v0.6.0 installed, so the real class probe genuinely passes; a stub
missing the two methods stands in for a 0.5.1 runtime and is genuinely blocked.
"""

from __future__ import annotations

import pytest

from backend.sensing.depth.constants import DEPTH_ASYNC_READ_METHOD, DEPTH_LATEST_READ_METHOD
from backend.sensing.depth.toggle import DepthToggles
from backend.sensing.depth.version_gate import (
    DepthStartBlockedError,
    assert_depth_startable,
    depth_record_api_present,
    installed_realsense_camera_class,
    installed_runtime_supports_depth,
)


class _RuntimeWithoutDepthApi:
    """A stand-in for a 0.5.1 runtime: synchronous depth only, no async/latest."""

    def read_depth(self) -> None:
        """Synchronous depth read; the only depth path 0.5.1 offers."""


class _RuntimeWithDepthApi:
    """A stand-in for a 0.6.0 runtime exposing the async/latest depth API."""

    def async_read_depth(self) -> None:
        """Background-thread depth read (v0.6.0)."""

    def read_latest_depth(self) -> None:
        """Non-blocking latest-depth peek (v0.6.0)."""


_DEPTH_ON = DepthToggles(frozenset({"overhead"}))
_DEPTH_OFF = DepthToggles(frozenset())


def test_api_presence_is_the_judgment_not_a_version_string() -> None:
    """The gate reads the two method names, not a version."""
    assert depth_record_api_present(_RuntimeWithDepthApi)
    assert not depth_record_api_present(_RuntimeWithoutDepthApi)


def test_installed_lerobot_exposes_the_depth_record_api() -> None:
    """The v0.6.0 actually installed on this host carries both methods."""
    assert installed_runtime_supports_depth()
    realsense = installed_realsense_camera_class()
    assert hasattr(realsense, DEPTH_ASYNC_READ_METHOD)
    assert hasattr(realsense, DEPTH_LATEST_READ_METHOD)


def test_depth_on_with_a_051_runtime_blocks_start() -> None:
    """Depth toggled on against a runtime without the API blocks collection start."""
    with pytest.raises(DepthStartBlockedError, match="collection start is blocked"):
        assert_depth_startable(_DEPTH_ON, _RuntimeWithoutDepthApi)


def test_depth_on_with_a_060_runtime_is_startable() -> None:
    """Depth toggled on against a runtime with the API starts."""
    assert_depth_startable(_DEPTH_ON, _RuntimeWithDepthApi)
    assert_depth_startable(_DEPTH_ON, installed_realsense_camera_class())


def test_depth_off_never_gates_on_the_runtime() -> None:
    """With no depth toggled on, even a 0.5.1 runtime is startable — depth is optional."""
    assert_depth_startable(_DEPTH_OFF, _RuntimeWithoutDepthApi)
