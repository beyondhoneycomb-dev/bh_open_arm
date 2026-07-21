"""udev fixed-name binding for CAN adapters (WP-0B-05; `01` FR-SYS-008, `02` FR-CON-005).

The public surface downstream binds to is the four fixed names — `oa_fl`, `oa_fr`,
`oa_ll`, `oa_lr` — which WP-0B-06/07 consume as the stable interface identity. The rest
of the package is the generator, parsers and hardware-acceptance scaffold that produce
and verify the udev rules those names come from.
"""

from ops.hw.udev.determinism import (
    REQUIRED_REBOOT_CYCLES,
    DeterminismResult,
    RebootObservation,
    evaluate_determinism,
    physical_channel_key,
)
from ops.hw.udev.ethtool import (
    IN_TREE_DRIVER_FAMILY,
    DriverReport,
    is_in_tree_driver,
    parse_ethtool_i,
)
from ops.hw.udev.measurement import (
    ChannelEntry,
    MeasurementTable,
    build_measurement_table,
    dev_id_distinguishes_channels,
    serial_shared_per_adapter,
)
from ops.hw.udev.model import AdapterAxisKind, UdevInterface
from ops.hw.udev.parser import parse_udevadm_info
from ops.hw.udev.reverify import (
    FIXTURE_ENV_VAR,
    ReverifyReport,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from ops.hw.udev.rules import (
    ARPHRD_CAN_TYPE,
    BANNED_NAME_PREFIX,
    CONTRACT_NAMES,
    NAME_FRONT_LEFT,
    NAME_FRONT_RIGHT,
    NAME_LEFT_LEFT,
    NAME_LEFT_RIGHT,
    CanPrefixNameError,
    MissingAxisError,
    UdevRule,
    UdevRuleError,
    build_rule,
    build_rule_for_interface,
    render_ruleset,
)
from ops.hw.udev.staticcheck import (
    RuleViolation,
    find_can_prefixed_names,
    find_single_axis_rules,
)

__all__ = [
    "ARPHRD_CAN_TYPE",
    "BANNED_NAME_PREFIX",
    "CONTRACT_NAMES",
    "FIXTURE_ENV_VAR",
    "IN_TREE_DRIVER_FAMILY",
    "NAME_FRONT_LEFT",
    "NAME_FRONT_RIGHT",
    "NAME_LEFT_LEFT",
    "NAME_LEFT_RIGHT",
    "REQUIRED_REBOOT_CYCLES",
    "AdapterAxisKind",
    "CanPrefixNameError",
    "ChannelEntry",
    "DeterminismResult",
    "DriverReport",
    "MeasurementTable",
    "MissingAxisError",
    "RebootObservation",
    "ReverifyReport",
    "RuleViolation",
    "UdevInterface",
    "UdevRule",
    "UdevRuleError",
    "build_measurement_table",
    "build_rule",
    "build_rule_for_interface",
    "dev_id_distinguishes_channels",
    "evaluate_determinism",
    "find_can_prefixed_names",
    "find_single_axis_rules",
    "fixture_dir_from_env",
    "is_in_tree_driver",
    "parse_ethtool_i",
    "parse_udevadm_info",
    "physical_channel_key",
    "render_ruleset",
    "reverify_from_fixture",
    "serial_shared_per_adapter",
]
