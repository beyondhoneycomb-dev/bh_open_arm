"""Shared fixtures for the WP-5-05 phase-1 load-test suite.

The max-load profile is the one the acceptance items are judged under: many
high-resolution cameras (`backend.camera.fixtures.d415_quad_full_res`) over multiple
clients on a link the camera sum alone saturates, so the head-of-line pressure the WP
is about is actually present. The run is deterministic — a fixed step and fixed rates
— so "the p99 of the command class at this load" is reproducible across runs.
"""

from __future__ import annotations

import pytest

from backend.camera.fixtures import d415_quad_full_res
from backend.loadtest import LoadProfile, LoadRun, run_load
from backend.loadtest.constants import CLIENT_LOCALITY_LAN

# A 100 Mbps LAN link in bytes/sec. Large enough that a small control frame drains in
# one step, small enough that four high-res cameras across two clients saturate it —
# the regime the HOL judge must be exercised in.
_LAN_LINK_BYTES_PER_SEC = 12.5e6

_RUN_DURATION_SEC = 2.0


@pytest.fixture
def max_load_profile() -> LoadProfile:
    """Four full-res D415 (color+depth) over two LAN clients on a saturated link."""
    return LoadProfile(
        cameras=d415_quad_full_res(),
        client_count=2,
        link_capacity_bytes_per_sec=_LAN_LINK_BYTES_PER_SEC,
        locality=CLIENT_LOCALITY_LAN,
    )


@pytest.fixture
def saturated_run(max_load_profile: LoadProfile) -> LoadRun:
    """A completed load run at max load — camera saturated, control classes protected."""
    return run_load(max_load_profile, duration_sec=_RUN_DURATION_SEC, step_sec=0.001)
