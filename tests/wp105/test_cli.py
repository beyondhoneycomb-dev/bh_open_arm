"""The torque-ON preflight CLI: exit 0 when admitted, non-zero when startup is refused."""

from __future__ import annotations

import json
from pathlib import Path

from backend.actuation.config import RID9_NO_SEND_MARGIN_SEC, TICK_INTERVAL_SEC
from backend.torque_bringup.cli import main


def _manifest_document(safe_hash: str) -> dict:
    return {
        "safe_gate": {"gate_id": "PG-SAFE-001", "status": "PASS", "artifact_hash": safe_hash},
        "rid_gate": {"gate_id": "PG-RID-001", "status": "PASS", "artifact_hash": "rid-hash"},
        "zero_residual": {"within_tolerance": True},
        "gateway_bypass": {"bypass_count": 0},
        "rid9_send_period_sec": TICK_INTERVAL_SEC,
        "rid9_no_send_margin_sec": RID9_NO_SEND_MARGIN_SEC,
    }


def _write(tmp_path: Path, document: dict) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_preflight_admits_a_complete_manifest(tmp_path: Path) -> None:
    path = _write(tmp_path, _manifest_document(safe_hash="sha256:pass"))
    assert main(["--manifest", str(path)]) == 0


def test_preflight_refuses_missing_safe_hash(tmp_path: Path) -> None:
    path = _write(tmp_path, _manifest_document(safe_hash=""))
    assert main(["--manifest", str(path)]) == 1
