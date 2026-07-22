"""Unit checks on the friction model and the excitation-log contract's refusals.

The model must reject a non-positive tanh slope (no knee to identify), and the log must reject a
malformed excitation rather than fit a silently wrong friction on it.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.friction import ExcitationLog, FrictionParams
from backend.friction.constants import ARM_JOINT_COUNT
from backend.friction.errors import FrictionIdentificationError


def test_friction_model_evaluates_the_tanh_law() -> None:
    params = FrictionParams(f_o=0.1, f_v=0.5, f_c=1.0, k_eff=4.0)
    tau = params.tau(np.array([0.0, 1.0, -1.0]))
    assert tau[0] == pytest.approx(0.1)  # only the offset at zero velocity
    assert tau[1] == pytest.approx(0.1 + 0.5 + np.tanh(4.0))
    assert tau[2] == pytest.approx(0.1 - 0.5 - np.tanh(4.0))


def test_non_positive_slope_is_refused() -> None:
    with pytest.raises(FrictionIdentificationError):
        FrictionParams(f_o=0.0, f_v=0.1, f_c=1.0, k_eff=0.0)


def _log(n: int) -> dict[str, np.ndarray]:
    zeros = np.zeros((n, ARM_JOINT_COUNT), dtype=np.float64)
    return {"q": zeros, "qd": zeros.copy(), "qdd": zeros.copy(), "tau": zeros.copy()}


def test_log_accepts_a_well_formed_series() -> None:
    log = ExcitationLog(**_log(10), log_freq_hz=1000.0)
    assert log.n_samples == 10


def test_log_refuses_a_wrong_joint_width() -> None:
    channels = _log(10)
    channels["qd"] = np.zeros((10, ARM_JOINT_COUNT + 1), dtype=np.float64)
    with pytest.raises(FrictionIdentificationError):
        ExcitationLog(**channels, log_freq_hz=1000.0)


def test_log_refuses_mismatched_sample_counts() -> None:
    channels = _log(10)
    channels["tau"] = np.zeros((9, ARM_JOINT_COUNT), dtype=np.float64)
    with pytest.raises(FrictionIdentificationError):
        ExcitationLog(**channels, log_freq_hz=1000.0)


def test_log_refuses_a_non_positive_rate() -> None:
    with pytest.raises(FrictionIdentificationError):
        ExcitationLog(**_log(10), log_freq_hz=0.0)
