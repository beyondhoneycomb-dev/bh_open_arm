"""The operator's persisted overlay on the two shipped detection defaults (WP-2C-03).

NORM-009 and NORM-011 rule the same way about two different numbers: the per-joint collision
threshold (0.1 x effort) and the residual observer gain (K = 90) are *defaults*, not fixed
constants, so an operator must be able to change them and the changed value must survive a
restart. This module is that overlay — a persisted value wins, and where the operator never
set one the owning package's default stands. Both defaults are imported from the modules that
own them (`backend.threshold.constants`, `backend.gmo.constants`); neither is re-typed here.

Out of band is refused, never clamped. Clamping is right for a proposal *generator* — the
`proposer` and `presets` modules both clamp and flag the clamp — and wrong here, because the
rulings grant the operator the value they chose, so silently storing a different one is the
failure mode. The accepted threshold band is `backend.threshold`'s
`[THRESHOLD_MIN_NM, JOINT_EFFORT_LIMITS_NM]` rather than the marginally lower ten-LSB floor
this package's proposer clamps to (`backend.safety_bringup.thresholds.floor_for_joint`): the
only route a persisted threshold takes into the residual comparison is
`ThresholdCalibration.__post_init__`, which enforces the former, so a store that accepted the
lower floor would let an operator save a value the detector refuses at the next boot. The
store's accept-band has to stay a subset of the consumer's.

The write is persist-then-swap — sibling temp file, flush, fsync, `os.replace`, fsync the
parent directory — the discipline `backend.calibration.atomic_io` documents. That module's
writer is bound to the `OpenArmCalibration` shape and its frozen JSON Schema, so it cannot
persist this record; the discipline is reused, the schema-bound function is not. A torn write
leaves a safety parameter at an unknown value.

Loading runs the same band checks as the write path, so a hand-edited file is refused at read
time rather than surfacing later as a detection threshold nobody vetted. The gain is
re-checked against the `observer_gain_dt_s` stored beside it — the loop period that gain was
judged convergent at. It is NOT checked against the live loop period: judging a gain against
the *measured* band at activation time belongs to WP-2C-02 (`backend.detection_gate`), which
already owns activation and band resolution.

A record the load path refuses therefore locks the store: both setters read before they write,
so nothing can be saved until that file is gone, and no call here repairs or discards it.
Recovery is deleting the file — the same filesystem access the edit that broke it required. A
setter that swallowed the refusal and started from an empty record would hand the operator back
a threshold they did not choose, which is what refusing exists to prevent. Bumping
`SETTINGS_VERSION` puts every already-written file into that state, so a bump ships with a
migration or a deletion.

`resolved_*` and not `effective_*`: in this package `effective_nm` already means a value after
floor/cap clamping (`proposer`, `presets`), and one word cannot carry both meanings.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from backend.detection_gate import assert_gain_converges
from backend.gmo.constants import DEFAULT_OBSERVER_GAIN, OBSERVER_GAIN_MIN
from backend.threshold.constants import (
    JOINT_EFFORT_LIMITS_NM,
    N_ARM_JOINTS,
    THRESHOLD_DEFAULT_NM,
    THRESHOLD_MIN_NM,
)
from backend.threshold_calib.constants import (
    FIELD_OBSERVER_GAIN,
    FIELD_OBSERVER_GAIN_DT_S,
    FIELD_THRESHOLDS_NM,
    FIELD_VERSION,
    SETTINGS_FILENAME,
    SETTINGS_VERSION,
)


class SettingRefusedError(Exception):
    """Raised when an operator setting sits outside the band its ruling admits.

    Raised on the write path and the read path alike, so a value hand-edited into the file past
    a bound is refused when the file is read, not when the detector first compares against it.
    """


@dataclass(frozen=True)
class OperatorSettings:
    """The operator's overlay on the two shipped defaults.

    A `None` field is a number the operator never set, so the owning package's default stands.
    The gain carries the loop period beside it because NORM-011 makes a gain admissible only
    against a period — changing K reopens the `K*dt` judgement — so the pair is stored together
    and re-judged together.

    Attributes:
        thresholds_nm: Operator-set per-joint collision thresholds [Nm], or None.
        observer_gain: Operator-set residual observer gain K [1/s], or None.
        observer_gain_dt_s: The detection-loop period [s] the gain was judged against, or None.
    """

    thresholds_nm: tuple[float, ...] | None
    observer_gain: float | None
    observer_gain_dt_s: float | None

    def resolved_thresholds_nm(self) -> tuple[float, ...]:
        """Return the thresholds in force: the operator's if set, else the FR-SAF-020 default.

        Returns:
            (tuple[float, ...]) Per-joint collision thresholds [Nm], in joint order.
        """
        if self.thresholds_nm is None:
            return THRESHOLD_DEFAULT_NM
        return self.thresholds_nm

    def resolved_observer_gain(self) -> float:
        """Return the gain in force: the operator's if set, else the NFR-SAF-002 default.

        Returns:
            (float) The residual observer gain K [1/s].
        """
        if self.observer_gain is None:
            return DEFAULT_OBSERVER_GAIN
        return self.observer_gain


def _assert_thresholds_in_band(thresholds_nm: Sequence[float]) -> tuple[float, ...]:
    """Return the thresholds as floats, refusing any joint outside the settable band.

    Args:
        thresholds_nm: Candidate per-joint thresholds [Nm], in joint order.

    Returns:
        (tuple[float, ...]) The accepted values.

    Raises:
        SettingRefusedError: On the wrong joint width, or a value below its ten-LSB floor or
            above its URDF effort ceiling.
    """
    if len(thresholds_nm) != N_ARM_JOINTS:
        raise SettingRefusedError(
            f"thresholds must be {N_ARM_JOINTS} joints wide, got {len(thresholds_nm)}"
        )
    accepted: list[float] = []
    for joint, raw in enumerate(thresholds_nm):
        value = float(raw)
        floor = THRESHOLD_MIN_NM[joint]
        ceiling = JOINT_EFFORT_LIMITS_NM[joint]
        if not floor <= value <= ceiling:
            raise SettingRefusedError(
                f"joint{joint + 1} threshold {value} Nm is outside the settable band "
                f"[{floor:.4g}, {ceiling:.4g}] Nm (10 x LSB floor, effort-limit ceiling); "
                "refused, not clamped"
            )
        accepted.append(value)
    return tuple(accepted)


def _assert_gain_admissible(observer_gain: float, detection_dt_s: float) -> None:
    """Refuse a gain that is not strictly positive or cannot converge at this loop period.

    The convergence relation is WP-2C-02's (`backend.detection_gate.assert_gain_converges`); it
    owns and names the bound, so nothing here restates it. Its refusal is re-raised as this
    package's own type, chained, so a caller of the store has one refusal type to handle
    whatever the gate raises.

    Args:
        observer_gain: Candidate residual observer gain K [1/s].
        detection_dt_s: The detection-loop period [s] the gain is judged against.

    Raises:
        SettingRefusedError: If the gain is non-positive or diverges at this period.
    """
    if not observer_gain > OBSERVER_GAIN_MIN:
        raise SettingRefusedError(
            f"observer gain {observer_gain} must be strictly positive "
            f"(> {OBSERVER_GAIN_MIN}); refused, not clamped"
        )
    try:
        assert_gain_converges(observer_gain, detection_dt_s)
    except Exception as error:
        raise SettingRefusedError(
            f"observer gain {observer_gain} refused at loop period {detection_dt_s} s: {error}"
        ) from error


def settings_path_for(directory: Path) -> Path:
    """Return the operator-settings file path under a directory.

    Args:
        directory: The directory holding the operator settings file.

    Returns:
        (Path) `<directory>/operator_settings.oa_thr.json`.
    """
    return directory / SETTINGS_FILENAME


def _to_json_dict(settings: OperatorSettings) -> dict[str, Any]:
    """Return the settings record as a JSON-ready object."""
    thresholds = settings.thresholds_nm
    return {
        FIELD_VERSION: SETTINGS_VERSION,
        FIELD_THRESHOLDS_NM: None if thresholds is None else list(thresholds),
        FIELD_OBSERVER_GAIN: settings.observer_gain,
        FIELD_OBSERVER_GAIN_DT_S: settings.observer_gain_dt_s,
    }


def save_settings_atomic(path: Path, settings: OperatorSettings) -> None:
    """Write the operator settings to disk atomically.

    Args:
        path: Destination settings file path.
        settings: The record to persist.
    """
    body = json.dumps(_to_json_dict(settings), indent=2, sort_keys=True) + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)  # noqa: PTH105 — atomic rename primitive; Path.replace only wraps it
        _fsync_dir(path.parent)
    except BaseException:
        # A failed write must not leave a stray temp file a later glob would pick up.
        tmp_path.unlink(missing_ok=True)
        raise


def _fsync_dir(directory: Path) -> None:
    """Fsync a directory so a rename into it is durable across a crash."""
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _numbers_or_none(field: str, raw: Any) -> list[float] | None:
    """Return a stored numeric list as floats, or None when the field was never set.

    `bool` is excluded explicitly: it is an `int` subclass, so a `true` in the file would
    otherwise become a 1.0 Nm threshold that sits inside the band on the wrist joints.
    """
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise SettingRefusedError(f"{field} must be a list of numbers or absent, got {raw!r}")
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise SettingRefusedError(f"{field} must hold only numbers, found {value!r}")
    return [float(value) for value in raw]


def _number_or_none(field: str, raw: Any) -> float | None:
    """Return a stored number as a float, or None when the field was never set."""
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise SettingRefusedError(f"{field} must be a number or absent, got {raw!r}")
    return float(raw)


def load_settings(path: Path) -> OperatorSettings:
    """Read, validate and return the operator settings.

    Every stored value goes through the write path's band checks, so a file hand-edited below
    the noise floor, above the effort ceiling, or to a gain that cannot converge at its own
    recorded period is refused here rather than reaching the detector.

    Args:
        path: The settings file path.

    Returns:
        (OperatorSettings) The validated overlay.

    Raises:
        FileNotFoundError: If the file does not exist.
        SettingRefusedError: If the envelope is malformed or a stored value is out of band.
    """
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SettingRefusedError("settings file did not parse to an object")
    version = data.get(FIELD_VERSION)
    if version != SETTINGS_VERSION:
        raise SettingRefusedError(f"settings version must be {SETTINGS_VERSION}, got {version!r}")

    raw_thresholds = _numbers_or_none(FIELD_THRESHOLDS_NM, data.get(FIELD_THRESHOLDS_NM))
    thresholds = None if raw_thresholds is None else _assert_thresholds_in_band(raw_thresholds)
    gain = _number_or_none(FIELD_OBSERVER_GAIN, data.get(FIELD_OBSERVER_GAIN))
    dt_s = _number_or_none(FIELD_OBSERVER_GAIN_DT_S, data.get(FIELD_OBSERVER_GAIN_DT_S))
    if (gain is None) != (dt_s is None):
        raise SettingRefusedError(
            f"{FIELD_OBSERVER_GAIN} and {FIELD_OBSERVER_GAIN_DT_S} are stored together or not "
            "at all: a gain is admissible only against the loop period it was judged at"
        )
    if gain is not None and dt_s is not None:
        _assert_gain_admissible(gain, dt_s)
    return OperatorSettings(thresholds_nm=thresholds, observer_gain=gain, observer_gain_dt_s=dt_s)


@dataclass(frozen=True)
class OperatorSettingsStore:
    """The operator's persisted overlay under one directory.

    Ownership: the store holds no cache — every call reads the current file, so a fresh
    instance over the same directory sees exactly what a restarted process would, and a value
    written by another process is picked up on the next call. The caller supplies the
    directory; where an operator's settings live on a real deployment is not decided here.

    Attributes:
        directory: The directory holding the operator settings file.
    """

    directory: Path

    def load(self) -> OperatorSettings:
        """Return the stored overlay, or an empty one when nothing was ever set.

        Returns:
            (OperatorSettings) The validated overlay; all-None when no file exists.

        Raises:
            SettingRefusedError: If the stored file is malformed or out of band.
        """
        path = settings_path_for(self.directory)
        if not path.is_file():
            return OperatorSettings(thresholds_nm=None, observer_gain=None, observer_gain_dt_s=None)
        return load_settings(path)

    def set_thresholds(self, thresholds_nm: Sequence[float]) -> OperatorSettings:
        """Persist an operator-set per-joint threshold vector (NORM-009).

        Validated before anything is read or written, so a refused write leaves no file and no
        partially-updated record.

        Args:
            thresholds_nm: Per-joint collision thresholds [Nm], in joint order.

        Returns:
            (OperatorSettings) The record as written, with the gain overlay left as it was.

        Raises:
            SettingRefusedError: If any joint is outside the settable band.
        """
        accepted = _assert_thresholds_in_band(thresholds_nm)
        updated = replace(self.load(), thresholds_nm=accepted)
        save_settings_atomic(settings_path_for(self.directory), updated)
        return updated

    def set_observer_gain(self, observer_gain: float, detection_dt_s: float) -> OperatorSettings:
        """Persist an operator-set observer gain and the loop period it was judged at (NORM-011).

        Args:
            observer_gain: The residual observer gain K [1/s].
            detection_dt_s: The detection-loop period [s] the gain is judged against.

        Returns:
            (OperatorSettings) The record as written, with the threshold overlay left as it was.

        Raises:
            SettingRefusedError: If the gain is non-positive or diverges at this period.
        """
        _assert_gain_admissible(observer_gain, detection_dt_s)
        updated = replace(
            self.load(),
            observer_gain=float(observer_gain),
            observer_gain_dt_s=float(detection_dt_s),
        )
        save_settings_atomic(settings_path_for(self.directory), updated)
        return updated
