"""Acceptance ④ — nq/nv/nu = 19/19/17 is asserted as an asset-change tripwire."""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from sim.fkik.modelshape import (
    NQ_EXPECTED,
    NU_EXPECTED,
    NV_EXPECTED,
    ModelShapeError,
    assert_model_shape,
)
from sim.fkik.shuffle import build_canonical_model, build_shuffled_model


def test_shape_constants_are_the_frozen_triple() -> None:
    assert (NQ_EXPECTED, NV_EXPECTED, NU_EXPECTED) == (19, 19, 17)


def test_fixed_cell_has_expected_shape() -> None:
    shape = assert_model_shape(build_canonical_model())
    assert (shape.nq, shape.nv, shape.nu) == (19, 19, 17)


def test_shape_changed_model_is_rejected() -> None:
    # The shuffled twin adds a joint, so its shape moves off 19/19/17; the tripwire
    # must reject it rather than silently accept a different robot.
    changed = build_shuffled_model()
    assert changed.nq == NQ_EXPECTED + 1
    with pytest.raises(ModelShapeError):
        assert_model_shape(changed)
