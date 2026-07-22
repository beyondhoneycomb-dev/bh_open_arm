"""WP-1-03 acceptance suite — the single send_action gateway and the actuation spine.

Every acceptance item runs offline: the safety filter, the collision guard, the ERR
decoder, and the bus-writer tau routing are exercised on dummies, fake buses and a
controlled clock, with no torque-ON and no real CAN. The one thing that is NOT here
is a torque-ON hardware run — that is WP-1-05, gated on PG-SAFE-001.
"""
