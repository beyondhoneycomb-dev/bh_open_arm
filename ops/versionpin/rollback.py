"""Rollback procedure and rehearsal (WP-OPS-03 acceptance ②).

The procedure a version rollback follows:

  1. Select the prior manifest generation (in production, the previous committed
     revision of manifest.yaml; in the rehearsal, a fixture that is explicitly a
     prior generation, since generation 1 is the first freeze and has no genuine
     predecessor to fabricate).
  2. Confirm the prior is exactly one generation back (`prior.generation ==
     current.generation - 1`) — a rollback skips no generation.
  3. Re-run the pin-contract gate on the prior manifest. These are the gate jobs a
     version change can affect (WP-ENV-03 `pin-verify`): the manifest still validates,
     the auto-upgrade blocker still finds no range operator, the runtime reporter still
     produces a complete four-field report, and the Isaac pin still asserts Sim 5.1 /
     Lab 2.3.x. The broader CI jobs (lint, ownership, ledger) are re-run by the CI
     system on the manifest edit itself; this rehearsal exercises the subset a pin
     rollback moves.
  4. Confirm roll-forward: the same gate passes on the current manifest, so the rollback
     is reversible.

`rehearse_rollback` returns every check's verdict, so a rollback to a generation that
violates the contract (a range operator, an auto-upgraded Isaac pin) is caught rather
than rubber-stamped — which is what proves the gate re-pass is a real gate and not a
formality.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ops.versionpin.blocker import rejected, scan_manifest
from ops.versionpin.manifest import assert_isaac_pin, validate_manifest
from ops.versionpin.reporter import read_lerobot_sha, read_mujoco_version, report


@dataclass(frozen=True)
class GateCheck:
    """One pin-contract gate job's verdict on a manifest.

    Attributes:
        name: The gate job's name.
        passed: Whether the manifest passed it.
        detail: A one-line explanation; empty when passed with nothing to note.
    """

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class RollbackReport:
    """The verdict of rehearsing a one-generation rollback.

    Attributes:
        ok: True when the prior passes the gate, the roll-forward passes, and the
            generation step is exactly one.
        from_generation: The current generation rolled back from.
        to_generation: The prior generation rolled back to.
        prior_checks: The gate verdicts on the prior manifest.
        forward_checks: The gate verdicts on the current manifest.
    """

    ok: bool
    from_generation: int
    to_generation: int
    prior_checks: tuple[GateCheck, ...]
    forward_checks: tuple[GateCheck, ...]


def gate_checks(
    manifest: dict[str, Any],
    lerobot_sha_probe: Callable[[], str] = read_lerobot_sha,
    mujoco_probe: Callable[[], str] = read_mujoco_version,
) -> tuple[GateCheck, ...]:
    """Run the pin-contract gate jobs on a manifest.

    Args:
        manifest: A parsed manifest mapping.
        lerobot_sha_probe: Reporter probe; injectable for offline determinism.
        mujoco_probe: Reporter probe; injectable for offline determinism.

    Returns:
        (tuple[GateCheck, ...]) One verdict per gate job.
    """
    structure = validate_manifest(manifest)
    ranges = rejected(scan_manifest(manifest))
    isaac = assert_isaac_pin(manifest)
    versions = report(manifest, lerobot_sha_probe=lerobot_sha_probe, mujoco_probe=mujoco_probe)

    return (
        GateCheck("manifest-valid", structure.ok, "; ".join(structure.problems)),
        GateCheck(
            "no-auto-upgrade",
            not ranges,
            "; ".join(f"{v.where}: {v.reason}" for v in ranges),
        ),
        GateCheck(
            "runtime-report-complete",
            versions.complete,
            "" if versions.complete else "a version field is empty",
        ),
        GateCheck("isaac-pin-5.1/2.3.x", isaac.ok, "; ".join(isaac.problems)),
    )


def rehearse_rollback(
    current: dict[str, Any],
    prior: dict[str, Any],
    lerobot_sha_probe: Callable[[], str] = read_lerobot_sha,
    mujoco_probe: Callable[[], str] = read_mujoco_version,
) -> RollbackReport:
    """Rehearse a one-generation rollback and re-run the gate on both ends (acceptance ②).

    Args:
        current: The current manifest (generation N).
        prior: The prior manifest (generation N-1).
        lerobot_sha_probe: Reporter probe; injectable for offline determinism.
        mujoco_probe: Reporter probe; injectable for offline determinism.

    Returns:
        (RollbackReport) The generation step and both ends' gate verdicts.
    """
    current_gen = _generation(current)
    prior_gen = _generation(prior)

    prior_checks = gate_checks(prior, lerobot_sha_probe, mujoco_probe)
    forward_checks = gate_checks(current, lerobot_sha_probe, mujoco_probe)

    step_ok = prior_gen == current_gen - 1
    ok = step_ok and all(c.passed for c in prior_checks) and all(c.passed for c in forward_checks)

    return RollbackReport(
        ok=ok,
        from_generation=current_gen,
        to_generation=prior_gen,
        prior_checks=prior_checks,
        forward_checks=forward_checks,
    )


def _generation(manifest: dict[str, Any]) -> int:
    """Return a manifest's declared generation, or -1 when absent or non-integer."""
    value = manifest.get("generation")
    return value if isinstance(value, int) else -1
