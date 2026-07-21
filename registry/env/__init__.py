"""WP-ENV-04 — environment hash, start-block barrier, upstream contract regression.

`env_hash.py` and `barrier.py` are stdlib-only so the hash can be issued and the
start-block enforced in the light lane that never installs the robot stack.
`upstream.py` is the heavy contract-regression checker; `registry.check` must never
import it, which keeps the plan-machine free of torch/lerobot/mujoco.
"""
