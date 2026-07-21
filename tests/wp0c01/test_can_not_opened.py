"""Acceptance ② -- zero CAN-socket opens in SIM: static check + runtime hook.

Two independent proofs that the SIM backend opens no CAN socket (`09` FR-SIM-098,
`01` §4.1 SIM row):

- Static: an AST scan of the backend and sim-sync source finds no CAN-open
  primitive at all -- no `python-can` import, no `AF_CAN`/`PF_CAN`/`SOCK_RAW`
  socket use, no `flock`. Comments and string literals are ignored, so the guard's
  own prose about *not* opening CAN does not trip the scan.
- Runtime: the `can_guard` hook, which the backend re-checks at connect and before
  every actuation, refuses a non-zero CAN-open count; the single CAN-open chokepoint
  refuses outright in SIM; and after a full connect/observe/act cycle the backend's
  CAN-open count is still zero.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from packages.lerobot_robot_openarm_mujoco.can_guard import (
    SimModeCanError,
    assert_no_can_open,
    open_can_in_sim,
)
from tests.wp0c01 import BACKEND_PKG_DIR, SIM_MUJOCO_DIR

# CAN-open primitives, as code (never matched in comments or strings): the
# python-can package, the raw-CAN socket-address families, and the flock lock a
# hardware backend would take on its CAN channel.
_FORBIDDEN_IMPORT_ROOTS = {"can", "fcntl"}
_FORBIDDEN_NAMES = {"AF_CAN", "PF_CAN", "SOCK_RAW", "flock", "LOCK_EX"}


def _source_files() -> list[Path]:
    return sorted(BACKEND_PKG_DIR.rglob("*.py")) + sorted(SIM_MUJOCO_DIR.rglob("*.py"))


def _can_open_findings(source: str) -> list[str]:
    """Return code-level CAN-open primitives found in one source string."""
    tree = ast.parse(source)
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _FORBIDDEN_IMPORT_ROOTS:
                    findings.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in _FORBIDDEN_IMPORT_ROOTS:
                findings.append(node.module or "")
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_NAMES:
            findings.append(node.attr)
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            findings.append(node.id)
    return findings


def test_static_no_can_open_primitive_in_backend_source() -> None:
    files = _source_files()
    assert files, "expected backend and sim-sync source to exist"
    offenders = {
        str(path): findings
        for path in files
        if (findings := _can_open_findings(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}, f"CAN-open primitive(s) in SIM backend source: {offenders}"


def test_runtime_hook_rejects_nonzero_can_open_count() -> None:
    assert_no_can_open(0)  # the SIM invariant
    with pytest.raises(SimModeCanError):
        assert_no_can_open(1)


def test_can_open_chokepoint_refuses_in_sim() -> None:
    with pytest.raises(SimModeCanError):
        open_can_in_sim("oa_fl")


def test_full_cycle_opens_zero_can_sockets(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    pytest.importorskip("lerobot")
    from packages.lerobot_robot_openarm_mujoco import BiOpenArmMujoco, BiOpenArmMujocoConfig
    from sim.mujoco.sim_sync import action_channel_order

    backend = BiOpenArmMujoco(BiOpenArmMujocoConfig(id="wp0c01", calibration_dir=tmp_path))
    backend.connect()
    backend.get_observation()
    backend.send_action(dict.fromkeys(action_channel_order(), 0.0))
    backend.disconnect()
    # The runtime hook's subject: the backend held zero CAN opens for its whole life.
    assert backend._can_open_count == 0
