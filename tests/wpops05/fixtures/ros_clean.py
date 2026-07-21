"""Pass fixture: the timeseries path reaches MCAP through `mcap` alone (FR-OPS-006).

Proves the scan does not over-fire. `mcap` and the standard library are allowed; no ROS or
rosbag2 module appears, so the scan must find nothing.
"""

from __future__ import annotations

import json

from mcap.writer import Writer


def build(handle: object) -> Writer:
    """Construct an MCAP writer — the only allowed path to the format."""
    _ = json.dumps({"ok": True})
    return Writer(handle)
