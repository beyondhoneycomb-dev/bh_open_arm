"""Single-canon acceptance: a second registry definition in 13 is rejected.

Acceptance ⑩. 14 §2.10 is the sole canon; a document that asserts itself an
error-code registry (rather than pointing at doc 14) is a second definition. The
real spec 13 does not, and the canon is exempt from being its own second copy.
"""

from __future__ import annotations

from pathlib import Path

from contracts.errors.spec_scan import asserts_second_registry

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = REPO_ROOT / "docs" / "spec"
SPEC14 = SPEC_DIR / "14-시스템-운영.md"
SPEC13 = SPEC_DIR / "13-GUI-화면-명세.md"

# The canon's self-declaration phrase; a fixture doc 13 that carries it without
# naming doc 14 is asserting a second registry.
_SECOND_REGISTRY_DOC = (
    "# 13 GUI\n\n## 3.4 에러\n\n이 §3.4가 에러코드 정본 레지스트리다.\n\n"
    "| 코드 | severity |\n|---|---|\n| OA-CAN-001 | ERROR |\n"
)
_REFERENCE_DOC = "# 13 GUI\n\n에러코드 정본 레지스트리는 14 §2.10이다.\n"


def test_real_spec13_is_not_a_second_registry() -> None:
    """The committed spec 13 does not define a second registry (no over-blocking)."""
    assert asserts_second_registry(SPEC13, SPEC14) is False


def test_canon_is_exempt() -> None:
    """14 §2.10 self-declaring the registry is not a second copy of itself."""
    assert asserts_second_registry(SPEC14, SPEC14) is False


def test_second_registry_in_13_is_rejected(tmp_path: Path) -> None:
    """A doc 13 asserting its own registry is caught (acceptance ⑩)."""
    fixture = tmp_path / "13-GUI.md"
    fixture.write_text(_SECOND_REGISTRY_DOC, encoding="utf-8")
    assert asserts_second_registry(fixture, SPEC14) is True


def test_a_reference_to_the_canon_is_allowed(tmp_path: Path) -> None:
    """Pointing at doc 14 is a reference, not a second registry (no over-blocking)."""
    fixture = tmp_path / "13-ref.md"
    fixture.write_text(_REFERENCE_DOC, encoding="utf-8")
    assert asserts_second_registry(fixture, SPEC14) is False
