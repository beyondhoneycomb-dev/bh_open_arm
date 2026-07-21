"""The boot-order gate refuses backend startup on a failed bring-up (acceptance ③).

A real gate is `Requires=` plus `After=`: failure propagation and ordering together. The
validator here must accept that and reject the two near-misses — `Wants=` alone (no
propagation) and `Requires=` without `After=` (propagation not yet visible) — or it would
be a checker that is green while catching nothing.
"""

from __future__ import annotations

from ops.systemd.boot_order import (
    backend_gated_on_link,
    parse_unit_dependencies,
    render_backend_link_dropin,
)
from ops.systemd.constants import CAN_LINK_UNIT


def test_rendered_dropin_gates_the_backend() -> None:
    """The shipped drop-in refuses startup when the link unit fails."""
    dropin = render_backend_link_dropin()
    assert backend_gated_on_link([dropin])
    deps = parse_unit_dependencies(dropin)
    assert deps.refuses_startup_on_failure(CAN_LINK_UNIT)


def test_wants_only_is_rejected() -> None:
    """`Wants=` looks like a dependency but never propagates failure — must be rejected."""
    wants_only = f"[Unit]\nWants={CAN_LINK_UNIT}\nAfter={CAN_LINK_UNIT}\n"
    assert not backend_gated_on_link([wants_only])


def test_requires_without_after_is_rejected() -> None:
    """`Requires=` without ordering lets the backend start before the failure is visible."""
    unordered = f"[Unit]\nRequires={CAN_LINK_UNIT}\n"
    assert not backend_gated_on_link([unordered])


def test_gate_holds_across_the_unit_and_a_dropin_merge() -> None:
    """systemd merges drop-ins additively: After= in the unit, Requires= in the drop-in."""
    base_unit = f"[Unit]\nAfter={CAN_LINK_UNIT}\n"
    dropin = f"[Unit]\nRequires={CAN_LINK_UNIT}\n"
    assert backend_gated_on_link([base_unit, dropin])


def test_bindsto_also_propagates() -> None:
    """`BindsTo=` is a stronger propagator and, with ordering, also gates startup."""
    binds = f"[Unit]\nBindsTo={CAN_LINK_UNIT}\nAfter={CAN_LINK_UNIT}\n"
    assert backend_gated_on_link([binds])
