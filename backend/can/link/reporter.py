"""Emit the user-facing rejection guidance for a failed link verification.

FR-SYS-006 is explicit that code cannot set the link itself; on a mismatch the backend
must refuse startup and hand the operator the exact `lerobot-setup-can` command to run.
The command string is the load-bearing output (acceptance ②): it must carry
`lerobot-setup-can --mode=setup --interfaces=` with the offending channels appended.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.can.link.validator import LinkVerdict

SETUP_COMMAND_PREFIX = "lerobot-setup-can --mode=setup --interfaces="


def setup_command(ifaces: Sequence[str]) -> str:
    """Build the `lerobot-setup-can` command the operator must run.

    Args:
        ifaces: Channels to include in the `--interfaces=` list.

    Returns:
        (str) `lerobot-setup-can --mode=setup --interfaces=<comma-joined ifaces>`.
    """
    return f"{SETUP_COMMAND_PREFIX}{','.join(ifaces)}"


def render_rejection(verdict: LinkVerdict, ifaces: Sequence[str] | None = None) -> str:
    """Render the refusal message for a failed verdict.

    Args:
        verdict: A verdict whose `ok` is False.
        ifaces: Channels to pass to `lerobot-setup-can`; defaults to the verdict's own
            interface. A caller verifying several channels passes them all so the
            operator receives one command covering every channel.

    Returns:
        (str) A multi-line message: the failed criteria, the statement that the backend
        cannot set the link, and the exact command to run.

    Raises:
        ValueError: If called on a passing verdict — there is nothing to reject.
    """
    if verdict.ok:
        raise ValueError(f"render_rejection called on a passing verdict for {verdict.iface}")
    channels = list(ifaces) if ifaces is not None else [verdict.iface]
    lines = [
        f"CAN link {verdict.iface} failed startup verification (01 FR-SYS-006):",
        *(f"  - {mismatch}" for mismatch in verdict.mismatches),
        "The backend cannot configure the link itself. Run:",
        f"  {setup_command(channels)}",
    ]
    return "\n".join(lines)
