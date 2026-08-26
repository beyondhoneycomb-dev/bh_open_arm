"""Decide which camera is in which slot by covering one lens and watching which view goes dark.

The device cannot answer this. Both Arducam B0495 on this rig report the serial
`Arducam_202500915_0001` (`portpath` explains it at length), so udev writes one `by-id` entry and
the second camera has no stable name at all. The port path separates them, but a port path does
not say *left*. What does say left is the operator: cover the left wrist lens, and whichever view
darkens is the left wrist.

This is `ops/hw/canbind/identify` for cameras, deliberately built to the same shape — read a
baseline, ask the operator to act, read again, judge — because it is the same problem: two
devices a bus cannot tell apart, and a human who can.

The judgment is one-sided in the same way. A node counts as covered only when its brightness
drops by `COVERED_DROP_FRACTION` **and** every other candidate stays within
`STEADY_DROP_FRACTION`. Anything else is inconclusive rather than resolved to the largest drop —
two views that both darkened means a hand crossed both or the room light changed, and guessing
between them is the one failure this module exists to prevent.

The brightness reader is injected, so nothing here opens a camera and the tests need no rig.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from backend.camera.portpath import CaptureNode

# How far a view must darken before the drop is a hand and not the room. A covered lens goes
# essentially black; this sits well under that and well over the frame-to-frame wander of a fixed
# scene under mains lighting. It is also under half, so a stereo camera with only one of its two
# lenses covered still clears it.
COVERED_DROP_FRACTION = 0.4

# How steady every other view must stay for the covered one to be unambiguous. Below the covered
# threshold on purpose: the gap between them is the band where the answer is "ask again".
STEADY_DROP_FRACTION = 0.15

# What a baseline under this is: a lens cap, an unlit room, or a camera that opened without
# streaming. Judging a drop against it would divide by something near zero and report sensor
# noise as a covered lens.
MIN_USABLE_BRIGHTNESS = 0.02

# A reading is one node's mean frame brightness, normalised to 0..1 so the thresholds above are
# fractions rather than depending on the device's bit depth. The caller supplies the reader, so
# this module opens no camera.
BrightnessReader = Callable[[CaptureNode], float]


class IdentificationError(Exception):
    """Raised when the readings cannot be compared at all, as opposed to being inconclusive."""


@dataclass(frozen=True)
class NodeDarkening:
    """How much one node's view darkened between two readings.

    Attributes:
        port_path: The node's `bus_info`, which is what a slot is bound to.
        baseline: Mean brightness before the operator covered anything, 0..1.
        covered: Mean brightness while the operator was covering one lens, 0..1.
    """

    port_path: str
    baseline: float
    covered: float

    @property
    def drop_fraction(self) -> float:
        """The share of its own baseline this view lost. Zero when it got brighter."""
        if self.baseline <= 0.0:
            return 0.0
        return max(0.0, (self.baseline - self.covered) / self.baseline)

    @property
    def darkened(self) -> bool:
        """Whether this view cleared the covered threshold."""
        return self.drop_fraction >= COVERED_DROP_FRACTION

    @property
    def steady(self) -> bool:
        """Whether this view stayed within the steady band."""
        return self.drop_fraction <= STEADY_DROP_FRACTION


@dataclass(frozen=True)
class IdentificationResult:
    """One round's outcome.

    Attributes:
        port_path: The port of the node that was covered, or None when inconclusive.
        readings: Every candidate's darkening, for showing the operator the numbers behind a
            refusal — a round that failed on a 38% drop is a different instruction from one that
            failed on 3%.
        reason: Why it was inconclusive; empty when resolved.
    """

    port_path: str | None
    readings: tuple[NodeDarkening, ...]
    reason: str

    @property
    def resolved(self) -> bool:
        """Whether this round produced an unambiguous answer."""
        return self.port_path is not None


def read_baseline(
    nodes: Sequence[CaptureNode], read_brightness: BrightnessReader
) -> dict[str, float]:
    """Read every candidate once, before the operator covers anything."""
    return {node.port_path: read_brightness(node) for node in nodes}


def measure_darkening(
    nodes: Sequence[CaptureNode],
    read_brightness: BrightnessReader,
    before: Mapping[str, float],
) -> tuple[NodeDarkening, ...]:
    """Read every candidate again and return how much each darkened since `before`.

    Args:
        nodes: The candidates to read, in any order.
        read_brightness: Reads one node's mean frame brightness, normalised to 0..1.
        before: The baseline per port path, from `read_baseline`.

    Returns:
        (tuple[NodeDarkening, ...]) One entry per node, in the order given.

    Raises:
        IdentificationError: When a node has no baseline. The two readings would not be a pair,
            and a drop computed against a missing baseline is not a smaller number — it is a
            different measurement wearing the same name.
    """
    readings: list[NodeDarkening] = []
    for node in nodes:
        baseline = before.get(node.port_path)
        if baseline is None:
            raise IdentificationError(f"{node.port_path} has no baseline reading")
        readings.append(
            NodeDarkening(
                port_path=node.port_path, baseline=baseline, covered=read_brightness(node)
            )
        )
    return tuple(readings)


def judge(readings: Sequence[NodeDarkening]) -> IdentificationResult:
    """Decide which view was covered, refusing anything short of one clear answer.

    Args:
        readings: Per-node darkening from `measure_darkening`.

    Returns:
        (IdentificationResult) Resolved only when exactly one view cleared the covered threshold
            and every other stayed inside the steady band. Every other shape — a baseline too
            dark to judge, nothing darkened, two darkened, one darkened while another drifted
            into the middle band — is inconclusive with the reason stated.
    """
    frozen = tuple(readings)
    if not frozen:
        return IdentificationResult(None, frozen, "no cameras were read")
    dark_baselines = [
        reading.port_path for reading in frozen if reading.baseline < MIN_USABLE_BRIGHTNESS
    ]
    if dark_baselines:
        return IdentificationResult(
            None,
            frozen,
            f"{', '.join(dark_baselines)} read black before anything was covered; a lens cap, "
            "an unlit room, or a camera that opened without streaming. Every later drop would "
            "be measured against nothing",
        )
    darkened = [reading for reading in frozen if reading.darkened]
    if not darkened:
        margins = ", ".join(f"{r.port_path}={r.drop_fraction:.0%}" for r in frozen)
        return IdentificationResult(
            None,
            frozen,
            f"no view darkened past {COVERED_DROP_FRACTION:.0%} ({margins}); cover the lens "
            "fully, a hand near it is not a hand on it",
        )
    if len(darkened) > 1:
        names = ", ".join(reading.port_path for reading in darkened)
        return IdentificationResult(
            None, frozen, f"more than one view darkened ({names}); cover only one camera"
        )
    winner = darkened[0]
    drifted = [
        reading
        for reading in frozen
        if reading.port_path != winner.port_path and not reading.steady
    ]
    if drifted:
        names = ", ".join(f"{r.port_path}={r.drop_fraction:.0%}" for r in drifted)
        return IdentificationResult(
            None,
            frozen,
            f"{winner.port_path} darkened but {names} did not stay steady (under "
            f"{STEADY_DROP_FRACTION:.0%}); that is what a changing room light looks like, "
            "hold the light steady and repeat",
        )
    return IdentificationResult(winner.port_path, frozen, "")


def identify_covered_node(
    nodes: Sequence[CaptureNode],
    read_brightness: BrightnessReader,
    prompt_operator: Callable[[], None],
) -> IdentificationResult:
    """Run one round: read, ask the operator to cover one lens, read again, judge.

    Args:
        nodes: The candidates in play — the slots not yet assigned.
        read_brightness: Reads one node's mean frame brightness, normalised to 0..1.
        prompt_operator: Blocks until the operator says the lens is covered. The caller owns how
            that is asked — a CLI `input()`, a GUI button, a test stub.

    Returns:
        (IdentificationResult) The round's outcome; check `resolved` before using it.
    """
    baseline = read_baseline(nodes, read_brightness)
    prompt_operator()
    return judge(measure_darkening(nodes, read_brightness, baseline))


__all__ = [
    "COVERED_DROP_FRACTION",
    "MIN_USABLE_BRIGHTNESS",
    "STEADY_DROP_FRACTION",
    "BrightnessReader",
    "IdentificationError",
    "IdentificationResult",
    "NodeDarkening",
    "identify_covered_node",
    "judge",
    "measure_darkening",
    "read_baseline",
]
