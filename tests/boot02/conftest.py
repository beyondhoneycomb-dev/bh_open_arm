"""Shared fixtures for the WP-BOOT-02 manifest and index generators."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from registry.generate.source import (
    REGISTRY_PATH,
    WorkPackage,
    group_by_work_package,
    load_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def registry_document() -> dict[str, Any]:
    """Load the real traceability registry.

    Returns:
        dict[str, Any]: Parsed `registry/traceability.yaml`.
    """
    return load_registry(REPO_ROOT / REGISTRY_PATH)


@pytest.fixture(scope="session")
def packages(registry_document: dict[str, Any]) -> list[WorkPackage]:
    """Collapse the registry into work-package views.

    Args:
        registry_document: Parsed registry.

    Returns:
        list[WorkPackage]: One view per work package.
    """
    return group_by_work_package(registry_document)


@pytest.fixture
def single_stage_manifest() -> dict[str, Any]:
    """Build the smallest manifest the schema accepts for a single-stage package.

    Returns:
        dict[str, Any]: A valid single-stage manifest.
    """
    return {
        "wp_id": "WP-0C-02",
        "exec_class": "AI-offline",
        "workflow": "SHAPE-IM",
        "owns": [{"glob": "backend/ik/**", "mode": "EXCLUSIVE"}],
        "consumes": ["CTR-UNIT@v1"],
        "produces": [],
        "gates": ["CG-0C-02a", "PG-IK-001"],
        "normalization_hash": None,
        "env_hash": None,
    }


@pytest.fixture
def multi_stage_manifest() -> dict[str, Any]:
    """Build the smallest manifest the schema accepts for a multi-stage package.

    Returns:
        dict[str, Any]: A valid multi-stage manifest.
    """
    return {
        "wp_id": "WP-1-03",
        "phases": [
            {
                "workflow": "SHAPE-IM",
                "exec_class": "AI-offline",
                "owns": [],
                "cancel_policy": "finish-step",
                "after": None,
            },
            {
                "workflow": "SHAPE-MS",
                "exec_class": "AI-on-HW",
                "owns": [],
                "cancel_policy": "latch-to-hold",
                "after": 0,
            },
        ],
        "owns": [],
        "consumes": [],
        "produces": ["CTR-GW@v1"],
        "gates": ["CG-1-03a"],
        "normalization_hash": None,
        "env_hash": None,
    }
