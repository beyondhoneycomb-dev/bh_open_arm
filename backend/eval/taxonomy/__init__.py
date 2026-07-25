"""WP-4C-04 phase-1 — failure taxonomy schema + correlation engine (AI-offline).

The offline half of the failure taxonomy (`02c` §3.4): the tag schema, the engine that
auto-derives the nine machine tags from the committed WP-4A-08 signals, and the
tag<->error-code mapping. It never fabricates a human tag and never fakes a rollout — it
consumes committed signals and classifies them.

Public surface:

- `FailureTag` / `TagAxis` / `TagDerivation` / `FailureTagSpec` / `TAG_SPECS` — the
  schema; every tag carries a non-empty discriminating signal (CG-4C-04a). `spec_for`,
  `machine_tags` (the nine AUTO tags), `deferred_tags` (the HUMAN/FSM slots).
- `TAG_ERROR_CODES` / `code_for_tag` / `has_registry_code` / `NO_CODE` — each tag mapped
  to a `14` §2.10 code or an explicit "no code" (CG-4C-04d).
- `EpisodeSignals` / `TaxonomyThresholds` / `placeholder_taxonomy_thresholds` — the
  engine's aggregation-input contract, built from the committed dual-log / runaway /
  disconnect types and the FR-SIM-058 counters.
- `CorrelationEngine` — auto-derives the nine machine tags for one episode (CG-4C-04b/c/e).
"""

from __future__ import annotations

from backend.eval.taxonomy.engine import CorrelationEngine
from backend.eval.taxonomy.error_codes import (
    NO_CODE,
    TAG_ERROR_CODES,
    code_for_tag,
    has_registry_code,
)
from backend.eval.taxonomy.signals import (
    EpisodeSignals,
    TaxonomyThresholds,
    placeholder_taxonomy_thresholds,
)
from backend.eval.taxonomy.tags import (
    TAG_SPECS,
    FailureTag,
    FailureTagSpec,
    TagAxis,
    TagDerivation,
    deferred_tags,
    machine_tags,
    spec_for,
)

__all__ = [
    "NO_CODE",
    "TAG_ERROR_CODES",
    "TAG_SPECS",
    "CorrelationEngine",
    "EpisodeSignals",
    "FailureTag",
    "FailureTagSpec",
    "TagAxis",
    "TagDerivation",
    "TaxonomyThresholds",
    "code_for_tag",
    "deferred_tags",
    "has_registry_code",
    "machine_tags",
    "placeholder_taxonomy_thresholds",
    "spec_for",
]
