# 09 — Send one HTTP request through the capability proxy

**What to build:** Execute one allowed HTTP Tool run through the production proxy and persist an authoritative Receipt that no caller can fabricate or label allowed itself.

**Blocked by:** 07 — Encrypt credential-bearing wire Artifacts; 08 — Compile and enforce one Scope Policy.

**Status:** resolved

- [x] An allowed Tool run mints a cryptographically random short-lived capability and stores only its digest canonically.
- [x] The runtime sends the plaintext capability only to the local proxy, which resolves Program, Agent run, Tool run, Lane and current lifecycle before contacting the target.
- [x] The target receives the intended request but never proxy authorization, capability material or internal control headers.
- [x] The proxy creates one allowed Receipt through a database-owned writer and returns its stable identifier with the target response.
- [x] Missing, fabricated, cross-Program, expired and cleared capabilities are blocked before target contact and create only auditable blocked records.
- [x] The proxy role and even an owner-level negative fixture cannot directly insert a valid allowed Receipt outside the invariant.

## Comments

Implemented on branch `implementation/startup-assertion` in commit `1e7378f` on
2026-08-10. The two-axis review ran against the working tree rather than a
pushed commit, so the twenty-one findings it returned are answered inside that
same commit rather than in a follow-up one.

`src/redkraken/proxy.py` is the door: the control-header protocol, the fence
that asks the database, the forwarder, and `send`, which is what `rk proxy
request` runs. `20260810T214500Z__capability_proxy_egress.sql` is what makes the
database the only thing that can say "allowed": a resolver that refuses a
capability whose Program has closed, a trigger that refuses the row itself, one
canonical-form authorizer, and `record_proxy_exchange`, which checks the bytes a
Receipt names before it delegates. `rk proxy serve` and `rk proxy request` are
the two ends, and they are separate commands because they are separate roles --
the door runs as `rk2_proxy`, the caller as `rk2_runtime`.

0038 and 0040 already had the capability columns, `resolve_egress_capability`,
`write_allowed_receipt` and `write_blocked_receipt`. Nothing spent a capability.
This ticket adds the process that spends one, and closes the three ways the
arrangement was still open: a capability outliving a retired Program, an
authorizer that re-derived the request from a URL string, and
`register_proxy_artifacts`, a writer that registered four hashes with no bytes
behind any of them.

### What is asserted, and by what

`tests/test_proxy.py` is 23 offline tests against a stub fence and a loopback
target: that the control headers are *taken* out of the header container rather
than read past, that a refusal happens with the target's request count still at
zero, that exactly one Receipt is written per exchange and its identifier is
what the caller gets back, that a duplicate `Cookie` crosses twice, that a
body-less POST is forwarded byte for byte, and that a CONNECT carrying two
capabilities is answered 407 rather than raising out of the handler.

`ProxyEgressTest` in `tests/test_database.py` is 14 live tests, and the fence in
them is the real `rk2_proxy` on a real connection. One exchange runs in setup
and every criterion but the fifth is read out of what it left: the digest and
the expiry on the Tool run, the allowed Receipt and its `agent` lane, both
transcripts as artifacts on disk with matching hashes, and the target's own
record of what arrived. The fifth criterion is six arms, each with a capability
of its own -- missing, fabricated, cross-Program, expired, cleared by closing
the run, and minted under a Program since retired -- and each asserts the target
was not contacted and exactly one blocked Receipt exists. The sixth is two
tests: `rk2_proxy` refused on all four routes it might have (direct INSERT,
`write_allowed_receipt`, UPDATE, SELECT), and `rk2_owner` refused by the trigger
on a Receipt with no Tool run, a closed one, or another Program's -- with the
same INSERT against a live capability succeeding, so what fails is the invariant
and not the statement.

`ProxyCommandTest` in `tests/test_cli.py` is 6 more, on the two commands and on
where the capability may travel. `check_capability_receipt_fence()` gains two
negative controls in `CONTROLS` -- granting `write_allowed_receipt` back to
`rk2_proxy`, and an encrypted zero-byte artifact with no seal -- so both rules
this file adds have been seen to fail. `tests/fixtures.py` gains `Target`, the
recording counterparty both suites use, which records headers as a list of pairs
rather than a dict, because that is the only shape in which a duplicate header
is a testable fact.

Offline the suite is 461 tests green with 14 skipped; against the scratch
PostgreSQL 18 cluster ticket 08 built it is **590 tests, green, nothing
skipped**, and `python3 -m compileall -q src tests` is clean.

### Decisions worth naming

**One door to an allowed Receipt.** `record_proxy_exchange` registers the
artifacts, refuses a payload that mentions the capability, refuses a hash
registered elsewhere with a different length or visibility, requires the Receipt
to name the stored bytes of both directions, and only then calls
`write_allowed_receipt`. That second function is revoked from `rk2_proxy`, so
every one of those checks is mandatory for the role that runs the door. The
runtime keeps it: it is the harness's own connection and registers artifacts
through `rk artifact`.

**The capability is never a column.** `authorize_tool_run` mints 32 random bytes
and stores their SHA-256; the plaintext exists in the runtime's memory, in one
header on one loopback hop, and nowhere else. Closing the Tool run clears the
digest, which is what makes "cleared" a lifecycle fact rather than a revocation
step somebody has to remember to run.

**Control headers are taken, not read.** `take_control` removes
`X-RedKraken-*` from the `Message` before anything else looks at it, so the code
that builds the forwarded request cannot include what it never held. A duplicate
control header is refused rather than resolved: two capabilities in one request
is a question with no honest answer.

**The transcript is the wire.** The forwarder uses `putrequest(skip_host=True,
skip_accept_encoding=True)` + `putheader` + `endheaders(body)` rather than
`request(headers=dict)`, because the dict form collapses duplicate headers and
adds a `Content-Length: 0` of its own. The Receipt names the bytes that actually
crossed, which is the whole of what it is for.

**The decision header is a token, and the prose is a detail.**
`X-RedKraken-Decision` carries one of five fixed words; the sentence goes to
`X-RedKraken-Detail`, which nothing is meant to parse. A caller branches on the
first and reads the second, so rewording a refusal in a later ticket cannot
silently change what somebody branched to.

**The Program is bound again at every write.** One connection serves every
handler thread and `set_config` is session-wide, so between the decision and the
write another thread has the whole target round trip in which to rebind the
session. `allowed_receipt` binds again rather than inheriting, and a live test
interleaves the two by hand to prove it.

**The Receipt's reason cites the version it was decided against.**
`write_allowed_receipt` derives the row's `scope_version` from the Program's
current one, which is right -- the writer must not take a version from its
caller. So the decided version is written into the reason instead, and a policy
recompiled mid-exchange leaves the two visibly disagreeing rather than
relabelling what was decided.

**A refusal that cannot be filed is loud.** The blocked write is wrapped, but
narrowly -- `pg.DatabaseError`, `OSError`, `Refused` -- and it logs. The one
legitimate failure is a Program header naming a Program that does not exist:
there is no row to file the attempt against, and inventing one would be worse.
Anything else is this module being wrong, and a bug that swallows itself is a
fence nobody can see holes in.

**The target is reached through a seam, not through DNS.** The live suite
substitutes `connector`, because `127.0.0.1` can never be in a Program's scope.
What is faked is the address; the decision that authorised it is real, and that
seam is where ticket 11 attaches.

### What review changed

Twenty-one findings: fourteen on the Standards axis, seven on the Spec axis.
Sixteen were real and are fixed; five were wrong.

Four were behavioural. The transcript was built from the header list but sent as
a dict, so a duplicate `Cookie` collapsed on the wire while the hashed artifact
showed both, and a body-less POST gained a `Content-Length: 0` the transcript
omitted -- the Receipt named bytes the target never received. The Program bind
raced across handler threads, as above. `do_CONNECT` called `take_control`
unguarded, so a duplicated control header raised out of the handler and the
caller got no response rather than the intended refusal. And the decided
`scope_version` was resolved and then dropped on the floor.

Two were vocabulary, and `CONTEXT.md` is enforceable. `OPEN_CALL` /
`AUTHORIZE_CALL` / `CLOSE_CALL` named Tool runs "call", which that glossary
entry lists under _Avoid_; they are now `OPEN_TOOL_RUN` / `AUTHORIZE_TOOL_RUN` /
`CLOSE_TOOL_RUN`. `Grant` used the glossary's word for an operator's standing
predicate to mean the answer to one request; it is `Authorization`, and its
docstring says which of the two it is not.

The rest were smaller and are all closed: `typing.Callable` where every sibling
imports from `collections.abc`; a dead `root()` re-export and the
`ROOT_VARIABLE` import that existed only to feed it; two `# noqa` comments
against a linter this repo does not configure; missing annotations on five
functions; `keep = self.server.store`; `LiveTarget` and `Target` as two copies
of one recording handler, now one fixture; three verbatim copies of the same
`except Refused` arm in `_serve`, now one; a `Refused.reason` that mixed prose
with an identifier and a dead `status=407` on the endpoint check; and a fence
gaining rules with no negative control behind them, now two controls.

Five were wrong. **`p_identity` is not speculative generality**: the parameter
is consumed, matched against the Tool run's `identity_slot`, and a request
claiming an identity the run was not authorised for is refused -- what ticket 12
adds is a caller that passes something other than `""`. **Lane is not
unresolved**: there is no `lane` column on `tool_runs` or `agent_runs` to
resolve one from, and 0040 says so in as many words -- "the caller states a
purpose, never a lane: who acted is derived from what". A capability is what
mints an `agent` Receipt; a replay or a proxy-internal request reaches a
different writer. The test asserting the lane says this rather than asserting a
constant. **The blocked path is not untested**: each of the six arms asserts
exactly one record. **`cli._proxy` is not novel duplication**: it is the fourth
of four environment resolvers written the same way, and making it the odd one
out is not an improvement. And of the two rules called scope creep, one was --
`receipt_names_missing_artifact` is a retention question, it would have reported
the purge policy working as a fence that had broken, and it is gone -- while
`unsealed_zero_byte_wire_artifact` stays, because this file is what dropped the
writer whose name is the reason ticket 07's seal rule exempts empty artifacts.

### Raised by review and deliberately not built here

- **HTTPS does not go through this door.** `do_CONNECT` answers 405 with
  `tunnel-refused`, deliberately, after taking and validating the control
  headers. Ticket 10 is the tunnel; what this one settles is that a tunnel
  request is refused in the same words as anything else and never forwarded.
- **Nothing pins the address that was decided against.** `connect` resolves the
  name the ordinary way and dials whatever comes back, so a name that moves
  between the decision and the socket is not caught here. That is ticket 11, and
  the `connector` seam is where it attaches.
- **The identity is always empty.** `authorize_egress_request` takes
  `p_identity` and checks it against the Tool run's `identity_slot`; the proxy
  passes `""` because nothing injects a credential yet. Ticket 12 is what makes
  that argument carry something.
- **The wire view stays NULL, and `record_proxy_exchange` refuses to write one.**
  A wire hash would claim the bytes that crossed differed from the bytes the
  agent may read, and this door injects nothing, so there is no second view. A
  Receipt that carried one would be either the same bytes under a second
  visibility or credential-bearing material with no seal. Ticket 12 seals; this
  writer cannot.
- **No budget is counted and no halt is checked.** Ticket 08 left the time
  window compiled and unenforced and named the proxy as its enforcement point;
  it is still unenforced, along with the request budget and the halt flag,
  because those are ticket 13. What this ticket enforces is authority, not
  quantity.
- **Two earlier notes now cite a function that does not exist.** Ticket 07's
  "The proxy's placeholder artifacts are unsealed on purpose" explains its
  `byte_size = 0` exemption by `register_proxy_artifacts()`, which section 3
  drops; the exemption is now closed by rule 5 of `check_capability_receipt_fence`,
  which this file adds. Ticket 03's open finding about ticket 66 lists that same
  function among the three `rk2_runtime` can execute against the corpus's
  intent; two of the three remain, and that finding is smaller than it was but
  is not resolved.
- **"Capability" is still not in the glossary.** It is this change's central
  noun, `CONTEXT.md` has no entry for it, and the word appears on **Skill**'s
  _Avoid_ list, which is a different sense entirely. As with tickets 06, 07 and
  08, no implementation ticket in this branch edits that file, so it is
  documented in the migration header and in `proxy.py`'s own docstring and
  belongs in the glossary whenever `/domain-modeling` runs next.
- **The fence holds one connection for the whole process.** A connection per
  request would put the number of live database sessions under the control of
  whatever is making requests, which for a process whose job is to survive a
  hostile client is the wrong direction to fail in. The cost is a lock the
  handler threads queue on for the database half of each request, and the
  rebinding discipline described above; a pool is a thing to build when a
  measurement asks for one.

### A second review pass, over the committed work

Both axes run again against `92c546c`. Seventeen findings: ten Standards, seven
Spec. Thirteen were real and are fixed; four were wrong.

Three of them were holes, and all three are about what the audit trail does not
say.

**A duplicated control header bought a refusal nobody could see.** `take_control`
raised on two values under one name, before `_serve` had derived a Program, so
the request was refused and no row was written -- which made sending your own
capability header twice the quietest way to probe this fence. The Program was
never the ambiguous part of such a request: it is named once, and it is what the
attempt belongs to. `take_control` now reports the ambiguity instead of raising,
resolves the duplicated name to nothing so no later line can pick a side, and
`_serve` files the blocked Receipt whenever the Program survived. Two headers
naming two Programs still file nothing, because there is nothing to file under.
`do_CONNECT` keeps answering without a record, and that is a different case: no
tunnel is opened, so there is no exchange for a Receipt to be about.

**A served exchange whose record would not write left no record at all.** The
502 was right -- a caller must never read a 200 for an exchange the harness
cannot account for -- but the bytes had already crossed, and discarding both
transcripts and answering was the end of it. It now writes what can still be
written: a blocked Receipt naming the target, the status it answered with and
the moment of egress. It cannot name the transcripts, because registering them is
exactly what failed, so the unreachable bytes are still discarded.

**A refusal after contact looked like a refusal before it.** `target
unreachable` and `response too large` filed rows with no `ts_egress` and no
`status_code`, which is the shape of a request that never left. `_refuse` takes
the moment of egress on the paths that had one, and `Refused` carries the
target's status separately from the proxy's own answer -- one is what the fence
said, the other is what the target said, and a Receipt records both.

The fourth behavioural fix is the listener. `rk proxy serve --host` accepted any
interface, and `endpoint` refusing to send a capability anywhere but this machine
is worth nothing if the door binds a routable one: what arrives there is bearer
material, spendable by whoever reaches the port first. A non-loopback `--host` is
now refused with exit 2 rather than bound.

The rest were smaller: `README.md` said the corpus holds forty-seven files when
it holds forty-eight; `"no grant was returned"` used the glossary's word for an
operator's standing predicate to describe a capability that did not resolve; the
`BIND` statement was retyped as a literal in the runtime half; the two-branch
`jsonb` decode existed twice; the hop-by-hop and internal-prefix filter existed
twice, once per direction, which is a rule that can drift on one side only; the
target exchange came out of `_forward` as `_exchange`, which is also what let
every post-contact refusal be raised in one place; `_spend` took a `proxy` tuple
it indexed by position and which shadowed this module's own name; the proxy
subparsers were `hops` where `db` calls the same thing `operations`; and the two
suites each built their own recording counterparty, now `fixtures.counterparty`.
`authorize_egress_request` exempted GET, HEAD and OPTIONS from the declared-method
check with no comment saying why: §7 has subresources and redirects sharing one
capability, both arrive as GET whatever was declared, and a safe method is the
one substitution a holder of the capability gains nothing from. That is now
written down beside the rule.

Four were wrong. **The trigger's `lane = 'agent'` arm is not a bypass**: a
`replay` Receipt is the runtime re-executing a recorded exchange and a
`proxy_internal` one is the proxy acting for itself, and neither has a capability
by construction -- requiring a live one there would refuse the two lanes that
cannot have it, and the lane is derived by the writer rather than stated by a
caller. **`model = 'operator'` is not a deviation**: 0019's
`agent_runs_renderer_has_no_model` makes `model = 'none'` legal only for
`runs_as = 'renderer'`, and this run is a session, so the spelling review
proposed is the one the constraint refuses. **`(program_id, capability)` is not a
data clump wanting `Control`**: `Control.program` is the caller's unvalidated
word and `program_id` is what survived `_identifier`, and the split is what stops
the second from being the first. And **"capability" still wants a glossary entry
rather than a rename**, which is the note two sections above: `docs/agents/domain.md`
routes a missing term to `/domain-modeling`, and no implementation ticket in this
branch edits `CONTEXT.md`.

Six tests carry the four behavioural changes: the take reports ambiguity on each
of the two headers, a duplicated capability is refused and recorded while two
Programs record nothing, the receipt-refused path files a row carrying the status
and the egress moment, a refusal before contact carries neither, and the door
refuses to listen on `0.0.0.0`, `::` or a routable address. The live suite gains
the same duplicated-capability arm against the real database, where the row is
`agent`/`blocked`/`ambiguous control headers` with no Tool run named. 596 tests,
nothing skipped.

### Changed afterwards, by ticket 10

Naming a Receipt on refusals -- the second pass above -- had a consequence this
ticket recorded the wrong way round. `_spend` branched on `receipt is not None`,
so once a blocked request carried one, `rk proxy request` closed the Tool run
**`success`** and exited **0** for a request the door had refused. Ticket 10
fixed it: the branch is the decision token, a refused request closes `denied`,
fails the `egress` assertion with the door's own detail and exits **2**, and it
still names the Receipt. So the behaviour committed under this ticket -- a
refusal reported as a served request -- is not the behaviour on the branch, and
how a refusal is reported is read out of ticket 10 rather than out of this one.
