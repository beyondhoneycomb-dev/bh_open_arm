"""The extended-safety-bring-up CLI: derive and preflight both exit 0 offline.

`derive` emits the PG-VEL-001 derivation document (register never canon, basis not self);
`preflight` runs the committed-MJCF link7 check, the injected-URDF/scene checks, and the
octomap scan. Both run on this host and must genuinely pass.
"""

from __future__ import annotations

import json

from backend.safety_bringup import cli


def test_derive_exits_zero_and_emits_table(capsys) -> None:  # noqa: ANN001 — pytest capsys fixture
    assert cli.main(["derive"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["gate"] == "PG-VEL-001"
    assert document["register_is_never_canon"] is True
    assert len(document["three_way_table"]) == 7
    assert document["bootstrap_limiter_rad_s"] == [1.57, 1.57, 3.14, 3.14, 12.6, 12.6, 12.6]


def test_preflight_exits_zero_and_reports_assets(capsys) -> None:  # noqa: ANN001 — pytest capsys fixture
    assert cli.main(["preflight"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mjcf_link7_bodies"] == [
        "openarm_left_ee_base_link",
        "openarm_right_ee_base_link",
    ]
    assert report["urdf_link7_link"] == "link7"
    assert report["virtual_wall_geoms"] == 6
    assert report["octomap_symbols"] == 0
