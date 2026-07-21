"""Named literals for the OA-* error-code contract (CTR-ERR@v1).

Every value here carries meaning in the registry logic — the frozen data path,
the code grammar, the closed domain set, the field roster — so none of them is
spelled inline at a use site.
"""

from __future__ import annotations

import re
from pathlib import Path

# The frozen contract data, relative to the repository root. This module lives at
# contracts/errors/, so the registry sits beside it.
REGISTRY_FILENAME = "error_registry.yaml"
REGISTRY_PATH = Path(__file__).resolve().parent / REGISTRY_FILENAME

CONTRACT_ID = "CTR-ERR@v1"

# OA-<domain>-<3 chars>. The last group is hex because OA-MOT mirrors the Damiao
# ERR nibble (008..00E), so 00A..00E are valid code numbers, not typos.
CODE_PATTERN = re.compile(r"^OA-(?P<domain>[A-Z]+)-(?P<number>[0-9A-F]{3})$")

# The closed set of domain prefixes (14 §2.10). A code outside these is rejected;
# a new domain is a CTR-ERR@v(n+1) bump, never an in-place addition. The spec
# prose labels this set as eleven but enumerates ten, and every OA-* token across
# spec+plan resolves to these ten — the count is the miscount, not the set.
DOMAINS: tuple[str, ...] = (
    "OA-CAN",
    "OA-MOT",
    "OA-CTL",
    "OA-CAM",
    "OA-TEL",
    "OA-IK",
    "OA-SYS",
    "OA-INF",
    "OA-DAT",
    "OA-ZRO",
)

# The 10 fields every code row carries (14 §2.10). The last three are
# runtime-populated (null/0 at definition); the rest are authored in the file.
REQUIRED_FIELDS: tuple[str, ...] = (
    "code",
    "severity",
    "message_ko",
    "message_en",
    "hardware_id",
    "subsystem",
    "recovery_hint",
    "doc_url",
    "first_seen_t",
    "count",
)

RUNTIME_FIELDS: frozenset[str] = frozenset({"hardware_id", "first_seen_t", "count"})

# The Damiao feedback status byte packs the ERR code in its high nibble (14 §2.4).
# MotorState (damiao.py) drops the whole byte, so this shift is the extraction the
# upstream never performs (FR-OPS-018).
DAMIAO_ERR_NIBBLE_SHIFT = 4
DAMIAO_ERR_NIBBLE_MASK = 0xF

# Nibble 1 = Enable is a normal state, not an error, so it maps to no code.
DAMIAO_ENABLE_NIBBLE = 0x1

# The seven error nibbles that must be 1:1 with OA-MOT-0xx (acceptance ④). Nibble
# 0 (disabled) also maps, but it is a baseline state, not one of the seven faults.
DAMIAO_ERROR_NIBBLES: tuple[str, ...] = ("8", "9", "A", "B", "C", "D", "E")
