"""Requested and accepted actions are recorded together or not at all (WP-0A-02).

Acceptance ②: a frame that keeps only the post-clamp `acceptedPositionAction`
erases the pre-clamp request, making intervention and clamp saturation
undebuggable (00 §8.3); the reverse hides what was executed. Recording one without
the other is rejected.
"""

from __future__ import annotations

from contracts.action import validate_frame


def test_both_present_is_accepted() -> None:
    """A frame carrying both action channels passes."""
    assert validate_frame(has_requested=True, has_accepted=True) == ()


def test_neither_present_is_accepted() -> None:
    """A frame with no action channel (e.g. a hold tick) is not this rule's concern."""
    assert validate_frame(has_requested=False, has_accepted=False) == ()


def test_accepted_without_requested_is_rejected() -> None:
    """Post-clamp-only recording is rejected — the request is erased."""
    violations = validate_frame(has_requested=False, has_accepted=True)
    assert violations
    assert "requestedPositionAction" in violations[0]


def test_requested_without_accepted_is_rejected() -> None:
    """Request-only recording is rejected — the executed action is unknown."""
    violations = validate_frame(has_requested=True, has_accepted=False)
    assert violations
    assert "acceptedPositionAction" in violations[0]
