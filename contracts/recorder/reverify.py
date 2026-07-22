"""The reverify hook for CTR-REC@v1: the frozen body, the typed schema, and CTR-PRIM agree.

`contracts/recorder/schema.json` is the frozen, language-agnostic body of the
contract (`CONTRACT_FROZEN`, frozen by `WP-3A-06`). `schema.py` is the typed Python
source consumers import. Nothing keeps the two in step except a check, and nothing
keeps either honest against `CTR-PRIM@v1` except a check — so this module is that
check, a real predicate proven against the real body, not a re-hash.

It confirms in one pass the properties the contract stakes its acceptance on: the
action width and unit are `CTR-PRIM@v1`'s, position only, and carry no `.vel`/
`.torque` dimension; the camera image key is the primitive's own join; the timestamp
meta is the primitive's synthetic-grid domain; and the recorder redefines none of
the six primitives. The on-disk-body drift check is vacuous while `CTR-REC@v1` is
DRAFT — the frozen body is deliberately absent until `WP-3A-06` writes it from
`frozen_json_text()` and freezes it — and activates once the file exists. A mismatch
here is drift the frozen hash would otherwise hide until 3B amplified it thirteen ways.
"""

from __future__ import annotations

from pathlib import Path

import contracts.prim as prim
from contracts.prim import scan_module
from contracts.recorder import schema

_HERE = Path(__file__).resolve().parent
FROZEN_BODY = _HERE / "schema.json"
SOURCES = (_HERE / "schema.py", _HERE / "__init__.py")


def _body_matches_source() -> list[str]:
    """Report drift between the frozen body and the `schema.py` emitter, once it exists.

    While `CTR-REC@v1` is DRAFT the body is deliberately absent (WP-3A-06 writes it
    from `frozen_json_text()` and freezes it), so this check is vacuous rather than
    failing until the file is present.

    Returns:
        (list[str]) One message when an on-disk body differs from `frozen_json_text()`.
    """
    if not FROZEN_BODY.is_file():
        return []
    if FROZEN_BODY.read_text(encoding="utf-8") != schema.frozen_json_text():
        return [f"{FROZEN_BODY.name} has drifted from schema.frozen_json_text()"]
    return []


def _action_consumes_prim() -> list[str]:
    """Report any action fact that was restated instead of consumed from `CTR-PRIM@v1`.

    Returns:
        (list[str]) One message per mismatch between the frozen body and the primitive.
    """
    issues: list[str] = []
    document = schema.frozen_document()
    action = document["action"]
    if action["single_arm_dim"] != prim.SINGLE_ARM_ACTION_DIM:
        issues.append("action single_arm_dim does not match CTR-PRIM SINGLE_ARM_ACTION_DIM")
    if action["bimanual_dim"] != prim.BIMANUAL_ACTION_DIM:
        issues.append("action bimanual_dim does not match CTR-PRIM BIMANUAL_ACTION_DIM")
    if action["unit"] != prim.ACTION_POSITION_UNIT:
        issues.append("action unit does not match CTR-PRIM ACTION_POSITION_UNIT")
    if not action["position_only"] or not prim.ACTION_IS_POSITION_ONLY:
        issues.append("action is not marked position-only against CTR-PRIM")
    if set(action["forbidden_suffixes"]) != {schema.VELOCITY_SUFFIX, schema.TORQUE_SUFFIX}:
        issues.append("action forbidden suffixes are not exactly {.vel, .torque}")
    return issues


def _joins_consume_prim() -> list[str]:
    """Report any camera/timestamp join that was restated instead of consumed.

    Returns:
        (list[str]) One message per mismatch against the `CTR-PRIM@v1` joins.
    """
    issues: list[str] = []
    document = schema.frozen_document()
    probe = prim.arm_slot("left", "wrist")
    if document["images"]["rgb_key"].replace("<slot>", probe.value) != probe.image_key():
        issues.append("image rgb_key does not render through CameraSlotKey.image_key()")
    if document["images"]["depth_key"].replace("<slot>", probe.value) != probe.depth_key():
        issues.append("image depth_key does not render through CameraSlotKey.depth_key()")
    if document["timestamp_domain"] != prim.TimestampDomain.SYNTHETIC_GRID.value:
        issues.append("timestamp meta is not the CTR-PRIM synthetic-grid domain")
    return issues


def _redefines_no_primitive() -> list[str]:
    """Report any frozen primitive the recorder source redefines instead of imports.

    Returns:
        (list[str]) One message per redefinition found in the recorder modules.
    """
    return [
        f"{hit.path}:{hit.line} redefines primitive {hit.symbol}"
        for source in SOURCES
        for hit in scan_module(source)
    ]


def reverify() -> list[str]:
    """Run every CTR-REC@v1 consistency check and return the issues found.

    This is the callable `WP-3A-06`'s contract regression checker invokes: an empty
    result means the frozen body, the typed source and `CTR-PRIM@v1` all agree.

    Returns:
        (list[str]) Human-readable issue messages; empty when the contract is consistent.
    """
    return [
        *_body_matches_source(),
        *_action_consumes_prim(),
        *_joins_consume_prim(),
        *_redefines_no_primitive(),
    ]


def main() -> int:
    """Print the reverify result and return a process exit status.

    Returns:
        (int) 0 when consistent, 1 when any issue was found.
    """
    issues = reverify()
    if not issues:
        print(f"{schema.CONTRACT_ID} reverify: consistent")
        return 0
    for issue in issues:
        print(f"{schema.CONTRACT_ID} reverify: {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
