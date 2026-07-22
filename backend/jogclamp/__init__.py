"""WP-2A-03 — the jog-path clamp application (two-stage clamp + step-delta jump cap).

The producer-side shaping a jog target passes through before it reaches the single
`send_action` gateway. It reuses the Wave-1 `SafetyLimits` envelope and its
`validate()` (the operational-subset and rate-guard-separation checks); it does NOT
re-implement the gateway's `SafetyFilter`, its velocity check, or its step-delta
STOP. What it adds is the jog wiring: the two-stage clamp application, the
clip-and-proceed jump cap, the connect-seeded `_previous_q_deg`, and the clamp
counter that surfaces saturation instead of a silent `logger.debug` clip.
"""

from __future__ import annotations

from backend.jogclamp.counter import ClampCounter
from backend.jogclamp.path import (
    JogClampConfigError,
    JogClampNotSeededError,
    JogClampPath,
    JogClampResult,
)
from backend.jogclamp.reason import JogClampReason, to_clamp_reason

__all__ = [
    "ClampCounter",
    "JogClampConfigError",
    "JogClampNotSeededError",
    "JogClampPath",
    "JogClampReason",
    "JogClampResult",
    "to_clamp_reason",
]
