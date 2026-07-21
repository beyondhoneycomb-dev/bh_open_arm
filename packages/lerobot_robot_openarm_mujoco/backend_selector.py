"""Backend selection: MuJoCo is the default, canonical stage-1 backend (WP-0C-01).

`09` FR-SIM-102 fixes MuJoCo as the default backend and requires that an Isaac
request which cannot be met is auto-downgraded to MuJoCo, with the chosen backend
and version recorded -- never silently. This module makes the downgrade
impossible to hide: a `BackendSelection` that reports a downgrade must carry a
non-empty reason and must have actually changed the backend, so a "silent
downgrade" has no valid representation.

Isaac availability and version, and the MuJoCo version, are read through injected
probes so the auto-downgrade path is testable without a GPU (`09` FR-SIM-102): the
Isaac-unavailable fixture is just a probe that reports unavailable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class Backend(Enum):
    """A simulation backend on the shared OpenArm Robot ABC (`09` FR-SIM-097)."""

    MUJOCO = "mujoco"
    ISAAC = "isaac"


@dataclass(frozen=True)
class IsaacAvailability:
    """Whether the Isaac backend can run here, and why not when it cannot.

    Attributes:
        available: Whether Isaac Sim can be used.
        reason: When unavailable, the recorded cause; empty when available.
    """

    available: bool
    reason: str


@dataclass(frozen=True)
class BackendSelection:
    """The chosen backend, its version, and whether a downgrade occurred.

    Attributes:
        backend: The backend that was selected and will run.
        version: The selected backend's version string (`09` FR-SIM-102 recording).
        requested: The backend that was asked for.
        downgraded: Whether the request could not be met and was downgraded.
        reason: Why the downgrade happened; empty exactly when not downgraded.
    """

    backend: Backend
    version: str
    requested: Backend
    downgraded: bool
    reason: str

    def __post_init__(self) -> None:
        """Reject any selection that would hide a downgrade (`09` FR-SIM-102)."""
        if self.downgraded and not self.reason:
            raise ValueError("a downgrade must record its reason; a silent downgrade is forbidden")
        if self.downgraded and self.backend is self.requested:
            raise ValueError("a downgrade must select a backend other than the requested one")
        if not self.downgraded and self.backend is not self.requested:
            raise ValueError("a non-downgrade selection must return the requested backend")


def mujoco_version() -> str:
    """Return the installed MuJoCo version string, e.g. `mujoco 3.10`."""
    import mujoco

    return f"mujoco {mujoco.__version__}"


def probe_isaac() -> IsaacAvailability:
    """Probe whether the Isaac Sim GPU backend can run in this environment.

    Isaac is the stage-2 GPU backend; it needs the `isaacsim` runtime present.
    When the runtime cannot be imported, Isaac is unavailable and the reason is
    recorded so the downgrade is never silent (`09` FR-SIM-102).

    Returns:
        (IsaacAvailability) Availability and, when unavailable, the cause.
    """
    try:
        import isaacsim  # noqa: F401  # probe only; the module is never used here
    except ImportError as error:
        return IsaacAvailability(
            available=False,
            reason=f"Isaac Sim runtime not importable ({type(error).__name__}: {error})",
        )
    return IsaacAvailability(available=True, reason="")


def isaac_version() -> str:
    """Return the installed Isaac Sim version string, or a marker if unversioned."""
    try:
        import isaacsim

        return f"isaacsim {getattr(isaacsim, '__version__', 'unknown')}"
    except ImportError:
        return "isaacsim (unavailable)"


def select_backend(
    requested: Backend = Backend.MUJOCO,
    isaac_probe: Callable[[], IsaacAvailability] = probe_isaac,
    mujoco_version_probe: Callable[[], str] = mujoco_version,
    isaac_version_probe: Callable[[], str] = isaac_version,
) -> BackendSelection:
    """Select a backend, defaulting to MuJoCo and auto-downgrading Isaac if needed.

    The default request is MuJoCo, the stage-1 canonical backend (`09` FR-SIM-102),
    which is always available here. An Isaac request is honoured only when the probe
    reports it available; otherwise it is downgraded to MuJoCo with the reason
    recorded, so no downgrade is silent.

    Args:
        requested: The backend to try for; defaults to MuJoCo.
        isaac_probe: Isaac availability probe (injectable for the unavailable fixture).
        mujoco_version_probe: MuJoCo version reader.
        isaac_version_probe: Isaac version reader.

    Returns:
        (BackendSelection) The resolved backend, its version, and downgrade status.
    """
    if requested is Backend.MUJOCO:
        return BackendSelection(
            backend=Backend.MUJOCO,
            version=mujoco_version_probe(),
            requested=Backend.MUJOCO,
            downgraded=False,
            reason="",
        )

    availability = isaac_probe()
    if availability.available:
        return BackendSelection(
            backend=Backend.ISAAC,
            version=isaac_version_probe(),
            requested=Backend.ISAAC,
            downgraded=False,
            reason="",
        )
    return BackendSelection(
        backend=Backend.MUJOCO,
        version=mujoco_version_probe(),
        requested=Backend.ISAAC,
        downgraded=True,
        reason=(
            "Isaac requested but unavailable, auto-downgraded to MuJoCo (09 FR-SIM-102): "
            f"{availability.reason}"
        ),
    )
