"""The verdict a dataset preflight renders and the findings that justify it.

`02c` §1.2 WP-4A-02 fixes the shape of this report: a binary `verdict` and a list
of `findings`, each of which must name the channel it faults and — for an
observation-configuration fault — the joint and the per-motor component, because
"training config invalid" cannot tell an operator whether to fix the recording,
the rename map, or the statistics (`10` FR-TRN-061/063). A BLOCK with an
unlocatable finding is not actionable, so the finding carries the joint and
component the fault sits on.

`00` §8.0a: a `CG-*` acceptance check is a two-state judgment, so this verdict is
`PASS`/`BLOCK` and never a five-state gate status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from contracts.recorder import POSITION_SUFFIX, TORQUE_SUFFIX, VELOCITY_SUFFIX


class Verdict(StrEnum):
    """The binary outcome of a preflight run.

    BLOCK means at least one fault fixture-class defect was found and training
    must not start; PASS means the findings set is empty (`02c` §1.2 ⑤).
    """

    PASS = "PASS"
    BLOCK = "BLOCK"


class Component(StrEnum):
    """The per-motor `observation.state` component a channel carries.

    The three suffixes are imported from `CTR-REC@v1` rather than restated, so a
    finding's component label cannot drift from the contract's channel grammar
    (`07` §2.3.2). `.pos` is always present; `.vel`/`.torque` appear only under
    `use_velocity_and_torque`.
    """

    POS = POSITION_SUFFIX
    VEL = VELOCITY_SUFFIX
    TORQUE = TORQUE_SUFFIX


class PreflightCode(StrEnum):
    """The distinct fault codes, one per detectable defect class.

    Distinctness is the contract (as with `FR-TRN-017`): each acceptance fixture
    faults exactly one class, so the codes are never folded into a generic
    "invalid". Each maps to a `02c` §1.2 acceptance item.
    """

    # `names` order does not preserve the canonical per-motor layout — the silent
    # rename-rotation archetype and the torque-stripped-but-shape-kept fault
    # (`02c` §1.2 ①/②, `10` FR-TRN-061/063).
    OBSERVATION_STATE_ORDER = "OBSERVATION_STATE_ORDER"
    # `observation.state` `shape[0]` disagrees with the number of `names`; shape is
    # derived from names, so a mismatch means one was edited without the other.
    OBSERVATION_STATE_SHAPE_MISMATCH = "OBSERVATION_STATE_SHAPE_MISMATCH"
    # A quantile-normalized policy (pi0.5) was paired with statistics missing
    # `q01`/`q99` (`02c` §1.2 ③, `10` FR-TRN-020, `08` FR-DAT-026).
    QUANTILE_STATS_MISSING = "QUANTILE_STATS_MISSING"
    # A structural-exclusion meta feature (`timestamp`/`index`/…) was promoted into
    # the policy-input namespace (`02c` §1.2 ④, `10` FR-TRN-076, D-7).
    STRUCTURAL_FEATURE_PROMOTED = "STRUCTURAL_FEATURE_PROMOTED"


@dataclass(frozen=True)
class PreflightFinding:
    """One located preflight fault.

    Attributes:
        code: The fault class.
        channel_name: The feature key or `observation.state` channel the fault is
            on — always present so the fault is locatable.
        component: The per-motor component when the fault sits on a state channel;
            `None` for a feature-level fault (a missing statistic, a promoted meta
            feature) that has no single component.
        joint: The motor key when the fault sits on a state channel; `None` for a
            feature-level fault.
        detail: A human sentence naming the values that triggered the fault and,
            where relevant, the remediation (never auto-applied — see the
            `02c` §1.2 negative branch ③).
    """

    code: PreflightCode
    channel_name: str
    component: Component | None
    joint: str | None
    detail: str


@dataclass(frozen=True)
class PreflightReport:
    """The result of a preflight run: a verdict and the findings behind it.

    The verdict is a pure function of the findings — BLOCK iff any finding exists —
    so `from_findings` is the only constructor callers should use; it cannot
    produce a PASS that hides a finding or a BLOCK with an empty set.

    Attributes:
        verdict: PASS when `findings` is empty, else BLOCK.
        findings: The located faults, in detection order.
    """

    verdict: Verdict
    findings: tuple[PreflightFinding, ...] = field(default_factory=tuple)

    @classmethod
    def from_findings(cls, findings: tuple[PreflightFinding, ...]) -> PreflightReport:
        """Build a report whose verdict is derived from the findings.

        Args:
            findings: The located faults.

        Returns:
            (PreflightReport) BLOCK with the findings when any exist, else PASS
                with an empty set.
        """
        verdict = Verdict.BLOCK if findings else Verdict.PASS
        return cls(verdict=verdict, findings=tuple(findings))

    def codes(self) -> frozenset[PreflightCode]:
        """Return the distinct fault codes present, for a coarse assertion.

        Returns:
            (frozenset[PreflightCode]) The codes across all findings.
        """
        return frozenset(finding.code for finding in self.findings)
