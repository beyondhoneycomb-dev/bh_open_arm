"""One operator session for the torque-ON stage: admit once, schedule once, measure, verify.

Every deferred torque-ON acceptance ships its own fixture hook and its own capture directory.
Run them one at a time and a human has to hold a brakeless 40 Nm arm through a dozen separate
invocations. This runner collapses that into a single admission and a single timetable: the
operator learns every wall-clock instant they must act on before anything engages.

Wall clock, not relative time, and the measurement runs detached. A bash command's output
reaches the operator only when the command ends, so a countdown printed during a run is
invisible while it matters — three E-Stop attempts on this bench were lost that way and nearly
produced a "the E-Stop circuit is not connected" verdict. `--run` therefore prints the whole
timetable, forks the worker with `start_new_session`, and returns at once; `--status` reads what
the worker has recorded so far and is the command that carries the verdict.

What this runner does not do itself is the reason it is short. It opens no write path: the
engage drives the rig binding (`backend.torque_bringup.rig`) assembled over the real arms by
`scripts.rig_session`, so every torque-bearing frame it causes leaves the way a
commanded frame does — `send_action` filters, the publisher fills the mailbox, one scheduler
tick performs the one CAN write. A second write path opened here would put a torque frame
outside the single writer the safety filter guards, so what is missing is refused by name
instead. Every capture is round-tripped through its own hook's loader before it is written, and
a capture the hook refuses is never written at all.

An engaged arm is an arm being refreshed. Past the RID-9 no-send ceiling the motor stops
applying the last MIT command, and with no brake that is a fall, so the engage leaves a thread
re-sending the hold and the release stops it before dropping torque.

Entry point is `scripts/torque_session.sh`, which supplies the repository root on `sys.path`.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_RUNNING = 2

# No session has been scheduled in this capture tree at all. Distinct from EXIT_RUNNING because
# a caller reading only the exit code cannot otherwise tell "not finished yet" from "never
# started", and those two want opposite responses: wait, or schedule.
EXIT_NO_SESSION = 3

# Seconds between the timetable reaching the operator and the first torque transition. The
# operator has to read the timetable, put both hands on the arm, and settle before anything
# engages; the arm has no brake, so this margin is the whole safety of the scheduled design.
LEAD_SECONDS = 30.0

# Seconds of stillness between two steps. Long enough for the operator to change grip and for
# the previous step's motion to damp out before the next one commands anything.
STEP_GAP_SECONDS = 15.0

# How long the worker may wait past a step's scheduled instant before giving up on it. A worker
# that overslept has lost the operator's attention, and running a torque step nobody is watching
# is worse than not running it.
SCHEDULE_SLIP_TOLERANCE_SECONDS = 120.0

# What the worker records for a step whose instant it overslept. One name because the worker
# writes it and the release-is-never-skipped check reads it. The skip verb in this sentence also
# occurs inside the torque-write-path refusal, so a check matching that one word reads a step
# that refused for an entirely unrelated reason as a step that was skipped.
SCHEDULE_SLIP_SKIP_DETAIL = "예정 시각 {instant} 을 {late:.0f}초 넘겼다; 건너뛴다"

# Argument tokens that would raise this process's privileges. The runner never escalates; a
# command needing root is printed for the operator to run in their own shell.
PRIVILEGE_TOKENS = ("sudo", "pkexec", "doas", "su")

# What separates one command word from the next inside a single argv element. Whitespace alone
# is not it: `sh -c "true;sudo ip link set can0 up"` puts the escalation right against a `;`,
# and every shell operator — `;` `&` `|` `(` `$` backtick — begins a command with no space in
# front of it. Path characters are kept so `/usr/bin/sudo` still reduces to its basename.
COMMAND_WORD_SEPARATOR = re.compile(r"[^\w./-]+")

# Where the operator's captures live, and the per-hook subdirectory each one expects. The
# threshold directory keeps the name the operator guide already uses.
DEFAULT_CAPTURES_DIRNAME = "openarm_captures"
SESSION_DIRNAME = "torque_session"
RID_CAPTURE_DIRNAME = "rid"
STATE_FILENAME = "state.json"
LOG_FILENAME = "session.log"

# The rig binding this session needs and this repository does not have: a `TorqueEngageBus`
# (`read_present_pose` + `engage_hold`) over the real motors bus. `backend/rtbench/rig.py` is
# the precedent for the naming — a `rig` module in the owning package that binds the protocol to
# the follower. Probed by import so the refusal lifts by itself the day the binding lands.
TORQUE_RIG_MODULE = "backend.torque_bringup.rig"
TORQUE_RIG_FACTORY = "build_engage_bus"

# The external tool the real frames-per-cycle count comes from (`PG-CAN-001` pattern B). Absent
# from this host's PATH, which is a refusal rather than a fallback to a modelled count.
CANDUMP_BINARY = "candump"
CANDUMP_INSTALL_COMMAND = "sudo apt install can-utils"

# Provenance of a capture payload. Only a measured payload may be written into the operator's
# capture tree; the synthetic payloads `--check` builds exist to prove the layouts load and are
# refused everywhere else.
SOURCE_MEASURED = "measured"
SOURCE_SYNTHETIC = "synthetic"

# `PG-STOP-001` stop-latency measurement belongs to neither this session nor WP-1-05. Named so the
# writer refuses the key rather than letting another session's artifact settle into this tree
# unnoticed. The search is over the whole payload, not its top level: every hook here nests its
# numbers one or two objects deep, so a top-level-only scan refuses the one shape nobody would
# actually write.
STOP_LATENCY_KEY = "stop_latency"

# State-file key under which a session that ended with torque possibly still on records that
# fact. It is not a step; it is the condition the operator is left standing in.
TORQUE_STATE_KEY = "torque_state"

# What the worker says when it ends without having reached its release step. It does not drop
# torque itself: with no holding brake the drop is a fall, and the only safe release is one the
# operator is supporting the arm through.
TORQUE_LEFT_LIVE_DETAIL = (
    "세션이 토크를 내리지 못한 채 끝났다. 팔이 아직 인게이지돼 있을 수 있다.\n"
    "  팔을 두 손으로 받친 상태에서 직접 토크를 내린다. 이 러너는 대신 내려주지 않는다 — "
    "브레이크가 없어서, 받치지 않은 팔의 토크 해제는 정지가 아니라 낙하다."
)

# Angle spacing in a synthetic pose. Only `--check` builds one; the value carries no physical
# meaning beyond being non-zero, which is what makes a hold-at-present displacement of 0 mean
# something.
SYNTHETIC_POSE_STEP_RAD = 0.05

# The single writer this rig's two CAN channels need, as a factory over the per-arm slot plan
# (`scripts.rig_session.ArmWriteSlots`). None is why both torque steps refuse,
# and it is the one wire this session is missing.
#
# `BusCanWriter` binds one bus and one motor-name order, and one scheduler emission is
# `BIMANUAL_BATCH_WIDTH` slots wide across two channels whose eight motor names are the same
# eight names. Handed sixteen names over one channel it writes eight frames and the second arm's
# angles land on the first arm's motors — measured on this host: a left slot asking for 0.0 rad
# arrived as 458.4°. Handed eight it raises on the batch width. So the split that carries one
# emission to both channels, and leaves the unfitted slot alone, has to exist first, and it
# belongs in `backend/actuation` — the one tree `find_producer_can_access` exempts — because a
# split written anywhere else puts the CAN write symbol outside it.
BIMANUAL_CAN_WRITER: Callable[[Any], Any] | None = None

# How often the engaged hold is re-sent while the arm is energized, seconds. Past the RID-9
# no-send ceiling (`12` NFR-SAF-007, `RID9_NO_SEND_MARGIN_SEC`) the motor stops applying the
# last MIT command, and with no brake that is the arm falling rather than the arm stopping.
# Half the ceiling, so one whole missed period still lands inside it.
HOLD_REFRESH_DIVISOR = 2.0

# What a step records when the operator is holding the arm. `GuardedTorqueOn.disengage` refuses
# without this declaration, and it comes from the timetable rather than a prompt: the operator
# was shown this step's wall-clock instant and its instruction before anything engaged, and this
# process is detached from the terminal a question would have gone to.
ARM_SUPPORTED_BY_TIMETABLE = True

# Capture blocks the engage writes, and the keys inside them. `engage` is what the WP-1-05
# re-verification hook reads; `rig_engage` is what the rig-engage acceptance reads. Named once
# so the producer and the hooks cannot drift on a spelling.
CAPTURE_ENGAGE_BLOCK = "engage"
CAPTURE_RIG_ENGAGE_BLOCK = "rig_engage"
CAPTURE_SEND_IDS_KEY = "send_ids"
CAPTURE_PRESENT_KEY = "present_pose_rad"
CAPTURE_FRAME_KEY = "engaged_frame"
CAPTURE_ZERO_RESIDUAL_BLOCK = "zero_residual"
CAPTURE_WITHIN_TOLERANCE_KEY = "within_tolerance"
CAPTURE_INTERFACES_KEY = "interfaces"

# The capture file stem the engage writes under. One file per host, which is the shape every
# hook in this tree globs for.
ENGAGE_CAPTURE_NAME = "engage"


ARM_LEFT = "left"
ARM_RIGHT = "right"
ARMS = (ARM_LEFT, ARM_RIGHT)

CALIBRATION_DIRNAME = "calibration"
CALIBRATION_ROBOT_IDS = {ARM_LEFT: "openarm_left", ARM_RIGHT: "openarm_right"}

WALL_CLOCK_FORMAT = "%H:%M:%S"


class Torque(Enum):
    """What a step does to the motors, stated before the step runs.

    The arm has no holding brake, so ENGAGE and RELEASE are both events the operator must have
    their hands on the arm for — RELEASE more than ENGAGE, because the arm falls.
    """

    NONE = "토크 변화 없음"
    ENGAGE = "🔴 토크 ON — 이때 팔을 잡고 있어야 한다"
    HOLD = "토크 ON 유지 (이 단계에서 켜지지도 꺼지지도 않는다)"
    RELEASE = "🔴 토크 OFF — 브레이크가 없으므로 팔이 중력으로 떨어진다"


class SessionRefusedError(RuntimeError):
    """A precondition or a step refused. Carries the operator-readable reason."""


@dataclass(frozen=True)
class Measurement:
    """One step's capture payload and where the numbers came from.

    Attributes:
        source: `SOURCE_MEASURED` for numbers off the rig, `SOURCE_SYNTHETIC` for the layout
            self-check. Only the former may be written into the capture tree.
        name: The capture file stem the hook loads it under.
        payload: The capture body, already in the shape the hook's loader expects.
    """

    source: str
    name: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class Step:
    """One step of the torque-ON stage: what the operator does, what the software does.

    Attributes:
        number: Position in the session, and the value `--step` selects.
        key: Stable identifier used in the state file.
        title: One-line operator-facing name.
        capture_dirname: Subdirectory of the capture root this step's hook reads, or None
            for a step that measures nothing.
        operator_action: What the human physically does, in their language.
        software_action: What this runner does while they do it.
        torque: The torque transition, announced before the step runs.
        duration_seconds: How long the step occupies the operator, for the timetable.
        hook_env_var: The environment variable that points the hook at this capture, or None.
        hook_test_path: The pytest path that re-verifies this capture, or None.
        produce: Returns the measurement, or raises `SessionRefusedError` naming what is missing.
            None for a step whose whole content is a torque transition the operator performs:
            the release takes the arm's weight, and there is no number in that.
        stage: Writes the payload into a directory and re-runs the hook's own loader over it,
            or None alongside a None `produce`.
        perform: Carries out a step whose content is an action rather than a measurement, and
            returns the line recorded for it. Exactly one of `produce` and `perform` is set.
    """

    number: int
    key: str
    title: str
    capture_dirname: str | None
    operator_action: str
    software_action: str
    torque: Torque
    duration_seconds: float
    hook_env_var: str | None
    hook_test_path: str | None
    produce: Callable[[SessionConfig], Measurement] | None
    stage: Callable[[Path], None] | None
    perform: Callable[[SessionConfig], str] | None

    @property
    def measures(self) -> bool:
        """Whether this step produces a capture a hook judges.

        A step that measures nothing still occupies the operator and still announces its torque
        transition; it simply has no payload, so the write-and-judge path is skipped rather than
        handed a None to walk into.
        """
        return self.produce is not None


@dataclass(frozen=True)
class SessionConfig:
    """Everything a step needs to know about this rig and this operator's directories.

    Attributes:
        arm: Which arm the session operates on.
        captures_root: The operator's capture tree.
        rid_capture_dir: Directory of real RID dumps the torque preflight is confirmed against.
        operator: The name this session runs under, carried through to the detached worker's
            argv. No capture payload records it: the attestation on a threshold calibration is
            where it belongs, and that producer refuses before it builds one.
        candump_path: A real capture of bus traffic, or None when the operator supplied none.
        manifest_path: The startup manifest declaring the four torque-ON gate preconditions,
            PG-SAFE-001's PASS hash among them. None when the operator supplied none, which
            is a refusal rather than an assumed PASS: `02a` §7 makes the manifest — not the
            code — the place a precondition either exists or does not.
    """

    arm: str
    captures_root: Path
    rid_capture_dir: Path
    operator: str
    candump_path: Path | None
    manifest_path: Path | None = None


@dataclass
class AdmissionResult:
    """The verdict of the whole admission gate, with one line of evidence per check.

    Attributes:
        lines: `(passed, label, detail)` per check, in the order they ran.
    """

    lines: list[tuple[bool, str, str]] = field(default_factory=list)

    def record(self, passed: bool, label: str, detail: str) -> None:
        """Append one check's verdict and its evidence."""
        self.lines.append((passed, label, detail))

    @property
    def ok(self) -> bool:
        """Whether every admission check passed. A single failure blocks the session."""
        return all(passed for passed, _, _ in self.lines)

    def render(self) -> str:
        """Render every check as `[통과]`/`[거부] label — detail`, one per line."""
        return "\n".join(
            f"  {'[통과]' if passed else '[거부]'} {label} — {detail}"
            for passed, label, detail in self.lines
        )


def run_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command, refusing any argument vector that would raise privileges.

    Args:
        argv: The command and its arguments.

    Returns:
        (subprocess.CompletedProcess[str]) The finished process.

    Raises:
        SessionRefusedError: If any token would escalate. Root work is printed for the operator to
            run themselves; a runner that can `sudo` can also `sudo` something nobody read.
    """
    for token in argv:
        # Each token is broken into command words before it is judged: `bash -c "sudo ..."`
        # carries the escalation inside one argv element, and a whole-token match walks straight
        # past it. Splitting fail-closed is deliberate — a refused command the operator can run
        # themselves costs a minute, and the other direction costs an unread root command.
        words = COMMAND_WORD_SEPARATOR.split(token)
        if any(Path(word).name in PRIVILEGE_TOKENS for word in words if word):
            raise SessionRefusedError(
                f"권한 상승 거부: {' '.join(argv)}\n"
                "  이 러너는 sudo 를 쓰지 않는다. 루트가 필요한 명령은 화면에 찍고 "
                "운영자가 자기 셸에서 직접 실행한다."
            )
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def _atomic_write_json(path: Path, document: dict[str, Any]) -> None:
    """Write a JSON document through a sibling temp file and a rename.

    A half-written state file is read by `--status` as a session that did something other than
    what it did, so the swap is atomic like every other persisted record in this project.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle_fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _wall_clock(epoch: float) -> str:
    """Render an epoch as the operator's local wall-clock time."""
    return datetime.fromtimestamp(epoch).strftime(WALL_CLOCK_FORMAT)


# --- Capture staging: every payload is judged by its own hook before it is written ---


def _write_payload(directory: Path, name: str, payload: dict[str, Any]) -> None:
    """Write one capture file into a directory the hook will glob."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _stage_torque_bringup(directory: Path) -> None:
    """Re-run the WP-1-05 hook, then judge the verdicts it returns without acting on.

    The zero residual is a field of the hook's result that the hook itself refuses on nowhere,
    so an unzeroed arm's capture loads through it without complaint. That one is decided here.

    The fitted-motor comparison is decided in both places on purpose. `default_profile()` is
    the only external truth about which ids this bench carries — a capture's own id list is
    consistent with itself whatever it polled — and the id is the whole failure: motor `0x08`
    answered 0 of 20 polls here, and sixteen unanswered frames walk both channels to
    ERROR-PASSIVE, degrading the seven joints that are present.

    Raises:
        SessionRefusedError: If the hook refuses the capture, if the engage addressed a motor
            set other than the fitted one, if the engage moved the arm, or if the arm's zero
            residual was outside tolerance when the capture was taken.
    """
    from backend.endeffector import default_profile
    from backend.torque_bringup.reverify import reverify_from_fixture

    fitted = tuple(default_profile().motor_send_ids)
    for verification in reverify_from_fixture(directory):
        engaged = tuple(verification.engaged_send_ids)
        if engaged != fitted:
            shown = " ".join(f"{send_id:#04x}" for send_id in engaged)
            expected = " ".join(f"{send_id:#04x}" for send_id in fitted)
            raise SessionRefusedError(
                f"인게이지가 장착 모터 집합과 다르다: 캡처 [{shown}] vs 장착 [{expected}]. "
                "없는 모터에 프레임을 보내면 아무도 ACK 하지 않고 컨트롤러가 ERROR-PASSIVE 로 "
                "떨어져, 실제로 있는 관절들까지 함께 열화된다."
            )
        # Inert while `backend.torque_bringup.reverify._verify_engage` derives the displacement
        # by rebuilding the hold from the same `present_pose_rad` the capture supplied — every
        # entry is 0.0 for any capture, so this cannot refuse one. The capture format records
        # no commanded target to compare against. Kept because it is the acceptance the runner
        # would be checked on, and it fires the day the capture carries what was really sent.
        if set(verification.engage_displacement_rad) != {0.0}:
            raise SessionRefusedError(
                f"인게이지가 현재 자세를 벗어났다: {verification.engage_displacement_rad}"
            )
        if not verification.zero_residual_within_tolerance:
            raise SessionRefusedError(
                "영점 잔차가 허용범위를 벗어난 상태에서 캡처됐다. 영점이 틀린 팔의 인게이지는 "
                "아무도 측정하지 않은 각도를 목표로 잡는다 — 먼저 영점을 다시 잡는다."
            )


def stage_capture(step: Step, measurement: Measurement) -> None:
    """Judge a payload with its own hook in a throwaway directory.

    Nothing reaches the operator's capture tree until the hook that will later read it has
    already loaded it and agreed. A capture the hook refuses is never written, so the tree
    cannot accumulate files that only fail months later inside a pytest run.

    Raises:
        SessionRefusedError: If the step declares no hook to judge the payload with, or if the
            hook refused the payload.
    """
    if step.stage is None:
        raise SessionRefusedError(
            f"{step.key}: 이 단계에는 캡처를 판정할 훅이 없다. 판정자 없이 쓰인 캡처는 아무도 "
            "읽지 않는 파일로 캡처 트리에 남는다."
        )
    scratch = Path(tempfile.mkdtemp(prefix=f"oa-stage-{step.key}-"))
    try:
        _write_payload(scratch, measurement.name, measurement.payload)
        step.stage(scratch)
    except SessionRefusedError:
        raise
    except Exception as refusal:  # noqa: BLE001 — a hook's own refusal type is its verdict
        raise SessionRefusedError(
            f"{step.key}: 훅이 캡처를 거부했다 ({type(refusal).__name__}) {refusal}"
        ) from refusal
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _payload_carries_key(node: Any, key: str) -> bool:
    """Whether a key appears anywhere in a capture payload, at any nesting depth.

    A payload is a live Python object on its way to `json.dumps`, so a tuple is a list by the
    time anybody reads the file; both sequence shapes are walked or the scan is blind to
    whichever one the producer happened to build.

    Args:
        node: A payload or any fragment of one.
        key: The key being searched for.

    Returns:
        (bool) True if any object anywhere under `node` carries the key.
    """
    if isinstance(node, dict):
        return key in node or any(_payload_carries_key(value, key) for value in node.values())
    if isinstance(node, (list, tuple)):
        return any(_payload_carries_key(item, key) for item in node)
    return False


def write_capture(step: Step, measurement: Measurement, captures_root: Path) -> Path:
    """Stage, judge, then write one capture into the directory its hook reads.

    Args:
        step: The step the capture belongs to.
        measurement: The payload and its provenance.
        captures_root: The operator's capture tree.

    Returns:
        (Path) The written capture file.

    Raises:
        SessionRefusedError: If the step has no capture directory of its own, if the payload was
            not measured on the rig, if it carries the descoped stop-latency measurement, or if
            its own hook refused it.
    """
    if step.capture_dirname is None:
        raise SessionRefusedError(
            f"{step.key}: 이 단계는 캡처 디렉터리가 없다 — 측정하지 않는 단계다. "
            "동작만 하는 단계에 페이로드가 생겼다면 그 값은 어느 훅도 기다리지 않은 값이다."
        )
    if measurement.source != SOURCE_MEASURED:
        raise SessionRefusedError(
            f"{step.key}: 출처가 '{measurement.source}' 인 캡처는 캡처 트리에 쓰지 않는다. "
            "실측이 아닌 값이 훅에 들어가면 그 훅은 하드웨어 사실을 위조한 것이 된다."
        )
    if _payload_carries_key(measurement.payload, STOP_LATENCY_KEY):
        raise SessionRefusedError(
            f"{step.key}: 이 세션은 정지 지연(PG-STOP-001) 측정을 다루지 않는다. "
            f"캡처에 '{STOP_LATENCY_KEY}' 키가 있으면 다른 세션의 산출물이다."
        )
    stage_capture(step, measurement)
    directory = captures_root / step.capture_dirname
    _write_payload(directory, measurement.name, measurement.payload)
    return directory / f"{measurement.name}.json"


# --- Producers: what actually measures each step, and what refuses when it cannot ---


def torque_rig_factory() -> Callable[..., Any] | None:
    """Return the rig's engage-bus factory, or None while that binding does not exist.

    The one fact every torque-bearing refusal in this runner is derived from, kept in one
    place so the refusal and the self-check that proves the refusal cannot drift apart.

    The name has to be bound to something callable, not merely present. A module landing with
    `build_engage_bus = None` or a placeholder string would otherwise satisfy the admission
    gate on the strength of the name alone, and that gate is what decides whether a person is
    asked to put both hands on a brakeless arm.

    Returns:
        (Callable[..., Any] | None) `build_engage_bus`, or None when the module is absent or
        the name is not bound to a callable.
    """
    if importlib.util.find_spec(TORQUE_RIG_MODULE) is None:
        return None
    module = importlib.import_module(TORQUE_RIG_MODULE)
    factory: object = getattr(module, TORQUE_RIG_FACTORY, None)
    if not callable(factory):
        return None
    return factory


def _require_torque_write_path(step_key: str) -> None:
    """Refuse a step that needs the arm to move, naming the binding this repository lacks.

    `GuardedTorqueOn` drives a `TorqueEngageBus`, and the only implementations of that protocol
    in the tree are the recording fakes in `tests/wp105/conftest.py`. `OaOpenArmFollower` binds
    `connect_readonly` only, and its `send_action` does not publish onto the scheduler mailbox
    (`tests/wp103/test_gateway_write_path_assembly.py` skips on exactly that gap). No motor can
    be commanded from this repository today.

    Raises:
        SessionRefusedError: Always, until the rig binding module exists.
    """
    if torque_rig_factory() is not None:
        return
    raise SessionRefusedError(
        f"{step_key}: 토크 쓰기 경로가 조립되어 있지 않다.\n"
        f"  필요한 것: {TORQUE_RIG_MODULE}.{TORQUE_RIG_FACTORY}() — 실제 모터 버스 위의\n"
        "  TorqueEngageBus (read_present_pose / engage_hold). 지금 이 프로토콜을 구현한 것은\n"
        "  tests/wp105/conftest.py 의 기록용 가짜뿐이고, OaOpenArmFollower 는 connect_readonly\n"
        "  (토크 OFF)만 묶여 있다. send_action 의 통과분은 스케줄러 메일박스로 나가지 않는다\n"
        "  (tests/wp103/test_gateway_write_path_assembly.py 가 그 틈에서 건너뛴다).\n"
        "  이 러너는 그 경로를 여기서 새로 열지 않는다 — 단일 작성자 밖의 토크 프레임은\n"
        "  8단계 안전 필터를 우회하고, 브레이크 없는 40 Nm 팔에서 그것은 안전 거짓말이다."
    )


def _require_bimanual_writer(step_key: str) -> Callable[[Any], Any]:
    """Return the single-writer factory, refusing while this rig has none.

    The rig binding exists and the enforcement point publishes into the scheduler's mailbox;
    what is missing is the one object that carries a scheduler emission to two CAN channels.
    `BIMANUAL_CAN_WRITER` is where it is read from, so this refusal and the admission gate that
    reports it cannot drift apart.

    Args:
        step_key: The step asking, for the refusal message.

    Returns:
        (Callable[[Any], Any]) The factory that builds the writer from the per-arm slot plan.

    Raises:
        SessionRefusedError: While no writer exists. Engaging without one means 0xFC with no
            frame behind it, and the only `CanWriter` in the tree misaddresses this rig: over
            one channel with sixteen names it puts the right arm's angles on the left arm's
            motors, which on a brakeless arm is a commanded jump.
    """
    factory = BIMANUAL_CAN_WRITER
    if factory is not None:
        return factory
    raise SessionRefusedError(
        f"{step_key}: 토크 쓰기 경로가 절반만 조립돼 있다 — 두 채널에 하나의 이미션을 실어\n"
        "  보내는 단일 작성자가 없다.\n"
        "  지금 있는 유일한 프로덕션 CanWriter 는 BusCanWriter 이고, 그것은 버스 하나와 모터\n"
        "  이름 순서 하나에 묶인다. 이 리그는 채널이 둘이고 두 팔의 모터 이름 여덟 개가 같은\n"
        "  여덟 개다 — 한 채널에 16개 이름을 주면 프레임 8개만 나가고 오른팔 각도가 왼팔\n"
        "  모터에 실린다(이 호스트에서 실측: 0.0 rad 를 요구한 왼팔 슬롯이 458.4°로 도착).\n"
        "  8개를 주면 배치 폭에서 거부한다. 그래서 이미션을 두 채널로 쪼개고 장착되지 않은\n"
        "  슬롯(0x08)을 건너뛰는 작성자가 먼저 있어야 하고, 그 자리는 backend/actuation 이다\n"
        "  — find_producer_can_access 가 면제하는 단 하나의 트리이고, 그 밖에서 쪼개면 CAN\n"
        "  쓰기 심볼이 그 트리 밖으로 나간다."
    )


@dataclass
class LiveTorqueSession:
    """What the engage energized, kept so the release drops exactly that.

    Ownership: owns the assembled rig session (its two channel locks and two open sockets) and
    the thread re-sending the hold. The engage puts one of these here and the release takes it;
    nothing else may hold one, because two of them would be two writers on one channel.

    Attributes:
        guarded: The `GuardedTorqueOn` session whose `disengage` is the way out.
        rig: The assembled write path, held so the release can give the locks back.
        maintainer: The thread keeping the hold alive, stopped before the drop.
    """

    guarded: Any
    rig: Any
    maintainer: HoldMaintainer


# The one live torque session in this process. A module-level holder because the engage and the
# release are two separately scheduled steps of one worker, each called with nothing but the
# session config — and the release has to drop what the engage energized rather than a fresh
# assembly's idea of it.
_LIVE_SESSION: LiveTorqueSession | None = None


class HoldMaintainer(threading.Thread):
    """Re-sends the engaged hold until it is told to stop.

    An engage puts one frame on the bus; the arm stays up because the frame keeps being sent.
    Past the RID-9 no-send ceiling the motor stops applying the last MIT command, and with no
    brake that is the arm falling — so between the engage step and the release step, seventy
    seconds later, something has to keep ticking.

    Ownership: borrows the assembled rig and drives its `maintain_hold`, which is one scheduler
    tick and so one CAN write. It is the only thread that touches the bus while it runs, which
    is why the release stops and joins it before dropping torque: `disable_torque` and a MIT
    write share one socket.

    Threading: one instance per engaged session. A tick that raises stops the loop and is kept
    in `failure`, because a maintenance loop that died silently is an arm nobody is refreshing.
    """

    def __init__(self, rig: Any, period_sec: float) -> None:
        """Bind the maintainer to the rig whose hold it re-sends.

        Args:
            rig: The assembled rig; its `maintain_hold` is one tick.
            period_sec: Interval between re-sends, under the RID-9 no-send ceiling.
        """
        super().__init__(name="oa-hold-maintainer", daemon=True)
        self._rig = rig
        self._period_sec = period_sec
        # Not `_stop`: `threading.Thread._stop` is a method its own bootstrap calls when `run`
        # returns, and shadowing it with an Event makes the thread raise on its way out.
        self._stop_event = threading.Event()
        self.failure: BaseException | None = None
        self.ticks = 0

    def run(self) -> None:
        """Re-send the hold every period until stopped, recording the tick that failed."""
        while not self._stop_event.is_set():
            try:
                self._rig.maintain_hold()
            except BaseException as failure:  # noqa: BLE001 — a dead loop is the whole finding
                self.failure = failure
                return
            self.ticks += 1
            self._stop_event.wait(self._period_sec)

    def stop(self) -> None:
        """Stop re-sending and wait for the loop to leave the bus alone.

        Tolerant of never having started, because the engage records the live session before it
        engages: a bus that raised before 0xFC leaves a session the release still has to close.
        """
        self._stop_event.set()
        if self.ident is not None:
            self.join()


def _end_effector_record() -> Any:
    """Return what each arm carries, from the operator's record or the no-gripper default.

    The record is read when it exists, because which tool is bolted on is a fact about the
    bench that changes without any file changing. The fallback is `default_rig()` — both arms
    on the build with no motor on `0x08` — and that asymmetry is deliberate: defaulting to a
    gripper on a rig without one makes every poll address an id nobody answers on, which walks
    the controller to ERROR-PASSIVE and degrades the seven joints that are present.

    Returns:
        (RigEndEffectors) What each arm carries.

    Raises:
        SessionRefusedError: If either arm's record declares the gripper motor. That is the
            same rule the admission gate applies, re-applied to the record the engage will
            actually poll with: the gate reads the default profile, so a record that disagrees
            with it would reach the bus unjudged.
    """
    from backend.config.store import default_config_directory
    from backend.endeffector import GRIPPER_SEND_ID, SIDES, default_rig, load_rig, rig_path

    record = rig_path(default_config_directory())
    rig = load_rig(record) if record.is_file() else default_rig()
    for side in SIDES:
        profile = rig.for_side(side)
        if GRIPPER_SEND_ID in profile.motor_send_ids:
            raise SessionRefusedError(
                f"{side} 팔의 기록된 도구 {profile.tool_id} 가 {GRIPPER_SEND_ID:#04x} 를 "
                "선언한다. 이 벤치에서 그 id 는 20회 폴링 중 0회 응답했고, 응답 없는 프레임은 "
                "컨트롤러를 ERROR-PASSIVE 로 끌어내려 실제로 있는 7관절까지 열화시킨다. "
                "그리퍼를 실제로 장착했다면 모터 프로브부터 다시 뜬다."
            )
    return rig


def _startup_manifest(config: SessionConfig) -> Any:
    """Read the startup manifest the engage is admitted against.

    Args:
        config: This session's config, carrying the manifest path.

    Returns:
        (TorqueOnManifest) The four declared gate preconditions.

    Raises:
        SessionRefusedError: If no manifest was supplied, or it cannot be read. `02a` §7 makes
            the PG-SAFE-001 PASS hash a declared manifest field, so a manifest this runner
            filled in itself would be the code asserting the gate it is supposed to be gated by.
    """
    from backend.torque_bringup.cli import manifest_from_document

    if config.manifest_path is None:
        raise SessionRefusedError(
            "기동 매니페스트가 없다 (--manifest). PG-SAFE-001 의 PASS 해시는 매니페스트가 "
            "선언하는 값이고, 러너가 스스로 채우면 그것은 게이트를 통과한 증거가 아니라 "
            "게이트를 대신 선언한 것이 된다."
        )
    try:
        return manifest_from_document(json.loads(config.manifest_path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as refusal:
        raise SessionRefusedError(
            f"기동 매니페스트를 읽을 수 없다 ({config.manifest_path}): {refusal}"
        ) from refusal


def _preflight_report(config: SessionConfig, iface: str, locks: Any) -> Any:
    """Run the five torque-ON preconditions for the selected arm on its own channel.

    The report is built under the locks the session already holds, because one of the five is
    the writer lock: a report taken with the lock released describes a different host than the
    one about to engage.

    Every dump of this channel is judged and the blocking verdict wins, for the reason
    `_admit_preflight` states — choosing between two dumps of one channel by filename lets a
    passing dump stand in for a failing one.

    Args:
        config: This session's config.
        iface: The channel the selected arm is on, as the binding resolved it.
        locks: The manager holding both channels' locks.

    Returns:
        (PreflightReport) The report the engage authorizes against.

    Raises:
        SessionRefusedError: If the RID capture directory holds no dump of this channel.
    """
    from backend.can.link import parse_link_show
    from backend.can.rid.reverify import reverify_from_fixture
    from backend.endeffector import default_profile
    from backend.preflight import JogSessionPreflight, PreflightInputs, RidCrosscheck
    from contracts.plugin.config import Side
    from packages.lerobot_robot_openarm.openarm_follower_oa import build_safety_limits

    completed = run_command(["ip", "-details", "link", "show", iface])
    link = parse_link_show(completed.stdout, iface) if completed.returncode == 0 else None
    evaluations = [
        evaluation
        for evaluation in reverify_from_fixture(
            config.rid_capture_dir, expected_motor_ids=default_profile().motor_send_ids
        )
        if evaluation.iface == iface
    ]
    if not evaluations:
        raise SessionRefusedError(f"{config.rid_capture_dir} 에 {iface} RID 덤프가 없다")
    reports = [
        JogSessionPreflight().run(
            PreflightInputs(
                rid=RidCrosscheck.confirmed(evaluation),
                side=Side.LEFT if config.arm == ARM_LEFT else Side.RIGHT,
                link=link,
                lock_state=locks.lock_state([iface])[0],
                clamp_canon=build_safety_limits(config.arm),
            )
        )
        for evaluation in evaluations
    ]
    blocking = [report for report in reports if not report.may_enable_torque]
    return blocking[0] if blocking else reports[0]


def _assemble_rig(step_key: str, end_effectors: Any) -> Any:
    """Assemble the whole write path over both arms, with nothing energized.

    Args:
        step_key: The step assembling, so a refusal names the step the operator was called for.
        end_effectors: What each arm carries.

    Returns:
        (RigSession) The assembled session; torque is off on every motor.

    Raises:
        SessionRefusedError: If no single writer exists, or the assembly refused.
    """
    from backend.config.store import default_config_directory
    from scripts.rig_session import RigAssemblyError, build_rig_session

    make_writer = _require_bimanual_writer(step_key)
    directory = default_config_directory()
    try:
        return build_rig_session(
            make_can_writer=make_writer,
            end_effectors=end_effectors,
            calibration_dir=directory / CALIBRATION_DIRNAME,
            robot_ids=CALIBRATION_ROBOT_IDS,
            config_directory=directory,
        )
    except RigAssemblyError as refusal:
        raise SessionRefusedError(f"{step_key}: 쓰기 경로를 조립할 수 없다: {refusal}") from refusal


def _engaged_frame_for_arm(rig_session: Any, arm: str, fitted: tuple[str, ...]) -> list[Any]:
    """Return the fitted slice of the frame the single writer emitted for this arm's engage.

    The emission is one bimanual frame, so this arm's joints occupy its own half of it in the
    frozen arm-major order. Only the fitted slots are carried into the capture, because the
    hook compares the frame against a pose that is the fitted width and no motor answers behind
    the rest.

    Args:
        rig_session: The assembled session.
        arm: Which arm engaged.
        fitted: This arm's fitted motor names, in the order the read addressed them.

    Returns:
        (list) One `ExecutedMitCommand` per fitted motor.

    Raises:
        SessionRefusedError: If no frame was emitted for the engage. The engage compares the
            emission to the decision before and after 0xFC, so a missing one means the record
            of what reached the motors is gone.
    """
    from backend.calibration.schema import MOTOR_ORDER
    from backend.endeffector import SIDES

    emitted = rig_session.rig.for_side(arm).last_emitted_frame
    if emitted is None:
        raise SessionRefusedError(
            "인게이지가 단일 작성자의 프레임을 남기지 않았다. 모터에 실제로 무엇이 갔는지에 "
            "대한 기록이 없으면 캡처는 아무것도 판정할 수 없다."
        )
    offset = SIDES.index(arm) * len(MOTOR_ORDER)
    return [emitted[offset + MOTOR_ORDER.index(name)] for name in fitted]


def _zero_residual_within_tolerance(arm: str) -> bool:
    """Whether the persisted zero for an arm is inside the per-joint tolerance.

    Read off the calibration the arm actually loaded and recomputed through the one definition
    of the tolerance, rather than transcribed from the file's own verdict field.

    Args:
        arm: Which arm.

    Returns:
        (bool) True when every joint's residual is within tolerance.
    """
    from backend.calibration.atomic_io import calibration_path_for, load_calibration
    from backend.calibration.verify import compute_residual
    from backend.config.store import default_config_directory

    directory = default_config_directory() / CALIBRATION_DIRNAME
    calibration = load_calibration(calibration_path_for(directory, CALIBRATION_ROBOT_IDS[arm]))
    residual = compute_residual(
        list(calibration.motor_zero_raw), list(calibration.urdf_zero_offset)
    )
    return residual.within_tolerance


def _engage_payload(
    config: SessionConfig, rig_session: Any, result: Any, frame: list[Any]
) -> dict[str, Any]:
    """Build the capture the WP-1-05 hooks read, entirely out of what was measured.

    Two blocks carry the same ids and pose because two hooks read them: the re-verification
    hook rebuilds the hold from `engage`, and the rig-engage acceptance compares the frame the
    writer emitted against the pose in `rig_engage`. Neither derives the other's numbers.

    Args:
        config: This session's config.
        rig_session: The assembled session, for the channel each arm was on.
        result: The `EngageResult` the guarded engage returned.
        frame: The fitted slice of the frame the single writer emitted.

    Returns:
        (dict[str, Any]) The capture payload.
    """
    send_ids = [int(send_id) for send_id in result.send_ids]
    present = [float(angle.value) for angle in result.present]
    return {
        "host_id": platform.node() or config.operator,
        CAPTURE_INTERFACES_KEY: dict(rig_session.interfaces),
        CAPTURE_ENGAGE_BLOCK: {
            CAPTURE_SEND_IDS_KEY: send_ids,
            CAPTURE_PRESENT_KEY: present,
        },
        CAPTURE_RIG_ENGAGE_BLOCK: {
            CAPTURE_SEND_IDS_KEY: send_ids,
            CAPTURE_PRESENT_KEY: present,
            CAPTURE_FRAME_KEY: [
                {
                    "kp": float(command.kp),
                    "kd": float(command.kd),
                    "q": float(command.q.value),
                    "dq": float(command.dq.value),
                    "tau": float(command.tau.value),
                }
                for command in frame
            ],
        },
        CAPTURE_ZERO_RESIDUAL_BLOCK: {
            CAPTURE_WITHIN_TOLERANCE_KEY: _zero_residual_within_tolerance(config.arm)
        },
    }


def _release_torque(config: SessionConfig) -> str:
    """Drop torque on the fitted motors, ending the session.

    Not the stop path. `04` NFR-MAN-002 makes a stop a Cat-2 hold frame; this is the operator
    deliberately ending the session with the arm's weight already in their hands, which is the
    one condition under which removing torque from a brakeless arm is correct.

    `GuardedTorqueOn.disengage` takes that condition as an argument and refuses without it. The
    declaration comes from the timetable rather than from a prompt: the operator was shown this
    step's wall-clock instant and its instruction before anything engaged, and this process is
    detached from the terminal that would have carried a question. Asking here would be a
    question nobody can answer.

    The hold maintainer is stopped and joined before the drop. `disable_torque` and a MIT write
    share one socket, and a drop racing a re-send is a frame going out after the motors were
    told to let go.

    A selection that runs this step alone assembles its own session and drops there. Refusing
    for want of an engage in this process would strand an operator whose arm was energized by
    something else, and this is the step whose whole content is them taking its weight.

    Args:
        config: This session's config.

    Returns:
        (str) The recorded line naming the ids the drop addressed.

    Raises:
        SessionRefusedError: While no single writer exists, or if the assembly refused. Nothing
            is energized in either case, so there is nothing to release.
    """
    global _LIVE_SESSION

    _require_torque_write_path("release")
    live = _LIVE_SESSION
    if live is None:
        return _release_a_session_this_process_did_not_engage(config)

    _LIVE_SESSION = None
    live.maintainer.stop()
    try:
        dropped = live.guarded.disengage(arm_supported=ARM_SUPPORTED_BY_TIMETABLE)
    finally:
        live.rig.close()
    ids = " ".join(f"{send_id:#04x}" for send_id in dropped)
    line = f"{ids} 토크 해제, 유지 틱 {live.maintainer.ticks}회"
    if live.maintainer.failure is not None:
        # The loop died before the release reached it, so the arm was unrefreshed for some part
        # of the session. The drop still happened and the operator still has the weight; what
        # they need is to know the hold was not being sent.
        return f"{line}; 유지 루프가 먼저 죽었다: {live.maintainer.failure}"
    return line


def _release_a_session_this_process_did_not_engage(config: SessionConfig) -> str:
    """Assemble the rig and drop torque on the fitted motors, having engaged nothing.

    Args:
        config: This session's config.

    Returns:
        (str) The recorded line naming the ids the drop addressed.

    Raises:
        SessionRefusedError: If the write path cannot be assembled.
    """
    from backend.torque_bringup import GuardedTorqueOn

    end_effectors = _end_effector_record()
    rig_session = _assemble_rig("release", end_effectors)
    try:
        guarded = GuardedTorqueOn(
            rig_session.rig.for_side(config.arm),
            end_effectors.for_side(config.arm),
            _preflight_report(config, rig_session.interfaces[config.arm], rig_session.locks),
            _startup_manifest(config),
        )
        dropped = guarded.disengage(arm_supported=ARM_SUPPORTED_BY_TIMETABLE)
    finally:
        rig_session.close()
    ids = " ".join(f"{send_id:#04x}" for send_id in dropped)
    return f"{ids} 토크 해제 (이 프로세스가 인게이지한 적은 없다)"


def _produce_engage(config: SessionConfig) -> Measurement:
    """Guarded torque-ON: read the present pose, hold it, record the engage.

    The order is `GuardedTorqueOn.engage`'s and not this function's: authorize against both
    gates, prove the stop path cuts no torque, read the fitted motors' present pose, build the
    kp>0 hold, drive the whole write path once with torque still off and compare what the writer
    emitted against what the enforcement point decided, then 0xFC — and compare the frame after
    it too. Nothing here can reorder that, which is the point of it living there.

    What this adds is what happens next: the hold is re-sent from its own thread until the
    release step, because past the RID-9 no-send ceiling the motor stops applying the last MIT
    command and this arm has no brake.

    Args:
        config: This session's config.

    Returns:
        (Measurement) The engage capture, sourced from the rig.

    Raises:
        SessionRefusedError: If the write path is unassembled, if the manifest is missing, if
            the record declares a motor this bench does not have, or if the assembly refused.
    """
    global _LIVE_SESSION

    from backend.actuation.config import RID9_NO_SEND_MARGIN_SEC
    from backend.torque_bringup import GuardedTorqueOn
    from backend.torque_bringup.rig import fitted_motor_names

    _require_torque_write_path("engage")
    # Both halves of the write path are asked before anything else, because everything after
    # this reads the operator's persisted state and then opens two sockets. A refusal that lands
    # after the channels are held has already told the operator the session is going ahead.
    _require_bimanual_writer("engage")
    end_effectors = _end_effector_record()
    manifest = _startup_manifest(config)
    profile = end_effectors.for_side(config.arm)
    rig_session = _assemble_rig("engage", end_effectors)
    maintainer = HoldMaintainer(rig_session.rig, RID9_NO_SEND_MARGIN_SEC / HOLD_REFRESH_DIVISOR)
    guarded = GuardedTorqueOn(
        rig_session.rig.for_side(config.arm),
        profile,
        _preflight_report(config, rig_session.interfaces[config.arm], rig_session.locks),
        manifest,
    )
    # Recorded before the engage, not after it. A bus that raises once 0xFC has left leaves the
    # arm energized, and the release step has to have something to drop.
    _LIVE_SESSION = LiveTorqueSession(guarded=guarded, rig=rig_session, maintainer=maintainer)
    try:
        result = guarded.engage()
    except BaseException:
        if guarded.torque_may_be_live:
            # 0xFC left and the engage then refused what came back. The scheduler's cached hold
            # is still the pose read at assembly — where the arm is — so re-sending it keeps the
            # arm up, and the alternative is the RID-9 timeout and a fall. The release step is
            # what puts it down, with the operator holding the weight.
            maintainer.start()
        else:
            _LIVE_SESSION = None
            rig_session.close()
        raise
    maintainer.start()
    frame = _engaged_frame_for_arm(rig_session, config.arm, fitted_motor_names(profile))
    return Measurement(
        source=SOURCE_MEASURED,
        name=ENGAGE_CAPTURE_NAME,
        payload=_engage_payload(config, rig_session, result, frame),
    )


STEPS: tuple[Step, ...] = (
    Step(
        number=1,
        key="engage",
        title="가드된 토크 ON — 현재 자세 홀드",
        capture_dirname="torque_bringup",
        operator_action=(
            "두 손으로 팔을 받쳐 든다. 인게이지 시각이 지날 때까지 놓지 않는다. "
            "팔이 흔들리고 있으면 멈출 때까지 기다렸다가 세션을 다시 잡는다."
        ),
        software_action=(
            "장착 도구가 정하는 모터 id 만 읽어 현재 관절각을 얻고, 그 각도 그대로를 목표로 하는 "
            "홀드 프레임(kp>0)을 만들어 0xFC 로 인게이지한다. 자세 폭이 id 수와 다르거나 목표가 "
            "현재 자세가 아니면 프레임이 나가기 전에 거부한다."
        ),
        torque=Torque.ENGAGE,
        duration_seconds=60.0,
        hook_env_var="OPENARM_TORQUE_BRINGUP_REAL_FIXTURE",
        hook_test_path="tests/wp105",
        produce=_produce_engage,
        stage=_stage_torque_bringup,
        perform=None,
    ),
    Step(
        number=2,
        key="release",
        title="토크 OFF — 팔을 받쳐 내려놓는다",
        capture_dirname=None,
        operator_action=(
            "토크가 꺼진다. 팔을 받쳐 든 상태에서 천천히 내려놓는다 — 브레이크가 없다. "
            "그 다음은 손댈 것이 없다."
        ),
        software_action=(
            "장착 도구가 정하는 모터 id 에만 토크 해제를 보낸다. 측정하지 않는다 — 이 단계의 "
            "내용은 사람이 팔의 무게를 받는 것이고, 거기에 수치는 없다."
        ),
        torque=Torque.RELEASE,
        duration_seconds=60.0,
        hook_env_var=None,
        hook_test_path=None,
        produce=None,
        stage=None,
        perform=_release_torque,
    ),
)

STEP_BY_NUMBER = {step.number: step for step in STEPS}


# --- Admission: five gates, all fail-closed, none of them touching the motors ---


def _admit_binding(result: AdmissionResult, _config: SessionConfig) -> None:
    """Both follower roles must resolve to a CAN channel present right now."""
    from backend.config.store import default_config_directory
    from ops.hw.canbind import (
        ArmRole,
        BindingError,
        binding_path,
        check_binding,
        list_can_channels,
        load_binding,
    )

    path = binding_path(default_config_directory())
    try:
        binding = load_binding(path)
        check = check_binding(binding, tuple(list_can_channels()))
    except (BindingError, OSError) as refusal:
        result.record(False, "CAN 바인딩", str(refusal))
        return
    required = (ArmRole.FOLLOWER_LEFT, ArmRole.FOLLOWER_RIGHT)
    missing = [role.value for role in required if role not in check.resolved]
    if missing:
        result.record(
            False,
            "CAN 바인딩",
            f"{', '.join(missing)} 의 채널이 지금 없다; 어댑터 포트가 바뀌었다면 재식별한다",
        )
        return
    mapping = ", ".join(f"{role.value}={check.resolved[role]}" for role in required)
    result.record(True, "CAN 바인딩", mapping)


def _admit_calibration(result: AdmissionResult, _config: SessionConfig) -> None:
    """Both arms must carry a loadable, checksum-verified zero that survived a power cycle.

    `zero_power_cycle_verified` is required on its own terms, not only when the calibration
    also asks for a re-zero every session. Those are two separate fields and a file that turns
    the second one off does not make the first one true — reading it that way lets the
    calibration decide whether it is allowed to be unverified. An arm whose 0xFE zero was never
    watched across a power cycle engages at an angle nobody has measured.
    """
    from backend.calibration.atomic_io import calibration_path_for, load_calibration
    from backend.calibration.schema import CalibrationError
    from backend.config.store import default_config_directory

    directory = default_config_directory() / CALIBRATION_DIRNAME
    details: list[str] = []
    for arm in ARMS:
        path = calibration_path_for(directory, CALIBRATION_ROBOT_IDS[arm])
        try:
            calibration = load_calibration(path)
        except (CalibrationError, OSError, ValueError) as refusal:
            result.record(False, "영점 캘리브레이션", f"{path}: {refusal}")
            return
        if not calibration.zero_power_cycle_verified:
            result.record(
                False,
                "영점 캘리브레이션",
                f"{arm}: 전원을 껐다 켠 뒤 영점이 유지되는지 확인된 기록이 없다 "
                f"(zero_power_cycle_verified=False, require_rezero_each_session="
                f"{calibration.require_rezero_each_session}); 먼저 영점을 다시 잡고 "
                "전원 재투입 후 잔차를 확인한다",
            )
            return
        details.append(f"{arm}={calibration.checksum[:12]}")
    result.record(True, "영점 캘리브레이션", " ".join(details))


def _admit_end_effector(result: AdmissionResult, _config: SessionConfig) -> None:
    """The fitted tool decides which motor ids the session will poll, and `0x08` is not one.

    Printing the id set is not a check. What this gate decides is whether the profile the
    session is about to poll with addresses a motor this bench does not have: `0x08` answered
    0 of 20 probes on both arms, and an unanswered frame is not an error return — nobody ACKs
    it, the transmit error counter climbs, and the controller falls to ERROR-PASSIVE, taking
    the seven joints that do exist with it. The refusal lifts when a gripper is actually
    fitted and the motor probe records `0x08` answering.
    """
    from backend.endeffector import GRIPPER_SEND_ID, default_profile

    profile = default_profile()
    ids = " ".join(f"{motor_id:#04x}" for motor_id in profile.motor_send_ids)
    detail = f"{profile.tool_id}, 모터 {profile.motor_count}개: {ids}"
    if GRIPPER_SEND_ID in profile.motor_send_ids:
        result.record(
            False,
            "장착 엔드이펙터",
            f"{detail}\n"
            f"    {GRIPPER_SEND_ID:#04x} 는 이 벤치에서 20회 폴링 중 0회 응답했다. 그 id 로 "
            "프레임을 보내면 컨트롤러가 ERROR-PASSIVE 로 떨어지고 나머지 7관절까지 열화된다. "
            "그리퍼를 실제로 장착했다면 모터 프로브부터 다시 뜬다.",
        )
        return
    result.record(True, "장착 엔드이펙터", detail)


def _admit_preflight(result: AdmissionResult, config: SessionConfig) -> None:
    """The five WP-2A-09 torque-ON preconditions must all pass for the selected arm."""
    from backend.can.link import parse_link_show
    from backend.can.lock import LockManager
    from backend.can.rid.reverify import reverify_from_fixture
    from backend.config.store import default_config_directory
    from backend.endeffector import default_profile
    from backend.preflight import JogSessionPreflight, PreflightInputs, RidCrosscheck
    from contracts.plugin.config import Side
    from ops.hw.canbind import ArmRole, binding_path, check_binding, list_can_channels, load_binding
    from packages.lerobot_robot_openarm.openarm_follower_oa import build_safety_limits

    if not config.rid_capture_dir.is_dir():
        result.record(
            False,
            "토크-ON 선행조건 5건",
            f"RID 캡처 디렉터리가 없다: {config.rid_capture_dir} (PG-RID-001 실측이 먼저다)",
        )
        return

    role = ArmRole.FOLLOWER_LEFT if config.arm == ARM_LEFT else ArmRole.FOLLOWER_RIGHT
    binding = load_binding(binding_path(default_config_directory()))
    iface = check_binding(binding, tuple(list_can_channels())).resolved.get(role)
    if iface is None:
        result.record(False, "토크-ON 선행조건 5건", f"{role.value} 채널이 지금 없다")
        return

    completed = run_command(["ip", "-details", "link", "show", iface])
    link = parse_link_show(completed.stdout, iface) if completed.returncode == 0 else None

    profile = default_profile()
    evaluations = [
        evaluation
        for evaluation in reverify_from_fixture(
            config.rid_capture_dir, expected_motor_ids=profile.motor_send_ids
        )
        if evaluation.iface == iface
    ]
    if not evaluations:
        result.record(
            False, "토크-ON 선행조건 5건", f"{config.rid_capture_dir} 에 {iface} RID 덤프가 없다"
        )
        return

    manager = LockManager()
    try:
        manager.acquire_all([iface])
        # Every dump of this channel is judged, not whichever one the glob returned first. The
        # hook produces one evaluation per capture file ordered by filename, so a directory
        # holding two dumps of can0 carries two verdicts, and choosing between them by filename
        # lets a passing dump stand in for a failing one taken on the same channel.
        reports = [
            JogSessionPreflight().run(
                PreflightInputs(
                    rid=RidCrosscheck.confirmed(evaluation),
                    side=Side.LEFT if config.arm == ARM_LEFT else Side.RIGHT,
                    link=link,
                    lock_state=manager.lock_state([iface])[0],
                    clamp_canon=build_safety_limits(config.arm),
                )
            )
            for evaluation in evaluations
        ]
    finally:
        manager.release_all()
    blocking = [report for report in reports if not report.may_enable_torque]
    if blocking:
        result.record(
            False,
            "토크-ON 선행조건 5건",
            "\n".join(report.blocking_summary() for report in blocking),
        )
        return
    result.record(True, "토크-ON 선행조건 5건", reports[0].blocking_summary())


def _admit_torque_write_path(result: AdmissionResult, _config: SessionConfig) -> None:
    """The session must not ask the operator to hold the arm for steps that cannot run.

    This is the gate that stops the session before anybody puts a hand on a brakeless arm. The
    other four say the rig is ready; this one says whether the software can do anything with it.

    Both halves of the path are asked, because either one alone is not a write path: the rig
    binding turns a decision into an engage, and the single writer is what puts the frame on a
    channel. A gate that reported the binding's presence as the path would admit a session whose
    every torque step refuses, and the operator would already be holding the arm by then.
    """
    for require in (_require_torque_write_path, _require_bimanual_writer):
        try:
            require("session")
        except SessionRefusedError as refusal:
            result.record(False, "토크 쓰기 경로", str(refusal))
            return
    result.record(True, "토크 쓰기 경로", f"{TORQUE_RIG_MODULE}.{TORQUE_RIG_FACTORY} + 단일 작성자")


ADMISSION_GATES: tuple[Callable[[AdmissionResult, SessionConfig], None], ...] = (
    _admit_binding,
    _admit_calibration,
    _admit_end_effector,
    _admit_preflight,
    _admit_torque_write_path,
)


def admit(config: SessionConfig) -> AdmissionResult:
    """Run every admission gate. A gate that raises is recorded as a refusal, never as a pass."""
    result = AdmissionResult()
    for gate in ADMISSION_GATES:
        try:
            gate(result, config)
        except Exception as failure:  # noqa: BLE001 — an unexpected gate failure is a refusal
            result.record(False, gate.__name__, f"검사 자체가 실패했다: {failure}")
    return result


# --- Timetable and the detached worker ---


def torque_is_live_after(steps: tuple[Step, ...]) -> bool:
    """Whether the arm is still energized once this selection has run to its end.

    Folded over the whole selection rather than read off its last step: a selection may end on
    a step that changes nothing, and a tail of `Torque.NONE` after an engage is a timetable
    that energizes the arm and then walks away. `HOLD` counts as energizing because a hold
    presumes a torque-ON the operator was never shown, and an unshown presumption is treated
    as live rather than as nothing.

    Args:
        steps: The steps the selection resolved to, in session order.

    Returns:
        (bool) True when nothing after the last energizing step puts the torque back down.
    """
    live = False
    for step in steps:
        if step.torque in (Torque.ENGAGE, Torque.HOLD):
            live = True
        elif step.torque is Torque.RELEASE:
            live = False
    return live


def assert_session_releases_torque(steps: tuple[Step, ...]) -> None:
    """Refuse a step selection that leaves torque on when it ends.

    `Torque.RELEASE` exists on one step. A selection that finishes energized is a timetable
    that engages the arm and then stops talking, and there is no `finally` anywhere that can
    put it right, because dropping torque on a brakeless arm is a fall rather than a stop —
    `GuardedTorqueOn.disengage` refuses unless the operator has declared the arm supported, and
    that declaration only exists as a scheduled instant the operator was shown. So the release
    has to be *in the timetable*, and the only enforceable form of that is refusing the
    selection before anything is scheduled.

    Args:
        steps: The steps the selection resolved to, in session order.

    Raises:
        SessionRefusedError: If the selection ends with torque on.
    """
    if not torque_is_live_after(steps):
        return
    energizing = [step for step in steps if step.torque in (Torque.ENGAGE, Torque.HOLD)][-1]
    release = [step.number for step in STEPS if step.torque is Torque.RELEASE]
    selected = ",".join(str(step.number) for step in steps)
    raise SessionRefusedError(
        f"단계 선택 [{selected}] 은 토크가 켜진 채로 끝난다. 토크를 마지막으로 올린 단계는 "
        f"[{energizing.number}] {energizing.title} ('{energizing.torque.name}') 이고, "
        f"이 세션에서 토크를 내리는 단계는 {release} 뿐이다.\n"
        "  브레이크가 없는 팔에서 토크를 내리는 것은 정지가 아니라 낙하다. 그래서 이 러너는 "
        "끝에 해제를 몰래 붙이지 않는다 — 운영자가 팔을 받치고 있어야 하는 시각이 시간표에 "
        "찍혀 있어야 하고, 그것이 없는 선택은 예약 자체를 거부한다.\n"
        f"  해제 단계를 함께 고른다: --steps {selected},{release[-1] if release else ''}"
    )


def schedule(steps: tuple[Step, ...], start_epoch: float) -> list[tuple[Step, float]]:
    """Assign each step its absolute start instant, spaced by the operator's changeover gap."""
    plan: list[tuple[Step, float]] = []
    cursor = start_epoch
    for step in steps:
        plan.append((step, cursor))
        cursor += step.duration_seconds + STEP_GAP_SECONDS
    return plan


def render_timetable(plan: list[tuple[Step, float]]) -> str:
    """Render the whole session as absolute wall-clock instants.

    Relative time is useless to somebody holding an arm and watching a clock; every instant here
    is the time on the wall, because that is the only form of it the operator can act on.
    """
    lines = [f"지금 {_wall_clock(time.time())} — 아래 시각은 전부 벽시계다.", ""]
    for step, epoch in plan:
        lines.append(f"{_wall_clock(epoch)}  [{step.number}] {step.title}")
        lines.append(f"           토크: {step.torque.value}")
        lines.append(f"           당신: {step.operator_action}")
        lines.append(f"           SW  : {step.software_action}")
        lines.append(f"           끝  : {_wall_clock(epoch + step.duration_seconds)} 예정")
        lines.append("")
    return "\n".join(lines)


def session_dir(captures_root: Path) -> Path:
    """The directory this session's state and log live in."""
    return captures_root / SESSION_DIRNAME


def _record_step(captures_root: Path, key: str, entry: dict[str, Any]) -> None:
    """Merge one step's verdict into the state file, atomically."""
    path = session_dir(captures_root) / STATE_FILENAME
    document: dict[str, Any] = {"steps": {}}
    if path.exists():
        document = json.loads(path.read_text(encoding="utf-8"))
    document.setdefault("steps", {})[key] = entry
    _atomic_write_json(path, document)


def run_step(step: Step, config: SessionConfig) -> tuple[bool, str]:
    """Produce, judge and write one step's capture.

    Returns:
        (tuple[bool, str]) `(passed, detail)`. A refusal is a verdict, not an exception: the
        session records it and moves to the next step, so one failed step never destroys the
        captures the earlier steps already wrote.
    """
    try:
        if step.perform is not None:
            return True, step.perform(config)
        if step.produce is None:
            raise SessionRefusedError(f"{step.key}: 이 단계는 측정도 동작도 선언하지 않았다")
        measurement = step.produce(config)
        path = write_capture(step, measurement, config.captures_root)
    except SessionRefusedError as refusal:
        return False, str(refusal)
    except Exception as failure:  # noqa: BLE001 — any producer failure is this step's verdict
        return False, f"측정 실패: {failure}"
    return True, f"{path} 기록, {step.hook_test_path} 훅이 판정함"


def run_worker(steps: tuple[Step, ...], config: SessionConfig, start_epoch: float) -> int:
    """Run the scheduled steps in a detached process, waking at each step's instant.

    Ownership: this is the only process that touches the arm during a session. It re-runs the
    admission gate first, because the operator's shell returned long ago and the rig may have
    changed since — a lock taken by somebody else between scheduling and now must stop the
    session rather than be discovered mid-engage.

    Torque state is tracked across the loop, not inside a step. It is armed *before* an
    engaging step runs rather than after it passes, the same way `GuardedTorqueOn` sets
    `torque_may_be_live` before the bus call: a producer that raises after 0xFC has left leaves
    the arm energized with nothing recorded, and a session that ends in that state has to say
    so rather than exit 0.
    """
    assert_session_releases_torque(steps)
    admission = admit(config)
    print(f"[{_wall_clock(time.time())}] 워커 시작 — 선행조건 재확인", flush=True)
    print(admission.render(), flush=True)
    if not admission.ok:
        entry = {"passed": False, "detail": "워커 재확인 거부"}
        _record_step(config.captures_root, "admission", entry)
        return EXIT_REFUSED

    failures = 0
    torque_may_be_live = False
    released = False
    try:
        for step, epoch in schedule(steps, start_epoch):
            delay = epoch - time.time()
            # A release that is late is more necessary than one on time, so slip never skips
            # it. Skipping any other step costs a capture; skipping this one leaves the arm
            # energized with the operator no longer expecting it.
            if delay < -SCHEDULE_SLIP_TOLERANCE_SECONDS and step.torque is not Torque.RELEASE:
                detail = SCHEDULE_SLIP_SKIP_DETAIL.format(instant=_wall_clock(epoch), late=-delay)
                print(f"[{_wall_clock(time.time())}] [{step.number}] {detail}", flush=True)
                _record_step(config.captures_root, step.key, {"passed": False, "detail": detail})
                failures += 1
                continue
            if delay > 0:
                time.sleep(delay)
            if step.torque is Torque.ENGAGE:
                torque_may_be_live = True
            print(f"[{_wall_clock(time.time())}] [{step.number}] {step.title}", flush=True)
            passed, detail = run_step(step, config)
            mark = "통과" if passed else "거부"
            print(f"[{_wall_clock(time.time())}] [{step.number}] {mark}: {detail}", flush=True)
            _record_step(
                config.captures_root,
                step.key,
                {"passed": passed, "detail": detail, "finished_at": _wall_clock(time.time())},
            )
            if step.torque is Torque.RELEASE and passed:
                released = True
                torque_may_be_live = False
            failures += 0 if passed else 1
    finally:
        if torque_may_be_live and not released:
            print(f"[{_wall_clock(time.time())}] {TORQUE_LEFT_LIVE_DETAIL}", flush=True)
            _record_step(
                config.captures_root,
                TORQUE_STATE_KEY,
                {"passed": False, "detail": TORQUE_LEFT_LIVE_DETAIL},
            )
    return EXIT_OK if failures == 0 else EXIT_REFUSED


def spawn_worker(steps: tuple[Step, ...], config: SessionConfig, start_epoch: float) -> Path:
    """Fork the worker into its own session and return the log it writes to.

    The fork is the point of the whole design. The operator's shell prints nothing until the
    command it ran has ended, so the command that schedules must end immediately and leave the
    measurement running behind it.

    The worker's stdin is closed for the same reason the fork exists. It would otherwise
    inherit the terminal the operator is about to type their next command into, and a detached
    process reading that terminal is a question nobody can answer: the shell that would have
    displayed it has already returned. Every instruction this session has for the operator is
    in the timetable, printed before anything engages.
    """
    directory = session_dir(config.captures_root)
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / LOG_FILENAME
    argv = [
        sys.executable,
        "-m",
        "scripts.torque_session",
        "--worker",
        "--arm",
        config.arm,
        "--captures",
        str(config.captures_root),
        "--rid-capture",
        str(config.rid_capture_dir),
        "--operator",
        config.operator,
        "--steps",
        ",".join(str(step.number) for step in steps),
        "--start-epoch",
        f"{start_epoch:.3f}",
    ]
    if config.candump_path is not None:
        argv += ["--candump", str(config.candump_path)]
    if config.manifest_path is not None:
        argv += ["--manifest", str(config.manifest_path)]
    with log_path.open("a", encoding="utf-8") as log:
        subprocess.Popen(  # noqa: S603 — fixed argv, no shell, no user-supplied executable
            argv,
            cwd=str(Path(__file__).resolve().parents[1]),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return log_path


def report_status(config: SessionConfig) -> int:
    """Print what the worker has recorded and exit with the session's verdict.

    Returns:
        (int) `EXIT_OK` when every step of the session passed, `EXIT_REFUSED` when any refused,
        `EXIT_RUNNING` while the session has steps it has not reached yet, `EXIT_NO_SESSION`
        when this capture tree holds no session at all. Not-yet-green is not green, and
        never-started is not not-yet.
    """
    path = session_dir(config.captures_root) / STATE_FILENAME
    if not path.exists():
        print(f"세션 기록이 없다: {path}")
        return EXIT_NO_SESSION
    document = json.loads(path.read_text(encoding="utf-8"))
    recorded = document.get("steps", {})
    for step in STEPS:
        entry = recorded.get(step.key)
        if entry is None:
            print(f"  [ .. ] {step.number} {step.title}")
            continue
        mark = "통과" if entry.get("passed") else "거부"
        print(f"  [{mark}] {step.number} {step.title}\n         {entry.get('detail', '')}")
    # The worker also records conditions that are not steps — a refused re-admission, and the
    # arm being left energized. The second is the line the operator most needs, and printing
    # only the step table hides exactly it.
    step_keys = {step.key for step in STEPS}
    for key, entry in recorded.items():
        if key in step_keys:
            continue
        mark = "통과" if entry.get("passed") else "거부"
        print(f"  [{mark}] {key}\n         {entry.get('detail', '')}")
    if any(not entry.get("passed") for entry in recorded.values()):
        return EXIT_REFUSED
    # Completeness is counted over step keys alone. The non-step conditions are extra rows, and
    # counting them would let a session report green with a step it never reached.
    return EXIT_OK if step_keys <= recorded.keys() else EXIT_RUNNING


# --- Self-check: the layouts this runner writes must load through the hooks that read them ---


def _synthetic_torque_bringup(extra_motor: bool = False) -> Measurement:
    """The engage layout: the fitted ids and one angle each, never a wider pose."""
    from backend.endeffector import default_profile

    send_ids = list(default_profile().motor_send_ids)
    angles = [SYNTHETIC_POSE_STEP_RAD * index for index in range(len(send_ids))]
    if extra_motor:
        angles.append(SYNTHETIC_POSE_STEP_RAD * len(send_ids))
    return Measurement(
        source=SOURCE_SYNTHETIC,
        name="layout-check",
        payload={
            "host_id": "layout-check",
            "engage": {"send_ids": send_ids, "present_pose_rad": angles},
            "zero_residual": {"within_tolerance": True},
        },
    )


SYNTHETIC_BY_KEY: dict[str, Callable[[], Measurement]] = {
    "engage": _synthetic_torque_bringup,
}


def _check_layouts(report: list[tuple[bool, str]]) -> None:
    """Every capture layout this runner writes must load through the hook that reads it.

    A step that measures nothing writes no layout. It is skipped rather than reported, because
    a "layout OK" line for a step with no payload is a pass nobody earned.
    """
    for step in STEPS:
        if not step.measures:
            continue
        try:
            stage_capture(step, SYNTHETIC_BY_KEY[step.key]())
        except Exception as failure:  # noqa: BLE001 — the failure is the reported verdict
            report.append((False, f"layout/{step.key}: {failure}"))
        else:
            report.append((True, f"layout/{step.key}: {step.hook_test_path} 훅이 적재함"))


def _selfcheck_config(scratch: Path) -> SessionConfig:
    """A config pointed entirely at a throwaway directory.

    The self-check must reach no capture tree the operator owns and no real RID dump, so every
    path in it is inside the scratch directory the caller deletes.
    """
    return SessionConfig(
        arm=ARM_LEFT,
        captures_root=scratch,
        rid_capture_dir=scratch / RID_CAPTURE_DIRNAME,
        operator="selfcheck",
        candump_path=None,
    )


def _check_refusals(report: list[tuple[bool, str]]) -> None:
    """Each refusal must actually fire. A check that cannot fail is not a check."""
    scratch = Path(tempfile.mkdtemp(prefix="oa-selfcheck-"))
    try:
        engage = STEP_BY_NUMBER[1]
        synthetic = _synthetic_torque_bringup()
        try:
            write_capture(engage, synthetic, scratch)
        except SessionRefusedError as refusal:
            report.append((True, f"refuse/synthetic-into-capture-tree: {refusal!s:.60}…"))
        else:
            report.append((False, "refuse/synthetic-into-capture-tree: 합성 캡처가 그냥 쓰였다"))

        with_stop = Measurement(
            source=SOURCE_MEASURED,
            name=synthetic.name,
            payload={**synthetic.payload, STOP_LATENCY_KEY: {"samples_sec": [0.01]}},
        )
        try:
            write_capture(engage, with_stop, scratch)
        except SessionRefusedError:
            report.append((True, "refuse/stop-latency-key: 범위 밖 측정이 거부됨"))
        else:
            report.append((False, "refuse/stop-latency-key: 정지 지연 캡처가 그냥 쓰였다"))

        # A pose wider than the fitted ids is a bus that polled a motor nobody answers on.
        # Sixteen unanswered frames took both channels to ERROR-PASSIVE on this bench.
        try:
            stage_capture(engage, _synthetic_torque_bringup(extra_motor=True))
        except SessionRefusedError:
            report.append((True, "refuse/absent-motor-pose: 장착 id 보다 넓은 자세가 거부됨"))
        else:
            report.append((False, "refuse/absent-motor-pose: 없는 모터를 포함한 자세가 통과했다"))

        try:
            run_command(["sudo", "true"])
        except SessionRefusedError:
            report.append((True, "refuse/privilege-escalation: sudo 인자가 거부됨"))
        else:
            report.append((False, "refuse/privilege-escalation: sudo 가 실행됐다"))

        # A shell operator is a word boundary the same way a space is. Judged separately from
        # the bare case because a whitespace-only split passes the bare case and misses this.
        try:
            run_command(["sh", "-c", "ip link show can0;sudo ip link set can0 up"])
        except SessionRefusedError:
            report.append((True, "refuse/shell-wrapped-escalation: 셸 연산자 뒤 sudo 가 거부됨"))
        else:
            report.append((False, "refuse/shell-wrapped-escalation: 셸 안의 sudo 가 실행됐다"))

        # The gate has to be installed, and it has to reach the same verdict the rig binding
        # itself does. Both are checked, because either one alone passes while the other is
        # gone: a gate dropped from the tuple still refuses when called, and a neutered
        # `_require_torque_write_path` still leaves the tuple full.
        if _admit_torque_write_path in ADMISSION_GATES:
            report.append((True, "gate/torque-write-path: 승인 게이트 목록에 걸려 있다"))
        else:
            report.append((False, "gate/torque-write-path: 승인 게이트 목록에서 빠졌다"))

        # The gate's verdict has to be the conjunction of both halves of the path, not either
        # one. Comparing it against the rig binding alone is what let a gate pass while every
        # torque step refused for want of the single writer.
        assembled = torque_rig_factory() is not None and BIMANUAL_CAN_WRITER is not None
        verdict = AdmissionResult()
        _admit_torque_write_path(verdict, _selfcheck_config(scratch))
        if verdict.ok is assembled:
            state = "조립됨" if verdict.ok else "미조립"
            report.append(
                (True, f"refuse/torque-write-path: 게이트 판정이 쓰기 경로 상태와 같다 ({state})")
            )
        else:
            report.append(
                (
                    False,
                    "refuse/torque-write-path: 게이트가 "
                    f"{'통과' if verdict.ok else '거부'} 라고 했지만 "
                    f"{TORQUE_RIG_MODULE}.{TORQUE_RIG_FACTORY} 는 "
                    f"{'있다' if torque_rig_factory() is not None else '없다'}, "
                    f"단일 작성자는 {'있다' if BIMANUAL_CAN_WRITER is not None else '없다'}",
                )
            )

        try:
            assert_session_releases_torque((STEP_BY_NUMBER[1],))
        except SessionRefusedError:
            report.append(
                (True, "refuse/unreleased-selection: 토크가 켜진 채 끝나는 선택이 거부됨")
            )
        else:
            report.append((False, "refuse/unreleased-selection: 해제 없는 선택이 예약됐다"))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def run_self_check() -> int:
    """Judge this runner's own layout knowledge and its refusals, by exit code."""
    report: list[tuple[bool, str]] = []
    _check_layouts(report)
    _check_refusals(report)
    for passed, line in report:
        print(f"  {'[통과]' if passed else '[실패]'} {line}")
    failed = [line for passed, line in report if not passed]
    if failed:
        print(f"\n자체 검사 실패 {len(failed)}건")
        return EXIT_REFUSED
    print(f"\n자체 검사 {len(report)}건 전부 통과")
    return EXIT_OK


# --- Entry point ---


def _selected_steps(raw: str | None) -> tuple[Step, ...]:
    """Resolve a `--steps`/`--step` selection to the steps to run, in session order."""
    if raw is None:
        return STEPS
    wanted = {int(token) for token in raw.split(",") if token.strip()}
    unknown = wanted - set(STEP_BY_NUMBER)
    if unknown:
        raise SystemExit(f"알 수 없는 단계 번호: {sorted(unknown)}")
    return tuple(step for step in STEPS if step.number in wanted)


def _config_from_args(args: argparse.Namespace) -> SessionConfig:
    """Build the session config, defaulting the capture tree to the operator's home."""
    captures_root = Path(args.captures) if args.captures else Path.home() / DEFAULT_CAPTURES_DIRNAME
    rid_capture = (
        Path(args.rid_capture) if args.rid_capture else captures_root / RID_CAPTURE_DIRNAME
    )
    return SessionConfig(
        arm=args.arm,
        captures_root=captures_root,
        rid_capture_dir=rid_capture,
        operator=args.operator,
        candump_path=Path(args.candump) if args.candump else None,
        manifest_path=Path(args.manifest) if args.manifest else None,
    )


def _print_plan(steps: tuple[Step, ...]) -> None:
    """Print what each step asks of the operator and of the software, running nothing."""
    for step in steps:
        print(f"[{step.number}] {step.title}")
        print(f"     토크 : {step.torque.value}")
        print(f"     당신 : {step.operator_action}")
        print(f"     SW   : {step.software_action}")
        if step.capture_dirname is None:
            print("     캡처 : 없음 — 이 단계는 측정하지 않는다")
        else:
            print(f"     캡처 : <captures>/{step.capture_dirname}/")
        if step.hook_env_var is not None:
            print(f"     훅   : {step.hook_env_var}=<dir> pytest {step.hook_test_path} -q")
        print()


def main(argv: list[str] | None = None) -> int:
    """Admit the session, print the timetable, and hand the measurement to a detached worker."""
    parser = argparse.ArgumentParser(prog="torque_session", description=__doc__)
    parser.add_argument("--arm", choices=ARMS, default=ARM_LEFT)
    parser.add_argument("--captures", default=None, help="캡처 트리 (기본 ~/openarm_captures)")
    parser.add_argument("--rid-capture", default=None, help="실측 RID 덤프 디렉터리")
    parser.add_argument("--operator", default=platform.node() or "operator")
    parser.add_argument("--candump", default=None, help="실측 candump 캡처 파일")
    parser.add_argument("--manifest", default=None, help="기동 매니페스트 JSON (PG-SAFE-001 해시)")
    parser.add_argument("--step", type=int, default=None, help="이 단계 하나만")
    parser.add_argument("--steps", default=None, help="쉼표로 나눈 단계 번호들")
    parser.add_argument("--plan", action="store_true", help="계획만 찍고 아무것도 하지 않는다")
    parser.add_argument("--check", action="store_true", help="캡처 레이아웃과 거부를 자체 검사")
    parser.add_argument(
        "--status",
        action="store_true",
        help=(
            f"워커가 남긴 판정을 읽는다 "
            f"(종료코드 {EXIT_OK}=전부 통과, {EXIT_REFUSED}=거부, {EXIT_RUNNING}=아직 진행 중, "
            f"{EXIT_NO_SESSION}=예약된 세션이 없다)"
        ),
    )
    parser.add_argument("--run", action="store_true", help="선행조건 통과 시 세션을 예약한다")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--start-epoch", type=float, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    steps = _selected_steps(args.steps if args.step is None else str(args.step))
    config = _config_from_args(args)

    if args.check:
        return run_self_check()
    if args.status:
        return report_status(config)
    try:
        assert_session_releases_torque(steps)
    except SessionRefusedError as refusal:
        print(str(refusal))
        return EXIT_REFUSED
    if args.plan:
        _print_plan(steps)
        return EXIT_OK
    if args.worker:
        start = args.start_epoch if args.start_epoch is not None else time.time()
        return run_worker(steps, config, start)

    print(f"선행조건 검사 — {config.arm} 팔, 캡처 트리 {config.captures_root}")
    admission = admit(config)
    print(admission.render())
    if not admission.ok:
        print("\n세션을 시작하지 않는다. 위의 거부를 먼저 닫는다 — 반쯤 진행하다 죽으면")
        print("운영자의 시간을 버리고 팔이 인게이지된 채로 남는다.")
        return EXIT_REFUSED
    if not args.run:
        print("\n선행조건 통과. 세션을 예약하려면 --run 을 붙인다.")
        return EXIT_OK

    start_epoch = time.time() + LEAD_SECONDS
    print()
    print(render_timetable(schedule(steps, start_epoch)))
    log_path = spawn_worker(steps, config, start_epoch)
    print("측정은 백그라운드에서 돈다. 이 명령은 여기서 끝난다.")
    print(f"  진행 기록: {log_path}")
    print("  판정 확인: ./scripts/torque_session.sh --status")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
