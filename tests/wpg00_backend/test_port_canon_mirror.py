"""The declared port map against the two spec tables that own the numbers.

`01` §2.17 and `14` §2.1 are where the ports were decided, and they stay the canon. The YAML
beside the loader is the machine-readable copy the browser is served, and a copy that drifts
from its source is exactly the "third truth" S-13's own type comment forbids.

The comparison is over ports rather than component names because the two tables name the same
things differently — "웹 백엔드 (SPA 정적 + REST + WebSocket)" in one, "브라우저 SPA ↔ GUI
백엔드" in the other. The ports are what both tables agree on, and what a compare view is about.
"""

from __future__ import annotations

import re
from pathlib import Path

from contracts.ports import load_port_canon

_SPEC = Path(__file__).resolve().parents[2] / "docs" / "v1" / "spec"
ARCHITECTURE_PORT_TABLE = (_SPEC / "01-시스템-아키텍처.md", "### 2.17 포트 맵")
OPERATIONS_PORT_TABLE = (_SPEC / "14-시스템-운영.md", "**프로세스·포트 맵")

# A port cell in either table, with or without the bold markers the specs use for emphasis.
# Four digits because every declared port is in the 1024-65535 range and written out in full.
_PORT_CELL = re.compile(r"\|\s*\*{0,2}(\d{4})\*{0,2}\s*\|")


def _ports_in_table(path: Path, heading: str) -> set[int]:
    """Every port number in the markdown table that follows a heading.

    The table is read from the heading to the first blank line after its rows, so a port
    mentioned in the prose below it — the 8000-conflict warning both tables carry — is not
    counted as a declaration.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(heading))
    ports: set[int] = set()
    seen_row = False
    for line in lines[start:]:
        if line.startswith("|"):
            seen_row = True
            ports.update(int(match) for match in _PORT_CELL.findall(line))
        elif seen_row and not line.strip():
            break
    return ports


def test_the_declaration_carries_exactly_the_ports_the_two_tables_declare() -> None:
    declared = {row.port for row in load_port_canon() if row.port is not None}
    from_spec = _ports_in_table(*ARCHITECTURE_PORT_TABLE) | _ports_in_table(*OPERATIONS_PORT_TABLE)

    assert declared == from_spec


def test_the_scan_actually_finds_rows_in_both_tables() -> None:
    """A mirror over an empty set passes for the wrong reason.

    Both halves are asserted non-empty, because a heading that moved would leave this test
    comparing nothing to nothing and reporting agreement.
    """
    assert len(_ports_in_table(*ARCHITECTURE_PORT_TABLE)) >= 5
    assert len(_ports_in_table(*OPERATIONS_PORT_TABLE)) >= 5


def test_the_component_with_no_network_boundary_is_declared_rather_than_omitted() -> None:
    """`14` §2.1 states the backend-to-hardware hop is in-process, and the compare view
    renders that as "no port expected" rather than as a binding that went missing."""
    assert any(row.port is None for row in load_port_canon())
