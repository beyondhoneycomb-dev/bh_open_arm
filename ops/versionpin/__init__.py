"""WP-OPS-03 — version pin and rollback.

The no-auto-upgrade contract of U-3 / `09` FR-SIM-102, made enforceable:

  * `manifest` — the pin manifest distribution and its Isaac-pin assertion;
  * `blocker` — the auto-upgrade blocker that rejects range specifiers;
  * `reporter` — the runtime version reporter (LeRobot SHA, MuJoCo, Isaac Sim/Lab,
    physics backend);
  * `rollback` — the rollback procedure and its rehearsal.
"""

from __future__ import annotations

from ops.versionpin.blocker import (
    Classification,
    SpecifierVerdict,
    classify_specifier,
    rejected,
    scan_manifest,
    scan_specifiers,
)
from ops.versionpin.manifest import (
    IsaacPinReport,
    ManifestReport,
    assert_isaac_pin,
    load_manifest,
    validate_manifest,
)
from ops.versionpin.reporter import RuntimeVersions, report
from ops.versionpin.rollback import GateCheck, RollbackReport, gate_checks, rehearse_rollback

__all__ = [
    "Classification",
    "GateCheck",
    "IsaacPinReport",
    "ManifestReport",
    "RollbackReport",
    "RuntimeVersions",
    "SpecifierVerdict",
    "assert_isaac_pin",
    "classify_specifier",
    "gate_checks",
    "load_manifest",
    "rehearse_rollback",
    "rejected",
    "report",
    "scan_manifest",
    "scan_specifiers",
    "validate_manifest",
]
