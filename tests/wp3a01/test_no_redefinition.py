"""The two CTR-CAM@v1 static guards bite, and stay silent on the real contract.

`02b` §5.2 WP-3A-01 ① and WP-3A-00 ②: the camera schema must not fork a
CTR-PRIM@v1 primitive, and must not restate resolution or fps outside the
`CameraSpec` dict. Each scan is proven to fail on a synthetic offender and to pass
on this contract's own modules — a guard that cannot fail proves nothing.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import contracts.camera_registry as cam

CONTRACT_DIR = Path(cam.__file__).resolve().parent
CONTRACT_MODULES = sorted(CONTRACT_DIR.glob("*.py"))


def _write(path: Path, source: str) -> Path:
    """Write a synthetic module and return its path."""
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def test_real_contract_forks_no_primitive() -> None:
    """No camera-registry module redefines a CTR-PRIM@v1 primitive."""
    assert cam.check_no_primitive_redefinition(CONTRACT_MODULES) == []


def test_camera_schema_redefining_frame_type_fires(tmp_path: Path) -> None:
    """A camera module that declares its own FrameType has forked the primitive."""
    forked = _write(
        tmp_path / "cam_fork.py",
        """
        class FrameType:
            RGB = "rgb"
        """,
    )
    hits = cam.check_no_primitive_redefinition([forked])
    assert [hit.symbol for hit in hits] == ["FrameType"]


def test_real_contract_restates_no_geometry() -> None:
    """No camera-registry module binds width/height/fps to a fixed number."""
    assert cam.check_no_resolution_fps_redeclaration(CONTRACT_MODULES) == []


def test_hardcoded_fps_outside_the_dict_fires(tmp_path: Path) -> None:
    """A layer that hardcodes fps has restated geometry the CameraSpec dict owns."""
    offender = _write(
        tmp_path / "downstream.py",
        """
        FPS = 30

        def tile_count() -> int:
            width = 640
            return width
        """,
    )
    hits = cam.check_no_resolution_fps_redeclaration([offender])
    assert {hit.name for hit in hits} == {"FPS", "width"}


def test_annotated_geometry_literal_fires(tmp_path: Path) -> None:
    """An annotated rebinding of a geometry name to a literal is still a restatement."""
    offender = _write(
        tmp_path / "annotated.py",
        """
        height: int = 480
        """,
    )
    hits = cam.check_no_resolution_fps_redeclaration([offender])
    assert [hit.name for hit in hits] == ["height"]


def test_cameraspec_keyword_argument_is_not_a_restatement(tmp_path: Path) -> None:
    """Passing width=640 as a keyword is a call, not a geometry declaration."""
    construction = _write(
        tmp_path / "construct.py",
        """
        from contracts.camera_registry import CameraSpec

        def build(spec_cls: type) -> object:
            return spec_cls(width=640, height=480, fps=30)
        """,
    )
    assert cam.check_no_resolution_fps_redeclaration([construction]) == []
