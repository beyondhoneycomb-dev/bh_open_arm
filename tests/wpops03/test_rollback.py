"""Acceptance ② — rollback rehearsal: pin N -> N-1 -> all gate jobs re-pass.

Rolling the committed manifest (generation 1) back to the rehearsal prior (generation 0)
must leave every pin-contract gate job green, and rolling forward again must too. The
gate runs live here (MuJoCo and the LeRobot pin are present). The negative case proves
the gate is real: a prior generation that violates the contract (a range operator) must
NOT re-pass, or "all gate jobs re-pass" would be a rubber stamp.
"""

from __future__ import annotations

from ops.versionpin.manifest import load_manifest
from ops.versionpin.rollback import gate_checks, rehearse_rollback
from tests.wpops03.conftest import load_fixture


def test_gate_checks_pass_on_committed_manifest() -> None:
    checks = gate_checks(load_manifest())
    assert {check.name for check in checks} == {
        "manifest-valid",
        "no-auto-upgrade",
        "runtime-report-complete",
        "isaac-pin-5.1/2.3.x",
    }
    assert all(check.passed for check in checks), [c for c in checks if not c.passed]


def test_rollback_rehearsal_re_passes_all_gate_jobs() -> None:
    result = rehearse_rollback(load_manifest(), load_fixture("prior_generation.yaml"))
    assert result.ok
    assert result.from_generation == 1
    assert result.to_generation == 0
    assert all(check.passed for check in result.prior_checks)
    assert all(check.passed for check in result.forward_checks)


def test_rollback_to_broken_prior_is_caught() -> None:
    # The prior generation carries a range operator; the rehearsal must fail rather
    # than rubber-stamp it — this is what makes "all gate jobs re-pass" a real gate.
    result = rehearse_rollback(load_manifest(), load_fixture("prior_generation_broken.yaml"))
    assert not result.ok
    failed = {check.name for check in result.prior_checks if not check.passed}
    assert "no-auto-upgrade" in failed


def test_rollback_rejects_a_skipped_generation() -> None:
    # A rollback that is not exactly one generation back is not a rollback.
    prior = load_fixture("prior_generation.yaml")
    prior["generation"] = -5
    result = rehearse_rollback(load_manifest(), prior)
    assert not result.ok
