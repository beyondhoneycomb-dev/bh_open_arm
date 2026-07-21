"""Runtime version reporter (WP-OPS-03 acceptance ③, 09 FR-SIM-102).

Emits the four fields FR-SIM-102 requires a rollout/episode to record: the LeRobot
commit SHA, the MuJoCo version, the Isaac Sim/Lab pin, and the physics backend. Each
comes from its single source of truth:

  * LeRobot SHA — read as data from deps/lerobot.pin (WP-ENV-01 owns it; not duplicated);
  * MuJoCo — the installed distribution's version via importlib.metadata (WP-ENV-02's
    lock resolution, read live rather than copied into the manifest);
  * Isaac Sim/Lab — the declared pins from the manifest (Isaac is not installed on the
    default backend host, so the pin is the recorded policy, not an introspected import);
  * physics backend — the default backend's physics (MuJoCo's own solver), from the
    manifest.

The two resolved probes are injectable so the reporter runs deterministically offline;
by default they read the real environment, which is what makes acceptance ③ a live run
rather than a fixture. A probe that cannot resolve records an explicit "unavailable"
marker — never a silent empty field.
"""

from __future__ import annotations

import importlib.metadata
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ops.versionpin.manifest import load_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
LEROBOT_PIN_PATH = REPO_ROOT / "deps" / "lerobot.pin"

UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class RuntimeVersions:
    """The four version fields FR-SIM-102 records for a rollout.

    Attributes:
        lerobot_sha: The pinned LeRobot commit SHA (deps/lerobot.pin).
        mujoco: The installed MuJoCo version, or an unavailable marker.
        isaac_sim: The declared Isaac Sim pin (`5.1.0`).
        isaac_lab: The declared Isaac Lab pin (`2.3.x`).
        physics_backend: The default backend's physics engine.
    """

    lerobot_sha: str
    mujoco: str
    isaac_sim: str
    isaac_lab: str
    physics_backend: str

    @property
    def complete(self) -> bool:
        """Whether every field carries a non-empty value (acceptance ③)."""
        return all(str(value).strip() for value in asdict(self).values())

    def as_dict(self) -> dict[str, str]:
        """Return the report as the four-field mapping FR-SIM-102 records.

        Isaac Sim and Lab are joined into the single `isaac_sim_lab` field the spec
        names, while the dataclass keeps them apart for precise assertions.

        Returns:
            (dict[str, str]) `{lerobot_sha, mujoco, isaac_sim_lab, physics_backend}`.
        """
        return {
            "lerobot_sha": self.lerobot_sha,
            "mujoco": self.mujoco,
            "isaac_sim_lab": f"{self.isaac_sim} / {self.isaac_lab}",
            "physics_backend": self.physics_backend,
        }


def read_lerobot_sha(path: Path = LEROBOT_PIN_PATH) -> str:
    """Read the pinned LeRobot commit SHA from the WP-ENV-01 pin file.

    Args:
        path: Path to deps/lerobot.pin.

    Returns:
        (str) The commit SHA, or an unavailable marker when it cannot be read.
    """
    try:
        loaded: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return f"lerobot ({UNAVAILABLE})"
    sha = loaded.get("commit_sha") if isinstance(loaded, dict) else None
    return str(sha) if sha else f"lerobot ({UNAVAILABLE})"


def read_mujoco_version() -> str:
    """Read the installed MuJoCo distribution version via importlib.metadata.

    Uses distribution metadata rather than importing the C extension, so the reader
    stays light and needs no GPU. On the default backend host MuJoCo is installed and
    this returns its real version (acceptance ③).

    Returns:
        (str) The MuJoCo version, or an unavailable marker when not installed.
    """
    try:
        return importlib.metadata.version("mujoco")
    except importlib.metadata.PackageNotFoundError:
        return f"mujoco ({UNAVAILABLE})"


def report(
    manifest: dict[str, Any] | None = None,
    lerobot_sha_probe: Callable[[], str] = read_lerobot_sha,
    mujoco_probe: Callable[[], str] = read_mujoco_version,
) -> RuntimeVersions:
    """Build the runtime version report (acceptance ③).

    Args:
        manifest: A parsed manifest; loaded from disk when omitted.
        lerobot_sha_probe: Probe for the LeRobot SHA; injectable for offline determinism.
        mujoco_probe: Probe for the MuJoCo version; injectable for offline determinism.

    Returns:
        (RuntimeVersions) The four FR-SIM-102 fields.
    """
    resolved = manifest if manifest is not None else load_manifest()
    pins = resolved.get("pins", {})
    sim = pins.get("isaac_sim", {}) if isinstance(pins, dict) else {}
    lab = pins.get("isaac_lab", {}) if isinstance(pins, dict) else {}
    physics = pins.get("physics_backend", {}) if isinstance(pins, dict) else {}

    return RuntimeVersions(
        lerobot_sha=lerobot_sha_probe(),
        mujoco=mujoco_probe(),
        isaac_sim=str(sim.get("version", "")) if isinstance(sim, dict) else "",
        isaac_lab=str(lab.get("version", "")) if isinstance(lab, dict) else "",
        physics_backend=str(physics.get("default", "")) if isinstance(physics, dict) else "",
    )
