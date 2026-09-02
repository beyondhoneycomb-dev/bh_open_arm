"""Reuse, not fork: the harness reads its rules from the contract and the camera budget.

The WP interface contract says reuse the committed WS layer and the Wave 3B camera
bandwidth budget rather than restating them. These tests bind that: the backpressure
verdict reads the CTR-WS threshold; the mirrored 30/60 publish rates match the
frontend's own constants byte-for-byte (a fork would let them drift); and the camera
load is sized from `backend.camera.bandwidth`, not a hardcoded byte figure.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.camera.bandwidth import descriptor_bandwidth_mbps
from backend.camera.constants import BITS_PER_BYTE, MEGABIT_DIVISOR
from backend.camera.fixtures import d415_quad_full_res
from backend.loadtest import LoadProfile, verify_backpressure_policy
from backend.loadtest.constants import JPEG_PREVIEW_COMPRESSION_RATIO
from backend.ws.constants import WS_PUBLISH_RATE_DEFAULT_HZ, WS_PUBLISH_RATE_MAX_HZ
from contracts.ws.schema import BUFFERED_AMOUNT_THRESHOLD_BYTES

_FRONTEND_CONSTANTS = Path("frontend/src/viewport/constants.ts")


def _frontend_number(name: str) -> float:
    text = _FRONTEND_CONSTANTS.read_text(encoding="utf-8")
    match = re.search(rf"{name}\s*=\s*([0-9.]+)", text)
    assert match, f"{name} not found in {_FRONTEND_CONSTANTS}"
    return float(match.group(1))


def test_backpressure_threshold_is_the_contract_value() -> None:
    assert verify_backpressure_policy().threshold_bytes == BUFFERED_AMOUNT_THRESHOLD_BYTES


def test_publish_rates_match_the_frontend_constants() -> None:
    # The mirror must not drift from the frontend's own PUBLISH_RATE constants.
    assert _frontend_number("PUBLISH_RATE_DEFAULT_HZ") == WS_PUBLISH_RATE_DEFAULT_HZ
    assert _frontend_number("PUBLISH_RATE_MAX_HZ") == WS_PUBLISH_RATE_MAX_HZ


def test_camera_load_is_sized_from_the_bandwidth_budget() -> None:
    cameras = d415_quad_full_res()
    profile = LoadProfile(cameras=cameras, client_count=1, link_capacity_bytes_per_sec=1.0)
    # The offered preview rate is the 06 §2.9 budget (via backend.camera.bandwidth),
    # JPEG-compressed and summed — recomputed here from the same module, not a literal.
    expected = (
        sum(descriptor_bandwidth_mbps(cam) * MEGABIT_DIVISOR / BITS_PER_BYTE for cam in cameras)
        / JPEG_PREVIEW_COMPRESSION_RATIO
    )
    assert profile.camera_preview_bytes_per_sec() == expected
