"""WP-3D-04: the store persists on disk and refuses an incompatible generation.

A lineage store outlives one process, so it must reopen from a file and answer the
same reverse query. It also stamps its schema generation and refuses to reopen a
file whose generation differs, rather than misreading old bytes into a false answer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.dataset.lineage import LineageError, LineageStore
from backend.dataset.lineage.store import _SCHEMA_META_TABLE, _SCHEMA_VERSION_KEY
from tests.wp3d04._support import fixture_record


def test_records_survive_a_close_and_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "lineage.db"
    record = fixture_record((0, 1, 2), "/runs/a", 1000)
    with LineageStore(db_path) as store:
        store.record(record)

    with LineageStore(db_path) as reopened:
        hits = reopened.checkpoints_for_episode(record.dataset_content_hash, 1)
        assert [ref.output_dir for ref in hits] == ["/runs/a"]
        restored = reopened.get("/runs/a", 1000)
        assert restored is not None
        assert restored.episodes == (0, 1, 2)
        assert restored.channels == record.channels
        assert restored.encoder_settings == record.encoder_settings


def test_reopening_an_incompatible_generation_is_refused(tmp_path: Path) -> None:
    db_path = tmp_path / "lineage.db"
    with LineageStore(db_path) as store:
        store.record(fixture_record((0,), "/runs/a", 1000))
        store.mConnection.execute(
            f"UPDATE {_SCHEMA_META_TABLE} SET value = '999' WHERE key = ?",
            (_SCHEMA_VERSION_KEY,),
        )
        store.mConnection.commit()

    with pytest.raises(LineageError, match="schema version"):
        LineageStore(db_path)
