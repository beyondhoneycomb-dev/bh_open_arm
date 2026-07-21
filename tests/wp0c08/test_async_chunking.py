"""Acceptance ⑨⑩ — the async fallback rejects an unset chunk and shuns stale literals.

`16` D-11: `actions_per_chunk` is a required argument with no default, and
`chunk_size_threshold` defaults to 0.5. The documented `50 / 0.7` pair is stale.
This suite proves the enforcer rejects a plan that omits `actions_per_chunk`, takes
the threshold default as the introspected 0.5, and that neither stale literal is
written into the async-chunking source.
"""

from __future__ import annotations

import pytest

from backend.policy_matrix import (
    actions_per_chunk_is_required,
    async_chunk_size_threshold_default,
    build_async_chunking_plan,
)
from tests.wp0c08 import POLICY_MATRIX_DIR, numeric_literals

_ASYNC_SOURCE_FILES = ("enforce.py", "caps.py")
# `16` D-11: the documented `actions_per_chunk=50 / chunk_size_threshold=0.7` pair
# is stale; neither value may be written into the async-chunking logic.
_STALE_LITERALS = {50.0, 0.7}


def test_actions_per_chunk_is_required_upstream() -> None:
    """⑨ ground truth — the installed RobotClientConfig gives it no default."""
    assert actions_per_chunk_is_required() is True


def test_unset_actions_per_chunk_is_rejected() -> None:
    """⑨ — a plan that omits actions_per_chunk is refused instantiation."""
    with pytest.raises(ValueError, match="actions_per_chunk is required"):
        build_async_chunking_plan(None)


def test_chunk_size_threshold_default_is_half() -> None:
    """⑩ — the threshold default is the introspected 0.5, not the stale 0.7."""
    assert async_chunk_size_threshold_default() == 0.5
    plan = build_async_chunking_plan(actions_per_chunk=10)
    assert plan.chunk_size_threshold == 0.5
    assert plan.actions_per_chunk == 10


def test_explicit_threshold_is_honoured() -> None:
    """An explicit threshold overrides the introspected default."""
    plan = build_async_chunking_plan(actions_per_chunk=8, chunk_size_threshold=0.25)
    assert plan.chunk_size_threshold == 0.25


def test_no_stale_literal_residue() -> None:
    """⑩ — the stale `50 / 0.7` values are used in no async-chunking code literal."""
    for filename in _ASYNC_SOURCE_FILES:
        used = numeric_literals(POLICY_MATRIX_DIR / filename)
        assert not (used & _STALE_LITERALS), (
            f"stale literal in {filename}: {used & _STALE_LITERALS}"
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
