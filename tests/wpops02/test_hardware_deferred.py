"""Honestly-deferred hardware acceptances (①④) — skipped-with-reason, never faked.

Acceptance ① (the four fixed names come up with fd/bitrate/dbitrate/txqueuelen after boot)
and ④ (ten-reboot determinism) cannot be produced on a dev desktop with no CAN adapters and
no reboot loop. Each is guarded so that on a real, booted rig with the unit installed it runs
against live output, and here it skips with the reason and a pointer to the re-verification
hook that carries the same check to a real capture (plan 02a §4.1, shared with WP-0B-05).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from backend.can.link.parser import parse_link_show
from ops.systemd.constants import INTERFACE_NAMES
from ops.systemd.reverify import link_params_ok

# ARPHRD_CAN, as `/sys/class/net/<if>/type` reports it for a CAN link.
_CAN_TYPE = "280"
_NET_ROOT = Path("/sys/class/net")


def _fixed_names_present() -> bool:
    """Whether all four fixed names exist as CAN interfaces (unit installed on a booted rig).

    Reads sysfs directly so the probe needs no CAN tooling. Absent sysfs or any missing name
    yields False — the honest "no configured hardware here" answer.

    Returns:
        (bool) True iff every fixed name is present and typed as a CAN link.
    """
    if not _NET_ROOT.is_dir():
        return False
    for name in INTERFACE_NAMES:
        type_file = _NET_ROOT / name / "type"
        try:
            if type_file.read_text(encoding="utf-8").strip() != _CAN_TYPE:
                return False
        except OSError:
            return False
    return True


_NO_RIG_REASON = (
    "requires a booted rig with the CAN link unit installed (four fixed-name CAN "
    "interfaces); none present on this host. Supply a real capture to "
    "ops.systemd.reverify.reverify_from_fixture to re-verify (evidence shared with WP-0B-05)."
)


@pytest.mark.skipif(not _fixed_names_present(), reason=_NO_RIG_REASON)
def test_live_fixed_names_carry_the_verified_link_params() -> None:
    """Acceptance ①: each fixed name is CAN-FD at the verified bitrates with txqueuelen 1000."""
    for name in INTERFACE_NAMES:
        output = subprocess.run(
            ["ip", "-details", "link", "show", name],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert link_params_ok(parse_link_show(output, name))


@pytest.mark.skip(
    reason=(
        "acceptance ④ requires ten real reboots — impossible in-process. Capture one binding "
        "per boot into reboots.json and re-verify via ops.systemd.reverify.reverify_from_fixture "
        "(evaluator proven in test_reverify_hook; shared evidence with WP-0B-05 ⑤)."
    )
)
def test_reboot_determinism_ten_cycles() -> None:
    """Acceptance ④: ten reboots bind the four fixed names to the same physical channels."""
    raise AssertionError("unreachable: captured out-of-process, then re-verified via the hook")
