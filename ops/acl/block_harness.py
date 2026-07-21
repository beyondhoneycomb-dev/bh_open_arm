"""The unauthorized-send-block harness (`01` FR-SYS-007(iii), acceptance ①②).

The claim under test is that the mandatory layer blocks a process the cooperative flock
cannot: a rogue task that never consults the lock and just calls `socket(AF_CAN, …)`. This
module is the probe that tries exactly that, and the driver that runs it under a real
`RestrictAddressFamilies` seccomp filter.

Two facts split the acceptance across what runs here and what defers:

- **Socket *creation* is gated at `socket()`**, before any interface exists.
  `RestrictAddressFamilies` is a seccomp filter, so a denied family fails with `EAFNOSUPPORT`
  on a bare desktop with no
  CAN hardware at all. `run_attempt_under_families` proves this here via `systemd-run --user`,
  which applies the identical directive the shipped units carry — no vcan, no root.
- **Bind and transmit need a bus.** Proving a *send* is blocked (and that the authorized writer
  actually sends, acceptance ②'s "0 over-block"), requires an interface to bind to. That part is
  deferred to vcan and re-checked through `ops.acl.reverify`.

Run as a module (`python -m ops.acl.block_harness --json …`) it is the child the driver launches
inside the sandbox; imported, it is the probe and the driver the tests call.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import struct
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_SYSTEMD_RUN = "systemd-run"
_REPO_ROOT = Path(__file__).resolve().parents[2]

# struct can_frame: can_id (u32, native), can_dlc (u8) + 3 pad, then 8 data bytes.
_CAN_FRAME = struct.Struct("=IB3x8s")
_PROBE_CAN_ID = 0x123

# Stage labels, from least to most progress, so a reader can see how far the probe got.
STAGE_CREATE_BLOCKED = "create_blocked"
STAGE_CREATED = "created"
STAGE_BIND_FAILED = "bind_failed"
STAGE_BOUND = "bound"
STAGE_SEND_FAILED = "send_failed"
STAGE_SENT = "sent"


@dataclass(frozen=True)
class AttemptOutcome:
    """What happened when the probe tried to reach the bus.

    Attributes:
        created: Whether `socket(AF_CAN, …)` succeeded (False means the sandbox blocked it).
        bound: Whether a bind to the requested interface succeeded.
        sent: Whether a frame was transmitted.
        stage: The furthest stage reached (one of the `STAGE_*` labels).
        errno: The errno of the failing step, or None on full success.
        error: The human-readable error of the failing step, or None.
    """

    created: bool
    bound: bool
    sent: bool
    stage: str
    errno: int | None
    error: str | None

    def as_dict(self) -> dict[str, Any]:
        """Return the outcome as a plain dict for JSON transport."""
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> AttemptOutcome:
        """Reconstruct an outcome from its transported dict.

        Args:
            data: The dict produced by `as_dict`.

        Returns:
            (AttemptOutcome) The reconstructed outcome.
        """
        return AttemptOutcome(
            created=bool(data["created"]),
            bound=bool(data["bound"]),
            sent=bool(data["sent"]),
            stage=str(data["stage"]),
            errno=data["errno"] if data["errno"] is None else int(data["errno"]),
            error=data["error"] if data["error"] is None else str(data["error"]),
        )


def attempt_can_socket(interface: str | None, do_bind: bool, do_send: bool) -> AttemptOutcome:
    """Try to open, optionally bind, and optionally transmit on a CAN raw socket.

    Each step is attempted only if the previous one succeeded, and the outcome records where
    it stopped. A blocked `socket()` (the sandbox case) returns immediately with `created=False`.

    Args:
        interface: Interface to bind to, e.g. `vcan0`. Required when `do_bind` is True.
        do_bind: Whether to bind to `interface` after creating the socket.
        do_send: Whether to transmit one frame after binding.

    Returns:
        (AttemptOutcome) The furthest stage reached and any failure detail.
    """
    try:
        sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    except OSError as error:
        return AttemptOutcome(False, False, False, STAGE_CREATE_BLOCKED, error.errno, str(error))

    try:
        if not do_bind:
            return AttemptOutcome(True, False, False, STAGE_CREATED, None, None)
        try:
            sock.bind((interface,))  # AF_CAN bind takes a 1-tuple of the interface name
        except OSError as error:
            return AttemptOutcome(True, False, False, STAGE_BIND_FAILED, error.errno, str(error))

        if not do_send:
            return AttemptOutcome(True, True, False, STAGE_BOUND, None, None)
        try:
            sock.send(_CAN_FRAME.pack(_PROBE_CAN_ID, 1, b"\x01" + b"\x00" * 7))
        except OSError as error:
            return AttemptOutcome(True, True, False, STAGE_SEND_FAILED, error.errno, str(error))
        return AttemptOutcome(True, True, True, STAGE_SENT, None, None)
    finally:
        sock.close()


def user_manager_available() -> bool:
    """Whether a transient user service can be run — the precondition for the seccomp proof.

    Probes with a trivial transient service rather than assuming, so a host with no user
    systemd/dbus session skips the seccomp test with a reason instead of erroring.

    Returns:
        (bool) True when `systemd-run --user` can launch a unit here.
    """
    if shutil.which(_SYSTEMD_RUN) is None:
        return False
    try:
        completed = subprocess.run(
            [_SYSTEMD_RUN, "--user", "--wait", "--pipe", "--quiet", "/bin/true"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def run_attempt_under_families(
    family_policy: str,
    interface: str | None,
    do_bind: bool,
    do_send: bool,
) -> AttemptOutcome:
    """Run the probe inside a transient service carrying a `RestrictAddressFamilies` filter.

    The seccomp filter applied here is the same directive the shipped units carry, so a block
    observed under this driver is the block the installed sandbox produces.

    Args:
        family_policy: The `RestrictAddressFamilies=` value to apply, e.g. `"~AF_CAN"` (deny)
            or `"AF_CAN AF_UNIX"` (allow).
        interface: Interface passed through to the probe.
        do_bind: Whether the probe should bind.
        do_send: Whether the probe should transmit.

    Returns:
        (AttemptOutcome) The probe's outcome under the sandbox.

    Raises:
        RuntimeError: If the transient service produced no parsable outcome.
    """
    child = [sys.executable, "-m", "ops.acl.block_harness", "--json"]
    if interface is not None:
        child += ["--interface", interface]
    if do_bind:
        child.append("--bind")
    if do_send:
        child.append("--send")
    completed = subprocess.run(
        [
            _SYSTEMD_RUN,
            "--user",
            "--wait",
            "--pipe",
            "--quiet",
            "--working-directory",
            str(_REPO_ROOT),
            "--property",
            f"RestrictAddressFamilies={family_policy}",
            "--property",
            "NoNewPrivileges=yes",
            *child,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in reversed(completed.stdout.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{"):
            return AttemptOutcome.from_dict(json.loads(stripped))
    raise RuntimeError(f"no outcome JSON from sandboxed probe; stdout was {completed.stdout!r}")


def main(argv: list[str] | None = None) -> int:
    """Child entry point: run the probe and print its outcome as JSON.

    Args:
        argv: Command-line arguments, defaulting to `sys.argv[1:]`.

    Returns:
        (int) Always 0 — a blocked socket is a reported outcome, not a process failure.
    """
    parser = argparse.ArgumentParser(description="CAN socket reach probe")
    parser.add_argument("--interface", default=None)
    parser.add_argument("--bind", action="store_true")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--json", action="store_true", help="emit the outcome as JSON")
    args = parser.parse_args(argv)

    outcome = attempt_can_socket(args.interface, args.bind, args.send)
    if args.json:
        print(json.dumps(outcome.as_dict()))
    else:
        print(outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
