"""Shared fixtures for the WP-2C-01 momentum-observer acceptance tests.

The model terms load the committed v2 MJCF and build the gravity backend, which is the same
handle for every test, so it is session-scoped: one load, reused. It carries mutable mujoco
scratch buffers, but the suite runs sequentially and every call fully sets the pose before
reading, so the reuse is safe.
"""

from __future__ import annotations

import pytest

from backend.gmo import GmoModelTerms


@pytest.fixture(scope="session")
def model_terms() -> GmoModelTerms:
    """The right-arm GMO model terms (reused gravity/Coriolis/friction plus the added inertia)."""
    return GmoModelTerms()
