"""Acceptance ④ (report side): a real `systemd-analyze security` verdict, attached as evidence.

`systemd-analyze security --offline=true` scores the unit *file* on this host exactly as it would
on the robot, so the report is genuine here — it is captured, written to the evidence tree, and
asserted to show the sandbox actually took (not merely that the directives are text). A comparison
against a bare unit proves the directives move the exposure score, which a presence-only check
could never establish.

If `systemd-analyze` is not installed the test skips with a reason rather than fabricating a score.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ops.acl.policy import WRITER_UNIT_FILENAME
from ops.acl.security_report import (
    run_security_analysis,
    systemd_analyze_available,
    write_report,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_UNITS = _REPO_ROOT / "ops" / "acl" / "units"
_EVIDENCE_DIR = _REPO_ROOT / "registry" / "build" / "evidence" / "CG-OPS-01d"
_KNOWN_LEVELS = {"OK", "MEDIUM", "EXPOSED", "UNSAFE", "DANGEROUS", "HAPPY"}

pytestmark = pytest.mark.skipif(
    not systemd_analyze_available(),
    reason="systemd-analyze is not installed; the sandbox verdict cannot be produced on this host",
)


def test_shipped_writer_report_is_captured_and_hardened() -> None:
    """The analyzer scores the writer, confirms the load-bearing directives, and is attached."""
    report = run_security_analysis(_UNITS / WRITER_UNIT_FILENAME)

    assert report.exposure_level in _KNOWN_LEVELS
    assert report.exposure_score >= 0.0

    # The mandatory-layer directives must register as applied in the analyzer's own view.
    for fragment in ("AF_(INET|INET6)", "User=", "NoNewPrivileges=", "ProtectSystem="):
        finding = report.finding(fragment)
        assert finding is not None, f"analyzer reported no {fragment} finding"
        assert finding.applied, f"{fragment} is not applied in the analyzer's view"

    written = write_report(report, _EVIDENCE_DIR / "security-openarm-can-writer.txt")
    assert written.is_file()
    assert "Overall exposure level" in written.read_text(encoding="utf-8")


def test_sandbox_directives_lower_exposure_versus_bare_unit(tmp_path: Path) -> None:
    """The sandbox is not cosmetic: it scores materially safer than a bare unit."""
    bare = tmp_path / "bare.service"
    bare.write_text("[Service]\nExecStart=/bin/true\n", encoding="utf-8")

    hardened = run_security_analysis(_UNITS / WRITER_UNIT_FILENAME)
    baseline = run_security_analysis(bare)

    # Lower exposure is safer; the hardened unit must be well below the bare one.
    assert hardened.exposure_score < baseline.exposure_score
