"""Stand-ins for the one thing a jog touches: a CAN channel with one DM motor on it.

No test here binds a socket. `can0`/`can1` are up and attached to a real robot, and a test that
opened one would move it.

Two decisions make these doubles able to catch a bug rather than agree with one:

* The motor answers with `can_node_watch_tests.watch_doubles.feedback_payload`, which packs with
  the vendor's own `double_to_uint` rather than with the tool's decoder run backwards.
* `unpack_mit` reads the command frame straight off `03` §2.3's byte table instead of calling the
  tool's encoder. A double that reused `jog_joint.mit_frame` would agree with any packing bug it
  has, and the property these tests exist to pin — that the first frame targets the position the
  motor is already at — lives entirely in those bytes.

The motor reports the state it was in *before* the frame it is answering, which is the DAMIAO
behaviour that makes a single-shot enable check always fail.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import can

from backend.actuation.gains import resolve_gain_profile
from backend.can.rid.layout import expected_type
from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS, MotorType
from contracts.units import Rad
from scripts.can_node_watch import (
    COMMAND_PAD_BYTE,
    DISABLE_COMMAND_CODE,
    POSITION_BITS,
    STATE_DISABLED,
    STATE_ENABLED,
    TORQUE_BITS,
    VELOCITY_BITS,
    MotorFeedback,
    feedback_id,
)
from scripts.can_node_watch_tests.watch_doubles import feedback_payload
from scripts.jog_joint import (
    DEFAULT_PROFILE_NAME,
    ENABLE_COMMAND_CODE,
    GAIN_BITS,
    KP_MAX,
    KP_MIN,
    AbortLimits,
    JogPlan,
    JogTarget,
    ResolvedGains,
    jog,
    resolve_gains,
)

# The temperatures a powered DM motor reports, degrees Celsius. Non-zero so a test can tell a
# decoded frame from a zeroed buffer.
AMBIENT_TEMP_C = 27
ROTOR_TEMP_C = 31

# Where the joint sits when a test does not say. Off zero so "the first frame targets the present
# position" cannot pass by accident against a zero-filled field.
RESTING_ANGLE = Rad(0.37)

# A wrist joint of the spatula build: fitted on this rig, DM4310, 7 N·m effort limit.
WRIST_SEND_ID = 0x07
WRIST_EFFORT_NM = 7.0
LEFT_INTERFACE = "can0"
LEFT_SIDE = "left"

# The move every wire-level test drives: a tenth of a radian, five frames each way, no gap and no
# hold. Frames go out with no pacing because nothing in a double arrives asynchronously, so the
# gap a real joint needs would only make the suite slower.
SMALL_DELTA = Rad(0.1)
SMALL_FRAMES = 5
NO_GAP_S = 0.0
NO_HOLD_FRAMES = 0

# What `resolve_gains` is passed when the run is on the profile as registered.
NO_OVERRIDE = None
TEST_LIMITS = AbortLimits(max_torque_nm=3.5, max_temp_c=80.0)

# One LSB of each signed field, for the wrist's motor type. A round trip through the frame lands
# within one of them and never exactly on the requested value: the vendor's encoder truncates, so
# an exact zero torque comes back as half an LSB negative.
POSITION_LSB_RAD = 2.0 * MOTOR_LIMIT_PARAMS[MotorType.DM4310].p_max / ((1 << POSITION_BITS) - 1)
TORQUE_LSB_NM = 2.0 * MOTOR_LIMIT_PARAMS[MotorType.DM4310].t_max / ((1 << TORQUE_BITS) - 1)

# The `kd` field is packed against [0, 5] like `kp` is against [0, 500]; the double needs both
# ranges to read a frame back, and only the kp range is worth importing from the tool (its bounds
# are what `request_refusals` judges). This is the other half of the same table (`03` §2.3).
KD_FIELD_MIN = 0.0
KD_FIELD_MAX = 5.0

_NIBBLE_MASK = 0x0F
_BYTE_BITS = 8
_NIBBLE_BITS = 4


@dataclass(frozen=True)
class MitCommand:
    """One MIT frame as read off the wire (`03` §2.3).

    Attributes:
        position: The commanded joint angle.
        velocity: The commanded velocity feed-forward.
        kp: Position gain. Zero means the frame commands no force.
        kd: Velocity gain.
        torque_ff_nm: The commanded torque feed-forward.
    """

    position: Rad
    velocity: float
    kp: float
    kd: float
    torque_ff_nm: float


def _from_uint(raw: int, low: float, high: float, bits: int) -> float:
    """Undo the vendor's linear packing (`03` §2.3 `uint_to_double`)."""
    return raw / ((1 << bits) - 1) * (high - low) + low


def is_command_frame(payload: bytes) -> bool:
    """Whether a payload is a simple command (`03` §2.5: seven pad bytes and a code)."""
    return all(byte == COMMAND_PAD_BYTE for byte in payload[:-1])


def command_code(payload: bytes) -> int:
    """The command byte of a simple command frame."""
    return payload[-1]


def unpack_mit(payload: bytes, motor_type: MotorType) -> MitCommand:
    """Read a MIT command frame back off the wire, straight from `03` §2.3's byte table.

    Args:
        payload: The eight-byte frame body.
        motor_type: The type whose scale limits the position, velocity and torque fields use.

    Returns:
        (MitCommand) What the frame commands.
    """
    limit = MOTOR_LIMIT_PARAMS[motor_type]
    position = (payload[0] << _BYTE_BITS) | payload[1]
    velocity = (payload[2] << _NIBBLE_BITS) | (payload[3] >> _NIBBLE_BITS)
    kp = ((payload[3] & _NIBBLE_MASK) << _BYTE_BITS) | payload[4]
    kd = (payload[5] << _NIBBLE_BITS) | (payload[6] >> _NIBBLE_BITS)
    torque = ((payload[6] & _NIBBLE_MASK) << _BYTE_BITS) | payload[7]
    return MitCommand(
        position=Rad(_from_uint(position, -limit.p_max, limit.p_max, POSITION_BITS)),
        velocity=_from_uint(velocity, -limit.v_max, limit.v_max, VELOCITY_BITS),
        kp=_from_uint(kp, KP_MIN, KP_MAX, GAIN_BITS),
        kd=_from_uint(kd, KD_FIELD_MIN, KD_FIELD_MAX, GAIN_BITS),
        torque_ff_nm=_from_uint(torque, -limit.t_max, limit.t_max, TORQUE_BITS),
    )


@dataclass(frozen=True)
class Reply:
    """What the motor does on one answer. A field left None keeps whatever it already was.

    Attributes:
        answers: False makes the motor silent for this frame, which is what a node that has
            dropped off the harness does — the frame goes out and nothing comes back.
        state: Overrides the state nibble from this answer on, for a protection trip or a lost
            enable.
        torque_nm: Overrides the reported torque from this answer on.
        temp_mos_c: Overrides the reported driver temperature from this answer on.
        temp_rotor_c: Overrides the reported coil temperature from this answer on.
    """

    answers: bool = True
    state: int | None = None
    torque_nm: float | None = None
    temp_mos_c: int | None = None
    temp_rotor_c: int | None = None


class FakeJogMotor:
    """One DM motor that energizes, tracks what it is commanded, and reports a stale state.

    Attributes:
        received: Every payload sent to this motor, in order. This is what the wire-level
            properties are asserted against.
        position: Where the joint is. A commanded frame with kp above zero moves it to the
            commanded target; a zero-gain frame does not, because it commands no force.
        state: The state nibble, updated by each command *after* that command's answer is built.
    """

    def __init__(self, send_id: int, position: Rad, script: list[Reply] | None) -> None:
        """Put one motor on the bus.

        Args:
            send_id: Its CAN send id.
            position: Its resting angle.
            script: One entry per answer, consumed in order; the last entry repeats once
                exhausted. None means it answers every frame, clean, forever.
        """
        self.send_id = send_id
        self.motor_type = expected_type(send_id)
        self.position = position
        self.state = STATE_DISABLED
        self.torque_nm = 0.0
        self.temp_mos_c = AMBIENT_TEMP_C
        self.temp_rotor_c = ROTOR_TEMP_C
        self.received: list[bytes] = []
        self._script = script
        self._answers = 0

    def _scripted(self) -> Reply | None:
        """The script entry governing this answer, or None when the motor is unscripted."""
        if self._script is None:
            return None
        index = min(self._answers, len(self._script) - 1)
        return self._script[index]

    def _apply(self, payload: bytes) -> None:
        """Process one frame: energize, drop, or follow a commanded position."""
        if is_command_frame(payload):
            code = command_code(payload)
            if code == ENABLE_COMMAND_CODE:
                self.state = STATE_ENABLED
            elif code == DISABLE_COMMAND_CODE:
                self.state = STATE_DISABLED
            return
        command = unpack_mit(payload, self.motor_type)
        if command.kp > 0.0:
            self.position = command.position

    def answer(self, payload: bytes) -> bytes | None:
        """Return this motor's reply to one frame, or None when it stays silent.

        The reported state is read before the frame is processed, which is the DAMIAO behaviour
        the enable poll exists for: the reply to `0xFC` still says disabled.

        Args:
            payload: The frame body.

        Returns:
            (bytes | None) The eight-byte feedback payload, or None for silence.
        """
        self.received.append(payload)
        reported_state = self.state
        self._apply(payload)
        entry = self._scripted()
        self._answers += 1
        if entry is not None:
            if not entry.answers:
                return None
            if entry.state is not None:
                reported_state = entry.state
                self.state = entry.state
            if entry.torque_nm is not None:
                self.torque_nm = entry.torque_nm
            if entry.temp_mos_c is not None:
                self.temp_mos_c = entry.temp_mos_c
            if entry.temp_rotor_c is not None:
                self.temp_rotor_c = entry.temp_rotor_c
        return feedback_payload(
            MotorFeedback(
                state=reported_state,
                motor_id=self.send_id,
                position=self.position,
                velocity=0.0,
                torque_nm=self.torque_nm,
                temp_mos_c=self.temp_mos_c,
                temp_rotor_c=self.temp_rotor_c,
            ),
            self.motor_type,
        )

    def mit_commands(self) -> list[MitCommand]:
        """Every MIT frame this motor received, decoded, in order."""
        return [
            unpack_mit(payload, self.motor_type)
            for payload in self.received
            if not is_command_frame(payload)
        ]

    def command_codes(self) -> list[int]:
        """The command byte of every simple command frame this motor received, in order."""
        return [command_code(payload) for payload in self.received if is_command_frame(payload)]


class SendFailedError(Exception):
    """Raised by `FakeJogBus` to stand in for a link that goes away mid-move."""


class FakeJogBus:
    """One CAN channel carrying one motor, with nothing bound to anything.

    Attributes:
        recv_timeouts: The timeout each receive was asked to wait, in order.
        closed: Whether `shutdown` was called.
        fail_on_send: Frame index that raises instead of sending, or None. This is how the
            disable-on-exception property is put under a failure that is not an abort the tool
            knows about.
    """

    def __init__(self, motor: FakeJogMotor, fail_on_send: int | None = None) -> None:
        """Put one motor on one channel.

        Args:
            motor: The motor present. Any other id addressed here answers nothing, which is what
                an unfitted or dead node does.
            fail_on_send: Index of the send that raises `SendFailedError`, or None when the
                link is healthy.
        """
        self._motor = motor
        self._queue: deque[can.Message] = deque()
        self._sends = 0
        self._fail_on_send = fail_on_send
        self.recv_timeouts: list[float] = []
        self.closed = False

    def send(self, msg: can.Message) -> None:
        """Queue whatever the addressed motor answers, or raise on the scripted failure."""
        index = self._sends
        self._sends += 1
        if self._fail_on_send is not None and index == self._fail_on_send:
            raise SendFailedError(f"link went away on send {index}")
        if msg.arbitration_id != self._motor.send_id:
            return
        payload = self._motor.answer(bytes(msg.data))
        if payload is None:
            return
        self._queue.append(
            can.Message(
                arbitration_id=feedback_id(self._motor.send_id),
                data=payload,
                is_extended_id=False,
                is_fd=False,
            )
        )

    def recv(self, timeout: float) -> can.Message | None:
        """Return the next queued frame, or None when nothing is waiting.

        The timeout is recorded rather than waited out: nothing arrives here asynchronously, so
        an empty queue at the start of the wait is an empty queue at the end of it.
        """
        self.recv_timeouts.append(timeout)
        return self._queue.popleft() if self._queue else None

    def shutdown(self) -> None:
        """Close the channel."""
        self.closed = True


def wrist_target() -> JogTarget:
    """The left arm's wrist joint, as `resolve_target` would have produced it."""
    return JogTarget(
        side=LEFT_SIDE,
        interface=LEFT_INTERFACE,
        send_id=WRIST_SEND_ID,
        motor_type=expected_type(WRIST_SEND_ID),
        effort_limit_nm=WRIST_EFFORT_NM,
    )


def wrist_gains() -> ResolvedGains:
    """The wrist's gains as the tool resolves them, read from the registry rather than restated.

    The wire tests only need a driving stiffness, but taking it from the default profile means a
    registry edit that broke this joint's entry surfaces here as well as at the bench.
    """
    return resolve_gains(
        resolve_gain_profile(DEFAULT_PROFILE_NAME), WRIST_SEND_ID, NO_OVERRIDE, NO_OVERRIDE
    )


def small_move_plan(returns: bool, hold_frames: int = NO_HOLD_FRAMES) -> JogPlan:
    """The judged move the wire-level tests drive.

    Args:
        returns: Whether the joint comes back.
        hold_frames: How many frames the far end is held for.

    Returns:
        (JogPlan) The move.
    """
    return JogPlan(
        target=wrist_target(),
        delta=SMALL_DELTA,
        gains=wrist_gains(),
        frames=SMALL_FRAMES,
        period_s=NO_GAP_S,
        hold_frames=hold_frames,
        returns=returns,
        limits=TEST_LIMITS,
    )


def run_jog(motor: FakeJogMotor, returns: bool, hold_frames: int = NO_HOLD_FRAMES) -> str | None:
    """Drive one whole jog against a fake channel carrying that motor.

    Args:
        motor: The motor on the channel.
        returns: Whether the joint comes back.
        hold_frames: How many frames the far end is held for.

    Returns:
        (str | None) The abort reason, or None when the joint moved and came back.
    """
    return jog(small_move_plan(returns, hold_frames), FakeJogBus(motor, None))
