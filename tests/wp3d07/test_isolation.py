"""WP-3D-07 ②: the import environment is isolated from the native runtime.

`FR-DAT-040`: the import runs in a separate environment
(`openarm_dataset[lerobot-dataset-v3-0]`). This module checks the runtime evidence of
that boundary — the converter module is not loadable in the native process — and that
the environment descriptor keeps the Python lower bound honestly unresolved (`08` §2.9
/ `NFR-REC-007`) rather than fabricating one.
"""

from __future__ import annotations

from backend.dataset.import_export import (
    ISOLATED_ENV_EXTRA,
    REQUIRED_ISOLATED_ENV,
    assert_converter_not_imported,
    converter_present_in_native_runtime,
    python_lower_bound_resolved,
)


def test_converter_not_present_in_native_runtime() -> None:
    """The legacy converter is not importable in the native process (`FR-DAT-040`)."""
    assert not converter_present_in_native_runtime()
    assert_converter_not_imported()


def test_python_lower_bound_is_unresolved() -> None:
    """The isolated env's Python lower bound is left unresolved, not guessed."""
    assert not python_lower_bound_resolved()
    assert REQUIRED_ISOLATED_ENV.python_lower_bound is None


def test_isolated_env_descriptor() -> None:
    """The required isolated environment names the v3.0 dataset extra."""
    assert REQUIRED_ISOLATED_ENV.extra == ISOLATED_ENV_EXTRA
    assert REQUIRED_ISOLATED_ENV.converter_module == "openarm_dataset"
