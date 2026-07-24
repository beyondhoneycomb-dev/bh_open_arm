"""Remote-disconnect classification — transport vs empty-action as distinct codes.

`FR-INF-046` refuses to lump remote failures into one bucket. The load-bearing split
is (a) a **transport** disconnect — the gRPC channel is down, an RPC deadline lapsed,
or the `Ready` readiness probe failed — versus (b) an **empty-action** — the channel
is fine but the server returned no action. CG-4A-08d requires these to classify to
**different error codes**, because their recoveries differ: a transport loss waits on
the server coming back, an empty-action waits on the server producing output.

The registry (`14` §2.10) gives exactly the two codes this needs:

- `OA-INF-001` "policy server unresponsive" — recovery "즉시 홀드 + 액션 큐 비움.
  stale 액션 실행 금지" — covers TRANSPORT and STALE_ACTION (session epoch / wall-age
  violations, which are the same "do not execute stale" family).
- `OA-INF-002` "action queue exhausted" — covers EMPTY_ACTION and QUEUE_WAIT_TIMEOUT.

`obs_queue_timeout` (2 s) is classified as its own `QUEUE_WAIT_TIMEOUT` and marked
**not** a network disconnect (`is_network_disconnect` False): `FR-INF-046` is explicit
that it is a queue-wait timeout, not a network timeout, and conflating it with
TRANSPORT would misattribute a slow consumer as a dead link.

The hold a disconnect provokes is a **Cat-2 controlled stop** — the committed Wave 2C
`ReactionStrategy.STOP_HOLD` (`StopCategory.CAT_2`), reused here rather than renamed,
so "protective stop" means the one thing across the collision and disconnect paths.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from backend.reaction import ReactionStrategy, StopCategory, properties
from contracts.errors import codes

# The protective stop a remote disconnect drives is the Wave 2C category-2 controlled
# stop (power kept, no fall): `FR-INF-046` "protective stop (Cat-2 controlled stop)".
# Reusing the committed strategy keeps a single definition of what a Cat-2 hold is.
PROTECTIVE_STOP_STRATEGY = ReactionStrategy.STOP_HOLD
PROTECTIVE_STOP_CATEGORY = StopCategory.CAT_2


class DisconnectClass(Enum):
    """The distinct remote-failure classes `FR-INF-046` requires kept apart.

    TRANSPORT and STALE_ACTION are network/session failures (`is_network_disconnect`
    True); EMPTY_ACTION and QUEUE_WAIT_TIMEOUT are not — the channel is alive, so a
    queue-wait timeout is not a dead link.
    """

    TRANSPORT = "transport"
    STALE_ACTION = "stale_action"
    EMPTY_ACTION = "empty_action"
    QUEUE_WAIT_TIMEOUT = "queue_wait_timeout"


# Each class to its canonical registry code (`14` §2.10). TRANSPORT and EMPTY_ACTION
# resolve to *different* codes — the CG-4A-08d invariant — and the two network-family
# and two queue-family classes reuse the two codes the registry actually defines
# rather than inventing unregistered ones.
DISCONNECT_ERROR_CODES: dict[DisconnectClass, str] = {
    DisconnectClass.TRANSPORT: codes.OA_INF_001,
    DisconnectClass.STALE_ACTION: codes.OA_INF_001,
    DisconnectClass.EMPTY_ACTION: codes.OA_INF_002,
    DisconnectClass.QUEUE_WAIT_TIMEOUT: codes.OA_INF_002,
}

_NETWORK_CLASSES = frozenset({DisconnectClass.TRANSPORT, DisconnectClass.STALE_ACTION})


@dataclass(frozen=True)
class RemoteHealth:
    """One tick's remote-inference health signals, snapshotted for classification.

    Attributes:
        transport_ok: Whether the gRPC channel is up.
        ready_ok: Whether the server's `Ready` readiness probe passed.
        rpc_deadline_exceeded: Whether the last RPC exceeded its deadline.
        session_epoch: The session epoch the last action carried.
        expected_epoch: The session epoch the client expects; a mismatch is stale.
        observation_wall_age_sec: Wall-clock age of the observation the action was
            computed from.
        max_wall_age_sec: The maximum tolerated observation wall-age.
        action: The action the server returned this tick, or None/empty for an
            empty-action.
        queue_wait_timed_out: Whether the `obs_queue_timeout` (2 s) queue-wait lapsed
            — a queue-wait timeout, explicitly NOT a network timeout (`FR-INF-046`).
    """

    transport_ok: bool
    ready_ok: bool
    rpc_deadline_exceeded: bool
    session_epoch: int
    expected_epoch: int
    observation_wall_age_sec: float
    max_wall_age_sec: float
    action: Sequence[float] | None
    queue_wait_timed_out: bool


def is_network_disconnect(disconnect_class: DisconnectClass) -> bool:
    """Whether a class is a network/session loss rather than a live-channel event.

    Args:
        disconnect_class: The class to test.

    Returns:
        (bool) True for TRANSPORT and STALE_ACTION; False for EMPTY_ACTION and
        QUEUE_WAIT_TIMEOUT (the channel is alive) — encoding `FR-INF-046`'s rule that
        `obs_queue_timeout` is not a network timeout.
    """
    return disconnect_class in _NETWORK_CLASSES


def error_code_for(disconnect_class: DisconnectClass) -> str:
    """Resolve a disconnect class to its registered OA-INF code.

    Args:
        disconnect_class: The class to map.

    Returns:
        (str) The canonical registry code (a `contracts.errors.codes` symbol value).
    """
    return DISCONNECT_ERROR_CODES[disconnect_class]


def classify_remote(health: RemoteHealth) -> DisconnectClass | None:
    """Classify a tick's remote health, or None when the remote path is healthy.

    Priority is transport first (a dead link subsumes everything downstream of it),
    then staleness (a live link delivering stale actions), then empty-action (a live,
    fresh link that returned nothing), then a queue-wait timeout. The order matters:
    an empty action over a dead channel is a TRANSPORT loss, not an EMPTY_ACTION, so
    transport must be decided before the action contents are inspected.

    Args:
        health: This tick's snapshotted remote signals.

    Returns:
        (DisconnectClass | None) The class of failure, or None when healthy.
    """
    if not health.transport_ok or health.rpc_deadline_exceeded or not health.ready_ok:
        return DisconnectClass.TRANSPORT
    if (
        health.session_epoch != health.expected_epoch
        or health.observation_wall_age_sec > health.max_wall_age_sec
    ):
        return DisconnectClass.STALE_ACTION
    if health.action is None or len(health.action) == 0:
        return DisconnectClass.EMPTY_ACTION
    if health.queue_wait_timed_out:
        return DisconnectClass.QUEUE_WAIT_TIMEOUT
    return None


def protective_stop_is_category_two() -> bool:
    """Confirm the reused protective-stop strategy is a category-2 hold (no fall).

    A remote disconnect must protective-stop as a Cat-2 controlled stop
    (`FR-INF-046`), and this reads that fact from the committed Wave 2C strategy table
    rather than restating it — if a future change made STOP_HOLD fall, this stops
    being true and the disconnect path's hold assumption is caught.

    Returns:
        (bool) True when STOP_HOLD is category 2 and does not drop the arm.
    """
    facts = properties(PROTECTIVE_STOP_STRATEGY)
    return facts.category is PROTECTIVE_STOP_CATEGORY and not facts.causes_fall
