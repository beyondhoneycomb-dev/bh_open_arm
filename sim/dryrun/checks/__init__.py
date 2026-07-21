"""The six dry-run checks (`09` FR-SIM-030), one module per check.

`02a` WP-0C-09 shape SHAPE-IM(6): the dry-run 6-check body fans out to one file
per check so a change to the torque rule never risks the collision rule. Each
module exposes a pure ``check_*`` function over a compiled MuJoCo model/data and a
sim time, returning the distinct-coded violations it found and nothing merged.
"""
