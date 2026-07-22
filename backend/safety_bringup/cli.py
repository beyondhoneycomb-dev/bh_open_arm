"""The extended-safety-bring-up CLI: emit the velocity derivation, or run the asset preflight.

Two offline commands, both of which RUN here and must genuinely pass:

  * `derive` — the PG-VEL-001 derivation-basis document (`03` §5.6 evidence ⑨-c/⑨-d): the
    three-way register/catalogue/URDF table per joint, the bootstrap limiter, the proof the
    register is never canon, and the self-approval refusal when the basis URIs point at the
    gate's own result.
  * `preflight` — the offline asset checks: link7 collision coverage in the committed MJCF
    and the injected URDF descriptor, zero octomap symbols in the code tree, and the
    virtual-wall geoms in the injected scene.

Neither command touches the powered arm; the command-following sweep is deferred behind the
fixture hook.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from backend.safety_bringup.collision import (
    assert_link7_collision_in_mjcf,
    assert_link7_collision_in_urdf,
    committed_mjcf_path,
    count_virtual_wall_geoms,
    inject_link7_collision_urdf,
    inject_virtual_walls,
)
from backend.safety_bringup.detection import scan_octomap_symbols
from backend.safety_bringup.velocity import (
    assert_derivation_basis_not_self,
    assert_register_never_canon,
    bootstrap_limiter_rad_s,
    physical_canon_rad_s,
    three_way_table,
)

EXIT_OK = 0
EXIT_FAILED = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
INJECTED_URDF = REPO_ROOT / "sim" / "safety" / "urdf" / "openarm_link7_collision.urdf"
INJECTED_WALLS = REPO_ROOT / "sim" / "safety" / "scene" / "virtual_walls.xml"

# The physical sources the velocity derivation rests on (`03` §5.6.0 ①). A basis URI must be
# one of these, never the gate's own result record — the self-approval refusal reads this.
DERIVATION_BASIS_URIS = (
    "docs/spec/03-모터-설정.md#2.1",
    "docs/spec/03-모터-설정.md#trap-2",
    "backend/can/rid/motor_limits.py#MOTOR_LIMIT_PARAMS",
    "https://docs.openarm.dev/hardware/openarm-2.0/motor/",
)
DERIVATION_RESULT_RECORD_URI = "registry/build/evidence/CG-1-06i/"

# The code trees the octomap scan covers, and the paths whose octomap mentions are data
# (this package names the deprecated symbols as constants and checker logic).
OCTOMAP_SCAN_ROOTS = (
    REPO_ROOT / "backend",
    REPO_ROOT / "packages",
    REPO_ROOT / "sim",
    REPO_ROOT / "contracts",
    REPO_ROOT / "ops",
    REPO_ROOT / "dashboard",
)
OCTOMAP_SCAN_EXCLUDE = (REPO_ROOT / "backend" / "safety_bringup",)


def _derivation_document() -> dict[str, Any]:
    """Build the velocity derivation document (the ⑨-c/⑨-d evidence).

    Returns:
        (dict[str, Any]) The three-way table, bootstrap limiter, and basis provenance.

    Raises:
        DerivationSelfApprovalError: If the register is any joint's canon, or the basis
            points at the gate's own result.
    """
    table = three_way_table()
    assert_register_never_canon(table)
    assert_derivation_basis_not_self(DERIVATION_BASIS_URIS, DERIVATION_RESULT_RECORD_URI)
    rows = [
        {
            "joint": row.joint_index + 1,
            "register_vmax_rad_s": row.register_vmax_rad_s,
            "catalogue_no_load_rad_s": row.catalogue_no_load_rad_s,
            "urdf_velocity_rad_s": row.urdf_velocity_rad_s,
            "canon_rad_s": row.canon_rad_s,
            "canon_source": row.canon_source.value,
            "register_is_canon": row.register_is_canon,
        }
        for row in table
    ]
    return {
        "gate": "PG-VEL-001",
        "three_way_table": rows,
        "physical_canon_rad_s": list(physical_canon_rad_s()),
        "bootstrap_limiter_rad_s": list(bootstrap_limiter_rad_s()),
        "derivation_basis_uris": list(DERIVATION_BASIS_URIS),
        "register_is_never_canon": True,
        "note": (
            "derived by arithmetic from datasheet/URDF/catalogue; the command-following "
            "sweep is deferred to the real fixture (⑨-a/⑨-b) and never asserted here"
        ),
    }


def _run_derive() -> int:
    """Emit the velocity derivation document, or report why it is FAIL_BLOCKING.

    Returns:
        (int) 0 on success, 1 when the derivation is refused.
    """
    try:
        document = _derivation_document()
    except Exception as failure:  # noqa: BLE001 — the failure message is the CLI output
        print(f"PG-VEL-001 derivation FAILED: {failure}", file=sys.stderr)
        return EXIT_FAILED
    print(json.dumps(document, ensure_ascii=False, indent=2))
    return EXIT_OK


def _run_preflight() -> int:
    """Run the offline asset checks, injecting the sim/safety variants if absent.

    Returns:
        (int) 0 when every asset check passes, 1 otherwise.
    """
    try:
        mjcf_bodies = assert_link7_collision_in_mjcf(committed_mjcf_path())
        if not INJECTED_URDF.exists():
            inject_link7_collision_urdf(INJECTED_URDF)
        urdf_link = assert_link7_collision_in_urdf(INJECTED_URDF)
        if not INJECTED_WALLS.exists():
            inject_virtual_walls(INJECTED_WALLS)
        wall_count = count_virtual_wall_geoms(INJECTED_WALLS)
        octomap = scan_octomap_symbols(OCTOMAP_SCAN_ROOTS, OCTOMAP_SCAN_EXCLUDE)
    except Exception as failure:  # noqa: BLE001 — the failure message is the CLI output
        print(f"safety preflight FAILED: {failure}", file=sys.stderr)
        return EXIT_FAILED
    if octomap:
        for reference in octomap:
            print(
                f"octomap symbol {reference.symbol!r} at {reference.path}:{reference.line}",
                file=sys.stderr,
            )
        print(
            "safety preflight FAILED: octomap pipeline is deprecated (12 FR-SAF-012)",
            file=sys.stderr,
        )
        return EXIT_FAILED
    print(
        json.dumps(
            {
                "mjcf_link7_bodies": list(mjcf_bodies),
                "urdf_link7_link": urdf_link,
                "virtual_wall_geoms": wall_count,
                "octomap_symbols": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    """Run the extended-safety-bring-up CLI.

    Args:
        argv: Command-line arguments; defaults to `sys.argv`.

    Returns:
        (int) 0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(prog="oa-safety-bringup", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("derive", help="emit the PG-VEL-001 velocity derivation document")
    subparsers.add_parser("preflight", help="run the offline collision/octomap asset checks")
    args = parser.parse_args(argv)

    if args.command == "derive":
        return _run_derive()
    return _run_preflight()


if __name__ == "__main__":
    raise SystemExit(main())
