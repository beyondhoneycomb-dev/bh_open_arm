"""A delete with any check unmet is FAIL_BLOCKING — the single delete point refuses it.

`delete_certified` is the one place the band removes a raw source, and it refuses —
by raising — any decision that is not DELETABLE. This is the runtime guard that makes
"a delete with any check unmet" impossible: even a caller that already holds a
refused decision cannot turn it into a deletion (`02b` §7.2 WP-3C-06, the
`FAIL_BLOCKING` branch — irreversible data loss).
"""

from __future__ import annotations

import pytest

from backend.capture_interlock import (
    CaptureInterlockError,
    CaptureSource,
    SourceDeleteInterlock,
)
from tests.wp3c06 import faults
from tests.wp3c06.materialize import Fixture


def test_delete_certified_raises_on_a_refused_decision(pair: Fixture) -> None:
    """Handing a REFUSED decision to the delete point raises and deletes nothing."""
    faults.inject_capture_ts_reordered(pair)
    interlock = SourceDeleteInterlock()
    source = CaptureSource(pair.raw_root)

    decision = interlock.decide(pair.raw_root, pair.converted_root)
    assert not decision.deletable

    with pytest.raises(CaptureInterlockError):
        interlock.delete_certified(source, decision)

    # The raw source is untouched — the refused delete never fired.
    assert source.exists()
    assert source.episode_indices() == tuple(range(pair.episodes))


def test_delete_certified_refuses_a_not_ready_decision(pair: Fixture) -> None:
    """A decision refused only for a READY failure still cannot be forced to delete."""
    faults.inject_ready_invalid(pair)
    interlock = SourceDeleteInterlock()
    source = CaptureSource(pair.raw_root)

    decision = interlock.decide(pair.raw_root, pair.converted_root)
    assert decision.all_preserved and not decision.training_ready

    with pytest.raises(CaptureInterlockError):
        interlock.delete_certified(source, decision)

    assert source.exists()
