"""WP-ENV-01 — LeRobot v0.6.0 commit-SHA pin and phantom-version defence.

The plan-machine (`registry/`, `ops/`, `dashboard/`) must import nothing from
here: `deps.imports` introspects the installed LeRobot and therefore pulls the
heavy robot stack. `deps.phantom` and `deps.pin` are light (stdlib only) so the
pin can be validated without that stack.
"""
