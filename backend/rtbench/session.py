"""The read-only measurement session: one `connect()`, torque OFF, channel lock held.

`02a` WP-1-04 fixes three hard preconditions on any measurement this WP publishes,
and this session enforces all three as refusals, never warnings:

1. `connect()` is called exactly once per session (acceptance ②, `15` NFR-PRF-055).
   A repeat re-runs the driver's zeroing and destroys the `WP-1-02` operator zero, so
   the second call raises rather than reconnecting.
2. Torque is OFF on every motor for the whole measurement (acceptance ③, `12`
   FR-SAF-075). Read-only bring-up must never energise a motor; an engaged motor at
   any check refuses the measurement.
3. The CAN channel lock (`WP-0B-01`) is held before connecting and before publishing
   (acceptance ④, `15` §2.10 precondition). A measurement taken without the lock is
   invalid and must not be published.

The real `connect_readonly()` binding and the real torque read live on the rig and are
injected here: on this host the connect callable is a dummy and the torque probe reads
an all-OFF fixture; on the rig they are the `WP-1-03` follower and its enable state.
The session holds no write path — it opens a read session and asserts, nothing else.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from backend.can.lock.connect_guard import assert_lock_held
from backend.can.lock.manager import LockManager

T = TypeVar("T")


class RepeatedConnectError(RuntimeError):
    """`connect()` was called more than once in a session.

    `15` NFR-PRF-055 allows exactly one `connect()` per session because a reconnect
    re-runs zeroing and destroys the operator zero `WP-1-02` established; the second
    call is refused rather than performed.
    """


class TorqueEngagedError(RuntimeError):
    """A measurement was attempted or published while a motor had torque enabled.

    `12` FR-SAF-075 requires read-only bring-up to stay torque-OFF; any engaged motor
    refuses the measurement.
    """


class NotConnectedError(RuntimeError):
    """Publication was attempted before the session's single `connect()` ran."""


@dataclass(frozen=True)
class TorqueState:
    """Per-motor torque-enable state at a moment in the measurement.

    Attributes:
        enabled: motor_id -> True when that motor currently has torque enabled.
    """

    enabled: dict[int, bool]

    def engaged_ids(self) -> tuple[int, ...]:
        """Return the motors that currently have torque enabled.

        Returns:
            (tuple[int, ...]) Enabled motor ids, ascending.
        """
        return tuple(sorted(motor_id for motor_id, on in self.enabled.items() if on))

    def all_off(self) -> bool:
        """Report whether every motor has torque OFF.

        Returns:
            (bool) True when no motor is enabled.
        """
        return not self.engaged_ids()


# Reports the torque state of the motors under measurement. Injected so this host can
# supply an all-OFF fixture while the rig reads the follower's real enable state.
TorqueProbe = Callable[[], TorqueState]


class ReadOnlyMeasurementSession(Generic[T]):
    """A single-connect, torque-OFF, lock-held measurement session.

    Ownership: holds the lock manager (owned by the caller), the interfaces the
    measurement uses, the single-session connect callable, and the torque probe. It
    counts `connect()` calls and never opens a second session; it produces no write.

    Args:
        manager: The `WP-0B-01` lock manager expected to hold the channel locks.
        ifaces: The CAN interfaces the measurement uses; all must be locked.
        connect: The read-only connect callable (`connect_readonly` on the rig);
            invoked at most once.
        torque_probe: Reports the torque state of the motors under measurement.
    """

    def __init__(
        self,
        manager: LockManager,
        ifaces: Sequence[str],
        connect: Callable[[], T],
        torque_probe: TorqueProbe,
    ) -> None:
        self._manager = manager
        self._ifaces = tuple(ifaces)
        self._connect = connect
        self._torque_probe = torque_probe
        self._connect_call_count = 0
        self._binding: T | None = None

    @property
    def connect_call_count(self) -> int:
        """How many times `connect()` has run this session — must stay 1 to publish."""
        return self._connect_call_count

    @property
    def ifaces(self) -> tuple[str, ...]:
        """The CAN interfaces this session measures over."""
        return self._ifaces

    def connect(self) -> T:
        """Open the single read-only session, refusing a second connect.

        The lock is asserted before the connect callable runs (`01` FR-SYS-005): on a
        missing lock the callable is never invoked. The torque probe is asserted
        immediately after connecting, so a session that comes up energised is caught at
        bring-up, not only at publish.

        Returns:
            (T) Whatever the connect callable returns (the bound follower on the rig).

        Raises:
            RepeatedConnectError: On the second and later calls.
            LockOrderingError: If any interface lock is not held.
            TorqueEngagedError: If any motor is energised on connect.
        """
        if self._connect_call_count >= 1:
            raise RepeatedConnectError(
                f"connect() already called {self._connect_call_count} time(s); one connect "
                "per session (15 NFR-PRF-055) — a reconnect destroys the WP-1-02 zero"
            )
        assert_lock_held(self._manager, self._ifaces)
        self._connect_call_count += 1
        self._binding = self._connect()
        self._assert_torque_off()
        return self._binding

    def assert_publishable(self) -> None:
        """Refuse publication unless all three preconditions still hold.

        Args:
            (none)

        Raises:
            NotConnectedError: If `connect()` never ran.
            RepeatedConnectError: If `connect()` ran more than once.
            LockOrderingError: If the channel lock is no longer held.
            TorqueEngagedError: If any motor is energised.
        """
        if self._connect_call_count == 0:
            raise NotConnectedError(
                "no measurement session was connected; refusing to publish (acceptance ②)"
            )
        if self._connect_call_count != 1:
            raise RepeatedConnectError(
                f"connect() ran {self._connect_call_count} times; exactly one is required "
                "to publish (acceptance ②)"
            )
        assert_lock_held(self._manager, self._ifaces)
        self._assert_torque_off()

    def _assert_torque_off(self) -> None:
        """Raise if any motor under measurement currently has torque enabled.

        Raises:
            TorqueEngagedError: If the probe reports any engaged motor.
        """
        torque = self._torque_probe()
        if not torque.all_off():
            raise TorqueEngagedError(
                f"torque enabled on motors {torque.engaged_ids()}; read-only measurement "
                "must stay torque-OFF (12 FR-SAF-075, acceptance ③)"
            )
