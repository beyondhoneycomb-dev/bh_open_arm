"""Where the document lives and how it survives a failed write.

The atomic-write assertions are about the failure path, not the happy one. A writer that leaves
a half-written `runtime_config.json` leaves the rig unsure whether motor `0x08` exists, and a
writer that leaves a stray `.tmp` beside it leaves that uncertainty for a later glob to find.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.config.constants import (
    APP_DIRECTORY,
    CONFIG_FILENAME,
    DENSITY_DEFAULT,
    FIELD_TOOL_ID,
    SUBOBJECT_END_EFFECTOR,
    SUBOBJECT_LAYOUT,
    XDG_CONFIG_HOME_FALLBACK,
    XDG_CONFIG_HOME_VAR,
)
from backend.config.model import SUBOBJECT_KEYS, default_document
from backend.config.store import (
    RuntimeConfigStore,
    UnknownSubobjectError,
    default_config_directory,
    save_document_atomic,
)
from backend.endeffector import SIDE_LEFT, TOOL_GRIPPER
from tests.wpg00_backend.conftest import (
    GRIPPER_ON_BOTH_ARMS,
    NON_DEFAULT_LAYOUT,
    write_raw_document,
)

TEMP_FILE_GLOB = "*.tmp"


def _refuse_rename(source: object, destination: object) -> None:
    """Stand in for `os.replace` failing mid-write — the torn-write case."""
    raise OSError("simulated failure during the atomic rename")


def test_missing_file_yields_defaults_without_reporting_a_fault(
    store: RuntimeConfigStore,
) -> None:
    """Nothing stored is not the same as something corrupt; only the latter is reported."""
    parsed = store.load()

    assert parsed.defaulted == ()
    assert parsed.document == default_document()


def test_round_trip_survives_a_cold_read(store: RuntimeConfigStore) -> None:
    """A saved document reloads from the bytes on disk — the restart case."""
    store.replace_subobject(SUBOBJECT_END_EFFECTOR, GRIPPER_ON_BOTH_ARMS)
    store.replace_subobject(SUBOBJECT_LAYOUT, NON_DEFAULT_LAYOUT)

    reloaded = RuntimeConfigStore(directory=store.directory).load()

    assert reloaded.defaulted == ()
    assert reloaded.document.end_effector.left.tool_id == TOOL_GRIPPER
    assert reloaded.document.layout.sidebar_collapsed is True


def test_successful_write_leaves_no_temp_file(store: RuntimeConfigStore) -> None:
    """The temp file is renamed, not left beside the document."""
    save_document_atomic(store.path, default_document())

    assert list(store.directory.glob(TEMP_FILE_GLOB)) == []
    assert store.path.is_file()


def test_torn_write_leaves_no_stray_temp_file(
    store: RuntimeConfigStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rename that fails takes its temp file with it, and the previous document is untouched."""
    store.replace_subobject(SUBOBJECT_END_EFFECTOR, GRIPPER_ON_BOTH_ARMS)
    before = store.path.read_text(encoding="utf-8")
    monkeypatch.setattr("backend.config.store.os.replace", _refuse_rename)

    with pytest.raises(OSError, match="simulated failure"):
        store.replace_subobject(SUBOBJECT_LAYOUT, NON_DEFAULT_LAYOUT)

    assert list(store.directory.glob(TEMP_FILE_GLOB)) == []
    assert store.path.read_text(encoding="utf-8") == before


def test_replace_subobject_touches_no_other_subobject(store: RuntimeConfigStore) -> None:
    """One PUT, one subobject. The rest are read back and written out as they were."""
    store.replace_subobject(SUBOBJECT_END_EFFECTOR, GRIPPER_ON_BOTH_ARMS)

    written = store.replace_subobject(SUBOBJECT_LAYOUT, NON_DEFAULT_LAYOUT)

    assert written.document.end_effector.left.tool_id == TOOL_GRIPPER
    assert written.document.end_effector.right.tool_id == TOOL_GRIPPER


def test_unknown_subobject_is_refused_with_the_known_keys_named(
    store: RuntimeConfigStore,
) -> None:
    """An accepted unknown key would be written and then dropped by the next read, silently."""
    with pytest.raises(UnknownSubobjectError) as refusal:
        store.replace_subobject("layouts", {})

    message = str(refusal.value)
    assert "layouts" in message
    assert SUBOBJECT_LAYOUT in message
    assert SUBOBJECT_END_EFFECTOR in message


def test_corrupt_bytes_default_every_subobject_and_say_so(store: RuntimeConfigStore) -> None:
    """A file that is not JSON at all has no structure left to isolate within."""
    store.directory.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not json", encoding="utf-8")

    parsed = store.load()

    assert parsed.defaulted != ()
    assert parsed.document == default_document()


def test_write_over_a_corrupt_end_effector_stops_reporting_it(
    store: RuntimeConfigStore,
) -> None:
    """The key just written is authoritative; the bytes it replaced are no longer a fault."""
    write_raw_document(
        store,
        {
            SUBOBJECT_LAYOUT: NON_DEFAULT_LAYOUT,
            SUBOBJECT_END_EFFECTOR: {SIDE_LEFT: {FIELD_TOOL_ID: "vacuum_cup"}},
        },
    )
    assert store.load().defaulted == (SUBOBJECT_END_EFFECTOR,)

    written = store.replace_subobject(SUBOBJECT_END_EFFECTOR, GRIPPER_ON_BOTH_ARMS)

    assert written.defaulted == ()
    assert store.load().document.layout.sidebar_collapsed is True


def test_xdg_config_home_wins_when_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller's environment decides, and the application gets its own directory under it."""
    monkeypatch.setenv(XDG_CONFIG_HOME_VAR, str(tmp_path))

    assert default_config_directory() == tmp_path / APP_DIRECTORY


def test_xdg_falls_back_to_dot_config_under_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unset means the XDG default, not the working directory."""
    monkeypatch.delenv(XDG_CONFIG_HOME_VAR, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert default_config_directory() == tmp_path / XDG_CONFIG_HOME_FALLBACK / APP_DIRECTORY


def test_relative_xdg_config_home_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative value would put the operator's config wherever the backend was started."""
    monkeypatch.setenv(XDG_CONFIG_HOME_VAR, "relative/config")
    monkeypatch.setenv("HOME", str(tmp_path))

    assert default_config_directory() == tmp_path / XDG_CONFIG_HOME_FALLBACK / APP_DIRECTORY


def test_store_path_is_the_named_file_under_the_caller_directory(tmp_path: Path) -> None:
    """The directory is the caller's; the file name is this package's."""
    assert RuntimeConfigStore(directory=tmp_path).path == tmp_path / CONFIG_FILENAME


def test_an_undecodable_file_falls_back_instead_of_escaping(tmp_path: Path) -> None:
    """One invalid byte in the stored file must not take the REST surface down with it.

    `UnicodeDecodeError` is not a subclass of `OSError` or `JSONDecodeError`, so leaving it out
    of the except clause let it propagate through every route — a corrupt config wedged the whole
    API rather than defaulting. Confirmed by mutation before this test existed.
    """
    store = RuntimeConfigStore(tmp_path)
    store.path.write_bytes(b'{"layout": {"density": "\xff"}}')

    parsed = store.load()

    assert set(parsed.defaulted) == set(SUBOBJECT_KEYS)
    assert parsed.document.layout.density == DENSITY_DEFAULT
