"""The result model of a tolerant connect: one disposition per camera, plus the arm.

`06` §2.12 / §4.1 fix the shape of the answer this WP must produce. Each camera gets
a binary disposition — it OPENED, or it was SKIPPED — and a skip carries a reason and,
where a registered `OA-*` code fits, an `ErrorEnvelope` drawn from `CTR-PRIM@v1`. The
one invariant the aggregate encodes is `FR-CAM-084`: a camera's death never appears in
`blocking_failures`, so `arm_may_proceed` is structurally true no matter how many
cameras died. A USB2 fallback (`FR-CAM-003`) is a warning plus any bandwidth-exceeding
profiles refused, on a camera that still opens — it is not a skip and not an arm block.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.camera.descriptor import CameraProfile, LinkSpeed
from contracts.prim import ErrorEnvelope


class ConnectStatus(Enum):
    """Whether a camera came up. The binary `FR-CAM-084` cares about, nothing more."""

    OPENED = "opened"
    SKIPPED = "skipped"


class SkipReason(Enum):
    """Why a camera was skipped — each a tolerated, non-fatal condition (`06` §4.2)."""

    UNBOUND = "unbound"
    DISCONNECTED = "disconnected"
    OPEN_FAILED = "open_failed"
    NO_FRAME = "no_frame"


@dataclass(frozen=True)
class BlockedProfile:
    """A profile refused because it overruns the fallback link's bandwidth budget.

    The `06` §2.9 formula lives in `backend.camera.bandwidth`; this only records the
    verdict for one profile so the UI can name what a USB2 camera may not select
    (`FR-CAM-003`). The camera still opens on a profile that fits.

    Attributes:
        profile: The negotiated profile that was refused.
        required_mbps: The profile's uncompressed bandwidth.
        budget_mbps: The fallback-link budget it exceeded.
    """

    profile: CameraProfile
    required_mbps: float
    budget_mbps: float


@dataclass(frozen=True)
class CameraConnectOutcome:
    """One camera's connect disposition and everything surfaced about it.

    Attributes:
        slot: The camera's slot key (a `CTR-CAM@v1` registered camera).
        serial: The stable serial it bound to, or None when UNBOUND.
        status: OPENED or SKIPPED.
        reason: Why it was skipped, or None when it opened.
        link_speed: Negotiated link speed, or None when the camera never enumerated.
        error: A registered `OA-*` envelope for a device-side death, or None.
        warnings: Human-readable lines for conditions with no registered code
            (a USB2 fallback, a refused profile, an unbound slot).
        blocked_profiles: Profiles refused under a USB2 fallback budget.
    """

    slot: str
    serial: str | None
    status: ConnectStatus
    reason: SkipReason | None
    link_speed: LinkSpeed | None
    error: ErrorEnvelope | None
    warnings: tuple[str, ...]
    blocked_profiles: tuple[BlockedProfile, ...]

    @property
    def is_opened(self) -> bool:
        """Whether the camera came up and a live frame arrived."""
        return self.status is ConnectStatus.OPENED

    @property
    def is_skipped(self) -> bool:
        """Whether the camera was warned and skipped (never fatal to the arm)."""
        return self.status is ConnectStatus.SKIPPED

    @property
    def is_usb2_fallback(self) -> bool:
        """Whether the camera negotiated a USB2 link (`FR-CAM-003`)."""
        return self.link_speed is LinkSpeed.USB2


@dataclass(frozen=True)
class ConnectReport:
    """The whole session's connect result: per-camera outcomes and the arm verdict.

    `blocking_failures` is the mechanism behind the `FR-CAM-084` invariant: the
    tolerant connect never puts a camera condition into it, so `arm_may_proceed`
    stays true however many cameras were skipped. A test that injects a dead camera
    asserts this list is empty — which is the contract, not a tautology.

    Attributes:
        outcomes: Per-camera outcomes, one per registered camera, sorted by slot.
        blocking_failures: Non-camera reasons that would block arm connect; the
            tolerant connect contributes nothing here by construction.
    """

    outcomes: tuple[CameraConnectOutcome, ...]
    blocking_failures: tuple[str, ...]

    @property
    def arm_may_proceed(self) -> bool:
        """The tolerant-connect invariant: no camera death blocks the arm (`FR-CAM-084`)."""
        return not self.blocking_failures

    @property
    def opened(self) -> tuple[CameraConnectOutcome, ...]:
        """The cameras that came up."""
        return tuple(o for o in self.outcomes if o.is_opened)

    @property
    def skipped(self) -> tuple[CameraConnectOutcome, ...]:
        """The cameras that were warned and skipped."""
        return tuple(o for o in self.outcomes if o.is_skipped)

    @property
    def usb2_fallbacks(self) -> tuple[CameraConnectOutcome, ...]:
        """The cameras that negotiated a USB2 link (`FR-CAM-003`)."""
        return tuple(o for o in self.outcomes if o.is_usb2_fallback)

    @property
    def blocked_profiles(self) -> tuple[BlockedProfile, ...]:
        """Every profile refused across all cameras under a USB2 budget."""
        return tuple(profile for o in self.outcomes for profile in o.blocked_profiles)

    @property
    def resolved_serials(self) -> dict[str, str]:
        """The serial each opened camera bound to — stable across a re-enumeration.

        `FR-CAM-004` acceptance ②: a reboot/re-plug reshuffles enumeration order but
        not serials, so connecting twice against the same serials yields this same
        map. The binding is by serial, so the mapping is order-independent by design.
        """
        return {o.slot: o.serial for o in self.opened if o.serial is not None}

    def by_slot(self, slot: str) -> CameraConnectOutcome:
        """Return the outcome for one slot.

        Args:
            slot: The slot key to look up.

        Returns:
            (CameraConnectOutcome) That camera's outcome.

        Raises:
            KeyError: If no camera under that slot is in the report.
        """
        for outcome in self.outcomes:
            if outcome.slot == slot:
                return outcome
        raise KeyError(slot)
