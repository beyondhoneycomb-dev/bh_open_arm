"""The conversion guard — the single authorization point for `openarm-dataset-convert`.

Every conversion request passes through `evaluate_conversion`, which renders one
`ConversionDecision` and is the only place that may return `allowed=True`. There is
no branch anywhere that authorizes exporting a native recording: the two refusal
paths (a LeRobot input, and a `gr00t`/`lerobot_v2.1` output) are the "0 export path"
of `02b` §8.2 WP-3D-07 ①, enforced statically by the absence of an allow branch and
at runtime by `authorize_conversion` raising.

An allowed request is a legacy OpenArm -> LeRobot v3.0 import; `plan_import` composes
the isolated-environment invocation for it (`FR-DAT-040`) without running it here — the
converter lives in a separate environment and is never imported into this runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.dataset.import_export.constants import (
    CONVERT_TOOL,
    IMPORT_ONLY_FORMAT,
    ISOLATED_ENV_EXTRA,
    ISOLATED_PYTHON_LOWER_BOUND,
)
from backend.dataset.import_export.formats import (
    FormatDisposition,
    InputKind,
    disposition_of,
)


class ConversionRefusedError(RuntimeError):
    """Base for every refusal `openarm-dataset-convert` may raise through this guard."""


class NoReversePathError(ConversionRefusedError):
    """A LeRobot dataset was offered as input — the reverse conversion does not exist.

    `FR-DAT-039` / `OA-DAT-008`: the converter's input is always OpenArm format; there
    is no `from_lerobot` path in the tool, so a request to convert one of our LeRobot
    recordings back out has no route and is always refused.
    """


class ExportBlockedError(ConversionRefusedError):
    """A `gr00t`/`lerobot_v2.1` output was requested — production is blocked.

    `FR-DAT-042` / `OA-DAT-009`: GR00T trains directly on the native v3.0 dataset, so
    a `gr00t` conversion is unnecessary; v2.1 cannot load under `lerobot >= 0.5`, so
    producing it is pointless.
    """


class UnsupportedOutputError(ConversionRefusedError):
    """An `openarm` output was requested — a legacy passthrough this platform never uses.

    `08` §2.2: the tool's only valid use here is the v3.0 import; a legacy-to-legacy
    `openarm` output produces nothing this platform ingests.
    """


class RefusalKind(Enum):
    """Which refusal a non-allowed decision carries, mapped to an exception on raise."""

    NO_REVERSE_PATH = "no_reverse_path"
    EXPORT_BLOCKED = "export_blocked"
    UNSUPPORTED_OUTPUT = "unsupported_output"


_REFUSAL_EXCEPTIONS: dict[RefusalKind, type[ConversionRefusedError]] = {
    RefusalKind.NO_REVERSE_PATH: NoReversePathError,
    RefusalKind.EXPORT_BLOCKED: ExportBlockedError,
    RefusalKind.UNSUPPORTED_OUTPUT: UnsupportedOutputError,
}


@dataclass(frozen=True)
class ConversionRequest:
    """A request to run `openarm-dataset-convert`.

    Attributes:
        input_kind: What the input dataset is. Only `LEGACY_OPENARM` can be opened.
        output_format: The requested `--format` value.
    """

    input_kind: InputKind
    output_format: str


@dataclass(frozen=True)
class ConversionDecision:
    """The resolved verdict on a conversion request.

    Attributes:
        allowed: True only for a legacy OpenArm -> LeRobot v3.0 import.
        disposition: The format disposition the decision rests on.
        reason: Human-readable justification for the verdict.
        refusal: The refusal kind when not allowed, else None.
    """

    allowed: bool
    disposition: FormatDisposition
    reason: str
    refusal: RefusalKind | None


def evaluate_conversion(request: ConversionRequest) -> ConversionDecision:
    """Resolve a conversion request without raising — the one authorization point.

    The reverse-path refusal is checked first: a LeRobot input is refused regardless
    of the requested output, because no output format gives our own recordings an
    export route (`FR-DAT-039`). Only a legacy OpenArm input with the `lerobot_v3.0`
    output is allowed.

    Args:
        request: The conversion request.

    Returns:
        (ConversionDecision) The verdict; `allowed=True` only for the one-way import.
    """
    if request.input_kind is InputKind.LEROBOT:
        return ConversionDecision(
            allowed=False,
            disposition=disposition_of(request.output_format),
            reason=(
                f"{CONVERT_TOOL} input is always OpenArm format; there is no LeRobot-input "
                "path, so a native recording has no export route (FR-DAT-039)"
            ),
            refusal=RefusalKind.NO_REVERSE_PATH,
        )

    disposition = disposition_of(request.output_format)
    if disposition is FormatDisposition.IMPORT_ALLOWED:
        return ConversionDecision(
            allowed=True,
            disposition=disposition,
            reason=(
                f"legacy OpenArm -> {IMPORT_ONLY_FORMAT} one-way import, the only valid use "
                f"of {CONVERT_TOOL} (FR-DAT-040)"
            ),
            refusal=None,
        )
    if disposition is FormatDisposition.EXPORT_BLOCKED:
        return ConversionDecision(
            allowed=False,
            disposition=disposition,
            reason=(
                f"--format {request.output_format} output is blocked: GR00T is a native "
                "LeRobot policy and v2.1 will not load under lerobot >= 0.5 (FR-DAT-042)"
            ),
            refusal=RefusalKind.EXPORT_BLOCKED,
        )
    return ConversionDecision(
        allowed=False,
        disposition=disposition,
        reason=(
            f"--format {request.output_format} is a legacy passthrough that produces no "
            "LeRobot artifact this platform ingests"
        ),
        refusal=RefusalKind.UNSUPPORTED_OUTPUT,
    )


def authorize_conversion(request: ConversionRequest) -> ConversionDecision:
    """Authorize a conversion request, raising the specific refusal when not allowed.

    Args:
        request: The conversion request.

    Returns:
        (ConversionDecision) The allowing decision.

    Raises:
        NoReversePathError: A LeRobot dataset was offered as input.
        ExportBlockedError: A `gr00t`/`lerobot_v2.1` output was requested.
        UnsupportedOutputError: An `openarm` legacy passthrough was requested.
    """
    decision = evaluate_conversion(request)
    if decision.allowed:
        return decision
    assert decision.refusal is not None  # a non-allowed decision always names its refusal
    raise _REFUSAL_EXCEPTIONS[decision.refusal](decision.reason)


@dataclass(frozen=True)
class IsolatedInvocation:
    """The isolated-environment command for an authorized import (`FR-DAT-040`).

    The import runs in a separate environment (`openarm_dataset[lerobot-dataset-v3-0]`)
    so the converter's dependencies never enter this runtime. This object describes
    that invocation; it is not executed here, and the converter is never imported into
    the native process.

    Attributes:
        argv: The `openarm-dataset-convert` command line for the import.
        env_extra: The isolated-environment extra to provision it under.
        python_lower_bound: The environment's Python lower bound, or None while it is
            unresolved (`08` §2.9 / `NFR-REC-007`).
    """

    argv: tuple[str, ...]
    env_extra: str
    python_lower_bound: str | None


def plan_import(input_path: str, output_path: str, fps: int) -> IsolatedInvocation:
    """Authorize a legacy import and compose its isolated-environment invocation.

    Args:
        input_path: The legacy OpenArm dataset directory.
        output_path: The destination for the LeRobot v3.0 dataset.
        fps: The frame rate to stamp on the imported grid.

    Returns:
        (IsolatedInvocation) The command to run in the isolated environment.

    Raises:
        ConversionRefusedError: When the request is not a legacy v3.0 import.
    """
    request = ConversionRequest(
        input_kind=InputKind.LEGACY_OPENARM, output_format=IMPORT_ONLY_FORMAT
    )
    authorize_conversion(request)
    argv = (
        CONVERT_TOOL,
        input_path,
        output_path,
        "--format",
        IMPORT_ONLY_FORMAT,
        "--fps",
        str(fps),
    )
    return IsolatedInvocation(
        argv=argv,
        env_extra=ISOLATED_ENV_EXTRA,
        python_lower_bound=ISOLATED_PYTHON_LOWER_BOUND,
    )
