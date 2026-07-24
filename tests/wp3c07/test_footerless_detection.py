"""WP-3C-07 ①: a footerless parquet is detected — from a genuine SIGKILL, and the
detector is not vacuous.

`02b` §7 WP-3C-07 ①. The fault is not simulated at the file level: `inject_sigkill`
spawns a real subprocess writing a real parquet and kills it with SIGKILL before the
footer, so the artefact the detector fires on is the product of an actual kill. The
detector reuses the recorder band's `is_footerless_parquet` (WP-3B-12), so this also
proves that reused check bites on a real crash artefact, and — against a complete
parquet — that it is not vacuously true.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from backend.crash_recovery.faults import FaultKind, inject_sigkill
from backend.recorder.quality.crash import is_footerless_parquet

_ROWS = 6


def test_sigkill_produces_a_genuinely_footerless_parquet(tmp_path: Path) -> None:
    """A real SIGKILL mid-write leaves a footerless parquet the detector fires on."""
    target = tmp_path / "data" / "chunk-000" / "file-000.parquet"

    fault = inject_sigkill(target, rows=_ROWS)

    assert fault.kind is FaultKind.SIGKILL
    assert fault.footerless_parquet == target
    # The file exists (the row group was written) but has no footer (the kill preceded
    # writer.close()), so the trailing PAR1 magic is absent.
    assert target.is_file()
    assert target.stat().st_size > 0
    assert is_footerless_parquet(target) is True


def test_detector_is_not_vacuous_on_a_complete_parquet(tmp_path: Path) -> None:
    """A complete parquet is NOT flagged, so the footerless check is a real discriminator."""
    complete = tmp_path / "complete.parquet"
    pq.write_table(pa.table({"frame_index": list(range(_ROWS))}), complete)

    assert is_footerless_parquet(complete) is False


def test_injection_reports_the_footerless_artefact(tmp_path: Path) -> None:
    """The injected-fault record names the footerless file the recovery step acts on."""
    target = tmp_path / "data" / "chunk-000" / "file-001.parquet"

    fault = inject_sigkill(target, rows=_ROWS)

    assert fault.partial_episode_index is None
    assert fault.unmatched_video is None
    assert "footer" in fault.description
