"""The WP-2C-02 detection activation gate: the single gateway for 2C real activation (SHAPE-IG).

FR-SAF-030 makes collision detection a function of one fact — PG-FRIC-001 PASS — and FR-SAF-001b
makes a detection loop that misses 1 kHz a degrade with an effective-delay display, not a silent
continuation. This module fuses both into one verdict a caller cannot route around:

  * The lock (①). While PG-FRIC-001 is not PASS the verdict is DISABLED and `activation_permitted`
    is False; `assert_can_activate` and the API-level `assert_activation_allowed` raise. On this
    host PG-FRIC-001 is hardware-deferred (real excitation logs on a torque-ON arm plus PG-J7-001,
    of which this host has neither), so the real gate is always locked here — that LOCK is what the
    tests prove; the PASS branch is exercised only with a synthetic status to check the logic, never
    to claim the gate is open.

  * The measured downgrade (②). Activation always carries a `DetectionBand` — the loop cycle-time
    measurement is a required input, never skipped — and a band that misses 1 kHz demotes the mode.
    The band math (the pattern-B 625 Hz clamp, the ≈1/f effective latency) is WP-1-06's and is
    reused from `backend.safety_bringup.band`, not re-derived.

  * No silent downgrade (③). A DEGRADED_ACCEPTED verdict is built only through `resolve_activation`,
    and its `__post_init__` refuses to exist unless it carries a speed-cap scale below 1.0 with the
    latency shown. A degrade that would display latency without lowering the cap cannot be
    constructed, so the alibi 02b §3.3 warns of has no representation.

This is the general conditional form of the same FR-SAF-030 rule WP-2B-08's `DetectionLock`
specialises: that lock is unconditional because path B is by definition the friction-unidentified
state; this gate reads the PG-FRIC-001 verdict and resolves DISABLED / ACTIVE / DEGRADED /
ARCHITECTURE_REOPEN from it, of which path-B's permanent FAIL_BLOCKING is one input value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.detection_gate.banner import (
    degraded_banner_text,
    disabled_banner_text,
    reopen_banner_text,
)
from backend.detection_gate.constants import GATE_STATE_PASS
from backend.detection_gate.errors import (
    DetectionActivationRefusedError,
    SilentDowngradeError,
)
from backend.rtbench.fmax import FMax
from backend.safety_bringup.band import DetectionBand, resolve_detection_band
from backend.safety_bringup.constants import DETECTION_LOOP_TARGET_HZ

# A fully active loop shows no banner; the other three modes each carry one. Named so the
# "banner is shown" predicate reads off intent rather than an empty-string test.
NO_BANNER = ""

# The full-rate speed cap: an un-degraded loop imposes no detection-driven downgrade, and the
# DISABLED/REOPEN states impose none either (detection is not running, so the conservative
# velocity limiter — WP-2A-04 — is what governs speed, not this gate).
FULL_SPEED_CAP_SCALE = 1.0


class DetectionActivationMode(Enum):
    """The four resolved states of the detection activation gate (02b §3.0/§3.2).

    DISABLED and ARCHITECTURE_REOPEN are locked (activation refused); ACTIVE and DEGRADED permit
    activation, the latter only with its speed cap lowered and effective delay shown.
    """

    DISABLED = "DISABLED"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    ARCHITECTURE_REOPEN = "ARCHITECTURE_REOPEN"


_LOCKED_MODES = frozenset(
    {DetectionActivationMode.DISABLED, DetectionActivationMode.ARCHITECTURE_REOPEN}
)
_PERMITTED_MODES = frozenset({DetectionActivationMode.ACTIVE, DetectionActivationMode.DEGRADED})


@dataclass(frozen=True)
class DetectionActivation:
    """One resolved activation verdict — the single object 2C real activation passes through.

    Built only by `resolve_activation` (CI-owned single-constructor property, checked by
    `staticcheck.scan_activation_construction`). `__post_init__` enforces the per-mode invariants
    so a silent downgrade cannot be represented even by a caller that tries to bypass the factory.

    Attributes:
        mode: The resolved activation mode.
        pg_fric_001_status: The PG-FRIC-001 gate-state the verdict was resolved against.
        band: The measured detection-loop bandwidth (always present — ② requires it measured).
        speed_cap_scale: The jog/teleop speed-cap fraction this state enforces. Below 1.0 only in
            DEGRADED, where it is the actual downgrade; 1.0 otherwise.
        banner: The operator banner for this mode, empty only when fully ACTIVE.
    """

    mode: DetectionActivationMode
    pg_fric_001_status: str
    band: DetectionBand
    speed_cap_scale: float
    banner: str

    def __post_init__(self) -> None:
        """Refuse any verdict that violates its mode's safety invariant.

        Raises:
            SilentDowngradeError: If a DEGRADED verdict does not lower the speed cap below 1.0 or
                shows no effective-delay banner — the silent downgrade acceptance ③ forbids.
            ValueError: If a non-DEGRADED verdict is internally inconsistent (a locked mode that
                claims activation, or an ACTIVE mode built over a degraded band).
        """
        if self.mode is DetectionActivationMode.DEGRADED:
            if not self.band.degraded:
                raise ValueError("DEGRADED activation built over a band that is not degraded")
            if not self.speed_cap_scale < FULL_SPEED_CAP_SCALE:
                raise SilentDowngradeError(
                    f"DEGRADED_ACCEPTED activation carries speed_cap_scale={self.speed_cap_scale}, "
                    "not below 1.0: a degrade that does not lower the jog/teleop speed cap is the "
                    "silent downgrade 02b §3.3 forbids (acceptance ③)"
                )
            if not self.banner:
                raise SilentDowngradeError(
                    "DEGRADED_ACCEPTED activation shows no effective-delay banner; the ≈1/f delay "
                    "must be displayed (FR-SAF-001b, acceptance ③)"
                )
            return
        if self.mode is DetectionActivationMode.ACTIVE and self.band.degraded:
            raise ValueError("ACTIVE activation built over a degraded band")
        if self.speed_cap_scale != FULL_SPEED_CAP_SCALE:
            raise ValueError(
                f"{self.mode.value} activation must carry the full speed cap; "
                "only DEGRADED lowers it"
            )

    @property
    def locked(self) -> bool:
        """Whether activation is refused in this mode (DISABLED or ARCHITECTURE_REOPEN)."""
        return self.mode in _LOCKED_MODES

    @property
    def activation_permitted(self) -> bool:
        """Whether the gate permits detection to run in this mode (ACTIVE or DEGRADED)."""
        return self.mode in _PERMITTED_MODES

    @property
    def banner_visible(self) -> bool:
        """Whether an operator banner is shown — true for every mode except fully ACTIVE."""
        return bool(self.banner)

    @property
    def effective_hz(self) -> float:
        """The measured effective detection-loop rate (reused from the band)."""
        return self.band.effective_hz

    @property
    def effective_latency_sec(self) -> float:
        """The effective detection delay in seconds (≈1/f), the figure FR-SAF-001b shows."""
        return self.band.effective_latency_sec

    def assert_can_activate(self) -> None:
        """Refuse activation unless the gate permits it (① the code-level lock).

        Raises:
            DetectionActivationRefusedError: If the mode is DISABLED (PG-FRIC-001 not PASS) or
                ARCHITECTURE_REOPEN (1 kHz unreachable by any pattern).
        """
        if self.mode is DetectionActivationMode.DISABLED:
            raise DetectionActivationRefusedError(
                f"collision detection is DISABLED: PG-FRIC-001 is "
                f"{self.pg_fric_001_status!r}, not {GATE_STATE_PASS}; activation is locked "
                "until it passes (FR-SAF-030, acceptance ①)"
            )
        if self.mode is DetectionActivationMode.ARCHITECTURE_REOPEN:
            raise DetectionActivationRefusedError(
                "collision detection cannot activate: the loop misses 1 kHz on every frame "
                "pattern, which is an architecture-reopen escalation, not an accepted degrade "
                "(02b §3.2, spec 12 §2.9)"
            )


def resolve_activation(pg_fric_001_status: str, band: DetectionBand) -> DetectionActivation:
    """Resolve the detection activation verdict from the friction gate and the measured band.

    The single gateway (SHAPE-IG). PG-FRIC-001 decides whether detection may run at all; the band
    then decides at what rate. A band that misses 1 kHz demotes to DEGRADED_ACCEPTED when the miss
    is the pattern-B CAN-FD clamp (the designed 625 Hz fallback), or to ARCHITECTURE_REOPEN when it
    is not clamped — pattern A is the 1 kHz-capable pattern, so a shortfall there means no pattern
    reaches 1 kHz, which is a design escalation rather than an accepted degrade.

    Args:
        pg_fric_001_status: The PG-FRIC-001 gate-state (`PASS` opens the gate; anything else locks
            it). Hardware-deferred on this host, so it is not PASS here and the gate stays locked.
        band: The measured detection-loop bandwidth (WP-1-06 `resolve_detection_band` output).

    Returns:
        (DetectionActivation) The resolved verdict — the sole constructor of the type.
    """
    if pg_fric_001_status != GATE_STATE_PASS:
        return DetectionActivation(
            mode=DetectionActivationMode.DISABLED,
            pg_fric_001_status=pg_fric_001_status,
            band=band,
            speed_cap_scale=FULL_SPEED_CAP_SCALE,
            banner=disabled_banner_text(),
        )
    if not band.degraded:
        return DetectionActivation(
            mode=DetectionActivationMode.ACTIVE,
            pg_fric_001_status=pg_fric_001_status,
            band=band,
            speed_cap_scale=FULL_SPEED_CAP_SCALE,
            banner=NO_BANNER,
        )
    if band.clamped:
        scale = _degraded_speed_cap_scale(band)
        return DetectionActivation(
            mode=DetectionActivationMode.DEGRADED,
            pg_fric_001_status=pg_fric_001_status,
            band=band,
            speed_cap_scale=scale,
            banner=degraded_banner_text(band.effective_latency_sec, scale),
        )
    return DetectionActivation(
        mode=DetectionActivationMode.ARCHITECTURE_REOPEN,
        pg_fric_001_status=pg_fric_001_status,
        band=band,
        speed_cap_scale=FULL_SPEED_CAP_SCALE,
        banner=reopen_banner_text(),
    )


def measure_and_resolve(
    pg_fric_001_status: str, frames_per_cycle: int, fmax: FMax
) -> DetectionActivation:
    """Measure the loop band and resolve the activation verdict in one call (② always measured).

    The cycle-time measurement is not an optional step a caller can skip: this composes the band
    resolution with the activation gate so every verdict carries a fresh band, DISABLED verdicts
    included.

    Args:
        pg_fric_001_status: The PG-FRIC-001 gate-state.
        frames_per_cycle: The CAN read pattern in effect (16 == A, 32 == B).
        fmax: The `WP-1-04` f_max figure the band is bounded by (provisional on this host).

    Returns:
        (DetectionActivation) The resolved verdict over the measured band.
    """
    band = resolve_detection_band(frames_per_cycle, fmax)
    return resolve_activation(pg_fric_001_status, band)


def assert_activation_allowed(pg_fric_001_status: str) -> None:
    """Refuse detection activation at the API boundary unless PG-FRIC-001 has passed (① the lock).

    The entry-point guard any activation UI/API path calls before engaging, mirroring
    `torque_bringup.assert_torque_on_allowed`. It turns a non-PASS friction verdict into a loud
    refusal at the door rather than a detection loop that runs on an unidentified model.

    Args:
        pg_fric_001_status: The PG-FRIC-001 gate-state.

    Raises:
        DetectionActivationRefusedError: If the status is anything other than PASS.
    """
    if pg_fric_001_status != GATE_STATE_PASS:
        raise DetectionActivationRefusedError(
            f"detection activation refused: PG-FRIC-001 is {pg_fric_001_status!r}, not "
            f"{GATE_STATE_PASS}; the UI/API is locked until it passes (FR-SAF-030, acceptance ①)"
        )


def assert_no_silent_downgrade(activation: DetectionActivation) -> None:
    """Affirm a verdict carries its downgrade defenses — the public form of the ③ guard.

    `DetectionActivation.__post_init__` already makes a silent-downgrade object impossible to
    construct; this is the affirmation a consumer can call to state the property at the point it
    accepts a verdict, so accepting a DEGRADED state without the cap/latency is a caught error.

    Args:
        activation: The verdict to check.

    Raises:
        SilentDowngradeError: If a DEGRADED verdict lacks a lowered speed cap or its delay banner.
    """
    if activation.mode is not DetectionActivationMode.DEGRADED:
        return
    if not activation.speed_cap_scale < FULL_SPEED_CAP_SCALE or not activation.banner:
        raise SilentDowngradeError(
            "DEGRADED_ACCEPTED verdict is missing its speed-cap downgrade or effective-delay "
            "display (acceptance ③)"
        )


def _degraded_speed_cap_scale(band: DetectionBand) -> float:
    """Derive the jog/teleop speed-cap fraction a degraded loop must enforce.

    The cap is lowered in proportion to the detection-rate shortfall: at `effective_hz` instead of
    the 1 kHz target, holding the worst-case intrusion distance between detection samples to the
    full-rate budget needs speed scaled by `effective_hz / target`. This is derived from the
    measured band, not a fixed target (I-6, no target before measurement), and rides the band's
    provisional f_max, so it is stale when PG-RT-001b re-derives the bound.

    Args:
        band: The degraded detection band.

    Returns:
        (float) The speed-cap fraction (< 1.0 for a degraded band), bounded at 1.0.
    """
    target = DETECTION_LOOP_TARGET_HZ
    return min(band.effective_hz / target, FULL_SPEED_CAP_SCALE)
