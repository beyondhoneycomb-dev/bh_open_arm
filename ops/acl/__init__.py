"""Writer ACL + systemd sandbox — the mandatory CAN-TX gate (WP-OPS-01; `01` FR-SYS-007(iii)).

`01` FR-SYS-007(iii) requires that unauthorized processes be blocked from CAN TX *at all*, and
names the mechanism: a device ACL plus a systemd sandbox (`DeviceAllow` /
`RestrictAddressFamilies=AF_CAN`). That is the mandatory, kernel-enforced complement to the
cooperative flock of WP-0B-01 — flock stops
a well-behaved process from double-opening a bus; nothing but this layer stops a rogue one from
opening `AF_CAN` and transmitting. The two layers are kept **simultaneously**: the sandbox even
re-grants the flock directory so it cannot silently disable the layer it complements.

The package surface:

- `units/openarm-can-writer.service` — the authorized writer unit carrying the full sandbox, and
  `units/10-openarm-deny-can.conf` — the deny drop-in that subtracts `AF_CAN` from every other unit.
- `policy` — the one frozen declaration of what a sandboxed writer unit must be.
- `unitfile` / `staticcheck` — parse installed unit text and reject a unit that drops a directive,
  widens the family allowlist, or seals the filesystem without re-granting the lock directory.
- `security_report` — run `systemd-analyze security` and capture the analyzer's verdict as evidence.
- `block_harness` — the probe that tries to reach the bus, and the `systemd-run` driver that runs it
  under a real seccomp filter (proves the socket-creation block here, no vcan).
- `reverify` — the hook that re-checks the bus-bound half (unauthorized cannot transmit, authorized
  can, 0 over-block) against a vcan interface on the rig.
"""

from ops.acl.block_harness import (
    AttemptOutcome,
    attempt_can_socket,
    run_attempt_under_families,
    user_manager_available,
)
from ops.acl.policy import (
    AUTHORIZED_FAMILIES,
    CAN_FAMILY,
    DENY_DROPIN_FILENAME,
    FORBIDDEN_FAMILIES,
    LOCK_DIR_MUST_BE_WRITABLE,
    REQUIRED_DIRECTIVES,
    WRITER_UNIT_FILENAME,
    RequiredDirective,
)
from ops.acl.reverify import (
    VCAN_ENV_VAR,
    AclReverifyReport,
    reverify_from_capture,
    reverify_on_interface,
    vcan_interface_from_env,
)
from ops.acl.security_report import (
    DirectiveFinding,
    SecurityReport,
    run_security_analysis,
    systemd_analyze_available,
    write_report,
)
from ops.acl.staticcheck import (
    AddressFamilyRule,
    DirectiveViolation,
    address_family_rule,
    find_dropin_not_denying_can,
    find_lock_dir_not_writable,
    find_missing_sandbox_directives,
)
from ops.acl.unitfile import UnitFile, parse_unit

__all__ = [
    "AUTHORIZED_FAMILIES",
    "CAN_FAMILY",
    "DENY_DROPIN_FILENAME",
    "FORBIDDEN_FAMILIES",
    "LOCK_DIR_MUST_BE_WRITABLE",
    "REQUIRED_DIRECTIVES",
    "WRITER_UNIT_FILENAME",
    "AclReverifyReport",
    "AddressFamilyRule",
    "AttemptOutcome",
    "DirectiveFinding",
    "DirectiveViolation",
    "RequiredDirective",
    "SecurityReport",
    "UnitFile",
    "VCAN_ENV_VAR",
    "address_family_rule",
    "attempt_can_socket",
    "find_dropin_not_denying_can",
    "find_lock_dir_not_writable",
    "find_missing_sandbox_directives",
    "parse_unit",
    "reverify_from_capture",
    "reverify_on_interface",
    "run_attempt_under_families",
    "run_security_analysis",
    "systemd_analyze_available",
    "user_manager_available",
    "vcan_interface_from_env",
    "write_report",
]
