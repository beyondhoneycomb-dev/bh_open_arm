"""Real-bus re-verification hook for the ACL block (plan 02a §4.1, acceptance ①②).

`run_attempt_under_families` proves the socket-*creation* block on this desktop, but the
bus-bound half of the acceptance cannot be shown without an interface to bind to: that an
unauthorized process cannot *transmit*, and that the authorized writer *does* transmit with
zero over-block (②). Those defer to a vcan (or real CAN) interface, and this hook is how they
are re-checked the moment one exists — never faked in between.

Two entry points, same contract:

- `reverify_on_interface` runs live on the rig. It fires two probes at a real interface: one
  under the deny policy (must be blocked before it ever binds) and one under the allow policy
  (must bind and send). It is the true acceptance, deferred here and run there.
- `reverify_from_capture` validates a recorded capture from such a run against the same
  contract, so a rig's evidence can be checked offline — and so the hook's own logic is
  exercisable here against a synthetic capture without inventing a bus.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from ops.acl.block_harness import (
    STAGE_SENT,
    AttemptOutcome,
    run_attempt_under_families,
    user_manager_available,
)
from ops.acl.policy import AUTHORIZED_FAMILIES, CAN_FAMILY

VCAN_ENV_VAR = "OPENARM_ACL_VCAN_INTERFACE"
_NET_ROOT = Path("/sys/class/net")
_DENY_POLICY = f"~{CAN_FAMILY}"
_ALLOW_POLICY = " ".join(AUTHORIZED_FAMILIES)


@dataclass(frozen=True)
class AclReverifyReport:
    """Outcome of re-checking the block contract against a real bus or its capture.

    Attributes:
        matched: True iff the unauthorized probe was blocked and the authorized one transmitted.
        checked: The contract points evaluated.
        mismatches: One line per contract point that did not hold.
    """

    matched: bool
    checked: tuple[str, ...]
    mismatches: tuple[str, ...] = field(default_factory=tuple)


def vcan_interface_from_env() -> str | None:
    """Return the vcan interface named by the environment, if it exists.

    Returns:
        (str | None) The interface name, or None when unset or absent from `/sys/class/net`.
    """
    name = os.environ.get(VCAN_ENV_VAR)
    if not name:
        return None
    return name if (_NET_ROOT / name).is_dir() else None


def _evaluate(deny_outcome: AttemptOutcome, allow_outcome: AttemptOutcome) -> AclReverifyReport:
    """Check a deny/allow outcome pair against the block contract.

    Args:
        deny_outcome: Probe outcome under the deny policy (unauthorized process).
        allow_outcome: Probe outcome under the allow policy (authorized writer).

    Returns:
        (AclReverifyReport) The verdict over both contract points.
    """
    mismatches: list[str] = []
    if deny_outcome.created:
        mismatches.append(
            f"unauthorized probe was not blocked: reached stage {deny_outcome.stage!r} "
            "(expected the socket to be refused at creation)"
        )
    if not allow_outcome.sent:
        mismatches.append(
            f"authorized writer did not transmit: stopped at {allow_outcome.stage!r} "
            f"(errno {allow_outcome.errno}) — over-block, expected stage {STAGE_SENT!r}"
        )
    return AclReverifyReport(
        matched=not mismatches,
        checked=("unauthorized_blocked", "authorized_transmits"),
        mismatches=tuple(mismatches),
    )


def reverify_on_interface(interface: str) -> AclReverifyReport:
    """Run the live block acceptance against a real (or virtual) CAN interface.

    Args:
        interface: The interface to bind on, e.g. `vcan0`.

    Returns:
        (AclReverifyReport) The verdict; `matched` is the acceptance-①② pass.

    Raises:
        RuntimeError: If no user service manager is available to apply the sandbox.
    """
    if not user_manager_available():
        raise RuntimeError("no user service manager to apply RestrictAddressFamilies")
    deny_outcome = run_attempt_under_families(_DENY_POLICY, interface, do_bind=True, do_send=True)
    allow_outcome = run_attempt_under_families(_ALLOW_POLICY, interface, do_bind=True, do_send=True)
    return _evaluate(deny_outcome, allow_outcome)


def reverify_from_capture(capture_path: Path) -> AclReverifyReport:
    """Validate a recorded rig capture against the block contract.

    The capture is a JSON object with `deny` and `allow` keys, each an `AttemptOutcome` dict as
    produced on the rig. This lets a real-bus run's evidence be re-checked offline, and exercises
    the hook's contract logic without a live interface.

    Args:
        capture_path: Path to the capture JSON.

    Returns:
        (AclReverifyReport) The verdict over the recorded outcomes.

    Raises:
        FileNotFoundError: If the capture file is missing.
    """
    if not capture_path.is_file():
        raise FileNotFoundError(f"missing ACL block capture: {capture_path}")
    data = json.loads(capture_path.read_text(encoding="utf-8"))
    return _evaluate(
        AttemptOutcome.from_dict(data["deny"]),
        AttemptOutcome.from_dict(data["allow"]),
    )
