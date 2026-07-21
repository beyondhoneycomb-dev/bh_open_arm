"""MuJoCo sim substrate for the OpenArm bimanual backend (WP-0C-01).

Two modules with one job each: ``sim_sync`` is the single LeRobot<->MJCF unit
boundary (deg<->rad), and ``scene`` is the only place the ``mujoco`` package is
touched. Keeping them apart is what lets the unit crossing have exactly one home
while the scene stays in radians throughout (the MJCF boundary is radians).
"""
