"""Does every fitted motor keep answering, over time and across postures — with torque OFF.

A snapshot cannot answer that. On the sibling rig driving this same hardware a non-responding node
MOVED between joints inside one session — left J6, then right J6, then recovered, then right J1
(`bh_remy_openArm/config/calibration/remy_left.yaml:65-67`). Every single read in that session
would have called the rig healthy or called one fixed joint dead, and both answers were wrong.

The question is worth asking before torque and nowhere else. A node that drops out *while*
energized cannot be handled: a stop removes force, and a shoulder holding 11.67 N·m does not halt
when the force goes — the arm falls (`03` FR-MOT-044, `12` FR-SAF-042). So the only window in
which a flaky harness can still be caught is the window before 0xFC, which is this one.

**Torque-free, and that property is what the whole tool is built around.** It sends one frame,
`FF FF FF FF FF FF FF FD` — Disable, `03` §2.5 — and the motor answers with its state nibble,
position, velocity, torque and both temperatures (`03` §2.7). 0xFC never leaves this file. Every
other reader here goes through `DamiaoMotorsBus.connect()`, whose handshake enables every
registered motor, which is why those tools refuse until the operator has the arm in their hands.
This one needs no hand on the arm, and demanding one would be theatre.

The residual risk runs the other way: 0xFD onto a motor that is *already* energized drops it, and
a brakeless arm falls. Two things close it and neither is a guess. A sanctioned energized session
holds that channel's lock (`01` FR-SYS-005), and this tool refuses while any lock is held. A motor
left enabled by a process that died drops enable by itself on the comm-loss timeout (`16` M-4,
`backend/can/rid/registers.py`).

**Silence and a fault are different diagnoses and are reported apart.** A DAMIAO that is
overheating or overloaded ANSWERS, carrying a state nibble of 0x8 or above (`03` FR-MOT-041 —
`openarm_can` and LeRobot both drop `data[0]`, so this decode is ours to do). No answer at all
means the MCU is not running or is not listening on that id; no protection behaviour produces
that symptom. Reading the nibble as an error field is the other half of the mistake: 0x0 disabled
and 0x1 enabled are both normal, and a tool that flags them false-alarms on every healthy motor.

**Which motors are polled is read, never assumed.** `ARM_SEND_IDS` is the registration of a fully
populated arm; the set on the bus is decided by the fitted end effector, and addressing a motor
that is not there walks the controller to ERROR-PASSIVE and degrades the seven joints that are
present. The pollable set comes from `EndEffectorProfile.motor_send_ids`.

**The timetable is printed first and the watch is detached.** A terminal shows a command's output
only once the command has ended, so "move the arm now" printed by a running command arrives after
the instant it names — three E-Stop measurements were lost that way on this bench
(`docs/guide/05` §「이 문서 전체를 지배하는 규칙 하나」). `--run` prints absolute wall-clock
instants and forks; `--status` carries the verdict.

The posture at each transition is recorded always, not behind a flag. Harness faults depend on
bending, so *where the arm was* when a node dropped is the evidence that separates a harness from
a dead node — a run that collected it and did not show it would be a run to repeat.

Exit codes, which are the verdict:

    0  every fitted motor answered every attempt, with no fault nibble
    1  refused, or a node was silent, intermittent or faulted — do not put torque on
    2  --status only: the watch is still running
    3  --status only: this capture tree holds no watch at all

Entry point is `scripts/can_node_watch.sh`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import can

from backend.can.lock import LockManager, assert_lock_held
from backend.can.rid.layout import expected_type
from backend.can.rid.motor_limits import MOTOR_LIMIT_PARAMS, MotorType
from backend.config.store import default_config_directory
from backend.endeffector import (
    SIDE_LEFT,
    SIDE_RIGHT,
    SIDES,
    RigEndEffectors,
    default_rig,
    load_rig,
    rig_path,
)
from contracts.units import Rad, rad_to_deg
from ops.hw.canbind import (
    ArmRole,
    BindingError,
    CanChannel,
    binding_path,
    bring_up_command,
    check_binding,
    list_can_channels,
    load_binding,
)

EXIT_OK = 0
EXIT_REFUSED = 1

# The watch is scheduled and its verdict is not in yet. Distinct from EXIT_REFUSED because nothing
# has gone wrong: the answer is "wait", not "fix something".
EXIT_RUNNING = 2

# This capture tree holds no watch at all. Distinct from EXIT_RUNNING for the reason it is in
# `canbind_session`: "not finished" and "never started" want opposite responses.
EXIT_NO_SESSION = 3


# --- The Damiao wire protocol this tool speaks directly (`03` §2.5, §2.7) ---
#
# Directly, rather than through `DamiaoMotorsBus`, for one reason: that bus energizes the arm on
# connect. Nothing else in this file needs the vendor stack, and the two frames below are the
# whole protocol surface it uses.

# Command payload (`03` §2.5): seven pad bytes and the command code.
COMMAND_FRAME_LENGTH = 8
COMMAND_PAD_BYTE = 0xFF

# Disable (`03` §2.5, FR-MOT-022). The one code this tool is allowed to send. The motor answers a
# full feedback frame to it, which is what makes a torque-free read possible at all.
DISABLE_COMMAND_CODE = 0xFD

# Feedback id = send id + this (`03` §2.1: send `0x01–0x08`, recv `0x11–0x18`). Named because a
# bare `+ 0x10` at a call site reads as arithmetic rather than as the arm's addressing rule.
RECV_ID_OFFSET = 0x10

# Feedback frame (`03` §2.7): D0 = `ID | (ERR << 4)`, D1-D2 POS, D3-D4 VEL, D4-D5 T, D6 T_MOS,
# D7 T_Rotor.
FEEDBACK_FRAME_LENGTH = 8
POSITION_BITS = 16
VELOCITY_BITS = 12
TORQUE_BITS = 12
BYTE_BITS = 8
NIBBLE_BITS = 4
LOW_NIBBLE_MASK = 0x0F

# The D0 high nibble is a STATE code, not an error code (`03` §2.7, FR-MOT-041). Both values below
# are normal operation; a tool that treats the field as "non-zero means broken" reports a fault on
# every enabled motor on the bus.
STATE_DISABLED = 0x0
STATE_ENABLED = 0x1

# From here up the motor is reporting a protection trip. It is still answering — that is the whole
# distinction this tool draws between a fault and silence.
LOWEST_FAULT_STATE = 0x8

STATE_NAMES: dict[int, str] = {
    STATE_DISABLED: "disabled",
    STATE_ENABLED: "enabled",
    0x8: "over-voltage",
    0x9: "under-voltage",
    0xA: "over-current",
    0xB: "mos-over-temperature",
    0xC: "coil-over-temperature",
    0xD: "communication-lost",
    0xE: "overloaded",
}

# The link runs CAN-FD on this rig — `bring_up_command` brings every channel up with `fd on`. The
# socket is opened FD-capable to match it; the frames this tool sends are classic 8-byte frames,
# which is what the vendor command format is.
LINK_IS_CAN_FD = True

# The link bitrates, for the bring-up command printed when a channel is down. The tool never
# brings a link up itself: that needs CAP_NET_ADMIN, and a tool that silently escalates is a tool
# nobody can audit.
LINK_BITRATE_BPS = 1_000_000
LINK_DATA_BITRATE_BPS = 5_000_000


# --- Watch timing ---

# How long one node's reply is waited for. The bench round trip is sub-millisecond; what this
# watch needs is repetitions, not a generous window, and a long timeout on a dead node is time
# taken away from every live one.
REPLY_TIMEOUT_S = 0.005

# Gap between rounds. Fast enough that a drop lasting a tenth of a second is seen, slow enough
# that the watch is not itself the dominant traffic on a bus somebody may be inspecting.
ROUND_PERIOD_S = 0.02

# Receive with no blocking at all, for draining frames that arrived before this poll.
NO_WAIT_S = 0.0

# Drain cap. Unbounded, a channel carrying traffic from somewhere else would hold the drain loop
# forever and no frame would ever be sent.
MAX_DRAIN_FRAMES = 64

# How long the watch runs by default. Long enough that the operator can walk the arm through its
# range by hand rather than holding one pose.
DEFAULT_WATCH_SECONDS = 120.0

# Gap between the timetable reaching the operator and the first frame. Nothing is energized here,
# so this margin only has to cover reading the timetable and getting to the arm.
LEAD_SECONDS = 20.0

# Transitions kept per node. A node that flaps every round would otherwise write a record
# proportional to the run length; what is dropped is counted and reported, never silently cut.
MAX_RECORDED_TRANSITIONS = 200

WALL_CLOCK_FORMAT = "%H:%M:%S"

DEFAULT_CAPTURES_DIRNAME = "openarm_captures"
SESSION_DIRNAME = "can_node_watch"
STATE_FILENAME = "state.json"
LOG_FILENAME = "watch.log"

FIELD_STATE = "state"
FIELD_REASON = "reason"
FIELD_SECONDS = "seconds"
FIELD_ELAPSED_SECONDS = "elapsed_seconds"
FIELD_VERDICT_AT = "verdict_at"
FIELD_FINISHED_AT = "finished_at"
FIELD_NODES = "nodes"
FIELD_SIDE = "side"
FIELD_INTERFACE = "interface"
FIELD_SEND_ID = "send_id"
FIELD_MOTOR_TYPE = "motor_type"
FIELD_ATTEMPTS = "attempts"
FIELD_REPLIES = "replies"
FIELD_TRANSITIONS = "transitions"
FIELD_TRANSITION_COUNT = "transition_count"
FIELD_FAULT_COUNTS = "fault_counts"
FIELD_AT_SECONDS = "at_seconds"
FIELD_KIND = "kind"
FIELD_POSTURE_DEG = "posture_deg"

# What a watch can be. `FINISHED` is the only one that carries per-node numbers; the other two are
# kept apart because they ask the operator for different things — wait, or fix the rig.
WATCH_SCHEDULED = "scheduled"
WATCH_FINISHED = "finished"
WATCH_REFUSED = "refused"

TRANSITION_DROP = "drop"
TRANSITION_BACK = "back"

# The follower role each declared side occupies in the persisted binding. Same pairing
# `scripts.canbind_session` writes and `scripts.rig_session` reads; a test pins all three equal,
# because a disagreement here watches the left arm and reports it under the right arm's name.
ROLE_BY_SIDE: dict[str, ArmRole] = {
    SIDE_LEFT: ArmRole.FOLLOWER_LEFT,
    SIDE_RIGHT: ArmRole.FOLLOWER_RIGHT,
}

# Operator-facing name per side, matching the runners this sits beside.
LABEL_BY_SIDE = {SIDE_LEFT: "왼팔", SIDE_RIGHT: "오른팔"}


class WatchRefusedError(Exception):
    """Raised when the watch cannot be set up from what is on the bench right now."""


class FeedbackFrameError(Exception):
    """Raised when a frame carrying a motor's feedback id is not a feedback frame."""


class NodeBus(Protocol):
    """The three bus operations one watch needs, and nothing wider.

    Declared as exactly what this tool calls rather than as the vendor bus: `python-can`'s
    `BusABC` satisfies it as-is, and so does a double that binds no socket, which is how every
    test here drives the whole watch on a host with no adapter.
    """

    def send(self, msg: can.Message) -> None:
        """Put one frame on the wire."""
        ...

    def recv(self, timeout: float) -> can.Message | None:
        """Return the next frame, or None when none arrived within the timeout."""
        ...

    def shutdown(self) -> None:
        """Close the socket."""
        ...


# --- Frames ---


def command_frame(code: int) -> bytes:
    """Build a Damiao simple-command payload (`03` §2.5).

    Args:
        code: The command byte. This module only ever passes `DISABLE_COMMAND_CODE`.

    Returns:
        (bytes) Seven pad bytes followed by the command code.
    """
    return bytes([COMMAND_PAD_BYTE] * (COMMAND_FRAME_LENGTH - 1) + [code])


def feedback_id(send_id: int) -> int:
    """Return the CAN id a motor answers on for a given send id."""
    return send_id + RECV_ID_OFFSET


def disable_message(send_id: int) -> can.Message:
    """Build the one message this tool transmits: Disable, to one motor.

    Args:
        send_id: The motor's CAN send id.

    Returns:
        (can.Message) A classic 8-byte frame. Classic rather than FD because that is the format
        the vendor command frame is defined in, on a link that is FD-capable either way.
    """
    return can.Message(
        arbitration_id=send_id,
        data=command_frame(DISABLE_COMMAND_CODE),
        is_extended_id=False,
        is_fd=False,
    )


def _from_uint(raw: int, low: float, high: float, bits: int) -> float:
    """Undo the Damiao linear packing (`03` §2.3 `double_to_uint`).

    Args:
        raw: The packed integer.
        low: Bottom of the encoded range.
        high: Top of the encoded range.
        bits: Field width.

    Returns:
        (float) The physical value.
    """
    return raw / ((1 << bits) - 1) * (high - low) + low


@dataclass(frozen=True)
class MotorFeedback:
    """One motor's answer to one frame, decoded whole (`03` §2.7).

    Every field the frame carries is decoded, including the ones this tool does not judge. A
    partial decode is how a reader ends up asserting something about a field it never read.

    Attributes:
        state: The D0 high nibble. A STATE code, not an error code — see `STATE_NAMES`.
        motor_id: The D0 low nibble, the motor's own id as it reports it.
        position: Joint angle, radians.
        velocity: Joint velocity, radians per second.
        torque_nm: Reported torque, newton-metres.
        temp_mos_c: Driver MOSFET temperature, whole degrees Celsius.
        temp_rotor_c: Coil temperature, whole degrees Celsius.
    """

    state: int
    motor_id: int
    position: Rad
    velocity: float
    torque_nm: float
    temp_mos_c: int
    temp_rotor_c: int

    @property
    def is_fault(self) -> bool:
        """Whether the motor is reporting a protection trip rather than normal operation."""
        return self.state >= LOWEST_FAULT_STATE

    @property
    def state_name(self) -> str:
        """The state nibble as a name, or its hex value when the vendor table does not list it."""
        return STATE_NAMES.get(self.state, f"0x{self.state:X}")


def decode_feedback(data: bytes, motor_type: MotorType) -> MotorFeedback:
    """Decode a feedback frame under the scaling registered for that motor type.

    The scaling is motor-dependent (`03` §2.3): the same sixteen bits mean different angles on a
    DM8009 and a DM4310, so the type is a parameter rather than a default.

    Args:
        data: The frame payload.
        motor_type: The type registered at this CAN id (`backend.can.rid.layout`).

    Returns:
        (MotorFeedback) Every field the frame carries.

    Raises:
        FeedbackFrameError: When the payload is shorter than a feedback frame.
    """
    if len(data) < FEEDBACK_FRAME_LENGTH:
        raise FeedbackFrameError(
            f"feedback frame is {len(data)} bytes, needs {FEEDBACK_FRAME_LENGTH}"
        )
    limit = MOTOR_LIMIT_PARAMS[motor_type]
    return MotorFeedback(
        state=data[0] >> NIBBLE_BITS,
        motor_id=data[0] & LOW_NIBBLE_MASK,
        position=Rad(
            _from_uint((data[1] << BYTE_BITS) | data[2], -limit.p_max, limit.p_max, POSITION_BITS)
        ),
        velocity=_from_uint(
            (data[3] << NIBBLE_BITS) | (data[4] >> NIBBLE_BITS),
            -limit.v_max,
            limit.v_max,
            VELOCITY_BITS,
        ),
        torque_nm=_from_uint(
            ((data[4] & LOW_NIBBLE_MASK) << BYTE_BITS) | data[5],
            -limit.t_max,
            limit.t_max,
            TORQUE_BITS,
        ),
        temp_mos_c=data[6],
        temp_rotor_c=data[7],
    )


# --- What is on the bench: which channel, and which motors on it ---


@dataclass(frozen=True)
class ArmTarget:
    """One arm to watch.

    Attributes:
        side: The declared arm side.
        interface: The kernel interface its channel is on right now, resolved from the persisted
            binding — never taken as an argument and never derived from the interface name.
        send_ids: The motors fitted to this arm. Nothing outside this set is ever addressed.
    """

    side: str
    interface: str
    send_ids: tuple[int, ...]


def end_effector_rig(config_directory: Path) -> RigEndEffectors:
    """Return what each arm carries, from the operator's record or the no-gripper default.

    The fallback asymmetry is deliberate and is the same one `torque_session` applies: defaulting
    to a gripper on a rig without one makes every round address an id nobody answers on, which
    walks the controller to ERROR-PASSIVE and degrades the seven joints that are present.

    Args:
        config_directory: Where the end-effector record lives.

    Returns:
        (RigEndEffectors) What each arm carries.
    """
    record = rig_path(config_directory)
    return load_rig(record) if record.is_file() else default_rig()


def arm_targets(config_directory: Path, channels: tuple[CanChannel, ...]) -> tuple[ArmTarget, ...]:
    """Resolve both arms to the channel they are on and the motors fitted to them.

    Args:
        config_directory: Where the binding and end-effector records live.
        channels: The CAN channels enumerated right now.

    Returns:
        (tuple[ArmTarget, ...]) One target per declared side, in the frozen arm order.

    Raises:
        WatchRefusedError: When the binding cannot be read, or a follower role's channel is not
            present. Both are refusals rather than a fallback to "the first CAN interface": the
            arms are indistinguishable on the bus (`03` §2.1), so a fallback is indistinguishable
            from the right answer until the report names the wrong arm.
    """
    try:
        binding = load_binding(binding_path(config_directory))
        rig = end_effector_rig(config_directory)
    except (BindingError, OSError, ValueError) as refusal:
        raise WatchRefusedError(
            f"벤치 기록을 읽을 수 없다: {refusal}. 어느 팔이 어느 채널인지, 어느 모터가 달려 "
            "있는지는 버스에서 알아낼 수 없다 — 되돌아갈 기본값이 없다."
        ) from refusal
    check = check_binding(binding, channels)
    targets: list[ArmTarget] = []
    for side in SIDES:
        role = ROLE_BY_SIDE[side]
        interface = check.resolved.get(role)
        if interface is None:
            raise WatchRefusedError(
                f"{role.value} 의 채널이 지금 없다. 어댑터가 다른 포트로 옮겨졌거나 다른 것이 "
                "꽂혀 있다. ./scripts/canbind_session.sh 로 다시 식별한다 — 인터페이스 이름으로 "
                "짐작하는 것이 바인딩 기록이 막으려는 바로 그 일이다."
            )
        targets.append(
            ArmTarget(
                side=side,
                interface=interface,
                send_ids=rig.for_side(side).motor_send_ids,
            )
        )
    return tuple(targets)


# --- Admission: everything that must hold before a socket opens ---


@dataclass(frozen=True)
class Admission:
    """What `--run` found before anything opened.

    Attributes:
        refusals: One line per reason this watch cannot start. Empty means it can.
        targets: The arms that would be watched, empty when they could not be resolved.
    """

    refusals: tuple[str, ...]
    targets: tuple[ArmTarget, ...]

    @property
    def ok(self) -> bool:
        """Whether the watch may be scheduled."""
        return not self.refusals

    def render(self) -> str:
        """Render the arms resolved and every refusal against them."""
        lines = [
            "이 도구는 0xFD(Disable)만 보낸다 — 토크를 인가하지 않으므로 팔을 잡고 있지 "
            "않아도 된다."
        ]
        lines.extend(
            f"  {LABEL_BY_SIDE[target.side]} ({target.side})  {target.interface}  "
            f"모터 {', '.join(f'{send_id:#04x}' for send_id in target.send_ids)}"
            for target in self.targets
        )
        if self.ok:
            lines.append("  거부 없음")
        lines.extend(f"  거부: {refusal}" for refusal in self.refusals)
        return "\n".join(lines)


def rig_refusals(
    targets: tuple[ArmTarget, ...], channels: tuple[CanChannel, ...], locks: LockManager
) -> tuple[str, ...]:
    """Every reason the resolved channels cannot be read right now.

    Args:
        targets: The arms to be watched.
        channels: The CAN channels enumerated right now.
        locks: The lock manager used to probe who holds each channel.

    Returns:
        (tuple[str, ...]) One line per refusal; empty when the watch may open the channels.
    """
    refusals: list[str] = []
    by_interface = {channel.interface: channel for channel in channels}
    interfaces = [target.interface for target in targets]
    down = [name for name in interfaces if not by_interface[name].is_up]
    if down:
        argv = bring_up_command(down[0], LINK_BITRATE_BPS, LINK_DATA_BITRATE_BPS)
        refusals.append(
            f"링크가 내려가 있다: {', '.join(down)}. 이 도구는 링크를 올리지 않는다"
            f"(CAP_NET_ADMIN 이 필요하고, 몰래 권한을 올리는 도구는 감사할 수 없다). "
            f"당신 셸에서 채널마다: {' '.join(argv)}"
        )
    for state in locks.lock_state(interfaces):
        if state.holder is None:
            continue
        refusals.append(
            f"{state.iface} 의 채널 잠금을 {state.holder.holder_pid} 번 프로세스가 쥐고 있다"
            f"({state.lock_path}). 소켓은 잠금을 잡은 뒤에만 열린다(01 FR-SYS-005) — 한 채널에 "
            "읽는 쪽이 둘이면 한쪽이 다른 쪽의 응답을 집어가고 그 노드는 빠진 것으로 찍힌다. "
            "잠금을 쥔 쪽이 통전 세션이라면 0xFD 는 그 팔을 떨어뜨린다."
        )
    return tuple(refusals)


def admit(
    channels: tuple[CanChannel, ...], locks: LockManager, config_directory: Path
) -> Admission:
    """Judge everything that must hold before a socket opens.

    The bench record comes first because it decides *which* channels the rest is judged against;
    a link or lock verdict over channels this watch would never open answers a question nobody
    asked.

    Args:
        channels: The CAN channels this host exposes.
        locks: The lock manager used to probe who holds each channel.
        config_directory: Where the binding and end-effector records live.

    Returns:
        (Admission) The arms resolved and every refusal against them.
    """
    try:
        targets = arm_targets(config_directory, channels)
    except WatchRefusedError as refusal:
        return Admission(refusals=(str(refusal),), targets=())
    return Admission(refusals=rig_refusals(targets, channels, locks), targets=targets)


# --- The timetable, which reaches the operator before anything opens ---


def _wall_clock(epoch: float) -> str:
    """Render an epoch as the operator's local wall-clock time."""
    return datetime.fromtimestamp(epoch).strftime(WALL_CLOCK_FORMAT)


def render_timetable(start_epoch: float, seconds: float) -> str:
    """Render the watch as absolute wall-clock instants the operator can act on.

    Relative time is useless to somebody standing at the rig — "for about two minutes" means
    nothing when the instant it counts from is not on the screen — so every instant here is the
    time on the wall.

    Args:
        start_epoch: When the first frame goes out.
        seconds: How long the watch runs.

    Returns:
        (str) The timetable.
    """
    end_epoch = start_epoch + seconds
    return "\n".join(
        [
            f"지금 {_wall_clock(time.time())} — 아래 시각은 전부 벽시계다.",
            "",
            f"{_wall_clock(start_epoch)}  감시 시작 — 0xFD(Disable)만 나간다. 토크는 "
            "인가되지 않고, 팔은 손으로 밀면 밀린다.",
            f"{_wall_clock(start_epoch)} ~ {_wall_clock(end_epoch)}",
            "           ▶ 두 팔을 손으로 천천히, 계속 움직인다. 어깨·팔꿈치·손목 순으로 "
            "굽힘을 바꾼다.",
            "           ▶ 한 자세로 두면 안 된다. 하네스 접촉 결함은 굽힘에 의존하므로 "
            "가만히 둔 자세에서는 나오지 않는다.",
            f"{_wall_clock(end_epoch)}  감시 끝 · 판정",
            "",
            "판정 기준: 장착된 모터가 매 라운드 전부 응답하고 상태 니블이 정상(0x0/0x1)일 "
            "때만 0이 나온다. 응답률 99%는 통과가 아니라 간헐 고장이다.",
        ]
    )


# --- Accumulating what the bus answered ---


@dataclass(frozen=True)
class Transition:
    """One moment a node changed between answering and not.

    Attributes:
        at_seconds: Seconds into the watch, stamped to the round — which is the resolution the
            watch has, since a round is one pass over every fitted motor.
        kind: `TRANSITION_DROP` or `TRANSITION_BACK`.
        posture: The arm's last known angle per motor at that moment, radians. This is what
            separates a harness fault from a dead node: harness contact depends on bending, so
            drops that cluster at one posture are cable, and drops with no posture pattern are
            the node itself.
    """

    at_seconds: float
    kind: str
    posture: dict[int, Rad]


class NodeWatch:
    """One motor's answering history over a watch.

    Ownership: holds only its own counters. It knows whether *it* changed state; it does not know
    where the arm was, so the posture on a transition is supplied by the arm that owns it.
    """

    def __init__(self, side: str, interface: str, send_id: int, motor_type: MotorType) -> None:
        """Start an empty history for one motor.

        Args:
            side: The arm this motor is on.
            interface: The channel it answers on.
            send_id: Its CAN send id.
            motor_type: The type registered at that id, which fixes the feedback scaling.
        """
        self.side = side
        self.interface = interface
        self.send_id = send_id
        self.motor_type = motor_type
        self.attempts = 0
        self.replies = 0
        self.transition_count = 0
        self.transitions: list[Transition] = []
        self.fault_counts: dict[int, int] = {}
        self.last_position: Rad | None = None
        self._answering: bool | None = None

    def observe(self, feedback: MotorFeedback | None) -> str | None:
        """Record one attempt and report whether it changed this node's answering state.

        Args:
            feedback: What came back, or None when nothing did.

        Returns:
            (str | None) `TRANSITION_DROP` or `TRANSITION_BACK` when the state changed, else None.
            The first attempt establishes the state and is never a transition — there is nothing
            for it to have changed from.
        """
        self.attempts += 1
        answered = feedback is not None
        if feedback is not None:
            self.replies += 1
            self.last_position = feedback.position
            if feedback.is_fault:
                self.fault_counts[feedback.state] = self.fault_counts.get(feedback.state, 0) + 1
        if self._answering is None:
            self._answering = answered
            return None
        if answered == self._answering:
            return None
        self._answering = answered
        return TRANSITION_BACK if answered else TRANSITION_DROP

    def record_transition(self, at_seconds: float, kind: str, posture: dict[int, Rad]) -> None:
        """Store one transition, counting it even past the record cap.

        Args:
            at_seconds: Seconds into the watch.
            kind: `TRANSITION_DROP` or `TRANSITION_BACK`.
            posture: The arm's last known angles.
        """
        self.transition_count += 1
        if len(self.transitions) < MAX_RECORDED_TRANSITIONS:
            self.transitions.append(Transition(at_seconds=at_seconds, kind=kind, posture=posture))


class ArmWatch:
    """Every fitted motor on one arm, and what each of them answered.

    Ownership: owns its nodes' histories and is the only thing that knows the arm's pose, so it is
    where a node's transition gets its posture attached.
    """

    def __init__(self, target: ArmTarget) -> None:
        """Start an empty history for every motor fitted to one arm.

        Args:
            target: The arm, its channel and its fitted motors.
        """
        self.target = target
        self.nodes = {
            send_id: NodeWatch(
                side=target.side,
                interface=target.interface,
                send_id=send_id,
                motor_type=expected_type(send_id),
            )
            for send_id in target.send_ids
        }

    def posture(self) -> dict[int, Rad]:
        """The arm's last known angle per motor, skipping motors that have never answered."""
        return {
            send_id: node.last_position
            for send_id, node in self.nodes.items()
            if node.last_position is not None
        }

    def observe(self, send_id: int, at_seconds: float, feedback: MotorFeedback | None) -> None:
        """Record one motor's attempt, attaching the arm's pose to any transition it caused.

        Args:
            send_id: The motor polled.
            at_seconds: Seconds into the watch.
            feedback: What came back, or None when nothing did.
        """
        node = self.nodes[send_id]
        kind = node.observe(feedback)
        if kind is not None:
            node.record_transition(at_seconds, kind, self.posture())


# --- Polling ---


class NodeReader:
    """Sends the disable frame to one channel's motors and collects what answers.

    Ownership: borrows the bus and closes nothing; the watch that opened it closes it.

    Each poll drains first. Without that, a reply that arrived after its own poll timed out would
    be counted as the answer to the *next* poll of the same motor, which turns a node that is
    consistently one round late into a node that looks healthy.
    """

    def __init__(self, bus: NodeBus, reply_timeout_s: float) -> None:
        """Bind the reader to one open channel.

        Args:
            bus: The open channel.
            reply_timeout_s: How long one motor's reply is waited for.
        """
        self._bus = bus
        self._reply_timeout_s = reply_timeout_s

    def poll(self, send_id: int, motor_type: MotorType) -> MotorFeedback | None:
        """Send one disable frame and return what that motor answered.

        Args:
            send_id: The motor's CAN send id.
            motor_type: The type registered at that id, which fixes the feedback scaling.

        Returns:
            (MotorFeedback | None) The decoded answer, or None when the motor said nothing within
            the reply window. Frames from other motors are discarded rather than counted: an
            answer is only an answer when it carries this motor's feedback id.
        """
        drain(self._bus)
        self._bus.send(disable_message(send_id))
        wanted = feedback_id(send_id)
        deadline = time.perf_counter() + self._reply_timeout_s
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return None
            message = self._bus.recv(timeout=remaining)
            if message is None:
                return None
            if message.arbitration_id == wanted and len(message.data) >= FEEDBACK_FRAME_LENGTH:
                return decode_feedback(bytes(message.data), motor_type)


def drain(bus: NodeBus) -> None:
    """Discard frames already queued, so a reply accepted afterwards was produced afterwards.

    Args:
        bus: The channel to empty. The cap matters: on a channel carrying traffic from somewhere
            else an unbounded drain never returns, and nothing is ever sent.
    """
    for _ in range(MAX_DRAIN_FRAMES):
        if bus.recv(timeout=NO_WAIT_S) is None:
            return


@dataclass(frozen=True)
class ArmChannel:
    """One arm's watch bound to the reader that feeds it.

    Attributes:
        watch: The arm's accumulating history.
        reader: The reader over that arm's open channel.
    """

    watch: ArmWatch
    reader: NodeReader


def poll_round(channels: Sequence[ArmChannel], at_seconds: float) -> None:
    """Poll every fitted motor on every arm once.

    Args:
        channels: The arms and their readers.
        at_seconds: Seconds into the watch, stamped onto anything that changed this round.
    """
    for channel in channels:
        for send_id in channel.watch.target.send_ids:
            node = channel.watch.nodes[send_id]
            channel.watch.observe(
                send_id, at_seconds, channel.reader.poll(send_id, node.motor_type)
            )


def run_watch(channels: Sequence[ArmChannel], seconds: float, period_s: float) -> float:
    """Poll every fitted motor repeatedly until the watch window closes.

    Args:
        channels: The arms and their readers.
        seconds: How long to run.
        period_s: Gap between rounds.

    Returns:
        (float) How long the watch actually ran, seconds.
    """
    started = time.perf_counter()
    deadline = started + seconds
    while time.perf_counter() < deadline:
        poll_round(channels, time.perf_counter() - started)
        time.sleep(period_s)
    return time.perf_counter() - started


# --- Opening and closing the channels ---


def open_bus(interface: str, locks: LockManager) -> NodeBus:
    """Open one channel for reading, with its lock already held.

    Args:
        interface: The kernel interface name.
        locks: The manager that must already hold this interface's lock.

    Returns:
        (NodeBus) The open socket. Nothing is energized by opening it — unlike the vendor bus,
        this open is a socket and nothing else.

    Raises:
        LockOrderingError: When the lock is not held (`01` FR-SYS-005).
    """
    assert_lock_held(locks, [interface])
    bus: NodeBus = can.interface.Bus(channel=interface, interface="socketcan", fd=LINK_IS_CAN_FD)
    drain(bus)
    return bus


def close_buses(buses: Sequence[NodeBus]) -> None:
    """Close every open channel.

    No torque is dropped on the way out because none was ever applied: the watch's only frame is
    already the disable frame.

    Args:
        buses: The channels this watch opened.
    """
    for bus in buses:
        bus.shutdown()


# --- The record ---


def session_dir(captures_root: Path) -> Path:
    """The directory this watch's state and log live in."""
    return captures_root / SESSION_DIRNAME


def state_path(captures_root: Path) -> Path:
    """The file the watch's verdict is recorded in."""
    return session_dir(captures_root) / STATE_FILENAME


def _write_state(path: Path, document: dict[str, Any]) -> None:
    """Replace the state file in one step, so `--status` never reads half a watch.

    `--status` can run at any instant, including while the watch is recording. A rename is atomic
    where a truncate-and-rewrite is not, and a torn file reads as a parse error at exactly the
    moment the operator is asking for the verdict.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle_fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        temp_path.replace(path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def record_watch(captures_root: Path, document: dict[str, Any]) -> None:
    """Replace the recorded watch with this one. A watch is the whole measurement, not a half."""
    _write_state(state_path(captures_root), document)


def read_watch(captures_root: Path) -> dict[str, Any] | None:
    """Return the recorded watch, or None when this tree holds none."""
    path = state_path(captures_root)
    if not path.exists():
        return None
    loaded: Any = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else None


def _posture_document(posture: Mapping[int, Rad]) -> dict[str, float]:
    """Render a pose for the record in degrees, at the one place this crosses units.

    The bus speaks radians (`03` §2.3) and this is the only conversion in the file (CTR-UNIT@v1:
    one named crossing per boundary, never an arithmetic expression at a call site). Degrees
    because the reader is a person standing at the arm comparing what they see to what is printed.
    """
    return {str(send_id): rad_to_deg(angle).value for send_id, angle in posture.items()}


def node_document(node: NodeWatch) -> dict[str, Any]:
    """Turn one node's history into its record entry."""
    return {
        FIELD_SIDE: node.side,
        FIELD_INTERFACE: node.interface,
        FIELD_SEND_ID: node.send_id,
        FIELD_MOTOR_TYPE: node.motor_type.value,
        FIELD_ATTEMPTS: node.attempts,
        FIELD_REPLIES: node.replies,
        FIELD_TRANSITION_COUNT: node.transition_count,
        FIELD_TRANSITIONS: [
            {
                FIELD_AT_SECONDS: transition.at_seconds,
                FIELD_KIND: transition.kind,
                FIELD_POSTURE_DEG: _posture_document(transition.posture),
            }
            for transition in node.transitions
        ],
        FIELD_FAULT_COUNTS: {str(state): count for state, count in node.fault_counts.items()},
    }


def finished_document(channels: Sequence[ArmChannel], elapsed_s: float) -> dict[str, Any]:
    """Turn a completed watch into the record `--status` reads."""
    return {
        FIELD_STATE: WATCH_FINISHED,
        FIELD_ELAPSED_SECONDS: elapsed_s,
        FIELD_FINISHED_AT: _wall_clock(time.time()),
        FIELD_NODES: [
            node_document(channel.watch.nodes[send_id])
            for channel in channels
            for send_id in channel.watch.target.send_ids
        ],
    }


def refused_document(reason: str) -> dict[str, Any]:
    """The record of a watch that never reached a measurement."""
    return {
        FIELD_STATE: WATCH_REFUSED,
        FIELD_REASON: reason,
        FIELD_FINISHED_AT: _wall_clock(time.time()),
    }


# --- The detached watch ---


def run_worker(
    captures_root: Path, config_directory: Path, seconds: float, start_epoch: float
) -> int:
    """Run the watch in the detached process, opening nothing before its instant.

    Ownership: this is the only process that touches the bus during a watch. It re-checks the
    bench, because the operator's shell returned long ago and a lock taken by somebody else in the
    meantime must stop the watch rather than be discovered after the socket is open.

    Args:
        captures_root: Where the watch is recorded.
        config_directory: Where the binding and end-effector records live.
        seconds: How long to watch.
        start_epoch: The instant the timetable promised the first frame.

    Returns:
        (int) `EXIT_OK` when every fitted motor stayed clean, `EXIT_REFUSED` otherwise.
    """
    admission = admit(tuple(list_can_channels()), LockManager(), config_directory)
    if not admission.ok:
        record_watch(captures_root, refused_document(" / ".join(admission.refusals)))
        return EXIT_REFUSED

    locks = LockManager()
    interfaces = [target.interface for target in admission.targets]
    acquired = locks.acquire_all(interfaces)
    if not acquired.ok:
        record_watch(
            captures_root,
            refused_document(
                f"{acquired.blocked_iface} 의 채널 잠금을 다른 프로세스가 쥐고 있다 "
                f"({acquired.holder})"
            ),
        )
        return EXIT_REFUSED

    buses: list[NodeBus] = []
    try:
        _sleep_until(start_epoch)
        print(f"[{_wall_clock(time.time())}] 감시 시작 — 0xFD 만 나간다", flush=True)
        channels = []
        for target in admission.targets:
            bus = open_bus(target.interface, locks)
            buses.append(bus)
            channels.append(
                ArmChannel(watch=ArmWatch(target), reader=NodeReader(bus, REPLY_TIMEOUT_S))
            )
        elapsed = run_watch(channels, seconds, ROUND_PERIOD_S)
    except Exception as failure:
        # Every failure from here is this watch's verdict, whatever raised it. A traceback in a log
        # nobody opens is a watch with no answer; recorded, it reaches `--status`, which is the
        # only surface the operator reads after their shell returned.
        print(f"[{_wall_clock(time.time())}] 거부: {failure}", flush=True)
        record_watch(captures_root, refused_document(str(failure)))
        return EXIT_REFUSED
    finally:
        close_buses(buses)
        locks.release_all()

    document = finished_document(channels, elapsed)
    record_watch(captures_root, document)
    code, message = watch_verdict(document)
    print(f"[{_wall_clock(time.time())}] 판정: {message}", flush=True)
    return code


def _sleep_until(epoch: float) -> None:
    """Sleep until an absolute instant, returning at once when it has passed."""
    remaining = epoch - time.time()
    if remaining > 0:
        time.sleep(remaining)


def spawn_worker(captures_root: Path, seconds: float, start_epoch: float) -> Path:
    """Fork the watch into its own session and return the log it writes to.

    The fork is the point of the whole shape. The operator's shell prints nothing until the
    command it ran has ended, so the command that schedules has to end at once and leave the watch
    running behind it. Its stdin is closed for the same reason: a detached process reading the
    terminal the operator is about to type into is a question nobody can answer.

    Args:
        captures_root: Where the watch is recorded.
        seconds: How long to watch.
        start_epoch: The instant the timetable promised the first frame.

    Returns:
        (Path) The worker's log file.
    """
    directory = session_dir(captures_root)
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / LOG_FILENAME
    argv = [
        sys.executable,
        "-m",
        "scripts.can_node_watch",
        "--worker",
        "--captures",
        str(captures_root),
        "--seconds",
        f"{seconds:.3f}",
        "--start-epoch",
        f"{start_epoch:.3f}",
    ]
    # Fixed argv, no shell, no user-supplied executable.
    with log_path.open("a", encoding="utf-8") as log:
        subprocess.Popen(
            argv,
            cwd=str(Path(__file__).resolve().parents[1]),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return log_path


# --- The verdict ---


def _node_findings(nodes: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Sort every node into the diagnosis it earned.

    Silence, intermittency and a fault nibble are kept apart because they are different failures
    with different repairs: a silent node has no power, the wrong id, or a stopped MCU; an
    intermittent one is contact or harness; a faulted one is answering and telling you what is
    wrong with it.

    Args:
        nodes: The recorded node entries.

    Returns:
        (dict[str, list[str]]) Node labels per finding kind.
    """
    findings: dict[str, list[str]] = {
        "silent": [],
        "intermittent": [],
        "faulted": [],
        "unmeasured": [],
    }
    for node in nodes:
        label = f"{node[FIELD_SIDE]}/{node[FIELD_SEND_ID]:#04x}"
        attempts = int(node[FIELD_ATTEMPTS])
        replies = int(node[FIELD_REPLIES])
        if attempts == 0:
            findings["unmeasured"].append(label)
            continue
        if replies == 0:
            findings["silent"].append(label)
        elif replies < attempts:
            findings["intermittent"].append(label)
        if node[FIELD_FAULT_COUNTS]:
            names = ", ".join(
                STATE_NAMES.get(int(state), f"0x{int(state):X}")
                for state in sorted(node[FIELD_FAULT_COUNTS])
            )
            findings["faulted"].append(f"{label} ({names})")
    return findings


def watch_verdict(document: Mapping[str, Any]) -> tuple[int, str]:
    """Judge a recorded watch: the exit code, and what the operator should do next.

    Args:
        document: The recorded watch.

    Returns:
        (tuple[int, str]) The exit code and the one line that explains it.
    """
    state = document.get(FIELD_STATE)
    if state == WATCH_SCHEDULED:
        return (
            EXIT_RUNNING,
            f"아직 돌고 있다. 판정 시각 {document.get(FIELD_VERDICT_AT, '?')} 이후에 다시 읽는다.",
        )
    if state != WATCH_FINISHED:
        return EXIT_REFUSED, f"거부됨: {document.get(FIELD_REASON, '')}"
    nodes = document.get(FIELD_NODES) or []
    findings = _node_findings(nodes)
    if not any(findings.values()):
        return (
            EXIT_OK,
            "장착된 모터가 전부 매 라운드 응답했고 고장 니블도 없었다. 이 시간·이 자세 "
            "범위에서는 문제가 없다 — 간헐 고장은 자세 의존이므로 팔을 더 크게 움직여 다시 "
            "돌려볼 값어치가 있다.",
        )
    return EXIT_REFUSED, "응답이 온전하지 않은 노드가 있다. 토크를 인가하지 마라."


def _render_node(node: Mapping[str, Any]) -> str:
    """Render one node's line of the report."""
    attempts = int(node[FIELD_ATTEMPTS])
    replies = int(node[FIELD_REPLIES])
    rate = 100.0 * replies / attempts if attempts else 0.0
    faults = ""
    if node[FIELD_FAULT_COUNTS]:
        faults = "  고장: " + ", ".join(
            f"{STATE_NAMES.get(int(state), f'0x{int(state):X}')}×{count}"
            for state, count in sorted(node[FIELD_FAULT_COUNTS].items())
        )
    return (
        f"   {node[FIELD_SIDE]:<6}{node[FIELD_SEND_ID]:#04x} {node[FIELD_MOTOR_TYPE]:<8}"
        f"{rate:7.2f}% {attempts:8d} {node[FIELD_TRANSITION_COUNT]:6d}{faults}"
    )


def _render_transitions(node: Mapping[str, Any]) -> list[str]:
    """Render one node's transitions with the posture each happened at."""
    lines: list[str] = []
    for transition in node[FIELD_TRANSITIONS]:
        posture = "  ".join(
            f"{int(send_id):#04x}={angle:+.0f}°"
            for send_id, angle in sorted(transition[FIELD_POSTURE_DEG].items())
        )
        mark = "드롭" if transition[FIELD_KIND] == TRANSITION_DROP else "복구"
        lines.append(
            f"     t={transition[FIELD_AT_SECONDS]:7.2f}s  "
            f"{node[FIELD_SIDE]}/{node[FIELD_SEND_ID]:#04x}  {mark}   {posture}"
        )
    dropped = int(node[FIELD_TRANSITION_COUNT]) - len(node[FIELD_TRANSITIONS])
    if dropped > 0:
        lines.append(
            f"     … 전환 {dropped}건은 기록 상한({MAX_RECORDED_TRANSITIONS})을 넘어 안 남겼다"
        )
    return lines


def render_report(document: Mapping[str, Any]) -> str:
    """Render a recorded watch for the operator.

    Args:
        document: The recorded watch.

    Returns:
        (str) The report, ending with the line the exit code stands for.
    """
    state = document.get(FIELD_STATE)
    if state != WATCH_FINISHED:
        return watch_verdict(document)[1]
    lines = [
        f"  === {float(document[FIELD_ELAPSED_SECONDS]):.0f}s 감시 결과 "
        f"({document.get(FIELD_FINISHED_AT, '?')}) ===",
        "",
        f"   {'팔':<6}{'id':<5}{'종류':<8}{'응답률':>8}{'시도':>9}{'전환':>7}",
    ]
    nodes: Sequence[Mapping[str, Any]] = document.get(FIELD_NODES) or []
    lines.extend(_render_node(node) for node in nodes)
    transitions = [line for node in nodes for line in _render_transitions(node)]
    if transitions:
        lines.append("")
        lines.append("  전환 — 드롭이 특정 자세에 몰리면 하네스이고, 자세와 무관하면 노드다:")
        lines.extend(transitions)
    lines.append("")
    lines.extend(_render_findings(_node_findings(nodes)))
    lines.append(watch_verdict(document)[1])
    return "\n".join(lines)


def _render_findings(findings: Mapping[str, list[str]]) -> list[str]:
    """Render each diagnosis with what it means and what to do about it."""
    lines: list[str] = []
    if findings["silent"]:
        lines.append(f"  → 고정 무응답: {', '.join(findings['silent'])}")
        lines.append(
            "     이 시간 내내 한 번도 안 답했다. 셋 중 하나다 — ① 그 노드에 24V 가 안 간다"
        )
        lines.append("     ② CAN id 불일치 ③ MCU 정지. 보호 동작은 이 증상을 만들지 못한다:")
        lines.append("     DAMIAO 는 과열·과부하여도 상태 니블을 실어 응답한다.")
    if findings["intermittent"]:
        lines.append(f"  → 간헐: {', '.join(findings['intermittent'])}")
        lines.append("     응답이 오다 말다 했다 = 접촉·하네스다. 모터 고장은 이렇게 안 나온다.")
        lines.append("     위 전환 시각의 자세를 보라 — 특정 굽힘에서 몰리면 그 구간의 케이블이다.")
    if findings["faulted"]:
        lines.append(f"  → 고장 니블: {', '.join(findings['faulted'])}")
        lines.append(
            "     이 노드는 **응답하고 있고**, 자기 상태를 말하고 있다. 침묵과 다른 진단이다."
        )
        lines.append("     전압·전류·온도를 확인하고 clear_error 전에 원인을 없앤다.")
    if findings["unmeasured"]:
        lines.append(f"  → 미측정: {', '.join(findings['unmeasured'])}")
    if any(findings.values()):
        lines.append("")
        lines.append("  ⚠ 토크를 인가하지 마라. 통전 중에 노드가 빠지는 것은 못 막는다 — 정지는")
        lines.append("     힘을 빼는 것이라 어깨(11.67 N·m)가 빠지면 팔은 그대로 떨어진다.")
        lines.append("")
    return lines


def report_status(captures_root: Path) -> int:
    """Print what the detached watch recorded and exit with its verdict.

    Args:
        captures_root: The capture tree the watch was recorded in.

    Returns:
        (int) `EXIT_OK` when every fitted motor stayed clean, `EXIT_REFUSED` when one did not or
        the watch was refused, `EXIT_RUNNING` while it is still going, `EXIT_NO_SESSION` when this
        tree holds no watch at all.
    """
    document = read_watch(captures_root)
    if document is None:
        print(f"기록이 없다: {state_path(captures_root)}")
        return EXIT_NO_SESSION
    print(render_report(document))
    return watch_verdict(document)[0]


# --- Entry point ---


def _captures_root(args: argparse.Namespace) -> Path:
    """The capture tree this invocation reads and writes, defaulting to the operator's home."""
    return Path(args.captures) if args.captures else Path.home() / DEFAULT_CAPTURES_DIRNAME


def _schedule(captures_root: Path, seconds: float, start_epoch: float) -> None:
    """Print the timetable, mark the watch scheduled, and hand it to the detached worker."""
    print()
    print(render_timetable(start_epoch, seconds))
    record_watch(
        captures_root,
        {
            FIELD_STATE: WATCH_SCHEDULED,
            FIELD_SECONDS: seconds,
            FIELD_VERDICT_AT: _wall_clock(start_epoch + seconds),
        },
    )
    log_path = spawn_worker(captures_root, seconds, start_epoch)
    print()
    print("감시는 백그라운드에서 돈다. 이 명령은 여기서 끝난다.")
    print(f"  진행 기록: {log_path}")
    print("  판정 확인: ./scripts/can_node_watch.sh --status")


def main(argv: list[str] | None = None) -> int:
    """Admit the watch, print the timetable, and hand the measurement to a detached worker."""
    parser = argparse.ArgumentParser(prog="can_node_watch", description=__doc__)
    parser.add_argument("--captures", default=None, help="캡처 트리 (기본 ~/openarm_captures)")
    parser.add_argument(
        "--seconds",
        type=float,
        default=DEFAULT_WATCH_SECONDS,
        help="감시 시간 (기본 %(default)s초)",
    )
    parser.add_argument("--run", action="store_true", help="선행조건 통과 시 감시를 예약한다")
    parser.add_argument("--status", action="store_true", help="감시가 남긴 판정을 읽는다")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--start-epoch", type=float, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    captures_root = _captures_root(args)
    config_directory = default_config_directory()
    if args.status:
        return report_status(captures_root)
    if args.worker:
        start_epoch = args.start_epoch if args.start_epoch is not None else time.time()
        return run_worker(captures_root, config_directory, args.seconds, start_epoch)

    print(f"선행조건 검사 — 캡처 트리 {captures_root}")
    admission = admit(tuple(list_can_channels()), LockManager(), config_directory)
    print(admission.render())
    if not admission.ok:
        return EXIT_REFUSED
    if not args.run:
        print("\n선행조건 통과. 감시를 예약하려면 --run 을 붙인다.")
        return EXIT_OK
    _schedule(captures_root, args.seconds, time.time() + LEAD_SECONDS)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
