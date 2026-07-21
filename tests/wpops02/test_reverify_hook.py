"""The re-verification hook re-runs ①④ against real captures, and compares — not asserts.

Acceptances ① (link parameters after boot) and ④ (ten-reboot determinism) are deferred to
hardware. The hook re-runs the identical evaluators — WP-0B-02's link parser and WP-0B-05's
determinism evaluator — on a supplied capture and checks each result against a recorded
expectation. These tests drive it with synthetic captures so the machinery is proven here:
a correct capture matches, a recorded expectation that disagrees is caught, and a partial
capture checks only what it has.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ops.systemd.constants import INTERFACE_NAMES
from ops.systemd.reverify import (
    FIXTURE_ENV_VAR,
    fixture_dir_from_env,
    reverify_from_fixture,
)

_GOOD_LINKSHOW = (
    "3: {name}: <NOARP,UP,LOWER_UP,ECHO> mtu 72 qdisc pfifo_fast "
    "state UP mode DEFAULT group default qlen 1000\n"
    "    link/can  promiscuity 0\n"
    "    can <FD,TDC-AUTO> state ERROR-ACTIVE (berr-counter tx 0 rx 0) restart-ms 100\n"
    "          bitrate 1000000 sample-point 0.750\n"
    "          dbitrate 5000000 dsample-point 0.750\n"
)
_BAD_LINKSHOW = (
    "3: {name}: <NOARP,UP,LOWER_UP,ECHO> mtu 16 qdisc pfifo_fast "
    "state UP mode DEFAULT group default qlen 10\n"
    "    link/can  promiscuity 0\n"
    "    can state ERROR-ACTIVE (berr-counter tx 0 rx 0) restart-ms 100\n"
    "          bitrate 500000 sample-point 0.750\n"
)

_STABLE_KEYS = {name: f"channel:{index}" for index, name in enumerate(INTERFACE_NAMES)}
_REQUIRED_CYCLES = 10


def _write_linkshow(capture: Path, template: str) -> None:
    """Write one link-show dump per fixed name using the given template."""
    linkshow = capture / "linkshow"
    linkshow.mkdir(parents=True, exist_ok=True)
    for name in INTERFACE_NAMES:
        (linkshow / f"{name}.txt").write_text(template.format(name=name), encoding="utf-8")


def _write_reboots(capture: Path, drift: bool) -> None:
    """Write a ten-boot log; when `drift` one later boot rebinds a name to another channel."""
    boots = []
    for index in range(_REQUIRED_CYCLES):
        bindings = dict(_STABLE_KEYS)
        if drift and index == _REQUIRED_CYCLES - 1:
            bindings[INTERFACE_NAMES[0]] = "channel:moved"
        boots.append({"reboot_index": index, "bindings": bindings})
    (capture / "reboots.json").write_text(json.dumps(boots), encoding="utf-8")


def _write_expected(capture: Path, expected: dict[str, bool]) -> None:
    """Write the recorded truth the hook compares against."""
    (capture / "expected.json").write_text(json.dumps(expected), encoding="utf-8")


def test_good_capture_matches_recorded_truth(tmp_path: Path) -> None:
    """A correct boot capture matches an expectation of all-green, checking both keys."""
    _write_linkshow(tmp_path, _GOOD_LINKSHOW)
    _write_reboots(tmp_path, drift=False)
    _write_expected(tmp_path, {"link_ok": True, "determinism_stable": True})
    report = reverify_from_fixture(tmp_path)
    assert report.matched
    assert set(report.checked) == {"link_ok", "determinism_stable"}


def test_bad_capture_matches_a_recorded_false(tmp_path: Path) -> None:
    """A mis-set link and drifting reboots match an expectation that recorded them false."""
    _write_linkshow(tmp_path, _BAD_LINKSHOW)
    _write_reboots(tmp_path, drift=True)
    _write_expected(tmp_path, {"link_ok": False, "determinism_stable": False})
    report = reverify_from_fixture(tmp_path)
    assert report.matched


def test_hook_catches_a_wrong_expectation(tmp_path: Path) -> None:
    """A good capture against an expectation of false is a mismatch — the hook compares."""
    _write_linkshow(tmp_path, _GOOD_LINKSHOW)
    _write_reboots(tmp_path, drift=False)
    _write_expected(tmp_path, {"link_ok": False, "determinism_stable": True})
    report = reverify_from_fixture(tmp_path)
    assert not report.matched
    assert any("link_ok" in line for line in report.mismatches)


def test_partial_capture_checks_only_present_keys(tmp_path: Path) -> None:
    """An expectation naming only link_ok evaluates link_ok and stays silent on determinism."""
    _write_linkshow(tmp_path, _GOOD_LINKSHOW)
    _write_expected(tmp_path, {"link_ok": True})
    report = reverify_from_fixture(tmp_path)
    assert report.checked == ("link_ok",)
    assert report.matched


def test_missing_expected_is_an_error(tmp_path: Path) -> None:
    """A capture with no expected.json cannot be re-verified against anything."""
    _write_linkshow(tmp_path, _GOOD_LINKSHOW)
    with pytest.raises(FileNotFoundError):
        reverify_from_fixture(tmp_path)


def test_fixture_dir_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The hook discovers a capture directory from the environment, or None when unset."""
    monkeypatch.delenv(FIXTURE_ENV_VAR, raising=False)
    assert fixture_dir_from_env() is None
    monkeypatch.setenv(FIXTURE_ENV_VAR, str(tmp_path))
    assert fixture_dir_from_env() == tmp_path
