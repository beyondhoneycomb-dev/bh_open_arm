"""Repo-owned MJCF v2 sim assets and their invariant checker (WP-0C-03).

The single source of truth for the OpenArm bimanual sim asset. ``v2/`` holds the
vendored, J7-corrected MJCF, the cell scene, its re-parented head-camera variant,
and the meshes the models compile against. ``invariant`` audits the assets for the
motor-class contradictions the fix exists to remove.
"""

from sim.mjcf.invariant import AuditReport, audit

__all__ = ["AuditReport", "audit"]
