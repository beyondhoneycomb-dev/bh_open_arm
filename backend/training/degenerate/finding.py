"""The located degeneracy fault and the three-way decision that resolves it.

`02c` §1.3 fixes these two shapes (`FR-TRN-067`/`FR-TRN-068`):

    DegenerateFinding{channel_name, joint, component, norm_mode, statistic,
                      threshold, amplification_estimate}
    DegenerateDecision{finding, choice: EXCLUDE|MANUAL_STATS|PROCEED, rationale}

A finding must LOCATE the fault — the joint key and the per-motor component — for
the same reason a preflight finding must (`10` FR-TRN-067: the warning names the
joint and component); "some channel is degenerate" cannot tell an operator which
motor's velocity was stationary. The component reuses `backend.training.preflight.
Component` (the `CTR-REC@v1` suffixes), so a degeneracy component label cannot
drift from the recorder's channel grammar. The norm mode reuses the LeRobot
`NormalizationMode` values, so the mode a finding was judged under is exactly the
mode the trainer will normalize with.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from lerobot.configs.types import NormalizationMode

from backend.training.preflight import Component


class NormMode(StrEnum):
    """The three normalization modes whose degeneracy statistic differs.

    `FR-TRN-067` gives one detection rule per mode, judged by that mode's own
    statistic — never one formula for all three (`02c` §1.3 ③): MEAN_STD by the
    per-channel std, MIN_MAX by the max−min extent, QUANTILES by the q99−q01 span.
    Values are pinned to the LeRobot `NormalizationMode` enum so a mode string here
    is the same token the trainer keys its normalizer on. IDENTITY and QUANTILE10
    are intentionally absent: IDENTITY does not normalize (no amplification), and
    `02c` §1.3 names exactly these three.
    """

    MEAN_STD = NormalizationMode.MEAN_STD.value
    MIN_MAX = NormalizationMode.MIN_MAX.value
    QUANTILES = NormalizationMode.QUANTILES.value


class DegenerateChoice(StrEnum):
    """The forced three-way resolution of a degenerate finding (`FR-TRN-068`).

    Training must not start without one of these being recorded for every finding
    (`02c` §1.3 ④). The set is exactly three because the remedy space is exactly
    three: EXCLUDE drops the channel (the only real fix — `FR-TRN-069` forbids the
    per-group rescaling that could otherwise save it); MANUAL_STATS substitutes a
    hand-supplied statistic so the eps-floor amplification does not bite; PROCEED
    accepts the amplified channel knowingly.
    """

    EXCLUDE = "EXCLUDE"
    MANUAL_STATS = "MANUAL_STATS"
    PROCEED = "PROCEED"


@dataclass(frozen=True)
class DegenerateFinding:
    """One located degeneracy fault under one normalization mode.

    Frozen so a finding is a stable identity a decision can be matched to and a
    lineage record can immutably carry (`FR-TRN-054` (h)).

    Attributes:
        channel_name: The `observation.state` channel the fault sits on, e.g.
            `left_joint_2.vel` — always present so the fault is locatable.
        joint: The motor key parsed from `channel_name` (`left_joint_2`), never a
            positional guess (`FR-TRN-063` discipline: derive from the name string).
        component: The per-motor component (`.pos`/`.vel`/`.torque`), or `None` when
            the channel carries no contract suffix.
        norm_mode: The mode the channel was judged under; fixes which statistic the
            `statistic`/`threshold` pair refers to.
        statistic: The mode's measured value for this channel (std, max−min, or
            q99−q01) — the number that fell below `threshold`.
        threshold: The σ_min/δ_min applied (derived by the harness, never a plan
            constant — `02c` §1.3 σ_min-derivation block).
        amplification_estimate: The normalizer's gain 1/(statistic+eps): the factor
            by which this channel's raw deviation is scaled before it enters the
            loss. A well-conditioned channel is O(1); a degenerate channel is
            ~1e6–1e8, which is how a zero-information channel comes to dominate the
            loss (`FR-TRN-067`). An estimate, not a measured loss contribution.
    """

    channel_name: str
    joint: str
    component: Component | None
    norm_mode: NormMode
    statistic: float
    threshold: float
    amplification_estimate: float


@dataclass(frozen=True)
class DegenerateDecision:
    """A recorded resolution of one finding — the (h) element of `FR-TRN-054`.

    Attributes:
        finding: The finding this decision resolves; carried whole so lineage can
            answer "what was decided, and about which channel, under which mode".
        choice: The operator's three-way choice.
        rationale: Why this choice — the human sentence lineage preserves so a later
            reader can judge whether an amplified channel was accepted deliberately.
    """

    finding: DegenerateFinding
    choice: DegenerateChoice
    rationale: str
