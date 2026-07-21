"""The offline harness never opens a rig session — connect() call count is 0.

Real-rig binding and its single-session `connect()` are `WP-1-04`. This harness holds
the `WP-0C-05` dummy as its bench device but must never connect it. This is checked
two ways: at runtime the dummy's `connect` is instrumented and a measurement is run,
and statically the harness source is scanned so the only `.connect(` call sits inside
the deliberately-unused `connect_readonly`, which nothing in the harness invokes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sim.harness.load_profile import LoadProfile

HARNESS_DIR = Path(__file__).resolve().parents[2] / "sim" / "harness"


def test_connect_is_never_called_at_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Running the interleaved measurement calls the dummy's connect zero times."""
    from packages.lerobot_robot_openarm_dummy.robot import DummyOpenArmRobot
    from sim.harness.interleave import run_interleaved

    calls: list[bool] = []
    original = DummyOpenArmRobot.connect

    def _counting_connect(self: DummyOpenArmRobot, calibrate: bool = True) -> None:
        calls.append(True)
        original(self, calibrate)

    monkeypatch.setattr(DummyOpenArmRobot, "connect", _counting_connect)

    run_interleaved(
        LoadProfile(5, 320, 240, 32 * 1024, 128 * 1024),
        target_hz=250.0,
        warmup=10,
        segment_len=8,
        repeats=4,
        dataset_dir=str(tmp_path),
    )
    assert calls == []


def test_harness_source_only_connects_inside_the_unused_readonly_path() -> None:
    """Statically, the sole `.connect(` sits in `connect_readonly`, which nothing calls."""
    connect_sites: list[tuple[str, str]] = []
    readonly_call_sites: list[tuple[str, str]] = []
    for path in sorted(HARNESS_DIR.glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if ".connect(" in stripped and not stripped.startswith(("#", '"', "*")):
                connect_sites.append((path.name, stripped))
            if "connect_readonly()" in stripped:
                readonly_call_sites.append((path.name, stripped))

    assert connect_sites == [("control_loop.py", "self._robot.connect(calibrate=False)")]
    assert readonly_call_sites == []


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
