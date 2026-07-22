"""Domain constants for WP-2C-04 — collision-detection threshold modes and confirm/hysteresis.

Every value here is a spec figure, not a tuning guess. The per-joint arrays are the seven arm
joints joint1..joint7 (spec 12 §2.2 Table); the gripper joint8 carries no torque feedback and is
excluded from residual detection (WP-2C-11), so it never appears in a length-7 array here.

The threshold band is bounded on both ends and neither bound is arbitrary:

* Floor = 10 x the torque 12-bit LSB (DM8009 0.0264 / DM4340 0.0137 / DM4310 0.0049 Nm). A
  threshold below ten quantisation steps is below the sensor's own resolution — it would fire on
  quantisation noise, so WP-2C-03 blocks it and WP-2C-04 refuses to consume it (FR-SAF-019).
* Ceiling = the URDF effort limit. A threshold above the joint's own torque ceiling can never be
  exceeded, so detection on that joint would be dead (WP-2C-03 acceptance ③).

The STATIC default [4.0, 4.0, 2.7, 2.7, 0.7, 0.7, 0.7] Nm is exactly 0.1 x the effort limit — the
FR-SAF-020 literature-derived starting point (PMC7805958: bounds at +/-5-10 % of nominal max). It
is NOT an OpenArm-measured value; WP-2C-03's calibration wizard replaces it with a per-joint
measured figure, and this package consumes whichever value it is handed.
"""

from __future__ import annotations

# The seven torque-controlled arm joints. joint8 (gripper) has no torque feedback and is excluded
# from residual-based detection (spec 12 §2.2, WP-2C-11), so every per-joint array here is width 7.
N_ARM_JOINTS = 7

# URDF effort limits [Nm], joint1..joint7 (spec 12 §2.2 Table). The threshold ceiling: a per-joint
# threshold set above this can never be reached, leaving that joint's detection dead.
JOINT_EFFORT_LIMITS_NM = (40.0, 40.0, 27.0, 27.0, 7.0, 7.0, 7.0)

# Torque 12-bit LSB [Nm] per joint (spec 12 §2.2 Table): DM8009 0.0264, DM4340 0.0137,
# DM4310 0.0049. The detection threshold floor is ten of these steps.
TORQUE_LSB_NM = (0.0264, 0.0264, 0.0137, 0.0137, 0.0049, 0.0049, 0.0049)

# A threshold below this many LSB sits under the sensor's resolution and would fire on the
# quantiser alone (FR-SAF-019, WP-2C-03 acceptance ②).
THRESHOLD_LSB_FLOOR_MULTIPLE = 10.0

# Per-joint threshold floor [Nm] = 10 x LSB. Consuming a calibrated threshold below this is refused.
THRESHOLD_MIN_NM = tuple(lsb * THRESHOLD_LSB_FLOOR_MULTIPLE for lsb in TORQUE_LSB_NM)

# STATIC-mode default base threshold thr0 [Nm] = 0.1 x effort (FR-SAF-020). Literature-derived
# starting point, not an OpenArm-measured value — WP-2C-03 supersedes it with a calibrated figure.
THRESHOLD_DEFAULT_NM = (4.0, 4.0, 2.7, 2.7, 0.7, 0.7, 0.7)

# Velocity-scaling coefficient c_i [Nm.s/rad] for VELOCITY_SCALED, where
# thr_i(qdot) = thr0_i + c_i.|qdot_i| (spec 12 §2.12 [A] `detection.threshold_vel_coeff`,
# default 0.05, range 0..1.0).
VEL_COEFF_DEFAULT = 0.05
VEL_COEFF_MIN = 0.0
VEL_COEFF_MAX = 1.0

# Acceleration-scaling coefficient a_i [Nm.s^2/rad] for the optional accel term: + a_i.|qddot_i|
# (spec 12 §2.12 [A] `detection.threshold_acc_coeff`, default 0.0, range 0..0.5). It compensates the
# inertial-torque leakage M(q).qddot that dominates false positives when accel limits are off
# (spec 12 §2.13). Default 0.0 = off; a_i tuned toward the joint's effective inertia when on.
ACC_COEFF_DEFAULT = 0.0
ACC_COEFF_MIN = 0.0
ACC_COEFF_MAX = 0.5

# Consecutive over-threshold samples required to confirm a collision (spec 12 §2.12 [A]
# `detection.confirm_samples`, default 5 = 5 ms @1 kHz, range 1..50). The rising-edge debounce
# that rejects single-sample residual spikes from CAN jitter and 12-bit quantisation (FR-SAF-022).
CONFIRM_SAMPLES_DEFAULT = 5
CONFIRM_SAMPLES_MIN = 1
CONFIRM_SAMPLES_MAX = 50

# Release-threshold ratio (spec 12 §2.12 [A] `detection.hysteresis_ratio`, default 0.7, range
# 0.3..0.95). Once confirmed, a joint releases only when |r_i| drops to hysteresis_ratio x thr_i —
# the Schmitt band that stops the confirmed signal chattering around a threshold (FR-SAF-022).
HYSTERESIS_RATIO_DEFAULT = 0.7
HYSTERESIS_RATIO_MIN = 0.3
HYSTERESIS_RATIO_MAX = 0.95
