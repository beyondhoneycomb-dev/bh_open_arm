"""The v2 asset's qpos/dof/actuator shape, asserted as a regression tripwire.

`09` §1.1 pins the bimanual cell to nq/nv/nu = 19/19/17 — lifter 1 + left 7+2 +
right 7+2 joints, and 17 actuators (16 arm/finger drivers + 1 lifter). The whole
FK<->IK round trip resolves joints by name, so it stays correct across a qpos
reordering; it does *not* stay correct across a change in the joint *count*. A model
that gained or lost a joint is a different robot, and the round-trip residual would
be comparing poses on two incompatible models. This shape assertion is the tripwire
that turns such an asset change into an explicit, named failure instead of a silent
mismatch (acceptance ④, "자산 변경 감지").
"""

from __future__ import annotations

from dataclasses import dataclass

import mujoco

# The frozen shape of the WP-0C-03 fixed cell. A deviation is an asset change, not a
# tolerance question, so these are exact equalities rather than ranges.
NQ_EXPECTED = 19
NV_EXPECTED = 19
NU_EXPECTED = 17


class ModelShapeError(RuntimeError):
    """Raised when a model's nq/nv/nu differs from the frozen v2 cell shape.

    Carries the expected and actual triples so a caller can see which axis moved
    without re-reading the model.
    """


@dataclass(frozen=True)
class ModelShape:
    """One model's (nq, nv, nu) triple.

    Attributes:
        nq: Generalised-coordinate count.
        nv: Degree-of-freedom count.
        nu: Actuator count.
    """

    nq: int
    nv: int
    nu: int

    @classmethod
    def of(cls, model: mujoco.MjModel) -> ModelShape:
        """Read the shape triple from a compiled model."""
        return cls(nq=int(model.nq), nv=int(model.nv), nu=int(model.nu))

    def matches_expected(self) -> bool:
        """Return whether this triple equals the frozen v2 cell shape."""
        return (self.nq, self.nv, self.nu) == (NQ_EXPECTED, NV_EXPECTED, NU_EXPECTED)


def assert_model_shape(model: mujoco.MjModel) -> ModelShape:
    """Assert a model has the frozen v2 cell shape, or reject.

    Args:
        model: The compiled model to check.

    Returns:
        (ModelShape) The confirmed shape, so a caller can log the triple.

    Raises:
        ModelShapeError: When nq, nv, or nu differs from 19/19/17.
    """
    shape = ModelShape.of(model)
    if not shape.matches_expected():
        raise ModelShapeError(
            f"model shape {(shape.nq, shape.nv, shape.nu)} != expected "
            f"{(NQ_EXPECTED, NV_EXPECTED, NU_EXPECTED)} (nq/nv/nu); the v2 asset "
            "gained or lost a joint or actuator, so the FK<->IK round trip is "
            "comparing poses on a different robot"
        )
    return shape
