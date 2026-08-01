"""Joining the enforcement point's accepted output to the single writer.

The gateway decides and the scheduler writes. Verified apart both hold; joined wrongly the
scheduler's guarantee stops meaning anything, because that guarantee is about what reaches
the bus. A target published straight onto the mailbox is judged only by the decider's
position clamp, and a position clamp admits an unsafe *rate*: an angle well inside the joint
envelope, asked for in one control period. Only the ordered eight-check filter refuses that,
so the filter's verdict is what the mailbox has to carry.

The argument type is the enforcement. `offer` takes a `GateResult`, and the only place one is
constructed is `ActuationGateway.submit`, so a position vector that never met the filter has
no shape in which to arrive here. A refusal is not dropped on the way either:
`GateResult.accepted` is the present pose on a rejection, so a refused command reaches the
scheduler as the hold it was turned into rather than as the target it asked for.

What lands in `TimestampedTarget.request` is therefore post-filter, and the decider's
`clamp_request` then runs over a vector already inside the envelope — idempotent, not a
second opinion. Nothing is lost by that: the pre-clamp request stays on the gateway side in
`GateFrame`, which is where the audit pair (`00` §8.3) lives.

A round publishes both arms or neither. The mailbox slot is one bimanual target, so filling
half of it from this command and the other half from whatever was there before hands the
scheduler a frame no single decision produced. The pair is judged whole and refused whole
(`BiOaOpenArmFollower.send_action`), so it is published whole.
"""

from __future__ import annotations

from backend.actuation.clock import Clock
from backend.actuation.enforcement import GateResult
from backend.actuation.mailbox import TargetMailbox, TimestampedTarget
from contracts.action import RequestedPositionAction
from contracts.units import Deg, Nm


class AcceptedTargetPublisher:
    """The one path from an enforcement decision onto the scheduler's mailbox.

    Ownership: holds the mailbox it publishes into and the clock the scheduler reads
    freshness against. It holds no gateway, no producer and no CAN handle, so it can decide
    nothing — it only carries a decision already made.

    Threading: one publisher serves one bimanual pair, driven from the thread that commands
    it. The per-side decisions of a round are buffered between `offer` calls, so two threads
    offering concurrently would publish interleaved halves.
    """

    def __init__(self, mailbox: TargetMailbox, clock: Clock, sides: tuple[str, ...]) -> None:
        """Bind the publisher to the mailbox, the scheduler's clock, and the arm order.

        Args:
            mailbox: The single-slot channel the scheduler tick reads.
            clock: The source the published timestamp is taken from. It must be the clock the
                scheduler ticks against: freshness is a comparison on one time base, and two
                sources let a stale target read as fresh. Required rather than defaulted, for
                the reason `FreedriveProducer` requires one.
            sides: The arm names in the order their joints occupy the bimanual vector
                (arm-major, `contracts/action_observation.yaml` `joints.arms`). A round
                publishes once every one of these has offered a decision.

        Raises:
            ValueError: If `sides` is empty, or names a side twice. Both make a round
                uncompletable — a round is complete when one decision is buffered per
                declared side, and a name that appears twice can only ever hold one — so the
                pair would publish nothing for as long as it ran, and an arm commanded into
                silence looks exactly like an arm holding on purpose.
        """
        if not sides:
            raise ValueError("a publisher with no declared sides can never complete a round")
        if len(set(sides)) != len(sides):
            raise ValueError(
                f"declared sides {list(sides)} repeat a name; a repeated side buffers one "
                "decision against two slots, so no round it opens can ever complete"
            )
        self._mailbox = mailbox
        self._clock = clock
        self._sides = sides
        self._pending: dict[str, GateResult] = {}

    def offer(self, side: str, decision: GateResult) -> TimestampedTarget | None:
        """Record one arm's decision, publishing the pair once every side has offered one.

        Args:
            side: Which arm the decision belongs to.
            decision: The gateway's verdict for that arm — its accepted target, or the
                present-pose hold a refusal was turned into.

        Returns:
            (TimestampedTarget | None) The target published, or None while the round is still
            missing a side.

        Raises:
            ValueError: If `side` is not one of the declared sides. What completes a round is
                a count of buffered decisions, and that count cannot see which sides they
                came from — an undeclared name pushes it over the line with a declared arm
                still missing. Refusing the name at the door is what keeps the count from
                lying about which arms have been judged.
        """
        if side not in self._sides:
            raise ValueError(f"side {side!r} is not one of the declared arms {list(self._sides)}")
        self._pending[side] = decision
        if len(self._pending) < len(self._sides):
            return None

        positions: list[Deg] = []
        torques: list[Nm] = []
        for name in self._sides:
            offered = self._pending[name]
            positions.extend(offered.accepted)
            torques.extend(offered.feedforward_torque_nm)
        target = TimestampedTarget(
            request=RequestedPositionAction(values=tuple(positions)),
            published_at=self._clock.now(),
            feedforward_torque=tuple(torques),
        )
        self._mailbox.publish(target)
        self._pending = {}
        return target
