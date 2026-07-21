"""Acceptance ⑦ — the asset report records the friction.yaml and re-parenting facts.

⑦ requires the 0-byte ``friction.yaml`` fact (v1 friction void) to be written into
the asset report as the reason path A has not started. The head-camera re-parenting
note and the exact fix sites are recorded alongside. The empirical half asserts
that any ``friction.yaml`` actually shipped in the installed asset trees is indeed
0 bytes, matching the recorded fact.
"""

from __future__ import annotations

from pathlib import Path

from tests.wp0c03 import AUDIT_MD


def _audit_text() -> str:
    return AUDIT_MD.read_text(encoding="utf-8")


def test_friction_yaml_void_fact_recorded() -> None:
    text = _audit_text()
    assert "friction.yaml" in text
    assert "0-byte" in text or "0 bytes" in text
    assert "PG-FRIC-001" in text


def test_reparenting_note_recorded() -> None:
    text = _audit_text()
    assert "need to adjust x after lifter link is adjusted" in text
    assert "openarm_lifter_link" in text
    assert "cell_head_reparented.xml" in text


def test_fix_sites_recorded() -> None:
    text = _audit_text()
    assert "openarm_left_joint7" in text
    assert "openarm_right_joint7" in text
    assert "motor_DM3507" in text
    assert "motor_DM4310" in text


def test_shipped_friction_yaml_is_empty_if_present() -> None:
    roots: list[Path] = []
    for module_name in ("openarm_mujoco", "openarm_control"):
        try:
            module = __import__(module_name)
        except ImportError:
            continue
        module_file = getattr(module, "__file__", None)
        if module_file is not None:
            roots.append(Path(module_file).resolve().parent)
        for entry in getattr(module, "__path__", []):
            roots.append(Path(entry).resolve())

    found = {path for root in roots for path in root.rglob("friction.yaml")}
    for path in found:
        assert path.stat().st_size == 0, f"{path} is not the 0-byte void-friction file"
