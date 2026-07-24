"""The factory gates on WP-4A-05 lineage: an incomplete-lineage checkpoint cannot be served.

`FR-TRN-054`/`FR-OPS-071`: an inference engine that cannot say exactly which checkpoint it
is serving — which dataset, stats, code SHA, LeRobot version — cannot be reproduced or
audited. So `build_inference_engine` calls the committed `LineageRecord.validate()` before
it configures a backend, and a record missing an element BLOCKs (CG-4A-05a). This is the
genuine consumption of the committed lineage record, and the reason the WP-4A-05 →
WP-4A-07 dependency edge is a real static import.
"""

from __future__ import annotations

import dataclasses

import pytest

from backend.actuation import ManualClock, TargetMailbox
from backend.inference.adapter import (
    ActParams,
    InferenceBackend,
    InferenceSession,
    RtcParams,
)
from backend.inference.adapter.factory import build_inference_engine
from backend.training.lineage import LineageRecordError
from tests.wp4a07.support import FixturePolicy, make_dummy_robot, make_lineage


def _build(backend: InferenceBackend, params: object, lineage: object) -> InferenceSession:
    """Run the factory with a fresh dummy robot and the given backend/params/lineage."""
    return build_inference_engine(
        backend=backend,
        robot=make_dummy_robot(),
        mailbox=TargetMailbox(),
        clock=ManualClock(),
        policy=FixturePolicy(),
        params=params,  # type: ignore[arg-type]
        fps=30.0,
        lineage=lineage,  # type: ignore[arg-type]
    )


def test_factory_serves_a_complete_lineage() -> None:
    """A complete lineage record lets the factory build the requested backend."""
    session = _build(InferenceBackend.SYNC, ActParams(), make_lineage())
    assert session.backend is InferenceBackend.SYNC


def test_factory_refuses_incomplete_lineage() -> None:
    """A lineage record missing an element BLOCKs the engine build (CG-4A-05a)."""
    incomplete = dataclasses.replace(make_lineage(), train_config={})
    with pytest.raises(LineageRecordError):
        _build(InferenceBackend.RTC, RtcParams(), incomplete)


def test_factory_applies_input_stage_validation_after_lineage() -> None:
    """With good lineage, the factory still enforces backend param validation."""
    from backend.inference.adapter import InferenceParamError

    with pytest.raises(InferenceParamError):
        _build(InferenceBackend.RTC, RtcParams(max_guidance_weight=0.0), make_lineage())
