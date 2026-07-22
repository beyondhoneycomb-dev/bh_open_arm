"""Cartesian jog adapter (WP-2D-01) — the jog API WP-2D-02/09 consume.

Translation and rotation jog over the reused Wave 0-C IK adapter (``sim.ik``), with
reference frames (world/base/tool), TCP selection, the q_lift reflection into the base
frame, and runtime-exposed IK parameters. The jog never builds a second IK: it reaches
``Kinematics`` only through ``sim.ik.build_ik_adapter``'s ordered build, and a failed
step holds and reports rather than skipping (02b §4.2 WP-2D-01).

Consumption surface:

- WP-2D-02 (singularity monitor + nullspace): ``arm_joints``, ``q_lift``, ``ik_params``,
  ``set_velocity_scale``, ``set_singularity_monitor`` (+ ``JogStopReason.SINGULARITY``).
- WP-2D-09 (numeric Move-to): ``plan_pose(commit=False)`` / ``ik_solution_exists`` for
  the IK-existence check, ``plan_pose(commit=True)`` to execute, ``current_pose``.
"""

from __future__ import annotations

from backend.cartesian_jog.frames import KinematicFrames, ReferenceFrame
from backend.cartesian_jog.jog import (
    CartesianJog,
    JogAxis,
    JogCommand,
    JogKind,
    JogResult,
    JogStopReason,
    SingularityMonitor,
    build_cartesian_jog,
)
from backend.cartesian_jog.tcp import TcpSelection, ToolCenterPoint

__all__ = [
    "CartesianJog",
    "JogAxis",
    "JogCommand",
    "JogKind",
    "JogResult",
    "JogStopReason",
    "KinematicFrames",
    "ReferenceFrame",
    "SingularityMonitor",
    "TcpSelection",
    "ToolCenterPoint",
    "build_cartesian_jog",
]
