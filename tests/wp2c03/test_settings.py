"""Operator-set thresholds and observer gain persist across a restart (NORM-009, NORM-011).

Both rulings say the same thing about two different numbers: the value the code ships is a
*default*, so the operator must be able to change it and the changed value must survive a
restart. These tests hold both halves — the default stands when nothing was set, and a set
value comes back on a store built fresh over the same directory — plus the three refusals the
rulings' bands imply, each paired with the accepted case so a refusal cannot be refusing
everything, and the envelope refusals the reader raises on a file it did not write.

The vector's width and the file's name are pinned as well. Neither is a band, and both are
load-bearing in a way no other case here reaches: a vector of the wrong width is indexed against
the seven-joint residual joint by joint, and the file name is what keeps this record and the
three sibling `.oa_*.json` records off each other's bytes.

Both merge directions are held, not one: each setter reads the stored record before writing,
and the direction that runs against an empty file cannot tell a merge from a replacement.

Every expected default, floor and ceiling is imported from the production constant that owns
it, and every persisted value is compared to what was passed in rather than to what was read
back, so no assertion is derived from the thing under test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from backend.calibration.atomic_io import CALIBRATION_SUFFIX
from backend.gmo.constants import DEFAULT_OBSERVER_GAIN, NOMINAL_DETECTION_DT_S
from backend.gripper_endpoint.constants import RECORD_SUFFIX
from backend.safety_bringup.thresholds import floor_for_joint
from backend.teaching.constants import COLLECTION_SUFFIX
from backend.threshold import ThresholdCalibration
from backend.threshold.constants import (
    JOINT_EFFORT_LIMITS_NM,
    N_ARM_JOINTS,
    THRESHOLD_DEFAULT_NM,
    THRESHOLD_MIN_NM,
)
from backend.threshold_calib import (
    SETTINGS_FILENAME,
    SETTINGS_VERSION,
    NoCollisionJudgment,
    OperatorSettings,
    OperatorSettingsStore,
    ResidualStats,
    SettingRefusedError,
    attested_calibration,
    load_settings,
    propose_max_plus_sigma,
    save_settings_atomic,
    settings_path_for,
)
from backend.threshold_calib import settings as settings_module
from backend.threshold_calib.constants import (
    FIELD_OBSERVER_GAIN,
    FIELD_OBSERVER_GAIN_DT_S,
    FIELD_THRESHOLDS_NM,
    FIELD_VERSION,
)

# The two detection-loop rates NORM-011's `K*dt < 2` coupling separates for the shipped gain:
# at 100 Hz the residual settles, at 10 Hz it alternates and grows without bound. The bound
# itself is never written here — it belongs to `backend.detection_gate`, and a test that
# restated it would still pass with the production relation deleted.
CONVERGENT_LOOP_HZ = 100.0
DIVERGENT_LOOP_HZ = 10.0

# A joint moved off its default so a persisted vector is distinguishable from the shipped one.
# A mid-arm index, so an implementation that only ever carries element 0 does not pass.
MOVED_JOINT = 3
MOVED_JOINT_SCALE = 0.5

# Residual statistics for the canonical-calibration path: a max well inside the band on every
# joint, so `max + 3sigma` needs neither the floor nor the effort cap and the persisted value
# is the statistic itself rather than a clamp.
RESIDUAL_MAX_FRACTION_OF_DEFAULT = 0.5
RESIDUAL_SIGMA_FRACTION_OF_DEFAULT = 0.01
RESIDUAL_SAMPLE_COUNT = 1000

# The mirror of the two fractions above: `max + 3sigma` lands at 13 % of the floor, so the
# proposer's floor clamp fires on every joint and the handoff carries a clamped value.
CLAMPED_RESIDUAL_MAX_FRACTION_OF_FLOOR = 0.1
CLAMPED_RESIDUAL_SIGMA_FRACTION_OF_FLOOR = 0.01

# One past the only envelope version the reader accepts, for the refusal and lockout cases.
UNSUPPORTED_SETTINGS_VERSION = SETTINGS_VERSION + 1

# What a JSON `true` becomes once it is taken for a number. One name for all three units it
# lands in here — Nm, s, 1/s — because the reason each is 1.0 is the same `true`. Every guarded
# field admits it: 1.0 Nm sits inside every joint's threshold band and K*dt = 1.0 converges, so
# nothing but the bool guards can refuse it.
BOOL_AS_NUMBER = 1.0

# Zero-based index of joint7, the lowest-torque joint and the one the floor cases move.
WRIST_JOINT = 6

# The three sibling persisted records, each imported from the package that owns it. The settings
# file name must end in none of these: a shared suffix is two mechanisms reading each other's
# bytes, and the reader that lost would refuse a safety parameter it merely failed to recognise.
SIBLING_RECORD_SUFFIXES = (CALIBRATION_SUFFIX, COLLECTION_SUFFIX, RECORD_SUFFIX)


def _moved_thresholds() -> tuple[float, ...]:
    """Return the shipped default with one joint scaled off it."""
    moved = list(THRESHOLD_DEFAULT_NM)
    moved[MOVED_JOINT] = THRESHOLD_DEFAULT_NM[MOVED_JOINT] * MOVED_JOINT_SCALE
    return tuple(moved)


def _canonical_thresholds() -> tuple[float, ...]:
    """Return thresholds carried through the package's own attested-calibration path."""
    stats = tuple(
        ResidualStats(
            joint_index=joint,
            max_abs_nm=THRESHOLD_DEFAULT_NM[joint] * RESIDUAL_MAX_FRACTION_OF_DEFAULT,
            sigma_nm=THRESHOLD_DEFAULT_NM[joint] * RESIDUAL_SIGMA_FRACTION_OF_DEFAULT,
            mean_nm=0.0,
            sample_count=RESIDUAL_SAMPLE_COUNT,
        )
        for joint in range(N_ARM_JOINTS)
    )
    judgment = NoCollisionJudgment("operator-1", "sweep-A", attested=True, note="clean")
    return attested_calibration(propose_max_plus_sigma(stats), judgment).require_canonical()


def _settings_json(overrides: dict[str, Any]) -> str:
    """Return a settings file body with every field absent except the ones overridden.

    Built field by field rather than through `save_settings_atomic`, because the load-path
    refusals are files the writer would never produce.
    """
    body: dict[str, Any] = {
        FIELD_VERSION: SETTINGS_VERSION,
        FIELD_THRESHOLDS_NM: None,
        FIELD_OBSERVER_GAIN: None,
        FIELD_OBSERVER_GAIN_DT_S: None,
    }
    body.update(overrides)
    return json.dumps(body)


def test_the_shipped_settings_file_name_is_pinned(tmp_path: Path) -> None:
    """The file name is a compatibility surface, so it is re-typed here rather than imported.

    Importing the constant and comparing it to itself would pass under any name at all. An
    already-deployed record lives under this exact name and nothing migrates it: renaming the
    constant silently resolves every operator to the shipped defaults, with their persisted
    threshold and gain still on disk and no longer read. That is a safety parameter reverting in
    silence, which is the failure NORM-009 and NORM-011 exist to close.
    """
    assert SETTINGS_FILENAME == "operator_settings.oa_thr.json"
    assert settings_path_for(tmp_path) == tmp_path / "operator_settings.oa_thr.json"
    # The other half of the name's job: no sibling record's reader may recognise this file.
    assert not any(SETTINGS_FILENAME.endswith(suffix) for suffix in SIBLING_RECORD_SUFFIXES)


def test_absent_file_resolves_to_the_shipped_defaults(tmp_path: Path) -> None:
    """With nothing ever set, both numbers resolve to the value their owning package ships."""
    store = OperatorSettingsStore(tmp_path)
    assert store.load().resolved_thresholds_nm() == THRESHOLD_DEFAULT_NM
    assert store.load().resolved_observer_gain() == DEFAULT_OBSERVER_GAIN
    assert not settings_path_for(tmp_path).exists()


def test_operator_thresholds_survive_a_restart(tmp_path: Path) -> None:
    """NORM-009: a set threshold vector comes back on a store built fresh over the directory."""
    moved = _moved_thresholds()
    OperatorSettingsStore(tmp_path).set_thresholds(moved)

    restarted = OperatorSettingsStore(tmp_path).load()
    assert restarted.resolved_thresholds_nm() == moved
    # Without this a store that dropped the write and returned the default would pass above.
    assert restarted.resolved_thresholds_nm() != THRESHOLD_DEFAULT_NM


def test_operator_gain_survives_a_restart(tmp_path: Path) -> None:
    """NORM-011: a set observer gain comes back on a store built fresh over the directory."""
    gain = DEFAULT_OBSERVER_GAIN / 2.0
    OperatorSettingsStore(tmp_path).set_observer_gain(gain, NOMINAL_DETECTION_DT_S)

    restarted = OperatorSettingsStore(tmp_path).load()
    assert restarted.resolved_observer_gain() == gain
    assert restarted.resolved_observer_gain() != DEFAULT_OBSERVER_GAIN
    assert restarted.observer_gain_dt_s == NOMINAL_DETECTION_DT_S


def test_a_threshold_written_after_a_gain_keeps_the_gain(tmp_path: Path) -> None:
    """The threshold setter merges onto a record that already carries a gain."""
    store = OperatorSettingsStore(tmp_path)
    gain = DEFAULT_OBSERVER_GAIN / 2.0
    store.set_observer_gain(gain, NOMINAL_DETECTION_DT_S)
    assert store.load().resolved_thresholds_nm() == THRESHOLD_DEFAULT_NM

    moved = _moved_thresholds()
    store.set_thresholds(moved)
    reloaded = OperatorSettingsStore(tmp_path).load()
    assert reloaded.resolved_thresholds_nm() == moved
    assert reloaded.resolved_observer_gain() == gain


def test_a_gain_written_after_a_threshold_keeps_the_threshold(tmp_path: Path) -> None:
    """The gain setter merges onto a record that already carries thresholds.

    The direction above is vacuous for this setter — it runs against an empty file, where
    merging and replacing are the same write. A gain setter that built a fresh record would
    pass every other case here while reverting a calibrated joint to the shipped default the
    next time an operator touched the gain, which is the NORM-009 persistence destroyed.
    """
    store = OperatorSettingsStore(tmp_path)
    moved = _moved_thresholds()
    store.set_thresholds(moved)

    gain = DEFAULT_OBSERVER_GAIN / 2.0
    store.set_observer_gain(gain, NOMINAL_DETECTION_DT_S)

    reloaded = OperatorSettingsStore(tmp_path).load()
    assert reloaded.resolved_thresholds_nm() == moved
    assert reloaded.resolved_thresholds_nm() != THRESHOLD_DEFAULT_NM
    assert reloaded.resolved_observer_gain() == gain


# Threshold vectors of the wrong width, one direction each. Every element is some joint's shipped
# default, so each sits inside a band and the width is the only thing left to refuse them for.
WRONG_WIDTH_THRESHOLDS = [
    pytest.param(THRESHOLD_DEFAULT_NM[:WRIST_JOINT], id="one_joint_short"),
    pytest.param((*THRESHOLD_DEFAULT_NM, THRESHOLD_DEFAULT_NM[WRIST_JOINT]), id="one_joint_long"),
]


@pytest.mark.parametrize("thresholds", WRONG_WIDTH_THRESHOLDS)
def test_a_threshold_vector_of_the_wrong_width_is_refused(
    tmp_path: Path, thresholds: tuple[float, ...]
) -> None:
    """Width is checked before value, because a vector of any other width is mis-indexed.

    No band can catch these: every element is in band for the position it sits at, so width is
    all there is to refuse them for. `ThresholdCalibration` refuses the same widths, which is the
    point rather than a redundancy — without the guard here the vector is *persisted*, and the
    refusal moves from the write, where the operator is standing and can retype it, to the next
    boot, where the detector has no threshold to run on and nobody is watching.

    Held on both paths. The write path is where a caller with a stale joint count comes in; the
    read path is where a file written before a joint-count change does.
    """
    store = OperatorSettingsStore(tmp_path)
    with pytest.raises(SettingRefusedError, match="joints wide"):
        store.set_thresholds(thresholds)
    assert not settings_path_for(tmp_path).exists()

    path = settings_path_for(tmp_path)
    path.write_text(_settings_json({FIELD_THRESHOLDS_NM: list(thresholds)}), encoding="utf-8")
    with pytest.raises(SettingRefusedError, match="joints wide"):
        store.load()


def test_threshold_below_the_floor_is_refused_not_clamped(tmp_path: Path) -> None:
    """Under the ten-LSB floor a threshold fires on quantisation noise, so the write is refused."""
    under_floor = list(THRESHOLD_DEFAULT_NM)
    under_floor[WRIST_JOINT] = THRESHOLD_MIN_NM[WRIST_JOINT] / 2.0

    store = OperatorSettingsStore(tmp_path)
    with pytest.raises(SettingRefusedError, match="joint7") as refusal:
        store.set_thresholds(tuple(under_floor))
    assert f"{THRESHOLD_MIN_NM[WRIST_JOINT]:.4g}" in str(refusal.value)
    # A refusal that still wrote the file is the hazard the message would hide.
    assert not settings_path_for(tmp_path).exists()


def test_threshold_above_the_effort_ceiling_is_refused(tmp_path: Path) -> None:
    """Above the joint's torque ceiling the threshold can never be reached, so detection is dead."""
    over_ceiling = list(THRESHOLD_DEFAULT_NM)
    over_ceiling[0] = JOINT_EFFORT_LIMITS_NM[0] + 1.0

    store = OperatorSettingsStore(tmp_path)
    with pytest.raises(SettingRefusedError, match="joint1") as refusal:
        store.set_thresholds(tuple(over_ceiling))
    assert f"{JOINT_EFFORT_LIMITS_NM[0]:.4g}" in str(refusal.value)
    assert not settings_path_for(tmp_path).exists()


def test_the_band_edges_are_accepted(tmp_path: Path) -> None:
    """The paired positive: both bounds are inclusive, so the refusals refuse only what is out."""
    for edge in (THRESHOLD_MIN_NM, JOINT_EFFORT_LIMITS_NM):
        store = OperatorSettingsStore(tmp_path)
        store.set_thresholds(edge)
        assert OperatorSettingsStore(tmp_path).load().resolved_thresholds_nm() == edge


def test_non_positive_gain_is_refused(tmp_path: Path) -> None:
    """`r_dot = K*(tau_ext - r)` is a low-pass only for K > 0, so K <= 0 is a config error."""
    store = OperatorSettingsStore(tmp_path)
    for gain in (0.0, -1.0):
        with pytest.raises(SettingRefusedError, match="positive"):
            store.set_observer_gain(gain, NOMINAL_DETECTION_DT_S)
    assert not settings_path_for(tmp_path).exists()

    store.set_observer_gain(DEFAULT_OBSERVER_GAIN, NOMINAL_DETECTION_DT_S)
    assert OperatorSettingsStore(tmp_path).load().resolved_observer_gain() == DEFAULT_OBSERVER_GAIN


def test_a_gain_that_cannot_converge_at_the_loop_period_is_refused(tmp_path: Path) -> None:
    """NORM-011's coupling: changing K reopens the loop-period judgement, so the pair is checked."""
    store = OperatorSettingsStore(tmp_path)
    with pytest.raises(SettingRefusedError):
        store.set_observer_gain(DEFAULT_OBSERVER_GAIN, 1.0 / DIVERGENT_LOOP_HZ)
    assert not settings_path_for(tmp_path).exists()

    store.set_observer_gain(DEFAULT_OBSERVER_GAIN, 1.0 / CONVERGENT_LOOP_HZ)
    restarted = OperatorSettingsStore(tmp_path).load()
    assert restarted.resolved_observer_gain() == DEFAULT_OBSERVER_GAIN
    assert restarted.observer_gain_dt_s == 1.0 / CONVERGENT_LOOP_HZ


def test_a_hand_edited_out_of_band_file_is_refused_on_load(tmp_path: Path) -> None:
    """The band binds on the read path too, not only where the store wrote it."""
    under_floor = list(THRESHOLD_DEFAULT_NM)
    under_floor[WRIST_JOINT] = THRESHOLD_MIN_NM[WRIST_JOINT] / 2.0
    path = settings_path_for(tmp_path)
    path.write_text(
        json.dumps(
            {
                FIELD_VERSION: SETTINGS_VERSION,
                FIELD_THRESHOLDS_NM: under_floor,
                FIELD_OBSERVER_GAIN: None,
                FIELD_OBSERVER_GAIN_DT_S: None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SettingRefusedError, match="joint7"):
        OperatorSettingsStore(tmp_path).load()
    with pytest.raises(SettingRefusedError, match="joint7"):
        load_settings(path)


def test_a_hand_edited_divergent_gain_pair_is_refused_on_load(tmp_path: Path) -> None:
    """A stored K/dt pair is re-judged on load, so an edited period cannot smuggle a divergent K."""
    path = settings_path_for(tmp_path)
    path.write_text(
        json.dumps(
            {
                FIELD_VERSION: SETTINGS_VERSION,
                FIELD_THRESHOLDS_NM: None,
                FIELD_OBSERVER_GAIN: DEFAULT_OBSERVER_GAIN,
                FIELD_OBSERVER_GAIN_DT_S: 1.0 / DIVERGENT_LOOP_HZ,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SettingRefusedError):
        OperatorSettingsStore(tmp_path).load()


# Envelopes the load path must refuse, each paired with a fragment of the message naming the
# guard that fired. Every one of them is a file a hand edit or a future writer can produce; each
# is stored in the same field a valid record uses, so nothing here is refused by shape alone.
MALFORMED_SETTINGS_FILES = [
    pytest.param(
        json.dumps([SETTINGS_VERSION]),
        "did not parse to an object",
        id="not_an_object",
    ),
    pytest.param(
        _settings_json({FIELD_VERSION: UNSUPPORTED_SETTINGS_VERSION}),
        "version must be",
        id="unsupported_version",
    ),
    pytest.param(
        _settings_json({FIELD_THRESHOLDS_NM: THRESHOLD_DEFAULT_NM[0]}),
        "list of numbers",
        id="thresholds_not_a_list",
    ),
    pytest.param(
        _settings_json(
            {
                FIELD_THRESHOLDS_NM: [
                    *THRESHOLD_DEFAULT_NM[:WRIST_JOINT],
                    str(THRESHOLD_DEFAULT_NM[WRIST_JOINT]),
                ]
            }
        ),
        "only numbers",
        id="thresholds_hold_a_string",
    ),
    pytest.param(
        _settings_json({FIELD_OBSERVER_GAIN: DEFAULT_OBSERVER_GAIN}),
        "stored together",
        id="gain_without_its_period",
    ),
    pytest.param(
        _settings_json({FIELD_OBSERVER_GAIN_DT_S: NOMINAL_DETECTION_DT_S}),
        "stored together",
        id="period_without_its_gain",
    ),
]


@pytest.mark.parametrize(("body", "expected"), MALFORMED_SETTINGS_FILES)
def test_a_malformed_envelope_is_refused_on_load(tmp_path: Path, body: str, expected: str) -> None:
    """Each envelope guard refuses, and says which one: the alternative is a silent wrong read.

    A gain stored without its period is the one that does not look malformed. It is refused
    because the period is what makes the gain admissible, so a record missing it would be read
    back as an operator-set gain nothing ever judged for convergence.
    """
    path = settings_path_for(tmp_path)
    path.write_text(body, encoding="utf-8")

    with pytest.raises(SettingRefusedError, match=expected):
        OperatorSettingsStore(tmp_path).load()


def test_a_bool_in_the_thresholds_list_is_refused(tmp_path: Path) -> None:
    """`bool` is an `int` subclass, so a hand-edited `true` needs its own guard to be caught."""
    # Why a guard and not the band: the number `true` decays to is in band on every joint.
    assert all(
        THRESHOLD_MIN_NM[joint] < BOOL_AS_NUMBER < JOINT_EFFORT_LIMITS_NM[joint]
        for joint in range(N_ARM_JOINTS)
    )

    edited = list(THRESHOLD_DEFAULT_NM)
    edited[WRIST_JOINT] = True
    path = settings_path_for(tmp_path)
    path.write_text(_settings_json({FIELD_THRESHOLDS_NM: edited}), encoding="utf-8")

    with pytest.raises(SettingRefusedError, match="only numbers"):
        OperatorSettingsStore(tmp_path).load()


# Every scalar field the bool guard covers, each with the companion value that leaves the stored
# pair admissible once `true` decays to a number. Both are listed because the guard is one branch
# over both fields: narrowed to either one it still passes a suite that exercises only that one,
# and the field it stopped covering is then read back as a value nobody set.
BOOL_SCALAR_FIELDS = [
    pytest.param(
        FIELD_OBSERVER_GAIN,
        {FIELD_OBSERVER_GAIN_DT_S: NOMINAL_DETECTION_DT_S},
        id="observer_gain",
    ),
    pytest.param(
        FIELD_OBSERVER_GAIN_DT_S,
        {FIELD_OBSERVER_GAIN: BOOL_AS_NUMBER},
        id="observer_gain_dt_s",
    ),
]


@pytest.mark.parametrize(("field", "companion"), BOOL_SCALAR_FIELDS)
def test_a_bool_in_a_scalar_field_is_refused(
    tmp_path: Path, field: str, companion: dict[str, Any]
) -> None:
    """The scalar half of the same hazard: `true` reads as a 1.0 that every other guard admits.

    A bool period is the quieter of the two. It decays to a 1 Hz loop, and a gain judged
    convergent against a period the operator never set is the NORM-011 coupling gone — the pair
    is stored together precisely so the gain is never admitted on its own.
    """
    path = settings_path_for(tmp_path)
    path.write_text(_settings_json({**companion, field: True}), encoding="utf-8")

    with pytest.raises(SettingRefusedError, match="must be a number"):
        OperatorSettingsStore(tmp_path).load()

    # The paired positive: the same record with a real 1.0 loads, so only the guard refused above.
    admitted = {**companion, field: BOOL_AS_NUMBER}
    path.write_text(_settings_json(admitted), encoding="utf-8")
    loaded = OperatorSettingsStore(tmp_path).load()
    assert loaded.resolved_observer_gain() == admitted[FIELD_OBSERVER_GAIN]
    assert loaded.observer_gain_dt_s == admitted[FIELD_OBSERVER_GAIN_DT_S]


def test_a_refused_record_locks_the_setters_until_the_file_is_deleted(tmp_path: Path) -> None:
    """Both setters read before they write, so a record the load path refuses locks the store.

    No call repairs or discards it: recovery is deleting the file, the same filesystem access
    the edit that broke it needed. Repairing it in the setter would hand back a record the
    operator did not choose. Bumping `SETTINGS_VERSION` puts every deployed file in this state.
    """
    path = settings_path_for(tmp_path)
    path.write_text(_settings_json({FIELD_VERSION: UNSUPPORTED_SETTINGS_VERSION}), encoding="utf-8")
    store = OperatorSettingsStore(tmp_path)
    moved = _moved_thresholds()

    with pytest.raises(SettingRefusedError, match="version must be"):
        store.load()
    with pytest.raises(SettingRefusedError, match="version must be"):
        store.set_thresholds(moved)
    with pytest.raises(SettingRefusedError, match="version must be"):
        store.set_observer_gain(DEFAULT_OBSERVER_GAIN, NOMINAL_DETECTION_DT_S)

    path.unlink()
    store.set_thresholds(moved)
    assert OperatorSettingsStore(tmp_path).load().resolved_thresholds_nm() == moved


def test_a_write_that_dies_before_the_rename_leaves_the_previous_settings_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Persist-then-swap: a kill between the temp file and the rename cannot tear the record."""
    store = OperatorSettingsStore(tmp_path)
    first = _moved_thresholds()
    store.set_thresholds(first)
    path = settings_path_for(tmp_path)
    original_bytes = path.read_bytes()

    def _boom(_src: object, _dst: object) -> None:
        raise OSError("simulated crash before rename")

    monkeypatch.setattr(settings_module.os, "replace", _boom)
    with pytest.raises(OSError, match="simulated crash"):
        store.set_thresholds(THRESHOLD_DEFAULT_NM)

    assert path.read_bytes() == original_bytes
    assert OperatorSettingsStore(tmp_path).load().resolved_thresholds_nm() == first


def test_save_leaves_no_temp_file_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stray sibling temp file would be a second, unvetted copy of a safety parameter."""
    path = settings_path_for(tmp_path)
    save_settings_atomic(path, OperatorSettings(THRESHOLD_DEFAULT_NM, None, None))
    save_settings_atomic(path, OperatorSettings(_moved_thresholds(), None, None))
    assert list(path.parent.iterdir()) == [path]

    def _boom(_src: object, _dst: object) -> None:
        raise OSError("simulated crash before rename")

    monkeypatch.setattr(settings_module.os, "replace", _boom)
    with pytest.raises(OSError, match="simulated crash"):
        save_settings_atomic(path, OperatorSettings(THRESHOLD_DEFAULT_NM, None, None))
    assert list(path.parent.iterdir()) == [path]


def test_a_canonical_calibration_can_be_persisted_as_the_operator_threshold(tmp_path: Path) -> None:
    """The wizard's canonical output is what the store's threshold setter is fed."""
    canonical = _canonical_thresholds()
    OperatorSettingsStore(tmp_path).set_thresholds(canonical)
    assert OperatorSettingsStore(tmp_path).load().resolved_thresholds_nm() == canonical
    assert canonical != THRESHOLD_DEFAULT_NM


def test_a_floor_clamped_wizard_proposal_is_persisted_by_the_store(tmp_path: Path) -> None:
    """The same handoff on inputs where the proposer's floor clamp fires: it persists.

    This is the hardest input the handoff has. A calibration whose residual envelope sat under
    the noise floor comes out of the proposer sitting exactly on it, so it lands on the store's
    inclusive lower bound with nothing to spare — the one place a floor disagreement of any size
    separates the two packages.

    Which is what the first assertion holds, and it is an inequality rather than an equality on
    purpose. The handoff needs the proposer never to clamp *below* what the store admits; the two
    floors being the same number is today's way of satisfying that, not the requirement itself.
    Paired with the subset case further down, the two say the proposer's output is persistable
    and everything persistable is consumable — the whole chain WP-2C-03 hands to WP-2C-04.
    """
    # WP-1-06 owns `floor_for_joint`, WP-2C-04 owns `THRESHOLD_MIN_NM`. Neither imports the
    # other, so nothing but this holds them on the same side of the handoff.
    assert all(floor_for_joint(joint) >= THRESHOLD_MIN_NM[joint] for joint in range(N_ARM_JOINTS))

    stats = tuple(
        ResidualStats(
            joint_index=joint,
            max_abs_nm=floor_for_joint(joint) * CLAMPED_RESIDUAL_MAX_FRACTION_OF_FLOOR,
            sigma_nm=floor_for_joint(joint) * CLAMPED_RESIDUAL_SIGMA_FRACTION_OF_FLOOR,
            mean_nm=0.0,
            sample_count=RESIDUAL_SAMPLE_COUNT,
        )
        for joint in range(N_ARM_JOINTS)
    )
    proposal = propose_max_plus_sigma(stats)
    # Without this the statistics could drift over the floor and the case below would be vacuous.
    assert all(joint.floor_clamped for joint in proposal.per_joint)

    judgment = NoCollisionJudgment("operator-1", "sweep-A", attested=True, note="clean")
    canonical = attested_calibration(proposal, judgment).require_canonical()

    OperatorSettingsStore(tmp_path).set_thresholds(canonical)
    restarted = OperatorSettingsStore(tmp_path).load().resolved_thresholds_nm()
    assert restarted == canonical
    assert restarted != THRESHOLD_DEFAULT_NM
    # And the detector takes what the store just accepted, at the bound where that is tightest.
    assert ThresholdCalibration(thr0=restarted).thr0 == canonical


def test_every_threshold_the_store_accepts_is_accepted_by_the_detection_consumer(
    tmp_path: Path,
) -> None:
    """The store's accept-band must stay a subset of the band `ThresholdCalibration` enforces.

    Otherwise an operator saves a value here that the detector refuses at the next boot. The
    candidates sweep both floors this tree carries — `THRESHOLD_MIN_NM` and the `floor_for_joint`
    this package's own proposer clamps to. The two resolve to the same number and nothing couples
    them, so both are swept rather than one taken for the other. The implication is
    one-directional on purpose: it holds whether they agree or not.
    """
    store = OperatorSettingsStore(tmp_path)
    accepted_count = 0
    refused_count = 0
    for joint in range(N_ARM_JOINTS):
        for candidate in (
            floor_for_joint(joint) / 2.0,
            floor_for_joint(joint),
            THRESHOLD_MIN_NM[joint],
            THRESHOLD_DEFAULT_NM[joint],
            JOINT_EFFORT_LIMITS_NM[joint],
            JOINT_EFFORT_LIMITS_NM[joint] + 1.0,
        ):
            vector = list(THRESHOLD_DEFAULT_NM)
            vector[joint] = candidate
            try:
                store.set_thresholds(tuple(vector))
            except SettingRefusedError:
                refused_count += 1
                continue
            accepted_count += 1
            thr0 = OperatorSettingsStore(tmp_path).load().resolved_thresholds_nm()
            assert ThresholdCalibration(thr0=thr0).thr0 == tuple(vector)
    # Neither branch may be empty, or the sweep proves nothing about where the band sits.
    assert accepted_count > 0
    assert refused_count > 0
