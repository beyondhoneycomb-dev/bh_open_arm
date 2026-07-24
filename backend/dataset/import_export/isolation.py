"""Environment isolation for the legacy import (`FR-DAT-040`).

The import runs `openarm-dataset-convert` in a separate environment
(`openarm_dataset[lerobot-dataset-v3-0]`) so the converter's dependencies never enter
the native runtime. This module describes that environment and provides the runtime
evidence of the boundary: the native process must not have the converter module
loaded. The environment's Python lower bound is left unresolved on purpose — `08` §2.9
/ `NFR-REC-007` fix it as pending lerobot's `requires-python` from source, and a
fabricated bound would be worse than an honest gap.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass

from backend.dataset.import_export.constants import (
    CONVERTER_MODULE,
    ISOLATED_ENV_EXTRA,
    ISOLATED_PYTHON_LOWER_BOUND,
)


class IsolationBreachError(RuntimeError):
    """Raised when the converter module is present in the native runtime.

    The import must run in a separate environment; the converter loaded here means the
    isolation boundary was crossed (`FR-DAT-040`).
    """


@dataclass(frozen=True)
class IsolatedEnv:
    """The isolated import environment (`FR-DAT-040`).

    Attributes:
        extra: The dependency extra that provisions the converter and the v3.0 writer.
        python_lower_bound: The environment's Python lower bound, or None while it is
            unresolved (`08` §2.9 / `NFR-REC-007`).
        converter_module: The module the environment provides and the native runtime
            must not load.
    """

    extra: str
    python_lower_bound: str | None
    converter_module: str


REQUIRED_ISOLATED_ENV = IsolatedEnv(
    extra=ISOLATED_ENV_EXTRA,
    python_lower_bound=ISOLATED_PYTHON_LOWER_BOUND,
    converter_module=CONVERTER_MODULE,
)


def python_lower_bound_resolved() -> bool:
    """Report whether the isolated environment's Python lower bound has been fixed.

    Returns:
        (bool) True once a source-confirmed bound is set; False while it is pending.
    """
    return ISOLATED_PYTHON_LOWER_BOUND is not None


def converter_present_in_native_runtime() -> bool:
    """Report whether the converter module is importable in the native runtime.

    A properly isolated native environment does not install the converter, so the
    module is not importable here. This is the check that the import's dependencies did
    not leak into the native process.

    Returns:
        (bool) True when the converter module can be imported natively.
    """
    if CONVERTER_MODULE in sys.modules:
        return True
    return importlib.util.find_spec(CONVERTER_MODULE) is not None


def assert_converter_not_imported() -> None:
    """Assert the converter module is not loaded in the native process.

    Raises:
        IsolationBreachError: When the converter module is present in `sys.modules` —
            the native runtime imported code that belongs to the isolated environment.
    """
    if CONVERTER_MODULE in sys.modules:
        raise IsolationBreachError(
            f"{CONVERTER_MODULE} is loaded in the native runtime; the import must run in the "
            f"isolated environment ({ISOLATED_ENV_EXTRA}), not here (FR-DAT-040)"
        )
