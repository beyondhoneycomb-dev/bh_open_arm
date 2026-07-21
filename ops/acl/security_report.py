"""Run `systemd-analyze security` against a unit and capture the report (acceptance ④).

`systemd-analyze security --offline=true` evaluates a unit *file* without loading it, so the
sandbox can be scored on this dev host exactly as it would be on the robot. Acceptance ④ asks
for two things and this module produces both: proof the sandbox directives are present and
sound (that is `staticcheck`), and the analyzer's own verdict attached as evidence (that is
this module — the real report, its overall exposure score, and the per-directive findings that
show `RestrictAddressFamilies`, `User`, `NoNewPrivileges` and `ProtectSystem` actually took).

Nothing here is faked when the tool is missing: `systemd_analyze_available()` lets the caller
skip with a reason rather than fabricate a score.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_SYSTEMD_ANALYZE = "systemd-analyze"
_OVERALL = re.compile(r"Overall exposure level for .+?:\s+([0-9]+(?:\.[0-9]+)?)\s+(\S+)")


@dataclass(frozen=True)
class DirectiveFinding:
    """One directive line from the analyzer's per-directive breakdown.

    Attributes:
        name: The directive name as the analyzer prints it (`RestrictAddressFamilies=~…`).
        applied: Whether the analyzer considers the hardening applied (its `set` field).
        exposure: The exposure weight the analyzer assigns, or None when it contributes none.
        description: The analyzer's human-readable description.
    """

    name: str
    applied: bool
    exposure: float | None
    description: str


@dataclass(frozen=True)
class SecurityReport:
    """The captured result of one `systemd-analyze security` run.

    Attributes:
        unit_name: The unit file's name.
        exposure_score: The overall exposure score (lower is safer).
        exposure_level: The label the analyzer attaches (`OK`, `MEDIUM`, …).
        findings: Every per-directive finding, in analyzer order.
        raw_text: The full human-readable report, kept verbatim as the attached evidence.
    """

    unit_name: str
    exposure_score: float
    exposure_level: str
    findings: tuple[DirectiveFinding, ...]
    raw_text: str

    def finding(self, name_fragment: str) -> DirectiveFinding | None:
        """Return the first finding whose name contains a fragment.

        Args:
            name_fragment: Substring to match against finding names.

        Returns:
            (DirectiveFinding | None) The first match, or None.
        """
        for item in self.findings:
            if name_fragment in item.name:
                return item
        return None


def systemd_analyze_available() -> bool:
    """Whether `systemd-analyze` is on PATH.

    Returns:
        (bool) True when the tool can be invoked.
    """
    return shutil.which(_SYSTEMD_ANALYZE) is not None


def _run(unit_path: Path, extra: list[str]) -> str:
    """Invoke `systemd-analyze security --offline=true` and return its stdout.

    Args:
        unit_path: Path to the unit file to analyze.
        extra: Extra arguments (e.g. `--json=short`).

    Returns:
        (str) Captured stdout.
    """
    completed = subprocess.run(
        [_SYSTEMD_ANALYZE, "security", "--offline=true", "--no-pager", *extra, str(unit_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def _parse_findings(json_text: str) -> tuple[DirectiveFinding, ...]:
    """Parse the analyzer's `--json=short` array into findings.

    Args:
        json_text: The JSON stdout.

    Returns:
        (tuple[DirectiveFinding, ...]) One finding per directive.
    """
    findings: list[DirectiveFinding] = []
    for item in json.loads(json_text):
        raw_exposure = item.get("exposure")
        findings.append(
            DirectiveFinding(
                name=str(item["name"]),
                applied=bool(item["set"]),
                exposure=float(raw_exposure) if raw_exposure not in (None, "") else None,
                description=str(item.get("description", "")),
            )
        )
    return tuple(findings)


def run_security_analysis(unit_path: Path) -> SecurityReport:
    """Run the analyzer against a unit and capture score, level and per-directive findings.

    Args:
        unit_path: Path to the `.service` unit to analyze.

    Returns:
        (SecurityReport) The parsed report plus the verbatim text.

    Raises:
        RuntimeError: If the analyzer output has no parsable overall-exposure line.
    """
    text = _run(unit_path, [])
    findings = _parse_findings(_run(unit_path, ["--json=short"]))
    match = _OVERALL.search(text)
    if match is None:
        raise RuntimeError(f"no overall exposure line in systemd-analyze output for {unit_path}")
    return SecurityReport(
        unit_name=unit_path.name,
        exposure_score=float(match.group(1)),
        exposure_level=match.group(2),
        findings=findings,
        raw_text=text,
    )


def write_report(report: SecurityReport, destination: Path) -> Path:
    """Write the verbatim analyzer report to disk as attachable evidence.

    Args:
        report: The captured report.
        destination: File to write; missing parents are created.

    Returns:
        (Path) The path written.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(report.raw_text, encoding="utf-8")
    return destination
