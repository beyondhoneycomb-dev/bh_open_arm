"""CG-4B-05a — all FR-OPS-089 (a)-(g) items plus this band's extras run through the checker.

The assertion is not merely that the run is green: it is that every one of the seven
`FR-OPS-089` items and the four extra premises is present in the executed set and was
resolved and run by `registry.env.upstream.run_facts` — the committed Wave 0-Env
checker — not by a private runner this band forked.
"""

from __future__ import annotations

from backend.compat.contract_regression import predicates, register
from registry.env import upstream

# fact_id per FR-OPS-089 item. (b)/(d)/(e) are carried by the base Wave 0-Env facts;
# (a)/(c)/(f)/(g) are this band's. The merged run must present all seven.
FR_OPS_089_ITEMS = {
    "a": "CONNECT_CALLS_SET_ZERO",
    "b": "USE_VEL_TORQUE_DEFAULT_FALSE",
    "c": "PUSH_TO_HUB_DEFAULT_TRUE",
    "d": "SIDE_REQUIRES_EXPLICIT",
    "e": "SEND_ACTION_TAU_DQ_ZERO",
    "f": "FOLLOWER_FEATURE_KEYSETS",
    "g": "FEATURE_UTILS_OBS_STATE_FLATTEN",
}

# The four extra premises 02c §2.5 assigns to this band, beyond (a)-(g). MAX_STATE_DIM
# is base; MAX_ACTION_DIM here completes the pair the policy matrix reads.
EXTRA_ITEMS = {
    "MAX_ACTION_DIM_32",
    "NORMALIZE_DENOM_STD_EPS",
    "ROLLOUT_RTC_DEFAULTS",
    "EVAL_ENV_REQUIRED",
}


def test_predicates_register_into_the_checker_resolver() -> None:
    registered = register.register_predicates()
    assert set(registered) == set(predicates.ADDITIONAL_PREDICATES)
    for name in predicates.ADDITIONAL_PREDICATES:
        # resolve() is the checker's own lookup — a name it can resolve is a name the
        # checker will execute.
        assert upstream.resolve(name) is predicates.ADDITIONAL_PREDICATES[name]


def test_all_fr_ops_089_items_and_extras_are_executed_green() -> None:
    run = register.run()
    executed = {row.fact_id for row in run.rows}

    for letter, fact_id in FR_OPS_089_ITEMS.items():
        assert fact_id in executed, f"FR-OPS-089 item ({letter}) {fact_id} not executed"
    assert executed >= EXTRA_ITEMS

    assert run.ok, run.summary()
    assert run.failed() == ()


def test_max_state_and_action_dim_pair_are_both_present() -> None:
    run = register.run()
    executed = {row.fact_id for row in run.rows}
    # The pair is complete across base (state) + this band (action); 02c §2.5.
    assert {"MAX_STATE_DIM_32", "MAX_ACTION_DIM_32"} <= executed


def test_additional_facts_do_not_restate_a_base_fact() -> None:
    # merged_facts_document refuses a duplicate fact_id; a clean merge proves this
    # band restated none of the eleven base facts.
    document = register.merged_facts_document()
    fact_ids = [fact["fact_id"] for fact in document["facts"]]
    assert len(fact_ids) == len(set(fact_ids))
    assert len(document["facts"]) == 19
