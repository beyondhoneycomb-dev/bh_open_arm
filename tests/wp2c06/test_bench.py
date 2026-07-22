"""The bench assembles under a trusted clock and refuses otherwise.

The bench composes the `disable_torque` precondition, the trusted-clock refusal, and the
three-stage decomposition. These check that composition: it publishes under a trusted clock,
it refuses a missing or forged clock, it refuses a reaction path that holds `disable_torque`,
and it records NFR-SAF-002/003/004 as labelled references only — never a pass line
(`02b` WP-2C-06 acceptance 2).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.reaction_bench import (
    REFERENCE_TARGETS_DECISION_NEEDED,
    ReactionLatencyRefusedError,
    ReactionSample,
    build_reaction_time_regression_artifact,
)
from backend.reaction_bench.bench import REAL_CAPTURE_BASIS, SYNTHETIC_BASIS
from backend.reaction_bench.precondition import DisableTorqueOnReactionPathError
from backend.torque_bringup import ClockProvenance
from backend.torque_bringup.constants import CLOCK_METHOD_CANDUMP_HW_TIMESTAMP


def test_artifact_assembles_under_a_trusted_clock(
    synthetic_samples: list[ReactionSample], valid_clock: ClockProvenance
) -> None:
    artifact = build_reaction_time_regression_artifact(
        samples=synthetic_samples, clock_provenance=valid_clock
    )
    assert artifact["wp_id"] == "WP-2C-06"
    assert artifact["gate"] == "PG-SAFE-001"
    assert artifact["basis"] == SYNTHETIC_BASIS
    assert artifact["no_disable_torque_precondition"]["passed"] is True
    assert artifact["clock_provenance"]["method"] == valid_clock.method
    assert set(artifact["reaction_time"]["segments"]) == {"select", "schedule", "can"}
    assert artifact["reaction_time"]["total"]["raw_samples"]


def test_missing_clock_provenance_is_refused(
    synthetic_samples: list[ReactionSample],
) -> None:
    with pytest.raises(ReactionLatencyRefusedError):
        build_reaction_time_regression_artifact(samples=synthetic_samples, clock_provenance=None)


def test_candump_forge_clock_is_refused(synthetic_samples: list[ReactionSample]) -> None:
    forged = ClockProvenance(
        method=CLOCK_METHOD_CANDUMP_HW_TIMESTAMP, offset_sec=0.0, uncertainty_sec=0.0
    )
    with pytest.raises(ReactionLatencyRefusedError):
        build_reaction_time_regression_artifact(samples=synthetic_samples, clock_provenance=forged)


def test_disable_torque_on_reaction_path_is_refused_before_measuring(
    synthetic_samples: list[ReactionSample], valid_clock: ClockProvenance, tmp_path: Path
) -> None:
    (tmp_path / "cutting_reaction.py").write_text(
        "def react(bus):\n    bus.disable_torque()\n", encoding="utf-8"
    )
    with pytest.raises(DisableTorqueOnReactionPathError):
        build_reaction_time_regression_artifact(
            samples=synthetic_samples,
            clock_provenance=valid_clock,
            reaction_path_root=tmp_path,
        )


def test_targets_are_references_never_a_pass_line(
    synthetic_samples: list[ReactionSample], valid_clock: ClockProvenance
) -> None:
    artifact = build_reaction_time_regression_artifact(
        samples=synthetic_samples, clock_provenance=valid_clock
    )
    targets = artifact["reference_targets_decision_needed"]
    assert [target["req"] for target in targets] == [
        target["req"] for target in REFERENCE_TARGETS_DECISION_NEEDED
    ]
    assert "[결정필요]" in artifact["reference_note"]
    # No verdict on the reaction time: neither the artifact nor the distribution carries a
    # pass/fail field, and no target is compared against the measured numbers.
    assert "passed" not in artifact
    assert "status" not in artifact
    assert "passed" not in artifact["reaction_time"]


def test_deferred_manifest_names_the_hook_and_awaited_inputs(
    synthetic_samples: list[ReactionSample], valid_clock: ClockProvenance
) -> None:
    artifact = build_reaction_time_regression_artifact(
        samples=synthetic_samples, clock_provenance=valid_clock
    )
    deferred = artifact["deferred"]
    assert (
        deferred["reverification_hook"] == "backend.reaction_bench.reverify.reverify_from_fixture"
    )
    assert deferred["fixture_env_var"] == "OPENARM_REACTION_BENCH_REAL_FIXTURE"
    assert deferred["awaited_inputs"], "an offline run still awaits the on-rig measurement"


def test_real_capture_basis_awaits_nothing(
    synthetic_samples: list[ReactionSample], valid_clock: ClockProvenance
) -> None:
    artifact = build_reaction_time_regression_artifact(
        samples=synthetic_samples, clock_provenance=valid_clock, basis=REAL_CAPTURE_BASIS
    )
    assert artifact["deferred"]["awaited_inputs"] == []


def test_deferred_measurement_records_no_samples(valid_clock: ClockProvenance) -> None:
    # With no real samples the distribution is empty, not fabricated.
    artifact = build_reaction_time_regression_artifact(samples=[], clock_provenance=valid_clock)
    assert artifact["reaction_time"]["sample_count"] == 0
    assert artifact["reaction_time"]["total"]["raw_samples"] == []
