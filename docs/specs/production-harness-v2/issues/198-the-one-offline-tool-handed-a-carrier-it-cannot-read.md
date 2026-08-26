# 198 — The one offline tool handed a carrier it cannot read

**What to build:** the carrier rule `jsscan.py` already applies, for the one
registered tool that is not `jsscan.py`.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

Database `rk2here`, 2026-08-26, after two sittings.

```
tool=jq  status=error  exit=5  n=42
```

Forty-two offline Tool runs, every one of them `jq`, every one of them failed,
and no run of any other tool. `js_routes`, `js_parse` and `js_map` are granted
to `recon` and have never been called.

```
recon      | mcp__rk2__net_request  x138
recon      | mcp__rk2__run_tool     x42
web_hunter | mcp__rk2__net_request  x6
```

That second line is what ticket 186 was for and it is working: `recon` reaches
for an offline tool on its own. What it reaches for is `jq`, over the 984 JSON
responses this campaign has stored, and every attempt is thrown away.

## The mechanism

Reproduced outside the harness, against `rk2tools:latest`:

```
$ printf 'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{"a":1}\n' \
    | docker run --rm -i rk2tools:latest jq 'keys'
jq: parse error: Invalid numeric literal at line 1, column 9
exit=5

$ printf '{"a":1}' | docker run --rm -i rk2tools:latest jq 'keys'
[ "a" ]
exit=0
```

jq 1.7 is present and correct. What it is handed is not JSON.

Every Artifact the door files is the whole exchange:

```
artifact content types:
message/http x3887
(null) x2
```

`jsscan.py` knows this and says so in `carried_body`'s docstring — *every
Artifact the door files is one of these* — and strips the carrier itself,
reporting how many bytes it skipped. jq cannot, because jq is the one
registered tool with no analyser:

```
compare_responses | exec=/usr/local/bin/python3 | analyser=compare.py
extract_paths     | exec=/usr/local/bin/python3 | analyser=extract_paths.py
jq                | exec=/usr/bin/jq            | analyser=-
js_map            | exec=/usr/local/bin/python3 | analyser=jsscan.py
js_parse          | exec=/usr/local/bin/python3 | analyser=jsscan.py
js_routes         | exec=/usr/local/bin/python3 | analyser=jsscan.py
```

Five tools run a program this harness ships and digests into
`tool_runs.analyser_sha256`. The sixth runs a binary straight, so there is
nowhere for the carrier rule to live.

## What is not broken, measured

The JavaScript chain works. Twelve of the twenty-seven stored bundles were run
through `js_routes` by hand:

```
AF310.http  bytes=378573 carrier=386 routes=0 paths=0
AF316.http  bytes=6135   carrier=383 routes=0 paths=0
...
```

`carrier_bytes` is right on every one, `byte_size` matches the response's own
`Content-Length`, and `source_sha256` is the Artifact's hash rather than the
stripped body's — which is what `check_source_citation` holds a citation
against. `js_parse` over the 378 KB bundle finds its path literals
(`/download`, `/privacy/cookie-policy`). Against a control with two calls:

```json
{"routes": [{"method": "POST", "path": "/api/v2/orders", ...},
            {"method": "GET",  "path": "/api/v2/users/{id}", ...}]}
```

Grounded, with the call site and the templated segment. The zero routes on the
live bundles are the honest answer: they are marketing-site chunks from
`landrover.here.com` that make no calls with literal paths. Ticket 186 is
reachable and correct. This ticket is about the sixth tool.

## What has to be decided

- **An analyser for jq**, like the other five. `offline_tools.analyser` becomes
  a small program that applies `carried_body` and then executes
  `/usr/bin/jq`. It lands jq in the shape every other tool is already in, its
  bytes get digested into `analyser_sha256`, and the carrier rule stays in one
  place per tool rather than one place per caller.
- **Or compose the strip into the filter.** `jq -R -s` can cut the head off in
  jq itself, which needs no new program — and means wrapping model-supplied
  filter text inside a larger jq program, reading every input as one string
  first, and a parse failure that no longer says which line of JSON was wrong.

## Answer

The analyser, and then the thing the gate found underneath it.

- [x] **`jqrun.py`, and jq joins the other five.** `20261127T000000Z` gives jq
      `executable = /usr/local/bin/python3` and `analyser = 'jqrun.py'`, so the
      run records `analyser_sha256` like every other tool's. The wrapper applies
      `jsscan.carried_body`'s rule, hands jq the body on stdin, and passes back
      what jq wrote including the exit code -- jq's 1, 4 and 5 each mean
      something a caller acts on, and flattening them would turn "the filter
      matched nothing" into "the tool failed".

      Measured in the real image:

      ```
      $ docker run ... rk2tools:latest python3 /input/jqrun.py --version
      rk2-jq 1 (jq-1.7)
      $ ... /input/jqrun.py jq 'keys' /input/AF1
      rk2-jq 1: skipped 51 carrier byte(s) of 65
      [ "a", "b" ]
      ```

      The version names both, so `tool_runs.tool_version` still answers which jq
      the image holds. A wrapper that reported only itself would hide the tool
      it wraps.

- [x] **The carrier rule is duplicated, and the duplication is tracked.** Each
      analyser is mounted alone at `/input` with no `redkraken` on its path, so
      the rule cannot be imported. `tests/test_jqrun.py::CarrierRuleTest` holds
      the two copies against each other over the cases that separate them --
      a body with a blank line of its own, a truncated capture, LF-only
      headers -- and pins both constants.

- [x] **A registry row now answers only for the runs it describes.** Applying
      the change made two standing arms report forty-two runs at once:
      `recorded_version_now_refused` and `analyser_run_without_its_hash`. Both
      are right about what they see and wrong about what it means -- those runs
      recorded `jq-1.7`, which is what the image said, and had no analyser to
      hash because the row did not name one yet.

      Neither arm was written for a row that changes. `20261128T000000Z` gives
      `offline_tools` a `contract_since`, defaulting to `-infinity`, and scopes
      both arms by it. Every other tool keeps the behaviour it had. The
      alternative was deleting forty-two failed runs to make a check quiet,
      and those runs are the measurement at the top of this file.

- [x] **A standing statement, not a jq fix.** `20261127T000000Z`'s guard is
      written generally: no enabled tool may run without an analyser. The next
      tool registered as a bare binary is the next tool handed an envelope it
      cannot read.

## Why

An analyser that fails every time it is called is worse than one nobody calls.
The Task closes, the model reads an error it cannot act on, and the campaign
records forty-two attempts at a technique that was never going to work — which
reads as a technique that does not pay rather than a tool holding the wrong end
of its input.
