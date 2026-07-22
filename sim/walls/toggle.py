"""The runtime ``--walls``-equivalent toggle over the six cell walls (WP-2C-07).

`12` FR-SAF-013, `02b` §1.2 WP-2C-07: the cell's six wall collision geoms are
*inactive by default* at runtime (``contype=0; conaffinity=0``) and must be switched
on before a cell-collision check may be trusted. This module is that toggle, and it
is the piece WP-2A-00's `backend.interlock.walls` referred forward to: WP-2A-00 owns
the *refusal* (a check over inactive walls is vacuous and may not gate real-send);
this owns the *runtime state* that refusal reads.

The default is off on purpose. The committed cell asset (`sim/mjcf/v2/cell.xml`,
WP-0C-03, read-only here) ships its walls active; constructing a toggle over a model
flips them to the safe default, so "check ran and passed" can never mean "walls were
never on". The table (`cell_table_col`) is excluded from the toggled set and stays
active always — WP-2A-00's `CELL_WALL_GEOMS` already draws that line, and this reuses
it rather than re-listing the walls.

The activation state is read back through WP-2A-00's `inactive_cell_walls` /
`assert_cell_walls_active`, never a second predicate — one rule for "a wall is active",
owned by the interlock, so the toggle and the gate can never disagree about it.
"""

from __future__ import annotations

import mujoco

from backend.interlock.walls import (
    CELL_WALL_GEOMS,
    assert_cell_walls_active,
    inactive_cell_walls,
)

# The always-active cell surface. It is not among `CELL_WALL_GEOMS` (WP-2A-00 excludes
# it precisely so this toggle leaves it alone), and acceptance ③ requires it stay active
# through every wall toggle.
CELL_TABLE_GEOM = "cell_table_col"

# The runtime default: walls off. `02b` §1.2 WP-2C-07 makes deactivation the default so a
# cell-collision check refuses until walls are explicitly activated.
DEFAULT_WALLS_ENABLED = False

# The collision-mask value written to switch a geom back into the contact system when its
# asset-declared mask cannot be recovered (a model handed over already deactivated). Any
# non-zero contype/conaffinity makes a geom collidable; 1 matches the cell asset's walls.
_ACTIVE_MASK_FALLBACK = 1
_INACTIVE_MASK = 0


class CellTableInactiveError(RuntimeError):
    """Raised when the always-active cell table is absent or collision-inactive.

    Acceptance ③: `cell_table_col` must stay active through every wall toggle. A model
    whose table is off is a broken scene the toggle refuses to operate on, because the
    table is the one cell surface a check must always see.
    """


class CellWallToggle:
    """Runtime activation state for the six cell walls; default off (WP-2C-07).

    Ownership/lifecycle: wraps one compiled `mujoco.MjModel` and mutates its geom
    collision masks in place. Constructing a toggle **writes the model** — it captures
    each wall's asset-declared mask, then applies the requested state (the safe default,
    off, unless told otherwise). Not thread-safe; one toggle per model per session.
    """

    def __init__(self, model: mujoco.MjModel, enabled: bool = DEFAULT_WALLS_ENABLED) -> None:
        """Capture the walls' asset masks and apply the initial state (default off).

        Args:
            model: The compiled model whose cell walls this toggles — the same model a
                cell-collision check will read.
            enabled: Initial wall state; defaults to off per WP-2C-07.

        Raises:
            CellTableInactiveError: If the table geom is absent or already inactive.
        """
        self._model = model
        self._assert_table_active()
        # Capture before the first toggle so activate() can restore the asset's own mask
        # rather than assuming 1/1; a wall already off contributes the fallback instead.
        self._active_masks: dict[str, tuple[int, int]] = {}
        for name in CELL_WALL_GEOMS:
            self._active_masks[name] = self._captured_active_mask(name)
        self.set_enabled(enabled)

    @property
    def walls_active(self) -> bool:
        """Whether all six cell walls are currently collision-active.

        Reuses WP-2A-00's `inactive_cell_walls`: active means the interlock's own
        emptiness of the inactive set, not a private re-derivation.
        """
        return inactive_cell_walls(self._model) == ()

    @property
    def table_active(self) -> bool:
        """Whether the always-active cell table is present and collision-active (③)."""
        return self._geom_is_active(CELL_TABLE_GEOM)

    def activate(self) -> None:
        """Switch all six cell walls into the contact system (the ``--walls`` on state).

        Restores each wall's asset-declared collision mask; a check run after this is no
        longer vacuous. The table is untouched — it was never in the toggled set.
        """
        for name, (contype, conaffinity) in self._active_masks.items():
            self._write_mask(name, contype, conaffinity)

    def deactivate(self) -> None:
        """Switch all six cell walls out of the contact system (the runtime default).

        Leaves the table active (③): only `CELL_WALL_GEOMS` are cleared.
        """
        for name in CELL_WALL_GEOMS:
            self._write_mask(name, _INACTIVE_MASK, _INACTIVE_MASK)

    def set_enabled(self, enabled: bool) -> None:
        """Set the wall state from a boolean — the ``--walls`` toggle itself.

        Args:
            enabled: True activates the six walls, False deactivates them.
        """
        if enabled:
            self.activate()
        else:
            self.deactivate()

    def require_active(self) -> None:
        """Refuse unless all six walls are active, reusing WP-2A-00's assertion.

        This is the precondition a cell-collision check calls before trusting a result:
        with the default-off toggle, a check that skipped activation is refused here, not
        silently passed.

        Raises:
            CellWallsInactiveError: If any of the six cell walls is inactive (WP-2A-00).
        """
        assert_cell_walls_active(self._model)

    def _assert_table_active(self) -> None:
        """Verify the always-active table before the toggle takes over the model (③).

        Raises:
            CellTableInactiveError: If the table geom is absent or collision-inactive.
        """
        if not self._geom_is_active(CELL_TABLE_GEOM):
            raise CellTableInactiveError(
                f"cell table {CELL_TABLE_GEOM!r} is absent or collision-inactive; the "
                "toggle will not operate on a scene whose always-active table is off "
                "(02b §1.2 WP-2C-07 ③)"
            )

    def _captured_active_mask(self, name: str) -> tuple[int, int]:
        """Return the mask to restore on activation for a wall.

        The asset-declared mask when the wall is already active; the fallback when it is
        not (a model handed over deactivated), so activation always yields a live wall.

        Args:
            name: Wall geom name.

        Returns:
            (tuple[int, int]) The (contype, conaffinity) to write on activate.
        """
        geom_id = self._geom_id(name)
        if geom_id < 0:
            return (_ACTIVE_MASK_FALLBACK, _ACTIVE_MASK_FALLBACK)
        contype = int(self._model.geom_contype[geom_id])
        conaffinity = int(self._model.geom_conaffinity[geom_id])
        if contype != 0 and conaffinity != 0:
            return (contype, conaffinity)
        return (_ACTIVE_MASK_FALLBACK, _ACTIVE_MASK_FALLBACK)

    def _write_mask(self, name: str, contype: int, conaffinity: int) -> None:
        """Write a geom's collision masks, if the geom exists.

        Args:
            name: Geom name.
            contype: Contact type bitmask to write.
            conaffinity: Contact affinity bitmask to write.
        """
        geom_id = self._geom_id(name)
        if geom_id < 0:
            return
        self._model.geom_contype[geom_id] = contype
        self._model.geom_conaffinity[geom_id] = conaffinity

    def _geom_is_active(self, name: str) -> bool:
        """Whether a named geom is present and collision-active (both masks non-zero).

        Args:
            name: Geom name.

        Returns:
            (bool) True when present with both masks non-zero.
        """
        geom_id = self._geom_id(name)
        if geom_id < 0:
            return False
        contype = int(self._model.geom_contype[geom_id])
        conaffinity = int(self._model.geom_conaffinity[geom_id])
        return contype != 0 and conaffinity != 0

    def _geom_id(self, name: str) -> int:
        """Resolve a geom name to its id, or -1 when absent.

        Args:
            name: Geom name.

        Returns:
            (int) Geom id, or -1 if the model has no such geom.
        """
        return int(mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_GEOM, name))
