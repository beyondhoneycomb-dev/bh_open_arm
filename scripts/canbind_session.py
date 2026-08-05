"""Which arm is on which CAN channel: move one arm by hand, read both channels, write it down.

`ops.hw.canbind.identify` holds the judgment and opens nothing — it takes its reader as a
parameter so it needs no CAN socket and its tests need no rig. This is the program that supplies
that reader over a real bus. It lives under `scripts/` because `registry/`, `ops/` and
`dashboard/` import only pyyaml, jsonschema and mcap (pyproject records the rule and an AST scan
verifies it), and opening a channel needs the robot stack.

Three properties are the whole design, and each was a defect on this bench before it was a rule.

**The timetable is printed first and the measurement is detached.** A shell shows a command's
output only once the command has ended, so "move the arm now" printed by a running command
arrives after the instant it names — three E-Stop measurements were lost that way (`05` §1).
`--run` prints absolute wall-clock instants and forks; `--status` carries the verdict.

**Degrees in, radians out, at one named place.** `MOTION_THRESHOLD_RAD` is radians and
`DamiaoMotorsBus` decodes to degrees (`_decode_motor_state` returns `np.degrees(...)`; `01`
FR-SYS-016). Feeding degrees to the judge fails silently rather than loudly: 2.9° of noise would
clear a 0.05 "rad" motion gate while the quiet gate becomes 0.01°, which nothing on a live bus
satisfies, so every round would answer "did not stay still" and none could ever resolve.
`_joint_angles_rad` is the single crossing (CTR-UNIT@v1).

**Nothing here knows which arm is which, and that is the point rather than an omission.**
`scripts.rig_session` resolves an arm to an interface by reading the persisted binding; this
program is what determines that binding, so building on it would be circular — and the binding
does not currently resolve at all, because the adapter moved USB ports (`05` §3-2a). Every
channel is opened as an opaque interface name: no side, no role, no calibration, no zero. The
only side in the flow is the one the operator declares they are about to move by hand.

Opening a channel energizes it. `DamiaoMotorsBus.connect()` handshakes every registered motor
with 0xFC, so both arms are live — limp, because nothing commands kp, kd or tau, but live — from
the moment the socket opens rather than from any later step. `--run` refuses without
`--i-am-holding-the-arm`, and it refuses before the socket opens, not after.

Entry point is `scripts/canbind_session.sh`.
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
from typing import Any

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.damiao import DamiaoMotorsBus
from lerobot.robots.openarm_follower.config_openarm_follower import OpenArmFollowerConfig

from backend.actuation import DropCounter, is_cache_initialiser
from backend.can.lock import LockManager, guarded_connect
from backend.config.store import default_config_directory
from backend.endeffector import ARM_JOINT_SEND_IDS, SIDE_LEFT, SIDE_RIGHT, SIDES
from backend.torque_bringup.rig import POSITION_FIELD
from contracts.units import Deg, Rad, deg_to_rad
from ops.hw.canbind import (
    MOTION_THRESHOLD_RAD,
    QUIET_THRESHOLD_RAD,
    ArmRole,
    CanChannel,
    ChannelBinding,
    IdentificationResult,
    binding_path,
    bring_up_command,
    identify_moved_channel,
    list_can_channels,
    save_binding,
)

EXIT_OK = 0
EXIT_REFUSED = 1

# A round is scheduled and its verdict is not in yet, or one arm has no round at all. Distinct
# from EXIT_REFUSED because nothing has gone wrong: the answer is "wait" or "run the other arm",
# not "fix something".
EXIT_RUNNING = 2

# This capture tree holds no round at all. Distinct from EXIT_RUNNING for the same reason it is
# in `torque_session`: "not finished" and "never started" want opposite responses.
EXIT_NO_SESSION = 3

# Seconds between the timetable reaching the operator and the channel opening. The operator has
# to read the timetable and take hold of the arm before the handshake energizes it, and the arm
# has no brake, so this margin is the safety of the whole scheduled shape.
LEAD_SECONDS = 30.0

# Seconds between the channels opening and the baseline reading. The baseline is the pose every
# delta is measured from; taken while the operator is still settling their grip, it carries part
# of the motion the judge is about to look for.
SETTLE_SECONDS = 10.0

# Seconds the operator has to make the move. One deliberate shoulder swing of five degrees or
# more, not a race against a countdown they cannot see.
MOVE_WINDOW_SECONDS = 20.0

# Both follower channels have to be present. Fewer than two is nothing to tell apart, and every
# channel this opens is handshaked over the seven arm joints — a channel with no arm behind it
# fails the open rather than reading as the quiet one.
REQUIRED_CHANNEL_COUNT = 2

# The link bitrates this rig runs, for the bring-up command printed when a channel is down. The
# tool never brings a link up itself: that needs CAP_NET_ADMIN, and a tool that silently
# escalates is a tool nobody can audit.
LINK_BITRATE_BPS = 1_000_000
LINK_DATA_BITRATE_BPS = 5_000_000

WALL_CLOCK_FORMAT = "%H:%M:%S"

DEFAULT_CAPTURES_DIRNAME = "openarm_captures"
SESSION_DIRNAME = "canbind_session"
STATE_FILENAME = "state.json"
LOG_FILENAME = "session.log"

FIELD_ROUNDS = "rounds"
FIELD_STATE = "state"
FIELD_REASON = "reason"
FIELD_MOVED_INTERFACE = "moved_interface"
FIELD_MOVED_CHANNEL_KEY = "moved_channel_key"
FIELD_MOTIONS = "motions"
FIELD_INTERFACE = "interface"
FIELD_MAX_DELTA_RAD = "max_delta_rad"
FIELD_VERDICT_AT = "verdict_at"
FIELD_FINISHED_AT = "finished_at"

# What a round can be. `RESOLVED` is the only one the binding may be written from; the other
# three are all "do it again", and they are kept apart because they ask the operator for
# different things — wait, move differently, or fix the rig.
ROUND_SCHEDULED = "scheduled"
ROUND_RESOLVED = "resolved"
ROUND_INCONCLUSIVE = "inconclusive"
ROUND_REFUSED = "refused"

# The follower role each declared side occupies in the persisted record. This is the producer
# side of the pairing `scripts.rig_session.ARM_ROLE_BY_SIDE` reads back; a test pins the two
# equal, because a disagreement here writes the left arm's answer under the right arm's name.
ROLE_BY_SIDE: dict[str, ArmRole] = {
    SIDE_LEFT: ArmRole.FOLLOWER_LEFT,
    SIDE_RIGHT: ArmRole.FOLLOWER_RIGHT,
}

# Operator-facing name per side. The whole guide this implements is Korean and so is every other
# runner's output; a tool that answered in English here would be the only one.
LABEL_BY_SIDE = {SIDE_LEFT: "왼팔", SIDE_RIGHT: "오른팔"}

# The motors every round registers: the seven arm joints, which every tool build carries. The
# gripper id `0x08` is left out deliberately — whether it is fitted is recorded per side, and the
# side is the unknown this program exists to settle. Addressing a motor that is not on the bus
# walks the controller to ERROR-PASSIVE and degrades the seven joints that are.
IDENTIFICATION_SEND_IDS = ARM_JOINT_SEND_IDS

# The flag that stands in for the operator saying it out loud. It is a flag rather than a prompt
# because the prompt cannot be answered: the measurement runs detached with its stdin closed, and
# the shell that would show a question has already returned.
HOLD_ACKNOWLEDGEMENT_FLAG = "--i-am-holding-the-arm"

# The follower's stock motor table and CAN link settings live on its config, and constructing one
# takes a port. Reading the table needs no channel, so this name is never opened — `open_channel`
# builds its own config for the interface it does open.
TABLE_ONLY_PORT = "unopened"


class ChannelReadError(Exception):
    """Raised when a channel's reading cannot be used, so no verdict is derived from it."""


@dataclass(frozen=True)
class SessionConfig:
    """One identification round: which arm the operator will move, and where it is recorded.

    It carries no path to the binding record on purpose. A round measures and reports; writing
    the answer down is a separate command the operator types after reading the verdict, and the
    two are kept apart because the file is what makes the torque session's first gate pass.

    Attributes:
        side: The arm the operator declares they will move. A declaration, never a measurement —
            what is measured is which channel answered.
        captures_root: The operator's capture tree; the round state and the worker log live under
            it.
    """

    side: str
    captures_root: Path


@dataclass(frozen=True)
class RoundPlan:
    """The instants of one round, absolute because the operator reads them off a wall clock.

    Attributes:
        open_epoch: When the channels open and the arms go live.
        baseline_epoch: When the pose every delta is measured from is read.
        move_end_epoch: When the second reading is taken; the operator's move must be finished.
    """

    open_epoch: float
    baseline_epoch: float
    move_end_epoch: float


@dataclass(frozen=True)
class Admission:
    """What `--run` found before anything opened.

    Attributes:
        refusals: One line per reason this round cannot start. Empty means it can.
        channels: The CAN channels present, in the order they will be read.
    """

    refusals: tuple[str, ...]
    channels: tuple[CanChannel, ...]

    @property
    def ok(self) -> bool:
        """Whether the round may be scheduled."""
        return not self.refusals

    def render(self) -> str:
        """Render the channels found and every refusal against them."""
        lines = [f"채널 {len(self.channels)}개 열거됨"]
        lines.extend(
            f"  {channel.interface}  {channel.channel_key}  링크 {channel.state or '알 수 없음'}"
            for channel in self.channels
        )
        if self.ok:
            lines.append("  거부 없음")
        lines.extend(f"  거부: {refusal}" for refusal in self.refusals)
        return "\n".join(lines)


def _wall_clock(epoch: float) -> str:
    """Render an epoch as the operator's local wall-clock time."""
    return datetime.fromtimestamp(epoch).strftime(WALL_CLOCK_FORMAT)


def session_dir(captures_root: Path) -> Path:
    """The directory this round's state and log live in."""
    return captures_root / SESSION_DIRNAME


def state_path(captures_root: Path) -> Path:
    """The file every round's verdict is recorded in."""
    return session_dir(captures_root) / STATE_FILENAME


# --- Admission: the person first, then the rig, and both before any socket ---


def _hold_refusals(acknowledged: bool) -> tuple[str, ...]:
    """Refuse until the operator has said the arm is in their hands.

    Args:
        acknowledged: Whether the acknowledgement flag was given.

    Returns:
        (tuple[str, ...]) The refusal, or empty. The refusal exists because the bus handshake
        enables every fitted motor with 0xFC before anything else happens: the arm is live from
        the socket rather than from a later step, and there is no point in the round at which a
        person can still be told to take hold.
    """
    if acknowledged:
        return ()
    return (
        f"팔을 잡고 있다는 확인이 없다. 채널을 여는 순간 핸드셰이크가 모든 모터에 0xFC 를 "
        f"보내서 두 팔이 통전된다 — 토크 명령은 없지만 팔은 그때부터 살아 있다. "
        f"먼저 팔을 잡고, 그다음 {HOLD_ACKNOWLEDGEMENT_FLAG} 를 붙여 다시 실행한다.",
    )


def rig_refusals(channels: tuple[CanChannel, ...], locks: LockManager) -> tuple[str, ...]:
    """Every reason the rig cannot be read right now, in the order they are worth fixing.

    Args:
        channels: The CAN channels this host exposes.
        locks: The lock manager used to probe who holds each channel.

    Returns:
        (tuple[str, ...]) One line per refusal; empty when the round may open the channels.
    """
    refusals: list[str] = []
    if len(channels) != REQUIRED_CHANNEL_COUNT:
        refusals.append(
            f"CAN 채널이 {len(channels)}개다. {REQUIRED_CHANNEL_COUNT}개여야 한다 — 하나로는 "
            "가릴 대상이 없고, 이 도구가 여는 채널은 전부 일곱 관절로 핸드셰이크하므로 팔이 "
            "물려 있지 않은 채널은 조용한 쪽으로 읽히는 게 아니라 열기에서 실패한다."
        )
    down = [channel.interface for channel in channels if not channel.is_up]
    if down:
        argv = bring_up_command(down[0], LINK_BITRATE_BPS, LINK_DATA_BITRATE_BPS)
        refusals.append(
            f"링크가 내려가 있다: {', '.join(down)}. 이 도구는 링크를 올리지 않는다"
            f"(CAP_NET_ADMIN 이 필요하고, 몰래 권한을 올리는 도구는 감사할 수 없다). "
            f"당신 셸에서 채널마다: {' '.join(argv)}"
        )
    for state in locks.lock_state([channel.interface for channel in channels]):
        if state.holder is None:
            continue
        refusals.append(
            f"{state.iface} 의 채널 잠금을 {state.holder.holder_pid} 번 프로세스가 쥐고 있다"
            f"({state.lock_path}). 소켓은 잠금을 잡은 뒤에만 열린다(01 FR-SYS-005) — 한 채널에 "
            "작성자가 둘이면 두 번째가 내보내는 프레임은 아무도 판정하지 않은 프레임이다."
        )
    return tuple(refusals)


def admit(channels: tuple[CanChannel, ...], locks: LockManager, acknowledged: bool) -> Admission:
    """Judge everything that must hold before a socket opens: the operator, then the rig.

    Args:
        channels: The CAN channels this host exposes.
        locks: The lock manager used to probe who holds each channel.
        acknowledged: Whether the operator declared the arm is in their hands.

    Returns:
        (Admission) The channels found and every refusal against them.
    """
    return Admission(
        refusals=_hold_refusals(acknowledged) + rig_refusals(channels, locks),
        channels=channels,
    )


# --- The timetable, which reaches the operator before anything opens ---


def plan_round(start_epoch: float) -> RoundPlan:
    """Lay one round out from the instant the channels open."""
    baseline_epoch = start_epoch + SETTLE_SECONDS
    return RoundPlan(
        open_epoch=start_epoch,
        baseline_epoch=baseline_epoch,
        move_end_epoch=baseline_epoch + MOVE_WINDOW_SECONDS,
    )


def render_timetable(plan: RoundPlan, side: str) -> str:
    """Render the round as absolute wall-clock instants the operator can act on.

    Relative time is useless to somebody holding an arm and watching a clock — "in about fifteen
    seconds" means nothing when the moment it counts from is not on the screen — so every instant
    here is the time on the wall.

    Args:
        plan: The round's instants.
        side: The arm the operator declared they will move.

    Returns:
        (str) The timetable.
    """
    label = LABEL_BY_SIDE[side]
    other = LABEL_BY_SIDE[SIDE_RIGHT if side == SIDE_LEFT else SIDE_LEFT]
    return "\n".join(
        [
            f"지금 {_wall_clock(time.time())} — 아래 시각은 전부 벽시계다.",
            "",
            f"{_wall_clock(plan.open_epoch)}  채널 열림 — 이 시각 전에 {label}을 잡고 있어야 "
            "한다. 두 팔 모두 통전된다(0xFC). 토크 명령은 없고, 손으로 밀면 밀린다.",
            f"{_wall_clock(plan.baseline_epoch)}  기준값 읽음 — 이 순간에는 아무것도 움직이지 "
            "않아야 한다.",
            f"{_wall_clock(plan.baseline_epoch)} ~ {_wall_clock(plan.move_end_epoch)}",
            f"           ▶ {label}의 어깨(J1 또는 J2)를 한 번 크게 움직인다. 5도면 충분하다.",
            f"           ▶ {other}에는 손을 대지 않는다. 스치기만 해도 판정 불가가 된다.",
            f"{_wall_clock(plan.move_end_epoch)}  두 번째 읽음 · 판정 — 이 시각에는 손을 떼고 "
            "가만히 둔다.",
            "",
            f"판정 기준: 한 채널이 {MOTION_THRESHOLD_RAD} rad(약 2.9도)보다 크게 움직이고 "
            f"나머지가 {QUIET_THRESHOLD_RAD} rad(약 0.57도) 아래로 조용할 때만 답이 나온다. "
            "더 많이 움직인 쪽을 고르는 일은 없다.",
        ]
    )


# --- Reading a channel: degrees off the bus, radians to the judge ---


def _joint_angles_rad(
    states: Mapping[str, Mapping[str, float]], motor_names: tuple[str, ...]
) -> tuple[Rad, ...]:
    """Convert one channel's reading into the radian axis the judge measures on.

    This is the single site where a value from this bus changes unit (CTR-UNIT@v1: a boundary
    owns exactly one conversion site, and the crossing is the named `deg_to_rad`, never an
    arithmetic expression at a call site). `DamiaoMotorsBus._decode_motor_state` returns
    `np.degrees(position_rad)` and `MotorNormMode.DEGREES` keeps it that way (`01` FR-SYS-016),
    while `identify.MOTION_THRESHOLD_RAD` and `QUIET_THRESHOLD_RAD` are radians.

    Args:
        states: One state mapping per motor name, as the bus returned it.
        motor_names: The motors to read, in the order the vector carries them.

    Returns:
        (tuple[Rad, ...]) One angle per named motor.
    """
    return tuple(deg_to_rad(Deg(float(states[name][POSITION_FIELD]))) for name in motor_names)


class ChannelJointReader:
    """Reads one channel's joint angles for `identify_moved_channel`.

    Ownership: borrows the buses the round opened and closes none of them. It adds one thing to
    the bus's own read, and that thing is a refusal: a reading that lost a packet is not used.

    The bus does not distinguish a reply from a miss. It keeps a state cache initialised to zero
    for every registered motor and returns an entry for every name asked for, reporting a motor
    that said nothing as a `logging.WARNING` and leaving the previous value in place. Passed
    through, a motor that dropped on one of the two reads contributes a delta of zero, and the
    round then answers "no channel moved" while the arm plainly did.
    """

    def __init__(self, buses: Mapping[str, DamiaoMotorsBus], motor_names: tuple[str, ...]) -> None:
        """Bind the reader to the round's open channels.

        Args:
            buses: One open bus per interface, keyed by the interface name.
            motor_names: The motors to poll on every channel, and no others.
        """
        self._buses = buses
        self._motor_names = motor_names

    def __call__(self, interface: str) -> Sequence[float]:
        """Read one channel, in radians, refusing anything short of a full answer.

        Args:
            interface: The channel to read.

        Returns:
            (Sequence[float]) One angle per registered motor, radians — the plain floats
            `identify.JointReader` is declared over, unwrapped at this one point because that
            module carries no unit types.

        Raises:
            ChannelReadError: When the channel was never opened, when the bus lost a packet
                during the read, or when a motor answered nothing at all.
        """
        bus = self._buses.get(interface)
        if bus is None:
            raise ChannelReadError(f"{interface} 는 이번 회차에서 열린 채널이 아니다")
        drops = DropCounter()
        drops.attach()
        try:
            states = bus.sync_read_all_states(list(self._motor_names))
        finally:
            drops.detach()
        self._assert_answered(interface, states, drops.count)
        return tuple(angle.value for angle in _joint_angles_rad(states, self._motor_names))

    def _assert_answered(
        self, interface: str, states: Mapping[str, Mapping[str, float]], drops: int
    ) -> None:
        """Refuse a reading that is not one answer per registered motor.

        Args:
            interface: The channel read, for the refusal message.
            states: What the bus returned.
            drops: How many packet drops the bus logged during this read.

        Raises:
            ChannelReadError: On a drop, a missing entry, or a motor whose state is still the
                zeroed cache the bus was constructed with.
        """
        if drops:
            raise ChannelReadError(
                f"{interface} 를 읽는 동안 패킷이 {drops}개 유실됐다. 유실된 관절은 직전 값이 "
                "그대로 돌아오므로 움직인 팔이 조용한 것처럼 읽힌다 — 이 읽기는 버린다."
            )
        missing = [
            name
            for name in self._motor_names
            if name not in states or POSITION_FIELD not in states[name]
        ]
        if missing:
            raise ChannelReadError(f"{interface}: {', '.join(missing)} 의 위치가 오지 않았다")
        silent = [name for name in self._motor_names if is_cache_initialiser(states[name])]
        if silent:
            raise ChannelReadError(
                f"{interface}: {', '.join(silent)} 이(가) 한 번도 답하지 않았다. 버스는 그 자리에 "
                "초기화된 0을 돌려주고, 0도는 팔이 늘어져 있는 자세라 그럴듯해 보인다."
            )


class MoveWindow:
    """Waits out the window the operator was told to move in.

    `identify_moved_channel` calls this between the two readings; the ops module owns the
    judgment and the caller owns how the operator is asked. Here nobody is asked anything at all.
    The operator was given a wall-clock instant before this process existed, and the shell that
    could have carried a question returned long ago.
    """

    def __init__(self, end_epoch: float) -> None:
        """Wait until this instant.

        Args:
            end_epoch: When the second reading is due.
        """
        self._end_epoch = end_epoch

    def __call__(self) -> None:
        """Block until the move window has closed."""
        _sleep_until(self._end_epoch)


def _sleep_until(epoch: float) -> None:
    """Sleep until an absolute instant, returning at once when it has passed."""
    remaining = epoch - time.time()
    if remaining > 0:
        time.sleep(remaining)


# --- Opening a channel as nothing but a channel ---


def identification_motors(table: Mapping[str, tuple[int, int, str]]) -> dict[str, Motor]:
    """Build the motor registration one channel is opened with.

    Narrowed to the seven arm joints by send id rather than by name: the profile's authority is
    the id, and a name-keyed filter would agree with a table whose names had drifted.

    Args:
        table: The follower's motor table, name to `(send id, recv id, type)`.

    Returns:
        (dict[str, Motor]) The registration, in the table's order.
    """
    motors: dict[str, Motor] = {}
    for name, (send_id, recv_id, motor_type) in table.items():
        if send_id not in IDENTIFICATION_SEND_IDS:
            continue
        motor = Motor(send_id, motor_type, MotorNormMode.DEGREES)
        motor.recv_id = recv_id
        motor.motor_type_str = motor_type
        motors[name] = motor
    return motors


def identification_motor_names() -> tuple[str, ...]:
    """The motor names every channel is registered with, in the follower table's order.

    Read from the table rather than from an open bus: the reader has to know what it asked for
    before the first answer comes back, and every channel this round opens registers the same set.
    """
    return tuple(identification_motors(OpenArmFollowerConfig(port=TABLE_ONLY_PORT).motor_config))


def open_channel(interface: str, locks: LockManager) -> DamiaoMotorsBus:
    """Open one channel as an opaque interface, with no arm identity attached to it.

    No side, no role, no calibration, no zero: those are all keyed to an arm, and which arm this
    is, is the question. The socket opens through `guarded_connect`, so the channel lock is held
    first (`01` FR-SYS-005) and a missing lock never reaches the open.

    Args:
        interface: The kernel interface name.
        locks: The manager already holding this interface's lock.

    Returns:
        (DamiaoMotorsBus) The open bus. Every registered motor is enabled by the handshake.
    """
    config = OpenArmFollowerConfig(port=interface)
    bus = DamiaoMotorsBus(
        port=interface,
        motors=identification_motors(config.motor_config),
        calibration=None,
        can_interface=config.can_interface,
        use_can_fd=config.use_can_fd,
        bitrate=config.can_bitrate,
        data_bitrate=config.can_data_bitrate if config.use_can_fd else None,
    )
    guarded_connect(locks, [interface], bus.connect)
    return bus


def close_channels(buses: Mapping[str, DamiaoMotorsBus]) -> None:
    """Close every open channel, dropping torque on the way out.

    The opposite of what the torque session does on close, and for a reason that holds only here:
    that session may be holding a pose, and cutting torque under a brakeless arm is a fall rather
    than a stop. This round commands no kp, no kd and no tau, so the arm is limp either way; what
    the 0xFD changes is that the motors do not stay enabled after the process that opened them
    has gone.

    Args:
        buses: The channels this round opened.
    """
    for bus in buses.values():
        if bus.is_connected:
            bus.disconnect(disable_torque=True)


# --- The round, run detached ---


def round_entry_from(
    result: IdentificationResult, channels: tuple[CanChannel, ...]
) -> dict[str, Any]:
    """Turn one judged round into the record `--status` and `--write-binding` read.

    Args:
        result: The judge's own outcome. Never re-derived here — the judge refuses an ambiguous
            round on purpose, and a caller that picked the larger number would be the guess this
            whole module exists to prevent.
        channels: The channels as enumerated at measurement time, for their stable keys.

    Returns:
        (dict[str, Any]) The round record.
    """
    key_by_interface = {channel.interface: channel.channel_key for channel in channels}
    return {
        FIELD_STATE: ROUND_RESOLVED if result.resolved else ROUND_INCONCLUSIVE,
        FIELD_REASON: result.reason,
        FIELD_MOVED_INTERFACE: result.moved_interface,
        FIELD_MOVED_CHANNEL_KEY: key_by_interface.get(result.moved_interface or ""),
        FIELD_MOTIONS: [
            {FIELD_INTERFACE: motion.interface, FIELD_MAX_DELTA_RAD: motion.max_delta_rad}
            for motion in result.motions
        ],
        FIELD_FINISHED_AT: _wall_clock(time.time()),
    }


def _refused_entry(reason: str) -> dict[str, Any]:
    """The record of a round that never reached a judgment."""
    return {
        FIELD_STATE: ROUND_REFUSED,
        FIELD_REASON: reason,
        FIELD_FINISHED_AT: _wall_clock(time.time()),
    }


def run_worker(config: SessionConfig, plan: RoundPlan) -> int:
    """Run one round in the detached process, waking at each instant the operator was shown.

    Ownership: this is the only process that touches the bus during a round. It re-checks the
    rig, because the operator's shell returned long ago and a lock taken by somebody else in the
    meantime must stop the round rather than be discovered after the socket is open.

    Args:
        config: Where to record, and which arm the operator declared.
        plan: The instants the timetable promised.

    Returns:
        (int) `EXIT_OK` when the round resolved, `EXIT_REFUSED` otherwise.
    """
    channels = tuple(list_can_channels())
    locks = LockManager()
    refusals = rig_refusals(channels, locks)
    if refusals:
        record_round(config, _refused_entry(" / ".join(refusals)))
        return EXIT_REFUSED

    interfaces = tuple(channel.interface for channel in channels)
    acquired = locks.acquire_all(list(interfaces))
    if not acquired.ok:
        record_round(
            config,
            _refused_entry(
                f"{acquired.blocked_iface} 의 채널 잠금을 다른 프로세스가 쥐고 있다 "
                f"({acquired.holder})"
            ),
        )
        return EXIT_REFUSED

    buses: dict[str, DamiaoMotorsBus] = {}
    try:
        _sleep_until(plan.open_epoch)
        print(f"[{_wall_clock(time.time())}] 채널 열림 — 두 팔 통전", flush=True)
        for interface in interfaces:
            buses[interface] = open_channel(interface, locks)
        _sleep_until(plan.baseline_epoch)
        print(f"[{_wall_clock(time.time())}] 기준값 읽음", flush=True)
        result = identify_moved_channel(
            interfaces,
            ChannelJointReader(buses, identification_motor_names()),
            MoveWindow(plan.move_end_epoch),
        )
    except Exception as failure:
        # Every failure from here is this round's verdict, whatever raised it. A traceback into a
        # log nobody opens is a round with no answer; recorded, it reaches `--status`, which is
        # the only surface the operator reads after their shell returned.
        print(f"[{_wall_clock(time.time())}] 거부: {failure}", flush=True)
        record_round(config, _refused_entry(str(failure)))
        return EXIT_REFUSED
    finally:
        close_channels(buses)
        locks.release_all()

    entry = round_entry_from(result, channels)
    record_round(config, entry)
    verdict = f"{entry[FIELD_STATE]} {entry[FIELD_REASON]}"
    print(f"[{_wall_clock(time.time())}] 판정: {verdict}", flush=True)
    return EXIT_OK if result.resolved else EXIT_REFUSED


def spawn_worker(config: SessionConfig, start_epoch: float) -> Path:
    """Fork the round into its own session and return the log it writes to.

    The fork is the point of the whole design. The operator's shell prints nothing until the
    command it ran has ended, so the command that schedules has to end at once and leave the
    measurement running behind it. Its stdin is closed for the same reason: a detached process
    reading the terminal the operator is about to type into is a question nobody can answer.

    Args:
        config: The round to run.
        start_epoch: The instant the timetable promised the channels would open.

    Returns:
        (Path) The worker's log file.
    """
    directory = session_dir(config.captures_root)
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / LOG_FILENAME
    argv = [
        sys.executable,
        "-m",
        "scripts.canbind_session",
        "--worker",
        "--arm",
        config.side,
        "--captures",
        str(config.captures_root),
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


# --- The record, and the two commands that read it ---


def _write_state(path: Path, document: dict[str, Any]) -> None:
    """Replace the state file in one step, so `--status` never reads half a round.

    `--status` can run at any instant, including while the worker is recording. A rename is
    atomic where a truncate-and-rewrite is not, and a torn file reads as a parse error at exactly
    the moment the operator is asking for the verdict.
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


def read_rounds(captures_root: Path) -> dict[str, dict[str, Any]]:
    """Return every recorded round by side, empty when this tree holds none."""
    path = state_path(captures_root)
    if not path.exists():
        return {}
    document: Any = json.loads(path.read_text(encoding="utf-8"))
    rounds = document.get(FIELD_ROUNDS, {})
    return rounds if isinstance(rounds, dict) else {}


def record_round(config: SessionConfig, entry: dict[str, Any]) -> None:
    """Merge one arm's round into the state file, leaving the other arm's alone.

    Merging is right here and wrong in the torque session: a round is the whole measurement for
    one arm, so the other arm's standing answer is not a leftover from a run that did not finish
    — it is the other half of the same procedure.
    """
    rounds = read_rounds(config.captures_root)
    rounds[config.side] = entry
    _write_state(state_path(config.captures_root), {FIELD_ROUNDS: rounds})


def _render_round(side: str, entry: dict[str, Any] | None) -> str:
    """Render one arm's round for the operator."""
    label = LABEL_BY_SIDE[side]
    if entry is None:
        return f"  [ .. ] {label} ({side}) — 아직 안 함"
    state = entry.get(FIELD_STATE)
    if state == ROUND_SCHEDULED:
        return f"  [ .. ] {label} ({side}) — 예약됨, 판정 시각 {entry.get(FIELD_VERDICT_AT, '?')}"
    mark = "판정" if state == ROUND_RESOLVED else "거부"
    lines = [f"  [{mark}] {label} ({side}) — {entry.get(FIELD_FINISHED_AT, '?')}"]
    if state == ROUND_RESOLVED:
        lines.append(f"         움직인 채널 {entry.get(FIELD_MOVED_INTERFACE)}")
        lines.append(f"         채널 키     {entry.get(FIELD_MOVED_CHANNEL_KEY)}")
    else:
        lines.append(f"         {entry.get(FIELD_REASON, '')}")
    motions = entry.get(FIELD_MOTIONS) or []
    if motions:
        numbers = "  ".join(
            f"{motion[FIELD_INTERFACE]}={motion[FIELD_MAX_DELTA_RAD]:.4f}rad" for motion in motions
        )
        lines.append(f"         측정값     {numbers}")
    return "\n".join(lines)


def report_status(captures_root: Path) -> int:
    """Print what the detached rounds recorded and exit with the procedure's verdict.

    Takes no side: the procedure needs a round per arm, and showing one of them is how "half
    done" reads as done.

    Args:
        captures_root: The capture tree the rounds were recorded in.

    Returns:
        (int) `EXIT_OK` when both arms resolved onto different channels, `EXIT_REFUSED` when a
        recorded round did not resolve, `EXIT_RUNNING` while a round is scheduled or an arm has
        no round yet, `EXIT_NO_SESSION` when this tree holds no round at all.
    """
    rounds = read_rounds(captures_root)
    if not rounds:
        print(f"기록이 없다: {state_path(captures_root)}")
        return EXIT_NO_SESSION
    for side in SIDES:
        print(_render_round(side, rounds.get(side)))
    verdict = _procedure_verdict(rounds)
    print()
    print(verdict[1])
    return verdict[0]


def _procedure_verdict(rounds: Mapping[str, dict[str, Any]]) -> tuple[int, str]:
    """Judge the two rounds together: what the operator should do next, and the exit code."""
    states = {side: (rounds.get(side) or {}).get(FIELD_STATE) for side in SIDES}
    if any(state in (ROUND_REFUSED, ROUND_INCONCLUSIVE) for state in states.values()):
        return (
            EXIT_REFUSED,
            "판정이 나지 않은 회차가 있다. 위의 이유를 읽고 그 팔만 다시 한다 — 더 많이 움직인 "
            "쪽을 고르는 일은 없다.",
        )
    unfinished = [side for side, state in states.items() if state != ROUND_RESOLVED]
    if unfinished:
        return (
            EXIT_RUNNING,
            "아직 끝나지 않았다: " + ", ".join(f"{LABEL_BY_SIDE[side]}" for side in unfinished),
        )
    keys = {side: (rounds[side] or {}).get(FIELD_MOVED_CHANNEL_KEY) for side in SIDES}
    if keys[SIDE_LEFT] == keys[SIDE_RIGHT]:
        return (
            EXIT_REFUSED,
            "두 회차가 같은 채널을 가리킨다. 한 소켓이 두 팔일 수는 없다 — 케이블과 회차를 "
            "다시 확인하고 두 팔 모두 다시 한다.",
        )
    return (
        EXIT_OK,
        "두 팔 모두 판정됐다. 기록하려면: ./scripts/canbind_session.sh --write-binding",
    )


def write_binding(captures_root: Path, config_directory: Path) -> int:
    """Persist the two resolved rounds as the channel binding, refusing anything less.

    Writing this file is what makes the torque session's first gate pass, and a file written
    from a guess passes it just as quietly (`05` §3-2a records that happening on this bench). So
    it is a separate command the operator types after reading `--status`, it takes both arms'
    resolved rounds and nothing else, and it refuses when the channels those rounds were measured
    against are not the channels present now.

    Args:
        captures_root: The capture tree the rounds were recorded in.
        config_directory: Where the binding record lives.

    Returns:
        (int) `EXIT_OK` when the binding was written, `EXIT_REFUSED` otherwise.
    """
    rounds = read_rounds(captures_root)
    code, message = _procedure_verdict(rounds) if rounds else (EXIT_NO_SESSION, "기록이 없다")
    if code != EXIT_OK:
        print(message)
        return EXIT_REFUSED
    keys = {side: str(rounds[side][FIELD_MOVED_CHANNEL_KEY]) for side in SIDES}
    present = {channel.channel_key for channel in list_can_channels()}
    absent = [key for key in keys.values() if key not in present]
    if absent:
        print(
            f"회차가 잰 채널이 지금 없다: {', '.join(absent)}. 그 사이에 어댑터가 다른 포트로 "
            "옮겨졌다 — 지금 열거되는 채널에 옛 판정을 붙이는 것이 이 절차가 막으려는 그 일이다. "
            "두 팔 모두 다시 한다."
        )
        return EXIT_REFUSED
    path = binding_path(config_directory)
    save_binding(path, ChannelBinding(roles={ROLE_BY_SIDE[side]: keys[side] for side in SIDES}))
    print(f"{path} 에 기록했다:")
    for side in SIDES:
        print(f"  {ROLE_BY_SIDE[side].value:<16}{keys[side]}")
    print(
        "이 답은 어댑터를 다른 포트로 옮기거나, 팔 케이블을 뽑거나, 어댑터를 바꾸면 무효다. "
        "'뽑았다가 같은 자리에 도로 꽂았다'도 무효다."
    )
    return EXIT_OK


# --- Entry point ---


def _captures_root(args: argparse.Namespace) -> Path:
    """The capture tree this invocation reads and writes, defaulting to the operator's home."""
    return Path(args.captures) if args.captures else Path.home() / DEFAULT_CAPTURES_DIRNAME


def _schedule(config: SessionConfig, plan: RoundPlan, start_epoch: float) -> None:
    """Print the timetable, mark the round scheduled, and hand it to the detached worker."""
    print()
    print(render_timetable(plan, config.side))
    record_round(
        config,
        {
            FIELD_STATE: ROUND_SCHEDULED,
            FIELD_VERDICT_AT: _wall_clock(plan.move_end_epoch),
        },
    )
    log_path = spawn_worker(config, start_epoch)
    print()
    print("계측은 백그라운드에서 돈다. 이 명령은 여기서 끝난다.")
    print(f"  진행 기록: {log_path}")
    print("  판정 확인: ./scripts/canbind_session.sh --status")


def main(argv: list[str] | None = None) -> int:
    """Admit the round, print the timetable, and hand the measurement to a detached worker."""
    parser = argparse.ArgumentParser(prog="canbind_session", description=__doc__)
    parser.add_argument(
        "--arm",
        choices=SIDES,
        default=None,
        help="당신이 손으로 움직일 팔. 도구가 알아내는 것은 '어느 채널이 답했는가'뿐이다",
    )
    parser.add_argument("--captures", default=None, help="캡처 트리 (기본 ~/openarm_captures)")
    parser.add_argument("--run", action="store_true", help="선행조건 통과 시 회차를 예약한다")
    parser.add_argument("--status", action="store_true", help="회차가 남긴 판정을 읽는다")
    parser.add_argument(
        "--write-binding",
        action="store_true",
        help="두 팔 모두 판정됐을 때, 그 답을 채널 바인딩으로 기록한다",
    )
    parser.add_argument(
        HOLD_ACKNOWLEDGEMENT_FLAG,
        action="store_true",
        help="팔을 잡고 있다는 확인. 채널을 여는 순간 두 팔이 통전되므로 이것 없이는 열지 않는다",
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--start-epoch", type=float, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    captures_root = _captures_root(args)
    if args.status:
        return report_status(captures_root)
    if args.write_binding:
        return write_binding(captures_root, default_config_directory())
    if args.arm is None:
        print(
            "--arm left|right 이 필요하다. 어느 팔을 움직일지는 당신이 정해서 알려주는 값이고, "
            "도구가 재는 것은 그때 어느 채널이 답했는가다. 두 팔은 버스에서 똑같이 생겼다"
            "(03 §2.1)."
        )
        return EXIT_REFUSED
    config = SessionConfig(side=args.arm, captures_root=captures_root)
    if args.worker:
        start_epoch = args.start_epoch if args.start_epoch is not None else time.time()
        return run_worker(config, plan_round(start_epoch))

    print(
        f"선행조건 검사 — {LABEL_BY_SIDE[config.side]}을 움직인다, 캡처 트리 {config.captures_root}"
    )
    admission = admit(tuple(list_can_channels()), LockManager(), args.i_am_holding_the_arm)
    print(admission.render())
    if not admission.ok:
        return EXIT_REFUSED
    if not args.run:
        print("\n선행조건 통과. 회차를 예약하려면 --run 을 붙인다.")
        return EXIT_OK
    start_epoch = time.time() + LEAD_SECONDS
    _schedule(config, plan_round(start_epoch), start_epoch)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
