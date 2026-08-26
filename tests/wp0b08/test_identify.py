"""Covering one lens names one camera, and everything short of that is refused.

The judgment is deliberately one-sided, for the same reason `ops/hw/canbind/identify` is: the
answer it produces is written to disk and every later run trusts it. A round that resolved to
"whichever dropped most" would be right most of the time and silently wrong when the room light
changed — and a wrist pair bound backwards does not show up in the footage.

Every reading here is supplied by a stub. Nothing opens a camera.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from backend.camera.identify import (
    COVERED_DROP_FRACTION,
    MIN_USABLE_BRIGHTNESS,
    STEADY_DROP_FRACTION,
    IdentificationError,
    NodeDarkening,
    identify_covered_node,
    judge,
    measure_darkening,
)
from backend.camera.portpath import CaptureNode

LEFT = CaptureNode(device=Path("/dev/video2"), port_path="usb-a-1", card="Arducam B0495")
RIGHT = CaptureNode(device=Path("/dev/video4"), port_path="usb-a-2", card="Arducam B0495")
STEREO = CaptureNode(device=Path("/dev/video0"), port_path="usb-b-1", card="ZED-M")
NODES = (LEFT, RIGHT, STEREO)

# A lit room. Well over `MIN_USABLE_BRIGHTNESS` so the baseline is never the thing under test.
LIT = 0.5


class StubBrightness:
    """Answers a scripted brightness per node, one script per call round."""

    def __init__(self, rounds: list[Mapping[str, float]]) -> None:
        """Bind the stub to its scripted rounds.

        Args:
            rounds: One mapping of port path to brightness per full pass over the nodes. The
                stub advances a round each time it has answered every node once.
        """
        self._rounds = rounds
        self._answered: set[str] = set()
        self._index = 0

    def __call__(self, node: CaptureNode) -> float:
        """Answer this node's brightness for the current round."""
        if node.port_path in self._answered:
            self._answered = set()
            self._index += 1
        self._answered.add(node.port_path)
        return self._rounds[self._index][node.port_path]


class CountingPrompt:
    """Records that the operator was asked, without asking anyone."""

    def __init__(self) -> None:
        """Start with no asks recorded."""
        self.asks = 0

    def __call__(self) -> None:
        """Record one ask."""
        self.asks += 1


def _reading(port: str, drop: float) -> NodeDarkening:
    """Build a reading that lost `drop` of a lit baseline."""
    return NodeDarkening(port_path=port, baseline=LIT, covered=LIT * (1.0 - drop))


def test_the_covered_view_is_the_one_that_went_dark() -> None:
    """The whole point, and the only shape that resolves."""
    result = judge(
        [
            _reading(LEFT.port_path, 0.9),
            _reading(RIGHT.port_path, 0.01),
            _reading(STEREO.port_path, 0.0),
        ]
    )

    assert result.resolved is True
    assert result.port_path == LEFT.port_path


def test_two_views_that_darkened_resolve_to_nothing() -> None:
    """A hand across both, or the room light going out. Picking the larger drop is the bug.

    This is the failure the whole module exists to prevent: both numbers look like an answer, and
    the wrong one is written to disk and trusted by every run afterwards.
    """
    result = judge([_reading(LEFT.port_path, 0.9), _reading(RIGHT.port_path, 0.8)])

    assert result.resolved is False
    assert LEFT.port_path in result.reason
    assert RIGHT.port_path in result.reason


def test_a_clear_winner_beside_a_drifting_view_still_resolves_to_nothing() -> None:
    """The middle band is a refusal, not a rounding decision.

    One view is far past the covered threshold and the other is only in the middle — a shape that
    reads as a clean answer if only the largest drop is consulted. It is what a dimming room looks
    like, so it is refused.
    """
    drift = (COVERED_DROP_FRACTION + STEADY_DROP_FRACTION) / 2

    result = judge([_reading(LEFT.port_path, 0.95), _reading(RIGHT.port_path, drift)])

    assert result.resolved is False
    assert RIGHT.port_path in result.reason


def test_nothing_darkening_says_so_with_the_numbers() -> None:
    """An operator whose hand was close but not on the lens needs to see how close."""
    result = judge([_reading(LEFT.port_path, 0.05), _reading(RIGHT.port_path, 0.02)])

    assert result.resolved is False
    assert "5%" in result.reason


def test_a_black_baseline_is_refused_before_any_drop_is_believed() -> None:
    """Every later drop would be measured against nothing, and read as near-total.

    A lens cap or an unlit room produces exactly this, and without the check it produces a
    confident answer — the camera that happens to be darkest wins every round.
    """
    result = judge(
        [
            NodeDarkening(
                port_path=LEFT.port_path, baseline=MIN_USABLE_BRIGHTNESS / 2, covered=0.0
            ),
            _reading(RIGHT.port_path, 0.0),
        ]
    )

    assert result.resolved is False
    assert LEFT.port_path in result.reason


def test_a_view_that_got_brighter_counts_as_no_drop() -> None:
    """A hand entering frame near a light can raise the mean; that is not a covered lens."""
    brighter = NodeDarkening(port_path=LEFT.port_path, baseline=LIT, covered=LIT * 2)

    assert brighter.drop_fraction == 0.0
    assert brighter.darkened is False
    assert brighter.steady is True


def test_a_round_reads_before_and_after_the_operator_acts() -> None:
    """The prompt sits between the two reads, or the baseline already includes the covering."""
    prompt = CountingPrompt()
    brightness = StubBrightness(
        [
            {LEFT.port_path: LIT, RIGHT.port_path: LIT, STEREO.port_path: LIT},
            {LEFT.port_path: LIT, RIGHT.port_path: 0.01, STEREO.port_path: LIT},
        ]
    )

    result = identify_covered_node(NODES, brightness, prompt)

    assert prompt.asks == 1
    assert result.port_path == RIGHT.port_path


def test_a_node_with_no_baseline_is_an_error_not_an_inconclusive_round() -> None:
    """Two readings that are not a pair is a caller mistake, not an operator one."""
    with pytest.raises(IdentificationError, match=LEFT.port_path):
        measure_darkening([LEFT], lambda _node: LIT, {})
