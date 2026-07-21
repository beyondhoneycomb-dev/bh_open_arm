"""The read-only RID read harness: lock held, link verified, torque OFF, then read.

This is the entry point WP-0B-07 owns — a harness that reads RID values off the
motors under three hard preconditions and nothing else:

1. The channel lock (WP-0B-01) is held for the interface. A read shares the bus, so
   a reading taken without the lock is invalid and must not be published — the same
   rule `WP-0B-06` states for its measurements. `assert_lock_held` enforces it
   before any read.
2. The CAN link (WP-0B-02) passes FR-SYS-006 verification. Reading over a link with
   `fd off` or the wrong bitrate silently corrupts every frame (`01` §2.18 trap 5),
   so the harness verifies the injected link state and refuses on any mismatch.
3. Torque is OFF on every motor being read. RID reads need the motors powered, and
   `12` FR-SAF-075 requires bring-up to begin torque-OFF and *stay* there until an
   operator has verified zeroing; so the harness asserts a torque-OFF probe before
   reading and refuses if any motor is enabled. On this host the probe is injected;
   on the rig it reads real enable state, and that end-to-end assertion is deferred.

The harness holds no write path. It calls the injected `RidReader.read` and returns
the decoded dump; it never constructs a write frame, a `set_zero`, or a mode change
(the static check in `staticcheck.py` proves that absence over the whole tree).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from backend.can.link.parser import LinkState
from backend.can.link.validator import validate_link
from backend.can.lock.connect_guard import assert_lock_held
from backend.can.lock.manager import LockManager
from backend.can.rid.dump import RidDump
from backend.can.rid.reader import RidReader


class TorqueEngagedError(RuntimeError):
    """A RID read was attempted while one or more motors had torque enabled.

    `12` FR-SAF-075 requires the read to happen with torque OFF; a read attempted
    with a motor enabled is refused rather than performed.
    """


class LinkNotVerifiedError(RuntimeError):
    """A RID read was attempted over a CAN link that failed WP-0B-02 verification.

    `01` FR-SYS-006 / `01` §2.18 trap 5: a link with `fd off` or the wrong bitrate
    lets the socket open yet corrupts every frame silently, so a read taken over an
    unverified link is invalid. The harness refuses to read until the link clears
    the `{fd, bitrate, dbitrate, state}` criteria WP-0B-02 checks.
    """


@dataclass(frozen=True)
class TorqueState:
    """Per-motor torque-enable state at the moment of a read.

    Attributes:
        enabled: motor_id -> True when that motor currently has torque enabled.
    """

    enabled: dict[int, bool]

    def engaged_ids(self) -> tuple[int, ...]:
        """Return the motors that currently have torque enabled.

        Returns:
            (tuple[int, ...]) Enabled motor ids, ascending.
        """
        return tuple(sorted(mid for mid, on in self.enabled.items() if on))

    def all_off(self) -> bool:
        """Report whether every motor has torque OFF.

        Returns:
            (bool) True when no motor is enabled.
        """
        return not self.engaged_ids()


# A probe that reports the torque state of the motors about to be read. Injected so
# this host can supply an all-OFF probe while the rig supplies a real one.
TorqueProbe = Callable[[Sequence[int]], TorqueState]

# A probe that reports the parsed link state of the interface about to be read. Injected
# so this host can supply a fixture-parsed state while the rig parses real
# `ip -details link show` output; the harness verifies it (WP-0B-02) before any read.
LinkProbe = Callable[[str], LinkState]


class RidReadHarness:
    """Reads RID values under the lock-held and torque-OFF preconditions.

    Args:
        manager: The WP-0B-01 lock manager expected to hold the channel lock.
        reader: The read source (fixture on this host, real on the rig).
        torque_probe: Reports torque state for the motors about to be read; the
            harness refuses to read if it reports any motor enabled.
        link_probe: Reports the parsed link state (WP-0B-02) for the interface; the
            harness refuses to read if the link fails FR-SYS-006 verification.
    """

    def __init__(
        self,
        manager: LockManager,
        reader: RidReader,
        torque_probe: TorqueProbe,
        link_probe: LinkProbe,
    ) -> None:
        self._manager = manager
        self._reader = reader
        self._torque_probe = torque_probe
        self._link_probe = link_probe

    def read(self, iface: str, motor_ids: Sequence[int], rids: Sequence[int]) -> RidDump:
        """Read RIDs after asserting the lock is held, link verified, torque OFF.

        The preconditions strictly precede the read: on a missing lock, an
        unverified link, or an engaged motor the reader is never called, so no value
        is ever produced out of order, over a broken link, or with torque on.

        Args:
            iface: The CAN interface to read from; its lock must be held.
            motor_ids: The motors to read.
            rids: The registers to read from each motor.

        Returns:
            (RidDump) The decoded read-backs.

        Raises:
            LockOrderingError: If the interface lock is not held.
            LinkNotVerifiedError: If the CAN link fails WP-0B-02 verification.
            TorqueEngagedError: If any motor being read has torque enabled.
        """
        assert_lock_held(self._manager, [iface])
        verdict = validate_link(self._link_probe(iface))
        if not verdict.ok:
            raise LinkNotVerifiedError(
                f"refusing RID read on {iface}: link verification failed "
                f"({', '.join(str(m) for m in verdict.mismatches)}); WP-0B-02 requires a "
                "verified link (01 FR-SYS-006, 01 §2.18 trap 5)"
            )
        torque = self._torque_probe(motor_ids)
        if not torque.all_off():
            raise TorqueEngagedError(
                f"refusing RID read on {iface}: torque enabled on motors "
                f"{torque.engaged_ids()} (12 FR-SAF-075 requires torque-OFF)"
            )
        return self._reader.read(iface, motor_ids, rids)
