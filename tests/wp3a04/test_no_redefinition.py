"""WP-3A-04 — the no-redefinition scan bites on a primitive fork and a lease-semantics fork.

`02b` §5.2 WP-3A-04 makes two forks build-blocking: a `CTR-PRIM@v1` primitive
redefinition (the shared 3A ban) and a lease-semantics redefinition (the WS's own
"same lease, two meanings" ban). If either scan cannot fail, the ban is a
declaration rather than a lock, so both are proven here against synthetic modules —
one that forks and must fire, one that only imports and must stay silent — and the
real `schema.py` is confirmed clean.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import contracts.ws as ws
import contracts.ws.schema as ws_schema
from contracts.ws.redefinition import RESERVED_LEASE_SEMANTICS_SYMBOLS


def _write(path: Path, source: str) -> Path:
    """Write a synthetic module and return its path."""
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def test_ws_redefining_a_primitive_fires(tmp_path: Path) -> None:
    """A WS module that restates a CTR-PRIM primitive is caught (the shared 3A ban)."""
    module = _write(
        tmp_path / "ws_schema.py",
        """
        from contracts.prim import ClockRole

        # A WS trying to move expiry ownership onto the client clock.
        EXPIRY_JUDGE_ROLE = ClockRole.CLIENT

        class CameraSlotKey:
            pass
        """,
    )
    hits = ws.check_ws_no_redefinition([module])
    assert {h.symbol for h in hits} == {"EXPIRY_JUDGE_ROLE", "CameraSlotKey"}


def test_ws_redefining_a_lease_semantics_type_fires(tmp_path: Path) -> None:
    """A module that defines its own DeadmanLease/RenewalDecision has forked the lease canon."""
    module = _write(
        tmp_path / "ws_lease.py",
        """
        from dataclasses import dataclass

        @dataclass
        class DeadmanLease:
            expiry_mono_server: float

        class RenewalDecision:
            ACCEPTED = "accepted"

        def RearmHandshake() -> None:
            return None
        """,
    )
    hits = ws.check_ws_no_redefinition([module])
    assert {h.symbol for h in hits} == {"DeadmanLease", "RenewalDecision", "RearmHandshake"}


def test_clean_transport_that_only_imports_is_silent(tmp_path: Path) -> None:
    """A module that imports its primitives and names lease fields by string is clean."""
    module = _write(
        tmp_path / "ws_clean.py",
        """
        from contracts.prim import CameraSlotKey, FrameType

        # Transport names, not canon redefinitions.
        LEASE_GENERATION_FIELD = "lease_generation"

        def camera_tag(slot: CameraSlotKey, channel: FrameType) -> str:
            return slot.ws_tag(channel)
        """,
    )
    assert ws.check_ws_no_redefinition([module]) == []


def test_the_real_ws_schema_forks_nothing() -> None:
    """The shipped schema.py redefines no primitive and no lease-semantics type."""
    assert ws.check_ws_no_redefinition([Path(ws_schema.__file__)]) == []


def test_reserved_lease_set_covers_the_canon_types() -> None:
    """The reserved set names the dead-man canon types the transport must never redefine."""
    assert {
        "LeaseRenewal",
        "DeadmanLease",
        "RenewalDecision",
        "RearmHandshake",
        "ClientClockOffset",
    } <= RESERVED_LEASE_SEMANTICS_SYMBOLS
