"""Import checks for the pinned LeRobot (WP-ENV-01 acceptance ② and ③).

② the rollout engine entry imports; ③ the RealSense camera class symbol exists
(existence only — live capture is `PG-DEPTH-001`). The heavy `lerobot` import is
kept inside the functions so this module can be imported for inspection in a lane
that has not installed the robot stack; the checks themselves obviously require it.

`lerobot.scripts.rollout` does NOT exist in v0.6.0. The real onboard rollout
engine entry is the `lerobot-rollout` console script -> `lerobot.scripts.
lerobot_rollout:main`, backed by the `lerobot.rollout` engine module (`16` D-11).
"""

from __future__ import annotations

import importlib
import importlib.metadata as importlib_metadata
import importlib.util
from dataclasses import dataclass

ROLLOUT_CONSOLE_SCRIPT = "lerobot-rollout"
ROLLOUT_ENTRY_TARGET = "lerobot.scripts.lerobot_rollout:main"
ROLLOUT_ENGINE_MODULE = "lerobot.rollout"
ROLLOUT_ENGINE_SYMBOLS = ("RolloutConfig", "build_rollout_context", "create_strategy")

REALSENSE_MODULE = "lerobot.cameras.realsense"
REALSENSE_CLASS = "RealSenseCamera"


@dataclass(frozen=True)
class ImportCheck:
    """One import-check outcome.

    Attributes:
        name: Which acceptance item this is.
        ok: True when the check passed.
        detail: What was found, for the report.
    """

    name: str
    ok: bool
    detail: str


def check_rollout_entry() -> ImportCheck:
    """Acceptance ②: the rollout engine entry resolves and imports.

    The console-script entry point must point at `lerobot.scripts.
    lerobot_rollout:main`, and both the script module and the `lerobot.rollout`
    engine (with its config/context/strategy symbols) must import.

    Returns:
        (ImportCheck) The outcome.
    """
    scripts = importlib_metadata.entry_points(group="console_scripts")
    entry = next((e for e in scripts if e.name == ROLLOUT_CONSOLE_SCRIPT), None)
    if entry is None:
        return ImportCheck("rollout-entry", False, "no lerobot-rollout console script")
    if entry.value.replace(" ", "") != ROLLOUT_ENTRY_TARGET:
        return ImportCheck("rollout-entry", False, f"console script points at {entry.value!r}")
    try:
        script = importlib.import_module("lerobot.scripts.lerobot_rollout")
        engine = importlib.import_module(ROLLOUT_ENGINE_MODULE)
    except Exception as error:  # noqa: BLE001 — any import failure is a real fail
        return ImportCheck("rollout-entry", False, f"import failed: {error!r}")
    if not callable(getattr(script, "main", None)):
        return ImportCheck("rollout-entry", False, "lerobot_rollout.main not callable")
    missing = [s for s in ROLLOUT_ENGINE_SYMBOLS if not hasattr(engine, s)]
    if missing:
        return ImportCheck("rollout-entry", False, f"engine missing {missing}")
    return ImportCheck(
        "rollout-entry", True, f"{ROLLOUT_ENTRY_TARGET} imports; engine symbols present"
    )


def check_realsense_symbol() -> ImportCheck:
    """Acceptance ③: the RealSense camera class symbol exists (existence only).

    Returns:
        (ImportCheck) The outcome.
    """
    if importlib.util.find_spec(REALSENSE_MODULE) is None:
        return ImportCheck("realsense-symbol", False, f"no module {REALSENSE_MODULE}")
    module = importlib.import_module(REALSENSE_MODULE)
    symbol = getattr(module, REALSENSE_CLASS, None)
    if not isinstance(symbol, type):
        return ImportCheck("realsense-symbol", False, f"{REALSENSE_CLASS} is not a class")
    return ImportCheck("realsense-symbol", True, f"{REALSENSE_MODULE}.{REALSENSE_CLASS} exists")


def run_all() -> tuple[ImportCheck, ...]:
    """Run every WP-ENV-01 import check.

    Returns:
        (tuple[ImportCheck, ...]) One outcome per acceptance item.
    """
    return (check_rollout_entry(), check_realsense_symbol())
