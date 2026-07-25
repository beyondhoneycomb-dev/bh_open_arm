"""The command-security guard — FR-OPS-091 over the *one* deadman lease (U-4).

`FR-OPS-091` requires every command to carry `{session_id, lease_generation,
expiry, sequence, timestamp}` and the backend to refuse (a) an expired lease, (b) a
`lease_generation` mismatch, and (c) a `sequence`/`timestamp` regress (replay). The
load-bearing decision of this WP (`02c` §4.8 interface contract) is that this is the
**same** lease as the U-4 deadman, not a second one: the generation is read from the
deadman's re-arm handshake and expiry is read from the deadman's own lease clock, so
"the deadman is alive but the security lease expired" is a state that cannot exist.

What this guard *does* add — and all it adds — is per-command-stream anti-replay
state. The deadman's `RenewalReceiver` counts sequences on the *renewal* stream; a
command is a different stream with its own `sequence` and `timestamp`, so refusing a
replayed command needs a last-accepted `(sequence, timestamp)` per `(session,
generation)`. That is a property of the command stream, not a duplicate lease: the
generation and the expiry it is checked against are single-sourced from the deadman.

Expiry is judged on the server, never on the client. A command carries no expiry
field at all (mirroring `LeaseRenewal`), so no expiry decision can read a
client-supplied time; the guard reads `DeadmanController.latched` (the poll-driven
safe state) and the shared `LeaseManager.is_expired` on the server clock.

The check order is fixed so each refusal has one unambiguous reason, and it puts the
generation check *before* the holder check on purpose: after a forced release
(`FR-OPS-076`) the prior holder no longer holds the L2 lock **and** carries a stale
generation, and `CG-5-08c` wants that refusal attributed to the generation bump, not
to the lock having moved.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.actuation.clock import Clock
from backend.actuation.lease import LeaseManager
from backend.deadman.controller import DeadmanController
from backend.security.control_lock import CommandSourceLock
from contracts.ws import CONTROL_HOLDER_ROLE, WsRole


@dataclass(frozen=True)
class CommandEnvelope:
    """The FR-OPS-091 metadata every command carries, minus the server-owned expiry.

    A command references the lease it belongs to by `session_id` and
    `lease_generation`; it never states its own expiry, because expiry is the
    server's alone (U-4). `timestamp_mono_client` is the client's monotonic reading,
    used only as a replay-ordering input alongside `sequence` — never as an expiry
    input.

    Attributes:
        session_id: The control session this command is issued under. Must match the
            current L2 command-source lock holder.
        lease_generation: The re-arm epoch the command belongs to. Must equal the
            deadman's current generation; a forced release increments the generation
            and thereby invalidates a prior holder's in-flight commands.
        sequence: Strictly increasing per-`(session, generation)` counter. A value at
            or below the last accepted one is a replay or reorder.
        timestamp_mono_client: The client's monotonic clock reading when it issued
            the command. A replay-ordering input only; must also strictly increase.
    """

    session_id: str
    lease_generation: int
    sequence: int
    timestamp_mono_client: float


class CommandDecision(Enum):
    """Why the guard accepted or refused one command — one reason per refusal.

    The audit must tell a stale-generation refusal from a replay from a
    non-holder from an expired lease, because each means a different thing about the
    operator, the link, and the lock (`FR-OPS-091` negative branch).
    """

    ACCEPTED = "accepted"
    # The sender's role is not the single command-authority role (an observer, or an
    # admin — admin holds force-release but is not a second command source).
    REFUSED_NOT_OPERATOR = "refused_not_operator"
    # `lease_generation` != the deadman's current generation — a stale epoch, the
    # forced-release fence (`CG-5-08c`).
    REFUSED_GENERATION_MISMATCH = "refused_generation_mismatch"
    # The session is not the current L2 command-source lock holder.
    REFUSED_NOT_HOLDER = "refused_not_holder"
    # The one deadman lease is expired or latched — the safe state (`CG-5-08d`).
    REFUSED_LEASE_EXPIRED = "refused_lease_expired"
    # `sequence` at or below the last accepted for this `(session, generation)`.
    REFUSED_REPLAY_SEQUENCE = "refused_replay_sequence"
    # `timestamp` at or below the last accepted for this `(session, generation)`.
    REFUSED_REPLAY_TIMESTAMP = "refused_replay_timestamp"


@dataclass(frozen=True)
class CommandVerdict:
    """The guard's verdict on one command.

    Attributes:
        decision: The single reason the command was accepted or refused.
    """

    decision: CommandDecision

    @property
    def accepted(self) -> bool:
        """Whether the command was accepted.

        Returns:
            (bool) True only for an accepted command.
        """
        return self.decision is CommandDecision.ACCEPTED


class CommandGuard:
    """Validates each command against the one deadman lease and the L2 lock holder.

    Ownership: this guard owns **only** the per-command-stream anti-replay state. The
    generation, the expiry and the safe-state latch are read from the
    `DeadmanController` and the shared `LeaseManager` it renews — the single lease the
    scheduler also reads — so this class never mints a generation, never sets an
    expiry, and cannot drift from the deadman.
    """

    def __init__(
        self,
        controller: DeadmanController,
        lease: LeaseManager,
        command_lock: CommandSourceLock,
        clock: Clock,
    ) -> None:
        """Wire the guard onto the reused lease, latch, and L2 lock.

        Args:
            controller: The U-4 deadman controller — the sole source of the current
                `lease_generation` and of the latched safe state.
            lease: The `LeaseManager` the controller renews and the scheduler reads —
                the single lease whose server-clock expiry this guard checks. Must be
                the same instance the controller was built with.
            command_lock: The L2 command-source lock; a command is honoured only from
                its current holder session.
            clock: The server monotonic clock — the sole authority on expiry.
        """
        self._controller = controller
        self._lease = lease
        self._command_lock = command_lock
        self._clock = clock
        # (session_id, generation) -> (last_sequence, last_timestamp_mono_client).
        # Per-stream anti-replay only; the generation itself lives in the deadman.
        self._last_accepted: dict[tuple[str, int], tuple[int, float]] = {}

    def validate(self, envelope: CommandEnvelope, role: WsRole) -> CommandVerdict:
        """Judge one command against the reused lease, the holder, and anti-replay.

        The checks run in a fixed order so each refusal has one reason: role, then
        generation, then holder, then expiry, then sequence-replay, then
        timestamp-replay. Generation precedes holder so a forced release attributes a
        prior holder's resent command to the generation bump (`CG-5-08c`).

        Args:
            envelope: The command's FR-OPS-091 metadata.
            role: The sending session's WS role; only the operator may command.

        Returns:
            (CommandVerdict) The single decision. On acceptance the anti-replay
            baseline for this `(session, generation)` is advanced.
        """
        if role is not CONTROL_HOLDER_ROLE:
            return CommandVerdict(CommandDecision.REFUSED_NOT_OPERATOR)

        if envelope.lease_generation != self._controller.current_generation:
            return CommandVerdict(CommandDecision.REFUSED_GENERATION_MISMATCH)

        holder = self._command_lock.holder
        if holder is None or holder.session_id != envelope.session_id:
            return CommandVerdict(CommandDecision.REFUSED_NOT_HOLDER)

        if self._controller.latched or self._lease.is_expired(self._clock.now()):
            return CommandVerdict(CommandDecision.REFUSED_LEASE_EXPIRED)

        key = (envelope.session_id, envelope.lease_generation)
        last = self._last_accepted.get(key)
        if last is not None:
            last_sequence, last_timestamp = last
            if envelope.sequence <= last_sequence:
                return CommandVerdict(CommandDecision.REFUSED_REPLAY_SEQUENCE)
            if envelope.timestamp_mono_client <= last_timestamp:
                return CommandVerdict(CommandDecision.REFUSED_REPLAY_TIMESTAMP)

        self._last_accepted[key] = (envelope.sequence, envelope.timestamp_mono_client)
        return CommandVerdict(CommandDecision.ACCEPTED)
