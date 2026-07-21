"""Load and schema-validate the normalization ledger.

Loading is separated from semantic validation on purpose: a document that does
not even match the shape (`registry/normalization/ledger.schema.json`) cannot be
reasoned about row by row, so the CLI reports schema errors first and stops.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = Path(__file__).resolve().parent / "ledger.schema.json"
LEDGER_PATH = REPO_ROOT / "docs" / "plan" / "normalization" / "ledger.yaml"


def load_ledger(path: Path) -> dict[str, Any]:
    """Parse a ledger document from YAML.

    Args:
        path: Path to a ledger YAML file.

    Returns:
        (dict[str, Any]) The parsed document.

    Raises:
        TypeError: When the file does not parse to a mapping.
    """
    loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{path} did not parse to a mapping")
    return loaded


def load_schema() -> dict[str, Any]:
    """Load the ledger JSON Schema.

    Returns:
        (dict[str, Any]) The parsed schema document.
    """
    parsed: Any = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError(f"{SCHEMA_PATH} did not parse to a mapping")
    return parsed


def schema_errors(document: dict[str, Any]) -> list[str]:
    """Return the schema violations of a ledger document, in document order.

    Args:
        document: A parsed ledger document.

    Returns:
        (list[str]) One message per violation; empty when the document is valid.
    """
    validator = Draft202012Validator(load_schema())
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '(root)'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda error: error.absolute_path)
    ]
