"""Acceptance ① — the auto-upgrade blocker rejects range specifiers.

A range specifier (>=, ~=, ^, bare *, comma-joined constraints) lets a resolver climb
off the frozen pin; an exact version or a frozen-minor patch line (2.3.x / ==2.3.*)
does not. The blocker must reject the former and pass the latter, and it must catch the
range operators in a real fixture manifest — a checker green on the auto-upgrade fixture
would be catching nothing.
"""

from __future__ import annotations

import pytest

from ops.versionpin.blocker import (
    Classification,
    classify_specifier,
    rejected,
    scan_manifest,
)
from ops.versionpin.manifest import load_manifest
from tests.wpops03.conftest import load_fixture

_RANGE_SPECIFIERS = [
    ">=5.1",
    "~=2.3",
    ">2.3",
    "<3.0",
    "<=2.3",
    "!=2.3",
    "^2.3",
    "2.3.*,<3",
    "*",
    "latest",
    "",
]
_EXACT_SPECIFIERS = ["==5.1.0", "==2.3.*", "5.1.0", "2.3.x", "2.3.0", "0" * 40]


@pytest.mark.parametrize("specifier", _RANGE_SPECIFIERS)
def test_range_specifiers_are_rejected(specifier: str) -> None:
    verdict = classify_specifier(specifier, where="test")
    assert verdict.classification is Classification.RANGE
    assert verdict.rejected
    assert verdict.reason  # a rejection always names why


@pytest.mark.parametrize("specifier", _EXACT_SPECIFIERS)
def test_exact_specifiers_are_accepted(specifier: str) -> None:
    verdict = classify_specifier(specifier, where="test")
    assert verdict.classification is Classification.EXACT
    assert not verdict.rejected


def test_frozen_minor_patch_wildcard_is_exact_not_range() -> None:
    # U-3's "2.3.x" freezes the 2.3 minor and lets only the patch float; this is the
    # intended semantics, not an auto-upgrade, so it must classify EXACT.
    assert classify_specifier("==2.3.*").classification is Classification.EXACT
    assert classify_specifier("2.3.x").classification is Classification.EXACT
    # A wildcard on the minor, by contrast, floats the pin and is rejected.
    assert classify_specifier("2.*").rejected


def test_committed_manifest_has_no_range_operators() -> None:
    verdicts = scan_manifest(load_manifest())
    assert verdicts  # the manifest declares version-contract specs to scan
    assert not rejected(verdicts)


def test_auto_upgrade_fixture_is_rejected() -> None:
    # Acceptance ① — the fixture's Isaac pins use >= and ~=; both must be caught.
    caught = rejected(scan_manifest(load_fixture("range_operators.yaml")))
    caught_sites = {v.where for v in caught}
    assert caught_sites == {"pins.isaac_sim", "pins.isaac_lab"}


def test_blocker_scopes_to_specs_only() -> None:
    # commit_sha / resolved pins carry no `spec` and are not the blocker's to police
    # (they are upstream-owned references, not version-contract specifiers).
    verdicts = scan_manifest(load_manifest())
    scanned = {v.where for v in verdicts}
    assert scanned == {"pins.isaac_sim", "pins.isaac_lab"}
