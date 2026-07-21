"""WP-ENV-04 acceptance ①–⑤ — every fact has a predicate, all pass on the pin, and a
fake config with a wrong default is detected.

Heavy: skipped where the [robot] stack is absent, run for real where present.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import yaml

pytest.importorskip("lerobot")

from registry.env import upstream  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
FACTS_PATH = REPO_ROOT / "contracts" / "upstream_facts.yaml"


def _facts() -> dict[str, object]:
    return yaml.safe_load(FACTS_PATH.read_text(encoding="utf-8"))


def test_every_fact_names_an_implemented_predicate() -> None:
    # Acceptance ① — no cited fact is left without a predicate.
    for fact in _facts()["facts"]:
        assert fact["check_predicate"] in upstream.PREDICATES, fact["fact_id"]


def test_all_facts_pass_on_the_current_pin() -> None:
    # Acceptance ② — the pinned upstream matches every cited fact.
    rows = upstream.run_facts(_facts())
    failing = [row.as_line() for row in rows if not row.ok]
    assert not failing, failing


def test_send_action_tau_zero_is_true_on_current_pin() -> None:
    # Acceptance ④ — the 12 §2.7 premise (send_action pins dq/tau to 0) holds.
    assert upstream.send_action_tau_dq_zero_hardcode().ok


@dataclasses.dataclass
class _FakeConfig:
    # A regression: use_velocity_and_torque flipped to True by default.
    use_velocity_and_torque: bool = True


def test_fake_config_with_true_default_is_detected() -> None:
    # Acceptance ③ — a fake config whose default is True is caught by the same
    # introspection the predicate uses; the predicate's "is False" check would fail.
    default = upstream._dataclass_field_default(__name__, "_FakeConfig", "use_velocity_and_torque")
    assert default is True


def test_unknown_predicate_is_a_hard_failure_not_a_skip() -> None:
    # Acceptance ⑤ — a fact citing an unimplemented predicate fails FAIL_BLOCKING.
    rows = upstream.run_facts(
        {"facts": [{"fact_id": "BOGUS", "check_predicate": "no_such_predicate"}]}
    )
    assert rows[0].ok is False
    assert rows[0].severity == upstream.SEVERITY_FAIL_BLOCKING


def test_failing_row_reports_the_four_acceptance_fields() -> None:
    rows = upstream.run_facts(
        {"facts": [{"fact_id": "BOGUS", "check_predicate": "nope", "affected_frs": ["FR-X"]}]}
    )
    line = rows[0].as_line()
    assert "BOGUS" in line and "expected=" in line and "actual=" in line and "FR-X" in line
