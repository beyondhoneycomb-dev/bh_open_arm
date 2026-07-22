"""Tool-center-point selection for the Cartesian jog (WP-2D-01, acceptance ⑥).

The jog moves a TCP, and which point that is changes what the operator feels: the
default is the EE control point (the wrist flange the IK site sits on), which is
deliberately NOT the point between the fingers. Teaching about the flange when you
meant the fingertip mis-places every taught pose by the flange-to-tip offset, so the
default is stated (``constants.TCP_DEFAULT_NOTE``) and the grasp point is an explicit,
separate selection.

The TCP is a rigid offset from the control point, expressed in the control-point
frame. FLANGE is identity — the control point itself. GRASP carries the model-derived
finger offset (``KinematicFrames.grasp_offset_pose``). A jog computes a target for the
selected TCP; the adapter converts it back to the control-point pose the IK site
solves for by composing the inverse offset.
"""

from __future__ import annotations

from enum import Enum

import numpy as np

from backend.cartesian_jog.frames import QUAT_IDENTITY, KinematicFrames, make_pose


class TcpSelection(Enum):
    """Which tool-center point the jog acts on. FLANGE is the default (not grasp)."""

    FLANGE = "flange"
    GRASP = "grasp"


class ToolCenterPoint:
    """Resolves the offset from the EE control point to a selected TCP, per side.

    The FLANGE offset is identity by construction, which is the machine-checkable form
    of "the default TCP is the control point, not the grasp point". GRASP offsets are
    read from the gripper geometry once at build.
    """

    def __init__(self, frames: KinematicFrames) -> None:
        """Cache the per-side grasp offsets from the model geometry."""
        self._flange = make_pose(np.zeros(3), QUAT_IDENTITY)
        self._grasp = {side: frames.grasp_offset_pose(side) for side in ("right", "left")}

    def offset(self, side: str, selection: TcpSelection) -> np.ndarray:
        """Return the control-point → TCP offset pose for a side and selection."""
        if selection is TcpSelection.FLANGE:
            return self._flange.copy()
        if side not in self._grasp:
            raise ValueError(f"side must be 'right' or 'left', got {side!r}")
        return self._grasp[side].copy()

    def default_is_not_grasp(self, side: str) -> bool:
        """Report that FLANGE (the default) and GRASP resolve to distinct points."""
        flange = self.offset(side, TcpSelection.FLANGE)
        grasp = self.offset(side, TcpSelection.GRASP)
        return not np.allclose(flange[:3], grasp[:3])
