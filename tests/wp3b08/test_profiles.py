"""Acceptance ①: profiles resolve by fallback chain, never an exact-string whitelist.

The load-bearing assertion is the reproduction test: an exact-string whitelist (the
upstream `ar.js:119-136` gate feeding `main.py:164`) rejects an unknown headset, and a
rejected controller has its trigger dropped and therefore its pose withheld — the
whole teleop path goes dark. The same unknown headset resolves under the shipped
fallback chain, so the defect is proven real and the fix proven to avoid it. The
production resolver carries no whitelist; the buggy gate is constructed here, in the
test, purely to demonstrate the failure it would cause.
"""

from __future__ import annotations

import pytest

from backend.teleop.webxr.constants import FALLBACK_PROFILE_CHAIN, XR_STANDARD_MAPPING
from backend.teleop.webxr.profiles import (
    ProfileResolutionError,
    ResolvedVia,
    is_resolvable,
    resolve_layout,
)
from tests.wp3b08.support import UNKNOWN_QUEST_PROFILE

# The upstream exact-string whitelist (`ar.js:119-136`): only these profile strings
# have their trigger read. Reconstructed here to reproduce the outage, never shipped.
_UPSTREAM_WHITELIST = frozenset({"meta-quest-touch-plus", "pico-4u"})

# An analog trigger reading, stood in for the value the gamepad would report.
_TRIGGER_VALUE = 0.9


def _whitelist_trigger(profiles: list[str]) -> float | None:
    """Model `ar.js`: the trigger is read only on an exact whitelist match, else None."""
    return _TRIGGER_VALUE if profiles and profiles[0] in _UPSTREAM_WHITELIST else None


def _whitelist_publishes(profiles: list[str], pose: object) -> bool:
    """Model `main.py:164` `if pose in response and trigger in response`."""
    return pose is not None and _whitelist_trigger(profiles) is not None


def test_exact_whitelist_darkens_an_unknown_headset() -> None:
    # The reproduction: a real pose is present, but the unknown profile is not on the
    # whitelist, so the trigger is dropped and the pose is never published.
    profiles = [UNKNOWN_QUEST_PROFILE]
    real_pose = object()
    assert _whitelist_publishes(profiles, real_pose) is False


def test_fallback_chain_admits_the_same_unknown_headset() -> None:
    # The same unknown headset the whitelist darkens resolves under the fallback chain,
    # via the xr-standard mapping rather than any known profile string.
    profiles = [UNKNOWN_QUEST_PROFILE]
    assert _whitelist_publishes(profiles, object()) is False  # whitelist: dark
    assert is_resolvable(profiles, XR_STANDARD_MAPPING) is True  # chain: admitted
    resolution = resolve_layout(profiles, XR_STANDARD_MAPPING)
    assert resolution.via is ResolvedVia.XR_STANDARD
    assert resolution.matched_profile == XR_STANDARD_MAPPING


def test_unknown_profile_with_nonstandard_mapping_needs_no_whitelist() -> None:
    # An unknown profile whose gamepad does NOT report xr-standard is the one case that
    # is refused — the sanctioned startup refusal, not an unknown-headset lockout.
    assert is_resolvable([UNKNOWN_QUEST_PROFILE], "nonstandard-mapping") is False
    with pytest.raises(ProfileResolutionError):
        resolve_layout([UNKNOWN_QUEST_PROFILE], "nonstandard-mapping")


@pytest.mark.parametrize("profile", FALLBACK_PROFILE_CHAIN)
def test_every_chain_profile_resolves_via_chain(profile: str) -> None:
    # Each chain entry resolves by the chain even when the mapping is unreported.
    resolution = resolve_layout([profile], "")
    assert resolution.via is ResolvedVia.CHAIN
    assert resolution.matched_profile == profile


def test_most_specific_known_profile_wins() -> None:
    # profiles are ordered most-specific first; the first known one is the match.
    resolution = resolve_layout(
        ["oculus-touch-v3", "generic-trigger-squeeze-thumbstick"], XR_STANDARD_MAPPING
    )
    assert resolution.via is ResolvedVia.CHAIN
    assert resolution.matched_profile == "oculus-touch-v3"


def test_generic_floor_profile_resolves() -> None:
    # The generic registry floor resolves an otherwise-unknown controller by the chain.
    resolution = resolve_layout(
        [UNKNOWN_QUEST_PROFILE, "generic-trigger-squeeze-thumbstick"], "anything"
    )
    assert resolution.via is ResolvedVia.CHAIN
    assert resolution.matched_profile == "generic-trigger-squeeze-thumbstick"
