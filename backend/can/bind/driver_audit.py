"""M-24 verdict: does `openarm_driver` open a CAN socket in-process?

`16` M-24 asks exactly one question — does `openarm_driver` open CAN in the same
process as LeRobot — and fixes the consequence: if it does, exclude it from our
canonical path. `01` FR-SYS-010 already records the mechanism as documentary
evidence (`openarm_driver` → pybind11 → `openarm_can::CANSocket`). This module
turns that into a *reproducible source reading*: given the package's `driver.py`
it scans for the constructs that open a CAN socket and cites the exact lines, so
the M-24 ledger row is backed by code, not by the spec's assertion alone.

On this host `openarm_driver` is neither installed nor vendored, so the reading
cannot run here; `audit_installed_package` records that honestly (`present=False`)
and the verdict is deferred to the re-verification hook (`reverify`), which
re-runs the identical scan the moment a real `driver.py` path is supplied. The
scan logic itself is exercised here against synthetic `driver.py` fixtures and
cross-checked against the one relevant package that *is* installed —
`openarm_control`, which FR-SYS-010 / M-24 assert opens no CAN — to prove the
scan does not merely answer "yes" to everything.
"""

from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path

# CAN-socket-opening evidence, as (compiled needle, why-it-counts). Each is a
# construct that only appears when a module opens or binds a CAN socket; a plain
# `.bind(` is deliberately excluded because it is not CAN-specific. `import can`
# is anchored to a statement so it does not match the substring inside `import
# candump_helpers`.
_CAN_EVIDENCE: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bCANSocket\b"), "constructs an openarm_can CANSocket"),
    (re.compile(r"\bopenarm_can\b"), "binds the openarm_can pybind11 CAN module"),
    (re.compile(r"\bAF_CAN\b|\bPF_CAN\b"), "opens an AF_CAN/PF_CAN raw socket"),
    (re.compile(r"\bsocketcan\b|\bSocketcanBus\b"), "opens a SocketCAN bus"),
    (re.compile(r"^\s*(?:import\s+can\b|from\s+can\b)"), "imports python-can"),
)


@dataclass(frozen=True)
class CitedLine:
    """One source line that is evidence of (or against) a CAN socket open.

    Attributes:
        line: 1-indexed line number in the audited source.
        text: The line's text, stripped, quoted verbatim in the verdict.
        reason: Which evidence needle matched, in plain words.
    """

    line: int
    text: str
    reason: str


@dataclass(frozen=True)
class M24Verdict:
    """The M-24 judgment for `openarm_driver`, ready to render as a ledger row.

    Attributes:
        present: Whether a `driver.py` was found and actually read on this host.
        opens_can: True/False when read; None when `present` is False and the
            question could not be settled here (deferred, not assumed either way).
        cited_lines: The evidence lines, empty when nothing was found or nothing
            was read.
        source_path: The `driver.py` that was read, or None when absent.
        summary: One-line human summary of the judgment.
    """

    present: bool
    opens_can: bool | None
    cited_lines: tuple[CitedLine, ...]
    source_path: str | None
    summary: str


def audit_driver_source(source: Path) -> M24Verdict:
    """Read one `driver.py` and judge whether it opens a CAN socket, citing lines.

    This is the reusable core: it makes no assumption about *which* `driver.py` it
    is handed, so the synthetic fixtures, the installed `openarm_control` cross
    check, and the deferred real `openarm_driver` all flow through it unchanged.

    Args:
        source: Path to a Python source file to read.

    Returns:
        (M24Verdict) `present=True`, `opens_can` set from whether any evidence
        line matched, with every matching line cited.
    """
    cited: list[CitedLine] = []
    for number, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        for needle, reason in _CAN_EVIDENCE:
            if needle.search(raw):
                cited.append(CitedLine(line=number, text=raw.strip(), reason=reason))
                break
    opens_can = bool(cited)
    if opens_can:
        summary = (
            f"opens CAN in-process (evidence at {source.name}:"
            f"{','.join(str(item.line) for item in cited)}) — exclude from canonical path"
        )
    else:
        summary = f"no CAN-socket-opening construct found in {source.name}"
    return M24Verdict(
        present=True,
        opens_can=opens_can,
        cited_lines=tuple(cited),
        source_path=str(source),
        summary=summary,
    )


def _find_driver_source(package: str) -> Path | None:
    """Locate a package's `driver.py`, if the package is importable on this host.

    Args:
        package: Top-level package name, e.g. `openarm_driver`.

    Returns:
        (Path | None) The `driver.py` under the package, or None when the package
        is not installed or ships no such file.
    """
    spec = importlib.util.find_spec(package)
    if spec is None or not spec.submodule_search_locations:
        return None
    for location in spec.submodule_search_locations:
        candidate = Path(location) / "driver.py"
        if candidate.is_file():
            return candidate
        matches = sorted(Path(location).rglob("driver.py"))
        if matches:
            return matches[0]
    return None


def audit_installed_package(package: str = "openarm_driver") -> M24Verdict:
    """Judge the installed `openarm_driver`, or record honestly that it is absent.

    When the package is not installed or vendored — the state on this dev host —
    the question cannot be settled here, so the verdict is `present=False`,
    `opens_can=None` (deferred, not assumed either way), and its summary points at
    the re-verification hook. When it *is* present, its `driver.py` flows through
    `audit_driver_source` and the verdict is a real, line-cited judgment.

    Args:
        package: Package to locate and read; defaults to the banned one.

    Returns:
        (M24Verdict) A read judgment when present, else an honest deferral record.
    """
    source = _find_driver_source(package)
    if source is None:
        return M24Verdict(
            present=False,
            opens_can=None,
            cited_lines=(),
            source_path=None,
            summary=(
                f"{package} not installed/vendored on this host; source reading deferred "
                "to reverify hook (OPENARM_DRIVER_SOURCE). Documentary evidence (01 "
                "FR-SYS-010): openarm_driver -> pybind11 -> openarm_can::CANSocket => "
                "exclude from canonical path pending source confirmation"
            ),
        )
    return audit_driver_source(source)


def render_m24_row(verdict: M24Verdict) -> str:
    """Render the M-24 ledger row from a verdict — the acceptance ② artifact.

    The row mirrors the `16` M-24 table shape (`| id | question | finding |
    action |`). Ownership keeps this WP out of `docs/spec/16`, so the updated row
    is produced as an artifact here rather than written into the spec prose.

    Args:
        verdict: The judgment to render.

    Returns:
        (str) A single Markdown table row stating finding and action.
    """
    question = "openarm_driver opens CAN in-process?"
    if verdict.opens_can is None:
        finding = "UNRESOLVED-HERE: package absent"
        action = "read driver.py via reverify hook; exclude from canonical path (01 FR-SYS-010)"
    elif verdict.opens_can:
        cites = ", ".join(f"{item.line}:{item.text}" for item in verdict.cited_lines)
        finding = f"RESOLVED: opens CAN [{cites}]"
        action = "EXCLUDED from canonical path (01 FR-SYS-010)"
    else:
        finding = "RESOLVED: no CAN-socket open found in driver.py"
        action = "no double-bind exclusion required on this evidence"
    return f"| M-24 | {question} | {finding} | {action} |"
