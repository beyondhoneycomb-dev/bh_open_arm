"""WP-ENV-01 acceptance ② ③ — rollout entry imports; RealSense class symbol exists.

Heavy: skipped where the [robot] stack is absent (the light lane), run for real
where it is present.
"""

from __future__ import annotations

import pytest

pytest.importorskip("lerobot")

from deps.imports import check_realsense_symbol, check_rollout_entry  # noqa: E402


def test_rollout_engine_entry_imports() -> None:
    outcome = check_rollout_entry()
    assert outcome.ok, outcome.detail


def test_realsense_camera_symbol_exists() -> None:
    outcome = check_realsense_symbol()
    assert outcome.ok, outcome.detail
