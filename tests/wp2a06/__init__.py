"""WP-2A-06 acceptance suite — the stop path's declared shape and its no-torque-cut check.

Everything here runs on this host, and everything here is checkable without a clock: the
`disable_torque` scan over the real stop path (with a violation fixture proving the reused
scan still bites) and the four-stage shape declaration (with a vanished-anchor fixture
proving the resolution still bites). There is no deferred rig acceptance left in this
suite — the stop-path latency is not measured in this tree, so there is nothing here
waiting on a capture.
"""

from __future__ import annotations
