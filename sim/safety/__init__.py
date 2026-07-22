"""WP-1-06 sim/safety scene variants — collision-coverage assets this WP owns.

These are the FR-SAF-010 / FR-SAF-013 injection targets: a wrist-distal (link7) collision
descriptor and the workspace virtual-wall MJCF fragment. They live here, under this WP's
own tree, because the vendored MJCF is owned exclusively by `WP-0C-03` and is READ, never
written. The assets are produced by `backend.safety_bringup.collision` injectors and
verified by the same module; committing them lets the offline acceptance check the exact
bytes a caller loads.
"""
