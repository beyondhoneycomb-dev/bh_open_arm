"""CAN link bring-up distribution (WP-OPS-02; `01` FR-SYS-006/008/011, `14` FR-OPS-084).

The one contract this package holds and never breaks: the *unit* sets the CAN link and the
*backend* only verifies it (`01` FR-SYS-006 — "code cannot set it for the user"). So the
public surface is the setup unit renderer, the udev rule distribution (packaging, persist,
rollback — the file, where WP-0B-05 owns the probe), the boot-order dependency that refuses
backend startup on a failed bring-up, and the real-fixture hook for the two acceptances that
can only be observed after a real reboot.
"""

from ops.systemd.boot_order import (
    UnitDependencies,
    backend_gated_on_link,
    parse_unit_dependencies,
    render_backend_link_dropin,
)
from ops.systemd.can_link import (
    LINK_UNIT_NAME,
    link_setup_commands,
    link_up_command,
    render_can_link_unit,
    txqueuelen_command,
    unit_sets_the_link,
)
from ops.systemd.constants import (
    BACKEND_UNIT,
    CAN_LINK_UNIT,
    INTERFACE_NAMES,
    LINK_BITRATE,
    LINK_DBITRATE,
    LINK_TXQUEUELEN,
    UDEV_RULES_DEST,
)
from ops.systemd.reverify import (
    FIXTURE_ENV_VAR,
    ReverifyReport,
    fixture_dir_from_env,
    link_params_ok,
    reverify_from_fixture,
)
from ops.systemd.udev_dist import (
    InstallResult,
    install_ruleset,
    render_distribution,
    rollback,
)

__all__ = [
    "BACKEND_UNIT",
    "CAN_LINK_UNIT",
    "FIXTURE_ENV_VAR",
    "INTERFACE_NAMES",
    "LINK_BITRATE",
    "LINK_DBITRATE",
    "LINK_TXQUEUELEN",
    "LINK_UNIT_NAME",
    "UDEV_RULES_DEST",
    "InstallResult",
    "ReverifyReport",
    "UnitDependencies",
    "backend_gated_on_link",
    "fixture_dir_from_env",
    "install_ruleset",
    "link_params_ok",
    "link_setup_commands",
    "link_up_command",
    "parse_unit_dependencies",
    "render_backend_link_dropin",
    "render_can_link_unit",
    "render_distribution",
    "reverify_from_fixture",
    "rollback",
    "txqueuelen_command",
    "unit_sets_the_link",
]
