"""PROTOTYPE test-spec replay.

Q27's shape, executable: preconditions -> setup -> actions -> assertions ->
cleanup. Actions are structured request specs, not curl strings, so the same
spec can be replayed against either variant of the fixture without editing.

The assertion vocabulary is deliberately tiny. `differential` is the one that
carries the weight: an access-control finding is a claim about two identities,
and a spec that cannot express "userB sees what userA sees" cannot state the
finding at all.
"""


def _run_actions(actions, runtime, lane):
    results = {}
    receipts = []
    for act in actions:
        resp = runtime.request(lane, act.get("identity"), act.get("method", "GET"),
                               act["path"], act.get("body"))
        results[act["id"]] = resp
        receipts.append(resp.receipt_id)
    return results, receipts


def _check(assertion, results):
    kind = assertion["kind"]

    if kind == "status":
        got = results[assertion["action"]].status
        return got == assertion["equals"], "status=%d" % got

    if kind == "body_contains":
        body = results[assertion["action"]].body
        return assertion["value"] in body, "body[:60]=%r" % body[:60]

    if kind == "body_not_contains":
        body = results[assertion["action"]].body
        return assertion["value"] not in body, "body[:60]=%r" % body[:60]

    if kind == "differential":
        a = results[assertion["action_a"]]
        b = results[assertion["action_b"]]
        field = assertion.get("field", "body")
        va = a.body if field == "body" else a.status
        vb = b.body if field == "body" else b.status
        same = va == vb
        want_same = assertion.get("same", True)
        return same == want_same, "a=%r b=%r" % (str(va)[:40], str(vb)[:40])

    return False, "unknown assertion kind %r" % kind


def replay(spec, runtime, lane="replay"):
    """Execute a spec. Returns whether every assertion holds, plus the trace."""
    out = {"holds": False, "assertions": [], "receipts": [], "error": None}

    for pre in spec.get("preconditions", []):
        if pre.get("kind") == "identity" and pre["identity"] not in runtime._secrets:
            out["error"] = "precondition failed: no identity %s" % pre["identity"]
            return out

    try:
        _, setup_receipts = _run_actions(spec.get("setup", []), runtime, lane)
        results, action_receipts = _run_actions(spec.get("actions", []), runtime, lane)
        out["receipts"] = setup_receipts + action_receipts

        checks = []
        for assertion in spec.get("assertions", []):
            ok, detail = _check(assertion, results)
            checks.append({"assertion": assertion, "ok": ok, "detail": detail})
        out["assertions"] = checks
        out["holds"] = bool(checks) and all(c["ok"] for c in checks)
    except Exception as exc:                     # prototype: any failure is "does not hold"
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        try:
            _run_actions(spec.get("cleanup", []), runtime, lane)
        except Exception:
            pass
    return out
