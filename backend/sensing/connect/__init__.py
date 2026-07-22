"""Tolerant camera connect + serial binding (WP-3B-01).

`06` §2.12 / `FR-CAM-084`: cameras open independently, a dead one is warned and
skipped, and neither the skip nor a USB2 fallback fails the arm's connect or motion —
only observation and recording degrade. This package is that connect over the frozen
synthetic fixture, reusing WP-0B-08's serial binding (`backend.camera.binding`, index
rejected — `FR-CAM-004`) and bandwidth formula (`backend.camera.bandwidth`, the USB2
profile block — `FR-CAM-003`), and consuming `CTR-CAM@v1` / `CTR-PRIM@v1` by reference.

Real enumeration — real serials, real link speeds, a real first-frame grab — needs
hardware this host lacks; that boundary and its `02a` §4.1 re-verification hook are in
`deferred.py`, which skips with a reason until a real capture directory is supplied.
"""

from __future__ import annotations

from backend.sensing.connect.constants import (
    DEFAULT_PROBE_DEPTH,
    REAL_FIXTURE_ENV_VAR,
    USB2_NOMINAL_MBPS,
)
from backend.sensing.connect.deferred import (
    fixture_dir_from_env,
    real_connect_supported,
    reconnect_from_fixture,
)
from backend.sensing.connect.outcome import (
    BlockedProfile,
    CameraConnectOutcome,
    ConnectReport,
    ConnectStatus,
    SkipReason,
)
from backend.sensing.connect.probe import (
    LiveFrameSource,
    RecordedFrame,
    RecordedLiveness,
)
from backend.sensing.connect.tolerant import tolerant_connect

__all__ = [
    "DEFAULT_PROBE_DEPTH",
    "REAL_FIXTURE_ENV_VAR",
    "USB2_NOMINAL_MBPS",
    "BlockedProfile",
    "CameraConnectOutcome",
    "ConnectReport",
    "ConnectStatus",
    "LiveFrameSource",
    "RecordedFrame",
    "RecordedLiveness",
    "SkipReason",
    "fixture_dir_from_env",
    "real_connect_supported",
    "reconnect_from_fixture",
    "tolerant_connect",
]
