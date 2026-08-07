"""Ticket 31 proxy config — replaces ticket 04's `config.py` at run time.

Ticket 04's `config.py` says of itself: "Hand-written dicts, not the real config
format ... this file only has to be concrete enough that the addon has something
to enforce." That makes it the extension point, so ticket 31 supplies its own
rather than editing a vendored file.

What differs from ticket 04's version, and why:

  * one target, `t31`, on loopback. Ticket 04's `fixture` target also claims
    `127.0.0.1`, and `policy.decide` matches on host without a port, so the two
    entries would be ambiguous. Ticket 31's fixture pair lives on 18831/18832.
  * `csrf: None`. Ticket 05's fixture has no CSRF token anywhere; ticket 04's
    `fixture` target declares `extract.source: "/notes"`, which on ticket 05's
    app is a 404. This is divergence D-04/05-CSRF in the answer: the two
    prototypes' fixtures do not share an auth shape, and the composition has to
    say which one it is talking to.
  * identities `userA` / `userB` carry ticket 05's credentials
    (`fixture/app.py` USERS). They live here, in the proxy's own process, and
    are never handed to an agent — that is the standing constraint, unchanged.

Ports are ticket 31's own so nothing collides with a sibling session.
"""

from __future__ import annotations

import os

FIXTURE_VULN_PORT = int(os.environ.get("RK_T31_VULN_PORT", "18831"))
FIXTURE_SECURE_PORT = int(os.environ.get("RK_T31_SECURE_PORT", "18832"))

TARGETS = [
    {
        "id": "t31",
        # The fixture really is on loopback. Explicit, never implicit: an
        # implicit private-IP allowance is how SSRF guards get bypassed.
        "allow_private_ips": True,
        "hosts": ["127.0.0.1", "localhost", "fixture"],
        "deny": [],
        # `/__variant` is the harness's own back door into the fixture. An agent
        # that could read it would know which twin it is on, which is exactly
        # what the secure twin exists to hide. Excluded at the proxy, so the
        # refusal is a receipt rather than a convention.
        "excluded_paths": ["/__variant*"],
        "rate": {"rps": 50.0, "burst": 50, "max_concurrency": 8},
        "csrf": None,
    },
]

IDENTITIES = {
    "userA": {
        "target": "t31",
        "secrets": {"user": "userA", "password": "pw-a"},
        "static_headers": {},
    },
    "userB": {
        "target": "t31",
        "secrets": {"user": "userB", "password": "pw-b"},
        "static_headers": {},
    },
}

AGENT_PORT = int(os.environ.get("RK_AGENT_PORT", "18830"))
PROVISION_PORT = int(os.environ.get("RK_PROVISION_PORT", "18833"))

IDENTITY_HEADER = "X-RedKraken-Identity"
CSRF_RAW_HEADER = "X-RedKraken-Csrf-Raw"

STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}
