# PROTOTYPE: the v2 evaluation harness

Throwaway code. It exists to answer a question, not to be extended.

**Question** (ticket [Prototype the evaluation harness on one fixture pair](../../.scratch/redkraken-v2/issues/05-eval-harness-prototype.md)):
around one vulnerable/secure fixture pair, how is ground truth declared, how is a
reported finding matched against it, how are the two variants kept comparable,
what does a run emit, and which numbers fall out without new instrumentation?

The answer is in the ticket. This file says how to run it and what the run
establishes. Nothing here survives into v2 except the findings.

## Run it

```bash
bash run.sh        # boots both variants, 5 hunters x 2 variants, twice -> table
```

Needs `python3` (3.14.6 here) and nothing else. Stdlib only, no network, two
loopback ports (8801 vuln, 8802 secure). `out/` is wiped on every run.

## What is here

| file | what it is |
| --- | --- |
| `fixture/app.py` | the fixture pair: one source file, one `VARIANT` flag |
| `fixture/groundtruth.json` | ground truth as executable specs + the comparability contract |
| `harness.py` | boot, probe, run, grade, score, emit, re-run |
| `spec.py` | Q27 spec replay: preconditions / setup / actions / assertions / cleanup |
| `client.py` | runtime-side HTTP: holds credentials, emits receipts, three lanes |
| `receipts.py` | receipt table, same shape as the scope-proxy prototype |
| `sut.py` | five stub hunters: honest, spray, blind, hallucinate, confused |

## What the run establishes

**Comparability, 12 checks.** Ten requests declared identical across variants are
compared status-and-body; two declared divergences are required to differ. Both
halves must hold, otherwise a difference in outcome is not attributable to the
vulnerability. Sessions are a pure function of the username so the bytes can be
compared at all.

**Grading is three independent predicates**, applied in order:

| predicate | question | catches |
| --- | --- | --- |
| `grounded` | does every cited receipt exist, on the agent lane, in this run? | claims about requests never made |
| `reproducible_here` | does the claim's own spec replay true on the variant under test? | a real class reported against a target that lacks it |
| `discriminating` | does it replay true on vuln and false on secure? | claims true of any web application |

Neither of the last two is a superset of the other, which is the main thing this
prototype has to say to the metrics ticket.

**Five hunters, ten runs.**

```
mode        variant claims  drop  TP  FP unattr  FN  prec-s  prec-l  recall agent-reqs
honest      vuln         1     0   1   0      0   0     1.0     1.0     1.0          3
honest      secure       0     0   0   0      0   0    None    None    None          3
spray       vuln         9     0   1   7      1   0   0.111   0.125     1.0         11
spray       secure       7     0   0   7      0   0     0.0     0.0    None         11
blind       vuln         0     0   0   0      0   1    None    None     0.0          2
blind       secure       0     0   0   0      0   0    None    None    None          2
hallucinate vuln         2     2   0   0      0   1    None    None     0.0          1
hallucinate secure       2     2   0   0      0   0    None    None    None          1
confused    vuln         1     0   1   0      0   0     1.0     1.0     1.0          1
confused    secure       1     0   0   1      0   0     0.0     0.0    None          1

mode          recall(vuln)     prec(vuln)     admitted(secure)  pair-clean
honest                 1.0            1.0                    0         YES
spray                  1.0          0.111                    7          no
blind                  0.0           None                    0          no
hallucinate            0.0           None                    0          no
confused               1.0            1.0                    1          no
```

`spray` ties `honest` on recall. `confused` — which reports the same finding
whatever the target returns — is indistinguishable from `honest` on the
vulnerable variant alone, at 1.0/1.0. Only its one admitted claim on the secure
variant separates them. The unit of evaluation is the pair.

**Determinism.** Every run is executed twice and the graded output hashed. The
manifest carries no timestamp on purpose: a run is a function of (fixture,
ground truth, SUT, variant) and must diff to nothing.

## What a run emits

```
out/
  comparability.json          12 checks, pass/fail per request
  summary.json                per-run metrics + per-pair aggregate
  run-<mode>-<variant>/
    manifest.json             sha256 of fixture, ground truth, SUT; python; no clock
    claims.json               what the SUT reported, verbatim
    graded.json               per claim: grounded, replay on both variants, verdict
    metrics.json              TP/FP/FN, both precisions, requests by lane
    receipts.jsonl            every request, by lane
    PROTOTYPE-wipe-me-receipts.sqlite
  rerun-<mode>-<variant>/     the determinism check
```
