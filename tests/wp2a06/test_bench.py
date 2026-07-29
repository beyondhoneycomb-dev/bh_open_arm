"""The artifact assembles from the two surviving checks, and refuses when either fails.

The bench composes the `disable_torque` refusal and the path-shape anchor refusal. These
check that composition: it publishes when both hold, it refuses a stop path that cuts
torque, and it publishes no latency while saying in the artifact itself why there is none
— an absent number that explains itself cannot be mistaken for a number nobody produced.

The key set is checked as an allowlist rather than as the absence of the names the
measurement used to publish. A denylist of retired names lets any new name through, and the
new name this rig must never carry is a stop latency: `ethtool -T` reports no transmit
hardware timestamping and no PTP clock, so a millisecond figure here would be a rig fact
that was never observed. `no_latency_reason` is checked for the claims it has to carry for
the same reason — a field compared only against its own constant says whatever the constant
was last edited to say.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.stopbench import NO_LATENCY_REASON, build_stop_path_artifact
from backend.stopbench.precondition import DisableTorqueOnStopPathError

# Every key the artifact may carry, at each level. Anything outside these sets is published
# to a reader as a stop-path fact, so the set is stated here and compared for equality.
ARTIFACT_KEYS = {
    "wp_id",
    "generated_at",
    "no_disable_torque_precondition",
    "path_shape",
    "no_latency_reason",
}
PRECONDITION_KEYS = {
    "root",
    "symbol",
    "passed",
    "scanned_file_count",
    "reused_scan",
    "violations",
}
PATH_SHAPE_KEYS = {"stage_count", "stages", "ends_at", "durations"}
STAGE_KEYS = {"segment", "opens_at", "anchor", "owner_wp"}

# A figure in milliseconds, in the shapes a latency claim would be written in.
MILLISECOND_FIGURE = re.compile(r"\d+(?:\.\d+)?\s*ms")

# The one millisecond figure the reason is allowed to name, in the words that mark it as a
# target nobody has confirmed rather than as something this rig produced.
UNCONFIRMED_TARGET_PHRASE = "20 ms is an [unconfirmed] target"

# The only fields of the artifact that may hold a number. This package judges no quantity,
# so it counts declared things and publishes nothing else numeric; a number under any other
# name is a measurement, and the one this rig cannot take is a latency.
COUNT_FIELDS = {"stage_count", "scanned_file_count"}


def _numeric_fields(node: object, key: str = "<root>") -> Iterator[tuple[str, object]]:
    """Walk the artifact and yield every numeric leaf with the key holding it.

    Args:
        node: The artifact or a fragment of it.
        key: The key `node` was reached under.

    Returns:
        (Iterator[tuple[str, object]]) Key and value of each number, booleans excluded.
    """
    if isinstance(node, dict):
        for child_key, child in node.items():
            yield from _numeric_fields(child, child_key)
    elif isinstance(node, list):
        for child in node:
            yield from _numeric_fields(child, key)
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        yield key, node


def test_artifact_assembles_when_both_checks_hold() -> None:
    artifact = build_stop_path_artifact()
    assert artifact["wp_id"] == "WP-2A-06"
    assert artifact["no_disable_torque_precondition"]["passed"] is True
    assert artifact["path_shape"]["stage_count"] == 4
    assert [stage["segment"] for stage in artifact["path_shape"]["stages"]] == [
        "harness_event",
        "transmit",
        "scheduler",
        "can",
    ]


def test_disable_torque_on_stop_path_is_refused(tmp_path: Path) -> None:
    (tmp_path / "cutting_stop.py").write_text(
        "def stop(bus):\n    bus.disable_torque()\n", encoding="utf-8"
    )
    with pytest.raises(DisableTorqueOnStopPathError):
        build_stop_path_artifact(stop_path_root=tmp_path)


def test_artifact_carries_exactly_the_declared_keys() -> None:
    artifact = build_stop_path_artifact()
    assert set(artifact) == ARTIFACT_KEYS
    assert set(artifact["no_disable_torque_precondition"]) == PRECONDITION_KEYS
    assert set(artifact["path_shape"]) == PATH_SHAPE_KEYS
    for stage in artifact["path_shape"]["stages"]:
        assert set(stage) == STAGE_KEYS


def test_artifact_holds_no_number_but_the_declared_counts() -> None:
    artifact = build_stop_path_artifact()
    assert {key for key, _ in _numeric_fields(artifact)} == COUNT_FIELDS


def test_artifact_publishes_no_millisecond_figure_anywhere() -> None:
    # A stop latency cannot be measured on this rig at all, so the only place a millisecond
    # figure may appear is inside the reason that says so, naming the target it refuses to
    # be judged against.
    artifact = build_stop_path_artifact()
    for key, value in artifact.items():
        if key == "no_latency_reason":
            continue
        assert not MILLISECOND_FIGURE.search(repr(value)), key
    assert artifact["path_shape"]["durations"] is None


def test_artifact_publishes_no_latency_and_says_why() -> None:
    artifact = build_stop_path_artifact()
    assert artifact["no_latency_reason"] == NO_LATENCY_REASON


def test_reason_states_that_no_latency_is_published() -> None:
    assert "no stop-path latency is published" in NO_LATENCY_REASON


def test_reason_names_the_instrumentation_the_rig_lacks_and_cites_the_rule() -> None:
    # The two rig facts behind the descope, in the terms `ethtool -T can0` reports them,
    # plus the clause that requires them. A reason that carries none of these is not the
    # reason this package descoped on.
    assert "03 §5.7.0" in NO_LATENCY_REASON
    assert "transmit timestamping off" in NO_LATENCY_REASON
    assert "no PTP clock" in NO_LATENCY_REASON


def test_reason_claims_no_measured_latency() -> None:
    # The only figure permitted is the unconfirmed target, and it has to appear marked as
    # one; any second figure is a rig measurement this rig cannot take.
    assert MILLISECOND_FIGURE.findall(NO_LATENCY_REASON) == ["20 ms"]
    assert UNCONFIRMED_TARGET_PHRASE in NO_LATENCY_REASON


def test_artifact_declares_no_deferred_rig_capture() -> None:
    artifact = build_stop_path_artifact()
    # No awaited-capture manifest and no re-verification hook: nothing here is waiting on a
    # measurement the rig cannot take, which is the difference between descoped and stalled.
    assert "deferred" not in artifact
