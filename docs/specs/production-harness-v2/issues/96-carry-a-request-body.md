# 96 — Carry a request body

**What to build:** A `body` argument on `mcp__rk2__http_request`, the
in-container client that carries it to the door, and the three rules that decide
when a body may be sent, what an approval covers and what is written down
afterwards.

**Blocked by:** 95 — A bounded string argument must say maxLength.

**Status:** resolved

- [x] `mcp__rk2__http_request` declares `body` as a **string** with
      `bounds=(0, 65536)` and no pattern. A string and not an object, because
      the gate's forbidden-name scan walks every container argument at every
      depth and refuses `password`, `token`, `secret`, `authorization`,
      `credential` and eleven other names (`roster.py:229-244`,
      `roster.py:274`), while `_scan` returns immediately for anything that is
      not a `Mapping`, `list` or `tuple` (`roster.py:1334`). An object `body`
      would deny the single most common POST in web testing; a string one is
      never scanned. `bounds` alone makes the argument `constrained`
      (`roster.py:348-356`), so no `OPEN_ARGUMENTS` entry is needed
      (`roster.py:545-555`, `roster.py:1772-1774`) and the roster's rule that an
      unconstrained argument states why it is one is not spent here.
- [x] The gap that closes is the contract and the in-container client, not the
      door. The door already reads a request body, refuses a chunked one with
      the reason written down, and caps what it reads at `CEILING`
      (`proxy.py:2394-2409`; `CEILING` is 32 MiB at `proxy.py:328`). It already
      owns the framing: `content-length` and `transfer-encoding` are hop-by-hop
      (`proxy.py:288-303`) and a measured `Content-Length` is added back when
      there is a body (`proxy.py:2693-2694`). It already hashes the body as part
      of the message -- `transcript` is start line, headers and body
      (`proxy.py:789-798`), `sent` and `wire_sent` are built from it
      (`proxy.py:2829-2830`) -- and `receipts` has carried `request_agent_sha`
      and `request_wire_sha` since 005 (`0005_artifacts_and_provenance.sql:59-60`).
      What has no body is `proxy.spend` (`proxy.py:3897-3907`), `_through`
      (`proxy.py:3968`, `:3987`) and the handler that calls them
      (`_launch.py:627-635`). The ticket adds no column and states that it adds
      none: a `request_body_sha256` would be a second hash of bytes already
      hashed.
- [x] **Rule one, permission decided at open.** A request may carry a body only
      if the Tool run that authorized it was opened as body-bearing, and a Tool
      run is opened as body-bearing only when the Playbooks selected for its
      Task declare `bb:effects` above `read_only`. The runtime already writes
      `url` and `method` into `tool_runs.args` at open
      (`execution.py:1929-1944`) and this is where the risk class is computed
      and a human is asked (`assess_call_risk`,
      `0026_human_control.sql:280-311`), so it is where the answer belongs. The
      corpus is mostly read-only and stays that way: 37 of the 50 Playbooks
      declare `read_only`, and the floor that stops one understating itself is
      `playbook.py:95-112`. The door refuses the mismatch beside the method
      binding it mirrors (`20260810T214500Z__capability_proxy_egress.sql:240-255`),
      with a blocked Receipt like every other refusal.
- [x] **Rule two, the approval digest sees the bytes.** `canonical_request`
      derives `body_keys` only from an object body
      (`0026_human_control.sql:183-186`) and sets `reusable: true` for this tool
      (`:172`), and `equivalence_key` is the sha256 of that document
      (`:193-196`). Two entirely different string bodies to one path template
      therefore share one key and one human approval covers both. After this
      ticket they do not: either `body_sha256` is in the digest or a call with a
      non-object body is `reusable: false`.
- [x] **Rule three, the request artifact is redacted the way the response
      already is.** Redaction today is response-only:
      `project_identity_response` (`proxy.py:659-698`) drops the headers
      carrying an injected secret and replaces the secret's renderings in the
      body, searching eight spellings of each value. `sent` and `wire_sent` use
      the same `body` object (`proxy.py:2829-2830`), which is correct while the
      only injected material is headers and stops being correct the day an agent
      can put bytes in a body -- an agent that read a token out of one response
      Artifact can write it into the next request. The agent-visible request
      Artifact is scrubbed against the bound session's `secrets(url)`
      (`identity.py:331-351`); the wire view stays sealed and exact, so an
      exchange whose redaction was incomplete is still one an auditor can see
      whole.
- [x] Desync stays out of reach and is refused rather than discovered. The door
      strips both length headers and re-measures, and refuses a chunked body
      outright because "a proxy that re-chunks is recording bytes that differ
      from the ones it read" (`proxy.py:2394-2402`). A body whose declared
      framing disagrees with its bytes cannot survive this door, and the ticket
      says so where `playbooks/http-desync` can read it.
- [x] `Content-Type` is a header and not an argument, and `Content-Length` is
      neither. The existing name and value patterns (`roster.py:753-757`) do the
      constraining, "send a body with no Content-Type at all" stays expressible,
      and the length stays the door's (`proxy.py:2693-2694`).
- [x] The argument ceiling and the door's ceiling are different numbers, stated
      separately. 32 MiB is a store-and-hash bound on what a target may answer
      with (`proxy.py:328`); a tool argument is bytes in a model's context.
- [x] No new vocabulary. `body_parameter` already exists as a surface fact
      (`0032_playbooks.sql:57`) and has described endpoints no step could
      exercise since 032; `json_request`, `form_request`, `multipart_request`
      and `xml_request` exist beside it. `writes` on the contract needs no
      change either: it is already `("receipts", "artifacts", "artifact_refs")`
      (`roster.py:741`), which is exactly what a bodied request writes.

## Why

Capability A in
`docs/research/playbook-state-of-the-art/09-capability-matrix.md` -- first of
twelve, and by a wide margin: **61 of the 131 techniques** the eight research
files propose are downstream of it. The phase-1 contract, the argument shape and
the three rules above are from
`docs/research/harness-capabilities/11-request-primitive-design.md`, which
settles each of them field by field against RFC 9110/9112, OWASP's mass
assignment and logging guidance and LLM06 Excessive Agency.

`00-todo-and-harness-gaps.md` calls this "the blocker" and it is the reason the
whole effort is harness-first. Everything whose reading is "send this document
and see what comes back" is prose today rather than a procedure: GraphQL, gRPC,
SOAP, SCIM, token endpoints, multipart upload, the injection corpus and all ten
techniques in `08`. The contract's own comment records the reason it was
withheld -- "the child has no store, so it cannot name a body the door could
send" (`roster.py:758-765`) -- and the half of that sentence about the store is
what a bounded string argument answers.

## What was built

`body` is a bounded string on `mcp__rk2__http_request` (`roster.py:767-806`),
threaded through `_launch._spend`, `proxy.spend` and `_through` to the hop the
door terminates. The door already read, bounded, hashed and refused a chunked
request body; what was missing was every layer above it.

The comment that withheld the argument is replaced rather than deleted, because
half of its reason still holds: the child still has no store, and what changed
is that a bounded string is a body it can spell itself.

## Rule two, and which of the two ways out was taken

**A Tool run opened as body-bearing is `reusable: false`.** Its equivalence key
carries the nonce, so one human approval covers one Task rather than every
string body sent to one path template.

The alternative the ticket offered was `body_sha256` in the digest, and it is
the wrong one: `canonical_request` is written when the Tool run opens, and the
bytes are chosen after that. A `body_sha256` there would be the digest of a key
that is never present, which is a field that looks like a check and is not one.

## Rule one, decided where the human is asked

`body_allowed` is computed from the Playbooks selected for the Task and written
into `tool_runs.args` at open (`execution.py:1945`, `_body_allowed` at
`:2381-2402`), beside the `url` and `method` that were already there. It is the
maximum over the selection and not the minimum: one Playbook that submits a form
makes the attempt one that submits a form, whatever the others alongside it only
read. A selection that is entirely `read_only`, and a run carrying no Playbook
at all, are both opened without one, because silence on a permission is not a
grant.

The door refuses the mismatch beside the method binding it mirrors, with a
blocked Receipt like every other refusal.

## Rule three, the request Artifact redacted the way the response already was

`project_identity_request` (`proxy.py:701-745`) scrubs the agent-visible request
against the bound session's secrets. Replacement and not suppression, and unlike
the response side it goes for the headers too: a request header is the Agent's
own account of what it sent, so dropping one would make the record say the Agent
sent something it did not. `Content-Length` is restated rather than scrubbed,
because here it is the door's measurement of the door's own document. The wire
view stays sealed and exact.

## Two numbers, stated apart

64 KiB bounds the argument, because those bytes are written by a model into a
model's context. 32 MiB is the door's `CEILING`, which is how much of a target's
answer this harness will hold in memory to hash and store. They are answers to
different questions and neither is derived from the other.
