"""Positive control: correct use of the unit contract must PASS mypy --strict.

If this file ever fails mypy, the type errors the sibling fixtures rely on are not
distinguishing right from wrong — they are just "mypy always fails here". This
proves the checker rejects only the violations, not honest usage.
"""

from __future__ import annotations

from contracts.units import Deg, Nm, Rad, clamp_torque, deg_to_rad

angle_deg: Deg = Deg(90.0)
angle_rad: Rad = deg_to_rad(angle_deg)
summed_deg: Deg = Deg(1.0) + Deg(2.0)
bounded: Nm = clamp_torque(Nm(100.0), Nm(54.0))

evidence: tuple[Deg, Rad, Deg, Nm] = (angle_deg, angle_rad, summed_deg, bounded)
