"""The diagnosis: transitions, and the three failures that must never collapse into each other.

A silent node, an intermittent node and a faulted node are three different repairs — no power or
wrong id, a harness, and a motor that is answering and telling you what is wrong with it. A tool
that reported them as one number would send the operator to the wrong end of the arm.

The rate is deliberately not a threshold. A node at 99 % dropped, and a drop in one posture is a
harness fault; the transitions and the pose they happened at are the evidence, not the percentage.
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from backend.endeffector import ARM_JOINT_SEND_IDS, SIDE_LEFT
from contracts.units import Rad
from scripts import can_node_watch as watch
from scripts.can_node_watch_tests.watch_doubles import (
    INTERFACE_A,
    FakeMotor,
    FakeNodeBus,
    arm_channel,
    motors_for,
    target,
)

# The joint the operator's hand reaches, and the one whose harness is under suspicion.
SHOULDER = ARM_JOINT_SEND_IDS[0]
WRIST = ARM_JOINT_SEND_IDS[5]

# Two poses far enough apart that a drop at one and not the other is visible in the record.
FOLDED = Rad(-1.5)
EXTENDED = Rad(1.5)

DEGREES_PER_RADIAN = 57.29577951308232


def _run(channel: watch.ArmChannel, rounds: int) -> dict[str, Any]:
    """Poll a fixed number of rounds and return the record they produced."""
    for round_index in range(rounds):
        watch.poll_round([channel], at_seconds=float(round_index))
    return watch.finished_document([channel], elapsed_s=float(rounds))


def _node(document: Mapping[str, Any], send_id: int) -> dict[str, Any]:
    """One node's entry out of a recorded watch."""
    nodes: list[dict[str, Any]] = document[watch.FIELD_NODES]
    return next(node for node in nodes if node[watch.FIELD_SEND_ID] == send_id)


def test_a_bus_where_everything_answers_passes() -> None:
    """Every fitted motor, every round, normal state nibble."""
    arm = target(SIDE_LEFT, INTERFACE_A, ARM_JOINT_SEND_IDS)
    bus = FakeNodeBus(motors_for(ARM_JOINT_SEND_IDS))

    document = _run(arm_channel(arm, bus), rounds=5)

    assert watch.watch_verdict(document)[0] == watch.EXIT_OK
    assert _node(document, SHOULDER)[watch.FIELD_REPLIES] == 5


def test_a_node_that_never_answers_is_silent_not_intermittent() -> None:
    """No answer at all means the MCU is not running or is not listening on that id.

    No protection behaviour produces this symptom — a DAMIAO in trouble answers.
    """
    arm = target(SIDE_LEFT, INTERFACE_A, ARM_JOINT_SEND_IDS)
    present = tuple(send_id for send_id in ARM_JOINT_SEND_IDS if send_id != WRIST)
    bus = FakeNodeBus(motors_for(present))

    document = _run(arm_channel(arm, bus), rounds=4)

    assert watch.watch_verdict(document)[0] == watch.EXIT_REFUSED
    assert _node(document, WRIST)[watch.FIELD_REPLIES] == 0
    report = watch.render_report(document)
    assert "고정 무응답" in report
    assert "간헐" not in report


def test_a_node_that_drops_and_comes_back_is_intermittent_with_both_transitions() -> None:
    """The rate alone hides this. The transitions name it as contact rather than as a motor."""
    arm = target(SIDE_LEFT, INTERFACE_A, (SHOULDER,))
    bus = FakeNodeBus({SHOULDER: FakeMotor(SHOULDER, replies=[True, False, False, True])})

    document = _run(arm_channel(arm, bus), rounds=4)

    node = _node(document, SHOULDER)
    assert node[watch.FIELD_ATTEMPTS] == 4
    assert node[watch.FIELD_REPLIES] == 2
    kinds = [entry[watch.FIELD_KIND] for entry in node[watch.FIELD_TRANSITIONS]]
    assert kinds == [watch.TRANSITION_DROP, watch.TRANSITION_BACK]
    assert watch.watch_verdict(document)[0] == watch.EXIT_REFUSED
    assert "간헐" in watch.render_report(document)


def test_the_first_attempt_is_not_a_transition() -> None:
    """There is nothing for the first answer to have changed from.

    Counted as a transition, every node on a healthy arm would open its record with one.
    """
    arm = target(SIDE_LEFT, INTERFACE_A, (SHOULDER,))
    bus = FakeNodeBus({SHOULDER: FakeMotor(SHOULDER)})

    document = _run(arm_channel(arm, bus), rounds=3)

    assert _node(document, SHOULDER)[watch.FIELD_TRANSITION_COUNT] == 0


def test_a_drop_carries_the_posture_the_arm_was_in() -> None:
    """Harness contact depends on bending, so the pose at the drop is the diagnosis.

    Without it, "j6 dropped twice" and "j6 dropped twice, both times with the elbow folded" read
    the same, and only the second one tells the operator which length of cable to look at.
    """
    arm = target(SIDE_LEFT, INTERFACE_A, (SHOULDER, WRIST))
    shoulder = FakeMotor(SHOULDER, position=FOLDED)
    bus = FakeNodeBus({SHOULDER: shoulder, WRIST: FakeMotor(WRIST, replies=[True, False])})
    channel = arm_channel(arm, bus)

    watch.poll_round([channel], at_seconds=0.0)
    shoulder.position = EXTENDED
    watch.poll_round([channel], at_seconds=1.0)
    document = watch.finished_document([channel], elapsed_s=2.0)

    transitions = _node(document, WRIST)[watch.FIELD_TRANSITIONS]
    assert len(transitions) == 1
    drop = transitions[0]
    assert drop[watch.FIELD_AT_SECONDS] == 1.0
    assert drop[watch.FIELD_POSTURE_DEG][str(SHOULDER)] == pytest.approx(
        EXTENDED.value * DEGREES_PER_RADIAN, abs=0.1
    )


def test_a_faulted_node_is_answering_and_is_reported_apart_from_silence() -> None:
    """A DAMIAO that is overheating ANSWERS. Silence and a fault are different diagnoses.

    Rolled together, an over-temperature trip — which is a motor telling you exactly what is wrong
    — would be reported as a dead node, and the operator would go looking for a broken cable.
    """
    arm = target(SIDE_LEFT, INTERFACE_A, (SHOULDER,))
    bus = FakeNodeBus({SHOULDER: FakeMotor(SHOULDER, state=0xC)})

    document = _run(arm_channel(arm, bus), rounds=3)

    node = _node(document, SHOULDER)
    assert node[watch.FIELD_REPLIES] == 3
    assert node[watch.FIELD_FAULT_COUNTS] == {"12": 3}
    report = watch.render_report(document)
    assert "coil-over-temperature" in report
    assert "고정 무응답" not in report
    assert watch.watch_verdict(document)[0] == watch.EXIT_REFUSED


@pytest.mark.parametrize("state", [watch.STATE_DISABLED, watch.STATE_ENABLED])
def test_a_normal_state_nibble_is_not_a_fault(state: int) -> None:
    """0x0 and 0x1 are normal operation. Flagging them false-alarms on every healthy arm."""
    arm = target(SIDE_LEFT, INTERFACE_A, (SHOULDER,))
    bus = FakeNodeBus({SHOULDER: FakeMotor(SHOULDER, state=state)})

    document = _run(arm_channel(arm, bus), rounds=2)

    assert _node(document, SHOULDER)[watch.FIELD_FAULT_COUNTS] == {}
    assert watch.watch_verdict(document)[0] == watch.EXIT_OK


def test_transitions_past_the_record_cap_are_counted_and_said_so() -> None:
    """A silently truncated list reads as "that was all of them", which it was not."""
    rounds = 2 * watch.MAX_RECORDED_TRANSITIONS + 4
    arm = target(SIDE_LEFT, INTERFACE_A, (SHOULDER,))
    flapping = [index % 2 == 0 for index in range(rounds)]
    bus = FakeNodeBus({SHOULDER: FakeMotor(SHOULDER, replies=flapping)})

    document = _run(arm_channel(arm, bus), rounds=rounds)

    node = _node(document, SHOULDER)
    assert len(node[watch.FIELD_TRANSITIONS]) == watch.MAX_RECORDED_TRANSITIONS
    assert node[watch.FIELD_TRANSITION_COUNT] > watch.MAX_RECORDED_TRANSITIONS
    assert str(watch.MAX_RECORDED_TRANSITIONS) in watch.render_report(document)


def test_the_report_names_every_arm_it_watched() -> None:
    """Two arms, one record. A report that showed one of them is how half done reads as done."""
    left = arm_channel(
        target(SIDE_LEFT, INTERFACE_A, (SHOULDER,)), FakeNodeBus({SHOULDER: FakeMotor(SHOULDER)})
    )
    right = arm_channel(
        target("right", "can1", (SHOULDER,)), FakeNodeBus({SHOULDER: FakeMotor(SHOULDER)})
    )

    watch.poll_round([left, right], at_seconds=0.0)
    document = watch.finished_document([left, right], elapsed_s=1.0)

    sides = {node[watch.FIELD_SIDE] for node in document[watch.FIELD_NODES]}
    assert sides == {SIDE_LEFT, "right"}


def test_a_watch_still_running_is_not_a_pass_and_not_a_failure(tmp_path: Path) -> None:
    """ "Not finished" and "failed" want opposite responses from the operator."""
    watch.record_watch(
        tmp_path,
        {
            watch.FIELD_STATE: watch.WATCH_SCHEDULED,
            watch.FIELD_SECONDS: 120.0,
            watch.FIELD_VERDICT_AT: "21:04:30",
        },
    )

    with redirect_stdout(io.StringIO()) as printed:
        code = watch.report_status(tmp_path)

    assert code == watch.EXIT_RUNNING
    assert "21:04:30" in printed.getvalue()


def test_a_capture_tree_with_no_watch_says_so(tmp_path: Path) -> None:
    """ "Never started" and "did not finish" want opposite responses too."""
    with redirect_stdout(io.StringIO()) as printed:
        code = watch.report_status(tmp_path)

    assert code == watch.EXIT_NO_SESSION
    assert str(watch.state_path(tmp_path)) in printed.getvalue()


def test_a_refused_watch_reports_its_reason_through_status(tmp_path: Path) -> None:
    """The worker's refusal has to reach the one surface the operator reads afterwards."""
    watch.record_watch(
        tmp_path, watch.refused_document("can0 의 채널 잠금을 다른 프로세스가 쥐고 있다")
    )

    with redirect_stdout(io.StringIO()) as printed:
        code = watch.report_status(tmp_path)

    assert code == watch.EXIT_REFUSED
    assert "can0" in printed.getvalue()


def test_a_finished_watch_reports_through_status(tmp_path: Path) -> None:
    """The recorded numbers survive the round trip through the file, not just through memory."""
    arm = target(SIDE_LEFT, INTERFACE_A, (SHOULDER,))
    bus = FakeNodeBus({SHOULDER: FakeMotor(SHOULDER, replies=[True, False, True])})
    watch.record_watch(tmp_path, _run(arm_channel(arm, bus), rounds=3))

    with redirect_stdout(io.StringIO()) as printed:
        code = watch.report_status(tmp_path)

    assert code == watch.EXIT_REFUSED
    assert "간헐" in printed.getvalue()


def test_the_role_pairing_matches_the_runner_that_writes_it_and_the_one_that_reads_it() -> None:
    """A disagreement here watches the left arm and reports it under the right arm's name."""
    from scripts.canbind_session import ROLE_BY_SIDE as WRITER_ROLES
    from scripts.rig_session import ARM_ROLE_BY_SIDE as READER_ROLES

    assert watch.ROLE_BY_SIDE == WRITER_ROLES == READER_ROLES


def test_the_watch_loop_stops_at_its_deadline() -> None:
    """The window is what the operator was promised, so the loop has to end at it."""
    arm = target(SIDE_LEFT, INTERFACE_A, (SHOULDER,))
    bus = FakeNodeBus({SHOULDER: FakeMotor(SHOULDER)})
    channel = arm_channel(arm, bus)

    elapsed = watch.run_watch([channel], seconds=0.05, period_s=0.0)

    assert elapsed >= 0.05
    assert channel.watch.nodes[SHOULDER].attempts > 0
