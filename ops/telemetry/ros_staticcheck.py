"""Prove the MCAP path carries no rosbag2 / ROS dependency (`14` FR-OPS-006, acceptance ⑤).

FR-OPS-006 requires the timeseries be written with the `mcap` library *directly* and bans
rosbag2. "No dependency" is an absence, so it is checked by reading every import in the tree
rather than by observing that one run happened not to import ROS. Any import whose top-level
module is a ROS or rosbag package is a finding.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ops.telemetry.staticcheck import StaticViolation, iter_python

# Top-level module names that mean a ROS / rosbag2 dependency has entered the tree. The MCAP
# path must reach the format through `mcap` alone; none of these may appear.
FORBIDDEN_ROOTS = frozenset(
    {
        "rosbag2_py",
        "rosbags",
        "rosbag",
        "rclpy",
        "rclcpp",
        "ros2bag",
        "ros2",
        "sensor_msgs",
        "std_msgs",
        "geometry_msgs",
        "diagnostic_msgs",
    }
)


def _forbidden_root(module: str) -> str | None:
    """Return the forbidden top-level module a dotted import name resolves to, if any.

    Args:
        module: A dotted module name from an import statement.

    Returns:
        (str | None) The matched forbidden root, or None.
    """
    root = module.split(".", 1)[0]
    return root if root in FORBIDDEN_ROOTS else None


def find_forbidden_ros_imports(root: Path) -> list[StaticViolation]:
    """Find imports of any ROS / rosbag2 module under a tree.

    Args:
        root: Directory (or file) to scan.

    Returns:
        (list[StaticViolation]) One finding per forbidden import, sorted by path and line.
    """
    violations: list[StaticViolation] = []
    for path in iter_python(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    matched = _forbidden_root(alias.name)
                    if matched is not None:
                        violations.append(
                            StaticViolation(
                                path=path,
                                line=node.lineno,
                                symbol=alias.name,
                                rule="rosbag2/ROS dependency on the MCAP path",
                            )
                        )
            elif isinstance(node, ast.ImportFrom):
                matched = _forbidden_root(node.module or "")
                if matched is not None:
                    violations.append(
                        StaticViolation(
                            path=path,
                            line=node.lineno,
                            symbol=node.module or matched,
                            rule="rosbag2/ROS dependency on the MCAP path",
                        )
                    )
    return sorted(violations, key=lambda item: (str(item.path), item.line))
