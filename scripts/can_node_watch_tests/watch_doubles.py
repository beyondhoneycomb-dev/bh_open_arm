"""Stand-ins for the one thing a watch touches: a CAN channel with DM motors on it.

No test here binds a socket. The fake channel answers the disable frame the way a powered DM
motor does — a full eight-byte feedback frame at `send id + 0x10`, packed with the vendor's own
`double_to_uint` (`03` §2.3) rather than with the tool's decoder run backwards. A double that
reused the decoder would agree with any scaling bug the decoder has.

A motor that answers nothing simply enqueues nothing, which is what an absent, unpowered or
wrongly-addressed node does on a real bus: the frame goes out and the silence comes back.
"""

from __future__ import annotations

import functools
from collections import deque
from pathlib import Path
from typing import Any

import can

from backend.can.lock import LockManager
from backend.can.rid.layout import expected_type
from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS, MotorType
from backend.endeffector import RigEndEffectors, rig_path, save_rig, spatula_build
from contracts.units import Rad
from ops.hw.canbind import ArmRole, CanChannel, ChannelBinding, binding_path, save_binding
from scripts.can_node_watch import (
    POSITION_BITS,
    STATE_DISABLED,
    TORQUE_BITS,
    VELOCITY_BITS,
    ArmChannel,
    ArmTarget,
    ArmWatch,
    MotorFeedback,
    NodeReader,
    feedback_id,
)

# Two channels of one adapter, the shape this rig presents. The keys differ only in `dev_id`,
# which is the one axis that separates two channels of a multi-channel adapter.
ADAPTER_ID_PATH = "pci-0000:80:14.0-usb-0:7.1.2:1.0"
INTERFACE_A = "can0"
INTERFACE_B = "can1"

# The temperatures a powered DM motor reports, degrees Celsius. Non-zero so a test can tell a
# decoded frame from a zeroed buffer.
AMBIENT_TEMP_C = 27
ROTOR_TEMP_C = 31

# How long a fake reply is waited for. Nothing blocks, so this only has to be positive.
FAKE_REPLY_TIMEOUT_S = 0.05

# Where a joint sits until a test moves it.
RESTING_ANGLE = Rad(0.0)


def _to_uint(value: float, low: float, high: float, bits: int) -> int:
    """Pack a physical value the way the motor's own encoder does (`03` §2.3 `double_to_uint`)."""
    clamped = min(max(value, low), high)
    return int((clamped - low) / (high - low) * ((1 << bits) - 1))


def feedback_payload(feedback: MotorFeedback, motor_type: MotorType) -> bytes:
    """Pack one feedback frame as the motor would (`03` §2.7).

    Args:
        feedback: The values the motor is reporting.
        motor_type: The type whose scale limits the packing uses.

    Returns:
        (bytes) The eight-byte payload.
    """
    limit = MOTOR_LIMIT_PARAMS[motor_type]
    position = _to_uint(feedback.position.value, -limit.p_max, limit.p_max, POSITION_BITS)
    velocity = _to_uint(feedback.velocity, -limit.v_max, limit.v_max, VELOCITY_BITS)
    torque = _to_uint(feedback.torque_nm, -limit.t_max, limit.t_max, TORQUE_BITS)
    return bytes(
        (
            (feedback.state << 4) | feedback.motor_id,
            (position >> 8) & 0xFF,
            position & 0xFF,
            velocity >> 4,
            ((velocity & 0xF) << 4) | ((torque >> 8) & 0xF),
            torque & 0xFF,
            feedback.temp_mos_c,
            feedback.temp_rotor_c,
        )
    )


class FakeMotor:
    """One DM motor on the fake channel.

    Attributes:
        position: Where the joint is. A test moves it between polls the way the operator moves the
            arm by hand.
        state: The state nibble this motor reports.
        replies: One entry per poll, consumed in order; the last entry repeats once exhausted.
            `None` means it answers every poll.
    """

    def __init__(
        self,
        send_id: int,
        position: Rad = RESTING_ANGLE,
        state: int = STATE_DISABLED,
        replies: list[bool] | None = None,
    ) -> None:
        """Put one motor on the bus.

        Args:
            send_id: Its CAN send id.
            position: Its starting angle.
            state: Its starting state nibble.
            replies: The answer/no-answer script, or None to always answer.
        """
        self.send_id = send_id
        self.motor_type = expected_type(send_id)
        self.position = position
        self.state = state
        self.replies = replies
        self.polls = 0

    def answer(self) -> bytes | None:
        """Return this motor's reply to one poll, or None when it stays silent."""
        index = self.polls
        self.polls += 1
        if self.replies is not None and not self.replies[min(index, len(self.replies) - 1)]:
            return None
        return feedback_payload(
            MotorFeedback(
                state=self.state,
                motor_id=self.send_id,
                position=self.position,
                velocity=0.0,
                torque_nm=0.0,
                temp_mos_c=AMBIENT_TEMP_C,
                temp_rotor_c=ROTOR_TEMP_C,
            ),
            self.motor_type,
        )


class FakeNodeBus:
    """A CAN channel carrying a fixed set of motors, with nothing bound to anything.

    Attributes:
        sent: Every frame the watch transmitted, in order. This is what pins which ids were
            addressed and what was in the payload.
        recv_timeouts: The timeout each receive was asked to wait, in order. A poll's first
            receive is the drain and asks for none; the ones after it wait out the reply window.
        closed: Whether `shutdown` was called.
    """

    def __init__(self, motors: dict[int, FakeMotor]) -> None:
        """Put a set of motors on one channel.

        Args:
            motors: The motors present, keyed by send id. An id absent from this map answers
                nothing, which is what an unfitted or dead node does.
        """
        self._motors = motors
        self._queue: deque[can.Message] = deque()
        self.sent: list[can.Message] = []
        self.recv_timeouts: list[float] = []
        self.closed = False

    def send(self, msg: can.Message) -> None:
        """Record the frame and queue whatever the addressed motor answers."""
        self.sent.append(msg)
        motor = self._motors.get(msg.arbitration_id)
        if motor is None:
            return
        payload = motor.answer()
        if payload is None:
            return
        self._queue.append(
            can.Message(
                arbitration_id=self.reply_id(motor.send_id),
                data=payload,
                is_extended_id=False,
                is_fd=False,
            )
        )

    def reply_id(self, send_id: int) -> int:
        """The CAN id this channel's answers carry. Overridden to model a misaddressed reply."""
        return feedback_id(send_id)

    def recv(self, timeout: float) -> can.Message | None:
        """Return the next queued frame, or None when nothing is waiting.

        The timeout is recorded rather than waited out: nothing arrives here asynchronously, so an
        empty queue at the start of the wait is an empty queue at the end of it.
        """
        self.recv_timeouts.append(timeout)
        return self._queue.popleft() if self._queue else None

    def shutdown(self) -> None:
        """Close the channel."""
        self.closed = True

    def sent_ids(self) -> list[int]:
        """The CAN ids this channel was asked to address, in order."""
        return [message.arbitration_id for message in self.sent]


class MisaddressedBus(FakeNodeBus):
    """A channel where every answer carries a different motor's feedback id.

    The shape of a real bus under load: replies from several motors are in flight at once, and the
    frame that arrives inside one motor's reply window is often another motor's. A reader that
    counted whatever arrived would score a dead node off its neighbour's traffic.
    """

    def __init__(self, motors: dict[int, FakeMotor], id_shift: int) -> None:
        """Answer every send under a shifted feedback id.

        Args:
            motors: The motors present, keyed by send id.
            id_shift: Added to the correct feedback id, so no answer matches what was asked.
        """
        super().__init__(motors)
        self._id_shift = id_shift

    def reply_id(self, send_id: int) -> int:
        """The shifted id, which is nobody's answer to the frame that was sent."""
        return feedback_id(send_id) + self._id_shift


def motors_for(send_ids: tuple[int, ...]) -> dict[int, FakeMotor]:
    """A fully answering motor per send id."""
    return {send_id: FakeMotor(send_id) for send_id in send_ids}


def target(side: str, interface: str, send_ids: tuple[int, ...]) -> ArmTarget:
    """One arm to watch."""
    return ArmTarget(side=side, interface=interface, send_ids=send_ids)


def arm_channel(arm: ArmTarget, bus: FakeNodeBus) -> ArmChannel:
    """Bind an arm's watch to a fake channel."""
    return ArmChannel(watch=ArmWatch(arm), reader=NodeReader(bus, FAKE_REPLY_TIMEOUT_S))


def channel(interface: str, dev_id: str, state: str = "ERROR-ACTIVE") -> CanChannel:
    """One CAN channel as `list_can_channels` reports it."""
    return CanChannel(
        interface=interface,
        id_path=ADAPTER_ID_PATH,
        dev_id=dev_id,
        driver="peak_usb",
        state=state,
        bitrate_bps=1_000_000,
    )


def two_channels(state: str = "ERROR-ACTIVE") -> tuple[CanChannel, ...]:
    """The pair of channels this rig presents."""
    return (channel(INTERFACE_A, "0x0", state), channel(INTERFACE_B, "0x1", state))


def channel_lister(channels: tuple[CanChannel, ...]) -> Any:
    """A stand-in for `list_can_channels` that reports a fixed set."""
    return functools.partial(list, channels)


def lock_manager_factory(lock_dir: Path) -> Any:
    """A `LockManager` factory confined to a temporary lock directory."""
    return functools.partial(LockManager, lock_dir=str(lock_dir))


def write_bench_records(
    config_directory: Path,
    channels: tuple[CanChannel, ...],
    rig: RigEndEffectors | None = None,
) -> None:
    """Write the binding and end-effector records a watch resolves its targets from.

    Args:
        config_directory: Where the records go.
        channels: The channels the left and right followers are bound to, in that order.
        rig: What each arm carries; both arms on the spatula build when omitted, which is what
            this bench has fitted.
    """
    save_binding(
        binding_path(config_directory),
        ChannelBinding(
            roles={
                ArmRole.FOLLOWER_LEFT: channels[0].channel_key,
                ArmRole.FOLLOWER_RIGHT: channels[1].channel_key,
            }
        ),
    )
    save_rig(
        rig_path(config_directory),
        rig if rig is not None else RigEndEffectors(left=spatula_build(), right=spatula_build()),
    )
