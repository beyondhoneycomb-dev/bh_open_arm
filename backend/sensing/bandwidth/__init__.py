"""USB bandwidth budget block (WP-3B-02).

The public surface is the save/start block and its inputs. The bandwidth *formula*
is not re-exported here: it belongs to `backend.camera.bandwidth` (WP-0B-08) and is
imported by `budget`, so callers that need the raw arithmetic reach for that module
and this one stays the single home of the block, the topology reconciliation, and
the mitigation ladder.
"""

from __future__ import annotations

from backend.sensing.bandwidth.budget import (
    BandwidthBudgetError,
    BudgetDecision,
    enforce_budget,
    evaluate_budget,
    evaluate_budget_with_topology,
)
from backend.sensing.bandwidth.mitigation import (
    FrameTimeoutDiagnosis,
    MitigationStep,
    diagnose_frame_timeout,
    mitigation_steps,
)
from backend.sensing.bandwidth.spec import (
    spec_bandwidth_mbps,
    spec_profiles,
    spec_stream_count,
    specs_total_mbps,
)
from backend.sensing.bandwidth.topology import (
    UsbController,
    UsbDevice,
    UsbTopology,
    assign_controllers,
    parse_lsusb_tree,
)

__all__ = [
    "BandwidthBudgetError",
    "BudgetDecision",
    "FrameTimeoutDiagnosis",
    "MitigationStep",
    "UsbController",
    "UsbDevice",
    "UsbTopology",
    "assign_controllers",
    "diagnose_frame_timeout",
    "enforce_budget",
    "evaluate_budget",
    "evaluate_budget_with_topology",
    "mitigation_steps",
    "parse_lsusb_tree",
    "spec_bandwidth_mbps",
    "spec_profiles",
    "spec_stream_count",
    "specs_total_mbps",
]
