"""The guard that keeps the committed registry equal to what the corpus seeds.

The registry is the canon and the prose is a view of it (`05` §0.1), which only holds while the
committed `traceability.yaml` is exactly what seeding the corpus produces. If the two drift, a
reader has no way to tell which one is lying, and every downstream rule judges the wrong document.

Two properties are load-bearing here and neither is visible from a green gate:

Divergence is measured against the registry **as committed**. Seeding rewrites that file from the
same document the comparison uses, so a measurement taken afterwards is zero whatever the corpus
says — and it prints beside the real counts, where it reads as a verdict.

An empty or unreadable comparison basis diverges wholesale rather than agreeing. Absence is the
one input that would otherwise turn the guard off silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from registry.ingest.cli import diverged_requirements

_REQ = "FR-XXX-001"
_OTHER_REQ = "FR-XXX-002"


def _document(*reqs: str) -> dict:
    """A seeded document carrying one minimal record per requirement id."""
    return {"entries": [{"req": req, "wp": "WP-0-00"} for req in reqs]}


def _committed(path: Path, payload: object) -> Path:
    """Write a committed registry file and return its path."""
    path.write_text(yaml.dump(payload, allow_unicode=True), encoding="utf-8")
    return path


def test_a_registry_equal_to_the_seed_does_not_diverge(tmp_path: Path) -> None:
    document = _document(_REQ, _OTHER_REQ)
    committed = _committed(tmp_path / "traceability.yaml", document)

    assert diverged_requirements(document, committed) == []


def test_a_record_the_corpus_does_not_seed_diverges(tmp_path: Path) -> None:
    committed = _committed(tmp_path / "traceability.yaml", _document(_REQ, _OTHER_REQ))

    assert diverged_requirements(_document(_REQ), committed) == [_OTHER_REQ]


def test_a_seeded_record_absent_from_the_registry_diverges(tmp_path: Path) -> None:
    committed = _committed(tmp_path / "traceability.yaml", _document(_REQ))

    assert diverged_requirements(_document(_REQ, _OTHER_REQ), committed) == [_OTHER_REQ]


def test_the_same_id_with_different_content_diverges(tmp_path: Path) -> None:
    """Presence is not agreement — this is the case a set comparison would miss."""
    committed = _committed(
        tmp_path / "traceability.yaml", {"entries": [{"req": _REQ, "wp": "WP-9-99"}]}
    )

    assert diverged_requirements(_document(_REQ), committed) == [_REQ]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"entries": []}, id="empty-entries"),
        pytest.param({"entries": None}, id="null-entries"),
        pytest.param({}, id="no-entries-key"),
        pytest.param([], id="not-a-mapping"),
    ],
)
def test_a_registry_with_nothing_to_compare_diverges_wholesale(
    tmp_path: Path, payload: object
) -> None:
    """Fail-closed: an empty comparison basis must not read as agreement.

    `null` is its own case because `dict.get(key, default)` returns None for a key present with a
    null value, so the default never applies and a naive iteration raises instead of refusing.
    """
    committed = _committed(tmp_path / "traceability.yaml", payload)

    assert diverged_requirements(_document(_REQ, _OTHER_REQ), committed) == [_REQ, _OTHER_REQ]


def test_an_absent_registry_diverges_wholesale(tmp_path: Path) -> None:
    absent = tmp_path / "traceability.yaml"

    assert diverged_requirements(_document(_REQ), absent) == [_REQ]
