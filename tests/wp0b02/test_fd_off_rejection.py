"""Acceptance ② — an fd-off link is refused and the guidance names lerobot-setup-can.

The fd-off fixture is the trap-5 case (`01` §2.18): the link is CAN 2.0, python-can opens
it fd=True, and communication breaks silently. The verdict must reject, and the operator
guidance must carry `lerobot-setup-can --mode=setup --interfaces=` with the channel — the
exact command FR-SYS-006 requires, since code cannot set the link.
"""

from __future__ import annotations

from pathlib import Path

from backend.can.link import parse_link_show, render_rejection, validate_link
from backend.can.link.reporter import SETUP_COMMAND_PREFIX

_FD_OFF = Path(__file__).resolve().parent / "fixtures" / "corpus" / "fd_off.txt"


def test_fd_off_is_refused_with_setup_guidance() -> None:
    """fd off refuses startup and the guidance carries the exact setup command."""
    state = parse_link_show(_FD_OFF.read_text(encoding="utf-8"), "can0")
    verdict = validate_link(state)

    assert not verdict.ok
    assert any(mismatch.field == "fd" for mismatch in verdict.mismatches)

    message = render_rejection(verdict)
    assert SETUP_COMMAND_PREFIX in message
    assert "lerobot-setup-can --mode=setup --interfaces=can0" in message


def test_guidance_spans_all_channels_when_several_are_given() -> None:
    """A multi-channel caller gets one command covering every offending channel."""
    state = parse_link_show(_FD_OFF.read_text(encoding="utf-8"), "can0")
    message = render_rejection(validate_link(state), ["can0", "can1"])
    assert "lerobot-setup-can --mode=setup --interfaces=can0,can1" in message
