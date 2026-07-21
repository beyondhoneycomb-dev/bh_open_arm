"""Acceptance ⑤ (dependency half) — zero rosbag2 / ROS dependency on the MCAP path.

FR-OPS-006 requires the timeseries reach MCAP through `mcap` directly, never rosbag2. The scan
must (a) find zero ROS imports across the real `ops/telemetry` product tree, and (b) actually
bite on a fixture that imports one — a scan that finds nothing because it can find nothing is
the worst outcome.
"""

from __future__ import annotations

from pathlib import Path

from ops.telemetry.ros_staticcheck import find_forbidden_ros_imports

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TELEMETRY_PACKAGE = _REPO_ROOT / "ops" / "telemetry"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_product_tree_has_no_ros_dependency() -> None:
    """The real telemetry package imports no rosbag2 / ROS module anywhere."""
    assert find_forbidden_ros_imports(_TELEMETRY_PACKAGE) == []


def test_scan_bites_on_a_ros_dependency_fixture() -> None:
    """The scan flags a module that imports rosbag2 and rclpy."""
    violations = find_forbidden_ros_imports(_FIXTURES / "ros_dependency.py")
    symbols = {violation.symbol for violation in violations}
    assert "rosbag2_py" in symbols
    assert "rclpy" in symbols


def test_scan_does_not_overfire_on_the_mcap_only_fixture() -> None:
    """A module that reaches MCAP through `mcap` alone produces no finding."""
    assert find_forbidden_ros_imports(_FIXTURES / "ros_clean.py") == []
