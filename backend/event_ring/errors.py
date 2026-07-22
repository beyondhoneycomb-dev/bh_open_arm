"""Failures the event ring and its monitor raise, kept in one place.

Two of these encode a plan negative branch rather than an ordinary bug:
`EventRingLossError` is the surfaced form of the `02b` §3 WP-2C-09 RETRY_WITH_VARIANT
outcome (ring loss → recompute capacity/sample rate), and `HardwareDeferredError`
is how a re-verification hook refuses to report a green it has not earned on real
hardware. Neither is a stub: a lossy dump is detected and named, and a deferred
check fails loudly instead of passing on synthetic data.
"""

from __future__ import annotations


class EventRingShapeError(ValueError):
    """A telemetry sample did not carry exactly the joint-by-channel matrix declared.

    The dump's whole value is that every joint and channel is present for every
    retained tick; a ragged sample would make a later dump silently short a
    channel, so the shape is checked at construction, not at dump time.
    """


class EventRingLossError(RuntimeError):
    """A dump was required lossless but the ring dropped a within-window sample.

    Raised only when a caller asserts losslessness on a dump that lost samples to
    capacity pressure. It is the loud form of the WP-2C-09 negative branch: the
    remedy is to recompute capacity or sample rate (RETRY_WITH_VARIANT), never to
    treat the short window as complete.
    """


class HardwareDeferredError(RuntimeError):
    """A re-verification hook was called without the real capture it needs.

    The on-hardware acceptance of WP-2C-09 — a real collision event captured at the
    real loop rate, and the real re-identification threshold — cannot be decided on
    this host. The hook raises this rather than returning a pass, so a deferred item
    is never mistaken for a verified one.
    """
