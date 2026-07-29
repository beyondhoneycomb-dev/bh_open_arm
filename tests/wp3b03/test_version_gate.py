"""WP-3B-03 acceptance ① — the LeRobot depth gate blocks collection start.

The gate is judged by backend existence and API presence, never a parsed version string
(FR-CAM-083). This host has LeRobot v0.6.0 installed, so the RealSense class probe
genuinely passes; a stub missing the two methods stands in for a 0.5.1 runtime and is
genuinely blocked; and the ZED family is blocked one step earlier, because the installed
LeRobot ships no camera class for it to probe.

The order of those two judgments is itself under test: a caller-supplied camera class is
judged only after the family is known to have one, so no stub can stand in for a backend
that does not exist.
"""

from __future__ import annotations

import inspect

import pytest

from backend.sensing.depth.constants import (
    DEPTH_ASYNC_READ_METHOD,
    DEPTH_LATEST_READ_METHOD,
    LEROBOT_DEPTH_CAMERA_CLASS,
    DepthDevice,
)
from backend.sensing.depth.toggle import DepthToggles
from backend.sensing.depth.version_gate import (
    DepthApiMissingError,
    DepthBackendMissingError,
    DepthStartBlockedError,
    assert_depth_backend_exists,
    assert_depth_startable,
    depth_record_api_present,
    installed_depth_camera_class,
    installed_runtime_supports_depth,
    lerobot_backend_exists,
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


def test_every_named_family_has_a_backend_decision() -> None:
    """No family can be gated without a recorded decision about its backend."""
    assert set(LEROBOT_DEPTH_CAMERA_CLASS) == set(DepthDevice)


@pytest.mark.parametrize(
    "gate", [assert_depth_startable, installed_depth_camera_class, installed_runtime_supports_depth]
)
def test_no_gate_carries_a_default_family(gate: object) -> None:
    """`device` has no default anywhere: an omitted family would silently mean one.

    The one property in this file that only the signature enforces. A default leaves
    every behavioural test here passing while an omitted argument quietly probes the
    RealSense class and reports a green about a camera this rig does not have.
    """
    parameter = inspect.signature(gate).parameters["device"]  # type: ignore[arg-type]
    assert parameter.default is inspect.Parameter.empty


def test_installed_lerobot_drives_realsense_but_not_the_zed() -> None:
    """The v0.6.0 on this host ships a RealSense camera class and no ZED one."""
    assert lerobot_backend_exists(DepthDevice.INTEL_REALSENSE)
    assert not lerobot_backend_exists(DepthDevice.STEREOLABS_ZED)

    realsense = installed_depth_camera_class(DepthDevice.INTEL_REALSENSE)
    assert hasattr(realsense, DEPTH_ASYNC_READ_METHOD)
    assert hasattr(realsense, DEPTH_LATEST_READ_METHOD)

    assert installed_runtime_supports_depth(DepthDevice.INTEL_REALSENSE)
    assert not installed_runtime_supports_depth(DepthDevice.STEREOLABS_ZED)


def test_resolving_a_family_lerobot_cannot_drive_is_refused() -> None:
    """Asking for the ZED camera class raises rather than returning a stand-in."""
    with pytest.raises(DepthBackendMissingError, match="no camera class"):
        installed_depth_camera_class(DepthDevice.STEREOLABS_ZED)


def test_depth_on_for_the_zed_blocks_start_before_any_api_probe() -> None:
    """The fitted ZED blocks start: LeRobot has no class to record its depth through."""
    with pytest.raises(DepthBackendMissingError, match="stereolabs_zed"):
        assert_depth_startable(_DEPTH_ON, DepthDevice.STEREOLABS_ZED)


def test_a_supplied_camera_class_cannot_buy_a_green_for_an_undriveable_family() -> None:
    """Backend existence is judged before the API probe and independently of it.

    The gate's documented `DepthBackendMissingError` is only true if it holds on the
    branch a caller supplies a class on. Judging the class first turns a healthy stub
    into a start permit for a family LeRobot cannot open at all — the session begins,
    records no depth key, and the operator sees the toggle they set.
    """
    with pytest.raises(DepthBackendMissingError, match="no camera class"):
        assert_depth_startable(_DEPTH_ON, DepthDevice.STEREOLABS_ZED, _RuntimeWithDepthApi)


def test_the_backend_check_stands_alone_from_any_class() -> None:
    """The backend question is answerable with no camera class in hand at all."""
    assert_depth_backend_exists(DepthDevice.INTEL_REALSENSE)
    with pytest.raises(DepthBackendMissingError, match="stereolabs_zed"):
        assert_depth_backend_exists(DepthDevice.STEREOLABS_ZED)


def test_depth_on_with_a_051_runtime_blocks_start() -> None:
    """Depth toggled on against a runtime without the API blocks collection start."""
    with pytest.raises(DepthApiMissingError, match="collection start is blocked"):
        assert_depth_startable(_DEPTH_ON, DepthDevice.INTEL_REALSENSE, _RuntimeWithoutDepthApi)


def test_both_blocks_are_catchable_as_one_start_refusal() -> None:
    """A caller asking only "can this start?" catches the base of both refusals."""
    assert issubclass(DepthBackendMissingError, DepthStartBlockedError)
    assert issubclass(DepthApiMissingError, DepthStartBlockedError)
    with pytest.raises(DepthStartBlockedError):
        assert_depth_startable(_DEPTH_ON, DepthDevice.STEREOLABS_ZED)
    with pytest.raises(DepthStartBlockedError):
        assert_depth_startable(_DEPTH_ON, DepthDevice.INTEL_REALSENSE, _RuntimeWithoutDepthApi)


def test_depth_on_with_a_060_runtime_is_startable() -> None:
    """Depth toggled on against a runtime with the API starts."""
    assert_depth_startable(_DEPTH_ON, DepthDevice.INTEL_REALSENSE, _RuntimeWithDepthApi)
    assert_depth_startable(
        _DEPTH_ON,
        DepthDevice.INTEL_REALSENSE,
        installed_depth_camera_class(DepthDevice.INTEL_REALSENSE),
    )


def test_depth_off_never_gates_on_the_runtime() -> None:
    """With no depth on, even an undriveable family is startable — depth is optional."""
    assert_depth_startable(_DEPTH_OFF, DepthDevice.INTEL_REALSENSE, _RuntimeWithoutDepthApi)
    assert_depth_startable(_DEPTH_OFF, DepthDevice.STEREOLABS_ZED)
