"""Where runtime_config.json lives, and how it is written without ever being half-written.

The write is persist-then-swap — sibling temp file, flush, fsync, `os.replace`, fsync the parent
directory — the discipline `backend.threshold_calib.settings` and `backend.endeffector.rig`
already follow. It is not reused from either: both are bound to their own record shape. A torn
write here leaves the rig unsure whether motor `0x08` exists, and the next start would answer
that question from whichever half of the file survived.

The directory is the caller's, like every sibling persistence module in this tree: nothing here
decides where a deployment keeps operator state. `default_config_directory()` is the answer used
when the caller supplies none — the XDG config directory, which is where 13
§「설정 영속(서버측)」 puts it.

A subobject replacement is read-modify-write over the whole document, and the read is the
lenient one: a subobject that is already corrupt on disk is rewritten as its default rather than
blocking the operator from fixing an unrelated one. Which subobjects that cost is returned to
the caller, never swallowed.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.config.constants import (
    APP_DIRECTORY,
    CONFIG_FILENAME,
    XDG_CONFIG_HOME_FALLBACK,
    XDG_CONFIG_HOME_VAR,
)
from backend.config.model import (
    SUBOBJECT_BY_KEY,
    SUBOBJECT_KEYS,
    ParsedDocument,
    RuntimeConfigDocument,
    default_document,
    parse_document,
)

JSON_INDENT = 2


class UnknownSubobjectError(ValueError):
    """Raised when a caller names a top-level subobject the document does not have.

    A `ValueError` so a route that already funnels validation refusals into one 4xx catches this
    one too. Refused rather than created: an accepted unknown key would be written to disk and
    then dropped by the next read, so the operator would see their change vanish with no error.
    """


def default_config_directory() -> Path:
    """Return the XDG config directory for this application.

    `$XDG_CONFIG_HOME` wins when it is set and absolute; the specification says to ignore a
    relative value rather than resolve it against the working directory, which would put the
    operator's config wherever the backend happened to be started from.

    Returns:
        (Path) `$XDG_CONFIG_HOME/openarm` or `~/.config/openarm`.
    """
    configured = Path(os.environ.get(XDG_CONFIG_HOME_VAR, ""))
    if not configured.is_absolute():
        configured = Path.home() / XDG_CONFIG_HOME_FALLBACK
    return configured / APP_DIRECTORY


def config_path_for(directory: Path) -> Path:
    """Return the runtime_config file path under a directory."""
    return directory / CONFIG_FILENAME


def save_document_atomic(path: Path, document: RuntimeConfigDocument) -> None:
    """Write the whole document to disk atomically.

    Args:
        path: Destination file.
        document: The document to persist, serialized in its wire (camelCase) form.
    """
    body = json.dumps(document.to_wire(), indent=JSON_INDENT, sort_keys=True) + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)  # noqa: PTH105 — atomic rename primitive; Path.replace wraps it
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


def load_document(path: Path) -> ParsedDocument:
    """Read the document with per-subobject blast-radius isolation.

    A missing file is not a fault: nothing has been stored, so the defaults stand and nothing is
    reported as defaulted. A file that exists but does not parse as a JSON object loses every
    subobject at once — there is no surviving structure to isolate within — and says so.

    Args:
        path: The runtime_config file.

    Returns:
        (ParsedDocument) The document, and which subobjects fell back to their defaults.
    """
    if not path.is_file():
        return ParsedDocument(document=default_document(), defaulted=())
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ParsedDocument(document=default_document(), defaulted=SUBOBJECT_KEYS)
    return parse_document(raw)


@dataclass(frozen=True)
class RuntimeConfigStore:
    """The runtime_config document under one directory.

    Ownership: the store holds no cache — every call reads the current file, so a fresh instance
    over the same directory sees exactly what a restarted process would.

    Attributes:
        directory: The directory holding `runtime_config.json`.
    """

    directory: Path

    @property
    def path(self) -> Path:
        """The document file this store reads and writes."""
        return config_path_for(self.directory)

    def load(self) -> ParsedDocument:
        """Return the stored document, defaults in place of anything malformed."""
        return load_document(self.path)

    def replace_subobject(self, key: str, value: object) -> ParsedDocument:
        """Validate one subobject and persist it, leaving every other subobject as it was.

        Args:
            key: The top-level wire key, e.g. `endEffector`.
            value: The replacement subobject, as received on the wire.

        Returns:
            (ParsedDocument) The document as written, and which OTHER subobjects were already
                malformed on disk and were rewritten as defaults by this call.

        Raises:
            UnknownSubobjectError: When `key` is not a subobject of the document.
            pydantic.ValidationError: When `value` does not satisfy that subobject's schema. For
                `endEffector` this includes an unregistered `toolId` and a non-positive
                `toolMassKg`; both are refused rather than corrected, because the stored answer
                decides whether CAN id `0x08` is polled.
        """
        spec = SUBOBJECT_BY_KEY.get(key)
        if spec is None:
            known = ", ".join(SUBOBJECT_KEYS)
            raise UnknownSubobjectError(f"unknown config subobject {key!r}; known ones are {known}")
        validated = spec.model.model_validate(value)

        current = self.load()
        updated = current.document.model_copy(update={spec.field: validated})
        save_document_atomic(self.path, updated)
        # The key just written is authoritative now, so it is not reported as defaulted even if
        # the bytes it replaced were unreadable.
        return ParsedDocument(
            document=updated,
            defaulted=tuple(name for name in current.defaulted if name != key),
        )


def default_store() -> RuntimeConfigStore:
    """A store over the XDG config directory — the caller-supplies-nothing case."""
    return RuntimeConfigStore(directory=default_config_directory())


__all__ = [
    "RuntimeConfigStore",
    "UnknownSubobjectError",
    "config_path_for",
    "default_config_directory",
    "default_store",
    "load_document",
    "save_document_atomic",
]
