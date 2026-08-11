"""Move one motor a relative angle, slowly, and bring it back.

This is the first thing in this repository that makes a motor move, and it is deliberately the
smallest thing that can: one joint, one ramp, one return.

Four properties carry the safety of this file. Each names the function that holds it, and the
first is the one that throws an arm:

1. The first MIT frame after enable targets the position the motor is at *right now*. A motor
   enabled with a target it is not already at drives to that target at once, with a force
   proportional to kp. The resting position is read torque-free first — 0xFD answers with a full
   feedback frame — and every leg departs from it (`plan_legs`).
2. The target moves by ramp, never by jump (`ramp`).
3. Each frame's answer is judged before the next one goes out: torque, temperature, fault nibble
   and a lost enable each stop the run (`abort_reason`).
4. `finally` disables on every exit path, exceptions and Ctrl-C included (`jog`).

Enable confirmation is polled rather than read once. A DAMIAO answer carries the state the motor
was in *before* it processed the command, so the first reply after 0xFC still says disabled and a
single-shot check always fails. The poll frames carry kp = kd = 0, which command no force, so the
polling itself cannot move anything (`wait_until_enabled`).

An abort disables, and disabling a brakeless arm that was holding itself up drops it. The
shoulder's gravity hold reaches 11.67 N·m, so the abort torque is a fraction of that joint's own
effort limit rather than one small fixed number: a ceiling below the gravity hold would fire on a
healthy arm and turn a jog into a fall. The first move on this rig belongs on a wrist joint, with
a hand near the arm.

The gains are not a knob on this tool. It names a profile from the `03` §2.8 registry and reads
this joint's pair out of it (`--profile`), because one scalar kp is wrong at one end of the arm or
the other: `compliant` puts the elbow at 60 and the wrist at 10, and the difference is measured,
not argued (`DEFAULT_PROFILE_NAME`). `--override-kp` / `--override-kd` replace one half by hand for
probing, and every line that reports the gains says which halves were overridden.

No detached worker and no wall-clock timetable here, unlike `torque_session` and
`canbind_session`. Those fork because their measurement steps are long and the operator must act
at a stated instant, and a line printed by a still-running command reaches the terminal after the
instant it names. This run is short, the operator watches the joint throughout, and the only
instant that matters is now — a schedule would be ceremony. Do not add one.

The wire protocol is `scripts.can_node_watch`'s, imported rather than copied: a second decoder
agrees with any bug the first one has. 0xFC is this file's alone — the watch is torque-free by
construction and says so.

Exit codes, which are the verdict:

    0  the joint moved and came back
    1  refused before anything opened, or the motor never answered
    2  argparse's usage error — nothing was opened and nothing ran
    3  the move started and was aborted; read the reason, the motor is disabled

Entry point is `scripts/jog_joint.sh`.
"""

from __future__ import annotations

import argparse
import shlex
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import can

from backend.actuation.gains import (
    COMPLIANT,
    NamedGainProfile,
    UnknownGainProfileError,
    profile_names,
    resolve_gain_profile,
)
from backend.can.lock import LockManager, assert_lock_held
from backend.can.rid.layout import expected_type
from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS, MotorType
from backend.config.store import default_config_directory
from backend.endeffector import (
    ARM_JOINT_SEND_IDS,
    SIDES,
    RigEndEffectors,
    default_rig,
    load_rig,
    rig_path,
)
from backend.excitation.constants import DEFAULT_MAX_MOTOR_TEMP_C
from backend.jog import frame_count
from backend.safety_bringup.constants import URDF_EFFORT_LIMIT_NM
from backend.temp_gripper.constants import COIL_TEMP_FAULT_CAP_C
from contracts.units import Deg, Rad, deg_to_rad, rad_to_deg
from ops.hw.canbind import (
    BindingError,
    CanChannel,
    binding_path,
    bring_up_command,
    check_binding,
    list_can_channels,
    load_binding,
)
from scripts.can_node_watch import (
    DISABLE_COMMAND_CODE,
    FEEDBACK_FRAME_LENGTH,
    LABEL_BY_SIDE,
    LINK_BITRATE_BPS,
    LINK_DATA_BITRATE_BPS,
    LINK_IS_CAN_FD,
    POSITION_BITS,
    ROLE_BY_SIDE,
    STATE_ENABLED,
    TORQUE_BITS,
    VELOCITY_BITS,
    MotorFeedback,
    NodeBus,
    command_frame,
    decode_feedback,
    drain,
    feedback_id,
)

EXIT_OK = 0
EXIT_REFUSED = 1

# The move started and stopped early. Distinct from EXIT_REFUSED because the two want opposite
# responses: a refusal means fix the bench and run again, an abort means the motor reported
# something while energized and the reason is the finding. Three rather than two because argparse
# exits 2 on a usage error, and a caller reading "the arm moved and something stopped it" off a
# mistyped flag is the one confusion this tool cannot afford.
EXIT_ABORTED = 3


# --- The one frame `can_node_watch` is not allowed to send ---

# Enable (`03` §2.5, FR-MOT-022). Every other frame this file puts on the wire is either the
# watch's disable frame or a MIT command; this is the code that energizes, and it is why this
# tool refuses what the watch merely reports.
ENABLE_COMMAND_CODE = 0xFC


# --- MIT command frame (`03` §2.3) ---

# kp and kd are packed against a fixed range that does not depend on the motor (`03` §2.3 table,
# FR-MOT-018). Position, velocity and torque use the per-type ranges in `MOTOR_LIMIT_PARAMS`.
KP_MIN = 0.0
KP_MAX = 500.0
KD_MIN = 0.0
KD_MAX = 5.0
GAIN_BITS = 12

# Field widths shared with the feedback frame are imported rather than restated; these are the
# packing helpers' own.
BYTE_MASK = 0xFF
NIBBLE_MASK = 0x0F
BYTE_BITS = 8
NIBBLE_BITS = 4

# This runner commands position only. The MIT frame also carries a velocity feed-forward and a
# torque feed-forward, and both stay at zero: a jog that also injected torque would be commanding
# two things at once and could not attribute what came back.
COMMAND_VELOCITY_RAD_S = 0.0
COMMAND_TORQUE_FF_NM = 0.0

# The gains a poll frame carries. Zero on both means the motor computes no force from it, which
# is what makes it safe to send at a motor whose state is not yet known (`03` §2.3: the commanded
# effort is kp·(q_des − q) + kd·(dq_des − dq) + tau, and all three terms vanish).
PROBE_KP = 0.0
PROBE_KD = 0.0


# --- Timing ---

# How long one motor's reply is waited for. The bench round trip is sub-millisecond; this only
# has to cover a scheduling hiccup, and a longer window on a silent motor is a longer window with
# the arm energized and nothing being judged.
REPLY_TIMEOUT_S = 0.05

# The enable command's own reply window and how many zero-gain frames confirmation is polled for.
# The count is generous because the cost of one more poll is one more no-force frame, and the
# cost of giving up early is a run that reports "enable failed" at a motor that was about to
# report enabled.
ENABLE_REPLY_TIMEOUT_S = 0.2
ENABLE_POLL_ATTEMPTS = 20
ENABLE_POLL_PERIOD_S = 0.02


# --- Move defaults ---

# The profile a run uses when the operator names none. `compliant` is the softest set `03` §2.8
# registers and the one this tool's job asks for: one unloaded joint, moved by hand-sized deltas,
# with a hand near the arm. Soft also keeps the run readable — the position error printed on each
# line is visible under a soft gain and near zero under a stiff one, and that error is the only
# thing on screen saying the joint is following.
#
# Per joint rather than one number, and that part is measured: on this rig kp=10 moved the elbow
# 0.02° of a commanded 5°, while kp=60 moved it 3.4°. `compliant` declares J4 kp=60 and J7 kp=10,
# so the registry already held both answers — a single default would have been wrong at one end of
# the arm whichever value it took.
DEFAULT_PROFILE_NAME = COMPLIANT

# The flags that replace one half of a profile's pair by hand. Named, and named as overrides, so a
# run on `--override-kp 60` cannot be read back as a run on a registered profile.
OVERRIDE_KP_FLAG = "--override-kp"
OVERRIDE_KD_FLAG = "--override-kd"

DEFAULT_RAMP_SECONDS = 2.0
DEFAULT_RAMP_HZ = 20.0
DEFAULT_HOLD_SECONDS = 1.0

# A ramp needs both of its ends: one frame would be the jump property 1 exists to forbid.
MIN_RAMP_FRAMES = 2

# The abort torque, as a fraction of that joint's URDF effort limit (`URDF_EFFORT_LIMIT_NM` —
# 40/40/27/27/7/7/7). A flat small number cannot work here: the shoulder's gravity hold alone
# reaches 11.67 N·m, so a 2 N·m ceiling fires on a healthy arm — and an abort disables, which on a
# brakeless shoulder is the fall it was meant to prevent. Half the effort limit clears the
# shoulder's gravity hold (20.0 against 11.67) and still stops the wrist at 3.5 N·m, well above
# its 0.53 N·m hold and well under its 7 N·m limit.
ABORT_TORQUE_FRACTION_OF_EFFORT = 0.5

# The largest relative move this runner accepts, degrees. It is a typo bound, not a limit check:
# this tool reads no joint limit and no collision geometry, so it cannot tell an operator whether
# a joint has the travel. What it can catch is the realistic mistake — a radian value typed into a
# degree field, or one extra digit — and a move larger than this is several jogs, watched.
MAX_DELTA_DEG = 30.0

# What each stretch of the run is called on the progress lines.
LEG_NAMES = ("이동", "복귀")
HOLD_LEG_NAME = "유지"

# How often a progress line is printed. Every frame at 20 Hz scrolls faster than an operator can
# read while also watching the joint; the last frame of a leg is always printed regardless.
PROGRESS_EVERY_N_FRAMES = 5

# `URDF_EFFORT_LIMIT_NM` is indexed by joint, and this rig's joints start at CAN send id 0x01.
FIRST_ARM_SEND_ID = ARM_JOINT_SEND_IDS[0]


class JogRefusedError(Exception):
    """Raised when the move cannot be set up from what is on the bench right now."""


# --- Argument conversion ---


def can_id(text: str) -> int:
    """Read a CAN send id written in any base, so `0x07` and `7` both work.

    Args:
        text: The argument as typed.

    Returns:
        (int) The id.

    Raises:
        ArgumentTypeError: When it is not a number.
    """
    try:
        return int(text, 0)
    except ValueError as bad:
        raise argparse.ArgumentTypeError(f"{text!r} is not a CAN id") from bad


def gain_profile(text: str) -> NamedGainProfile:
    """Resolve a registered gain profile by name (`03` §2.8), refusing an unknown one.

    Args:
        text: The profile name as typed.

    Returns:
        (NamedGainProfile) The registered set.

    Raises:
        ArgumentTypeError: When no profile carries that name. The registry refuses rather than
            substituting a default (`13` FR-GUI-068), and raising here keeps that refusal on the
            usage line, where the operator reads which names exist.
    """
    try:
        return resolve_gain_profile(text)
    except UnknownGainProfileError as unknown:
        raise argparse.ArgumentTypeError(str(unknown)) from unknown


def positive_float(text: str) -> float:
    """Read a rate or a duration that has to be above zero.

    A zero rate divides by zero building the plan and a zero ramp duration emits no frames, so
    both are rejected where the operator can see which flag they typed.

    Args:
        text: The argument as typed.

    Returns:
        (float) The value.

    Raises:
        ArgumentTypeError: When it is not a number, or is not above zero.
    """
    value = _as_float(text)
    if value <= 0.0:
        raise argparse.ArgumentTypeError(f"{text!r} must be above zero")
    return value


def non_negative_float(text: str) -> float:
    """Read a duration that may be zero, which is how a hold is turned off.

    Args:
        text: The argument as typed.

    Returns:
        (float) The value.

    Raises:
        ArgumentTypeError: When it is not a number, or is negative.
    """
    value = _as_float(text)
    if value < 0.0:
        raise argparse.ArgumentTypeError(f"{text!r} may not be negative")
    return value


def _as_float(text: str) -> float:
    """Parse a float argument, reporting a bad one as a usage error."""
    try:
        return float(text)
    except ValueError as bad:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from bad


# --- Frames ---


def _to_uint(value: float, low: float, high: float, bits: int) -> int:
    """Pack a physical value the way the motor's encoder does (`03` §2.3 `double_to_uint`).

    The clamp is the vendor's and is silent, which is why `request_refusals` rejects an
    out-of-range gain instead of letting it be quietly trimmed on the way out (FR-MOT-018).

    Args:
        value: The physical value.
        low: Bottom of the encoded range.
        high: Top of the encoded range.
        bits: Field width.

    Returns:
        (int) The packed integer.
    """
    clamped = min(max(value, low), high)
    return int((clamped - low) / (high - low) * ((1 << bits) - 1))


def mit_frame(motor_type: MotorType, position: Rad, kp: float, kd: float) -> bytes:
    """Build a MIT position command (`03` §2.3).

    Args:
        motor_type: The type registered at this id, which fixes the position scaling.
        position: The commanded joint angle.
        kp: Position gain. Zero commands no force whatever the position error is.
        kd: Velocity gain.

    Returns:
        (bytes) The eight-byte payload, sent at the motor's own CAN id with no mode offset.
    """
    # DM4340 V_MAX in this table is 10.0, read off this bench's RID 22 — not the 8 the LeRobot
    # table carries. It scales the velocity field, and the same table decodes the answer.
    limit = MOTOR_LIMIT_PARAMS[motor_type]
    q = _to_uint(position.value, -limit.p_max, limit.p_max, POSITION_BITS)
    dq = _to_uint(COMMAND_VELOCITY_RAD_S, -limit.v_max, limit.v_max, VELOCITY_BITS)
    kp_packed = _to_uint(kp, KP_MIN, KP_MAX, GAIN_BITS)
    kd_packed = _to_uint(kd, KD_MIN, KD_MAX, GAIN_BITS)
    tau = _to_uint(COMMAND_TORQUE_FF_NM, -limit.t_max, limit.t_max, TORQUE_BITS)
    return bytes(
        (
            (q >> BYTE_BITS) & BYTE_MASK,
            q & BYTE_MASK,
            dq >> NIBBLE_BITS,
            ((dq & NIBBLE_MASK) << NIBBLE_BITS) | ((kp_packed >> BYTE_BITS) & NIBBLE_MASK),
            kp_packed & BYTE_MASK,
            kd_packed >> NIBBLE_BITS,
            ((kd_packed & NIBBLE_MASK) << NIBBLE_BITS) | ((tau >> BYTE_BITS) & NIBBLE_MASK),
            tau & BYTE_MASK,
        )
    )


class MotorLink:
    """One motor's request-and-answer channel over an open CAN socket.

    Ownership: borrows the bus and closes nothing; `jog` opened it and `jog` closes it.

    Every exchange drains first. Without that, a reply that arrived after its own frame timed out
    would be read as the answer to the *next* frame, and a motor answering one command late would
    look like a motor that is following.
    """

    def __init__(self, bus: NodeBus, send_id: int, motor_type: MotorType) -> None:
        """Bind the link to one motor on one open channel.

        Args:
            bus: The open channel.
            send_id: The motor's CAN send id.
            motor_type: The type registered at that id, which fixes the frame scaling.
        """
        self._bus = bus
        self._send_id = send_id
        self._motor_type = motor_type

    @property
    def motor_type(self) -> MotorType:
        """The type registered at this motor's id."""
        return self._motor_type

    def exchange(self, payload: bytes, reply_timeout_s: float) -> MotorFeedback | None:
        """Send one frame and return what this motor answered.

        Args:
            payload: The eight-byte frame body.
            reply_timeout_s: How long this motor's reply is waited for.

        Returns:
            (MotorFeedback | None) The decoded answer, or None when nothing carrying this motor's
            feedback id arrived in the window. Frames from other motors are discarded rather than
            accepted: an answer is only an answer when it is addressed to the question.
        """
        drain(self._bus)
        self._bus.send(
            can.Message(
                arbitration_id=self._send_id,
                data=payload,
                is_extended_id=False,
                is_fd=False,
            )
        )
        wanted = feedback_id(self._send_id)
        deadline = time.perf_counter() + reply_timeout_s
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return None
            message = self._bus.recv(timeout=remaining)
            if message is None:
                return None
            if message.arbitration_id == wanted and len(message.data) >= FEEDBACK_FRAME_LENGTH:
                return decode_feedback(bytes(message.data), self._motor_type)


# --- What is on the bench: which channel, which motor, and its ceilings ---


@dataclass(frozen=True)
class JogTarget:
    """The one motor this run addresses, resolved before anything opens.

    Attributes:
        side: The declared arm side.
        interface: The kernel interface its channel is on right now, resolved from the persisted
            binding — never taken as an argument and never guessed from the interface name.
        send_id: The motor's CAN send id, checked against the fitted set.
        motor_type: The type registered at that id.
        effort_limit_nm: That joint's URDF effort limit, which bounds the abort torque.
    """

    side: str
    interface: str
    send_id: int
    motor_type: MotorType
    effort_limit_nm: float

    @property
    def default_abort_torque_nm(self) -> float:
        """The abort torque used when the operator names none."""
        return self.effort_limit_nm * ABORT_TORQUE_FRACTION_OF_EFFORT

    @property
    def label(self) -> str:
        """How this motor is named on screen."""
        return (
            f"{LABEL_BY_SIDE[self.side]} {self.interface} {self.send_id:#04x} "
            f"({self.motor_type.value})"
        )


def end_effector_rig(config_directory: Path) -> RigEndEffectors:
    """Return what each arm carries, from the operator's record or the no-gripper default.

    Args:
        config_directory: Where the end-effector record lives.

    Returns:
        (RigEndEffectors) What each arm carries. The fallback is the gripper-less build for the
        reason `can_node_watch` and `torque_session` share it: assuming a gripper on a rig without
        one addresses an id nobody answers on, which walks the controller to ERROR-PASSIVE and
        degrades the seven joints that are present.
    """
    record = rig_path(config_directory)
    return load_rig(record) if record.is_file() else default_rig()


def resolve_target(
    side: str, send_id: int, config_directory: Path, channels: tuple[CanChannel, ...]
) -> JogTarget:
    """Resolve one arm and motor to the channel to open and the ceilings to judge against.

    Args:
        side: The declared arm side.
        send_id: The requested CAN send id.
        config_directory: Where the binding and end-effector records live.
        channels: The CAN channels enumerated right now.

    Returns:
        (JogTarget) The motor to address.

    Raises:
        JogRefusedError: When the bench records cannot be read, when the arm's channel is not
            present, or when the id is not an arm joint fitted to that arm. The last is the sharp
            one: addressing a motor that is not on the bus walks the controller to ERROR-PASSIVE
            and degrades the joints that are.
    """
    try:
        binding = load_binding(binding_path(config_directory))
        rig = end_effector_rig(config_directory)
    except (BindingError, OSError, ValueError) as refusal:
        raise JogRefusedError(
            f"벤치 기록을 읽을 수 없다: {refusal}. 어느 팔이 어느 채널인지, 어느 모터가 달려 "
            "있는지는 버스에서 알아낼 수 없다 — 되돌아갈 기본값이 없다."
        ) from refusal

    role = ROLE_BY_SIDE[side]
    interface = check_binding(binding, channels).resolved.get(role)
    if interface is None:
        raise JogRefusedError(
            f"{role.value} 의 채널이 지금 없다. 어댑터가 다른 포트로 옮겨졌거나 다른 것이 꽂혀 "
            "있다. ./scripts/canbind_session.sh 로 다시 식별한다 — 인터페이스 이름으로 짐작하는 "
            "것이 바인딩 기록이 막으려는 바로 그 일이다."
        )

    fitted = rig.for_side(side).motor_send_ids
    if send_id not in fitted:
        raise JogRefusedError(
            f"{send_id:#04x} 는 {LABEL_BY_SIDE[side]}에 달려 있지 않다. 장착된 모터는 "
            f"{', '.join(f'{fitted_id:#04x}' for fitted_id in fitted)} 다. 없는 모터에 프레임을 "
            "보내면 아무도 ACK 하지 않아 송신 에러 카운터가 올라가고 컨트롤러가 ERROR-PASSIVE 로 "
            "떨어진다 — 달려 있는 관절들까지 같이 나빠진다."
        )
    if send_id not in ARM_JOINT_SEND_IDS:
        raise JogRefusedError(
            f"{send_id:#04x} 는 팔 관절이 아니다. 이 도구는 J1-J7 만 다룬다 — 그리퍼는 힘 제어"
            "(POS_FORCE)라 MIT 위치 지령의 대상이 아니고, URDF effort 상한 행도 없어서 중단 "
            "토크를 유도할 근거가 없다."
        )

    return JogTarget(
        side=side,
        interface=interface,
        send_id=send_id,
        motor_type=expected_type(send_id),
        effort_limit_nm=URDF_EFFORT_LIMIT_NM[send_id - FIRST_ARM_SEND_ID],
    )


def channel_refusals(
    interface: str, channels: tuple[CanChannel, ...], locks: LockManager
) -> tuple[str, ...]:
    """Every reason this channel cannot be driven right now.

    Args:
        interface: The kernel interface the target arm is on.
        channels: The CAN channels enumerated right now.
        locks: The lock manager used to probe who holds the channel.

    Returns:
        (tuple[str, ...]) One line per refusal; empty when the channel may be opened.
    """
    refusals: list[str] = []
    by_interface = {channel.interface: channel for channel in channels}
    channel = by_interface.get(interface)
    if channel is None:
        return (f"{interface} 가 지금 없다. 어댑터가 빠졌거나 다른 포트로 옮겨졌다.",)
    if not channel.is_up:
        argv = bring_up_command(interface, LINK_BITRATE_BPS, LINK_DATA_BITRATE_BPS)
        refusals.append(
            f"링크가 내려가 있다: {interface}. 이 도구는 링크를 올리지 않는다(CAP_NET_ADMIN 이 "
            f"필요하고, 몰래 권한을 올리는 도구는 감사할 수 없다). 당신 셸에서: {shlex.join(argv)}"
        )
    for state in locks.lock_state([interface]):
        if state.holder is None:
            continue
        refusals.append(
            f"{state.iface} 의 채널 잠금을 {state.holder.holder_pid} 번 프로세스가 쥐고 있다"
            f"({state.lock_path}). 소켓은 잠금을 잡은 뒤에만 열린다(01 FR-SYS-005) — 한 채널에 "
            "쓰는 쪽이 둘이면 팔은 두 곳에서 온 지령을 번갈아 받는다."
        )
    return tuple(refusals)


def request_refusals(
    target: JogTarget, delta: Deg, kp: float, kd: float, max_torque_nm: float, max_temp_c: float
) -> tuple[str, ...]:
    """Every reason the requested move is not one this runner will make.

    Args:
        target: The motor to address.
        delta: The requested relative move.
        kp: Position gain.
        kd: Velocity gain.
        max_torque_nm: The abort torque.
        max_temp_c: The abort temperature.

    Returns:
        (tuple[str, ...]) One line per refusal; empty when the move may be attempted.
    """
    refusals: list[str] = []
    if abs(delta.value) > MAX_DELTA_DEG:
        refusals.append(
            f"--delta {delta.value:+.2f}° 는 이 도구의 상한 {MAX_DELTA_DEG:.0f}° 를 넘는다. "
            "이 상한은 관절 한계 검사가 아니라 오타 방어다 — 이 도구는 관절 한계도 충돌 형상도 "
            "읽지 않는다. 더 크게 움직일 거면 여러 번 나눠서, 보면서 한다."
        )
    if not KP_MIN <= kp <= KP_MAX:
        refusals.append(
            f"kp {kp} 는 MIT 인코딩 범위 [{KP_MIN}, {KP_MAX}] 밖이다(FR-MOT-018). 인코더는 "
            "범위를 넘긴 값을 에러 없이 잘라서 내보내므로, 거부하지 않으면 조용히 다른 게인으로 "
            f"움직인다. 등록된 프로파일은 레지스트리가 가져올 때 이미 검사하므로 이 값은 "
            f"{OVERRIDE_KP_FLAG} 에서 왔다."
        )
    if not KD_MIN < kd <= KD_MAX:
        refusals.append(
            f"kd {kd} 는 (0, {KD_MAX}] 밖이다. 상한은 MIT 인코딩 범위이고(FR-MOT-018), 0 이 "
            "빠진 건 Damiao 공식 제약이다(FR-MOT-021): 위치 제어에서 kd=0 이면 모터가 진동하거나 "
            f"폭주한다. 등록된 프로파일은 이미 검사되므로 이 값은 {OVERRIDE_KD_FLAG} 에서 왔다."
        )
    if max_torque_nm > target.effort_limit_nm:
        refusals.append(
            f"--max-torque {max_torque_nm} N·m 는 이 관절의 effort 상한 "
            f"{target.effort_limit_nm} N·m 보다 높다. 상한 위의 중단선은 중단선이 아니다."
        )
    if max_temp_c > COIL_TEMP_FAULT_CAP_C:
        refusals.append(
            f"--max-temp {max_temp_c}°C 는 코일 고장 상한 {COIL_TEMP_FAULT_CAP_C}°C 보다 높다. "
            "그 위에서 멈추는 중단선은 모터가 스스로 보호에 들어간 뒤에야 걸린다."
        )
    return tuple(refusals)


# --- The move ---


@dataclass(frozen=True)
class ResolvedGains:
    """The pair this run commands at one joint, and where each half of it came from.

    Attributes:
        kp: Position gain that goes in every commanded frame.
        kd: Velocity gain that goes in every commanded frame.
        profile_name: The registered profile the pair was read from.
        overridden: The flags whose values replaced the registered ones, empty when the run is on
            the profile as registered.

    The origin travels with the numbers because the two are not interchangeable on a bench: a run
    on a registered profile is repeatable from its name alone, and a run carrying an override is
    only repeatable from the command line that produced it.
    """

    kp: float
    kd: float
    profile_name: str
    overridden: tuple[str, ...]

    @property
    def label(self) -> str:
        """How the gains are named on screen: the profile, plus any hand override on top of it."""
        origin = self.profile_name
        if self.overridden:
            origin = f"{origin} + {' '.join(self.overridden)}"
        return f"게인 {origin} kp={self.kp} kd={self.kd}"


def resolve_gains(
    profile: NamedGainProfile, send_id: int, override_kp: float | None, override_kd: float | None
) -> ResolvedGains:
    """Read one joint's gains out of a profile, then apply whatever the operator overrode.

    Args:
        profile: The registered profile named on the command line.
        send_id: The motor's CAN send id, which selects the entry — this is the whole point of a
            profile over a scalar, since `compliant` is kp 60 at J4 and kp 10 at J7.
        override_kp: A stiffness that replaces the registered one, or None.
        override_kd: A damping that replaces the registered one, or None.

    Returns:
        (ResolvedGains) What the frames carry, and what to call it.

    Raises:
        GainProfileError: When the profile has no entry for this id.
    """
    registered = profile.for_send_id(send_id)
    overridden: list[str] = []
    kp = registered.kp
    kd = registered.kd
    if override_kp is not None:
        kp = override_kp
        overridden.append(OVERRIDE_KP_FLAG)
    if override_kd is not None:
        kd = override_kd
        overridden.append(OVERRIDE_KD_FLAG)
    return ResolvedGains(kp=kp, kd=kd, profile_name=profile.name, overridden=tuple(overridden))


@dataclass(frozen=True)
class AbortLimits:
    """What stops the move, judged on every frame's answer.

    Attributes:
        max_torque_nm: Reported torque magnitude that stops the run.
        max_temp_c: Reported temperature, either channel, that stops the run.
    """

    max_torque_nm: float
    max_temp_c: float


def abort_reason(feedback: MotorFeedback | None, limits: AbortLimits) -> str | None:
    """Judge one answer and report why the move must stop, or None to continue.

    Silence is an abort like any other: an energized motor that stopped answering is a motor
    nothing is judging, and continuing to command it is commanding blind.

    Args:
        feedback: What came back, or None when nothing did.
        limits: The ceilings this run judges against.

    Returns:
        (str | None) The reason to stop, or None when this answer is clean.
    """
    if feedback is None:
        return "피드백 유실 — 통전 상태에서 응답이 끊겼다"
    if feedback.is_fault:
        return f"모터 보호 동작: {feedback.state_name}"
    if feedback.state != STATE_ENABLED:
        return f"enable 이 풀렸다 (상태 {feedback.state_name})"
    if abs(feedback.torque_nm) > limits.max_torque_nm:
        return f"토크 {feedback.torque_nm:+.2f} N·m > {limits.max_torque_nm:.2f} N·m"
    if max(feedback.temp_mos_c, feedback.temp_rotor_c) > limits.max_temp_c:
        return f"온도 {feedback.temp_mos_c}/{feedback.temp_rotor_c}°C > {limits.max_temp_c:.0f}°C"
    return None


def ramp(start: Rad, end: Rad, frames: int) -> tuple[Rad, ...]:
    """Evenly spaced targets from `start` to `end`, both ends included.

    The first element is exactly `start` and the last exactly `end`. That the first is exact is
    property 1 of this file: the leg that departs from the resting position commands the resting
    position first, so enabling and the first stiff frame ask for the same place the motor is
    already in.

    Args:
        start: Where the leg departs from.
        end: Where the leg arrives.
        frames: How many targets to emit, at least `MIN_RAMP_FRAMES`.

    Returns:
        (tuple[Rad, ...]) The targets in command order.

    Raises:
        ValueError: If `frames` is below `MIN_RAMP_FRAMES`; one frame is the jump this exists to
            forbid.
    """
    if frames < MIN_RAMP_FRAMES:
        raise ValueError(f"a ramp needs at least {MIN_RAMP_FRAMES} frames, got {frames}")
    span = end.value - start.value
    intervals = frames - 1
    return tuple(Rad(start.value + span * step / intervals) for step in range(frames))


def plan_legs(resting: Rad, delta: Rad, frames: int, returns: bool) -> tuple[tuple[Rad, ...], ...]:
    """Plan the ramps this run commands, each departing from where the previous one arrived.

    Args:
        resting: The position read before anything was energized.
        delta: The relative move.
        frames: Targets per leg.
        returns: Whether the joint comes back.

    Returns:
        (tuple[tuple[Rad, ...], ...]) One tuple of targets per leg. The first leg's first target
        is `resting`, which is what makes the first commanded position the present one.
    """
    reached = resting + delta
    legs = [ramp(resting, reached, frames)]
    if returns:
        legs.append(ramp(reached, resting, frames))
    return tuple(legs)


def wait_until_enabled(link: MotorLink, resting: Rad) -> MotorFeedback | None:
    """Poll with no-force frames until the motor reports enabled.

    A single check cannot work: the answer to a command carries the state from before that
    command was processed, so the reply to 0xFC itself always says disabled. The poll frames hold
    the resting position with kp = kd = 0, so they command nothing while the answer is awaited.

    Args:
        link: The motor's channel.
        resting: The position the poll frames name, which is where the motor already is.

    Returns:
        (MotorFeedback | None) The first answer reporting enabled, or None when the motor never
        did within `ENABLE_POLL_ATTEMPTS`.
    """
    probe = mit_frame(link.motor_type, resting, PROBE_KP, PROBE_KD)
    for _ in range(ENABLE_POLL_ATTEMPTS):
        feedback = link.exchange(probe, ENABLE_REPLY_TIMEOUT_S)
        if feedback is not None and feedback.state == STATE_ENABLED:
            return feedback
        time.sleep(ENABLE_POLL_PERIOD_S)
    return None


def _say(line: str) -> None:
    """Print one operator-facing line as it happens.

    Flushed because stdout is block-buffered whenever it is not a terminal, and a progress line
    that arrives after the joint stopped moving is a progress line nobody could act on.
    """
    print(line, flush=True)


def _progress(leg_name: str, target: Rad, feedback: MotorFeedback) -> str:
    """Render one commanded frame against what came back."""
    return (
        f"  [{leg_name}] 목표 {rad_to_deg(target).value:+7.2f}°  "
        f"실제 {rad_to_deg(feedback.position).value:+7.2f}°  "
        f"오차 {rad_to_deg(feedback.position - target).value:+6.2f}°  "
        f"τ {feedback.torque_nm:+6.2f} N·m  "
        f"{feedback.temp_mos_c}/{feedback.temp_rotor_c}°C"
    )


def run_leg(
    link: MotorLink,
    leg_name: str,
    targets: Sequence[Rad],
    kp: float,
    kd: float,
    limits: AbortLimits,
    period_s: float,
) -> str | None:
    """Command one ramp, judging every answer before the next frame goes out.

    Args:
        link: The motor's channel.
        leg_name: What this leg is called on screen.
        targets: The ramp, in command order.
        kp: Position gain.
        kd: Velocity gain.
        limits: The ceilings each answer is judged against.
        period_s: Gap between frames.

    Returns:
        (str | None) The abort reason, or None when the whole leg completed clean.
    """
    last = len(targets) - 1
    for index, target in enumerate(targets):
        feedback = link.exchange(mit_frame(link.motor_type, target, kp, kd), REPLY_TIMEOUT_S)
        reason = abort_reason(feedback, limits)
        if reason is not None:
            return reason
        if feedback is not None and (index % PROGRESS_EVERY_N_FRAMES == 0 or index == last):
            _say(_progress(leg_name, target, feedback))
        time.sleep(period_s)
    return None


def hold_at(
    link: MotorLink,
    target: Rad,
    kp: float,
    kd: float,
    limits: AbortLimits,
    frames: int,
    period_s: float,
) -> str | None:
    """Keep commanding one position for a while, still judging every answer.

    The frames have to keep going out. A held position with no traffic is not a hold: the motor's
    comm-loss timeout drops its enable, and until it does nothing is watching the temperature.

    Args:
        link: The motor's channel.
        target: The position to hold.
        kp: Position gain.
        kd: Velocity gain.
        limits: The ceilings each answer is judged against.
        frames: How many frames to hold for.
        period_s: Gap between frames.

    Returns:
        (str | None) The abort reason, or None when the hold completed clean.
    """
    return run_leg(link, HOLD_LEG_NAME, (target,) * frames, kp, kd, limits, period_s)


def open_bus(interface: str, locks: LockManager) -> NodeBus:
    """Open one channel for driving, with its lock already held.

    Args:
        interface: The kernel interface name.
        locks: The manager that must already hold this interface's lock.

    Returns:
        (NodeBus) The open socket. Opening energizes nothing; the enable frame does that.

    Raises:
        LockOrderingError: When the lock is not held (`01` FR-SYS-005).
    """
    assert_lock_held(locks, [interface])
    bus: NodeBus = can.interface.Bus(channel=interface, interface="socketcan", fd=LINK_IS_CAN_FD)
    drain(bus)
    return bus


@dataclass(frozen=True)
class JogPlan:
    """Everything the move needs once the bench has been judged.

    Attributes:
        target: The motor to address.
        delta: The relative move.
        gains: The pair every commanded frame carries, and which profile it came from.
        frames: Targets per leg.
        period_s: Gap between frames.
        hold_frames: How many frames the far end is held for; zero means no hold.
        returns: Whether the joint comes back.
        limits: The ceilings each answer is judged against.
    """

    target: JogTarget
    delta: Rad
    gains: ResolvedGains
    frames: int
    period_s: float
    hold_frames: int
    returns: bool
    limits: AbortLimits


def jog(plan: JogPlan, bus: NodeBus) -> str | None:
    """Read the resting position, energize, ramp there and back, and always disable.

    The `finally` is property 4 and covers every exit path this function has, including an
    exception raised inside a leg and the KeyboardInterrupt an operator sends when they do not
    like what they are seeing. It runs before the caller closes the socket, so the last frame the
    motor receives is always a disable.

    Args:
        plan: The judged move.
        bus: The open channel, whose lock the caller holds.

    Returns:
        (str | None) The abort reason, or None when the joint moved and came back.
    """
    link = MotorLink(bus, plan.target.send_id, plan.target.motor_type)
    disable = command_frame(DISABLE_COMMAND_CODE)
    try:
        resting_feedback = link.exchange(disable, REPLY_TIMEOUT_S)
        if resting_feedback is None:
            return (
                f"{plan.target.label} 가 응답하지 않는다. 통전 전에 "
                "./scripts/can_node_watch.sh --run 으로 노드부터 확인한다."
            )
        resting = resting_feedback.position
        _say(
            f"{plan.target.label}  현재 {rad_to_deg(resting).value:+.2f}°  "
            f"τ {resting_feedback.torque_nm:+.2f} N·m  "
            f"{resting_feedback.temp_mos_c}/{resting_feedback.temp_rotor_c}°C"
        )
        legs = plan_legs(resting, plan.delta, plan.frames, plan.returns)
        _say(
            f"목표 {rad_to_deg(resting + plan.delta).value:+.2f}°  "
            f"{plan.gains.label}  프레임 {plan.frames}개/구간  "
            f"중단 τ {plan.limits.max_torque_nm:.2f} N·m · {plan.limits.max_temp_c:.0f}°C"
        )

        link.exchange(command_frame(ENABLE_COMMAND_CODE), ENABLE_REPLY_TIMEOUT_S)
        if wait_until_enabled(link, resting) is None:
            return (
                f"enable 확인 실패: 무력 프레임 {ENABLE_POLL_ATTEMPTS}회 동안 enabled 상태를 "
                "보지 못했다"
            )

        for index, targets in enumerate(legs):
            reason = run_leg(
                link,
                LEG_NAMES[index],
                targets,
                plan.gains.kp,
                plan.gains.kd,
                plan.limits,
                plan.period_s,
            )
            if reason is not None:
                return reason
            if index == 0 and plan.hold_frames > 0:
                reason = hold_at(
                    link,
                    targets[-1],
                    plan.gains.kp,
                    plan.gains.kd,
                    plan.limits,
                    plan.hold_frames,
                    plan.period_s,
                )
                if reason is not None:
                    return reason
        return None
    finally:
        final = link.exchange(disable, REPLY_TIMEOUT_S)
        _say(
            f"disable 완료. 최종 {rad_to_deg(final.position).value:+.2f}°"
            if final is not None
            else "disable 전송 — 응답 없음"
        )


# --- Entry point ---


def build_plan(target: JogTarget, args: argparse.Namespace) -> JogPlan:
    """Turn the parsed arguments into the judged move, converting degrees to radians once.

    This is the one place this file crosses units (CTR-UNIT@v1): the CLI is degrees because that
    is what the operator reads off the arm, and everything below is radians because that is what
    the CAN frame carries (`03` §2.3). It is also where the named profile becomes two numbers, at
    the joint this run addresses and nowhere else.

    Args:
        target: The motor to address.
        args: The parsed arguments.

    Returns:
        (JogPlan) The move, ready to run.

    Raises:
        GainProfileError: When the named profile has no entry for this joint.
    """
    max_torque = args.max_torque if args.max_torque is not None else target.default_abort_torque_nm
    return JogPlan(
        target=target,
        delta=deg_to_rad(Deg(args.delta)),
        gains=resolve_gains(args.profile, target.send_id, args.override_kp, args.override_kd),
        frames=max(MIN_RAMP_FRAMES, frame_count(args.hz, args.seconds)),
        period_s=1.0 / args.hz,
        hold_frames=round(args.hz * args.hold),
        returns=not args.no_return,
        limits=AbortLimits(max_torque_nm=max_torque, max_temp_c=args.max_temp),
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser. Angles are degrees here and nowhere below."""
    parser = argparse.ArgumentParser(prog="jog_joint", description=__doc__)
    parser.add_argument("--arm", choices=SIDES, required=True, help="어느 팔인가")
    parser.add_argument(
        "--id",
        dest="send_id",
        type=can_id,
        required=True,
        help="모터 CAN 송신 id (J1-J7 = 0x01-0x07)",
    )
    parser.add_argument(
        "--delta", type=float, required=True, help="현재 위치 기준 상대 각도(도), 필수"
    )
    parser.add_argument(
        "--profile",
        type=gain_profile,
        default=resolve_gain_profile(DEFAULT_PROFILE_NAME),
        help=(
            f"게인 프로파일 이름 — 03 §2.8 정본 {', '.join(profile_names())} "
            f"(기본 {DEFAULT_PROFILE_NAME})"
        ),
    )
    parser.add_argument(
        OVERRIDE_KP_FLAG,
        type=float,
        default=None,
        help="프로파일의 이 관절 kp 를 손으로 대체한다 (탐침용, 화면에 override 로 표시된다)",
    )
    parser.add_argument(
        OVERRIDE_KD_FLAG,
        type=float,
        default=None,
        help="프로파일의 이 관절 kd 를 손으로 대체한다 (탐침용, 화면에 override 로 표시된다)",
    )
    parser.add_argument(
        "--seconds",
        type=positive_float,
        default=DEFAULT_RAMP_SECONDS,
        help="편도 램프 시간, 초 (기본 %(default)s)",
    )
    parser.add_argument(
        "--hz",
        type=positive_float,
        default=DEFAULT_RAMP_HZ,
        help="프레임 주기, Hz (기본 %(default)s)",
    )
    parser.add_argument(
        "--hold",
        type=non_negative_float,
        default=DEFAULT_HOLD_SECONDS,
        help="목표 도달 후 유지 시간, 초 (기본 %(default)s)",
    )
    parser.add_argument(
        "--max-torque",
        type=float,
        default=None,
        help=f"중단 토크, N·m (기본 = 그 관절 effort 상한 × {ABORT_TORQUE_FRACTION_OF_EFFORT})",
    )
    parser.add_argument(
        "--max-temp",
        type=float,
        default=DEFAULT_MAX_MOTOR_TEMP_C,
        help="중단 온도, °C (기본 %(default)s)",
    )
    parser.add_argument("--no-return", action="store_true", help="원위치로 되돌리지 않는다")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Judge the bench, then move one joint and bring it back.

    Returns:
        (int) `EXIT_OK` when the joint moved and came back, `EXIT_REFUSED` when nothing was
        opened or the motor never answered, `EXIT_ABORTED` when the move stopped early.
    """
    args = build_parser().parse_args(argv)
    channels = tuple(list_can_channels())
    locks = LockManager()
    try:
        target = resolve_target(args.arm, args.send_id, default_config_directory(), channels)
    except JogRefusedError as unresolved:
        _say(f"거부: {unresolved}")
        return EXIT_REFUSED

    plan = build_plan(target, args)
    refusals = channel_refusals(target.interface, channels, locks) + request_refusals(
        target,
        Deg(args.delta),
        plan.gains.kp,
        plan.gains.kd,
        plan.limits.max_torque_nm,
        plan.limits.max_temp_c,
    )
    if refusals:
        for refusal in refusals:
            _say(f"거부: {refusal}")
        return EXIT_REFUSED

    acquired = locks.acquire_all([target.interface])
    if not acquired.ok:
        _say(
            f"거부: {acquired.blocked_iface} 의 채널 잠금을 다른 프로세스가 쥐고 있다 "
            f"({acquired.holder})"
        )
        return EXIT_REFUSED

    bus = open_bus(target.interface, locks)
    try:
        reason = jog(plan, bus)
    finally:
        bus.shutdown()
        locks.release_all()

    if reason is not None:
        _say(f"중단: {reason}")
        return EXIT_ABORTED
    _say("완료 — 관절이 움직였고 제자리로 돌아왔다. 모터는 disable 상태다.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
