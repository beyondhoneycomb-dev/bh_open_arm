"""The fixed MJCF asset the IK adapter resolves over (09 §1.1, WP-0C-03).

``mink.ConfigurationLimit`` reads the model's ``jnt_range`` and nothing else
(kinematics.py:170), so IK's real limit source is the MJCF — which makes a defective
asset a defect in the *real* command path, not a sim-quality nicety (09 §1.1). This
module points the adapter at the repo-owned, J7-corrected cell scene that WP-0C-03
owns, rather than ``openarm_control``'s hard-coded upstream default, so the limits IK
sees are the audited ones.

The cell scene, not the bare bimanual model, is the IK asset: it carries the
``home`` keyframe and attaches the bimanual with an empty prefix, so
``right_ee_control_point`` / ``left_ee_control_point`` resolve unprefixed and the
model is nq/nv/nu = 19/19/17 (lifter + two 7+2 arms). Paths are resolved through the
``sim.mjcf`` package so the adapter is independent of the working directory; this
module only *reads* the asset — WP-0C-03 owns writing it.
"""

from __future__ import annotations

from pathlib import Path

import sim.mjcf

# EE control-point sites the cell exposes unprefixed; the default IK frames.
RIGHT_EE_SITE = "right_ee_control_point"
LEFT_EE_SITE = "left_ee_control_point"
EE_FRAME_TYPE = "site"

# The keyframe the cell defines as the arms' rest pose; IK seeds its configuration
# from it, matching openarm_control's own default.
HOME_KEYFRAME = "home"


def fixed_cell_xml() -> Path:
    """Return the path to the WP-0C-03 fixed cell scene used as the IK asset.

    Returns:
        (Path) Absolute path to ``sim/mjcf/v2/cell.xml``.

    Raises:
        FileNotFoundError: When the vendored asset is absent.
    """
    mjcf_dir = Path(sim.mjcf.__file__).resolve().parent
    path = mjcf_dir / "v2" / "cell.xml"
    if not path.is_file():
        raise FileNotFoundError(f"fixed IK cell asset not found: {path}")
    return path
