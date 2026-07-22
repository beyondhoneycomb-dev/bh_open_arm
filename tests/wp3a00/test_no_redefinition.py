"""WP-3A-00 ② — the no-primitive-redefinition scan bites, and only on redefinitions.

`02b` §5.2 WP-3A-00 ② requires a static check proving the five consuming schemas
(`CTR-CAM`..`CTR-REC`) redefine zero primitives, with the named example: a CAP
schema that declares its own timestamp domain must fail. The consumers do not
exist yet, so the scan is proven here by synthetic consumer modules — one that
forks primitives (must fire) and one that only imports them (must stay silent).

If this scan cannot fail, "single definition point" is a declaration, not a lock.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import contracts.prim as prim


def _write(path: Path, source: str) -> Path:
    """Write a synthetic consumer module and return its path."""
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def test_cap_declaring_its_own_timestamp_domain_fires(tmp_path: Path) -> None:
    """The named example: a CAP schema that restates the timestamp domain must fail."""
    cap = _write(
        tmp_path / "cap_schema.py",
        """
        from contracts.prim import CameraSlotKey

        # CAP forking the timestamp primitive instead of importing it.
        CLOCK_SOURCE = "CLOCK_REALTIME"

        class TimestampDomain:
            CAPTURE = "capture"
        """,
    )
    hits = prim.check_no_redefinition([cap])
    assert {h.symbol for h in hits} == {"CLOCK_SOURCE", "TimestampDomain"}
    assert {h.kind for h in hits} == {"assign", "class"}


def test_cam_redefining_the_slot_key_fires(tmp_path: Path) -> None:
    """A CAM schema that defines its own `CameraSlotKey` has forked the identifier."""
    cam = _write(
        tmp_path / "cam_schema.py",
        """
        class CameraSlotKey:
            def __init__(self, value: str) -> None:
                self.value = value
        """,
    )
    hits = prim.check_no_redefinition([cam])
    assert [h.symbol for h in hits] == ["CameraSlotKey"]


def test_consumer_that_only_imports_is_silent(tmp_path: Path) -> None:
    """A schema that imports every primitive and defines its own new names is clean."""
    good = _write(
        tmp_path / "rec_schema.py",
        """
        from contracts.prim import (
            CameraSlotKey,
            CaptureTimestamp,
            ClockRole,
            ErrorEnvelope,
            FrameType,
            QueueSemantics,
        )

        # Consumer-owned names that are NOT primitives are allowed.
        REC_FEATURE_COUNT = 5

        def rec_image_key(slot: CameraSlotKey) -> str:
            return slot.image_key()
        """,
    )
    assert prim.check_no_redefinition([good]) == []


def test_tuple_assignment_of_a_reserved_name_fires(tmp_path: Path) -> None:
    """A reserved name bound inside a tuple unpacking is still a redefinition."""
    module = _write(
        tmp_path / "tel_schema.py",
        """
        FrameType, other = object(), object()
        """,
    )
    hits = prim.check_no_redefinition([module])
    assert [h.symbol for h in hits] == ["FrameType"]


def test_annotated_assignment_of_a_reserved_name_fires(tmp_path: Path) -> None:
    """An annotated reassignment of a reserved constant is a redefinition."""
    module = _write(
        tmp_path / "ws_schema.py",
        """
        CLOCK_SOURCE: str = "CLOCK_BOOTTIME"
        """,
    )
    hits = prim.check_no_redefinition([module])
    assert [h.symbol for h in hits] == ["CLOCK_SOURCE"]


def test_reserved_set_covers_all_six_primitives() -> None:
    """The reserved set names a symbol from each of the six primitives, so each is guarded."""
    reserved = prim.RESERVED_PRIMITIVE_SYMBOLS
    assert "CameraSlotKey" in reserved  # camera identifier
    assert {"ClockRole", "CLOCK_SOURCE", "EXPIRY_JUDGE_ROLE", "TimestampDomain"} <= reserved
    assert "FrameType" in reserved  # frame type
    assert {"DropPolicy", "DropClassification", "QueueSemantics"} <= reserved  # queue
    assert "ErrorEnvelope" in reserved  # error envelope
