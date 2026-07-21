"""The "Frame did not arrive in time" diagnostic (`06` FR-CAM-013).

librealsense raises this on a starved stream, and its cause is genuinely ambiguous
between two physical faults: insufficient USB bandwidth and insufficient bus power
(librealsense#1873). FR-CAM-013 requires the diagnostic to name *both* — so an
operator does not chase a bandwidth problem that is really a powered-hub problem, or
the reverse. The message builder here always states both causes.

The message builder and the classifier run on any host. What cannot run here is
provoking the real error under load, which needs a real starved camera — that is the
deferred half of `02a` WP-0B-08 ⑦, skipped with a reason and re-run by the fixture
hook against a captured error string.
"""

from __future__ import annotations

FRAME_TIMEOUT_ERROR = "Frame did not arrive in time"

_BANDWIDTH_CAUSE = (
    "insufficient USB bandwidth (too many streams or too high a profile on one "
    "controller — see the bandwidth budget)"
)
_POWER_CAUSE = (
    "insufficient bus power (an unpowered hub or a marginal cable — try a powered "
    "hub or a direct root-port connection)"
)


def is_frame_timeout(error_text: str) -> bool:
    """Report whether an error string is the frame-timeout condition."""
    return FRAME_TIMEOUT_ERROR.lower() in error_text.lower()


def diagnose_frame_timeout(camera_label: str) -> str:
    """Build the frame-timeout diagnostic naming both bandwidth and power (FR-CAM-013).

    Args:
        camera_label: Human-readable camera identifier for the message.

    Returns:
        (str) A diagnostic that explicitly cites both the bandwidth and power causes.
    """
    return (
        f"{FRAME_TIMEOUT_ERROR} on {camera_label}: this has two possible causes and "
        f"you must rule out both — {_BANDWIDTH_CAUSE}; and {_POWER_CAUSE}."
    )
