"""SIM-mode CAN guard: the MuJoCo backend never opens a CAN socket (WP-0C-01).

`09` FR-SIM-098 makes pure sim CAN-less end to end, and `01` §4.1 (SIM row) says
the SIM path acquires no CAN flock. This module is the runtime-hook half of
acceptance ②: `open_can_in_sim` is the single chokepoint any CAN open would have
to pass through, and in SIM it raises before a socket can be created;
`assert_no_can_open` is the invariant the backend re-checks at connect and before
every actuation, so a zero CAN-open count is enforced, not merely assumed. The
static half -- that no CAN-open primitive appears in the backend source at all --
is proven separately by tests/wp0c01.

This module imports no robot stack and no `mujoco`: the guard is pure so it holds
regardless of which lane loads it.
"""

from __future__ import annotations

# The CAN-open count a SIM backend must always report. A non-zero value means a CAN
# socket was opened on a path that FR-SIM-098 forbids in simulation.
SIM_CAN_OPEN_COUNT = 0


class SimModeCanError(RuntimeError):
    """Raised when SIM-mode code reaches a CAN-open path (`09` FR-SIM-098)."""


def open_can_in_sim(interface: str) -> None:
    """The single CAN-open chokepoint for the SIM backend; it always refuses.

    Pure simulation opens no CAN socket and holds no flock (`09` FR-SIM-098,
    `01` §4.1). Routing every conceivable CAN open through here means the only way
    to reach hardware in SIM is to call this function, and it raises first.

    Args:
        interface: The CAN interface name that was about to be opened.

    Raises:
        SimModeCanError: Always, in SIM mode.
    """
    raise SimModeCanError(
        f"SIM mode must not open a CAN socket (interface={interface!r}); pure simulation "
        "is CAN-less end to end and holds no flock (09 FR-SIM-098, 01 §4.1)"
    )


def assert_no_can_open(can_open_count: int) -> None:
    """Runtime hook: refuse to proceed unless zero CAN sockets were opened in SIM.

    The backend calls this at connect and before every actuation with its own
    CAN-open counter, which stays zero for a SIM backend's whole life. A non-zero
    count is a CAN open that slipped past the chokepoint, and this stops the run.

    Args:
        can_open_count: The number of CAN sockets the backend has opened.

    Raises:
        SimModeCanError: If `can_open_count` is not zero.
    """
    if can_open_count != SIM_CAN_OPEN_COUNT:
        raise SimModeCanError(
            f"SIM backend opened {can_open_count} CAN socket(s); simulation must open "
            "none (09 FR-SIM-098)"
        )
