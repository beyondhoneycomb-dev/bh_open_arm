"""WP-2B-06 acceptance suite — exciting-trajectory design and the injection harness.

The band design, the trajectory, the three hard gates, the four abort causes, and
resume-by-index all run `AI-offline` on this host against a recording torque path and a
scripted observer. The one thing that cannot run — the torque-ON injection on the real
arm — is SKIPPED WITH A REASON in `test_deferred_injection`, never asserted green.
"""
