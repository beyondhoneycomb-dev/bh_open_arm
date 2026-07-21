"""A stop path that cuts torque — the acceptance-⑦ violation fixture.

Scanning this must find `disable_torque`: the stop path must be a hold frame, not
a torque cut (`04` NFR-MAN-002), and this fixture does the banned thing so the scan
(`backend.actuation.staticcheck.find_disable_torque`) can be shown to bite.
"""

from __future__ import annotations

from typing import Any


def wrong_stop(bus: Any) -> None:
    """Cut torque on stop — the banned shape.

    Args:
        bus: A CAN bus object; calling `disable_torque` here is the violation.
    """
    bus.disable_torque()
