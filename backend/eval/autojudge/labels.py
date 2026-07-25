"""Label provenance and the success-rate canon guard (`02c` §3.7, `FR-INF-079`).

`FR-INF-079` fixes the load-bearing rule: until the auto-judge is validated, the
success-rate canon is the HUMAN label, and a MODEL label never enters it. `02c` §3.7
names the field `EpisodeRecord.label_source ∈ {HUMAN, MODEL}` as "already defined in
§3.2", but §3.2 (WP-4C-02 human labelling) is a Human band and is NOT landed, so the
committed `EpisodeRecord` (WP-4C-03) carries no `label_source` field. Rather than
fork that committed contract (which this WP must not redefine), the provenance lives
HERE, at the auto-judge boundary, as `JudgedEpisode` wrapping the committed
`EpisodeRecord`. When §3.2 lands and moves `label_source` onto the record itself,
this wrapper collapses into it; until then it is the honest phase-1 realization.

The canon guard is `canon_episodes`: it is the ONLY function in this package that
unwraps `JudgedEpisode` into the committed `EpisodeRecord`s that WP-4C-03's
`aggregate` consumes, and it yields the HUMAN-sourced ones only. A MODEL label is
dropped before it can reach the canon (CG-4C-07a). This package deliberately never
calls the WP-4C-03 aggregator itself — it prepares the human-only set and hands it
off — so there is no in-package path by which a model label could become a canon
success number.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from backend.eval.autojudge.constants import (
    LABEL_SOURCE_HUMAN,
    LABEL_SOURCE_MODEL,
    SIDECAR_TAG_HUMAN_LABELED,
    SIDECAR_TAG_MODEL_JUDGED,
)

# WP-4C-03 contract consumption: the canon aggregation input is the committed
# `EpisodeRecord`, imported (never redefined) so `canon_episodes` returns exactly the
# type WP-4C-03's `aggregate` takes. Imported from the submodule, not the package
# `__init__`, so this stays free of the aggregator's numpy dependency.
from backend.eval.stats.episode import EpisodeRecord


class LabelSource(Enum):
    """Where an episode's success label came from (`02c` §3.7, `FR-INF-079`).

    HUMAN is the canon source; MODEL is the auto-judge's output, admissible for
    disagreement measurement and screening but never for the success-rate canon.
    """

    HUMAN = LABEL_SOURCE_HUMAN
    MODEL = LABEL_SOURCE_MODEL


class LabelProvenanceError(ValueError):
    """Raised when a labelled episode's provenance is internally inconsistent.

    The one case: a MODEL-sourced episode with no judge sidecar, or a HUMAN-sourced
    episode carrying a model sidecar. Provenance and sidecar must agree, or the
    "model-judged vs human-labeled" distinction (CG-4C-07c) is not trustworthy.
    """


@dataclass(frozen=True)
class JudgeSidecar:
    """The `model-judged` sidecar metadata for one auto-judged episode (`FR-SIM-095`).

    `FR-SIM-095` requires an auto-judged result to be recorded as sidecar metadata
    tagged `model-judged`, kept distinct from a human-labelled result. This is that
    sidecar: its `tag` is always `SIDECAR_TAG_MODEL_JUDGED`, so a value of this type
    is, by construction, a model judgement — a human label carries no `JudgeSidecar`.

    Attributes:
        model_name: The judge that produced the label (e.g. Cosmos Reason 2). Identity
            for attribution, not evidence a real run occurred (the run is DEFERRED).
        rationale: The judge's stated reason (`FR-SIM-095` output = success/fail +
            근거). Prose, carried verbatim; empty is allowed but tracked.
        tag: Fixed to `SIDECAR_TAG_MODEL_JUDGED`; `__post_init__` refuses any other.
    """

    model_name: str
    rationale: str
    tag: str = SIDECAR_TAG_MODEL_JUDGED

    def __post_init__(self) -> None:
        """Refuse a sidecar whose tag is not the model-judged marker (CG-4C-07c)."""
        if self.tag != SIDECAR_TAG_MODEL_JUDGED:
            raise LabelProvenanceError(
                f"a JudgeSidecar must be tagged {SIDECAR_TAG_MODEL_JUDGED!r}; got {self.tag!r}"
            )


@dataclass(frozen=True)
class JudgedEpisode:
    """A committed `EpisodeRecord` paired with the provenance of its success label.

    Frozen because a labelled outcome is a recorded fact. The `episode` is the
    committed WP-4C-03 contract, unmodified; `source` is the provenance this WP adds;
    `sidecar` is present iff `source` is MODEL, so the pair is self-describing and
    `__post_init__` enforces the correspondence.

    Attributes:
        episode: The committed `EpisodeRecord` (its `success` is the label in question).
        source: Whether the label is HUMAN (canon) or MODEL (auto-judge).
        sidecar: The `model-judged` sidecar; present iff `source is MODEL`.
    """

    episode: EpisodeRecord
    source: LabelSource
    sidecar: JudgeSidecar | None = None

    def __post_init__(self) -> None:
        """Enforce that sidecar presence matches label source (CG-4C-07c)."""
        if self.source is LabelSource.MODEL and self.sidecar is None:
            raise LabelProvenanceError(
                "a MODEL-sourced episode must carry a JudgeSidecar (model-judged), got none"
            )
        if self.source is LabelSource.HUMAN and self.sidecar is not None:
            raise LabelProvenanceError(
                "a HUMAN-sourced episode must not carry a JudgeSidecar; a human label is "
                f"tagged {SIDECAR_TAG_HUMAN_LABELED!r}, never model-judged"
            )

    @property
    def is_canon(self) -> bool:
        """Whether this label may enter the success-rate canon — i.e. it is HUMAN."""
        return self.source is LabelSource.HUMAN

    @property
    def sidecar_tag(self) -> str:
        """The provenance tag for the sidecar record (CG-4C-07c).

        Returns:
            (str) `model-judged` for a MODEL label, `human-labeled` for a HUMAN one.
        """
        if self.source is LabelSource.MODEL:
            return SIDECAR_TAG_MODEL_JUDGED
        return SIDECAR_TAG_HUMAN_LABELED


def canon_episodes(judged: Sequence[JudgedEpisode]) -> tuple[EpisodeRecord, ...]:
    """The canon guard: return the HUMAN-labelled episodes' committed records only.

    This is the single, sanctioned bridge from this package's labelled episodes to
    the WP-4C-03 success-rate aggregator. `FR-INF-079` fixes that the canon is the
    human label; a MODEL-sourced entry is dropped here, before it can reach the
    aggregator, so no model label ever becomes a canon success number (CG-4C-07a).

    It never calls the aggregator itself — it returns the exact `EpisodeRecord`
    sequence WP-4C-03's `aggregate` takes, and the caller (a DEFERRED pipeline stage)
    runs the canon. That separation is why this WP being on or off does not change
    WP-4C-03 (`02c` §3.3 워크플로우 형상).

    Args:
        judged: The labelled episodes, of mixed provenance.

    Returns:
        (tuple[EpisodeRecord, ...]) The committed records of the HUMAN-labelled ones,
            in input order; empty when none are human-labelled.
    """
    return tuple(item.episode for item in judged if item.source is LabelSource.HUMAN)


def model_labels_excluded_from_canon(judged: Sequence[JudgedEpisode]) -> int:
    """Count MODEL-sourced labels the canon guard drops — the guard's audit view.

    Args:
        judged: The labelled episodes the guard filtered.

    Returns:
        (int) How many MODEL-sourced entries `canon_episodes` excluded.
    """
    return sum(1 for item in judged if item.source is LabelSource.MODEL)


def sidecar_records(judged: Sequence[JudgedEpisode]) -> tuple[Mapping[str, str], ...]:
    """Render each episode's provenance sidecar with its distinct tag (CG-4C-07c).

    `FR-SIM-095` requires a model-judged result to be tagged distinctly from a
    human-labelled one in the sidecar metadata. This renders that tag for every
    episode, so a MODEL entry reads `model-judged` (with the judge and rationale) and
    a HUMAN entry reads `human-labeled` (with neither) — never the same tag.

    Args:
        judged: The labelled episodes to render sidecars for.

    Returns:
        (tuple[Mapping[str, str], ...]) One sidecar mapping per episode, in order.
    """
    records: list[Mapping[str, str]] = []
    for item in judged:
        record = {
            "task_id": item.episode.task_id,
            "seed": str(item.episode.seed),
            "source": item.source.value,
            "provenance_tag": item.sidecar_tag,
        }
        if item.sidecar is not None:
            record["model_name"] = item.sidecar.model_name
            record["rationale"] = item.sidecar.rationale
        records.append(record)
    return tuple(records)
