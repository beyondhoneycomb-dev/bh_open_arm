"""The dry-run hard gate is MuJoCo-canonical, never Isaac (`09` FR-SIM-135).

Three backend rules the dry-run must hold:

- **The final hard gate is MuJoCo (tier 1), not Isaac** (FR-SIM-135). Isaac's
  determinism holds only under identical HW + Isaac/PhysX version + seed +
  num_envs, so it is a GPU pre-filter, never the last word before real
  transmission. ``designate_hard_gate`` rejects Isaac as the gate backend.
- **The default backend is MuJoCo, and an unmet Isaac request auto-downgrades
  with a recorded reason** (FR-SIM-102). This reuses WP-0C-01's ``select_backend``,
  which already makes a silent downgrade unrepresentable; the gate binds to
  whatever it resolved.
- **Identification values and DR centres do not cross backends** (FR-SIM-092).
  Isaac ``ImplicitActuatorCfg`` gains (80/4) are neither the MJCF stiff gains nor
  the real values; transplanting a DR centre identified on one backend onto a run
  on another is refused, with the backend tag preserved on the centre.
"""

from __future__ import annotations

from dataclasses import dataclass

from packages.lerobot_robot_openarm_mujoco.backend_selector import (
    Backend,
    BackendSelection,
    select_backend,
)


class IsaacHardGateError(RuntimeError):
    """Raised when Isaac is designated the final hard gate (`09` FR-SIM-135)."""


class CrossBackendTransplantError(RuntimeError):
    """Raised when a DR centre from one backend is used on another (`09` FR-SIM-092)."""


@dataclass(frozen=True)
class HardGate:
    """The backend the dry-run's real-transmission hard gate runs on.

    Construction asserts the gate backend is MuJoCo; an Isaac gate is impossible to
    represent (FR-SIM-135). The recorded ``selection`` keeps the downgrade reason
    visible when an Isaac request was auto-downgraded (FR-SIM-102).

    Attributes:
        selection: The resolved backend selection (backend, version, downgrade).
    """

    selection: BackendSelection

    def __post_init__(self) -> None:
        """Refuse any hard gate not running on the canonical MuJoCo backend."""
        if self.selection.backend is not Backend.MUJOCO:
            raise IsaacHardGateError(
                f"the dry-run hard gate must be MuJoCo (tier-1 canon), not "
                f"{self.selection.backend.value}; Isaac is a GPU pre-filter only "
                "(09 FR-SIM-135)"
            )

    @property
    def backend(self) -> Backend:
        """The gate backend (always MuJoCo)."""
        return self.selection.backend

    @property
    def version(self) -> str:
        """The gate backend's recorded version string."""
        return self.selection.version


def designate_hard_gate(requested: Backend = Backend.MUJOCO) -> HardGate:
    """Resolve a backend and bind it as the dry-run hard gate.

    Defaults to MuJoCo. An Isaac *request* auto-downgrades to MuJoCo when Isaac is
    unavailable (FR-SIM-102). An Isaac request that *does* resolve to Isaac is
    refused as a hard gate — Isaac may pre-filter, but the last gate is MuJoCo
    (FR-SIM-135).

    Args:
        requested: The backend requested for the gate; defaults to MuJoCo.

    Returns:
        (HardGate) The MuJoCo-backed hard gate, carrying any downgrade reason.

    Raises:
        IsaacHardGateError: If the request resolves to Isaac as the gate.
    """
    return HardGate(selection=select_backend(requested=requested))


@dataclass(frozen=True)
class DomainRandomizationCenter:
    """A DR distribution centre tagged with the backend it was identified on.

    Attributes:
        parameter: The randomised parameter's name.
        value: The centre value.
        source_backend: The backend whose identification produced the value.
    """

    parameter: str
    value: float
    source_backend: Backend


def guard_dr_center_transplant(center: DomainRandomizationCenter, run_backend: Backend) -> None:
    """Refuse a DR centre identified on a different backend than the run's.

    Args:
        center: The DR centre, carrying its source backend tag.
        run_backend: The backend the run executes on.

    Raises:
        CrossBackendTransplantError: If the centre's source backend differs from the
            run backend (`09` FR-SIM-092).
    """
    if center.source_backend is not run_backend:
        raise CrossBackendTransplantError(
            f"DR centre for {center.parameter!r} was identified on "
            f"{center.source_backend.value} but the run is on {run_backend.value}; "
            "cross-backend transplant of identification/DR values is forbidden "
            "(09 FR-SIM-092)"
        )
