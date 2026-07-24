"""Conversion-format policy — which converter output is an import, which is blocked.

This module holds the pure classification that the guard (`guard.py`) and the CLI
(`cli.py`) both route through, so there is exactly one place that decides what
`openarm-dataset-convert` is allowed to do. The two facts it encodes (`08` §2.2/§2.3):

- The converter's INPUT is always an OpenArm-layout dataset; `--format` selects only
  the OUTPUT. There is no LeRobot-input path, so our own recordings have no export
  route (`FR-DAT-039`) — captured here as `InputKind`.
- Of the four output formats, only `lerobot_v3.0` is an import into this platform;
  `gr00t`/`lerobot_v2.1` are blocked (`FR-DAT-042`); `openarm` is a legacy-to-legacy
  passthrough that produces nothing this platform ingests.
"""

from __future__ import annotations

from enum import Enum

from backend.dataset.import_export.constants import (
    CONVERTER_FORMAT_CHOICES,
    EXPORT_BLOCKED_FORMATS,
    IMPORT_ONLY_FORMAT,
)


class InputKind(Enum):
    """What kind of dataset is offered to the converter as input.

    Attributes:
        LEGACY_OPENARM: An OpenArm-layout dataset (`metadata.yaml` +
            `episodes/<id>/...`) — the only input the converter can open (`08` §2.2).
        LEROBOT: A LeRobot-format dataset (native or already imported). The converter
            has no LeRobot-input path, so offering one is a reverse-conversion request
            that does not exist (`FR-DAT-039`).
    """

    LEGACY_OPENARM = "legacy_openarm"
    LEROBOT = "lerobot"


class FormatDisposition(Enum):
    """How a requested `--format` output is dispositioned by policy.

    Attributes:
        IMPORT_ALLOWED: `lerobot_v3.0` — the one-way legacy import (`FR-DAT-040`).
        EXPORT_BLOCKED: `gr00t`/`lerobot_v2.1` — production refused (`FR-DAT-042`).
        NON_IMPORT: `openarm` — legacy-to-legacy passthrough; produces no artifact
            this platform ingests, so it is not a usable conversion here.
    """

    IMPORT_ALLOWED = "import_allowed"
    EXPORT_BLOCKED = "export_blocked"
    NON_IMPORT = "non_import"


def is_known_format(output_format: str) -> bool:
    """Report whether a token is one of the converter's declared `--format` choices.

    Args:
        output_format: The `--format` value.

    Returns:
        (bool) True when the token is in `CONVERTER_FORMAT_CHOICES`.
    """
    return output_format in CONVERTER_FORMAT_CHOICES


def is_export_blocked(output_format: str) -> bool:
    """Report whether an output format is one this band refuses to produce.

    Args:
        output_format: The `--format` value.

    Returns:
        (bool) True for `gr00t`/`lerobot_v2.1` (`FR-DAT-042`).
    """
    return output_format in EXPORT_BLOCKED_FORMATS


def disposition_of(output_format: str) -> FormatDisposition:
    """Classify a requested output format under the import/export policy.

    Args:
        output_format: The `--format` value; must be a known converter choice.

    Returns:
        (FormatDisposition) The policy disposition of the format.

    Raises:
        ValueError: When the token is not a declared converter format choice — an
            unknown format is a caller error, not a silent no-op.
    """
    if not is_known_format(output_format):
        raise ValueError(
            f"unknown --format {output_format!r}; choices are {list(CONVERTER_FORMAT_CHOICES)}"
        )
    if output_format == IMPORT_ONLY_FORMAT:
        return FormatDisposition.IMPORT_ALLOWED
    if is_export_blocked(output_format):
        return FormatDisposition.EXPORT_BLOCKED
    return FormatDisposition.NON_IMPORT
