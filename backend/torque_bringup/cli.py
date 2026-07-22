"""The torque-ON preflight: load a startup manifest and refuse the door if it fails.

`02a` §7 makes startup *refused* when the PG-SAFE-001 PASS hash is undeclared, and this is
the entry point that enforces it. It reads a startup manifest, runs the four-precondition
gate, and exits non-zero on refusal — the offline, machine-checkable form of "this WP does
not exist without PG-SAFE-001". It never engages torque; engaging is the hardware path,
deferred behind this gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from backend.actuation.config import RID9_NO_SEND_MARGIN_SEC
from backend.torque_bringup.preconditions import (
    GatePass,
    GatewayBypassPrecondition,
    TorqueOnManifest,
    TorqueOnRefusedError,
    ZeroResidualPrecondition,
    assert_torque_on_allowed,
)

EXIT_OK = 0
EXIT_REFUSED = 1


def manifest_from_document(document: dict[str, Any]) -> TorqueOnManifest:
    """Build a startup manifest from a loaded mapping.

    Args:
        document: The parsed manifest document.

    Returns:
        (TorqueOnManifest) The manifest the preflight gate reads.
    """

    def gate(key: str) -> GatePass:
        raw = document[key]
        return GatePass(
            gate_id=str(raw["gate_id"]),
            status=str(raw["status"]),
            artifact_hash=str(raw.get("artifact_hash", "")),
        )

    return TorqueOnManifest(
        safe_gate=gate("safe_gate"),
        rid_gate=gate("rid_gate"),
        zero_residual=ZeroResidualPrecondition(
            within_tolerance=bool(document["zero_residual"]["within_tolerance"])
        ),
        gateway_bypass=GatewayBypassPrecondition(
            bypass_count=int(document["gateway_bypass"]["bypass_count"])
        ),
        rid9_send_period_sec=float(document["rid9_send_period_sec"]),
        rid9_no_send_margin_sec=float(
            document.get("rid9_no_send_margin_sec", RID9_NO_SEND_MARGIN_SEC)
        ),
    )


def main(argv: list[str] | None = None) -> int:
    """Run the torque-ON preflight over a startup manifest.

    Args:
        argv: Command-line arguments; defaults to `sys.argv`.

    Returns:
        (int) 0 when torque-ON is admitted, 1 when it is refused.
    """
    parser = argparse.ArgumentParser(prog="oa-torque-preflight", description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="startup manifest JSON")
    args = parser.parse_args(argv)

    document = json.loads(args.manifest.read_text(encoding="utf-8"))
    try:
        assert_torque_on_allowed(manifest_from_document(document))
    except TorqueOnRefusedError as refusal:
        print(f"torque-ON REFUSED: {refusal}", file=sys.stderr)
        return EXIT_REFUSED
    print("torque-ON admitted: four preconditions clear")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
