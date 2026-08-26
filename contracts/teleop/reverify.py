"""The CTR-TEL@v1 frozen mirror renderer and its reverification hook.

`02b` freeze mechanics: `WP-3A-03` builds the contract and leaves it DRAFT;
`WP-3A-06` freezes `CTR-TEL@v1` sequentially, by content hash of the frozen glob
`contracts/teleop/schema.json`. That mirror does not exist during this WP — a DRAFT
contract whose `CONTRACT_FROZEN` glob had files on disk would fail CI-09 ("content
but no FROZEN hash") — so this module is the single, deterministic source of the
mirror: `WP-3A-06` writes `render_frozen_json()` to `schema.json` and freezes it.

`reverify` is the hook. Before the freeze it is verification-only: it reports the
DRAFT registration and, finding no mirror on disk, asserts no drift. After the
freeze it recomputes the mirror from `schema.py` and compares it byte-for-byte to
the frozen `schema.json`, so the Python contract and the frozen artefact cannot
diverge. Reads only the committed JSON authority; no robot stack, light lane.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from contracts.prim import BIMANUAL_ACTION_DIM, SINGLE_ARM_ACTION_DIM
from contracts.teleop import schema

# The owning work package (`02b` §5.2). `WP-3A-06` freezes it; `WP-3A-03` owns it.
OWNER_WP = "WP-3A-03"

# The frozen glob `WP-3A-06` locks by content hash, and the committed freeze
# authority CI-09 reads. The mirror path is intentionally absent until the freeze.
FROZEN_MIRROR_PATH = "contracts/teleop/schema.json"

STATUS_FROZEN = "FROZEN"
STATUS_DRAFT = "DRAFT"


def frozen_schema() -> dict[str, object]:
    """Assemble the language-agnostic CTR-TEL@v1 contract facts.

    Every value is sourced from `schema.py` — the position action width is consumed
    from `CTR-PRIM@v1`, the validity codes are the frozen `OA-TEL-*` strings — so this
    is a mirror, not a second definition.

    Returns:
        (dict[str, object]) The frozen contract, ready to serialise.
    """
    return {
        "contract": schema.CONTRACT_ID,
        "schema_version": schema.SCHEMA_VERSION,
        "consumed_contracts": list(schema.CONSUMED_CONTRACTS),
        "plugin": {
            "dist_prefix": schema.TELEOPERATOR_DIST_PREFIX,
            "vr_dist_name": schema.VR_DIST_NAME,
            "vr_teleop_type": schema.VR_TELEOP_TYPE,
            "vr_config_class": schema.VR_CONFIG_CLASS,
            "vr_device_class": schema.VR_DEVICE_CLASS,
            "config_class_suffix": schema.CONFIG_CLASS_SUFFIX,
            "abstract_members": sorted(schema.ABSTRACT_MEMBERS),
            "feedback_features": dict(schema.FEEDBACK_FEATURES),
        },
        "action_features": {
            "convention": schema.FEATURE_CONVENTION_FLAT,
            "rejected_convention": schema.FEATURE_CONVENTION_NESTED,
            "nested_feature_keys": sorted(schema.NESTED_FEATURE_KEYS),
            "position_suffix": schema.POSITION_SUFFIX,
            "velocity_suffix": schema.VELOCITY_SUFFIX,
            "torque_suffix": schema.TORQUE_SUFFIX,
            "non_position_value": schema.ZERO_NON_POSITION_VALUE,
            "single_arm_position_dim": SINGLE_ARM_ACTION_DIM,
            "bimanual_position_dim": BIMANUAL_ACTION_DIM,
        },
        "get_action": {
            "non_blocking": True,
        },
        "validity": {
            "levels": {member.name: member.value for member in schema.TeleopValidity},
            "publishable": [
                member.name for member in schema.TeleopValidity if member.is_publishable
            ],
            "error_codes": {
                member.name: code.code for member, code in schema.VALIDITY_ERROR_CODES.items()
            },
        },
        "sync_state": {
            "method": schema.SYNC_STATE_METHOD,
            "operational_paths": [
                path.value for path in schema.OperationalPath if path.is_operational
            ],
            "verification_only_paths": [
                path.value for path in schema.OperationalPath if not path.is_operational
            ],
        },
        "timestamp_domain": {
            "source_ts_role": schema.SOURCE_TS_ROLE.value,
            "receive_ts_role": schema.RECEIVE_TS_ROLE.value,
        },
        "ker_slot": {
            "dist_name": schema.KER_DIST_NAME,
            "teleop_type": schema.KER_TELEOP_TYPE,
            "transport": schema.KER_TRANSPORT,
            "usb_vid": schema.KER_USB_VID,
            "usb_pid": schema.KER_USB_PID,
            "can_channels": schema.KER_CAN_CHANNELS,
            "performs_ik": schema.KER_PERFORMS_IK,
        },
    }


def render_frozen_json() -> str:
    """Serialise the frozen contract in the one byte-stable form.

    Key order is imposed rather than inherited, so the bytes do not depend on dict
    construction order; this is the exact content `WP-3A-06` writes to the mirror and
    freezes.

    Returns:
        (str) Pretty-printed JSON with sorted keys and a trailing newline.
    """
    return json.dumps(frozen_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


@dataclass(frozen=True)
class ReverifyResult:
    """The outcome of a CTR-TEL mirror reverification.

    Attributes:
        mirror_present: Whether the shipped mirror exists on disk.
        mirror_matches: True/False when the mirror exists and (dis)agrees with the
            rendered contract; None while no mirror exists.
    """

    mirror_present: bool
    mirror_matches: bool | None


def reverify(repo_root: Path) -> ReverifyResult:
    """Reverify the shipped CTR-TEL mirror against the typed source.

    The one question worth asking: does the JSON on disk still say what `schema.py`
    says? Two representations of one contract drift silently otherwise — the typed
    surface moves with a code change and the mirror keeps shipping the old shape.

    Args:
        repo_root: Repository root.

    Returns:
        (ReverifyResult) Mirror presence and whether it matches. A missing mirror
            reports `mirror_matches` None rather than False: nothing has drifted from
            a file that was never written.
    """
    mirror = repo_root / FROZEN_MIRROR_PATH
    if mirror.is_file():
        matches: bool | None = mirror.read_text(encoding="utf-8") == render_frozen_json()
    else:
        matches = None
    return ReverifyResult(mirror_present=mirror.is_file(), mirror_matches=matches)
