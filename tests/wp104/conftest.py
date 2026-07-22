"""Shared fixtures for the WP-1-04 suite.

The one genuinely expensive thing in the suite is a real synthetic-harness run, and
every test that needs a `HarnessResult` needs the *same* one, so it is built once at
session scope and reused. It runs the actual `WP-0C-06` harness on the fast config —
the honest synthetic basis PG-RT-001a is judged against — never a fabricated stand-in.
"""

from __future__ import annotations

import pytest

from sim.harness.harness import HarnessResult, run_harness
from sim.harness.load_profile import LoadProfile
from tests.wp104 import FAST_CONFIG


@pytest.fixture(scope="session")
def harness_result() -> HarnessResult:
    """Run the synthetic harness once and share the result across the suite.

    Returns:
        (HarnessResult) A completed fast synthetic-load run.
    """
    profile = LoadProfile(5, 320, 240, 32 * 1024, 128 * 1024)
    return run_harness(profile, FAST_CONFIG)
