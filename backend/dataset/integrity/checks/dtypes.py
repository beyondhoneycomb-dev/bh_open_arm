"""Check 5 — data parquet dtypes match `info.json` (`02b` §8.2 WP-3D-05).

`info.json` declares each feature's dtype; the data parquet stores the columns. A
vector feature (a `shape` of integer dims, such as `observation.state`) is a
`list<value_type>` column, and a scalar meta feature is a plain column. If the
declared dtype and the stored dtype diverge — a `float32` state silently written
as `float64`, say — a training loader reads values it will mis-scale, so the two
must be identical, element type included.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from backend.dataset.integrity.constants import CHECK_DTYPE_MATCH
from backend.dataset.integrity.dataset import DatasetInventory, InventoryError
from backend.dataset.integrity.report import CheckResult, failed, passed
from backend.dataset.viewer.constants import FEATURE_DTYPE_KEY, FEATURE_SHAPE_KEY

# The `info.json` dtype spellings the recorder emits, mapped to the pyarrow type a
# well-formed column carries. Kept explicit rather than resolved through numpy so an
# unrecognised dtype fails loudly instead of matching by coincidence.
_ARROW_TYPE_BY_DTYPE: dict[str, pa.DataType] = {
    "float32": pa.float32(),
    "float64": pa.float64(),
    "int64": pa.int64(),
    "int32": pa.int32(),
    "int16": pa.int16(),
    "uint8": pa.uint8(),
    "bool": pa.bool_(),
}


def _is_vector(body: Mapping[str, Any]) -> bool:
    """Whether a feature body describes a vector (a numeric `shape`), not a scalar."""
    shape = body.get(FEATURE_SHAPE_KEY)
    return isinstance(shape, (list, tuple)) and all(isinstance(dim, int) for dim in shape)


def _expected_type(body: Mapping[str, Any]) -> pa.DataType | None:
    """The pyarrow type a feature's column should carry, or None for an unknown dtype."""
    dtype = str(body.get(FEATURE_DTYPE_KEY, ""))
    value_type = _ARROW_TYPE_BY_DTYPE.get(dtype)
    if value_type is None:
        return None
    return pa.list_(value_type) if _is_vector(body) else value_type


def _matches(actual: pa.DataType, expected: pa.DataType) -> bool:
    """Whether a stored column type matches the expected one (list value type included)."""
    if pa.types.is_list(expected) or pa.types.is_large_list(expected):
        if not (pa.types.is_list(actual) or pa.types.is_large_list(actual)):
            return False
        return bool(actual.value_type.equals(expected.value_type))
    return bool(actual.equals(expected))


def check_dtype_match(inventory: DatasetInventory) -> CheckResult:
    """Verify each stored feature's parquet column type matches its `info.json` dtype.

    Args:
        inventory: The shared dataset read.

    Returns:
        (CheckResult) PASS when every stored feature's column type matches; FAIL
            naming the first feature whose dtype diverges or is unrecognised.
    """
    try:
        layout = inventory.require_layout()
        stored = inventory.stored_feature_keys()
        data_files = inventory.data_files()
    except InventoryError as bad:
        return failed(CHECK_DTYPE_MATCH, f"info.json/layout unreadable: {bad}")

    checked = 0
    for data_file in data_files:
        try:
            schema = pq.read_schema(data_file)
        except Exception as bad:  # noqa: BLE001 — an unreadable schema is a dtype failure
            return failed(CHECK_DTYPE_MATCH, f"{data_file}: schema unreadable ({bad})")

        for key in sorted(stored):
            body = layout.features[key]
            expected = _expected_type(body)
            if expected is None:
                return failed(
                    CHECK_DTYPE_MATCH,
                    f"{key}: info.json declares unrecognised dtype {body.get(FEATURE_DTYPE_KEY)!r}",
                )
            field_index = schema.get_field_index(key)
            if field_index < 0:
                return failed(CHECK_DTYPE_MATCH, f"{key}: no column in {data_file}")
            actual = schema.field(field_index).type
            if not _matches(actual, expected):
                return failed(
                    CHECK_DTYPE_MATCH,
                    f"{key}: parquet dtype {actual} != info.json dtype {expected} in {data_file}",
                )
            checked += 1

    return passed(CHECK_DTYPE_MATCH, f"{checked} stored column dtype(s) match info.json")
