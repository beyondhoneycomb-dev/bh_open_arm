"""The WP-2C-02 detection activation gate: the single gateway for 2C real activation (SHAPE-IG).

FR-SAF-030 makes collision detection a function of one fact — PG-FRIC-001 PASS — and FR-SAF-001b
makes a detection loop that misses its rate a degrade with an effective-delay display, not a silent
continuation. NORM-008 settles what that rate is: not the discarded 1 kHz, but the 100 Hz at which
the forward-Euler residual converges for the configured gain. This module fuses them into one
verdict a caller cannot route around:

  * The lock (①). While PG-FRIC-001 is not PASS the verdict is DISABLED and `activation_permitted`
    is False; `assert_can_activate` and the API-level `assert_activation_allowed` raise. On this
    host PG-FRIC-001 is hardware-deferred (real excitation logs on a torque-ON arm plus PG-J7-001,
    of which this host has neither), so the real gate is always locked here — that LOCK is what the
    tests prove; the PASS branch is exercised only with a synthetic status to check the logic, never
    to claim the gate is open.

  * The measured downgrade (②). Activation always carries a `DetectionBand` — the loop cycle-time
    measurement is a required input, never skipped — and a band under the residual-detection target
    demotes the mode. The band math (the pattern-B 625 Hz clamp, the ≈1/f effective latency) is
    WP-1-06's and is reused from `backend.safety_bringup.band`, not re-derived. What is NOT reused
    is that module's `target_hz`/`degraded` pair: those are the 1 kHz pass/fail flag NORM-008
    discards, while the rate measurement they ride on is what it keeps. Wiring `band.degraded` back
    in is the obvious simpler thing to try, and it reinstates the discarded target.

  * No silent downgrade (③). A DEGRADED_ACCEPTED verdict is built only through `resolve_activation`,
    and its `__post_init__` refuses to exist unless it carries a speed-cap scale below 1.0 with the
    latency shown. A degrade that would display latency without lowering the cap cannot be
    constructed, so the alibi 02b §3.3 warns of has no representation. The same guard carries
    NORM-008's runtime assert: neither permitted mode can exist over a loop whose `K*dt` reaches
    the divergence bound, since capping speed does not redeem a residual that means nothing.

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
from backend.detection_gate.constants import (
    GATE_STATE_PASS,
    RESIDUAL_DETECTION_TARGET_HZ,
)
from backend.detection_gate.convergence import assert_gain_converges, gain_converges
from backend.detection_gate.errors import (
    DetectionActivationRefusedError,
    SilentDowngradeError,
)
from backend.rtbench.fmax import FMax
from backend.safety_bringup.band import DetectionBand, resolve_detection_band

# A fully active loop shows no banner; the other three modes each carry one. Named so the
# "banner is shown" predicate reads off intent rather than an empty-string test.
NO_BANNER = ""

# The full-rate speed cap: an un-degraded loop imposes no detection-driven downgrade, and the
# DISABLED/REOPEN states impose none either (detection is not running, so the conservative
# velocity limiter — WP-2A-04 — is what governs speed, not this gate).
FULL_SPEED_CAP_SCALE = 1.0

# The exclusive floor of a degrade's speed cap. The cap multiplies commanded jog/teleop velocity,
# so at zero it is a stop and below zero it reverses the command — neither is the "slower but
# still moving" state DEGRADED_ACCEPTED means, and both clear an unbounded "below full speed"
# test, which is why the degrade guard is a range and not a single comparison.
MIN_SPEED_CAP_SCALE = 0.0


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
        observer_gain: The residual-loop gain `K` in force. Required, not defaulted: the gate
            cannot evaluate `K*dt` without it, and a safety gate that assumes `K` is the silent
            path NORM-008 closes.
    """

    mode: DetectionActivationMode
    pg_fric_001_status: str
    band: DetectionBand
    speed_cap_scale: float
    banner: str
    observer_gain: float

    def __post_init__(self) -> None:
        """Refuse any verdict that violates its mode's safety invariant.

        The convergence check runs first and covers both permitted modes: a verdict that lets
        detection run over a loop the gain diverges at is not a downgrade to be capped, it is a
        residual that means nothing, so no amount of speed cap or banner redeems it.

        Raises:
            ObserverDivergenceError: If a mode that permits detection does not satisfy `K*dt < 2`
                over its own measured band (NORM-008's runtime assert).
            SilentDowngradeError: If a DEGRADED verdict's speed cap is not strictly between zero
                and 1.0, or it shows no effective-delay banner — the silent downgrade acceptance
                ③ forbids.
            ValueError: If a verdict sits on the wrong side of the residual-detection target for
                its mode, or a non-DEGRADED verdict carries a lowered cap.
        """
        if self.mode in _PERMITTED_MODES:
            assert_gain_converges(self.observer_gain, self.band.effective_latency_sec)
        if self.mode is DetectionActivationMode.DEGRADED:
            if not self.effective_hz < RESIDUAL_DETECTION_TARGET_HZ:
                raise ValueError(
                    f"DEGRADED activation built over {self.effective_hz} Hz, which meets the "
                    f"{RESIDUAL_DETECTION_TARGET_HZ} Hz residual-detection target"
                )
            if not MIN_SPEED_CAP_SCALE < self.speed_cap_scale < FULL_SPEED_CAP_SCALE:
                raise SilentDowngradeError(
                    f"DEGRADED_ACCEPTED activation carries speed_cap_scale={self.speed_cap_scale}, "
                    f"outside ({MIN_SPEED_CAP_SCALE}, {FULL_SPEED_CAP_SCALE}): a cap that is not "
                    "below full speed is the silent downgrade 02b §3.3 forbids, and one at or "
                    "below zero is a stop or a reversed command wearing the degrade's label "
                    "(acceptance ③)"
                )
            if not self.banner:
                raise SilentDowngradeError(
                    "DEGRADED_ACCEPTED activation shows no effective-delay banner; the ≈1/f delay "
                    "must be displayed (FR-SAF-001b, acceptance ③)"
                )
            return
        if (
            self.mode is DetectionActivationMode.ACTIVE
            and not self.effective_hz >= RESIDUAL_DETECTION_TARGET_HZ
        ):
            raise ValueError(
                f"ACTIVE activation built over {self.effective_hz} Hz, below the "
                f"{RESIDUAL_DETECTION_TARGET_HZ} Hz residual-detection target"
            )
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

    @property
    def converges(self) -> bool:
        """Whether the residual converges at this gain over this loop period (NORM-008).

        The band's effective latency IS the loop period, so it is passed straight through rather
        than a second `1/f` being derived here.
        """
        return gain_converges(self.observer_gain, self.band.effective_latency_sec)

    def assert_can_activate(self) -> None:
        """Refuse activation unless the gate permits it (① the code-level lock).

        Raises:
            DetectionActivationRefusedError: If the mode is DISABLED (PG-FRIC-001 not PASS) or
                ARCHITECTURE_REOPEN (no achievable rate converges at this gain).
        """
        if self.mode is DetectionActivationMode.DISABLED:
            raise DetectionActivationRefusedError(
                f"collision detection is DISABLED: PG-FRIC-001 is "
                f"{self.pg_fric_001_status!r}, not {GATE_STATE_PASS}; activation is locked "
                "until it passes (FR-SAF-030, acceptance ①)"
            )
        if self.mode is DetectionActivationMode.ARCHITECTURE_REOPEN:
            raise DetectionActivationRefusedError(
                f"collision detection cannot activate: at gain {self.observer_gain} the loop's "
                f"{self.effective_hz} Hz does not converge the residual, which is an "
                "architecture-reopen escalation, not an accepted degrade (02b §3.2, NORM-008)"
            )


def resolve_activation(
    pg_fric_001_status: str, band: DetectionBand, observer_gain: float
) -> DetectionActivation:
    """Resolve the detection activation verdict from the friction gate, the band, and the gain.

    The single gateway (SHAPE-IG). PG-FRIC-001 decides whether detection may run at all; the
    measured rate and the gain together decide in what state. Divergence is tested before the
    target because it dominates: a rate well above 100 Hz is still invalid if the gain is too
    large for it, so the escalation is not a rate verdict but a `K*dt` one.

    ARCHITECTURE_REOPEN keeps the shape it always had — no achievable rate meets what detection
    needs, so this is a design escalation and not an accepted degrade — and only the requirement
    changes, from an unreachable 1 kHz to the convergence floor. The band between that floor and
    the target is the real DEGRADED case: the residual does converge there, but it overshoots to
    roughly twice the contact torque on the way, which is a physical reason to cap speed rather
    than an invented one.

    Args:
        pg_fric_001_status: The PG-FRIC-001 gate-state (`PASS` opens the gate; anything else locks
            it). Hardware-deferred on this host, so it is not PASS here and the gate stays locked.
        band: The measured detection-loop bandwidth (WP-1-06 `resolve_detection_band` output).
        observer_gain: The residual-loop gain `K` the loop period is judged against.

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
            observer_gain=observer_gain,
        )
    if not gain_converges(observer_gain, band.effective_latency_sec):
        return DetectionActivation(
            mode=DetectionActivationMode.ARCHITECTURE_REOPEN,
            pg_fric_001_status=pg_fric_001_status,
            band=band,
            speed_cap_scale=FULL_SPEED_CAP_SCALE,
            banner=reopen_banner_text(observer_gain, band.effective_latency_sec),
            observer_gain=observer_gain,
        )
    if band.effective_hz >= RESIDUAL_DETECTION_TARGET_HZ:
        return DetectionActivation(
            mode=DetectionActivationMode.ACTIVE,
            pg_fric_001_status=pg_fric_001_status,
            band=band,
            speed_cap_scale=FULL_SPEED_CAP_SCALE,
            banner=NO_BANNER,
            observer_gain=observer_gain,
        )
    scale = _degraded_speed_cap_scale(band)
    return DetectionActivation(
        mode=DetectionActivationMode.DEGRADED,
        pg_fric_001_status=pg_fric_001_status,
        band=band,
        speed_cap_scale=scale,
        banner=degraded_banner_text(band.effective_latency_sec, scale),
        observer_gain=observer_gain,
    )


def measure_and_resolve(
    pg_fric_001_status: str, frames_per_cycle: int, fmax: FMax, observer_gain: float
) -> DetectionActivation:
    """Measure the loop band and resolve the activation verdict in one call (② always measured).

    The cycle-time measurement is not an optional step a caller can skip: this composes the band
    resolution with the activation gate so every verdict carries a fresh band, DISABLED verdicts
    included.

    Args:
        pg_fric_001_status: The PG-FRIC-001 gate-state.
        frames_per_cycle: The CAN read pattern in effect (16 == A, 32 == B).
        fmax: The `WP-1-04` f_max figure the band is bounded by (provisional on this host).
        observer_gain: The residual-loop gain `K` the measured period is judged against.

    Returns:
        (DetectionActivation) The resolved verdict over the measured band.
    """
    band = resolve_detection_band(frames_per_cycle, fmax)
    return resolve_activation(pg_fric_001_status, band, observer_gain)


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
        SilentDowngradeError: If a DEGRADED verdict's speed cap is not strictly between zero and
            full, or its delay banner is missing.
    """
    if activation.mode is not DetectionActivationMode.DEGRADED:
        return
    lowers_speed = MIN_SPEED_CAP_SCALE < activation.speed_cap_scale < FULL_SPEED_CAP_SCALE
    if not lowers_speed or not activation.banner:
        raise SilentDowngradeError(
            "DEGRADED_ACCEPTED verdict is missing its speed-cap downgrade or effective-delay "
            "display (acceptance ③)"
        )


def _degraded_speed_cap_scale(band: DetectionBand) -> float:
    """Derive the jog/teleop speed-cap fraction a degraded loop must enforce.

    The cap is lowered in proportion to the detection-rate shortfall: at `effective_hz` instead of
    the residual-detection target, holding the worst-case intrusion distance between detection
    samples to the full-rate budget needs speed scaled by `effective_hz / target`. It rides the
    band's provisional f_max, so it is stale when PG-RT-001b re-derives the bound.

    Args:
        band: A band whose `effective_hz` is below `RESIDUAL_DETECTION_TARGET_HZ` — the only case
            `resolve_activation` calls this for, so the ratio is below 1.0 without a clamp.

    Returns:
        (float) The speed-cap fraction.
    """
    return band.effective_hz / RESIDUAL_DETECTION_TARGET_HZ
