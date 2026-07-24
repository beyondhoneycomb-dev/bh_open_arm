"""`expected_hz` is a `11` §2.6 lookup with provenance, never an estimate (CG-4B-04f).

`FR-INF-034` sources the expected inference frequency from the `11` §2.6 table;
`FR-TRN-004` forbids presenting an estimate as measured. The table covers GR00T only and,
among the fleet, only Jetson Orin — so (jetson_orin, groot) has a sourced 4.6 Hz ceiling
and every other pair is honestly unknown (`None`), never a borrowed lookalike figure.
`estimate_violations` is the machine proof of CG-4B-04f: across the whole fleet × policy
grid, zero presented frequencies are estimates.
"""

from __future__ import annotations

from backend.compat.deploy_matrix.expected_hz import (
    GROOT_2_6_TABLE,
    estimate_violations,
    expected_hz,
    sourced_hz_values,
)
from backend.compat.deploy_matrix.target import DeploymentTarget


def test_orin_groot_is_the_sourced_ceiling() -> None:
    """(jetson_orin, groot) resolves to 4.6 Hz with a §2.6 provenance line."""
    result = expected_hz(DeploymentTarget.JETSON_ORIN, "groot")
    assert result.hz == 4.6
    assert result.estimated is False
    assert "11 §2.6" in result.source
    assert "DiT-only" in result.source


def test_orin_ceiling_is_the_best_supported_mode() -> None:
    """The Orin ceiling is the highest-Hz Orin row (DiT-only), not the eager 2.9 Hz row."""
    orin_rows = [row.hz for row in GROOT_2_6_TABLE if row.platform == "Jetson Orin"]
    assert max(orin_rows) == 4.6
    assert expected_hz(DeploymentTarget.JETSON_ORIN, "groot").hz == max(orin_rows)


def test_nano_has_no_sourced_ceiling() -> None:
    """Jetson Nano has NO §2.6 row: the honest value is None, never Orin's 4.6.

    This is the entry that separates a faithful §2.6 lookup from the runtime guard's
    `(jetson_nano, groot): 4.6`, which §2.6 does not support.
    """
    result = expected_hz(DeploymentTarget.JETSON_NANO, "groot")
    assert result.hz is None
    assert result.estimated is False
    assert "self-bench" in result.source


def test_rtx_targets_have_no_sourced_ceiling() -> None:
    """RTX 5090/A6000 are absent from §2.6 (their lookalikes are different SKUs)."""
    for target in (DeploymentTarget.RTX_5090, DeploymentTarget.RTX_A6000):
        result = expected_hz(target, "groot")
        assert result.hz is None
        assert result.estimated is False


def test_non_groot_policy_has_no_sourced_ceiling() -> None:
    """§2.6 measures GR00T only; a non-GR00T policy has no primary latency source."""
    result = expected_hz(DeploymentTarget.JETSON_ORIN, "act")
    assert result.hz is None
    assert result.estimated is False


def test_no_estimated_frequency_across_the_fleet_grid() -> None:
    """CG-4B-04f: over every (target, policy) pair, zero presented values are estimates."""
    policies = ("smolvla", "pi0", "pi05", "act", "diffusion", "vqbet", "groot")
    pairs = tuple((target, policy) for target in DeploymentTarget for policy in policies)
    assert estimate_violations(pairs) == ()


def test_every_non_none_frequency_is_a_table_value() -> None:
    """Any Hz the lookup returns must be a value the §2.6 table actually states."""
    sourced = sourced_hz_values()
    policies = ("smolvla", "pi0", "pi05", "act", "diffusion", "vqbet", "groot")
    for target in DeploymentTarget:
        for policy in policies:
            hz = expected_hz(target, policy).hz
            assert hz is None or hz in sourced
