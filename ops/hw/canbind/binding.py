"""Which arm is on which CAN channel, decided once by the operator and re-checked every start.

`03` §2.1 is the constraint this module exists under: both arms answer on send `0x01–0x08` and
recv `0x11–0x18`, so **a bus scan cannot tell left from right**, and the spec records that three
upstream projects disagree about which channel is which (`can0=right` / `can0=follower left` /
`can0=leader`). Nothing readable from the bus settles it.

udev rules settle it by renaming, but this rig cannot use the strong form: `16` M-12 makes
`ATTRS{serial}` the preferred axis and the PCAN-USB Pro FD on this bench **reports no serial**,
so a rule falls back to `KERNELS==` — the USB port path — which changes the moment the adapter
moves to another port. That is not a hypothetical here: the same adapter was observed at
`3-4:1.0` and later at `3-10.3.1.2:1.0`.

So identity is settled the one way that does not depend on any of it: **the operator moves an
arm by hand and whichever channel's joint positions change is that arm.** Torque is off, no
model is consulted, and the answer is about the physical arm rather than about a port. What is
persisted is that answer, keyed to the channel it was observed on.

The persisted key is still the fragile `(ID_PATH, dev_id)` pair — that cannot be helped without
a serial. What this module refuses to do is *pretend otherwise*: when the channels present do
not match the channels the binding was recorded against, it reports a mismatch and the operator
re-identifies. A binding that silently follows a renumbered bus is how the left arm's limits end
up enforced against the right arm.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ops.hw.canbind.discovery import CanChannel

BINDING_FILENAME = "can_binding.json"
BINDING_VERSION = 1

FIELD_VERSION = "version"
FIELD_ROLES = "roles"


class ArmRole(Enum):
    """The roles a CAN channel can carry on this rig.

    Follower arms are the powered pair. The leader roles exist because `openarm_teleop` puts a
    leader on `can0`; this rig has none today, and a role nobody binds is simply absent from the
    stored record rather than bound to a placeholder.
    """

    FOLLOWER_LEFT = "follower_left"
    FOLLOWER_RIGHT = "follower_right"
    LEADER_LEFT = "leader_left"
    LEADER_RIGHT = "leader_right"


class BindingError(Exception):
    """Raised when a binding cannot be trusted for the channels actually present."""


@dataclass(frozen=True)
class ChannelBinding:
    """The operator's answer: role -> the channel key it was physically confirmed on.

    Attributes:
        roles: Role to `CanChannel.channel_key`. A role absent from the map was never bound.
    """

    roles: dict[ArmRole, str]

    def key_for(self, role: ArmRole) -> str | None:
        """Return the channel key bound to a role, or None when it was never bound."""
        return self.roles.get(role)

    def interface_for(self, role: ArmRole, present: tuple[CanChannel, ...]) -> str:
        """Resolve a role to the kernel interface name to open right now.

        Args:
            role: The arm role to resolve.
            present: The channels enumerated this run.

        Returns:
            (str) The current interface name (`can0`), which may differ from the one seen when
                the binding was recorded — that is the whole point of keying on the channel.

        Raises:
            BindingError: When the role was never bound, or its channel is not present. Both are
                refusals rather than a fallback to "the first CAN interface", because the
                fallback is indistinguishable from the correct answer until the arm moves.
        """
        key = self.key_for(role)
        if key is None:
            raise BindingError(f"{role.value} has no bound channel; run identification first")
        for channel in present:
            if channel.channel_key == key:
                return channel.interface
        raise BindingError(
            f"{role.value} was bound to channel {key!r}, which is not present now. "
            "The adapter moved ports, or a different adapter is plugged in. Re-identify; "
            "do not guess, because the arms are indistinguishable on the bus (03 §2.1)."
        )


@dataclass(frozen=True)
class BindingCheck:
    """What changed between a stored binding and the channels present.

    Attributes:
        resolved: Roles whose bound channel is present, mapped to the interface to open.
        missing: Roles whose bound channel is absent.
        unbound_keys: Channel keys present that no role claims.
    """

    resolved: dict[ArmRole, str]
    missing: tuple[ArmRole, ...]
    unbound_keys: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """Whether every bound role resolved. Unclaimed channels are not a failure."""
        return not self.missing


def check_binding(binding: ChannelBinding, present: tuple[CanChannel, ...]) -> BindingCheck:
    """Compare a stored binding against the channels enumerated now.

    Args:
        binding: The stored role-to-channel answer.
        present: The channels this host exposes right now.

    Returns:
        (BindingCheck) What resolved, what went missing, and what is present but unclaimed.
    """
    by_key = {channel.channel_key: channel.interface for channel in present}
    resolved: dict[ArmRole, str] = {}
    missing: list[ArmRole] = []
    for role, key in binding.roles.items():
        interface = by_key.get(key)
        if interface is None:
            missing.append(role)
        else:
            resolved[role] = interface
    claimed = set(binding.roles.values())
    unbound = tuple(sorted(key for key in by_key if key not in claimed))
    return BindingCheck(resolved=resolved, missing=tuple(missing), unbound_keys=unbound)


def binding_path(directory: Path) -> Path:
    """Return the binding file path under a directory."""
    return directory / BINDING_FILENAME


def save_binding(path: Path, binding: ChannelBinding) -> None:
    """Write the binding atomically: temp file, fsync, rename, fsync the directory.

    A torn write here leaves the rig with a half-read map of which arm is which, and the failure
    surfaces as an arm moving to the other arm's command rather than as a parse error.
    """
    body = json.dumps(
        {
            FIELD_VERSION: BINDING_VERSION,
            FIELD_ROLES: {
                role.value: key
                for role, key in sorted(binding.roles.items(), key=lambda item: item[0].value)
            },
        },
        indent=2,
        sort_keys=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    handle_fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            handle.write(body + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)  # noqa: PTH105 — atomic rename primitive
        _fsync_dir(path.parent)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _fsync_dir(directory: Path) -> None:
    """Fsync a directory so a rename into it survives a crash."""
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def load_binding(path: Path) -> ChannelBinding:
    """Read and validate a stored binding.

    Args:
        path: The binding file.

    Returns:
        (ChannelBinding) The stored role-to-channel map.

    Raises:
        BindingError: On a malformed envelope, an unknown role name, a non-string key, or two
            roles claiming one channel. The last is the sharp one: it means both arms would be
            driven through the same socket, and it is refused at read time rather than at the
            moment both arms move together.
    """
    try:
        loaded: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as bad:
        raise BindingError(f"{path} could not be read as JSON: {bad}") from bad
    if not isinstance(loaded, dict):
        raise BindingError(f"{path} did not parse to an object")
    if loaded.get(FIELD_VERSION) != BINDING_VERSION:
        raise BindingError(
            f"{path} declares version {loaded.get(FIELD_VERSION)!r}, expected {BINDING_VERSION}"
        )
    raw_roles = loaded.get(FIELD_ROLES)
    if not isinstance(raw_roles, dict):
        raise BindingError(f"{path} carries no {FIELD_ROLES} object")

    roles: dict[ArmRole, str] = {}
    for name, key in raw_roles.items():
        try:
            role = ArmRole(name)
        except ValueError as bad:
            raise BindingError(f"{path} names an unknown role {name!r}") from bad
        if not isinstance(key, str) or not key:
            raise BindingError(f"{path}: {name} has no channel key")
        roles[role] = key

    seen: dict[str, ArmRole] = {}
    for role, key in roles.items():
        if key in seen:
            raise BindingError(
                f"{path}: {seen[key].value} and {role.value} both claim channel {key!r}; "
                "one socket cannot be two arms"
            )
        seen[key] = role
    return ChannelBinding(roles=roles)
