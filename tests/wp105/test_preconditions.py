"""Acceptance ①②: the four mandatory torque-ON preconditions and the manifest gate.

The manifest is where the PG-SAFE-001 PASS hash either exists or does not (`02a` §7): a
missing hash refuses startup outright. Each test clears every precondition but one, so the
refusal it asserts is attributable to exactly that precondition.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.torque_bringup import (
    GatePass,
    GatewayBypassPrecondition,
    TorqueOnManifest,
    TorqueOnRefusedError,
    ZeroResidualPrecondition,
    assert_torque_on_allowed,
)
from backend.torque_bringup.constants import PG_SAFE_001


def test_all_four_preconditions_admit_torque_on(passing_manifest: TorqueOnManifest) -> None:
    # A manifest with all four cleared does not raise: torque-ON is admitted.
    assert_torque_on_allowed(passing_manifest)


def test_missing_pg_safe_001_hash_refuses_startup(passing_manifest: TorqueOnManifest) -> None:
    # Acceptance ①: no declared PG-SAFE-001 PASS hash => startup refused.
    manifest = dataclasses.replace(
        passing_manifest,
        safe_gate=GatePass(gate_id=PG_SAFE_001, status="PASS", artifact_hash=""),
    )
    with pytest.raises(TorqueOnRefusedError, match="no PG-SAFE-001 PASS artifact hash"):
        assert_torque_on_allowed(manifest)


def test_pg_safe_001_not_pass_refuses(passing_manifest: TorqueOnManifest) -> None:
    # A declared hash but a non-PASS status is FAIL_BLOCKING and refuses.
    manifest = dataclasses.replace(
        passing_manifest,
        safe_gate=GatePass(gate_id=PG_SAFE_001, status="FAIL_BLOCKING", artifact_hash="h"),
    )
    with pytest.raises(TorqueOnRefusedError, match="not PASS"):
        assert_torque_on_allowed(manifest)


def test_pg_rid_001_not_pass_forbids_torque_on(passing_manifest: TorqueOnManifest) -> None:
    # Acceptance ②: a RID read failure (not PASS) forbids torque-ON.
    manifest = dataclasses.replace(
        passing_manifest,
        rid_gate=GatePass(gate_id="PG-RID-001", status="FAIL_BLOCKING", artifact_hash="h"),
    )
    with pytest.raises(TorqueOnRefusedError, match="RID read failure forbids torque-ON"):
        assert_torque_on_allowed(manifest)


def test_send_period_not_under_rid9_margin_refuses(passing_manifest: TorqueOnManifest) -> None:
    # Acceptance ②: the Cat-2 hold send period must stay under the RID-9 no-send margin.
    manifest = dataclasses.replace(
        passing_manifest,
        rid9_send_period_sec=passing_manifest.rid9_no_send_margin_sec,
    )
    with pytest.raises(TorqueOnRefusedError, match="RID-9 no-send margin"):
        assert_torque_on_allowed(manifest)


def test_zero_residual_out_of_tolerance_refuses(passing_manifest: TorqueOnManifest) -> None:
    # WP-1-02 residual out of tolerance is a commanded jump on power-up.
    manifest = dataclasses.replace(
        passing_manifest,
        zero_residual=ZeroResidualPrecondition(within_tolerance=False),
    )
    with pytest.raises(TorqueOnRefusedError, match="zero residual is out of tolerance"):
        assert_torque_on_allowed(manifest)


def test_gateway_bypass_refuses(passing_manifest: TorqueOnManifest) -> None:
    # WP-1-03: any bypass of the single enforcement point forbids torque-ON.
    manifest = dataclasses.replace(
        passing_manifest,
        gateway_bypass=GatewayBypassPrecondition(bypass_count=1),
    )
    with pytest.raises(TorqueOnRefusedError, match="bypass count is 1"):
        assert_torque_on_allowed(manifest)
