"""The report's wire names against the browser's `SystemData`, and its route against the fetch.

Nothing binds the two across the language boundary. A renamed field here does not fail: the
browser reads `undefined`, `vmlckKb` renders empty, `preemptRt` is falsy, and the screen shows
a host with no realtime kernel and no locked memory — which is indistinguishable from a real
finding. That is the drift this reads out of the TypeScript source to catch.

Read as text rather than imported, because that file is what the bundle is built from.
"""

from __future__ import annotations

from pathlib import Path

from backend.system import report as backend_report
from backend.system.bundle import (
    INCLUDE_PII_FIELD,
    INCLUDE_VIDEO_FIELD,
    INCLUDED_ITEM_IDS_FIELD,
    PRODUCIBLE_ITEM_IDS,
)
from backend.system.constants import SYSTEM_REPORT_ROUTE

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src" / "screens" / "S-13"
TYPES_TS = _FRONTEND / "types.ts"
DATA_SOURCE_TS = _FRONTEND / "dataSource.ts"
BUNDLE_TS = _FRONTEND / "diagnosticBundle.ts"

# Every wire name the report writes, named individually rather than swept off the module so a
# constant added without a consumer is a decision somebody made rather than a silent extension.
MIRRORED = (
    backend_report.PORTS_FIELD,
    backend_report.PORTS_CANON_FIELD,
    backend_report.PORTS_ACTUAL_FIELD,
    backend_report.RT_FIELD,
    backend_report.BUNDLE_FIELD,
    backend_report.ERROR_REGISTRY_FIELD,
    backend_report.CANON_COMPONENT,
    backend_report.CANON_PROTOCOL,
    backend_report.CANON_PORT,
    backend_report.ACTUAL_PID,
    backend_report.ACTUAL_LISTENING,
    backend_report.RT_ENV_FIELD,
    backend_report.RT_PROCESSES_FIELD,
    backend_report.RT_FINDINGS_FIELD,
    backend_report.ENV_KERNEL_RELEASE,
    backend_report.ENV_PREEMPT_RT,
    backend_report.ENV_PYTHON_VERSION,
    backend_report.PROCESS_SCHED_POLICY,
    backend_report.PROCESS_SCHED_PRIORITY,
    backend_report.PROCESS_CPU_AFFINITY,
    backend_report.PROCESS_VMLCK_KB,
    backend_report.PROCESS_MLOCKALL_OK,
    backend_report.FINDING_CODE,
    backend_report.FINDING_NOTE,
    backend_report.REGISTRY_SEVERITY,
    backend_report.REGISTRY_MESSAGE_KO,
    backend_report.REGISTRY_MESSAGE_EN,
    backend_report.REGISTRY_RECOVERY_HINT,
    backend_report.REGISTRY_DOC_URL,
    backend_report.REGISTRY_SUBSYSTEM,
)


def test_every_field_the_report_writes_is_declared_by_the_browser() -> None:
    source = TYPES_TS.read_text(encoding="utf-8")

    missing = [name for name in MIRRORED if name not in source]

    assert not missing, (
        f"{missing} are written by backend/system/report.py and declared nowhere in "
        f"{TYPES_TS.name}. A field the browser does not know reads as undefined, which on this "
        "screen is indistinguishable from a real finding."
    )


def test_the_manifest_field_names_are_the_browsers() -> None:
    source = TYPES_TS.read_text(encoding="utf-8")

    for name in (INCLUDED_ITEM_IDS_FIELD, INCLUDE_VIDEO_FIELD, INCLUDE_PII_FIELD):
        assert name in source, name


def test_the_claimed_bundle_items_are_ids_the_browser_requires() -> None:
    """An id the browser does not list would silently claim nothing, leaving the item missing."""
    source = BUNDLE_TS.read_text(encoding="utf-8")

    for item in PRODUCIBLE_ITEM_IDS:
        assert f'"{item}"' in source, item


def test_the_route_the_backend_serves_is_the_one_the_browser_fetches() -> None:
    """A path that agrees only by coincidence is a 404 the screen renders as a failed host."""
    assert f'"{SYSTEM_REPORT_ROUTE}"' in DATA_SOURCE_TS.read_text(encoding="utf-8")
