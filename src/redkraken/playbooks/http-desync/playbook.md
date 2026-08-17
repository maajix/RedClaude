---
description: Ask what protocol and cipher the target itself negotiates rather than what the interception proxy negotiated with it, by requesting one measurement on the lane whose receipt is admissible for that question and comparing it against what the deployment advertises to callers.
bb:category: transport
bb:outputs: ["transport.tls_configuration"]
bb:triggers_all: ["read_method", "spa_surface", "tech_edge_proxy"]
bb:skills: ["compare-responses"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-05-15
bb:provenance: Written for ticket 56 as the v2 replacement for v1's http-desync pack against the tls_configuration leaf 018 already named; the pack's three pages are attached as maintainer references and its smuggling, desync, coalescing and tunnelling techniques are refused by step 6, because 025 records request framing as unmakeable behind the interception proxy and enforces that refusal in a trigger.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "transport_parameters_observed", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "transport_parameters_observed", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "transport_parameters_observed", "polarity": "supports", "min_count": 1}]
bb:references: ["http-attacks-http-2-downgrading.md", "http-attacks-request-smuggling-and-http-desync.md", "proxy-tunnels.md"]
---

# Ask the wire, because everything else in this harness is the proxy talking

Every ordinary request this harness sends is decoded and re-encoded on the way
out. The bytes the target frames, the protocol it agreed to speak and the
certificate it presented are all things the interception proxy saw and the
reading did not, and a reading that reported them would be describing its own
door.

That is not a gap in this Playbook, it is this Playbook's subject. One lane in
this harness exists to make an unintercepted measurement, and one class of claim
is admissible from it: what the target negotiated. Everything else the v1 pack
under this name contained -- smuggling, desync, coalescing, tunnelling -- is
refused, and step 6 says why with the mechanism attached.

The subject is a read on an application shell with a terminating front end in
front of it: many parallel requests for one document is where a disagreement
about the protocol shows up at all. The whole reading is one measurement, one
repeat and two ordinary reads.

## 1. Say what the deployment advertises, from two ordinary reads

Send the subject twice, through the ordinary path, presenting nothing. Record
from the answers alone:

* the protocol each response was delivered over, as this harness saw it
* `Alt-Svc`, if it is there, which is the deployment telling callers what else
  it will speak
* `Strict-Transport-Security`, if it is there

None of these is a claim yet. All three are what the deployment says about
itself, and the point of writing them down first is that step 4 compares them
against what the target actually did.

Twice rather than once for the same reason step 3 repeats the measurement. A
fleet whose members are configured differently advertises differently, and an
advertisement that moved between two sends is not the deployment's policy but one
member's. Where the two reads disagree on any of the three, this reading has
nothing stable to compare a measurement against and the verdict is
`inconclusive`, saying which of the three moved.

Complete this step with the three values, and with the word `absent` for each
one that is not there. An absent header is a measurement; a guessed one is not.

## 2. Request the measurement

One measurement, on the lane that does not intercept.

A measurement is not a request the reading composes. It is asked for by purpose,
it goes out unintercepted, and what comes back is a receipt carrying what the
target negotiated: the version, the cipher, the protocol chosen by ALPN, and
whether the chain and the hostname verified.

The receipt is admissible for this claim only if it is citable, and citable is a
property the database computes rather than the reading asserts: an unintercepted
exchange, allowed by the scope policy, whose version was recorded and whose chain
and hostname both verified. A receipt that fails any of those describes something
other than the target's transport, and an observation citing it is refused where
it is written.

If no citable receipt can be obtained, stop at step 6's last paragraph. The
verdict is `inconclusive`, it names the missing capability, and it routes to an
operator. That is the honest end of this reading and it is a common one.

## 3. Repeat the measurement

One more, identical, and this is the control.

A handshake is a negotiation, and a negotiation can go two ways on two
connections -- a front end fleet whose members are configured differently, a
session resumed rather than established, a cipher preference that depends on
what was offered. Two measurements agreeing is what makes the first one a
property of the target. Two measurements disagreeing is a finding about the
deployment's consistency and is reported as `inconclusive` here, because this
Playbook's claim is about what the target negotiates and there turned out to be
two answers.

## 4. Compare the measurement against the advertisement

Run `compare-responses` over the two ordinary reads, which is what settles that
the advertisement is the deployment's and not one member's. Then set the
measurement's fields beside the three values step 1 recorded, and cite both.

What is being looked for is a disagreement between the two, and there are two
shapes of it worth naming:

* the front end offers a protocol by `Alt-Svc` that the measurement shows it does
  not negotiate, or negotiates only one hop in
* the negotiated version or cipher is below what the deployment's own policy
  header implies it requires

There is deliberately no third shape about the certificate. A receipt whose chain
or hostname did not verify is not citable at all -- both are conjuncts of the
generated column -- so a reading can never hold one to report it from, and what
the certificate says is `transport.certificate_trust`, a different leaf with its
own `allowed_fields` that this Playbook does not output.

Every field asserted has to be one the receipt carries. The observation is
checked field by field against the receipt's wire-side columns at the moment it
is written, so a value the reading inferred, remembered from the ordinary path or
read off this harness's own certificate is rejected there rather than believed.

## 5. State the claim, and state what would refute it

The Hypothesis is `transport.tls_configuration` on the subject. It is supported
when a citable receipt shows a negotiated version, cipher or protocol weaker than
what the deployment advertises or than what its own policy header implies, and a
second citable receipt shows the same thing. It is refuted when the two citable
receipts agree with each other and with the advertisement -- which is what a
correctly configured front end looks like, and is worth recording as such.

Anything else is inconclusive: no citable receipt, two receipts that disagree, a
deployment that advertises nothing to compare against.

Two neighbours are close, and both are other Playbooks.

* Where the question is whether the front end and the application resolve one
  path differently, the class is `authorization.edge_rule` and the Playbook is
  `deployment`.
* Where the question is which channel policy headers a page carries, the class is
  `transport.header_policy` and the Playbook is `browser-framing`.

Cite the receipt, by label, and the fields it recorded. Quote the advertisement
from step 1 beside them.

## 6. The ceiling

This Playbook is `read_only`, holds no session, and sends two ordinary reads and
two measurements to one deployment.

It does not desynchronise anything, and this is the refusal the v1 pack under
this name was mostly made of. No request in it carries two length headers, a
chunked body with a trailing length, a header the front end and the application
would frame differently, a request line the front end would rewrite, or anything
else whose effect lands on the next connection. Two reasons, and the second is
the one that settles it. The next connection belongs to somebody who is not part
of this engagement, so a technique that poisons it has no bounded blast radius
and no undo -- and separately, 025 records request framing as unmakeable through
this harness at all: the proxy parses and re-serialises every request, so the
bytes the target frames are the proxy's rather than the reading's, and a
smuggling result would describe the proxy. That refusal is a trigger on the
Hypothesis table, not advice: the class cannot be written down.

It does not tunnel and it does not coalesce. It sends no `CONNECT`, no
absolute-form request line, and no request whose authority names a host other
than the one the Task scoped. A reading that got a front end to forward on its
behalf has reached something the Program did not grant, whatever the answer was.

It does not audit the endpoint. It does not scan a port, offer a deliberately
restricted parameter set, renegotiate, or open many connections to see which of
them get a different answer -- the two measurements in step 3 are two, and they
are two because a negotiation needs a repeat to be a property rather than an
event.

It does not compose the measurement itself. The measurement lane is a purpose the
runtime honours, and the claim rests on a receipt the database judged citable.
Where the runtime this Playbook is executing under has no route to that lane, the
reading does not substitute the ordinary path, does not read this harness's own
socket, and does not report what the proxy negotiated. The verdict is
`inconclusive`, it says which capability was missing in those words, and it stops
-- which is a better outcome than a claim the evidence cannot carry, and, until
that route exists, the only honest one available here.
