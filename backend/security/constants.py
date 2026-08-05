"""Named parameters of the residual-hardening layer (`WP-5-08`, `14` §3).

Every literal the security logic depends on is named here rather than buried at a
call site. Values that already have a single owner elsewhere are imported, not
restated: the WS scheme/Origin words are `CTR-WS@v2`'s (`contracts.ws`), the VR
datagram port is the teleoperator's (`backend.teleop.vr_udp`), and the deadman
lease generation/duration are the deadman's (`backend.deadman`). Restating any of
them here would fork a contract this WP only consumes.
"""

from __future__ import annotations

# The plaintext transport schemes a control binding must never use. `CTR-WS@v2`
# owns the WS pair (`WS_PLAINTEXT_SCHEME`/`WS_SECURE_SCHEME`); the HTTP pair is the
# REST side this WP adds, kept as the bare scheme word so no `scheme://` literal
# lives in a source file the plaintext-binding scanner reads about itself.
PLAINTEXT_HTTP_SCHEME = "http"
SECURE_HTTP_SCHEME = "https"

# The separator that turns a bare scheme into a URL prefix. Built at runtime so the
# scanner's own marker table never contains a literal plaintext URL that would make
# `origin_policy` flag itself (`CG-5-08a` self-scan cleanliness).
URL_SCHEME_SEPARATOR = "://"

# The CORS response header and the wildcard value that, together, admit any origin.
# `Access-Control-Allow-Origin: *` is the exact string `FR-OPS-090` forbids on the
# control channel.
CORS_ALLOW_ORIGIN_HEADER = "Access-Control-Allow-Origin"

# The two-level control-lock command sources (`FR-OPS-075` (L2)): exactly one of
# these may command at a time, enforced independently of the device-level CAN-fd
# lock (L1).
COMMAND_SOURCE_VR = "vr"
COMMAND_SOURCE_GUI = "gui"
COMMAND_SOURCE_POLICY = "policy"
