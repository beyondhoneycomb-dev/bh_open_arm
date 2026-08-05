"""Observer mode — read-only, refused on *every* command path (`FR-OPS-077`).

`FR-OPS-077` is not "an observer may not send commands" on one path; it is that an
observer holds command authority on **no** path. `CG-5-08f` checks that literally:
every write surface refuses an observer, not just the obvious one. So the write
surfaces are enumerated here as a closed set, and one predicate refuses an observer
on each — a new command path that forgets to consult it is a gap the enumeration
makes visible.

The WS-frame surfaces delegate to `contracts.ws.authorize_send`, so the "who may send
a control frame" rule has one definition (`CTR-WS@v2`) and this module states its
agreement by reference rather than restating it. The non-WS surfaces (the L2 lock,
the deadman renewal, VR pose injection, forced release) use the same single
command-authority role, `CTR-WS@v2`'s `CONTROL_HOLDER_ROLE`.

Reading is not a command path: an observer may subscribe to telemetry, camera and
diagnostics.

Neither is the soft stop, and it is the one write that is not. `CTR-WS@v2` carries
`stop_hold` as a client-authored frame with `control_frame: false`, because `13`
FR-GUI-065 requires the stop to be reachable by a client holding no control. What is
closed here is command AUTHORITY, not the set of bytes a client may send; `stop_hold`
is therefore deliberately absent from `CommandPath` below.
"""

from __future__ import annotations

from enum import Enum

from contracts.ws import (
    CONTROL_HOLDER_ROLE,
    WsError,
    WsFrameType,
    WsRole,
    authorize_send,
)


class ObserverWriteError(RuntimeError):
    """Raised when a non-authorised role attempts a write on a command path."""


class CommandPath(Enum):
    """Every write surface an observer must be refused on (`FR-OPS-077`, `CG-5-08f`).

    A closed enumeration is the point: "refused on every path" is only checkable if
    the paths are named in one place. The WS-frame members map to `CTR-WS@v2` control
    frames; the rest are the non-WS command surfaces this WP adds.

    `stop_hold` is not a member and must not become one. Every member here is a path an
    observer is refused, and the stop is the one client-authored frame an observer may
    send (`13` FR-GUI-065). Adding it would also be caught rather than silent:
    `authorize_send` admits it for every role, so `observer_refused_paths` would return
    less than the full set and `CG-5-08f` would fail.
    """

    WS_COMMAND = "ws_command"
    WS_LEASE_RENEW = "ws_lease_renew"
    WS_REARM_CONFIRM = "ws_rearm_confirm"
    COMMAND_SOURCE_LOCK_ACQUIRE = "command_source_lock_acquire"
    DEADMAN_RENEWAL = "deadman_renewal"
    VR_POSE_INJECT = "vr_pose_inject"
    FORCED_RELEASE = "forced_release"


# The WS command paths, mapped to the `CTR-WS@v2` control frame each one is, so the
# refusal on those paths is decided by `authorize_send` and never re-implemented.
_WS_FRAME_FOR_PATH = {
    CommandPath.WS_COMMAND: WsFrameType.COMMAND,
    CommandPath.WS_LEASE_RENEW: WsFrameType.LEASE_RENEW,
    CommandPath.WS_REARM_CONFIRM: WsFrameType.REARM_CONFIRM,
}

# The forced release is admin-only (`FR-OPS-076`), so both observer and operator are
# refused it; every other command path is the operator's alone. Either way, an
# observer is refused on all of them, which is what `CG-5-08f` checks.
_ADMIN_ONLY_PATHS = frozenset({CommandPath.FORCED_RELEASE})

# The full write surface, as a closed set for the "every path" iteration.
ALL_COMMAND_PATHS = tuple(CommandPath)


def may_read(role: WsRole) -> bool:
    """Whether a role may read state/video/diagnostics — true for all, observers too.

    Args:
        role: The connected client's role.

    Returns:
        (bool) Always True: reading is not a command path (`FR-OPS-077`).
    """
    return role in (WsRole.OBSERVER, WsRole.OPERATOR, WsRole.ADMIN)


def assert_write_authorized(role: WsRole, path: CommandPath) -> None:
    """Refuse a role that may not write on a command path; return None if it may.

    For the WS-frame paths this defers to `contracts.ws.authorize_send`, so the
    control-frame authority rule has a single owner. For the forced-release path it
    requires admin; for every other path it requires the single command-authority
    role. An observer is refused on all of them.

    Args:
        role: The sending client's role.
        path: The command path being attempted.

    Raises:
        ObserverWriteError: If the role may not write on this path.
    """
    ws_frame = _WS_FRAME_FOR_PATH.get(path)
    if ws_frame is not None:
        try:
            authorize_send(role, ws_frame)
        except WsError as error:
            raise ObserverWriteError(str(error)) from error
        return

    required = WsRole.ADMIN if path in _ADMIN_ONLY_PATHS else CONTROL_HOLDER_ROLE
    if role is not required:
        raise ObserverWriteError(
            f"role {role.value!r} may not write on command path {path.value!r}; "
            f"the authorised role is {required.value!r}"
        )


def observer_refused_paths(role: WsRole) -> tuple[CommandPath, ...]:
    """Return the command paths on which a given role is refused a write.

    For an observer this must be every path (`CG-5-08f`). Used by the acceptance test
    to prove the "every path" property without duplicating the refusal logic.

    Args:
        role: The role to evaluate.

    Returns:
        (tuple[CommandPath, ...]) The paths that raise for this role, in enum order.
    """
    refused: list[CommandPath] = []
    for path in ALL_COMMAND_PATHS:
        try:
            assert_write_authorized(role, path)
        except ObserverWriteError:
            refused.append(path)
    return tuple(refused)
