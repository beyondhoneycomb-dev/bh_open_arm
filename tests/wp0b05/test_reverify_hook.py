"""The real-fixture re-verification hook (plan 02a §4.1).

Two things are proven here. First, that the hook *logic* runs end to end — parser →
measurement → ethtool → determinism → comparison — by pointing it at a capture directory
assembled from the synthetic corpus. Second, that the true hardware path stays honest: the
bound acceptance skips with a reason until a directory of real captures is named via
`OPENARM_UDEV_REAL_FIXTURE`, and re-runs the identical hook against it the moment one is.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from ops.hw.udev.reverify import (
    FIXTURE_ENV_VAR,
    READABLE_EXPECTATION_FIELDS,
    fixture_dir_from_env,
    reverify_from_fixture,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _assemble_capture(destination: Path, *, determinism_source: str, expected_stable: bool) -> Path:
    """Build a capture directory in the shape the hook consumes.

    Args:
        destination: Root to build under.
        determinism_source: Which reboot fixture to copy in as `reboots.json`.
        expected_stable: The determinism verdict recorded in `expected.json`.

    Returns:
        (Path) The assembled capture directory.
    """
    udevadm = destination / "udevadm"
    ethtool = destination / "ethtool"
    udevadm.mkdir(parents=True)
    ethtool.mkdir(parents=True)
    for name in ("can0_serial.txt", "can1_serial.txt", "can2_serial.txt", "can3_serial.txt"):
        shutil.copy(_FIXTURES / "udevadm" / name, udevadm / name)
    shutil.copy(_FIXTURES / "ethtool" / "gs_usb.txt", ethtool / "can0.txt")
    shutil.copy(_FIXTURES / "reboots" / determinism_source, destination / "reboots.json")
    (destination / "expected.json").write_text(
        json.dumps(
            {
                "serial_shared": True,
                "dev_id_distinguishes": True,
                "all_in_tree": True,
                "determinism_stable": expected_stable,
            }
        ),
        encoding="utf-8",
    )
    return destination


def test_hook_reruns_every_check_on_a_capture(tmp_path: Path) -> None:
    """Pointed at a full capture, the hook re-runs and confirms each recorded expectation."""
    capture = _assemble_capture(
        tmp_path / "cap", determinism_source="stable.json", expected_stable=True
    )
    report = reverify_from_fixture(capture)
    assert report.matched is True
    assert set(report.checked) == {
        "serial_shared",
        "dev_id_distinguishes",
        "all_in_tree",
        "determinism_stable",
    }
    assert report.mismatches == ()


def test_hook_flags_a_capture_whose_expectation_is_wrong(tmp_path: Path) -> None:
    """A capture that drifted but claims stability is caught — the hook is not a rubber stamp."""
    capture = _assemble_capture(
        tmp_path / "cap", determinism_source="drift.json", expected_stable=True
    )
    report = reverify_from_fixture(capture)
    assert report.matched is False
    assert any("determinism_stable" in mismatch for mismatch in report.mismatches)


def test_an_empty_expectation_is_a_mismatch_not_a_match(tmp_path: Path) -> None:
    """`expected.json` of `{}` compares nothing, and nothing compared is not agreement."""
    capture = tmp_path / "cap"
    (capture / "udevadm").mkdir(parents=True)
    shutil.copy(_FIXTURES / "udevadm" / "can0_serial.txt", capture / "udevadm" / "can0.txt")
    (capture / "expected.json").write_text(json.dumps({}), encoding="utf-8")
    report = reverify_from_fixture(capture)
    assert report.matched is False
    assert report.checked == ()
    assert set(report.unchecked) == READABLE_EXPECTATION_FIELDS


def test_a_partial_capture_reports_what_it_could_not_settle(tmp_path: Path) -> None:
    """Whatever a capture omits comes back named, so `matched` cannot be read as full coverage.

    `checked` and `unchecked` partition the readable roster. A field evaluated by some branch
    but missing from `READABLE_EXPECTATION_FIELDS` breaks the partition here rather than
    quietly counting as coverage nobody offered.
    """
    capture = tmp_path / "cap"
    (capture / "udevadm").mkdir(parents=True)
    for name in ("can0_peak_hub_serial.txt", "can1_peak_hub_serial.txt"):
        shutil.copy(_FIXTURES / "udevadm" / name, capture / "udevadm" / name)
    (capture / "expected.json").write_text(
        json.dumps({"dev_id_distinguishes": True}), encoding="utf-8"
    )
    report = reverify_from_fixture(capture)
    assert report.matched is True
    assert report.checked == ("dev_id_distinguishes",)
    assert set(report.checked) | set(report.unchecked) == READABLE_EXPECTATION_FIELDS
    assert set(report.checked) & set(report.unchecked) == set()
    assert "serial_shared" in report.unchecked


@pytest.mark.skipif(
    FIXTURE_ENV_VAR not in os.environ,
    reason=(
        f"no real udev capture: set {FIXTURE_ENV_VAR} to a directory of real "
        "udevadm/ethtool/reboot captures to re-verify. The directory must also carry "
        "expected.json naming which claims it records — udevadm dumps alone raise "
        "FileNotFoundError, because a capture with no recorded expectation has nothing for the "
        "hook to disagree with. A capture from one two-channel adapter settles the channel "
        "axis only; serial sharing across adapters and the ten-reboot determinism come back "
        "in `unchecked` and stay deferred"
    ),
)
def test_reverify_against_real_capture() -> None:
    """Deferred acceptances ①②③⑤, to the extent the supplied capture records them.

    `matched` alone would let a capture recording one field read as the whole set, so the
    coverage the capture did not offer is asserted to be reported rather than absent.
    """
    fixture_dir = fixture_dir_from_env()
    assert fixture_dir is not None
    report = reverify_from_fixture(fixture_dir)
    assert report.matched, f"real-capture re-verification failed: {report.mismatches}"
    assert report.checked, "the capture recorded no readable expectation"
    assert set(report.checked) | set(report.unchecked) == READABLE_EXPECTATION_FIELDS
