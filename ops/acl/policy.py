"""The frozen ACL / systemd-sandbox policy (`01` FR-SYS-007(iii), FR-SYS-005).

This module is the single declaration of *what a sandboxed CAN-writer unit must be*,
kept as data so the unit file, the static check and the runtime harness all read one
source rather than three copies of a directive list that could drift apart.

The security model has two layers, and this policy names both:

- **Cooperative (flock, WP-0B-01)** — a lock file under `CANONICAL_LOCK_DIR` that only
  a process which agrees to check it respects. Necessary, but a rogue process ignores it.
- **Mandatory (this policy)** — kernel-enforced. `RestrictAddressFamilies` is a seccomp
  allowlist of socket families, and `DevicePolicy=closed` is the device-cgroup ACL. A
  process cannot opt out of either.

The mandatory layer *complements* the cooperative one; it does not replace it. The proof
that they coexist is `LOCK_DIR_MUST_BE_WRITABLE`: `ProtectSystem=strict` would make the
flock file uncreatable, so a correct sandbox has to re-grant exactly the lock directory,
and `staticcheck` fails a unit that forgets to (acceptance ③).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.can.lock import CANONICAL_LOCK_DIR

# The socket family a CAN writer exists to use. Its presence in the writer unit's
# allowlist and its absence from the deny drop-in are the whole AF_CAN gate.
CAN_FAMILY = "AF_CAN"

# The allowlist the authorized writer unit carries: the bus, link-state queries over
# rtnetlink, and local IPC/logging. Every family outside this set is refused at socket().
AUTHORIZED_FAMILIES = ("AF_CAN", "AF_NETLINK", "AF_UNIX")

# Families a bus writer must never be allowed to open. Their presence in a writer unit's
# allowlist widens the sandbox past what a CAN writer needs and is a policy violation.
FORBIDDEN_FAMILIES = ("AF_INET", "AF_INET6")

# The device-cgroup ACL mode. `closed` denies every node not re-admitted by DeviceAllow.
DEVICE_POLICY_CLOSED = "closed"

# The filenames of the two shipped artifacts, so tests and installers name them once.
WRITER_UNIT_FILENAME = "openarm-can-writer.service"
DENY_DROPIN_FILENAME = "10-openarm-deny-can.conf"

# The directive that keeps the mandatory layer a complement of the cooperative one: the
# canonical flock directory has to stay writable under ProtectSystem=strict, or the ACL
# layer silently disables flock (acceptance ③). Resolved from the lock layer so a change
# to the lock path can never leave this stale.
LOCK_DIR_MUST_BE_WRITABLE = CANONICAL_LOCK_DIR


@dataclass(frozen=True)
class RequiredDirective:
    """One directive an authorized CAN-writer unit must carry to count as sandboxed.

    Attributes:
        section: The unit-file section the directive lives in (`Service`).
        key: The directive name (`RestrictAddressFamilies`).
        rationale: Why the sandbox is incomplete without it, for the violation report.
    """

    section: str
    key: str
    rationale: str


# The directives whose mere presence a unit-text scan can assert. The *values* of the
# two load-bearing ones (the family allowlist, the writable lock dir) are checked by
# dedicated predicates in `staticcheck`, because presence alone would pass a unit that
# allowed AF_INET or forgot the lock directory.
REQUIRED_DIRECTIVES = (
    RequiredDirective(
        "Service",
        "RestrictAddressFamilies",
        "seccomp socket-family allowlist — without it any family, including AF_CAN, is open",
    ),
    RequiredDirective(
        "Service",
        "DevicePolicy",
        "device-cgroup ACL mode — without closed policy every /dev node is reachable",
    ),
    RequiredDirective(
        "Service",
        "NoNewPrivileges",
        "without it a child can regain privileges the sandbox just dropped",
    ),
    RequiredDirective(
        "Service",
        "ProtectSystem",
        "without it the writer can rewrite the OS file hierarchy",
    ),
    RequiredDirective(
        "Service",
        "User",
        "without a dedicated non-root identity the writer runs as root",
    ),
    RequiredDirective(
        "Service",
        "CapabilityBoundingSet",
        "without an emptied bounding set the writer keeps capabilities it never needs",
    ),
)
