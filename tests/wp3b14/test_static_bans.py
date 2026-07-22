"""WP-3B-14 acceptance ④ — the vendor is named correctly, and the static bans bite.

The device is an ESP32-S3 based USB encoder module (Espressif VID 0x303A), not an
"M5Stack" (FR-TEL-065): the wrong vendor name must appear nowhere in the package, and
the GUI descriptor must name the true silicon. This also proves the whole static-check
machinery is clean over the package and non-vacuous on control fixtures.
"""

from __future__ import annotations

from pathlib import Path

from backend.teleop.ker import (
    KER_FORCE_FEEDBACK_UNAVAILABLE_NOTICE,
    KER_UI_LABEL,
    RULE_CLI_SPAWN,
    RULE_INTREE_LOOP_IMPORT,
    check_package,
    check_source,
    scan_forbidden_token,
)

_KER_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "backend" / "teleop" / "ker"

# Assembled from parts so this test file itself never contains the literal it forbids,
# which would make the package scan below trip on the test rather than the source.
_FORBIDDEN_VENDOR = "M5" + "Stack"


def test_package_is_clean_under_every_static_ban() -> None:
    """No CAN, IK, in-tree-loop, spawn, or re-implementation violation in the package."""
    assert check_package(_KER_PACKAGE_ROOT) == ()


def test_package_never_names_the_wrong_vendor() -> None:
    """The forbidden vendor token appears on no line of the KER package."""
    assert scan_forbidden_token(_KER_PACKAGE_ROOT, _FORBIDDEN_VENDOR) == ()


def test_forbidden_token_scan_is_not_vacuous(tmp_path: Path) -> None:
    """The scan reports a line that does name the forbidden vendor."""
    fixture = tmp_path / "mislabelled.py"
    fixture.write_text(f'LABEL = "{_FORBIDDEN_VENDOR} encoder"\n', encoding="utf-8")
    findings = scan_forbidden_token(tmp_path, _FORBIDDEN_VENDOR)
    assert len(findings) == 1
    assert findings[0].line == 1


def test_gui_descriptor_names_the_true_silicon() -> None:
    """The GUI label names the ESP32-S3 module and never the wrong vendor."""
    assert "ESP32-S3" in KER_UI_LABEL
    assert _FORBIDDEN_VENDOR not in KER_UI_LABEL


def test_force_feedback_notice_states_the_hardware_fact() -> None:
    """The GUI notice states bilateral force feedback is impossible on the KER (⑤)."""
    assert KER_FORCE_FEEDBACK_UNAVAILABLE_NOTICE
    assert "KER" in KER_FORCE_FEEDBACK_UNAVAILABLE_NOTICE


def test_spawn_and_intree_loop_bans_are_not_vacuous() -> None:
    """Shelling out or importing an in-tree loop trips the plugin-discipline bans."""
    assert any(v.rule == RULE_CLI_SPAWN for v in check_source("import subprocess\n"))
    assert any(v.rule == RULE_CLI_SPAWN for v in check_source("import os\nos.system('x')\n"))
    assert any(
        v.rule == RULE_INTREE_LOOP_IMPORT
        for v in check_source("import lerobot.scripts.lerobot_record\n")
    )
