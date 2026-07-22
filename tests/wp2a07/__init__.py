"""WP-2A-07 acceptance suite — comm-loss watchdog and ERR-nibble fault hold.

Every item runs offline: the seven ERR codes are injected as synthetic status
bytes through the reused Wave-1 decoder, the silence timer is driven by a
controlled clock, and comm loss is a mocked `recv_all()` that returns nothing.
There is no real CAN, no motor, and no torque-ON here — the two hardware items of
this band (stop latency, gripper capture) belong to other work packages.
"""
