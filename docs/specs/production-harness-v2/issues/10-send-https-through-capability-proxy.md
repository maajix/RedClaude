# 10 — Send HTTPS through the same capability path

**What to build:** Make an HTTPS Tool run cross the exact same production capability, scope and Receipt path as HTTP, including certificate trust inside the real agent topology.

**Blocked by:** 09 — Send one HTTP request through the capability proxy.

**Status:** needs-triage

- [ ] The runtime configures both HTTP and HTTPS proxy schemes explicitly and installs only the run-specific trust root needed by the agent environment.
- [x] A local TLS target is reached through the proxy and produces a capability-bound allowed Receipt.
- [ ] Direct HTTPS from the agent network namespace fails even when a client ignores conventional proxy environment variables.
- [x] An out-of-scope HTTPS target is refused before target contact with an auditable blocked Receipt.
- [x] The agent never receives proxy authorization, target credentials or wire-only response material.
- [x] A regression test fails against the prototype behavior that configured only the HTTP proxy handler.

## Comments

Implemented on branch `implementation/startup-assertion` in commit `9c2ba9b` on
2026-08-10. **The first and third criteria are not ticked and this ticket is not
resolved**, which is why the status is `needs-triage` rather than `resolved`: see
the last section.

`src/redkraken/tls.py` is the run's certificate authority -- one per run, in a
directory the door owns, issuing a leaf that names exactly one host -- and
`agent_environment`, which is what a child is told about the door.
`src/redkraken/proxy.py` gains `do_CONNECT`, which terminates the TLS itself
rather than relaying it, `merge_control`, which joins the control headers of the
two hops a tunnelled request arrives on, and an https half of `connect`, `send`
and `_through`. `rk proxy serve --authority` and `rk proxy request --ca` are the
two ends of the trust, named separately because the side that holds the signing
key is not the side that verifies against the certificate.

The prototype's finding this closes is that it configured only the HTTP proxy
handler. What that produced was not an error: an https request went **around**
the door and left no Receipt. So the regression test is not about a status code
-- it is `test_a_client_configured_for_only_the_http_scheme_leaves_by_no_door`,
which sends the same URL twice through one opener holding one scheme and then
both. The URL names a port nothing listens on, so the two configurations are
told apart by where the failure comes from: with `http` alone the client dials
the target itself and the connection is refused with the door's authorize,
allowed and blocked lists all empty and the target untouched; with both schemes
the same URL is answered 200 with a Receipt.

### What is asserted, and by what

`tests/test_tls.py` is 19 offline tests, twelve of them on the authority: that it survives
a restart of the door rather than minting a second root the child was never
given, that the signing key is `0600` in a `0700` directory, that a leaf is
accepted by a client holding the run root and refused by one holding the
system's, that it is refused for a host it does not name, that an address
literal gets `IP:` and not `DNS:`, that a host carrying a newline is refused
before it can add an extension of its own, and that a run stops issuing once it
has certified `HOSTS` of them. `EnvironmentTest` is the other half of criterion
one: both schemes in both spellings, both bypass lists emptied, the trust root
under all four names clients look for, the signing key's path in nothing at all,
and a handshake showing that the hashed directory beside the trust file is no
longer a store the child reads.

`tests/test_proxy.py` grows from 28 to 41. `TunnelTest` is the eleven that run a
real handshake against the door: an https target reached through the tunnel and
answered with a Receipt, the target's own record showing no control header and
no `Proxy-Authorization`, the agent's answer showing the same and no transcript
digest either, an out-of-scope target refused before it is contacted,
a capability carried on either hop alone read as the capability, one carried on
both hops with different values refused as `TWO_HOPS`, the two on what happens
when the door is bypassed -- a client holding the run root cannot verify a
target it dials itself, and the door cannot verify one no public authority
vouches for -- and the regression test above.
`test_the_tunnel_is_terminated_at_the_door_and_never_reaches_the_target` asserts
the thing that makes the rest true: the target's TLS listener records no
handshake for a request the door answered. `ExchangeTest` gains the CONNECT
refusals that need no handshake -- a door started with no authority refuses the
tunnel rather than relaying it -- and the two on what a refusal tells the
caller: the reason and the record's name, never the database's error.

`ProxyEgressTest` in `tests/test_database.py` grows from 15 to 20, and the fence
in them is the real `rk2_proxy`. Setup now runs a second exchange through a real
tunnel to a real TLS target, and criterion 2 is read out of the row it left:
`agent`/`allowed`, scheme `https`, the host, port, path and status the request
actually had, `intercepted` true, the label the caller was handed, the scope
class the policy decided, and both wire hashes still null -- what the door saw
of the target's connection is not what the agent read, and the row says so by
leaving them empty rather than by repeating the agent's. The refusal arms
are two, because there are two fences: an out-of-scope https URL never mints a
capability at all -- `authorize_tool_run` refuses at the gate, `facts["response"]`
is `None`, the Tool run closes `denied` with a null digest -- and a request that
gets past the gate and is refused at the door is reported as a refusal, with the
blocked Receipt named, `ts_egress` set and the command exiting non-zero.

`ProxyCommandTest` in `tests/test_cli.py` is 8, two of them new: a door reports
the certificate an agent has to be given and writes it before the database is
reached, and the two certificate inputs are refused by name, because `--authority`
being unusable and `--ca` being unusable are different mistakes.

Offline the suite is 500 tests green with 14 skipped; against the scratch
PostgreSQL 18 cluster it is **635 tests, green, nothing skipped**, and
`python3 -m compileall -q src/redkraken tests` is clean.

### Decisions worth naming

**Interception, not relay.** `do_CONNECT` answers `200 Connection Established`
and then becomes the other end of the tunnel: it wraps its own socket with a
leaf minted for the host in the CONNECT line and reads the request inside. A
relay would satisfy every client and record nothing -- the Receipt it could
write would name a host and a byte count and could say nothing about what
crossed. This is the same act an attacker performs, and what makes it legitimate
is that the trust is narrow: one authority per run, one host per leaf, and a
signing key the child is never told the path of.

**No Receipt for the CONNECT.** A CONNECT is not an exchange; no bytes reach a
target because of one, and a row written for it would name a request nobody has
made yet. The requests inside are each recorded, refused ones included. What is
refused at the CONNECT is only what makes a tunnel impossible: ambiguous control
headers, no authority to sign with, and an authority-form that is not one. Scope
is deliberately not consulted there -- answering "may I speak to this host at
all" before a capability is spent would let a caller enumerate a Program's scope
for free.

**`merge_control` rather than a precedence rule.** A tunnelled request has two
places to carry a capability, and both are the caller's. Agreement carries;
silence on one hop carries the other; disagreement is `TWO_HOPS` and is refused,
because two capabilities across two hops is a question with no honest answer.
That is the same rule `take_control` already applies to two headers on one hop,
and it is stated once for both.

**The decision token is what the runtime branches on.** `X-RedKraken-Decision`
is present only on refusals -- the served path passes `decision=None` -- so its
presence is the reliable answer to "did this fence refuse", where the status is
not: a fence refusal and a target's own 407 are the same number on the wire, and
only one of them means no bytes crossed. `Answer` carries the status, the body,
the Receipt, the decision and the detail as five named facts for that reason.

**Two fences, and the report says which one answered.** An out-of-scope URL is
refused at the gate by `authorize_tool_run`, so no capability is minted and
nothing is sent anywhere. A request that was in scope when it was authorised is
refused at the door by `authorize_egress_request`, against the policy in force
when it arrived. Both close the Tool run `denied`; only the second names a
Receipt, because only the second is an attempt that reached a fence with a row
to write.

**The two trust inputs are two flags.** `--authority` is a directory holding a
private key; `--ca` is one file out of it. An installation that exported one
variable for both would be exporting the signing key to whatever it handed the
certificate to, and a child that can sign is a child that can be the door.
`_path` resolves both without a ledger, because absence is not a refusal here:
a door with no authority refuses tunnels and says so, and a plain HTTP request
should not have to name a certificate.

**A door with no authority refuses loudly.** `proxy.serve(authority=None)` is
the default, so HTTPS is opt-in. It is opt-in because the directory holds a
signing key and where that key lives is an operator's decision, not a default
this process should invent; and the refusal names the variable to set rather
than failing at the handshake.

**The runtime trusts the run root and nothing else.** `send` refuses an https
target with no `--ca` before it mints a capability, and `tls.trust` builds a
context from that file alone. A fallback to the system store would make the
door's certificate one of several hundred acceptable answers, which is the
failure this whole arrangement exists to make visible.

### What review changed

Two axes, fifteen findings: nine Standards, six Spec. Eight are fixed here,
three are declined as design, two are deferred to the tickets that own them --
both in the last section -- and two are kept deliberately, with the reason
written down beside the code.

One was behavioural, and it was the change's only real defect. Ticket 09's
second pass made refusals name a Receipt, and `_spend` branched on `receipt is
not None` -- so once a refusal carried one, a blocked request closed the Tool
run as **success** and `rk proxy request` exited 0. The row was right and the
report was a lie. `_spend` now branches on the decision token, closes the run
`denied` and fails the `egress` assertion with the door's own detail, while
still naming the Receipt, because a refusal is as auditable as an exchange. It
was falsified before it was fixed: with the new branch disabled, the live test
fails.

One more was about what the tests could not see. Every test in both suites
substitutes `connector`, so the production `connect` -- the only place a *real*
target certificate is verified -- was executed by nothing;
`test_the_door_itself_refuses_a_target_no_public_authority_vouches_for` now runs
it and gets `SSLCertVerificationError` with the target uncontacted. That is the
same gap the defect above hid in: every blocked arm in the live suite called
`_through` directly rather than `send`, so nothing looked at how a refusal was
reported. The two new arms go through `send`.

Two were vocabulary, and `CONTEXT.md` is enforceable. _Test_ lists **probe**
under _Avoid_ and it had become an identifier in `test_proxy.py`; it is `spare`.
_Startup assertion_ lists **validation** under _Avoid_, and `connect`'s docstring
said "validates an https target" fourteen lines from `send` calling the same act
"verified"; both are now "verify".

The rest were smaller and are all closed: a `# noqa: BLE001` for a linter this
repo does not configure, now a comment saying what the broad catch is for; the
two longest lines in the repo, both four-tuple assertions in `test_database.py`,
now wrapped; `tls_counterparty` reproducing five of `counterparty`'s six lines,
now one fixture taking an optional context; `_through` building and reading its
response twice, now `_answered`; `combine(tunnel, inner)`, which said nothing
beside `take_control` and `describes_this_hop`, now `merge_control`; and
`X-RedKraken-Detail` as a literal in three places, now `DETAIL` beside `RECEIPT`
and `DECISION` -- the runtime puts that header in its own report, so the string
a refusal is explained by has to be the string the door sent.

Two are kept, both flagged as scope creep. **`_refuse` naming a Receipt** is
what criterion 4 asks for: an out-of-scope target refused "with an auditable
blocked Receipt" is not auditable to a caller who has to go looking for the row
in a table they cannot read. What that finding did catch is the consequence,
which is the defect above. **`_port` filling the scheme's default** does change
the shape of blocked http rows, and deliberately: a blocked Receipt is read
beside the allowed ones, which name a port the canonicaliser filled the same
way, and a row saying `null` for `https://host/path` and `443` for
`https://host:443/path` would make two spellings of one refusal look like two
facts. The docstring now says so.

Three are declined as design. **`_through` and `_spend` are not a data clump
wanting `scope.Request`**: `url` is the string an operator typed and `request`
is what survived canonicalisation, both are passed on purpose, and the door's
answer is about the second while the report is about the first. **The protocol
is not one switch repeated**: `connect` decides how to dial and `send` decides
what to verify against, which are different questions that happen to read the
same field, and `trust` standing in for "is this https" in `_through` is the
same fact carried as the object that does the work rather than as a string to
switch on again. **`tls.trust` stays**, as the reviewer suggested it should: it
is one line over `ssl.create_default_context`, and what it adds is the name of
the intent -- this run's root and nothing else -- at the one call site where
getting that wrong is invisible.

### A second review pass, over the committed work

Both axes run again against `97ec396`, over `9c2ba9b` and `f0c7e78`. Nine
findings were real and are fixed; five are declined, and the reason for each is
below.

**The trust the child was given had a second half nobody set.** `SSL_CERT_FILE`
names a file, and OpenSSL looks up the hashed *directory* beside it
independently -- so a child handed this run's root still trusted every root the
system had installed, and the module's own comment claiming the first three
variables "replace the store they name" was false of the first one. It is fixed
by `STORE_VARIABLES`, which empties `SSL_CERT_DIR` in the child environment, and
it was measured rather than reasoned about:
`test_a_root_in_the_hashed_directory_is_not_a_store_the_child_still_reads` puts
a leaf in the file so the issuer can only be found in the directory, verifies a
handshake while the directory is named, and gets `ssl.SSLCertVerificationError`
once the environment has emptied it. With `STORE_VARIABLES` emptied to `()` the test
fails, which is the falsification: an empty value means "look in no directory"
and not "fall back to the default".

**A CONNECT could make the door mint certificates without limit.** The host in a
CONNECT line is unauthenticated -- it has to be, because the capability arrives
inside the tunnel -- and every host not seen before forked `openssl` twice and
left a file in the door's directory. `Authority.context` now stops at
`tls.HOSTS`, which `do_CONNECT` already answers as a 400 because it catches
`tls.Unusable`. The ceiling is on new hosts and not on requests: what has been
certified is still served, or a burst would take a target's own tunnels down
with it.

Two were breaches of what the code already says about itself. `cli._Source`
documented itself as "where one connection string comes from" while carrying a
URL, two paths, a directory and a key file, and the comment above `ARTIFACTS`
called it "the one input that is not a connection string" beside four others
that are not either. And `TRUST` resolved `--ca` under the fact `ca_file` while
`proxy.send` files every refusal about it under `trust_root`: one input under
two names, in the one field whose whole job is to be the name a refusal is filed
under. Both are corrected, and `_Source` now says why the field is not a
spelling invented in `cli`.

The IPv6 bracket strip existed three times -- `scope.normalize_host`,
`proxy._hostport` and `tls._san` -- which is three chances for one of them to
stop agreeing about what a host is. It is `scope.unbracket`, in the module that
owns how a host is spelled.

Two were about what the tests could not see.
`test_an_out_of_scope_https_target_is_refused_before_the_target_is_contacted`
spent a capability that resolved to nothing, so the stub refused on the
capability and the host was never looked at: the test's name and criterion 4's
evidence were about scope, and the assertion was not. `Stub` now refuses by host
through the same exception the real fence raises for both, and the test spends
the good capability against a host it has put out of scope. Criterion 5 had the
mirror gap: what the *target* saw was asserted and so was where the tunnel
ended, and nothing asserted what came back to the agent.
`test_the_agent_is_answered_without_the_capability_it_spent` reads the answer's
headers and body: no authorization echoed, no control header but the Receipt's
label, and neither transcript digest the door had just sealed.

The last two are this file and the one before it. Criterion 1 is unticked, for
the reason in the next section. And ticket 09 recorded nothing about the change
this ticket made to it: a blocked HTTP request closed the Tool run `success` and
exited 0 there, and closes `denied` and exits 2 here, so ticket 09 now says so
rather than describing behaviour the branch no longer has.

Five are declined. **`_path` is not a fifth resolver wanting to be folded in**:
the four that file a ledger differ in where the value comes from and in what
they say when it is absent, and folding them would take a callable per case,
which is the same code behind an indirection. **The dialler's four parameters
are not a clump wanting `scope.Request`**: `connect(host, port, timeout,
protocol)` is handed what it needs to open a socket and nothing else, and a
`Request` would hand the outbound side the path and the query it has no business
seeing. **`openssl` is not added to `rk doctor`**: `REQUIREMENTS` states modules
and distributions, `backup.DUMP` is not checked there either, and the refusal
that matters is at the point of use -- `_run` names the program and exits
`missing_dependency`. Adding one of the two programs would make that report look
complete. **A door with no authority still files a passing `authority`
assertion**, and that is what it is: HTTPS is opt-in, so no authority is a
configuration rather than a fault, and failing the assertion would make every
plain-HTTP run report a failure. The hold's own text says a tunnel is refused
rather than relayed. **`_port` filling the scheme's default** was already
answered in the first pass and the docstring carries the reason.

### Raised by review and deliberately not built here

- **Criterion 3 is half done, and that is why this ticket is not resolved.**
  "Direct HTTPS from the agent network namespace fails even when a client
  ignores conventional proxy environment variables" has a client half and a
  routing half. The client half is here: a client holding the run root cannot
  verify a target it dials directly, and a client configured for `http` alone
  reaches the target by no door -- both asserted. The routing half is a network
  namespace with no route but the door's, and this change creates no namespace.
  It is word for word ticket 11's first criterion ("raw internet TCP, external
  DNS, target networks, provisioning ports and control ports are unreachable
  while the proxy remains reachable"), and building it here would build ticket 11
  twice. What a maintainer has to decide is whether this criterion moves there
  or whether this ticket reopens when it lands; until then the box stays
  unticked, because a TCP connection to a directly-dialled target still succeeds
  and only the certificate check fails.
- **Criterion 1 is not ticked either, because `agent_environment` has no
  production caller.** It is a pure function, fully tested, and nothing in
  `src/redkraken/` builds a child environment yet -- ticket 16 is "start clean
  real agent child", and it is the consumer. So "the runtime configures both
  proxy schemes" is true of a function this branch never calls, which is not the
  same sentence. Adding a caller here was considered and rejected: the only
  candidate was `serve`'s report, which is written when the listener closes, so
  the endpoint it would carry is dead by the time anything reads it. The box was
  ticked in the first pass and is now unticked; what a maintainer decides is
  whether it moves to ticket 16 or this ticket reopens when 16 lands.
- **`NODE_EXTRA_CA_CERTS` adds rather than replaces.** The other three name a
  file and replace it, and `SSL_CERT_DIR` is emptied beside them, so the only
  store left over is Node's own bundled roots: a Node client in the child trusts
  this run *and* the public internet. A further variable does not close that --
  what closes it is having no route to the public internet, which is the
  previous point.
- **One request per tunnel.** `do_CONNECT` loops on `handle_one_request`, but
  `_answer` sets `close_connection = True` on every answer it sends, so in
  practice a client gets one request per CONNECT and reconnects. Keeping the
  connection open would mean deciding what a second request on a tunnel
  authorised for the first may do, and that question is worth answering when
  something asks it.
- **A refused CONNECT is reported as an integrity failure by the runtime.**
  No Receipt is written for a CONNECT, for the reason above, so `_spend` reaches
  its `receipt is None` arm and fails with `integrity_failed`. That is honest --
  the harness cannot account for the attempt -- but it is a different sentence
  from the one the door said, and a caller reading it learns less than the door
  knew.
- **Nothing pins the address that was decided against.** Unchanged from ticket
  09, and now it has a second edge: the leaf is minted for the host in the
  CONNECT line, and `connect` resolves that name again when the request inside
  is authorised. A name that moves between the two is not caught here. Ticket 11.
- **The wire view is still NULL and no budget is counted.** Also unchanged: this
  door injects nothing, so there is no second view of the bytes (ticket 12), and
  it enforces authority rather than quantity (ticket 13).
- **"Capability" is still not in the glossary**, and neither is anything about
  interception. As with tickets 06 to 09, no implementation ticket in this branch
  edits `CONTEXT.md`; `tls.py`'s docstring carries the argument for why the trust
  is narrow, and the terms belong in the glossary whenever `/domain-modeling`
  runs next.
