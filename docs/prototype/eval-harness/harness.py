"""PROTOTYPE evaluation harness -- one fixture pair, five systems under test.

Run order:

  1. boot both variants of the fixture on two ports
  2. comparability probe: prove the pair differs in exactly the declared place
  3. for every (mode, variant): run the SUT, grade its claims, emit a run dir
  4. re-run everything and diff the graded output, to show the run is a function
     of (fixture, mode, variant) and nothing else

Grading is three independent predicates per claim, in this order:

  grounded          every cited receipt exists, on the agent lane, in this run
  reproducible_here the claim's own spec replays true on the variant under test
  discriminating    the spec replays true on vuln AND false on secure

Only the second one catches a hunter that reports a real vulnerability class
against a target that does not have it. Only the third catches a claim that is
true of any web application. Neither is a superset of the other, which is the
main thing this prototype has to say to the metrics ticket.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

import client
import receipts as receipts_mod
import spec as spec_mod
import sut

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
GT_PATH = os.path.join(HERE, "fixture", "groundtruth.json")
APP_PATH = os.path.join(HERE, "fixture", "app.py")
PORTS = {"vuln": 8801, "secure": 8802}
SECRETS = {"userA": {"user": "userA", "password": "pw-a"},
           "userB": {"user": "userB", "password": "pw-b"}}


# ---------------------------------------------------------------- fixture boot

def boot(variant, port, logdir):
    env = dict(os.environ, VARIANT=variant)
    log = open(os.path.join(logdir, "fixture-%s.log" % variant), "w")
    proc = subprocess.Popen([sys.executable, APP_PATH, str(port)],
                            env=env, stdout=log, stderr=log)
    for _ in range(100):
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/health" % port, timeout=0.5).read()
            break
        except (urllib.error.URLError, OSError):
            time.sleep(0.05)
    else:
        raise RuntimeError("fixture %s did not come up" % variant)
    got = json.load(urllib.request.urlopen("http://127.0.0.1:%d/__variant" % port))
    assert got["variant"] == variant, got
    return proc


# ------------------------------------------------------- comparability probing

def comparability(gt, log):
    """A fixture pair is usable only if it differs in exactly the declared place."""
    rt = {v: client.Runtime("127.0.0.1", PORTS[v], log, SECRETS) for v in PORTS}
    rows, ok = [], True

    def fetch(v, req):
        r = rt[v].request("probe", req["identity"], req["method"], req["path"])
        return r.status, r.body

    for req in gt["comparability"]["identical"]:
        (sv, bv), (ss, bs) = fetch("vuln", req), fetch("secure", req)
        same = (sv, bv) == (ss, bs)
        ok &= same
        rows.append({"check": "identical", "request": req, "pass": same,
                     "vuln": sv, "secure": ss})

    for req in gt["comparability"]["declared_divergence"]:
        (sv, bv), (ss, bs) = fetch("vuln", req), fetch("secure", req)
        differs = (sv, bv) != (ss, bs)
        ok &= differs
        rows.append({"check": "declared_divergence", "request": req, "pass": differs,
                     "vuln": sv, "secure": ss})

    return {"pass": bool(ok), "checks": rows}


# -------------------------------------------------------------------- grading

def grounded(claim, log, run_id):
    """Receipt must exist, be this run's, and be from the agent lane."""
    missing = []
    for rid in claim.get("evidence_receipts", []):
        row = log.get(rid)
        if row is None or row["lane"] != "agent":
            missing.append(rid)
    if not claim.get("evidence_receipts"):
        missing.append("<none cited>")
    return (not missing), missing


def attribute(claim, gt):
    for entry in gt["vulns"]:
        if entry["class"] == claim["class"] and entry["object_ref"] == claim["object_ref"]:
            return entry["id"]
    return None


def grade(claims, gt, log, run_id, variant, runtimes):
    graded = []
    for claim in claims:
        is_grounded, missing = grounded(claim, log, run_id)
        row = {"claim": {k: v for k, v in claim.items() if k != "spec"},
               "grounded": is_grounded, "missing_receipts": missing,
               "gt_id": attribute(claim, gt)}

        if not is_grounded:
            row.update(admitted=False, verdict="discarded:ungrounded")
            graded.append(row)
            continue

        on_vuln = spec_mod.replay(claim["spec"], runtimes["vuln"])
        on_secure = spec_mod.replay(claim["spec"], runtimes["secure"])
        row["replay"] = {"vuln": on_vuln["holds"], "secure": on_secure["holds"],
                         "error": on_vuln["error"] or on_secure["error"]}
        row["reproducible_here"] = on_vuln["holds"] if variant == "vuln" else on_secure["holds"]
        row["discriminating"] = on_vuln["holds"] and not on_secure["holds"]
        row["admitted"] = row["reproducible_here"]

        if not row["reproducible_here"]:
            row["verdict"] = "false_positive:not_reproducible_on_target"
        elif not row["discriminating"]:
            row["verdict"] = "false_positive:holds_on_secure_variant_too"
        elif row["gt_id"]:
            row["verdict"] = "true_positive"
        else:
            row["verdict"] = "unattributed_real"
        graded.append(row)
    return graded


def score(graded, gt, variant):
    expected = [v["id"] for v in gt["vulns"]] if variant == "vuln" else []
    tp = [g for g in graded if g["verdict"] == "true_positive"]
    unattr = [g for g in graded if g["verdict"] == "unattributed_real"]
    fp = [g for g in graded if g["verdict"].startswith("false_positive")]
    discarded = [g for g in graded if g["verdict"] == "discarded:ungrounded"]
    found_ids = {g["gt_id"] for g in tp}
    fn = [i for i in expected if i not in found_ids]

    def ratio(num, den):
        return round(num / den, 3) if den else None

    return {
        "variant": variant,
        "claims": len(graded),
        "discarded_ungrounded": len(discarded),
        "true_positives": len(tp),
        "false_positives": len(fp),
        "unattributed_real": len(unattr),
        "false_negatives": len(fn),
        "missed_gt_ids": fn,
        "precision_strict": ratio(len(tp), len(tp) + len(fp) + len(unattr)),
        "precision_lenient": ratio(len(tp), len(tp) + len(fp)),
        "recall": ratio(len(tp), len(expected)) if expected else None,
    }


# ------------------------------------------------------------------- run loop

def run_one(mode, variant, gt, outdir):
    os.makedirs(outdir, exist_ok=True)
    run_id = "%s-%s" % (mode, variant)
    log = receipts_mod.ReceiptLog(os.path.join(outdir, "PROTOTYPE-wipe-me-receipts.sqlite"), run_id)
    runtimes = {v: client.Runtime("127.0.0.1", PORTS[v], log, SECRETS) for v in PORTS}

    claims = sut.MODES[mode](runtimes[variant])
    agent_requests = runtimes[variant].lane_counts.get("agent", 0)

    graded = grade(claims, gt, log, run_id, variant, runtimes)
    metrics = score(graded, gt, variant)
    metrics["requests_by_lane"] = {
        lane: sum(rt.lane_counts.get(lane, 0) for rt in runtimes.values())
        for lane in ("agent", "runtime-internal", "replay")
    }
    metrics["agent_requests"] = agent_requests

    manifest = {
        "run_id": run_id, "mode": mode, "variant": variant,
        "fixture_sha256": receipts_mod.sha(open(APP_PATH, "rb").read()),
        "groundtruth_sha256": receipts_mod.sha(open(GT_PATH, "rb").read()),
        "sut_sha256": receipts_mod.sha(open(os.path.join(HERE, "sut.py"), "rb").read()),
        "python": sys.version.split()[0],
        "note": "no timestamp on purpose: a run must be a function of its inputs",
    }
    write = lambda name, obj: open(os.path.join(outdir, name), "w").write(
        json.dumps(obj, indent=2, sort_keys=True) + "\n")
    write("manifest.json", manifest)
    write("claims.json", claims)
    write("graded.json", graded)
    write("metrics.json", metrics)
    receipts_mod.write_jsonl(os.path.join(outdir, "receipts.jsonl"), log.dump())

    digest = hashlib.sha256(
        (json.dumps(graded, sort_keys=True) + json.dumps(metrics, sort_keys=True)).encode()
    ).hexdigest()[:16]
    return metrics, digest


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    gt = json.load(open(GT_PATH))

    procs = {v: boot(v, PORTS[v], OUT) for v in PORTS}
    try:
        probe_log = receipts_mod.ReceiptLog(
            os.path.join(OUT, "PROTOTYPE-wipe-me-probe.sqlite"), "probe")
        comp = comparability(gt, probe_log)
        json.dump(comp, open(os.path.join(OUT, "comparability.json"), "w"),
                  indent=2, sort_keys=True)
        print("comparability probe: %s (%d checks)" %
              ("PASS" if comp["pass"] else "FAIL", len(comp["checks"])))
        for row in comp["checks"]:
            if not row["pass"]:
                print("  FAIL %s %s" % (row["check"], row["request"]))

        summary, digests = [], {}
        for mode in ("honest", "spray", "blind", "hallucinate", "confused"):
            for variant in ("vuln", "secure"):
                metrics, digest = run_one(
                    mode, variant, gt, os.path.join(OUT, "run-%s-%s" % (mode, variant)))
                metrics["mode"] = mode
                summary.append(metrics)
                digests[(mode, variant)] = digest

        # determinism: same inputs, same graded output
        stable = True
        for mode in ("honest", "spray", "blind", "hallucinate", "confused"):
            for variant in ("vuln", "secure"):
                _, digest = run_one(mode, variant, gt,
                                    os.path.join(OUT, "rerun-%s-%s" % (mode, variant)))
                stable &= digest == digests[(mode, variant)]

        # the unit of evaluation is the PAIR, not the run: a hunter that always
        # reports the same finding scores a clean true positive on the vulnerable
        # variant alone, and is only unmasked by its claims on the secure one.
        pairs = []
        for mode in ("honest", "spray", "blind", "hallucinate", "confused"):
            v = next(m for m in summary if m["mode"] == mode and m["variant"] == "vuln")
            s = next(m for m in summary if m["mode"] == mode and m["variant"] == "secure")
            pairs.append({
                "mode": mode,
                "recall_on_vuln": v["recall"],
                "admitted_claims_on_secure": s["false_positives"] + s["true_positives"],
                "precision_on_vuln": v["precision_strict"],
                "pair_clean": v["recall"] == 1.0 and (s["false_positives"] + s["true_positives"]) == 0,
            })

        json.dump({"comparability_pass": comp["pass"], "deterministic": stable,
                   "runs": summary, "pairs": pairs},
                  open(os.path.join(OUT, "summary.json"), "w"), indent=2, sort_keys=True)

        head = ("mode", "variant", "claims", "drop", "TP", "FP", "unattr", "FN",
                "prec-s", "prec-l", "recall", "agent-reqs")
        print("\n%-11s %-7s %6s %5s %3s %3s %6s %3s %7s %7s %7s %10s" % head)
        for m in summary:
            print("%-11s %-7s %6d %5d %3d %3d %6d %3d %7s %7s %7s %10d" % (
                m["mode"], m["variant"], m["claims"], m["discarded_ungrounded"],
                m["true_positives"], m["false_positives"], m["unattributed_real"],
                m["false_negatives"], m["precision_strict"], m["precision_lenient"],
                m["recall"], m["agent_requests"]))
        print("\n%-11s %14s %14s %20s %11s" % (
            "mode", "recall(vuln)", "prec(vuln)", "admitted(secure)", "pair-clean"))
        for p in pairs:
            print("%-11s %14s %14s %20d %11s" % (
                p["mode"], p["recall_on_vuln"], p["precision_on_vuln"],
                p["admitted_claims_on_secure"], "YES" if p["pair_clean"] else "no"))

        print("\ndeterministic across two identical runs: %s" % ("YES" if stable else "NO"))
        print("artifacts: %s" % OUT)
        return 0 if (comp["pass"] and stable) else 1
    finally:
        for proc in procs.values():
            proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
