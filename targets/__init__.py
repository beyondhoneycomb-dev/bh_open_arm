"""WP-ENV-02 — heterogeneous deploy-target matrix and its runtime guard predicates.

Stdlib-only: the matrix is data and the guards are pure predicates, so the light
lane can validate the matrix without the robot stack. Per-target *installation*
feasibility is recorded in `targets/matrix.yaml`; the per-target runtime *blocks*
(`11` FR-INF-033/034) are the callables in `targets.guards`.
"""
