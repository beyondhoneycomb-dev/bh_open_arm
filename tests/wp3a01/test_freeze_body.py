"""The CTR-CAM@v1 reverify hook: a deterministic frozen body, frozen by WP-3A-06.

`WP-3A-01` authored `CTR-CAM@v1` and left it DRAFT (`02b` §5.0b, the chained-ledger
race); `WP-3A-06` froze it after the four other consumers. This hook proves what the
freeze locked is a function of the contract alone — the canonical body is byte-stable —
and that the freeze now holds: the contract is FROZEN in the authority and its mirror is
on disk equal to `canonical_json_text`, so CI-09 reads the same body as a drift guard —
the exact mechanism the committed `tests/wp3a00/test_freeze_lock.py` proves for
`CTR-PRIM@v1`.
"""

from __future__ import annotations

import json
from pathlib import Path

from contracts.camera_registry.canonical import canonical_json_text
from registry.checks import ci_09
from registry.checks.corpus import Corpus

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = REPO_ROOT / "registry" / "contracts" / "contract_index.json"
FROZEN_MIRROR = REPO_ROOT / "contracts" / "camera_registry" / "schema.json"
CONTRACT_ID = "CTR-CAM@v1"


def test_canonical_body_is_deterministic() -> None:
    """The frozen body is byte-identical across calls, so the locked hash is stable."""
    assert canonical_json_text() == canonical_json_text()
    document = json.loads(canonical_json_text())
    assert document["contract"] == CONTRACT_ID
    assert document["consumes"] == "CTR-PRIM@v1"


def test_canonical_body_restates_no_geometry_value() -> None:
    """The body references the geometry field names but restates no resolution/fps number."""
    document = json.loads(canonical_json_text())
    assert document["geometry"]["fields"] == ["width", "height", "fps"]
    assert document["geometry"]["restated_elsewhere"] is False
    assert document["dataset_keys"]["derived_from"].startswith("slot key")


def test_contract_is_frozen_by_wp_3a_06() -> None:
    """CTR-CAM@v1 is FROZEN in the freeze authority — WP-3A-06 locked it, WP-3A-01 owns it."""
    index = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    row = next(record for record in index["contracts"] if record["contract_id"] == CONTRACT_ID)
    assert row["status"] == "FROZEN"
    assert row["owner_wp"] == "WP-3A-01"
    # The locked hash is the content hash of the committed mirror, not a drifted copy.
    assert row["canonical_hash"] == ci_09.content_hash(
        ("contracts/camera_registry/schema.json",), REPO_ROOT
    )


def test_frozen_mirror_is_present_and_matches_the_generator() -> None:
    """After the freeze the mirror is on disk, equals `canonical_json_text`, and CI-09 is clean."""
    assert FROZEN_MIRROR.exists()
    assert FROZEN_MIRROR.read_text(encoding="utf-8") == canonical_json_text()
    result = ci_09.run(Corpus(REPO_ROOT))
    assert [finding for finding in result.findings if finding.req_or_wp == CONTRACT_ID] == []
