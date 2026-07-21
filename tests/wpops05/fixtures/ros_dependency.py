"""Violation fixture: a rosbag2 / ROS dependency on the timeseries path (FR-OPS-006).

Proves `find_forbidden_ros_imports` bites. This module is never imported — the scan reads it
as text — so the absent ROS packages never need to exist; only the import statements matter.
"""

from __future__ import annotations

import rosbag2_py
from rclpy import time


def writer_names() -> tuple[object, object]:
    """Reference the forbidden imports so they are not dead code to the linter."""
    return (rosbag2_py, time)
