"""Freedrive keep-out from the WP-2C-07 Cartesian virtual walls — reused, not rebuilt.

During Freedrive the residual trip is suppressed (`detection`), but a Cartesian keep-out wall
is not a residual detector — it is a geometric collision check — so it stays live. `04`
FR-MAN-037 keeps the non-residual detections on, and this is the one that reuses `sim.walls`.

The reuse is by identity, not by re-implementation: this module imports the WP-2C-07
`CellWallToggle` (the runtime wall state) and `guarded_cell_collision` (the check that refuses
to run over inactive walls) and re-exports them, and a static test asserts the re-exports are
the very same objects. It defines no second `WallGeom` or `WallScene` — the two-sources-of-
truth the audit hunts for — it only adapts the reused check into the Freedrive suite's
zero-argument detector shape (`FreedriveDetectionSuite.cartesian_wall_check`).
"""

from __future__ import annotations

import mujoco

from sim.walls import CellWallsInactiveError, CellWallToggle, guarded_cell_collision

__all__ = [
    "CellWallToggle",
    "CellWallsInactiveError",
    "FreedriveCartesianWalls",
    "guarded_cell_collision",
]


class FreedriveCartesianWalls:
    """Adapts the reused WP-2C-07 cell-collision check into a Freedrive tick detector.

    Ownership: holds a compiled model and its state plus the reused `CellWallToggle`, and
    exposes the reused check as the suite's zero-argument detector. It writes nothing and owns
    no walls of its own — the geoms are the committed asset's, the activation state is the
    toggle's, and the check is `guarded_cell_collision`. The caller mutates `data` in place
    before a tick, so `check` reflects the current pose; `sim_t` is only the timestamp stamped
    onto each violation, so it is fixed at construction. One instance per model per thread.

    Attributes:
        toggle: The reused WP-2C-07 runtime wall toggle over the same model.
    """

    def __init__(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
        toggle: CellWallToggle,
        sim_t: float = 0.0,
    ) -> None:
        """Bind to a model, its state, the reused wall toggle, and the violation timestamp.

        Args:
            model: The compiled cell model whose walls the check reads.
            data: The state to evaluate; its contacts are recomputed under the active masks.
            toggle: The reused WP-2C-07 runtime wall toggle over the same model.
            sim_t: Simulation time stamped onto each violation.
        """
        self._model = model
        self._data = data
        self.toggle = toggle
        self._sim_t = sim_t

    def check(self) -> tuple[object, ...]:
        """Run the reused cell-collision check, refusing over inactive walls.

        The zero-argument shape `FreedriveDetectionSuite` consumes as its Cartesian detector:
        it reads the current `data` and returns the WP-2C-07 violations, or refuses if the
        walls are inactive — Freedrive must not hand-guide against a keep-out silently off.

        Returns:
            (tuple) The WP-2C-07 cell-collision violations over the active-walled scene.

        Raises:
            CellWallsInactiveError: If any of the six cell walls is inactive (WP-2C-07 ①).
        """
        return guarded_cell_collision(self._model, self._data, self._sim_t)
