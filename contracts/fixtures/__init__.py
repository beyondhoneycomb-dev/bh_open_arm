"""WP-3A-06 fixtures — the sole target 3B builds and tests against.

`02b` §5.2 WP-3A-06: 3B touches no real hardware, so every 3B unit and integration
test runs against these fixtures. Four are deterministic stand-ins for the physical
world — a synthetic camera, a synthetic VR pose stream, a dummy robot, a synthetic
48-dim dataset — and the fifth is the contract regression checker that fails CI when
any of the six frozen 3A contracts drifts, propagating staleness from `CTR-PRIM@v1`
to its five consumers.

Every fixture is built on the frozen contracts (`CTR-PRIM`/`CAM`/`CAP`/`TEL`/`WS`/
`REC`@v1) by import and restates no primitive, so a fixture cannot silently disagree
with the contract it stands in for.
"""

from __future__ import annotations

from contracts.fixtures.contract_regression import (
    AUTHORITY_RELPATH,
    SHARED_PRIMITIVE_CONTRACT,
    RegressionReport,
    check_contract_regression,
    check_repo,
    load_locked_hashes,
    prim_consumer_contracts,
    tracked_contract_ids,
)
from contracts.fixtures.dummy_robot import DummyRobot
from contracts.fixtures.synthetic_camera import SyntheticCamera, SyntheticFrame
from contracts.fixtures.synthetic_dataset import (
    DatasetFrame,
    SyntheticDataset,
    build_synthetic_dataset,
    default_camera_specs,
)
from contracts.fixtures.vr_pose_stream import (
    SyntheticVrPoseStream,
    VrPoseSample,
    timestamp_roles,
    validity_wire_values,
)

__all__ = [
    "AUTHORITY_RELPATH",
    "SHARED_PRIMITIVE_CONTRACT",
    "DatasetFrame",
    "DummyRobot",
    "RegressionReport",
    "SyntheticCamera",
    "SyntheticDataset",
    "SyntheticFrame",
    "SyntheticVrPoseStream",
    "VrPoseSample",
    "build_synthetic_dataset",
    "check_contract_regression",
    "check_repo",
    "default_camera_specs",
    "load_locked_hashes",
    "prim_consumer_contracts",
    "timestamp_roles",
    "tracked_contract_ids",
    "validity_wire_values",
]
