"""The udev rule distribution renders from measured descriptors and persists atomically.

WP-OPS-02 owns the rule *file*: it packages WP-0B-05's rule content, installs it without
ever leaving a half-written file, keeps a backup of what it replaced, and rolls back to it.
The measured serial/dev_id values are hardware-bound; these tests drive the distribution
with synthetic descriptors, which is exactly what the render step consumes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ops.hw.udev.model import UdevInterface
from ops.systemd.constants import INTERFACE_NAMES
from ops.systemd.udev_dist import install_ruleset, render_distribution, rollback


def _descriptors() -> list[UdevInterface]:
    """Two synthetic adapters, two channels each — the four-channel rig, serial-axis."""
    return [
        UdevInterface(
            "can0",
            dev_id="0x0",
            serial="OA_A",
            port_path="1-1:1.0",
            driver="gs_usb",
            arphrd_type="280",
        ),
        UdevInterface(
            "can1",
            dev_id="0x1",
            serial="OA_A",
            port_path="1-1:1.0",
            driver="gs_usb",
            arphrd_type="280",
        ),
        UdevInterface(
            "can2",
            dev_id="0x0",
            serial="OA_B",
            port_path="1-2:1.0",
            driver="gs_usb",
            arphrd_type="280",
        ),
        UdevInterface(
            "can3",
            dev_id="0x1",
            serial="OA_B",
            port_path="1-2:1.0",
            driver="gs_usb",
            arphrd_type="280",
        ),
    ]


def test_distribution_binds_the_four_fixed_names_two_axis() -> None:
    """The rendered body names all four fixed channels, each pinned on both axes."""
    body = render_distribution(_descriptors())
    for name in INTERFACE_NAMES:
        assert f'NAME="{name}"' in body
    assert body.count("ATTR{dev_id}") == len(INTERFACE_NAMES)
    assert body.count("ATTRS{serial}") == len(INTERFACE_NAMES)


def test_descriptor_count_must_match_name_count() -> None:
    """A short descriptor list is a packaging error, not a silently truncated rule set."""
    with pytest.raises(ValueError, match="argument"):
        render_distribution(_descriptors()[:3])


def test_first_install_writes_without_backup(tmp_path: Path) -> None:
    """Installing into an empty destination writes the body and takes no backup."""
    dest = tmp_path / "80-openarm-can.rules"
    backups = tmp_path / "backups"
    result = install_ruleset(render_distribution(_descriptors()), dest, backups)
    assert result.backup is None
    assert 'NAME="oa_fl"' in dest.read_text(encoding="utf-8")


def test_reinstall_backs_up_and_rollback_restores(tmp_path: Path) -> None:
    """A second install preserves the prior file; rollback returns exactly that content."""
    dest = tmp_path / "80-openarm-can.rules"
    backups = tmp_path / "backups"

    first_body = render_distribution(_descriptors())
    install_ruleset(first_body, dest, backups)

    second_body = first_body + "\n# revised on a later measurement\n"
    result = install_ruleset(second_body, dest, backups)
    assert result.backup is not None
    assert dest.read_text(encoding="utf-8") == second_body

    restored = rollback(dest, backups)
    assert restored is not None
    assert dest.read_text(encoding="utf-8") == first_body


def test_rollback_without_backup_is_a_noop(tmp_path: Path) -> None:
    """Rollback with nothing to restore reports None rather than corrupting the file."""
    assert rollback(tmp_path / "80-openarm-can.rules", tmp_path / "backups") is None
