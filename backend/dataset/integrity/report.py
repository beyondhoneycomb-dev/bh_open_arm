"""The verdict types the integrity verifier produces (`02b` §8.2 WP-3D-05).

A dataset is `READY` only when every required check ran and passed; anything else
is `INVALID`. Two failure modes both make it INVALID, and the distinction is
load-bearing: a check that ran and FAILED, and a check that never ran at all
(a missing check). The second is why `ready` tests the required-check set rather than
just scanning for failures — a verifier that silently skipped a check must not be
able to certify a dataset by omission.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from backend.dataset.integrity.constants import (
    REQUIRED_CHECKS,
    VERDICT_INVALID,
    VERDICT_READY,
)


class CheckStatus(Enum):
    """The binary outcome of one integrity check — no warning level exists."""

    PASS = "pass"
    FAIL = "fail"


class IntegrityError(ValueError):
    """Raised when an INVALID dataset is requested as a training input.

    This is the interlock surface WP-3C-06 (source-delete) consumes: a dataset
    that cannot certify READY must never reach a trainer, and a caller that asks
    for it as an input gets this exception rather than a partial dataset.
    """


@dataclass(frozen=True)
class CheckResult:
    """One integrity check's outcome and the evidence behind it.

    Attributes:
        name: The check id (one of `constants.REQUIRED_CHECKS`).
        status: PASS or FAIL.
        detail: A human-readable reason — the failing file/field on FAIL, a short
            confirmation on PASS.
    """

    name: str
    status: CheckStatus
    detail: str

    @property
    def passed(self) -> bool:
        """Whether this check passed."""
        return self.status is CheckStatus.PASS


def passed(name: str, detail: str) -> CheckResult:
    """Build a passing result for a check."""
    return CheckResult(name=name, status=CheckStatus.PASS, detail=detail)


def failed(name: str, detail: str) -> CheckResult:
    """Build a failing result for a check."""
    return CheckResult(name=name, status=CheckStatus.FAIL, detail=detail)


@dataclass(frozen=True)
class IntegrityReport:
    """The full result of verifying one dataset directory.

    Attributes:
        root: The dataset root that was verified.
        results: One `CheckResult` per check that ran.
        elapsed_seconds: Wall time the checks took, for the regression bound.
        dataset_bytes: Total on-disk size of the dataset, the regression numerator.
    """

    root: Path
    results: tuple[CheckResult, ...]
    elapsed_seconds: float
    dataset_bytes: int

    def result(self, name: str) -> CheckResult | None:
        """Return the result for a named check, or None if it did not run."""
        for result in self.results:
            if result.name == name:
                return result
        return None

    @property
    def checks_ran(self) -> frozenset[str]:
        """The set of check names that produced a result."""
        return frozenset(result.name for result in self.results)

    @property
    def missing_checks(self) -> tuple[str, ...]:
        """Required checks that produced no result — a FAIL_BLOCKING omission."""
        ran = self.checks_ran
        return tuple(name for name in REQUIRED_CHECKS if name not in ran)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        """Every check that ran and failed."""
        return tuple(result for result in self.results if not result.passed)

    @property
    def ready(self) -> bool:
        """True only when all required checks ran and every result passed.

        A missing check counts against readiness exactly as loudly as a failed
        one: a dataset is READY only when the whole check set was applied and
        none of it bit (`02b` §8.2 WP-3D-05).
        """
        return not self.missing_checks and not self.failures

    @property
    def verdict(self) -> str:
        """`READY` when `ready`, else `INVALID`."""
        return VERDICT_READY if self.ready else VERDICT_INVALID

    def raise_if_invalid(self) -> None:
        """Raise `IntegrityError` unless the dataset verified READY.

        Raises:
            IntegrityError: When any required check is missing or failed, naming
                the offending checks so the caller sees why the dataset is barred.
        """
        if self.ready:
            return
        reasons = [f"{result.name}: {result.detail}" for result in self.failures]
        reasons.extend(f"{name}: check did not run" for name in self.missing_checks)
        raise IntegrityError(
            f"dataset {self.root} is {VERDICT_INVALID}; not a training input: " + "; ".join(reasons)
        )
