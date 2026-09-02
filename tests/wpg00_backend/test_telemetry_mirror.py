"""The browser's telemetry key names against the backend's originals.

The frame's field list is already compared through the frozen envelope, which the frontend's
`FRAME_TABLE` mirrors. What that comparison does not reach is the keys INSIDE the body — the
observation vector's key, the per-side liveness names, the motor row names — because those live
in `backend/ws/telemetry.py` and are read in `frontend/src/ws/telemetryView.ts` with nothing
between them.

A drift there is silent in the worst way. `numberAt` answers null for a key that moved, the arm
is dropped from the parsed view, and the badge bar reports a healthy arm as disconnected — which
is exactly what a disconnected arm looks like.

Read out of the TypeScript source rather than imported, because that file is what the bundle is
built from.
"""

from __future__ import annotations

from pathlib import Path

from backend.ws import telemetry as backend_telemetry

_REPO_ROOT = Path(__file__).resolve().parents[2]
VIEW_TS = _REPO_ROOT / "frontend" / "src" / "ws" / "telemetryView.ts"

# The backend constants whose values must appear as string literals in the browser's reader.
# Named individually rather than swept off the module, so a constant added here without a
# consumer is a decision somebody made rather than a silent extension of this check.
MIRRORED = (
    backend_telemetry.OBSERVATION_STATE_KEY,
    backend_telemetry.ARM_READ_AGE,
    backend_telemetry.ARM_STALE,
    backend_telemetry.ARM_TICK_INDEX,
    backend_telemetry.ARM_OBSERVATION_PRESENT,
    backend_telemetry.ARM_BUS_READ_OK,
    backend_telemetry.ARM_LOCK_ACQUIRED,
    backend_telemetry.ARM_RESIDUAL_EXCEEDED,
)


def test_every_body_key_the_backend_emits_is_read_by_the_browser() -> None:
    """A renamed key parses as absent, and an absent arm renders as a disconnected one."""
    source = VIEW_TS.read_text(encoding="utf-8")

    missing = [key for key in MIRRORED if f'"{key}"' not in source]

    assert not missing, (
        f"{missing} are emitted by backend/ws/telemetry.py and named nowhere in "
        f"{VIEW_TS.name}. The reader drops what it cannot find, so the screen would show a "
        "live arm as absent with nothing failing."
    )


def test_the_motor_row_keys_are_read_by_the_screen_that_owns_them() -> None:
    """`S-03` parses `motor_states` itself, so its own file is where those keys must appear.

    Checked separately from the view above because the ownership is different: the row type and
    the missing-`err_nibble` default belong to that screen, and this test says so rather than
    letting the shared reader look like it models them.
    """
    domain = (_REPO_ROOT / "frontend" / "src" / "screens" / "S-03" / "motorDomain.ts").read_text(
        encoding="utf-8"
    )

    for key in (
        backend_telemetry.MOTOR_ROW_JOINT_NAME,
        backend_telemetry.MOTOR_ROW_TEMP_MOS,
        backend_telemetry.MOTOR_ROW_TEMP_ROTOR,
    ):
        assert key in domain, key
