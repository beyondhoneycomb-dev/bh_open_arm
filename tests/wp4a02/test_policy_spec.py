"""Policy-spec and observation-derivation units for WP-4A-02.

Two things are proved here. First, the quantile judgment is grounded in the real
installed policy configs, not a name table: `PI05Config` really maps STATE/ACTION to
QUANTILES and `SmolVLAConfig` really maps them to MEAN_STD, so the fixture's
normalization constants mirror reality (`10` FR-TRN-061's discipline applied to the
policy side). Second, the observation configuration is judged by `names`, so a
shape that outlives its names does not fool the derivation.
"""

from __future__ import annotations

import pytest

from backend.training.preflight import (
    Component,
    PolicyPreflightSpec,
    PreflightFinding,
    PreflightReport,
    Verdict,
    derive_observation_config,
    split_channel,
)
from backend.training.preflight.policy import QUANTILE_MODES
from backend.training.preflight.report import PreflightCode
from contracts.fixtures.synthetic_dataset import build_synthetic_dataset
from tests.wp4a02.fixtures import PI05_NORMALIZATION, SMOLVLA_NORMALIZATION


def test_installed_pi05_config_maps_state_action_to_quantiles() -> None:
    pytest.importorskip("torch")
    configuration_pi05 = pytest.importorskip("lerobot.policies.pi05.configuration_pi05")
    spec = PolicyPreflightSpec.from_lerobot_config("pi05", configuration_pi05.PI05Config())
    assert spec.requires_quantiles()
    assert spec.normalization_of("STATE") in QUANTILE_MODES
    assert spec.normalization_of("ACTION") in QUANTILE_MODES
    # The hermetic fixture constant must mirror the real config's STATE/ACTION modes.
    assert spec.normalization_of("STATE") == PI05_NORMALIZATION["STATE"]
    assert spec.normalization_of("ACTION") == PI05_NORMALIZATION["ACTION"]


def test_installed_smolvla_config_does_not_require_quantiles() -> None:
    pytest.importorskip("torch")
    configuration_smolvla = pytest.importorskip("lerobot.policies.smolvla.configuration_smolvla")
    spec = PolicyPreflightSpec.from_lerobot_config("smolvla", configuration_smolvla.SmolVLAConfig())
    assert not spec.requires_quantiles()
    assert spec.normalization_of("STATE") == SMOLVLA_NORMALIZATION["STATE"]


def test_requires_quantiles_on_quantile10_mode() -> None:
    spec = PolicyPreflightSpec(name="q10", normalization_modes={"STATE": "QUANTILE10"})
    assert spec.requires_quantiles()


def test_derive_observation_config_reads_full_48_layout() -> None:
    dataset = build_synthetic_dataset()
    config = derive_observation_config(dataset.info_features)
    assert config.use_velocity_and_torque is True
    assert config.state_dim == 48
    assert config.action_dim == 16
    assert config.bimanual is True
    assert len(config.names) == config.state_dim


def test_derive_judges_config_by_names_not_shape() -> None:
    # Names are position-only (16) but the shape lies at 48. The canonical judgment
    # follows the names: no `.torque`, so use_velocity_and_torque is False and
    # state_dim is the names width, not the shape.
    dataset = build_synthetic_dataset()
    info = {key: dict(body) for key, body in dataset.info_features.items()}
    info["observation.state"]["names"] = [
        n for n in info["observation.state"]["names"] if n.endswith(".pos")
    ]
    config = derive_observation_config(info)
    assert config.use_velocity_and_torque is False
    assert config.state_dim == 16
    assert config.state_dim != info["observation.state"]["shape"][0]


def test_split_channel_parses_joint_and_component() -> None:
    assert split_channel("left_joint_1.torque") == ("left_joint_1", Component.TORQUE)
    assert split_channel("right_gripper.pos") == ("right_gripper", Component.POS)
    joint, component = split_channel("frame_index")
    assert joint == "frame_index"
    assert component is None


def test_report_from_findings_derives_verdict() -> None:
    assert PreflightReport.from_findings(()).verdict is Verdict.PASS
    finding = PreflightFinding(
        code=PreflightCode.OBSERVATION_STATE_ORDER,
        channel_name="left_joint_1.pos",
        component=Component.POS,
        joint="left_joint_1",
        detail="x",
    )
    report = PreflightReport.from_findings((finding,))
    assert report.verdict is Verdict.BLOCK
    assert report.codes() == frozenset({PreflightCode.OBSERVATION_STATE_ORDER})
