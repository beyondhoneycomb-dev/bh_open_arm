"""The FR-MAN-047 adoption and the deferred operator confirm it does not fake (WP-2D-07).

WP-2D-07 is a two-phase package: an AI-offline phase that adopts and builds the home
decision, and a Human-judgment phase that cannot run offline. This module holds both
honestly.

The adopted decision (`HOME_DECISION`) records that home = `J4 = π/2` and that the `J4 = 0`
MoveIt pose — the mechanical lower hardstop — is *not* home. That is the AI-offline part,
and it is real.

The deferred part is a person looking at the arm and confirming that the `J4 = 0` pose is
in fact the fully-extended lower hardstop (`04` §3.6, phase2 = Human-judgment). It cannot be
produced offline, so it is SKIP-with-reason plus a re-verification hook, never asserted: the
hook only echoes an operator's recorded observation from a real fixture and refuses a
malformed one — it never invents a confirmation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.home.constants import (
    DEFAULT_HOME_Q_URDF,
    HARDSTOP_FIXTURE_ENV_VAR,
    HOME_J4_ANGLE_RAD,
    J4_LOWER_HARDSTOP_RAD,
)

CONFIRM_STATUS_SKIPPED = "SKIPPED"
CONFIRM_FIELD_OPERATOR = "operator"
CONFIRM_FIELD_IS_HARDSTOP = "j4_zero_is_fully_extended_hardstop"
CONFIRM_FIELD_OBSERVED = "observed"


@dataclass(frozen=True)
class HomeDecision:
    """The adopted resolution of FR-MAN-047 (`02b` WP-2D-07 ③, `04` §3.6).

    Attributes:
        requirement: The requirement resolved, `FR-MAN-047`.
        adopted_j4_rad: The adopted home elbow angle, π/2.
        adopted_q_urdf: The adopted default home driver state.
        rejected_j4_rad: The pose ruled out, `J4 = 0` (the mechanical lower hardstop).
        basis: The specification anchors the adoption rests on.
    """

    requirement: str
    adopted_j4_rad: float
    adopted_q_urdf: tuple[float, ...]
    rejected_j4_rad: float
    basis: tuple[str, ...]

    def as_record(self) -> dict[str, Any]:
        """Render the decision for an artifact.

        Returns:
            (dict[str, Any]) The requirement, adopted and rejected poses, and the basis.
        """
        return {
            "requirement": self.requirement,
            "adopted_home": "J4=pi/2",
            "adopted_j4_rad": self.adopted_j4_rad,
            "adopted_q_urdf": list(self.adopted_q_urdf),
            "rejected_home": "J4=0 (mechanical lower hardstop)",
            "rejected_j4_rad": self.rejected_j4_rad,
            "basis": list(self.basis),
        }


HOME_DECISION = HomeDecision(
    requirement="FR-MAN-047",
    adopted_j4_rad=HOME_J4_ANGLE_RAD,
    adopted_q_urdf=DEFAULT_HOME_Q_URDF,
    rejected_j4_rad=J4_LOWER_HARDSTOP_RAD,
    basis=("FR-MAN-047", "FR-MAN-048", "FR-MAN-049", "FR-GUI-118", "04 §3.6", "04 §2.10"),
)


@dataclass(frozen=True)
class DeferredVisualConfirm:
    """The SKIP-with-reason state of the operator J4=0-hardstop visual confirm (deferred).

    Attributes:
        status: Always `SKIPPED` until a real operator observation is supplied — the
            confirmation is a human judgment on hardware and is never produced offline.
        reason: Why it is deferred and what would close it.
        hook_env_var: The environment variable naming the real-fixture directory the
            re-verification hook reads.
    """

    status: str
    reason: str
    hook_env_var: str

    def as_record(self) -> dict[str, Any]:
        """Render the deferred state for an artifact.

        Returns:
            (dict[str, Any]) The status, reason, and hook variable.
        """
        return {"status": self.status, "reason": self.reason, "hook_env_var": self.hook_env_var}


def deferred_visual_confirm() -> DeferredVisualConfirm:
    """Return the deferred operator visual-confirm state (SKIP-with-reason).

    Returns:
        (DeferredVisualConfirm) The SKIPPED state, its reason, and the re-verification hook.
    """
    return DeferredVisualConfirm(
        status=CONFIRM_STATUS_SKIPPED,
        reason=(
            "an operator must visually confirm on real hardware that the J4=0 pose is the "
            "fully-extended lower hardstop before the J4=0-vs-pi/2 decision is closed; this "
            "is a human judgment (FR-MAN-047 phase2 = Human-judgment) and cannot be produced "
            "offline. The adopted decision (home = J4=pi/2) stands regardless; this confirm "
            "only records the operator's observation of the rejected pose."
        ),
        hook_env_var=HARDSTOP_FIXTURE_ENV_VAR,
    )


@dataclass(frozen=True)
class VisualConfirmRecord:
    """One operator observation of the J4=0 pose, as read from a real fixture.

    Attributes:
        operator: Who recorded the observation, empty when the capture was refused.
        is_fully_extended_hardstop: The operator's recorded verdict, or None when refused.
        observed: The operator's free-text note.
        refusal: Why the capture was refused, empty when it verified.
    """

    operator: str
    is_fully_extended_hardstop: bool | None
    observed: str
    refusal: str

    def as_record(self) -> dict[str, Any]:
        """Render the observation for an artifact.

        Returns:
            (dict[str, Any]) The operator, verdict, note, and any refusal.
        """
        return {
            "operator": self.operator,
            "is_fully_extended_hardstop": self.is_fully_extended_hardstop,
            "observed": self.observed,
            "refusal": self.refusal,
        }


def fixture_dir_from_env() -> Path | None:
    """Return the real-fixture directory named by the environment, if set and present.

    Returns:
        (Path | None) The directory, or None when unset or absent.
    """
    raw = os.environ.get(HARDSTOP_FIXTURE_ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _verify_one(capture: dict[str, Any]) -> VisualConfirmRecord:
    """Read one operator confirmation capture, refusing a malformed one.

    The verdict is the operator's, never this function's: a capture missing the operator or
    the boolean verdict is refused rather than defaulted, so a confirmation can only ever
    come from a real recorded observation.

    Args:
        capture: One parsed capture `{operator, j4_zero_is_fully_extended_hardstop, observed}`.

    Returns:
        (VisualConfirmRecord) The observation, or a refusal.
    """
    operator = str(capture.get(CONFIRM_FIELD_OPERATOR, ""))
    verdict = capture.get(CONFIRM_FIELD_IS_HARDSTOP)
    if not operator:
        return VisualConfirmRecord(
            operator="",
            is_fully_extended_hardstop=None,
            observed=str(capture.get(CONFIRM_FIELD_OBSERVED, "")),
            refusal=f"capture names no {CONFIRM_FIELD_OPERATOR!r}",
        )
    if not isinstance(verdict, bool):
        return VisualConfirmRecord(
            operator=operator,
            is_fully_extended_hardstop=None,
            observed=str(capture.get(CONFIRM_FIELD_OBSERVED, "")),
            refusal=f"capture field {CONFIRM_FIELD_IS_HARDSTOP!r} is not a boolean verdict",
        )
    return VisualConfirmRecord(
        operator=operator,
        is_fully_extended_hardstop=verdict,
        observed=str(capture.get(CONFIRM_FIELD_OBSERVED, "")),
        refusal="",
    )


def reverify_visual_confirm(fixture_dir: Path) -> list[VisualConfirmRecord]:
    """Read operator J4=0-hardstop confirmations from a real fixture directory.

    This is the hook the deferral ships: when an operator supplies recorded observations, it
    echoes each one and refuses the malformed. It renders no pass line of its own — a
    confirmation is the operator's verdict, so a green here can only ever be one they wrote.

    Args:
        fixture_dir: Directory of operator-confirmation JSON captures.

    Returns:
        (list[VisualConfirmRecord]) One record per capture, ordered by filename.

    Raises:
        FileNotFoundError: If the directory holds no `*.json` capture.
    """
    capture_files = sorted(fixture_dir.glob("*.json"))
    if not capture_files:
        raise FileNotFoundError(f"no *.json operator-confirmation capture in {fixture_dir}")
    return [_verify_one(json.loads(path.read_text(encoding="utf-8"))) for path in capture_files]
