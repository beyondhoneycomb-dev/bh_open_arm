"""Acceptance ⑥ — a producer reaching for the CAN handle is rejected statically.

The single-writer invariant has a structural half and a static half. Structurally,
a producer holds only a mailbox, whose surface has no path to a CAN frame. Because
"structurally" only lasts until someone imports around it, the static scan makes
any reference to the CAN writer's module or write symbols, from outside the owning
tree, a compile-stage finding — and the clean producer proves the scan does not
over-flag.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.actuation import (
    MailboxProducer,
    TargetMailbox,
    find_producer_can_access,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_ACTUATION_TREE = Path(__file__).resolve().parents[2] / "backend" / "actuation"

_CAN_HANDLE_SYMBOLS = {"mit_control_batch", "_mit_control_batch", "CanWriter", "FakeCanWriter"}


@pytest.mark.fixture_corpus
def test_producer_reaching_for_can_handle_is_flagged() -> None:
    """The violation fixture is flagged; the clean producer beside it is not."""
    violations = find_producer_can_access(_FIXTURES)

    flagged_files = {violation.path.name for violation in violations}
    assert "producer_can_access.py" in flagged_files
    assert "clean_producer.py" not in flagged_files
    assert "disable_torque_stop.py" not in flagged_files
    # The flagged symbols are CAN-handle reaches, not something incidental.
    assert {violation.symbol for violation in violations} & _CAN_HANDLE_SYMBOLS


@pytest.mark.fixture_corpus
def test_owning_actuation_tree_is_not_over_flagged() -> None:
    """The scan exempts the owner: the scheduler's own CAN use is not a violation."""
    assert find_producer_can_access(_ACTUATION_TREE) == []


def test_mailbox_surface_has_no_can_handle() -> None:
    """A producer holds only the mailbox, whose surface exposes no CAN frame path."""
    surface = {name for name in dir(TargetMailbox) if not name.startswith("_")}
    assert surface == {"publish", "take_latest"}
    assert not surface & _CAN_HANDLE_SYMBOLS


def test_producer_surface_has_no_can_handle() -> None:
    """The reference producer exposes only publish/identity/join — never a CAN handle."""
    mailbox = TargetMailbox()

    class _StubClock:
        def now(self) -> float:
            return 0.0

    producer = MailboxProducer("p", mailbox, _StubClock())
    surface = {name for name in dir(producer) if not name.startswith("_")}
    assert not surface & _CAN_HANDLE_SYMBOLS
    assert "publish" in surface
    # The mailbox reference the producer holds is itself CAN-free.
    assert not {name for name in dir(producer._mailbox) if not name.startswith("_")} & (
        _CAN_HANDLE_SYMBOLS
    )
