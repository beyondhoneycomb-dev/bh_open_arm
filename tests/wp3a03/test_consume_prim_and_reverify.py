"""WP-3A-03 — CTR-PRIM consumption by reference, and the reverify hook after the freeze.

The contract consumes exactly `CTR-PRIM@v1` (action payload shape, timestamp domain,
error envelope) and restates none of it. The reverify hook renders the frozen mirror
deterministically — the bytes `WP-3A-06` froze — and, now that the mirror is on disk,
confirms it byte-for-byte against the rendered contract, so the typed source and the
frozen artefact cannot diverge.
"""

from __future__ import annotations

import json
from pathlib import Path

import contracts.prim as prim
import contracts.teleop as tel
from contracts.teleop import schema

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = REPO_ROOT / "registry" / "contracts" / "contract_index.json"


def test_consumes_exactly_ctr_prim() -> None:
    """The declared consumed set is CTR-PRIM@v1 — the single upstream this schema reads."""
    assert tel.CONSUMED_CONTRACTS == ("CTR-PRIM@v1",)


def test_action_shape_is_the_ctr_prim_shape_not_a_restatement() -> None:
    """The position widths in the contract are CTR-PRIM's frozen action dims, not re-declared."""
    features = tel.frozen_schema()["action_features"]
    assert isinstance(features, dict)
    assert features["single_arm_position_dim"] == prim.SINGLE_ARM_ACTION_DIM
    assert features["bimanual_position_dim"] == prim.BIMANUAL_ACTION_DIM


def test_error_envelope_is_the_ctr_prim_envelope() -> None:
    """A surfaced teleop error is a CTR-PRIM ErrorEnvelope wrapping a registered OA-* code."""
    envelope = tel.validity_envelope(tel.TeleopValidity.INVALID)
    assert isinstance(envelope, prim.ErrorEnvelope)
    assert envelope is not None and envelope.severity == prim.Severity.ERROR


def test_timestamp_roles_are_ctr_prim_clock_roles() -> None:
    """Both timestamp roles are CTR-PRIM ClockRole members, not a teleop-local clock model."""
    assert isinstance(schema.SOURCE_TS_ROLE, prim.ClockRole)
    assert isinstance(schema.RECEIVE_TS_ROLE, prim.ClockRole)


def test_the_authority_registers_ctr_tel_as_frozen_owned_by_this_wp() -> None:
    """CTR-TEL@v1 is FROZEN in the freeze authority, still owned by WP-3A-03; WP-3A-06 locked it."""
    index = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    row = next(r for r in index["contracts"] if r["contract_id"] == "CTR-TEL@v1")
    assert row["status"] == "FROZEN"
    assert row["owner_wp"] == "WP-3A-03"
    assert row["canonical_hash"] is not None


def test_render_frozen_json_is_deterministic_and_canonical() -> None:
    """The mirror renders identically across calls, with sorted keys and a trailing newline."""
    first = tel.render_frozen_json()
    second = tel.render_frozen_json()
    assert first == second
    assert first.endswith("}\n")
    parsed = json.loads(first)
    assert parsed["contract"] == "CTR-TEL@v1"
    assert parsed["get_action"]["non_blocking"] is True
    assert parsed["ker_slot"]["can_channels"] == 0
    assert parsed["action_features"]["convention"] == "flat"


def test_frozen_schema_carries_every_acceptance_fact() -> None:
    """The mirror captures the plugin, flat features, validity, sync_state and KER facts."""
    body = tel.frozen_schema()
    assert body["plugin"]["vr_teleop_type"] == "openarm_vr"  # type: ignore[index]
    assert body["validity"]["levels"] == {"OK": 0, "STALE": 1, "INVALID": 2}  # type: ignore[index]
    assert body["sync_state"]["verification_only_paths"] == ["cli"]  # type: ignore[index]
    assert body["timestamp_domain"]["source_ts_role"] == "client"  # type: ignore[index]


def test_reverify_confirms_the_frozen_mirror_matches_the_source() -> None:
    """After the freeze the mirror is present and reverify confirms it equals the source."""
    result = tel.reverify(REPO_ROOT)
    assert result.registered
    assert result.status == "FROZEN"
    assert result.owner_wp == "WP-3A-03"
    assert result.mirror_present
    assert result.mirror_matches is True


def test_reverify_would_detect_mirror_drift_once_frozen(tmp_path: Path) -> None:
    """Once the mirror exists, reverify compares it byte-for-byte to the rendered contract."""
    (tmp_path / "contracts" / "teleop").mkdir(parents=True)
    (tmp_path / "registry" / "contracts").mkdir(parents=True)
    (tmp_path / "registry" / "contracts" / "contract_index.json").write_text(
        json.dumps({"contracts": [{"contract_id": "CTR-TEL@v1", "status": "FROZEN"}]}),
        encoding="utf-8",
    )
    mirror = tmp_path / tel.FROZEN_MIRROR_PATH
    mirror.write_text(tel.render_frozen_json(), encoding="utf-8")
    assert tel.reverify(tmp_path).mirror_matches is True
    mirror.write_text(tel.render_frozen_json() + " ", encoding="utf-8")
    assert tel.reverify(tmp_path).mirror_matches is False
