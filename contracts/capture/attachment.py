"""Static ban on a consumer producing `capture_ts` from a receive-time clock read.

`02b` §5.2 WP-3A-02 ① is the build-blocking rule this module enforces: a
`capture_ts` is attached at the grab site (`CTR-CAP` `SANCTIONED_ATTACHMENT_SITE`),
and a GUI or recorder that stamps the moment it *received* a frame has recorded
receive time under the capture column — the exposure phase difference is then lost
for good (the `FAIL_BLOCKING` negative branch). The consumers do not exist yet
(they land in 3B), so the scan is the contract's forward guarantee: the moment a
consumer feeds a live clock read into a capture-timestamp sink, this fires.

The distinction the scan draws is *produce* vs *read*. A consumer that reads a
sidecar column (`row[slot.capture_ts_column()]`, `slot_from_capture_ts_column`) or
builds a `CaptureTimestamp` from a device-supplied grab time is clean. A consumer
that writes a `<slot>_capture_ts` sink, or constructs a `CaptureTimestamp`, from a
`time.monotonic_ns()`-family call has produced the stamp itself, at receive time.

This is machinery, not the frozen contract: it is `EXCLUSIVE`, and the caller
chooses which trees are consumers to scan. The grab producer (`WP-3B-01`) is the
one sanctioned attachment site and is simply not in the scanned set.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from contracts.capture.schema import CAPTURE_TS_COLUMN_SUFFIX, FRAME_INDEX_COLUMN

# The clock reads that yield a receive instant. A capture-timestamp sink fed by any
# of these was stamped at the consumer, not at grab. Matched by the trailing callee
# name, so both `time.monotonic_ns()` and a bare imported `monotonic_ns()` are seen.
RECEIVE_CLOCK_CALLS = frozenset(
    {
        "monotonic",
        "monotonic_ns",
        "perf_counter",
        "perf_counter_ns",
        "time",
        "time_ns",
        "clock_gettime",
        "clock_gettime_ns",
    }
)

# The `CTR-PRIM` primitive a capture instant is carried as. A consumer constructing
# it from a clock read is the same defect as writing a `<slot>_capture_ts` column.
CAPTURE_TIMESTAMP_TYPE = "CaptureTimestamp"

# `frame_index` is the sidecar join column, not a capture instant; a consumer that
# assigns it (it is not a `*_capture_ts` sink) is untouched by this scan.
_JOIN_COLUMN = FRAME_INDEX_COLUMN


@dataclass(frozen=True)
class ConsumerAttachment:
    """One place a consumer produced `capture_ts` from a receive-time clock read.

    Attributes:
        path: File the attachment was found in.
        line: 1-indexed line of the offending statement.
        sink: The capture-timestamp sink the clock read flowed into.
        clock_call: The receive clock the value was read from.
    """

    path: str
    line: int
    sink: str
    clock_call: str


def _callee_name(node: ast.expr) -> str | None:
    """Return a call's trailing callee name (`time.monotonic_ns` -> `monotonic_ns`)."""
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _receive_clock_call(subtree: ast.AST) -> str | None:
    """Return the first receive-clock callee named anywhere in an expression subtree.

    Args:
        subtree: An expression node to walk.

    Returns:
        (str | None) The receive-clock callee name, or None when none is called.
    """
    for node in ast.walk(subtree):
        if isinstance(node, ast.Call):
            name = _callee_name(node.func)
            if name in RECEIVE_CLOCK_CALLS:
                return name
    return None


def _is_capture_ts_sink(target: ast.expr) -> str | None:
    """Return the sink name when an assignment target is a capture-timestamp slot.

    A sink is a name/attribute ending in the capture-ts column suffix (or the bare
    `capture_ts` field), or a subscript whose string key ends in that suffix — the
    `<slot>_capture_ts` sidecar cell. The `frame_index` join column is never a sink.

    Args:
        target: An assignment target expression.

    Returns:
        (str | None) The sink's textual name, or None when the target is not a sink.
    """
    suffix = CAPTURE_TS_COLUMN_SUFFIX
    bare = suffix.lstrip("_")
    if isinstance(target, ast.Name):
        return target.id if (target.id.endswith(suffix) or target.id == bare) else None
    if isinstance(target, ast.Attribute):
        return target.attr if (target.attr.endswith(suffix) or target.attr == bare) else None
    if isinstance(target, ast.Subscript):
        key = target.slice
        if (
            isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and key.value != _JOIN_COLUMN
            and (key.value.endswith(suffix) or key.value == bare)
        ):
            return key.value
    return None


def _constructs_capture_timestamp(value: ast.expr) -> bool:
    """Whether an expression constructs a `CaptureTimestamp`."""
    return isinstance(value, ast.Call) and _callee_name(value.func) == CAPTURE_TIMESTAMP_TYPE


def scan_module(path: Path) -> list[ConsumerAttachment]:
    """Find every receive-time capture-timestamp attachment in one consumer module.

    Two shapes fire: an assignment to a `<slot>_capture_ts` sink whose value reads a
    receive clock, and a `CaptureTimestamp(...)` construction whose argument reads
    one. Both mean the consumer produced the stamp instead of reading it.

    Args:
        path: Python file to scan (a consumer module).

    Returns:
        (list[ConsumerAttachment]) One entry per attachment, in source order.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[ConsumerAttachment] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            clock = _receive_clock_call(node.value)
            if clock is None:
                continue
            for target in node.targets:
                sink = _is_capture_ts_sink(target)
                if sink is not None:
                    hits.append(ConsumerAttachment(str(path), node.lineno, sink, clock))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            clock = _receive_clock_call(node.value)
            sink = _is_capture_ts_sink(node.target)
            if clock is not None and sink is not None:
                hits.append(ConsumerAttachment(str(path), node.lineno, sink, clock))
        elif _constructs_capture_timestamp(node):
            clock = _receive_clock_call(node)
            if clock is not None:
                hits.append(
                    ConsumerAttachment(str(path), node.lineno, CAPTURE_TIMESTAMP_TYPE, clock)
                )
    hits.sort(key=lambda hit: (hit.line, hit.sink))
    return hits


def check_no_consumer_attachment(paths: list[Path]) -> list[ConsumerAttachment]:
    """Scan several consumer modules for receive-time capture-timestamp attachment.

    Args:
        paths: Python files to scan.

    Returns:
        (list[ConsumerAttachment]) Every attachment found, in path then source order.
    """
    hits: list[ConsumerAttachment] = []
    for path in sorted(paths):
        hits.extend(scan_module(path))
    return hits
