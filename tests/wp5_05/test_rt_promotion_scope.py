"""NORM-014 — no production path asks for real-time scheduling, and the scan can prove it.

The zero-count assertion at the bottom is worthless on its own: a scan that finds nothing because
it looks for nothing also reports zero. So the positive controls come first — each shape of
promotion request is planted in a fixture and the scan must find it — and the negative controls
pin the two things that must NOT count, since over-reporting would force the deletion of the
WP-0C-06 experiment that measures whether promotion helps at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.loadtest.rt_promotion_scope import (
    RT_POLICY_ATTRIBUTES,
    RT_PROMOTION_CALLS,
    scan_rt_promotion,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The shipped control path. `sim/` is absent on purpose: `sim/harness/rt_promotion.py` promotes
# deliberately for WP-0C-06's NFR-PRF-040 experiment, which NORM-014 leaves standing.
_PRODUCTION_ROOTS = (
    _REPO_ROOT / "backend",
    _REPO_ROOT / "ops",
    _REPO_ROOT / "packages",
    _REPO_ROOT / "contracts",
)

# The checker names the forbidden symbols to look for them, which is a definition, not a request.
_EXCLUDED = (_REPO_ROOT / "backend" / "loadtest" / "rt_promotion_scope.py",)

# A floor on how many files the production scan must reach before its zero count means anything.
# Well below the real count; it only has to be large enough that a mistyped root cannot clear it.
_MIN_SCANNED_FILES = 100


def _fixture(tmp_path: Path, body: str) -> Path:
    """Write a one-module scan root and return its directory."""
    root = tmp_path / "tree"
    root.mkdir()
    (root / "module.py").write_text(body, encoding="utf-8")
    return root


@pytest.mark.parametrize("call", RT_PROMOTION_CALLS)
def test_every_promotion_call_is_found(tmp_path: Path, call: str) -> None:
    """Each libc/os entry point that performs promotion is a finding, under either import style."""
    root = _fixture(tmp_path, f"import os\n\n\ndef go() -> None:\n    os.{call}(0, 1, 2)\n")

    sites = scan_rt_promotion((root,), ())

    assert [site.symbol for site in sites] == [call]


@pytest.mark.parametrize("call", RT_PROMOTION_CALLS)
def test_a_bare_import_cannot_hide_a_promotion_call(tmp_path: Path, call: str) -> None:
    """A bare import reduces to the same name, so the import style is not a bypass."""
    body = f"from os import {call}\n\n\ndef go() -> None:\n    {call}(0, 1, 2)\n"
    root = _fixture(tmp_path, body)

    sites = scan_rt_promotion((root,), ())

    assert [site.symbol for site in sites] == [call]


@pytest.mark.parametrize("policy", RT_POLICY_ATTRIBUTES)
def test_a_policy_attribute_is_found_even_without_a_call(tmp_path: Path, policy: str) -> None:
    """Reaching for `os.SCHED_FIFO` is a request in progress; a call site would complete it."""
    root = _fixture(tmp_path, f"import os\n\n\nPOLICY = os.{policy}\n")

    sites = scan_rt_promotion((root,), ())

    assert [site.symbol for site in sites] == [policy]


def test_a_promotion_nested_inside_a_branch_is_still_found(tmp_path: Path) -> None:
    """The walk is not depth-limited: burying the call one level deeper is not a bypass."""
    body = (
        "import os\n\n\n"
        "def go(flag: bool) -> None:\n"
        "    if flag:\n"
        "        try:\n"
        "            pass\n"
        "        finally:\n"
        "            os.sched_setscheduler(0, 1, 2)\n"
    )
    root = _fixture(tmp_path, body)

    sites = scan_rt_promotion((root,), ())

    assert [site.symbol for site in sites] == ["sched_setscheduler"]


def test_naming_a_policy_in_display_text_is_not_a_request(tmp_path: Path) -> None:
    """S-13 reports which policy a process runs under; reporting is what NORM-014 keeps."""
    body = 'BANNER = "process is SCHED_FIFO"\nNOTE = "sched_setscheduler was refused"\n'
    root = _fixture(tmp_path, body)

    assert scan_rt_promotion((root,), ()) == []


def test_an_excluded_path_is_not_scanned(tmp_path: Path) -> None:
    """Exclusion is what keeps the checker from reporting its own symbol list."""
    root = _fixture(tmp_path, "import os\n\n\ndef go() -> None:\n    os.mlockall(3)\n")

    assert scan_rt_promotion((root,), (root / "module.py",)) == []


def test_an_unparsable_file_is_raised_not_skipped(tmp_path: Path) -> None:
    """A skipped file would turn the total into a lower bound while still reading as zero."""
    root = _fixture(tmp_path, "def go(:\n")

    with pytest.raises(SyntaxError):
        scan_rt_promotion((root,), ())


def test_the_production_tree_asks_for_no_real_time_promotion() -> None:
    """NORM-014: zero promotion requests on the shipped control path.

    The roots are asserted to exist and to hold files first. `scan_rt_promotion` skips a root that
    is not there, so a renamed tree would turn this into a scan of nothing that still reads as a
    clean zero — the same shape of self-disarming check CI-09 carried when an empty glob expansion
    released a frozen contract's lock.
    """
    for root in _PRODUCTION_ROOTS:
        assert root.is_dir(), f"{root} is not a directory: the scan would silently cover nothing"
    scanned = sum(len(list(root.rglob("*.py"))) for root in _PRODUCTION_ROOTS)
    assert scanned > _MIN_SCANNED_FILES, f"only {scanned} files reached the scan"

    sites = scan_rt_promotion(_PRODUCTION_ROOTS, _EXCLUDED)

    assert sites == [], "\n".join(f"{s.path}:{s.line} {s.symbol}" for s in sites)


def test_the_measurement_harness_is_outside_the_scanned_roots() -> None:
    """The WP-0C-06 experiment must keep promoting, or NFR-PRF-040 has nothing to publish.

    Pinned as its own case so that widening `_PRODUCTION_ROOTS` to include `sim/` fails here with
    the reason, rather than failing the zero-count assertion above as an apparent regression.
    """
    harness = _REPO_ROOT / "sim" / "harness" / "rt_promotion.py"
    assert harness.is_file()

    found = scan_rt_promotion((harness.parent,), ())

    assert [site.symbol for site in found]
    assert not any(root in harness.parents for root in _PRODUCTION_ROOTS)
