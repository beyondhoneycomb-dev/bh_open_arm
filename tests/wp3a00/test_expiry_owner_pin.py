"""WP-3A-00 ③ — expiry-judge clock ownership is pinned to SERVER at the primitive level.

U-4's dead-man rests on one fact: lease expiry is judged on the server clock, and
the client clock is only an age input. `02b` §5.2 WP-3A-00 ③ pins that ownership
here, below `CTR-WS@v1`, so the WS schema transports the lease but cannot re-own
who judges its expiry. These tests prove the pin holds and that a WS override is
refused two ways: the runtime guard and the static no-redefinition scan.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

import contracts.prim as prim


def test_expiry_owner_is_server() -> None:
    """The pinned expiry-judge role is the server clock; the client clock is age input."""
    assert prim.EXPIRY_JUDGE_ROLE == prim.ClockRole.SERVER
    assert prim.AGE_INPUT_ROLE == prim.ClockRole.CLIENT


def test_lease_fields_carry_their_clock_ownership() -> None:
    """The expiry field names the server clock; the issued field names the client clock."""
    assert prim.LEASE_EXPIRY_FIELD == "expiry_mono_server"
    assert prim.LEASE_ISSUED_FIELD == "issued_mono_client"


def test_server_owner_is_accepted() -> None:
    """A contract declaring the server clock as expiry judge agrees with the pin."""
    prim.verify_expiry_owner(prim.ClockRole.SERVER)


def test_ws_override_to_client_is_refused_at_runtime() -> None:
    """A CTR-WS override that claims the client clock judges expiry is refused."""
    with pytest.raises(prim.PrimitiveRedefinitionError):
        prim.verify_expiry_owner(prim.ClockRole.CLIENT)


def test_ws_redefining_the_pin_symbol_is_caught_statically(tmp_path: Path) -> None:
    """A WS schema that rebinds `EXPIRY_JUDGE_ROLE` is a redefinition the scan catches."""
    ws_schema = tmp_path / "ws_schema.py"
    ws_schema.write_text(
        textwrap.dedent(
            """
            from contracts.prim import ClockRole

            # A WS schema trying to move expiry ownership onto the client clock.
            EXPIRY_JUDGE_ROLE = ClockRole.CLIENT
            """
        ),
        encoding="utf-8",
    )
    hits = prim.check_no_redefinition([ws_schema])
    assert [h.symbol for h in hits] == ["EXPIRY_JUDGE_ROLE"]


def test_capture_and_synthetic_grid_are_distinct_domains() -> None:
    """A real capture instant and the synthetic playback grid are not interchangeable types."""
    capture = prim.CaptureTimestamp(mono_ns=1_234_567)
    grid = prim.SyntheticGridTimestamp(seconds=0.25)
    assert capture.domain == prim.TimestampDomain.CAPTURE
    assert grid.domain == prim.TimestampDomain.SYNTHETIC_GRID
    assert type(capture) is not type(grid)


def test_capture_timestamp_rejects_non_integer_ns() -> None:
    """A capture timestamp is monotonic nanoseconds — an integer, never a float or bool."""
    with pytest.raises(prim.PrimitiveRedefinitionError):
        prim.CaptureTimestamp(mono_ns=1.5)  # type: ignore[arg-type]
    with pytest.raises(prim.PrimitiveRedefinitionError):
        prim.CaptureTimestamp(mono_ns=True)  # type: ignore[arg-type]
