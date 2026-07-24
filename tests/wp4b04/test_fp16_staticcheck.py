"""CG-4B-04d: no fp16 inference path is exposed by default (`FR-INF-030`), checked statically.

"Not exposed by default" is an absence, so the check is a static AST scan. Two halves,
the WP-BOOT-03 discipline: the scan finds no fp16 default in the committed inference
adapter or this WP's own tree (the real surfaces), and — proving it is not vacuously
green — it flags every fp16-default form in an inline fixture. bf16/float32 defaults are
the sanctioned options and must NOT be flagged.
"""

from __future__ import annotations

from pathlib import Path

from backend.compat.deploy_matrix.fp16_staticcheck import (
    find_fp16_default_exposure,
    scan_source,
)

ADAPTER_ROOT = Path("backend/inference/adapter")
DEPLOY_MATRIX_ROOT = Path("backend/compat/deploy_matrix")


def test_no_fp16_default_in_inference_adapter() -> None:
    """The committed WP-4A-07 adapter exposes no fp16 precision default."""
    assert find_fp16_default_exposure(ADAPTER_ROOT) == []


def test_no_fp16_default_in_deploy_matrix() -> None:
    """This WP's own tree exposes no fp16 precision default either."""
    assert find_fp16_default_exposure(DEPLOY_MATRIX_ROOT) == []


def test_scan_bites_every_fp16_default_form() -> None:
    """The scan flags each exposure form, proving it is not vacuously green."""
    offending = (
        "precision = 'fp16'\n"
        "def build(dtype='float16'):\n"
        "    return dtype\n"
        "make(torch_dtype=torch.float16)\n"
        "CONFIG = {'precision': 'half'}\n"
        "class C:\n"
        "    dtype: str = 'float16'\n"
    )
    violations = scan_source(offending, Path("fixture_fp16.py"))
    details = {violation.detail for violation in violations}
    assert details == {
        "assignment",
        "function default",
        "call keyword",
        "dict entry",
        "dataclass/field default",
    }
    assert {violation.field for violation in violations} == {
        "precision",
        "dtype",
        "torch_dtype",
    }


def test_sanctioned_precisions_are_not_flagged() -> None:
    """bf16/bfloat16/float32 are the exposed options and must not trip the scan."""
    sanctioned = (
        "precision = 'bf16'\n"
        "def build(dtype='bfloat16'):\n"
        "    return dtype\n"
        "make(torch_dtype='float32')\n"
        "CONFIG = {'precision': 'bfloat16'}\n"
    )
    assert scan_source(sanctioned, Path("fixture_ok.py")) == []


def test_non_precision_field_with_fp16_value_is_not_flagged() -> None:
    """An fp16 literal on a non-precision field is out of scope — only precision counts."""
    unrelated = "label = 'float16'\ndef f(name='half'):\n    return name\n"
    assert scan_source(unrelated, Path("fixture_unrelated.py")) == []
