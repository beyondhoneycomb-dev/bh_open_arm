"""USB bandwidth budget calculator and the FR-CAM-011 save/start block verdict.

The formula is `06` §2.9 verbatim: `Mbps = W × H × Bpp × 8 × fps / 1e6`. A camera's
budget is the sum over its active profiles, so a depth-on RealSense naturally counts
as two streams (FR-CAM-010). The verdict blocks a configuration when the total, or
any single controller's sum, exceeds the effective cap (FR-CAM-011).

The cap is a parameter, defaulting to the `06` NFR-CAM-004 reference figure. It is
deliberately not frozen into the comparison: `02a` WP-0B-08 ⑨ forbids nailing a
numeric target before `PG-CAM-001` runs on real cameras, so the block logic is what
is verified here, against a caller-supplied cap — not a confirmed pass line.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.camera.constants import (
    BITS_PER_BYTE,
    MEGABIT_DIVISOR,
    USB3_EFFECTIVE_CAP_MBPS_REFERENCE,
)
from backend.camera.descriptor import CameraDescriptor, CameraProfile


def profile_bandwidth_mbps(profile: CameraProfile) -> float:
    """Return one profile's uncompressed bandwidth in Mbps (`06` §2.9 formula)."""
    bits = profile.width * profile.height * profile.bpp * BITS_PER_BYTE * profile.fps
    return bits / MEGABIT_DIVISOR


def descriptor_bandwidth_mbps(descriptor: CameraDescriptor) -> float:
    """Return one camera's total bandwidth, summed over its active profiles.

    Summing profiles is what makes a depth-on RealSense cost color + depth without a
    special case (`06` FR-CAM-010).
    """
    return sum(profile_bandwidth_mbps(p) for p in descriptor.profiles)


def total_bandwidth_mbps(descriptors: Sequence[CameraDescriptor]) -> float:
    """Return the registered configuration's aggregate bandwidth."""
    return sum(descriptor_bandwidth_mbps(d) for d in descriptors)


def controller_sums_mbps(descriptors: Sequence[CameraDescriptor]) -> dict[str, float]:
    """Return per-controller bandwidth sums (`06` FR-CAM-005 shared-controller budget).

    Returns:
        (dict[str, float]) Controller id to summed bandwidth, sorted by controller.
    """
    sums: dict[str, float] = {}
    for descriptor in descriptors:
        sums[descriptor.controller] = sums.get(
            descriptor.controller, 0.0
        ) + descriptor_bandwidth_mbps(descriptor)
    return dict(sorted(sums.items()))


@dataclass(frozen=True)
class BandwidthVerdict:
    """Whether a configuration may start, and why not when it may not (FR-CAM-011).

    Attributes:
        blocked: True when save/start must be refused.
        total_mbps: Aggregate registered bandwidth.
        per_controller_mbps: Per-controller sums.
        effective_cap_mbps: The cap this verdict was rendered against.
        reasons: One human-readable line per breach; empty when not blocked.
    """

    blocked: bool
    total_mbps: float
    per_controller_mbps: dict[str, float]
    effective_cap_mbps: float
    reasons: tuple[str, ...]


def evaluate_bandwidth(
    descriptors: Sequence[CameraDescriptor],
    effective_cap_mbps: float = USB3_EFFECTIVE_CAP_MBPS_REFERENCE,
) -> BandwidthVerdict:
    """Render the save/start block verdict for a registered configuration.

    Blocks when the aggregate exceeds the cap (NFR-CAM-004 ①) or when any single
    controller's sum does (NFR-CAM-004 ②). The cap is supplied by the caller so the
    comparison, not a frozen threshold, is what carries meaning.

    Args:
        descriptors: The registered cameras.
        effective_cap_mbps: USB3 effective ceiling to compare against.

    Returns:
        (BandwidthVerdict) The block decision with its breach reasons.
    """
    total = total_bandwidth_mbps(descriptors)
    per_controller = controller_sums_mbps(descriptors)

    reasons: list[str] = []
    if total > effective_cap_mbps:
        reasons.append(
            f"aggregate {total:.1f} Mbps exceeds effective cap {effective_cap_mbps:.1f} Mbps"
        )
    for controller, controller_sum in per_controller.items():
        if controller_sum > effective_cap_mbps:
            reasons.append(
                f"controller {controller!r} sum {controller_sum:.1f} Mbps exceeds "
                f"effective cap {effective_cap_mbps:.1f} Mbps"
            )

    return BandwidthVerdict(
        blocked=bool(reasons),
        total_mbps=total,
        per_controller_mbps=per_controller,
        effective_cap_mbps=effective_cap_mbps,
        reasons=tuple(reasons),
    )
