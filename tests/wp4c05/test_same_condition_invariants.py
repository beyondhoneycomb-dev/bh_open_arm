"""CG-4C-05a — a mismatched NOMINAL/PERTURBED set is refused at creation.

`02c` §3.5: the two conditions must share the same checkpoint hash, the same trial
count, and the same success-criterion id (`FR-TRN-073` (c)/(d)). A pair that disagrees
on any one of the three is not a controlled comparison, so `DualConditionSet.create`
refuses it rather than reporting a confounded gap. A positive control proves the guard
does not simply block every set.
"""

from __future__ import annotations

from backend.eval.protocol import Condition, ConditionSetError, DualConditionSet
from tests.wp4c05.support import arm, defined_protocol


def test_mismatched_checkpoint_hash_is_refused() -> None:
    """Different checkpoints -> set creation refused (CG-4C-05a)."""
    nominal = arm(Condition.NOMINAL, 15, 20, output_dir="/runs/a", step=1000)
    perturbed = arm(Condition.PERTURBED, 10, 20, output_dir="/runs/b", step=2000)
    try:
        DualConditionSet.create(nominal, perturbed, defined_protocol())
    except ConditionSetError as error:
        assert "checkpoint" in str(error).lower()
        return
    raise AssertionError("a checkpoint-hash mismatch must be refused (CG-4C-05a)")


def test_mismatched_trial_count_is_refused() -> None:
    """Different trial counts -> set creation refused (CG-4C-05a)."""
    nominal = arm(Condition.NOMINAL, 15, 20)
    perturbed = arm(Condition.PERTURBED, 12, 30)
    try:
        DualConditionSet.create(nominal, perturbed, defined_protocol())
    except ConditionSetError as error:
        assert "trial" in str(error).lower()
        return
    raise AssertionError("a trial-count mismatch must be refused (CG-4C-05a)")


def test_mismatched_success_criterion_is_refused() -> None:
    """Different success-criterion ids -> set creation refused (CG-4C-05a)."""
    nominal = arm(Condition.NOMINAL, 15, 20, success_criterion_id="crit-A")
    perturbed = arm(Condition.PERTURBED, 10, 20, success_criterion_id="crit-B")
    try:
        DualConditionSet.create(nominal, perturbed, defined_protocol())
    except ConditionSetError as error:
        assert "criterion" in str(error).lower()
        return
    raise AssertionError("a success-criterion mismatch must be refused (CG-4C-05a)")


def test_matched_pair_is_accepted() -> None:
    """Positive control: same checkpoint, trials, and criterion -> the set is built."""
    nominal = arm(Condition.NOMINAL, 15, 20, seed_base=0)
    perturbed = arm(Condition.PERTURBED, 10, 20, seed_base=100)
    dual = DualConditionSet.create(nominal, perturbed, defined_protocol())
    assert dual.nominal.checkpoint_hash == dual.perturbed.checkpoint_hash
    assert dual.nominal.n_trials == dual.perturbed.n_trials
    assert dual.nominal.success_criterion_id == dual.perturbed.success_criterion_id


def test_wrong_condition_in_slot_is_refused() -> None:
    """An arm in the wrong condition slot is refused — the slot names the condition."""
    perturbed_in_nominal_slot = arm(Condition.PERTURBED, 15, 20)
    try:
        DualConditionSet.create(perturbed_in_nominal_slot, None, defined_protocol())
    except ConditionSetError:
        return
    raise AssertionError("a PERTURBED arm in the nominal slot must be refused")
