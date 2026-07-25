"""CG-4C-04a — every tag definition carries a discriminating signal; none is signal-less."""

from __future__ import annotations

import pytest

from backend.eval.taxonomy import (
    TAG_SPECS,
    FailureTag,
    FailureTagSpec,
    TagAxis,
    TagDerivation,
    spec_for,
)


def test_every_tag_has_a_definition() -> None:
    """Every FailureTag has a spec — the schema is complete."""
    assert set(TAG_SPECS) == set(FailureTag)


def test_every_tag_declares_a_nonempty_signal() -> None:
    """No tag is pinned by impression alone; each carries a non-empty signal (CG-4C-04a)."""
    for tag in FailureTag:
        assert spec_for(tag).signal.strip(), f"{tag.name} has no discriminating signal"


def test_signal_less_tag_is_rejected_at_construction() -> None:
    """The schema refuses to define a signal-less tag — the static bite."""
    with pytest.raises(ValueError, match="discriminating signal"):
        FailureTagSpec(axis=TagAxis.POLICY, derivation=TagDerivation.AUTO, signal="   ")
