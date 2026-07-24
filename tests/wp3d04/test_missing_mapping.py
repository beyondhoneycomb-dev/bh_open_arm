"""WP-3D-04 negative branch: a missing lineage mapping is FAIL_BLOCKING.

Two guards must hold. `record()` refuses a run with no episodes at write time, so a
hole cannot enter through the API. `verify_mappings()` is the after-the-fact scan
that FIRES when a run has no episode mapping — the case that can only arise from
external tampering with the file. A green run leaves the scan empty; the fault
injection must make it non-empty.
"""

from __future__ import annotations

import pytest

from backend.dataset.lineage import LineageError, LineageStore
from backend.dataset.lineage.constants import MEMORY_DATABASE, RUN_TABLE
from tests.wp3d04._support import fixture_record


def test_recording_with_no_episodes_is_refused_at_write_time() -> None:
    with LineageStore(MEMORY_DATABASE) as store, pytest.raises(LineageError, match="FAIL_BLOCKING"):
        store.record(fixture_record((), "/runs/a", 1000))


def test_a_healthy_store_has_no_missing_mappings() -> None:
    with LineageStore(MEMORY_DATABASE) as store:
        store.record(fixture_record((0, 1), "/runs/a", 1000))
        store.record(fixture_record((2,), "/runs/b", 2000))
        assert store.verify_mappings() == ()


def test_verify_fires_on_a_tampered_run_with_no_episode_rows() -> None:
    with LineageStore(MEMORY_DATABASE) as store:
        store.record(fixture_record((0, 1), "/runs/good", 1000))
        # Inject a run row directly, bypassing record(), so it has no run_episode
        # rows — the exact hole verify_mappings() exists to catch.
        store.mConnection.execute(
            f"""
            INSERT INTO {RUN_TABLE} (
                repo_id, dataset_content_hash, revision, stats_hash,
                use_velocity_and_torque, state_dim, encoder_settings,
                channel_selection, output_dir, step
            ) VALUES ('r', 'h', 'rev', 's', 1, 48, '{{}}', '{{}}', '/runs/orphan', 3000)
            """
        )
        store.mConnection.commit()

        violations = store.verify_mappings()
        assert len(violations) == 1
        assert "/runs/orphan@3000" in violations[0]
        assert "FAIL_BLOCKING" in violations[0]
