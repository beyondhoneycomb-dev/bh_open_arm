"""WP-2B-09 — detection/control compensation-scale separation (FR-SAF-035, spec 12 §2.6).

Two compensation scales that must never collapse into one variable. The collision-residual
observer (WP-2C-01) subtracts the **full 100% model**; the control feedforward applies a
**partial** compensation (provisional v1 coefficients: friction 0.3, Coriolis 0.1). Binding them
turns the control coefficient into the detection model's scale, and the fraction it does not
compensate becomes the residual's standing floor — FAIL_BLOCKING (FR-SAF-035).

The public surface:

* `DetectionModelScales` — the residual model scales, pinned to 1.0 and validated (a partial
  detection model is refused at construction); build with `DetectionModelScales.full()`.
* `ControlCompensationScales` — the control partial-compensation set, defaults friction 0.3 /
  Coriolis 0.1, each validated to `[0, 1]`; `partial_comp_v1()` is the default.
* `detection_model_torque` / `control_feedforward_torque` — the two torque computations over the
  one WP-2B-02 `MUJOCO_V2` backend; the detection function takes no scale parameter, so its 100%
  model cannot be contaminated.
* `find_scale_bindings` / `assert_scales_independent` — the pure-AST static scan behind acceptance
  ②: zero code binds the two scales to one variable, and `ScaleBinding` is one finding.
"""

from __future__ import annotations

from backend.compscale.compensation import (
    control_feedforward_torque,
    detection_model_torque,
)
from backend.compscale.constants import (
    COMP_SCALE_MAX,
    COMP_SCALE_MIN,
    CORIOLIS_COMP_SCALE_DEFAULT,
    DETECTION_MODEL_SCALE,
    FRICTION_COMP_SCALE_DEFAULT,
)
from backend.compscale.errors import ScaleSeparationError
from backend.compscale.independence import (
    ScaleBinding,
    assert_scales_independent,
    compscale_package_files,
    find_scale_bindings,
)
from backend.compscale.scales import (
    CompensationScales,
    ControlCompensationScales,
    DetectionModelScales,
)

__all__ = [
    "COMP_SCALE_MAX",
    "COMP_SCALE_MIN",
    "CORIOLIS_COMP_SCALE_DEFAULT",
    "DETECTION_MODEL_SCALE",
    "FRICTION_COMP_SCALE_DEFAULT",
    "CompensationScales",
    "ControlCompensationScales",
    "DetectionModelScales",
    "ScaleBinding",
    "ScaleSeparationError",
    "assert_scales_independent",
    "compscale_package_files",
    "control_feedforward_torque",
    "detection_model_torque",
    "find_scale_bindings",
]
