"""Load, validate, and interrogate the WP-OPS-03 pin manifest.

Stdlib + pyyaml only, so the light lane validates the manifest without the robot
stack. The manifest (ops/versionpin/manifest.yaml) is the pin manifest distribution:
it declares the version-contract pins U-3 freezes (Isaac Sim/Lab) and references the
upstream-owned pins (LeRobot SHA, MuJoCo) as data rather than duplicating them.

Two guarantees this module enforces:

  * structure — a `contract_version`, an integer `generation`, and a `pins` mapping
    carrying the four pin sites (`09` FR-SIM-102 records backend + Isaac Sim/Lab
    version + physics backend);
  * the Isaac pin — `assert_isaac_pin` is WP-OPS-03 acceptance ④: the live pins are
    Sim 5.1 / Lab 2.3.x, their specs are exact (no auto-upgrade), and the manifest
    records the forbidden 6.0/Newton/3.0-beta upgrade targets.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ops.versionpin.blocker import Classification, classify_specifier

MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.yaml"

ISAAC_SIM_MINOR = (5, 1)
ISAAC_LAB_MINOR = (2, 3)

_REQUIRED_PINS = ("lerobot", "mujoco", "isaac_sim", "isaac_lab", "physics_backend")


@dataclass(frozen=True)
class ManifestReport:
    """The verdict of validating the pin manifest.

    Attributes:
        ok: True when the manifest is well-formed.
        problems: One line per structural defect; empty when `ok`.
        contract_version: The declared contract generation, echoed for callers.
        generation: The declared manifest generation, echoed for rollback.
    """

    ok: bool
    problems: tuple[str, ...]
    contract_version: int
    generation: int


@dataclass(frozen=True)
class IsaacPinReport:
    """The verdict of asserting the Isaac pin (acceptance ④).

    Attributes:
        ok: True when the Isaac pin is Sim 5.1 / Lab 2.3.x with exact specs.
        problems: One line per violation; empty when `ok`.
        isaac_sim: The declared Isaac Sim version.
        isaac_lab: The declared Isaac Lab version.
    """

    ok: bool
    problems: tuple[str, ...]
    isaac_sim: str
    isaac_lab: str


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    """Parse the pin manifest document.

    Args:
        path: Path to the manifest YAML.

    Returns:
        (dict[str, Any]) The parsed mapping.

    Raises:
        TypeError: When the document does not parse to a mapping.
    """
    loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{path} did not parse to a mapping")
    return loaded


def validate_manifest(manifest: dict[str, Any]) -> ManifestReport:
    """Validate the manifest's structure (not its pin values — see `assert_isaac_pin`).

    Args:
        manifest: A parsed manifest mapping.

    Returns:
        (ManifestReport) Verdict with per-defect problem lines.
    """
    problems: list[str] = []

    contract_version = manifest.get("contract_version")
    if not isinstance(contract_version, int):
        problems.append("contract_version is missing or not an integer")
        contract_version = -1

    generation = manifest.get("generation")
    if not isinstance(generation, int):
        problems.append("generation is missing or not an integer")
        generation = -1

    pins = manifest.get("pins")
    if not isinstance(pins, dict):
        problems.append("pins is missing or not a mapping")
    else:
        for name in _REQUIRED_PINS:
            if name not in pins:
                problems.append(f"pins is missing required pin: {name}")

    return ManifestReport(
        ok=not problems,
        problems=tuple(problems),
        contract_version=contract_version,
        generation=generation,
    )


def parse_minor(version_or_spec: str) -> tuple[int, int]:
    """Extract the `(major, minor)` line from a version or exact spec.

    Strips a leading `==` and reads the first two dotted components as integers, so
    `5.1.0`, `==5.1.0`, `2.3.x`, and `==2.3.*` all resolve to their minor line.

    Args:
        version_or_spec: A version string or exact specifier.

    Returns:
        (tuple[int, int]) The major and minor numbers.

    Raises:
        ValueError: When the first two components are not integers.
    """
    text = version_or_spec.strip().lstrip("=").strip()
    parts = text.split(".")
    if len(parts) < 2:
        raise ValueError(f"cannot read a minor line from {version_or_spec!r}")
    return int(parts[0]), int(parts[1])


def assert_isaac_pin(manifest: dict[str, Any]) -> IsaacPinReport:
    """Assert the Isaac pin is Sim 5.1 / Lab 2.3.x with no auto-upgrade (acceptance ④).

    Four checks, each of which a fixture can violate:

      * Isaac Sim resolves to the 5.1 minor line;
      * Isaac Lab resolves to the 2.3 minor line;
      * both declared specs classify EXACT (a range spec would let a resolver climb
        off the pinned line — the auto-upgrade the contract forbids);
      * the manifest records at least one forbidden upgrade target, so the ban on
        6.0/Newton/3.0-beta is documented rather than implied.

    Args:
        manifest: A parsed manifest mapping.

    Returns:
        (IsaacPinReport) Verdict with per-violation problem lines.
    """
    problems: list[str] = []
    pins = manifest.get("pins", {})
    sim = pins.get("isaac_sim", {}) if isinstance(pins, dict) else {}
    lab = pins.get("isaac_lab", {}) if isinstance(pins, dict) else {}
    sim_version = str(sim.get("version", "")) if isinstance(sim, dict) else ""
    lab_version = str(lab.get("version", "")) if isinstance(lab, dict) else ""

    _check_minor(problems, "Isaac Sim", sim_version, ISAAC_SIM_MINOR)
    _check_minor(problems, "Isaac Lab", lab_version, ISAAC_LAB_MINOR)

    for label, body in (("isaac_sim", sim), ("isaac_lab", lab)):
        spec = str(body.get("spec", "")) if isinstance(body, dict) else ""
        verdict = classify_specifier(spec, where=f"pins.{label}")
        if verdict.classification is not Classification.EXACT:
            problems.append(
                f"{label} spec {spec!r} is not exact: {verdict.reason} — auto-upgrade is possible"
            )

    forbidden = manifest.get("forbidden_upgrades")
    if not isinstance(forbidden, list) or not forbidden:
        problems.append(
            "forbidden_upgrades is empty; the 6.0/Newton/3.0-beta upgrade ban is undocumented"
        )

    return IsaacPinReport(
        ok=not problems,
        problems=tuple(problems),
        isaac_sim=sim_version,
        isaac_lab=lab_version,
    )


def _check_minor(problems: list[str], label: str, version: str, expected: tuple[int, int]) -> None:
    """Append a problem when `version` does not sit on the `expected` minor line.

    Args:
        problems: The accumulator to append to.
        label: Human label for the pin, e.g. `Isaac Sim`.
        version: The declared version string.
        expected: The required `(major, minor)` line.
    """
    if not version:
        problems.append(f"{label} version is missing")
        return
    try:
        minor = parse_minor(version)
    except ValueError as error:
        problems.append(f"{label} version {version!r} is unparseable: {error}")
        return
    if minor != expected:
        want = f"{expected[0]}.{expected[1]}"
        got = f"{minor[0]}.{minor[1]}"
        problems.append(
            f"{label} pin {version!r} is on minor {got}, not the pinned {want} line — auto-upgrade"
        )
