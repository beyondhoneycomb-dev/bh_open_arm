"""The one REST route S-13 reads.

A single GET assembling the whole payload, because the screen renders it as one state: four
independent fetches would let the port table describe a moment the RT posture does not, and the
compare view is a statement about one instant of this host.

Read-only and side-effect free. Nothing here starts a bundle — `FR-OPS-023`'s one-click
generation is a separate action with a file to write, and a GET that produced one would run
every time the screen mounted.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from backend.system.constants import SYSTEM_REPORT_ROUTE
from backend.system.report import system_report


def mount_system_routes(app: FastAPI) -> None:
    """Mount the system report route onto an application.

    Args:
        app: The application to mount onto.
    """

    @app.get(SYSTEM_REPORT_ROUTE)
    def read_system_report() -> dict[str, Any]:
        """Serve the port map, the realtime posture, the bundle manifest and the code registry."""
        return system_report()


__all__ = ["mount_system_routes"]
