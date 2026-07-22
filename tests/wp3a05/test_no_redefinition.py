"""CTR-REC@v1 consumes the primitives — it never restates one (`02b` §5.0b/§5.2 ②).

The central 3A discipline: `CTR-CAM`..`CTR-REC` import the six shared primitives
from `contracts.prim` and must not redefine any. This file proves it two ways for
the recorder: the real module redefines nothing, and the static scan still bites —
a synthetic recorder that forks a primitive (its own camera identifier, its own
timestamp domain) is caught, while one that only imports stays silent. Without the
biting half, "no redefinition" would be a claim rather than a lock.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from contracts.prim import check_no_redefinition, scan_module

RECORDER_SOURCES = (
    Path("contracts/recorder/schema.py"),
    Path("contracts/recorder/__init__.py"),
)


def _write(path: Path, source: str) -> Path:
    """Write a synthetic consumer module and return its path."""
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def test_real_recorder_redefines_no_primitive() -> None:
    """The shipped recorder contract restates zero frozen primitives (`02b` §5.2 ②)."""
    assert check_no_redefinition(list(RECORDER_SOURCES)) == []


def test_scan_bites_on_a_forked_camera_identifier(tmp_path: Path) -> None:
    """A recorder that declares its own CameraSlotKey is caught (the named defect)."""
    forked = _write(
        tmp_path / "forked_camera.py",
        """
        from dataclasses import dataclass

        @dataclass
        class CameraSlotKey:
            value: str
        """,
    )
    hits = scan_module(forked)
    assert [hit.symbol for hit in hits] == ["CameraSlotKey"]
    assert hits[0].kind == "class"


def test_scan_bites_on_a_forked_timestamp_domain(tmp_path: Path) -> None:
    """A recorder that declares its own timestamp domain is caught (`02b` §5.2 ② example)."""
    forked = _write(
        tmp_path / "forked_clock.py",
        """
        CLOCK_SOURCE = "TAI"
        TimestampDomain = ("capture", "wall_clock")
        """,
    )
    assert {hit.symbol for hit in scan_module(forked)} == {"CLOCK_SOURCE", "TimestampDomain"}


def test_scan_is_silent_on_an_importing_consumer(tmp_path: Path) -> None:
    """Binding a primitive by import is the sanctioned path — the scan stays quiet."""
    importer = _write(
        tmp_path / "good_consumer.py",
        """
        from contracts.prim import CameraSlotKey, FrameType, TimestampDomain

        ALLOWED = (CameraSlotKey, FrameType, TimestampDomain)
        """,
    )
    assert scan_module(importer) == []
