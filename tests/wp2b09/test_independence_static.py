"""Acceptance ② — zero code binds the detection and control scales to one variable.

The real compscale package must scan clean, and the scan must genuinely bite: for each binding
form (shared variable, cross-read, attribute-copy) a synthetic sample is written to disk and the
scanner is required to catch it. A checker that cannot fail is not evidence, so the negative cases
carry as much weight as the clean pass (FR-SAF-035).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.compscale import (
    ScaleSeparationError,
    assert_scales_independent,
    compscale_package_files,
    find_scale_bindings,
)
from backend.compscale.independence import (
    KIND_ATTRIBUTE_COPY,
    KIND_CROSS_READ,
    KIND_SHARED_VARIABLE,
)

_SHARED_VARIABLE_SAMPLE = """
from backend.compscale import ControlCompensationScales, DetectionModelScales

shared = 1.0
det = DetectionModelScales(friction_scale=shared, coriolis_scale=shared)
ctl = ControlCompensationScales(friction_scale=shared)
"""

_CROSS_READ_SAMPLE = """
from backend.compscale import ControlCompensationScales, DetectionModelScales

ctl = ControlCompensationScales()
det = DetectionModelScales(friction_scale=ctl.friction_scale)
"""

_ATTRIBUTE_COPY_SAMPLE = """
from backend.compscale import ControlCompensationScales, DetectionModelScales

ctl = ControlCompensationScales()
det = DetectionModelScales.full()
det.friction_scale = ctl.friction_scale
"""

_CLEAN_SAMPLE = """
from backend.compscale import ControlCompensationScales, DetectionModelScales

det = DetectionModelScales.full()
ctl = ControlCompensationScales(friction_scale=0.3, coriolis_scale=0.1)
"""


def test_compscale_package_has_no_bindings() -> None:
    """The real package binds the two scales nowhere."""
    assert find_scale_bindings(compscale_package_files()) == ()


def test_assert_scales_independent_passes_on_package() -> None:
    """The FAIL_BLOCKING guard does not fire on the real package."""
    assert_scales_independent()


def _write(tmp_path: Path, name: str, source: str) -> Path:
    """Write a sample module to disk and return its path."""
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def test_shared_variable_binding_is_caught(tmp_path: Path) -> None:
    """One variable feeding a scale on both types is flagged as shared-variable."""
    sample = _write(tmp_path, "shared.py", _SHARED_VARIABLE_SAMPLE)
    bindings = find_scale_bindings([sample])
    assert [binding.kind for binding in bindings] == [KIND_SHARED_VARIABLE]


def test_cross_read_binding_is_caught(tmp_path: Path) -> None:
    """A detection scale read off a control instance is flagged as cross-read."""
    sample = _write(tmp_path, "crossread.py", _CROSS_READ_SAMPLE)
    bindings = find_scale_bindings([sample])
    assert [binding.kind for binding in bindings] == [KIND_CROSS_READ]


def test_attribute_copy_binding_is_caught(tmp_path: Path) -> None:
    """Copying a control scale field onto a detection instance is flagged as attribute-copy."""
    sample = _write(tmp_path, "attrcopy.py", _ATTRIBUTE_COPY_SAMPLE)
    bindings = find_scale_bindings([sample])
    assert [binding.kind for binding in bindings] == [KIND_ATTRIBUTE_COPY]


def test_clean_sample_has_no_bindings(tmp_path: Path) -> None:
    """A sample that keeps the two scales independent scans clean."""
    sample = _write(tmp_path, "clean.py", _CLEAN_SAMPLE)
    assert find_scale_bindings([sample]) == ()


def test_assert_raises_on_bound_sample(tmp_path: Path) -> None:
    """The guard raises, and names the site, when a binding is present."""
    sample = _write(tmp_path, "shared.py", _SHARED_VARIABLE_SAMPLE)
    with pytest.raises(ScaleSeparationError) as caught:
        assert_scales_independent([sample])
    assert "shared.py" in str(caught.value)


def test_non_python_and_missing_paths_are_skipped(tmp_path: Path) -> None:
    """A non-.py path and a missing file are skipped, not errors."""
    text = tmp_path / "notes.txt"
    text.write_text("DetectionModelScales(friction_scale=x)\n", encoding="utf-8")
    missing = tmp_path / "gone.py"
    assert find_scale_bindings([text, missing]) == ()
