"""The dual-condition protocol consumes committed contracts and redefines none.

`02c` DO-NOT-DUPLICATE: WP-4C-05 imports the committed WP-4C-03 `SuccessRateReport` and
its `aggregate`, and the WP-4A-05 lineage `CheckpointId`; it does not fork them. It owns
the `Condition` enum, whose value is a plain string so WP-4C-06 can data-join by value
without importing the type. This test pins those consumption facts, which also back the
declared WP-4C-03 -> WP-4C-05 reference edge (`06` §5.6 / CI-16).
"""

from __future__ import annotations

from backend.eval.protocol import Condition, aggregate_condition
from backend.eval.protocol.dual_condition import ConditionArm
from backend.eval.stats import SuccessRateReport
from backend.eval.stats.report import SuccessRateReport as StatsReport
from backend.training.lineage import CheckpointId
from tests.wp4c05.support import checkpoint, episodes_with


def test_condition_arm_wraps_the_committed_success_rate_report() -> None:
    """The arm's report IS the committed WP-4C-03 type, not a fork of it."""
    armv = aggregate_condition(
        Condition.NOMINAL,
        "rs-1",
        checkpoint(),
        episodes_with(15, 20),
        "crit-1",
    )
    assert isinstance(armv.report, SuccessRateReport)
    assert SuccessRateReport is StatsReport


def test_aggregate_condition_delegates_to_the_wp4c03_aggregator() -> None:
    """`aggregate_condition` produces the same numbers the WP-4C-03 aggregator does."""
    from backend.eval.stats import aggregate

    episodes = episodes_with(13, 20)
    direct = aggregate("rs-1", checkpoint(), episodes)
    viaprotocol = aggregate_condition(
        Condition.NOMINAL, "rs-1", checkpoint(), episodes, "crit-1"
    ).report
    assert viaprotocol.point_estimate == direct.point_estimate
    assert viaprotocol.ci_wilson_95 == direct.ci_wilson_95
    assert viaprotocol.n_trials == direct.n_trials


def test_checkpoint_identity_is_the_lineage_type() -> None:
    """The checkpoint an arm is keyed by is the WP-4A-05 lineage `CheckpointId`."""
    armv = aggregate_condition(
        Condition.NOMINAL, "rs-1", CheckpointId("/runs/z", 500), episodes_with(10, 20), "crit-1"
    )
    assert armv.report.checkpoint == CheckpointId("/runs/z", 500)


def test_condition_value_is_a_plain_string_for_the_data_join() -> None:
    """The `Condition` value is a plain string, the join key WP-4C-06 reads by value."""
    assert Condition.NOMINAL.value == "NOMINAL"
    assert Condition.PERTURBED.value == "PERTURBED"
    assert {c.value for c in Condition} == {"NOMINAL", "PERTURBED"}


def test_condition_has_exactly_two_members() -> None:
    """`Condition` has exactly the two members the interface contract fixes."""
    assert [c.name for c in Condition] == ["NOMINAL", "PERTURBED"]


def test_condition_arm_is_this_wp_type() -> None:
    """Sanity: the arm type this WP owns is the one `aggregate_condition` returns."""
    armv = aggregate_condition(
        Condition.PERTURBED, "rs-1", checkpoint(), episodes_with(8, 20), "crit-1"
    )
    assert isinstance(armv, ConditionArm)
