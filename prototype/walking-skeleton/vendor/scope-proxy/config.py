"""PROTOTYPE config. Hand-written dicts, not the real config format.

Ticket 07 owns the real schema; this file only has to be concrete enough that
the addon has something to enforce. Stdlib only -- this is imported inside
mitmproxy's own pipx venv, which has no third-party packages we control.
"""

from __future__ import annotations

import os

FIXTURE_PORT = int(os.environ.get("RK_FIXTURE_PORT", "18099"))

# A target is the rate-limit and scope unit. NOT a host: one target may span
# several hosts, which is exactly why the budget is keyed on target id.
TARGETS = [
    {
        "id": "fixture",
        # `allow_private_ips` is explicit because the fixture really does live
        # on loopback. Making it implicit is how SSRF guards get bypassed.
        "allow_private_ips": True,
        # `fixture` is the compose service name in Phase B. Same target, reached
        # over a container network instead of loopback.
        "hosts": ["127.0.0.1", "localhost", "fixture"],
        "deny": [],
        "excluded_paths": ["/danger*"],
        "rate": {"rps": 50.0, "burst": 50, "max_concurrency": 8},
        # How this target carries its CSRF token. `extract` says where to read a
        # fresh token out of a response; `send` says where to put it back.
        #
        # `source` is the page the PROXY fetches on its own when it needs a token
        # and has none. Without it the proxy can only ever use a token that
        # happened to fly past on some earlier response -- and a token captured
        # before a login is already dead, because logging in rotates the session
        # the token is bound to. See `_refresh_csrf` in addon.py.
        "csrf": {
            "extract": {"kind": "html_input", "name": "csrf_token",
                        "source": "/notes"},
            "send": {"kind": "form_field", "name": "csrf_token"},
            # Double-submit repair. When the proxy owns the cookie jar, page JS
            # cannot read the cookie it is supposed to echo, so the proxy has to
            # echo it instead. Without this, every double-submit app is simply
            # broken for a browser behind this proxy.
            "double_submit": {"header": "X-CSRF-Token", "cookie": "XSRF"},
        },
    },
    {
        "id": "yekta",
        "allow_private_ips": False,
        "hosts": ["yekta-it.de", "*.yekta-it.de"],
        "deny": [],
        # Logging the session out from under a lease would poison every later
        # request that reuses it.
        "excluded_paths": ["/user/logout*"],
        # Real target, so a real Rules-of-Engagement rate rather than a test rate.
        "rate": {"rps": 2.0, "burst": 2, "max_concurrency": 2},
        "csrf": {
            "extract": {"kind": "html_input", "name": "form_token"},
            "send": {"kind": "form_field", "name": "form_token"},
        },
    },
    {
        # DNS-rebinding demo. The name is in scope; where it points is not.
        # localtest.me is a public name that resolves to 127.0.0.1.
        "id": "rebind-demo",
        "allow_private_ips": False,
        "hosts": ["localtest.me", "*.localtest.me"],
        "deny": [],
        "excluded_paths": [],
        "rate": {"rps": 5.0, "burst": 5, "max_concurrency": 2},
        "csrf": None,
    },
]

# An identity is a proxy upstream slot (Q15). `secrets` never leaves this
# process: it is what the proxy logs in WITH, and the agent can never read it.
IDENTITIES = {
    "userA": {
        "target": "fixture",
        "secrets": {"user": "alice", "password": "alice-pw-9f3c"},
        "static_headers": {},
    },
    "userB": {
        "target": "fixture",
        "secrets": {"user": "bob", "password": "bob-pw-27ae"},
        "static_headers": {},
    },
    # Unauthenticated slot against the real target: proves the identity path is
    # optional and that a request with no identity carries no credential.
    "anonYekta": {
        "target": "yekta",
        "secrets": {},
        "static_headers": {"X-Bug-Bounty": "redkraken-prototype"},
    },
}

# Two listeners, one policy engine.
#
# The agent lane strips every credential the client tried to send and injects
# from the jar instead. The provisioning lane is where the RUNTIME logs in: it
# is allowed to carry a credential, and whatever session it establishes is
# harvested into the jar. Both lanes are scope-checked, rate-limited against the
# same target budget, and receipted -- which is the point. Letting the runtime
# log in out-of-band would put real traffic on the target with no receipt and
# no share of the rate budget.
AGENT_PORT = int(os.environ.get("RK_AGENT_PORT", "18080"))
PROVISION_PORT = int(os.environ.get("RK_PROVISION_PORT", "18081"))

IDENTITY_HEADER = "X-RedKraken-Identity"
# Opt-out for deliberately testing CSRF enforcement: with this header the proxy
# leaves the token field exactly as the agent wrote it.
CSRF_RAW_HEADER = "X-RedKraken-Csrf-Raw"

STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}
