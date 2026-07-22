"""The single exception type for a rejected temperature or grasp-force configuration."""

from __future__ import annotations


class TempGripperConfigError(ValueError):
    """A temperature or grasp-force setting outside its allowed domain.

    Raised when a fault threshold is set above its FR-SAF-026 cap, when a warn/fault
    pair is mis-ordered, when a per-unit grasp threshold leaves the [0, 1] domain, or
    when a feedback frame is malformed — each a case that, accepted silently, would
    weaken a safety limit or read a bad value as a plausible one.
    """
