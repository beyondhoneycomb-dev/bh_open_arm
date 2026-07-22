"""Acceptance ①: the record loop is in-process — no process is spawned.

The proof is static (`02b` §6.2 WP-3B-11): the embed tree references none of the
process-spawn mechanisms nor the record console-script module, so there is no way
left to launch it as a subprocess or to invoke its robot-reconnecting CLI path.
The scan must also *bite* — a fixture that imports `subprocess`, spawns via `os`,
or imports the record script is caught — or a clean result proves nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.recorder.embed import scan_source, scan_tree

EMBED_TREE = Path("backend/recorder/embed")


def test_embed_tree_spawns_no_process() -> None:
    """The real embed tree carries no spawn mechanism or record-script import."""
    assert scan_tree(EMBED_TREE) == []


SPAWN_VIOLATIONS = [
    "import subprocess\n",
    "from subprocess import Popen\n",
    "import subprocess\nsubprocess.Popen(['lerobot-record'])\n",
    "import os\nos.system('lerobot-record')\n",
    "import os\nos.spawnv(os.P_NOWAIT, 'x', ['x'])\n",
    "from os import system\nsystem('x')\n",
    "import pty\n",
    "import lerobot.scripts.lerobot_record\n",
    "from lerobot.scripts.lerobot_record import record\n",
]


@pytest.mark.parametrize("source", SPAWN_VIOLATIONS)
def test_scan_bites_on_a_spawn(source: str) -> None:
    """Every process-spawn or record-script fixture is caught, not passed over."""
    assert scan_source(Path("violation.py"), source)


def test_scan_reports_line_of_the_offending_reference() -> None:
    """A finding points at the offending source line, for a usable report."""
    source = "import time\nimport subprocess\n"
    findings = scan_source(Path("violation.py"), source)
    assert [finding.line for finding in findings] == [2]
