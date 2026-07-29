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

What this runner refuses to do is the reason it is short. It engages nothing itself: the
guarded torque-ON sequence (`backend.torque_bringup.sequence`) drives a `TorqueEngageBus`, and
no module in this repository binds that protocol to a real `DamiaoMotorsBus`. Opening a second
write path here would put a torque frame outside the single writer the safety filter guards, so
each step that needs motion refuses by name instead. Every capture is round-tripped through its
own hook's loader before it is written, and a capture the hook refuses is never written at all.

Entry point is `scripts/torque_session.sh`, which supplies the repository root on `sys.path`.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
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

# Argument tokens that would raise this process's privileges. The runner never escalates; a
# command needing root is printed for the operator to run in their own shell.
PRIVILEGE_TOKENS = ("sudo", "pkexec", "doas", "su")

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

# `PG-STOP-001` stop-latency measurement is out of scope for this session and was descoped from
# WP-1-05 itself. Named so the writer refuses the key rather than letting another session's
# artifact settle into this tree unnoticed. The search is over the whole payload, not its top
# level: every hook here nests its numbers one or two objects deep, so a top-level-only scan
# refuses the one shape nobody would actually write.
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
        capture_dirname: Subdirectory of the capture root this step's hook reads.
        operator_action: What the human physically does, in their language.
        software_action: What this runner does while they do it.
        torque: The torque transition, announced before the step runs.
        duration_seconds: How long the step occupies the operator, for the timetable.
        hook_env_var: The environment variable that points the hook at this capture.
        hook_test_path: The pytest path that re-verifies this capture.
        produce: Returns the measurement, or raises `SessionRefusedError` naming what is missing.
        stage: Writes the payload into a directory and re-runs the hook's own loader over it.
    """

    number: int
    key: str
    title: str
    capture_dirname: str
    operator_action: str
    software_action: str
    torque: Torque
    duration_seconds: float
    hook_env_var: str
    hook_test_path: str
    produce: Callable[[SessionConfig], Measurement]
    stage: Callable[[Path], None]


@dataclass(frozen=True)
class SessionConfig:
    """Everything a step needs to know about this rig and this operator's directories.

    Attributes:
        arm: Which arm the session operates on.
        captures_root: The operator's capture tree.
        rid_capture_dir: Directory of real RID dumps the torque preflight is confirmed against.
        operator: The name recorded on the attestation a threshold calibration needs.
        candump_path: A real capture of bus traffic, or None when the operator supplied none.
    """

    arm: str
    captures_root: Path
    rid_capture_dir: Path
    operator: str
    candump_path: Path | None


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
        # Each token is split on whitespace before it is judged: `bash -c "sudo ..."` carries the
        # escalation inside one argv element, and a whole-token match walks straight past it.
        if any(Path(word).name in PRIVILEGE_TOKENS for word in token.split()):
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
    """Re-run the WP-1-05 hook, then judge the capture against this rig's fitted motor set.

    The hook's own width check compares the capture's pose against the capture's own id list,
    so a capture that consistently names an id this arm does not carry passes it. That id is
    the whole failure: motor `0x08` answered 0 of 20 polls on this bench, and sixteen
    unanswered frames walked both channels to ERROR-PASSIVE, which degrades the seven joints
    that are present. So the fitted set is compared here as well, against `default_profile()`
    rather than against anything the capture supplied.

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
        if set(verification.engage_displacement_rad) != {0.0}:
            raise SessionRefusedError(
                f"인게이지가 현재 자세를 벗어났다: {verification.engage_displacement_rad}"
            )
        if not verification.zero_residual_within_tolerance:
            raise SessionRefusedError(
                "영점 잔차가 허용범위를 벗어난 상태에서 캡처됐다. 영점이 틀린 팔의 인게이지는 "
                "아무도 측정하지 않은 각도를 목표로 잡는다 — 먼저 영점을 다시 잡는다."
            )


def _stage_safety_bringup(directory: Path) -> None:
    """Re-run the WP-1-06 publication gate over the sweep capture.

    Raises:
        SessionRefusedError: If the gate refused the sweep (multi-joint, unconstrained, or a
            command over the bootstrap limiter).
    """
    from backend.safety_bringup import reverify_from_fixture

    for verification in reverify_from_fixture(directory):
        if verification.publication is None:
            raise SessionRefusedError(f"스윕 게이트 거부: {verification.refusal}")


def _stage_threshold_calib(directory: Path) -> None:
    """Re-run the WP-2C-03 collector/proposer pipeline over the residual capture.

    Raises:
        SessionRefusedError: If the pipeline refused the capture, or the operator did not attest a
            collision-free run — an unattested run is recorded but never canon.
    """
    from backend.threshold_calib import reverify_from_fixture

    for verification in reverify_from_fixture(directory):
        if verification.calibration is None:
            raise SessionRefusedError(f"임계값 보정 거부: {verification.refusal}")
        if not verification.calibration.canonical:
            raise SessionRefusedError(
                "운영자가 무충돌을 증언하지 않아 정본이 되지 않았다; 기록만 남는다"
            )


def _stage_excitation(directory: Path) -> None:
    """Re-run the WP-2B-06 injection invariants over the session capture.

    Raises:
        SessionRefusedError: If any recorded invariant failed — the gates, the contiguity, the abort
            stopping the stream, or the resume index.
    """
    from backend.excitation.reverify import reverify_injection_sessions

    failed = [result for result in reverify_injection_sessions(directory) if not result.passed]
    if failed:
        detail = "; ".join(f"{result.check}: {result.detail}" for result in failed)
        raise SessionRefusedError(f"인젝션 불변식 실패: {detail}")


def _stage_friction(directory: Path) -> None:
    """Re-run the WP-2B-07 fit and separation over the excitation log.

    Raises:
        SessionRefusedError: If a joint's fit did not converge, or its residual did not separate.
    """
    from backend.friction import reverify_from_fixture

    for verification in reverify_from_fixture(directory):
        if not verification.all_converged:
            raise SessionRefusedError(f"{verification.capture_id}: 관절 적합이 수렴하지 않았다")
        if not verification.all_separated:
            raise SessionRefusedError(
                f"{verification.capture_id}: 분리 실패 {verification.per_joint_separated}"
            )


def _stage_rtbench(directory: Path) -> None:
    """Re-run the WP-1-04 judges over the real-CAN capture.

    Raises:
        SessionRefusedError: If the frame count was not judged from a real `candump`, or no real CAN
            bound reached `f_max`.
    """
    from backend.rtbench.frame_count import FrameCountSource
    from backend.rtbench.reverify import reverify_from_fixture

    for verification in reverify_from_fixture(directory):
        # Inert while `backend.rtbench.reverify._verify_one` labels every capture REAL_CANDUMP
        # by construction. What holds the line today is the producer refusing without `candump`
        # on PATH and a supplied capture; this fires the day the hook carries real provenance.
        if verification.pg_can_001.source is not FrameCountSource.REAL_CANDUMP:
            raise SessionRefusedError("프레임 수가 실측 candump 출처가 아니다")
        if verification.fmax.f_max_can_hz is None:
            raise SessionRefusedError("f_max_can 이 없다 (WP-0B-06 실측 필요)")


def stage_capture(step: Step, measurement: Measurement) -> None:
    """Judge a payload with its own hook in a throwaway directory.

    Nothing reaches the operator's capture tree until the hook that will later read it has
    already loaded it and agreed. A capture the hook refuses is never written, so the tree
    cannot accumulate files that only fail months later inside a pytest run.

    Raises:
        SessionRefusedError: If the hook refused the payload.
    """
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

    Args:
        node: A payload or any fragment of one.
        key: The key being searched for.

    Returns:
        (bool) True if any object anywhere under `node` carries the key.
    """
    if isinstance(node, dict):
        return key in node or any(_payload_carries_key(value, key) for value in node.values())
    if isinstance(node, list):
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
        SessionRefusedError: If the payload was not measured on the rig, if it carries the descoped
            stop-latency measurement, or if its own hook refused it.
    """
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

    Returns:
        (Callable[..., Any] | None) `build_engage_bus`, or None when the module or the factory
        is absent.
    """
    if importlib.util.find_spec(TORQUE_RIG_MODULE) is None:
        return None
    module = importlib.import_module(TORQUE_RIG_MODULE)
    factory: Callable[..., Any] | None = getattr(module, TORQUE_RIG_FACTORY, None)
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


def _produce_engage(_config: SessionConfig) -> Measurement:
    """Guarded torque-ON: read the present pose, hold it, record the engage."""
    _require_torque_write_path("engage")
    raise SessionRefusedError(
        "engage: 토크 쓰기 경로는 있으나 이 단계의 측정 코드가 아직 이 러너에 없다. "
        "합성값을 대신 넣지 않는다 — 훅은 그것을 실측으로 읽는다."
    )


def _produce_sweep(_config: SessionConfig) -> Measurement:
    """Single-joint command-following sweep under the bootstrap limiter."""
    _require_torque_write_path("sweep")
    raise SessionRefusedError(
        "sweep: 토크 쓰기 경로는 있으나 이 단계의 측정 코드가 아직 이 러너에 없다. "
        "합성값을 대신 넣지 않는다 — 훅은 그것을 실측으로 읽는다."
    )


def _produce_residual(_config: SessionConfig) -> Measurement:
    """Collision-threshold residual runs over a representative trajectory."""
    _require_torque_write_path("residual")
    raise SessionRefusedError(
        "residual: 토크 쓰기 경로는 있으나 이 단계의 측정 코드가 아직 이 러너에 없다. "
        "합성값을 대신 넣지 않는다 — 훅은 그것을 실측으로 읽는다."
    )


def _produce_excite(_config: SessionConfig) -> Measurement:
    """Exciting-trajectory injection with abort and resume-by-index."""
    _require_torque_write_path("excite")
    raise SessionRefusedError(
        "excite: 토크 쓰기 경로는 있으나 이 단계의 측정 코드가 아직 이 러너에 없다. "
        "합성값을 대신 넣지 않는다 — 훅은 그것을 실측으로 읽는다."
    )


def _produce_friction(_config: SessionConfig) -> Measurement:
    """Friction identification over the excitation logs step 4 recorded."""
    _require_torque_write_path("friction")
    raise SessionRefusedError(
        "friction: 토크 쓰기 경로는 있으나 이 단계의 측정 코드가 아직 이 러너에 없다. "
        "합성값을 대신 넣지 않는다 — 훅은 그것을 실측으로 읽는다."
    )


def _produce_rtbench(config: SessionConfig) -> Measurement:
    """Real-CAN frames-per-cycle and the band sweep, torque OFF.

    Raises:
        SessionRefusedError: When `candump` is absent from PATH or the operator supplied no capture.
            The frame count is `PG-CAN-001` pattern B and must come off the bus; a modelled
            count is the one number the gate exists to reject.
    """
    if shutil.which(CANDUMP_BINARY) is None:
        raise SessionRefusedError(
            f"rtbench: {CANDUMP_BINARY} 이 이 호스트의 PATH 에 없다 (can-utils 미설치).\n"
            f"  운영자가 자기 셸에서 실행할 명령: {CANDUMP_INSTALL_COMMAND}\n"
            "  이 러너는 sudo 를 쓰지 않는다. frames_per_cycle 은 실측 candump 에서만 나오고,\n"
            "  모델로 대신하면 PG-CAN-001 이 거르려고 존재하는 바로 그 숫자가 된다."
        )
    if config.candump_path is None:
        raise SessionRefusedError(
            "rtbench: candump 캡처가 없다. --candump 로 경로를 주거나 먼저 캡처한다:\n"
            f"  {CANDUMP_BINARY} -ta -x any > {config.captures_root}/rtbench/candump.txt"
        )
    raise SessionRefusedError(
        "rtbench: f_max_can (WP-0B-06) 실측이 없다. 밴드 스윕과 f_max_python 은 이 호스트에서 "
        "나오지만, f_max_can 은 실제 버스 대역 측정이고 그것 없이 캡처를 쓰면 훅이 거부한다."
    )


# --- The step table ---


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
    ),
    Step(
        number=2,
        key="sweep",
        title="단일 관절 명령추종 스윕 (PG-VEL-001 ⑨-a/⑨-b)",
        capture_dirname="safety_bringup",
        operator_action=(
            "스윕할 관절 하나만 남기고 나머지는 기계적으로 구속한다. 팔에서 손을 떼지 않는다. "
            "토크는 1단계에서 켜진 채로 유지된다."
        ),
        software_action=(
            "부트스트랩 리미터 아래에서만 속도를 명령하고 실측 속도를 같이 기록한다. "
            "리미터는 도출식에서 읽는다 — 캡처가 자기 천장을 올릴 수 없다."
        ),
        torque=Torque.HOLD,
        duration_seconds=180.0,
        hook_env_var="OPENARM_SAFETY_BRINGUP_REAL_FIXTURE",
        hook_test_path="tests/wp106",
        produce=_produce_sweep,
        stage=_stage_safety_bringup,
    ),
    Step(
        number=3,
        key="residual",
        title="충돌 임계값 보정 — 무충돌 잔차 수집",
        capture_dirname="threshold",
        operator_action=(
            "대표 궤적을 최소 두 번 돌리는 동안 접촉이 있었는지 눈으로 본다. "
            "끝나면 접촉이 없었는지 세션이 묻는다 — 없었을 때만 '예'라고 답한다."
        ),
        software_action=(
            "실 잔차를 모아 관절별 임계값을 제안한다. 하한은 물리에서 오고 캡처에서 오지 않으며, "
            "정본 도장은 운영자 증언에서만 나온다."
        ),
        torque=Torque.HOLD,
        duration_seconds=300.0,
        hook_env_var="OPENARM_THRESHOLD_CALIB_REAL_FIXTURE",
        hook_test_path="tests/wp2c03",
        produce=_produce_residual,
        stage=_stage_threshold_calib,
    ),
    Step(
        number=4,
        key="excite",
        title="여기 궤적 주입 (WP-2B-06)",
        capture_dirname="excitation",
        operator_action=(
            "중단 버튼에 손을 올린 채 팔의 궤적 전체를 지켜본다. 이 단계는 팔이 스스로 크게 "
            "움직이는 유일한 단계다."
        ),
        software_action=(
            "세 하드 게이트를 확인한 뒤 궤적을 인덱스 순서대로 주입한다. 중단이 걸리면 그 인덱스를 "
            "명령하기 전에 멈추고, 재개는 정확히 그 인덱스에서 시작한다."
        ),
        torque=Torque.HOLD,
        duration_seconds=240.0,
        hook_env_var="OPENARM_EXCITATION_REAL_FIXTURE",
        hook_test_path="tests/wp2b06",
        produce=_produce_excite,
        stage=_stage_excitation,
    ),
    Step(
        number=5,
        key="friction",
        title="마찰 식별 (PG-FRIC-001 증거)",
        capture_dirname="friction",
        operator_action="지켜보기만 한다. 4단계가 남긴 로그로 계산만 돈다.",
        software_action=(
            "4단계 로그로 관절별 마찰을 적합하고 잔차가 모델 신호에서 분리되는지 본다. "
            "PG-J7-001 은 이 훅이 판정하지 않는다 — 증거만 내고 판정은 인수 러너가 한다."
        ),
        torque=Torque.HOLD,
        duration_seconds=60.0,
        hook_env_var="OPENARM_FRICTION_REAL_FIXTURE",
        hook_test_path="tests/wp2b07",
        produce=_produce_friction,
        stage=_stage_friction,
    ),
    Step(
        number=6,
        key="rtbench",
        title="실시간성·CAN 측정 (PG-RT-001a / PG-CAN-001)",
        capture_dirname="rtbench",
        operator_action=(
            "토크가 꺼진다. 팔을 받쳐 든 상태에서 천천히 내려놓는다 — 브레이크가 없다. "
            "그 다음은 손댈 것이 없다."
        ),
        software_action=(
            "토크 OFF 를 확인한 읽기 전용 세션에서 밴드 오버런을 재고, 실측 candump 로 "
            "주기당 프레임 수를 센다. 프레임 수는 모델이 아니라 버스에서만 나온다."
        ),
        torque=Torque.RELEASE,
        duration_seconds=180.0,
        hook_env_var="OPENARM_RTBENCH_REAL_FIXTURE",
        hook_test_path="tests/wp104",
        produce=_produce_rtbench,
        stage=_stage_rtbench,
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
    """Both arms must carry a loadable, checksum-verified zero that survived a power cycle."""
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
        if calibration.require_rezero_each_session and not calibration.zero_power_cycle_verified:
            result.record(
                False,
                "영점 캘리브레이션",
                f"{arm}: 세션마다 재영점이 필요하다고 기록돼 있다; 먼저 영점을 다시 잡는다",
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
        report = JogSessionPreflight().run(
            PreflightInputs(
                rid=RidCrosscheck.confirmed(evaluations[0]),
                side=Side.LEFT if config.arm == ARM_LEFT else Side.RIGHT,
                link=link,
                lock_state=manager.lock_state([iface])[0],
                clamp_canon=build_safety_limits(config.arm),
            )
        )
    finally:
        manager.release_all()
    result.record(report.may_enable_torque, "토크-ON 선행조건 5건", report.blocking_summary())


def _admit_torque_write_path(result: AdmissionResult, _config: SessionConfig) -> None:
    """The session must not ask the operator to hold the arm for steps that cannot run.

    This is the gate that stops the session before anybody puts a hand on a brakeless arm. The
    other four say the rig is ready; this one says whether the software can do anything with it.
    """
    try:
        _require_torque_write_path("session")
    except SessionRefusedError as refusal:
        result.record(False, "토크 쓰기 경로", str(refusal))
        return
    result.record(True, "토크 쓰기 경로", f"{TORQUE_RIG_MODULE}.{TORQUE_RIG_FACTORY} 확인")


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


def assert_session_releases_torque(steps: tuple[Step, ...]) -> None:
    """Refuse a step selection whose last step leaves torque on.

    `Torque.RELEASE` exists on one step. A selection that ends on `ENGAGE` or `HOLD` is a
    timetable that energizes the arm and then stops talking, and there is no `finally` anywhere
    that can put it right, because dropping torque on a brakeless arm is a fall rather than a
    stop — `GuardedTorqueOn.disengage` refuses unless the operator has declared the arm
    supported, and that declaration only exists as a scheduled instant the operator was shown.
    So the release has to be *in the timetable*, and the only enforceable form of that is
    refusing the selection before anything is scheduled.

    Args:
        steps: The steps the selection resolved to, in session order.

    Raises:
        SessionRefusedError: If the selection ends with torque on.
    """
    if not steps or steps[-1].torque not in (Torque.ENGAGE, Torque.HOLD):
        return
    release = [step.number for step in STEPS if step.torque is Torque.RELEASE]
    selected = ",".join(str(step.number) for step in steps)
    raise SessionRefusedError(
        f"단계 선택 [{selected}] 은 토크가 켜진 채로 끝난다. 마지막 단계 "
        f"[{steps[-1].number}] {steps[-1].title} 의 토크는 '{steps[-1].torque.name}' 이고, "
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
                detail = f"예정 시각 {_wall_clock(epoch)} 을 {-delay:.0f}초 넘겼다; 건너뛴다"
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
    with log_path.open("a", encoding="utf-8") as log:
        subprocess.Popen(  # noqa: S603 — fixed argv, no shell, no user-supplied executable
            argv,
            cwd=str(Path(__file__).resolve().parents[1]),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return log_path


def report_status(config: SessionConfig) -> int:
    """Print what the worker has recorded and exit with the session's verdict.

    Returns:
        (int) 0 when every step of the session passed, 1 when any refused, 2 while the session
        has steps it has not reached yet. Not-yet-green is not green.
    """
    path = session_dir(config.captures_root) / STATE_FILENAME
    if not path.exists():
        print(f"세션 기록이 없다: {path}")
        return EXIT_RUNNING
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
    return EXIT_OK if len(recorded) >= len(STEPS) else EXIT_RUNNING


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


def _synthetic_safety_bringup(over_limiter: bool = False) -> Measurement:
    from backend.safety_bringup import bootstrap_limiter_rad_s

    joint_index = 2
    limiter = bootstrap_limiter_rad_s()[joint_index]
    factor = 1.1 if over_limiter else 0.5
    return Measurement(
        source=SOURCE_SYNTHETIC,
        name=f"joint{joint_index}",
        payload={
            "joint_index": joint_index,
            "single_joint": True,
            "mechanically_constrained": True,
            "samples": [
                {"commanded_rad_s": limiter * factor, "measured_rad_s": limiter * factor - 0.01}
            ],
        },
    )


def _synthetic_threshold_calib() -> Measurement:
    from backend.threshold_calib import METHOD_MAX_PLUS_SIGMA, synthetic_residual_run

    return Measurement(
        source=SOURCE_SYNTHETIC,
        name="layout-check",
        payload={
            "trajectory_id": "layout-check",
            "operator": "layout-check",
            "attested": True,
            "note": "",
            "method": METHOD_MAX_PLUS_SIGMA,
            "runs": [synthetic_residual_run(index).tolist() for index in range(3)],
        },
    )


def _synthetic_excitation() -> Measurement:
    return Measurement(
        source=SOURCE_SYNTHETIC,
        name="layout-check",
        payload={
            "torque_path_present": True,
            "dry_run_armed": True,
            "safe_state_confirmed": True,
            "segments": [
                {
                    "start_index": 0,
                    "commanded_indices": [0, 1, 2],
                    "abort": {"index": 3, "cause": "human_abort"},
                },
                {"start_index": 3, "commanded_indices": [3, 4, 5], "abort": None},
            ],
        },
    )


def _synthetic_friction() -> Measurement:
    from backend.friction import InverseDynamicsBasis, generate_synthetic_log
    from backend.gravity import Arm

    log = generate_synthetic_log(InverseDynamicsBasis(Arm.RIGHT)).log
    return Measurement(
        source=SOURCE_SYNTHETIC,
        name="layout-check",
        payload={
            "log_freq_hz": log.log_freq_hz,
            "q": log.q.tolist(),
            "qd": log.qd.tolist(),
            "qdd": log.qdd.tolist(),
            "tau": log.tau.tolist(),
        },
    )


def _synthetic_rtbench() -> Measurement:
    return Measurement(
        source=SOURCE_SYNTHETIC,
        name="layout-check",
        payload={
            "host_id": "layout-check",
            "band_overrun": [
                {"target_hz": 60.0, "overrun_rate": 0.0},
                {"target_hz": 250.0, "overrun_rate": 0.0},
            ],
            "frames_per_cycle": 32,
            "f_max_can_hz": 625.0,
            "f_max_python_hz": 500.0,
        },
    )


SYNTHETIC_BY_KEY: dict[str, Callable[[], Measurement]] = {
    "engage": _synthetic_torque_bringup,
    "sweep": _synthetic_safety_bringup,
    "residual": _synthetic_threshold_calib,
    "excite": _synthetic_excitation,
    "friction": _synthetic_friction,
    "rtbench": _synthetic_rtbench,
}


def _check_layouts(report: list[tuple[bool, str]]) -> None:
    """Every capture layout this runner writes must load through the hook that reads it."""
    for step in STEPS:
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

        try:
            stage_capture(STEP_BY_NUMBER[2], _synthetic_safety_bringup(over_limiter=True))
        except SessionRefusedError:
            report.append((True, "refuse/over-limiter-sweep: 훅이 거부한 캡처는 쓰이지 않는다"))
        else:
            report.append((False, "refuse/over-limiter-sweep: 리미터 초과 스윕이 통과했다"))

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

        # The gate has to be installed, and it has to reach the same verdict the rig binding
        # itself does. Both are checked, because either one alone passes while the other is
        # gone: a gate dropped from the tuple still refuses when called, and a neutered
        # `_require_torque_write_path` still leaves the tuple full.
        if _admit_torque_write_path in ADMISSION_GATES:
            report.append((True, "gate/torque-write-path: 승인 게이트 목록에 걸려 있다"))
        else:
            report.append((False, "gate/torque-write-path: 승인 게이트 목록에서 빠졌다"))

        verdict = AdmissionResult()
        _admit_torque_write_path(verdict, _selfcheck_config(scratch))
        if verdict.ok is (torque_rig_factory() is not None):
            state = "조립됨" if verdict.ok else "미조립"
            report.append(
                (True, f"refuse/torque-write-path: 게이트 판정이 리그 상태와 같다 ({state})")
            )
        else:
            report.append(
                (
                    False,
                    "refuse/torque-write-path: 게이트가 "
                    f"{'통과' if verdict.ok else '거부'} 라고 했지만 "
                    f"{TORQUE_RIG_MODULE}.{TORQUE_RIG_FACTORY} 는 "
                    f"{'있다' if torque_rig_factory() is not None else '없다'}",
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
    )


def _print_plan(steps: tuple[Step, ...]) -> None:
    """Print what each step asks of the operator and of the software, running nothing."""
    for step in steps:
        print(f"[{step.number}] {step.title}")
        print(f"     토크 : {step.torque.value}")
        print(f"     당신 : {step.operator_action}")
        print(f"     SW   : {step.software_action}")
        print(f"     캡처 : <captures>/{step.capture_dirname}/")
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
    parser.add_argument("--step", type=int, default=None, help="이 단계 하나만")
    parser.add_argument("--steps", default=None, help="쉼표로 나눈 단계 번호들")
    parser.add_argument("--plan", action="store_true", help="계획만 찍고 아무것도 하지 않는다")
    parser.add_argument("--check", action="store_true", help="캡처 레이아웃과 거부를 자체 검사")
    parser.add_argument("--status", action="store_true", help="워커가 남긴 판정을 읽는다")
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
