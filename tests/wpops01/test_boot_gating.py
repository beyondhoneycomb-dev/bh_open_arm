"""The shipped writer unit must satisfy the boot-order gate WP-OPS-02 defines.

`ops/systemd/boot_order.py` encodes `01` FR-SYS-006 ③: a backend that touches the bus
must *refuse to start* when CAN bring-up failed, which in systemd terms means `Requires=`
plus `After=`. `tests/wpops02/test_boot_order.py` already proves the predicate rejects a
`Wants=`-only definition — against synthetic bodies.

Nothing pointed it at the one real unit in the repository. A predicate that is correct,
tested, and never applied to the artifact it exists to judge is indistinguishable from no
predicate at all, and that is what these two assertions close. They also catch the failure
mode that made this necessary: systemd silently ignores an unknown unit name in `Wants=`
and `After=`, so a dependency on a service that does not exist is inert rather than an
error — the unit comes up in any order, against a link that may never have been configured.
"""

from __future__ import annotations

from pathlib import Path

from ops.acl.policy import WRITER_UNIT_FILENAME
from ops.systemd import backend_gated_on_link
from ops.systemd.boot_order import parse_unit_dependencies
from ops.systemd.constants import CAN_LINK_UNIT

_REPO_ROOT = Path(__file__).resolve().parents[2]
_UNITS = _REPO_ROOT / "ops" / "acl" / "units"


def _writer_unit() -> str:
    """Return the shipped authorized-CAN-writer unit body."""
    return (_UNITS / WRITER_UNIT_FILENAME).read_text(encoding="utf-8")


def test_shipped_writer_unit_refuses_to_start_on_a_failed_link() -> None:
    """The real unit, not a fixture, must pass WP-OPS-02's own gate predicate."""
    assert backend_gated_on_link([_writer_unit()]), (
        "the shipped CAN-writer unit does not propagate and order a bring-up failure; "
        "a Wants= is a wish, and the writer would start against an unconfigured link"
    )


def test_every_unit_the_writer_depends_on_is_one_this_repo_can_produce() -> None:
    """A dependency on a unit that does not exist is dropped, not reported.

    systemd does not error on an unknown unit name in `Requires=`/`Wants=`/`After=`; it
    silently drops it. So a typo'd or renamed dependency disarms the ordering while
    leaving the directives that `backend_gated_on_link` inspects intact — the gate reads
    as held and nothing enforces it. Every referenced unit must therefore be one this
    repository renders, or a systemd built-in target.
    """
    dependencies = parse_unit_dependencies(_writer_unit())
    referenced = dependencies.requires_or_binds | dependencies.after | dependencies.wants
    assert referenced, "the writer unit declares no bring-up dependency at all"

    unknown = {
        unit for unit in referenced if unit != CAN_LINK_UNIT and not unit.endswith(".target")
    }
    assert not unknown, (
        f"the writer unit depends on unit(s) this repository does not define: {sorted(unknown)}; "
        f"the only bring-up unit it renders is {CAN_LINK_UNIT}"
    )
