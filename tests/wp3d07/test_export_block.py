"""WP-3D-07 ②: a gr00t / v2.1 export request is BLOCKED — static and runtime.

`02b` §8.2 WP-3D-07 ①: there is 0 export path. Two facts make that true and this
module checks both directions: statically, the format policy has no disposition that
authorizes exporting a native recording, and `gr00t`/`lerobot_v2.1` are in the blocked
set; at runtime, `authorize_conversion` raises the specific refusal for a blocked
output and for a LeRobot input (`FR-DAT-039`, `FR-DAT-042`).
"""

from __future__ import annotations

import pytest

from backend.dataset.import_export import (
    CONVERTER_FORMAT_CHOICES,
    EXPORT_BLOCKED_FORMATS,
    ConversionRequest,
    ExportBlockedError,
    FormatDisposition,
    InputKind,
    NoReversePathError,
    UnsupportedOutputError,
    authorize_conversion,
    disposition_of,
    evaluate_conversion,
    is_export_blocked,
)

_LEGACY = InputKind.LEGACY_OPENARM


def test_blocked_set_covers_gr00t_and_v21() -> None:
    """The blocked output set is exactly the two the spec names (`FR-DAT-042`)."""
    assert set(EXPORT_BLOCKED_FORMATS) == {"gr00t", "lerobot_v2.1"}
    assert is_export_blocked("gr00t")
    assert is_export_blocked("lerobot_v2.1")


def test_no_disposition_authorizes_an_export_statically() -> None:
    """No known output format is dispositioned as anything but import/block/non-import.

    The only `IMPORT_ALLOWED` disposition is the v3.0 import; there is no disposition
    that authorizes turning a LeRobot dataset into another format, which is the static
    "0 export path".
    """
    allowed = [
        fmt
        for fmt in CONVERTER_FORMAT_CHOICES
        if disposition_of(fmt) is FormatDisposition.IMPORT_ALLOWED
    ]
    assert allowed == ["lerobot_v3.0"]


@pytest.mark.parametrize("output_format", list(EXPORT_BLOCKED_FORMATS))
def test_blocked_output_raises_at_runtime(output_format: str) -> None:
    """Authorizing a gr00t / v2.1 output raises `ExportBlockedError` (`FR-DAT-042`)."""
    request = ConversionRequest(input_kind=_LEGACY, output_format=output_format)
    with pytest.raises(ExportBlockedError):
        authorize_conversion(request)


def test_lerobot_input_is_refused_as_no_reverse_path() -> None:
    """A LeRobot dataset as input is refused — no reverse conversion exists (`FR-DAT-039`)."""
    request = ConversionRequest(input_kind=InputKind.LEROBOT, output_format="lerobot_v3.0")
    with pytest.raises(NoReversePathError):
        authorize_conversion(request)


def test_lerobot_input_refused_even_when_output_would_be_importable() -> None:
    """The reverse-path refusal wins regardless of the output format requested."""
    decision = evaluate_conversion(
        ConversionRequest(input_kind=InputKind.LEROBOT, output_format="lerobot_v3.0")
    )
    assert not decision.allowed
    assert "no LeRobot-input path" in decision.reason


def test_openarm_passthrough_is_not_an_import() -> None:
    """An `openarm` output produces no LeRobot artifact and is refused as unsupported."""
    request = ConversionRequest(input_kind=_LEGACY, output_format="openarm")
    with pytest.raises(UnsupportedOutputError):
        authorize_conversion(request)


def test_unknown_format_is_a_caller_error() -> None:
    """An undeclared `--format` token is a ValueError, never a silent no-op."""
    with pytest.raises(ValueError, match="unknown --format"):
        disposition_of("parquet_zip")
