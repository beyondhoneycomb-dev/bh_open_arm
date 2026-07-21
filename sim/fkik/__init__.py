"""FK<->IK round-trip regression suite (WP-0C-04).

The round trip ``q -> FK -> p -> IK -> q'`` and its EE residual, over the WP-0C-03
fixed cell and the WP-0C-02 IK adapter. Four pieces, one per contract guarantee:

- ``roundtrip`` — the residual distribution + histogram harness, no fixed threshold.
- ``shuffle`` — a qpos-order-permuted twin proving indices resolve by name.
- ``indexcheck`` — the static rejection of hard-coded state-array indices.
- ``modelshape`` — the nq/nv/nu = 19/19/17 tripwire for an asset change.
"""

from sim.fkik.indexcheck import HardcodedIndex, scan_source, scan_tree
from sim.fkik.modelshape import ModelShape, ModelShapeError, assert_model_shape
from sim.fkik.roundtrip import (
    RoundTripReport,
    RoundTripSample,
    format_histogram,
    run_distribution,
    run_round_trip,
    sample_interior_configs,
    sample_near_limit_configs,
)
from sim.fkik.shuffle import (
    build_canonical_model,
    build_shuffled_model,
    fk_by_name,
    qpos_index_of,
)

__all__ = [
    "HardcodedIndex",
    "ModelShape",
    "ModelShapeError",
    "RoundTripReport",
    "RoundTripSample",
    "assert_model_shape",
    "build_canonical_model",
    "build_shuffled_model",
    "fk_by_name",
    "format_histogram",
    "qpos_index_of",
    "run_distribution",
    "run_round_trip",
    "sample_interior_configs",
    "sample_near_limit_configs",
    "scan_source",
    "scan_tree",
]
