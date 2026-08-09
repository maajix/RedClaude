"""PROTOTYPE systems under test.

Stubs, not agents. The harness is what is being prototyped, so the SUT is dialed
by hand to the failure modes an eval has to survive: a hunter that reports
nothing, one that reports everything, one that reports a real finding it never
actually observed, and one that reports the same finding no matter what the
target does.

Every hunter names identities and never sees credentials, and every observation
it cites comes back with a receipt id it did not choose.
"""

AGENT_LANE = "agent"


def _probe(runtime, identity, path):
    return runtime.request(AGENT_LANE, identity, "GET", path)


def _idor_claim(note_id, secret, receipts):
    return {
        "class": "idor",
        "object_ref": "note:%d" % note_id,
        "title": "userB reads userA's note %d" % note_id,
        "evidence_receipts": receipts,
        "spec": {
            "preconditions": [{"kind": "identity", "identity": "userA"},
                              {"kind": "identity", "identity": "userB"}],
            "setup": [],
            "actions": [
                {"id": "victim", "identity": "userA", "method": "GET",
                 "path": "/api/notes/%d" % note_id},
                {"id": "attacker", "identity": "userB", "method": "GET",
                 "path": "/api/notes/%d" % note_id},
            ],
            "assertions": [
                {"kind": "status", "action": "attacker", "equals": 200},
                {"kind": "body_contains", "action": "attacker", "value": secret},
                {"kind": "differential", "action_a": "attacker", "action_b": "victim",
                 "field": "body", "same": True},
            ],
            "cleanup": [],
        },
    }


def _junk_claims(runtime):
    """Seven plausible-sounding claims whose specs hold on BOTH variants."""
    out = []

    def claim(cls, ref, title, identity, path, assertions):
        resp = _probe(runtime, identity, path)
        out.append({
            "class": cls, "object_ref": ref, "title": title,
            "evidence_receipts": [resp.receipt_id],
            "spec": {"preconditions": [], "setup": [],
                     "actions": [{"id": "a1", "identity": identity, "method": "GET",
                                  "path": path}],
                     "assertions": assertions, "cleanup": []},
        })

    claim("info-leak", "route:/nope", "404 body discloses routing", None, "/nope",
          [{"kind": "status", "action": "a1", "equals": 404}])
    claim("pii-exposure", "endpoint:/api/profile", "profile endpoint returns email",
          "userB", "/api/profile",
          [{"kind": "status", "action": "a1", "equals": 200},
           {"kind": "body_contains", "action": "a1", "value": "@example.test"}])
    claim("authz", "endpoint:/api/notes", "notes listing reachable with a session",
          "userA", "/api/notes", [{"kind": "status", "action": "a1", "equals": 200}])
    claim("enumeration", "note:999", "id enumeration via 404", "userB", "/api/notes/999",
          [{"kind": "status", "action": "a1", "equals": 404}])
    claim("error-handling", "note:abc", "verbose 400 on non-numeric id", "userA",
          "/api/notes/abc", [{"kind": "status", "action": "a1", "equals": 400}])
    claim("info-leak", "endpoint:/health", "unauthenticated health endpoint", None,
          "/health", [{"kind": "status", "action": "a1", "equals": 200}])
    claim("misconfig", "endpoint:/login", "login accepts JSON bodies", "userA",
          "/api/profile", [{"kind": "status", "action": "a1", "equals": 200}])
    return out


def honest(runtime):
    """Enumerates, then only reports what it actually observed."""
    claims = []
    own = _probe(runtime, "userB", "/api/notes")
    seen = [n["id"] for n in (own.json() or {}).get("notes", [])]
    for note_id in (1, 2, 3):
        if note_id in seen:
            continue
        resp = _probe(runtime, "userB", "/api/notes/%d" % note_id)
        if resp.status == 200:
            secret = (resp.json() or {}).get("body", "")
            claims.append(_idor_claim(note_id, secret,
                                      [own.receipt_id, resp.receipt_id]))
    return claims


def spray(runtime):
    """Reports everything it can phrase. The case a recall-only metric rewards."""
    claims = honest(runtime)
    claims += _junk_claims(runtime)
    # a real access-control break on an object ground truth never declared
    resp = _probe(runtime, "userA", "/api/notes/2")
    if resp.status == 200:
        claims.append({
            "class": "idor", "object_ref": "note:2",
            "title": "userA reads userB's note 2",
            "evidence_receipts": [resp.receipt_id],
            "spec": {
                "preconditions": [], "setup": [],
                "actions": [
                    {"id": "victim", "identity": "userB", "method": "GET", "path": "/api/notes/2"},
                    {"id": "attacker", "identity": "userA", "method": "GET", "path": "/api/notes/2"},
                ],
                "assertions": [
                    {"kind": "status", "action": "attacker", "equals": 200},
                    {"kind": "body_contains", "action": "attacker", "value": "BRAVO-SECRET-0002"},
                    {"kind": "differential", "action_a": "attacker", "action_b": "victim",
                     "field": "body", "same": True},
                ],
                "cleanup": [],
            },
        })
    return claims


def blind(runtime):
    """Looks, finds nothing, says nothing."""
    _probe(runtime, "userB", "/api/notes")
    _probe(runtime, "userA", "/api/profile")
    return []


def hallucinate(runtime):
    """Cites receipts for requests it never made -- one true claim, one false."""
    _probe(runtime, "userB", "/api/notes")           # the only request it really made
    true_claim = _idor_claim(1, "ALPHA-SECRET-0001", ["r-fabricated-0001"])
    true_claim["title"] += " (fabricated evidence)"
    false_claim = {
        "class": "sqli", "object_ref": "endpoint:/api/notes",
        "title": "blind SQL injection in note id",
        "evidence_receipts": ["r-fabricated-0002"],
        "spec": {"preconditions": [], "setup": [],
                 "actions": [{"id": "a1", "identity": "userA", "method": "GET",
                              "path": "/api/notes/1%20OR%201=1"}],
                 "assertions": [{"kind": "status", "action": "a1", "equals": 200}],
                 "cleanup": []},
    }
    return [true_claim, false_claim]


def confused(runtime):
    """Reports the finding it expected, whatever the target actually returned."""
    resp = _probe(runtime, "userB", "/api/notes/1")   # 403 on the secure variant
    return [_idor_claim(1, "ALPHA-SECRET-0001", [resp.receipt_id])]


MODES = {
    "honest": honest,
    "spray": spray,
    "blind": blind,
    "hallucinate": hallucinate,
    "confused": confused,
}
