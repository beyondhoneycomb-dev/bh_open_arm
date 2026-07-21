"""udev fixed-name rule distribution: render, persist atomically, roll back (WP-OPS-02).

`01` §4.6 splits the udev work: WP-0B-05 owns the *probe* (does a rule match, does the name
attach, is it deterministic across reboots) and this package owns the *file* — packaging it,
persisting it, and rolling it back. So this module never re-derives rule content; it calls
WP-0B-05's `build_rule_for_interface`/`render_ruleset` to produce the body and adds the three
things a distribution needs the probe does not: an atomic install that cannot leave a
half-written rules file, a kept backup of whatever it replaced, and a rollback to it.

The concrete adapter serials and `dev_id`s are measured on the target host (deferred,
`AI-on-HW`); the render step takes those measured descriptors as input, so the distribution
logic here is exercised against synthetic descriptors and stays honest about what it packages.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ops.hw.udev.model import UdevInterface
from ops.hw.udev.rules import CONTRACT_NAMES, build_rule_for_interface, render_ruleset

# Backups are sequence-numbered rather than timestamped so rollback is deterministic and
# a test can assert exactly which file it restored; four digits orders lexically past any
# realistic install count.
_BACKUP_SUFFIX = ".rules"
_BACKUP_WIDTH = 4


@dataclass(frozen=True)
class InstallResult:
    """The outcome of installing a rules body.

    Attributes:
        dest: The rules file that now holds the installed body.
        backup: The backup the prior contents were saved to, or None on a first install
            where there was nothing to preserve.
    """

    dest: Path
    backup: Path | None


def render_distribution(
    interfaces: Sequence[UdevInterface],
    names: Sequence[str] = CONTRACT_NAMES,
) -> str:
    """Render the installable `.rules` body binding the fixed names to measured channels.

    Delegates every rule decision (two-axis requirement, serial-else-port fallback,
    `can`-prefix ban) to WP-0B-05 rather than repeating it, so a change to the rule shape
    lands in one place and the distribution just packages the result.

    Args:
        interfaces: Measured interface descriptors, one per fixed name, in name order.
        names: The fixed names to bind, defaulting to the four contract names.

    Returns:
        (str) The `.rules` file body.

    Raises:
        ValueError: If the number of descriptors does not match the number of names.
        MissingAxisError: If any descriptor cannot supply both rule axes.
        CanPrefixNameError: If any name is `can`-prefixed.
    """
    rules = tuple(
        build_rule_for_interface(name, interface)
        for name, interface in zip(names, interfaces, strict=True)
    )
    return render_ruleset(rules)


def _atomic_write(dest: Path, body: str) -> None:
    """Write `body` to `dest` so a reader ever sees only the whole old or whole new file.

    The temp file is created in the destination directory so the rename is same-filesystem
    (atomic); `fsync` before the rename makes the bytes durable, so a crash cannot leave a
    rules file that is present but truncated.

    Args:
        dest: Final path to place the body at.
        body: File contents.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp")
    handle = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(handle, body.encode("utf-8"))
        os.fsync(handle)
    finally:
        os.close(handle)
    tmp.replace(dest)


def _existing_backups(backup_dir: Path) -> list[Path]:
    """Return the sequence-numbered backups present, in ascending order.

    Args:
        backup_dir: Directory holding backups.

    Returns:
        (list[Path]) Backup paths whose stems are integers, sorted ascending.
    """
    if not backup_dir.is_dir():
        return []
    numbered = [path for path in backup_dir.glob(f"*{_BACKUP_SUFFIX}") if path.stem.isdigit()]
    return sorted(numbered, key=lambda path: int(path.stem))


def install_ruleset(body: str, dest: Path, backup_dir: Path) -> InstallResult:
    """Persist a rules body atomically, backing up whatever it replaces.

    A pre-existing rules file is copied to the next backup sequence number before the new
    body is written, so every replaced version remains available to `rollback`. The write
    itself is atomic, so an interrupted install never yields a partial rules file.

    Args:
        body: The rules file body to install.
        dest: The rules file path to write.
        backup_dir: Directory to keep replaced versions in.

    Returns:
        (InstallResult) The destination and the backup taken, if any.
    """
    backup: Path | None = None
    if dest.is_file():
        backup_dir.mkdir(parents=True, exist_ok=True)
        sequence = len(_existing_backups(backup_dir)) + 1
        backup = backup_dir / f"{sequence:0{_BACKUP_WIDTH}d}{_BACKUP_SUFFIX}"
        _atomic_write(backup, dest.read_text(encoding="utf-8"))
    _atomic_write(dest, body)
    return InstallResult(dest=dest, backup=backup)


def rollback(dest: Path, backup_dir: Path) -> Path | None:
    """Restore the most recently replaced version of the rules file.

    Rollback exists because a rules change can only be validated by a reboot (deferred);
    when it misbehaves the operator must return to the last-known-good file, and this
    restores the newest backup atomically.

    Args:
        dest: The rules file to restore into.
        backup_dir: Directory holding the sequence-numbered backups.

    Returns:
        (Path | None) The backup that was restored, or None when no backup exists.
    """
    backups = _existing_backups(backup_dir)
    if not backups:
        return None
    latest = backups[-1]
    _atomic_write(dest, latest.read_text(encoding="utf-8"))
    return latest
