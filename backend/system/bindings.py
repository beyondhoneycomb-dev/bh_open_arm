"""What is actually listening on this host, and who owns it.

`14` §2.11 calls this `ports.json` — the real binding map, as opposed to the declared one. The
two are separate on purpose: a compare view that read the declaration twice would agree with
itself, and the conflict `FR-OPS-066` is about (two components defaulting to one port) is only
visible against what is really bound.

Read from `/proc/net/tcp` and `/proc/net/tcp6` rather than from a library, because there is no
process-listing dependency in this tree and the two files are the same evidence one would read
anyway. Both tables are read: a server bound to `::` appears only in the v6 one, and reporting
it absent is how a compare view invents a conflict that is not there.

Ownership is best-effort by construction. Mapping a socket to a pid means reading `/proc/<pid>/fd`,
which is permitted for this user's own processes and refused for everyone else's — so a socket
another user holds is reported bound with an unknown owner, which is exactly what was observed.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.system.constants import PROC_NET_TCP_PATHS, PROC_ROOT, TCP_STATE_LISTEN

# `/proc/net/tcp` columns, in the order the kernel writes them.
LOCAL_ADDRESS_COLUMN = 1
STATE_COLUMN = 3
INODE_COLUMN = 9

# How `/proc/<pid>/fd/<n>` names a socket link.
SOCKET_LINK_PREFIX = "socket:["
SOCKET_LINK_SUFFIX = "]"

UNKNOWN_OWNER = "unknown"


@dataclass(frozen=True)
class ActualBinding:
    """One listening socket.

    Attributes:
        component: Who is listening — the canon's own component name when this process holds
            the socket, otherwise the owning process's name, otherwise `unknown`.
        port: The bound port.
        pid: The owning process, or None when the owner could not be read.
        listening: Always true here; the field exists because the compare view distinguishes a
            socket that is bound from a canon row that has nothing bound at all.
    """

    component: str
    port: int
    pid: int | None
    listening: bool


def _listening_sockets() -> list[tuple[int, int]]:
    """Every listening TCP socket as `(port, inode)`, across both address families."""
    found: list[tuple[int, int]] = []
    for path in PROC_NET_TCP_PATHS:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) <= INODE_COLUMN or fields[STATE_COLUMN] != TCP_STATE_LISTEN:
                continue
            _, _, port_hex = fields[LOCAL_ADDRESS_COLUMN].partition(":")
            if not port_hex or not fields[INODE_COLUMN].isdigit():
                continue
            found.append((int(port_hex, 16), int(fields[INODE_COLUMN])))
    return found


def _socket_owners() -> dict[int, int]:
    """Map socket inode to the pid holding it, for every process this user can read."""
    owners: dict[int, int] = {}
    for entry in PROC_ROOT.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            descriptors = list((entry / "fd").iterdir())
        except OSError:
            # Another user's process, or one that exited while being listed. Both mean the
            # owner is unknown, which the row says rather than guessing.
            continue
        for descriptor in descriptors:
            try:
                target = str(descriptor.readlink())
            except OSError:
                continue
            if target.startswith(SOCKET_LINK_PREFIX) and target.endswith(SOCKET_LINK_SUFFIX):
                inode = target[len(SOCKET_LINK_PREFIX) : -len(SOCKET_LINK_SUFFIX)]
                if inode.isdigit():
                    owners[int(inode)] = int(entry.name)
    return owners


def _name_of(pid: int) -> str:
    """Read `/proc/<pid>/comm`, or report the owner as unknown."""
    try:
        return (PROC_ROOT / str(pid) / "comm").read_text(encoding="utf-8").strip() or UNKNOWN_OWNER
    except OSError:
        return UNKNOWN_OWNER


def read_bindings(
    own_component: str, own_pid: int, ports_of_interest: frozenset[int]
) -> tuple[ActualBinding, ...]:
    """Read the listening TCP sockets this rig's port map is about.

    Not every listening socket: a desktop has scores of them — resolver, print spooler, package
    daemons — and none is a component of this rig. Reporting them would fill the compare view's
    "bound but not declared" list with the operating system, which buries the one row that
    matters. What is kept is any socket on a declared port, plus every socket this process holds
    — so a stranger squatting on the web backend's port still shows up, and so does this server
    when `--port` moved it somewhere the canon does not name.

    A socket that appears in both the v4 and the v6 table is one binding, and is reported once.
    Two DIFFERENT owners on one port stay two rows: that is the `OA-SYS-006` conflict, and
    merging them would delete the finding this report exists to surface.

    Args:
        own_component: The canon component name this process fills. Sockets held by `own_pid`
            are labelled with it, because the compare view lines bindings up against the canon
            by component name and the process's own `comm` is not that name.
        own_pid: This process.
        ports_of_interest: The declared ports.

    Returns:
        (tuple[ActualBinding, ...]) One row per binding, port ascending.
    """
    owners = _socket_owners()
    rows: dict[tuple[int, int | None], ActualBinding] = {}
    for port, inode in _listening_sockets():
        pid = owners.get(inode)
        if port not in ports_of_interest and pid != own_pid:
            continue
        if pid == own_pid:
            component = own_component
        elif pid is None:
            component = UNKNOWN_OWNER
        else:
            component = _name_of(pid)
        rows[(port, pid)] = ActualBinding(component=component, port=port, pid=pid, listening=True)
    return tuple(sorted(rows.values(), key=lambda row: (row.port, row.pid or 0)))


__all__ = ["UNKNOWN_OWNER", "ActualBinding", "read_bindings"]
