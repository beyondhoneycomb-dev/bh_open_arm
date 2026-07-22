"""Acceptance ③ ⑥ ⑦ ⑧ ⑫: detection method, accel gate, octomap scan, teleop notice, GMO gate.

The octomap scan runs over the real code tree and must find zero live references; this is the
static proof FR-SAF-012's deprecation left nothing behind. The friction/GMO gate reflects the
committed state — no `friction.yaml` — so GMO is inactive by default (⑫).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.safety_bringup import (
    DEFAULT_DETECTION_METHOD,
    DetectionMethod,
    ResidualDetectionRefusedError,
    assert_teleop_notice_present,
    enable_residual_detection,
    gmo_active_default,
    scan_octomap_symbols,
    teleop_precheck_notice,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = (
    REPO_ROOT / "backend",
    REPO_ROOT / "packages",
    REPO_ROOT / "sim",
    REPO_ROOT / "contracts",
    REPO_ROOT / "ops",
    REPO_ROOT / "dashboard",
)
SCAN_EXCLUDE = (REPO_ROOT / "backend" / "safety_bringup",)


def test_default_detection_method_is_momentum_observer() -> None:
    # ⑥: the default detection method is MOMENTUM_OBSERVER.
    assert DEFAULT_DETECTION_METHOD is DetectionMethod.MOMENTUM_OBSERVER


def test_residual_detection_refused_without_accel_limit() -> None:
    # ③: a residual-based method with the accel limit inactive is refused.
    for method in (DetectionMethod.MOMENTUM_OBSERVER, DetectionMethod.TORQUE_RESIDUAL):
        with pytest.raises(ResidualDetectionRefusedError):
            enable_residual_detection(method, accel_limit_active=False)


def test_residual_detection_allowed_with_accel_limit() -> None:
    # ③: with the accel limit active the same activation is admitted.
    enable_residual_detection(DetectionMethod.MOMENTUM_OBSERVER, accel_limit_active=True)


def test_current_limit_method_needs_no_accel_limit() -> None:
    # CURRENT_LIMIT is not residual-based, so the accel-limit precondition does not apply.
    enable_residual_detection(DetectionMethod.CURRENT_LIMIT, accel_limit_active=False)


def test_octomap_symbols_are_absent_from_code_tree() -> None:
    # ⑦: the deprecated octomap pipeline left zero live references.
    assert scan_octomap_symbols(SCAN_ROOTS, SCAN_EXCLUDE) == []


def test_octomap_scan_finds_a_planted_reference(tmp_path: Path) -> None:
    # The scan is not vacuous: a planted octomap symbol is found.
    planted = tmp_path / "leftover.py"
    planted.write_text("updater = PointCloudOctomapUpdater()\n", encoding="utf-8")
    references = scan_octomap_symbols((tmp_path,), ())
    assert len(references) == 1
    assert references[0].symbol == "PointCloudOctomapUpdater"


def test_teleop_notice_is_present() -> None:
    # ⑧: the teleop QP-IK "no pre-collision check" notice exists.
    assert_teleop_notice_present((teleop_precheck_notice(),))


def test_teleop_notice_absence_is_refused() -> None:
    with pytest.raises(ValueError, match="pre-collision"):
        assert_teleop_notice_present(("some other tooltip",))


def test_gmo_inactive_without_friction_yaml(tmp_path: Path) -> None:
    # ⑫: absent friction.yaml => GMO inactive by default.
    assert gmo_active_default(tmp_path / "friction.yaml") is False


def test_gmo_inactive_with_zero_byte_friction_yaml(tmp_path: Path) -> None:
    # ⑫: a zero-byte friction.yaml is the un-established state — GMO stays inactive.
    empty = tmp_path / "friction.yaml"
    empty.write_text("", encoding="utf-8")
    assert gmo_active_default(empty) is False


def test_gmo_active_once_friction_established(tmp_path: Path) -> None:
    established = tmp_path / "friction.yaml"
    established.write_text("joint1: 0.1\n", encoding="utf-8")
    assert gmo_active_default(established) is True
