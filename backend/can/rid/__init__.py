"""Read-only RID read harness (WP-0B-07).

The motor exposes its configuration and limits as RID registers. This layer reads
them — never writes them — and judges what it reads against the registered truth,
so that a mis-registered motor (`03` FR-MOT-003/004), a comm-loss timeout (`16`
M-4), or a value read under the wrong type (`03` FR-MOT-010) is caught before
torque is ever enabled.

The surface, in the order a read flows through it:

- `registers` / `decoder` — the `03` FR-MOT-010 type rule (RID 7-10/13-16/35-36 =
  uint32, else float32, little-endian) and the decode of a read-back, plus the
  detection of a value read under the wrong type.
- `motor_limits` / `layout` — `MOTOR_LIMIT_PARAMS` and the registered per-arm motor
  layout the RID 21/22/23 read-back is compared against.
- `dump` — the raw-bytes-per-motor capture, one schema for synthetic and real.
- `harness` — the read entry point: it asserts the WP-0B-01 lock is held and torque
  is OFF (`12` FR-SAF-075), then reads through a `RidReader`; it holds no write path.
- `judge` / `evaluate` — the PG-J7-001, PG-VMAX-001 and PG-RID-001 judgment scaffolds
  and the full evaluation of one dump.
- `staticcheck` — the AST proof that no write path exists anywhere in the tree.
- `reverify` — the re-verification hook the deferred, hardware-only acceptances
  re-run against a real 16-motor capture.

This layer opens no CAN socket; it reads through an injected reader, and takes the
channel lock before any read because a bus-shared read taken without the lock is
invalid (the rule `WP-0B-06` states for its measurements).
"""

from __future__ import annotations

from backend.can.rid.decoder import (
    RID_VALUE_BYTES,
    RidKind,
    RidValue,
    TypeMisread,
    decode,
    decode_as,
    find_type_misreads,
    mandated_kind,
)
from backend.can.rid.dump import MotorDump, RidDump, load_dump, parse_dump
from backend.can.rid.evaluate import DumpEvaluation, MotorEvaluation, evaluate_dump
from backend.can.rid.harness import (
    RidReadHarness,
    TorqueEngagedError,
    TorqueProbe,
    TorqueState,
)
from backend.can.rid.judge import (
    J7Judgment,
    MotorTimeout,
    PgStatus,
    Rid9Branch,
    Rid9Judgment,
    VmaxJudgment,
    judge_j7,
    judge_rid9_timeout,
    judge_vmax,
)
from backend.can.rid.layout import (
    ARM_MOTOR_TYPES,
    ARM_SEND_IDS,
    DM4340_MOTOR_IDS,
    J7_EXPECTED_TYPE,
    J7_MOTOR_ID,
    expected_type,
)
from backend.can.rid.motor_limits import (
    MOTOR_LIMIT_PARAMS,
    FieldComparison,
    LimitComparison,
    LimitParam,
    MotorType,
    compare_limits,
)
from backend.can.rid.reader import FixtureRidReader, RidReader
from backend.can.rid.registers import (
    RID_OC,
    RID_OT,
    RID_OV,
    RID_PMAX,
    RID_TIMEOUT,
    RID_TMAX,
    RID_UV,
    RID_VMAX,
    is_uint32_rid,
    rid_name,
)
from backend.can.rid.reverify import (
    FIXTURE_ENV_VAR,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.can.rid.staticcheck import (
    FORBIDDEN_COMMAND_BYTES,
    FORBIDDEN_NAME_TOKENS,
    StaticViolation,
    find_write_symbols,
)

__all__ = [
    "ARM_MOTOR_TYPES",
    "ARM_SEND_IDS",
    "DM4340_MOTOR_IDS",
    "FIXTURE_ENV_VAR",
    "FORBIDDEN_COMMAND_BYTES",
    "FORBIDDEN_NAME_TOKENS",
    "MOTOR_LIMIT_PARAMS",
    "RID_OC",
    "RID_OT",
    "RID_OV",
    "RID_PMAX",
    "RID_TIMEOUT",
    "RID_TMAX",
    "RID_UV",
    "RID_VALUE_BYTES",
    "RID_VMAX",
    "DumpEvaluation",
    "FieldComparison",
    "FixtureRidReader",
    "J7Judgment",
    "J7_EXPECTED_TYPE",
    "J7_MOTOR_ID",
    "LimitComparison",
    "LimitParam",
    "MotorDump",
    "MotorEvaluation",
    "MotorTimeout",
    "MotorType",
    "PgStatus",
    "Rid9Branch",
    "Rid9Judgment",
    "RidDump",
    "RidKind",
    "RidReadHarness",
    "RidReader",
    "RidValue",
    "StaticViolation",
    "TorqueEngagedError",
    "TorqueProbe",
    "TorqueState",
    "TypeMisread",
    "VmaxJudgment",
    "compare_limits",
    "decode",
    "decode_as",
    "evaluate_dump",
    "expected_type",
    "find_type_misreads",
    "find_write_symbols",
    "fixture_dir_from_env",
    "is_uint32_rid",
    "judge_j7",
    "judge_rid9_timeout",
    "judge_vmax",
    "load_dump",
    "mandated_kind",
    "parse_dump",
    "reverify_from_fixture",
    "rid_name",
]
