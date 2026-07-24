"""WP-4B-01 — the usable-policy matrix engine (`02c` §2.1, `10` FR-TRN-064/065/017).

This band builds no policy; it builds refusals. The engine promotes the Wave 0-C
policy compatibility matrix (its initial data, consumed by import) into an
enforceable gate: it reads each policy's capability from the installed LeRobot
config at runtime (`capability`), evaluates the three-axis matrix — policy x
observation config x projection — against the six FR-TRN-017 rules (`matrix`), and
renders every block with the source FR-TRN-004 requires (`verdict`). `nohardcode`
is the CG-4B-01f static check that keeps a copied ceiling out of the engine.

It owns the engine, not a copy of the 0-C matrix: the observation config (WP-4A-02),
the projection selector (WP-4A-06) and the FR-TRN-017 rules (WP-0C-07) are consumed
by import, never restated.
"""

from __future__ import annotations

from backend.compat.policy_matrix.capability import (
    POLICY_FAMILIES,
    CameraConstraint,
    PolicyCapability,
    TrainingDefaults,
    build_capability_registry,
    capability_from_class,
    crosscheck_wave0c,
    introspect_capability,
    introspect_training_defaults,
    resolve_config_class,
    wave0c_block_code,
)
from backend.compat.policy_matrix.matrix import (
    CompatibilityMatrix,
    TrainingRequest,
    build_matrix,
)
from backend.compat.policy_matrix.nohardcode import (
    HardcodedLiteral,
    forbidden_capability_values,
    scan_package,
    scan_source,
)
from backend.compat.policy_matrix.verdict import BlockingReason, CompatibilityVerdict

__all__ = [
    "POLICY_FAMILIES",
    "BlockingReason",
    "CameraConstraint",
    "CompatibilityMatrix",
    "CompatibilityVerdict",
    "HardcodedLiteral",
    "PolicyCapability",
    "TrainingDefaults",
    "TrainingRequest",
    "build_capability_registry",
    "build_matrix",
    "capability_from_class",
    "crosscheck_wave0c",
    "forbidden_capability_values",
    "introspect_capability",
    "introspect_training_defaults",
    "resolve_config_class",
    "scan_package",
    "scan_source",
    "wave0c_block_code",
]
