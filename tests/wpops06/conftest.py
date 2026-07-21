"""Shared fixtures for the WP-OPS-06 acceptance tests.

Every content test needs two corpora: the real frozen registry (which must be
clean) and a one-field perturbation of it (which must be caught). Rebuilding a
`Registry` from a deep-copied document is how a fixture perturbs one row without
touching the frozen file on disk — the file stays byte-exact so the freeze lock
is never disturbed by a test run.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from contracts.errors.constants import REGISTRY_PATH
from contracts.errors.registry import Registry
from contracts.errors.spec_scan import canon_codes

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC14 = REPO_ROOT / "docs" / "spec" / "14-시스템-운영.md"


@pytest.fixture
def raw_document() -> dict[str, Any]:
    """Return the parsed frozen registry document.

    Returns:
        (dict[str, Any]) The `error_registry.yaml` mapping.
    """
    return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def mutate(raw_document: dict[str, Any]) -> Callable[[Callable[[dict[str, Any]], None]], Registry]:
    """Return a factory that deep-copies the document, perturbs it, and loads it.

    Args:
        raw_document: The clean document to copy from.

    Returns:
        (Callable) A function taking a perturbation and returning the loaded,
            perturbed registry.
    """

    def _build(perturb: Callable[[dict[str, Any]], None]) -> Registry:
        document = copy.deepcopy(raw_document)
        perturb(document)
        return Registry(document)

    return _build


@pytest.fixture
def required_codes() -> set[str]:
    """Return the codes the registry must cover: 14 §2.10 canon plus OA-SYS-001..011.

    Returns:
        (set[str]) Codes required to be present, read live from the spec.
    """
    return canon_codes(SPEC14) | {f"OA-SYS-{n:03d}" for n in range(1, 12)}
