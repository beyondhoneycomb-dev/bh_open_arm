"""The artifact assembles from the two surviving checks, and refuses when either fails.

The bench composes the `disable_torque` refusal and the path-shape anchor refusal. These
check that composition: it publishes when both hold, it refuses a reaction path that cuts
torque, and it publishes no reaction time while saying in the artifact itself why there is
none — an absent number that explains itself cannot be mistaken for a number nobody
produced.

The key set is checked as an allowlist, not as a denylist of names that must be absent: a
denylist lets any new name through, and the name this rig must never carry is a reaction
time. `ethtool -T` reports no transmit hardware timestamping and no PTP clock, so any figure
in a time or rate unit here would be a rig fact nobody observed — which is why the figure
sweep covers every unit rather than milliseconds alone, and covers every field including
`no_latency_reason`. That field is checked for the claims it has to carry, too; a field
compared only against its own constant says whatever the constant was last edited to say.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.reaction_bench import NO_LATENCY_REASON, build_reaction_path_artifact
from backend.reaction_bench.precondition import DisableTorqueOnReactionPathError

# Every key the artifact may carry, at each level. Anything outside these sets is published
# to a reader as a reaction-path fact, so the set is stated here and compared for equality.
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

# Every way a duration or a rate gets written, abbreviated or spelled out. An abbreviation-only
# pattern leaves `12 milliseconds` and `480 frames per second` publishing cleanly, which is the
# same fabricated rig fact wearing a longer word. The trailing lookahead is what keeps `4 stages`
# from reading as four seconds. Spelled forms come first so they win over the shorter alternatives.
_DURATION_OR_RATE_UNIT = (
    r"(?:nano|micro|milli)?seconds?"
    r"|minutes?"
    r"|(?:kilo|mega)?hertz"
    r"|frames?\s+per\s+second"
    r"|fps"
    r"|ns|µs|μs|us|ms|min|s"
    r"|kHz|MHz|Hz"
)
TIME_OR_RATE_FIGURE = re.compile(rf"\d+(?:\.\d+)?\s*(?:{_DURATION_OR_RATE_UNIT})(?![A-Za-z])")

# The only fields of the artifact that may hold a number. This package judges no quantity,
# so it counts declared things and publishes nothing else numeric; a number under any other
# name is a measurement, and the one this rig cannot take is a reaction time.
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
    artifact = build_reaction_path_artifact()
    assert artifact["wp_id"] == "WP-2C-06"
    assert artifact["no_disable_torque_precondition"]["passed"] is True
    assert artifact["path_shape"]["stage_count"] == 3
    assert [stage["segment"] for stage in artifact["path_shape"]["stages"]] == [
        "select",
        "schedule",
        "can",
    ]


def test_disable_torque_on_reaction_path_is_refused(tmp_path: Path) -> None:
    (tmp_path / "cutting_reaction.py").write_text(
        "def react(bus):\n    bus.disable_torque()\n", encoding="utf-8"
    )
    with pytest.raises(DisableTorqueOnReactionPathError):
        build_reaction_path_artifact(reaction_path_root=tmp_path)


def test_artifact_carries_exactly_the_declared_keys() -> None:
    artifact = build_reaction_path_artifact()
    assert set(artifact) == ARTIFACT_KEYS
    assert set(artifact["no_disable_torque_precondition"]) == PRECONDITION_KEYS
    assert set(artifact["path_shape"]) == PATH_SHAPE_KEYS
    for stage in artifact["path_shape"]["stages"]:
        assert set(stage) == STAGE_KEYS


def test_artifact_holds_no_number_but_the_declared_counts() -> None:
    artifact = build_reaction_path_artifact()
    assert {key for key, _ in _numeric_fields(artifact)} == COUNT_FIELDS


def test_artifact_publishes_no_time_or_rate_figure_anywhere() -> None:
    # No end of the interval can be timestamped on this rig and no line exists to judge a
    # figure against, so no field of this artifact — the reason included — may carry one, in
    # any unit.
    artifact = build_reaction_path_artifact()
    for key, value in artifact.items():
        assert not TIME_OR_RATE_FIGURE.search(repr(value)), key
    assert artifact["path_shape"]["durations"] is None


def test_artifact_publishes_no_reaction_time_and_says_why() -> None:
    artifact = build_reaction_path_artifact()
    assert artifact["no_latency_reason"] == NO_LATENCY_REASON


def test_reason_states_that_no_reaction_time_is_published() -> None:
    assert "no reaction time is published" in NO_LATENCY_REASON


def test_reason_names_the_instrumentation_the_rig_lacks_and_cites_the_rule() -> None:
    # The two rig facts behind the descope, in the terms `ethtool -T can0` reports them,
    # plus the clause that requires them. A reason that carries none of these is not the
    # reason this package descoped on.
    assert "03 §5.7.0" in NO_LATENCY_REASON
    assert "transmit timestamping off" in NO_LATENCY_REASON
    assert "no PTP clock" in NO_LATENCY_REASON


def test_reason_claims_no_measured_reaction_time() -> None:
    # Nothing here has a line to be judged against, so the reason names no figure at all.
    assert TIME_OR_RATE_FIGURE.findall(NO_LATENCY_REASON) == []
