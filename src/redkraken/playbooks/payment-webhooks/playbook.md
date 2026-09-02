---
description: Ask whether an incoming payment event is authenticated and applied once, by replaying one Program-supplied test or sandbox delivery beside an unsigned, body-modified, stale and duplicate arm and reading the target's authoritative payment state after each.
bb:category: authentication
bb:outputs: ["authentication.credential_verification"]
bb:triggers_all: ["json_request", "state_changing_method", "unauthenticated_endpoint"]
bb:skills: ["compare-responses", "handle-untrusted-content"]
bb:risk: approval_required
bb:effects: mutates_object
bb:baseline: pristine_surface
bb:status: draft
bb:stale_after: 2027-09-01
bb:provenance: Written for ticket 231 from the current official Stripe, Adyen and PayPal webhook verification contracts. Kept separate from webhooks because that Playbook asks whether caller input controls an outbound server request and concludes injection.request_forgery; this one asks whether a credential on an incoming provider event is verified and concludes authentication.credential_verification.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_differential", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["provider-webhook-contracts.md"]
---

# Ask whether the payment event presented a credential

An incoming payment webhook is an unauthenticated route only in the browser or
session sense. The provider still presents a credential over the original body
and delivery metadata. Authenticity, freshness and idempotent application are
three separate properties. An HTTP success response proves none of them: many
receivers deliberately acknowledge duplicates or invalid events while changing
no payment state.

Every reading is one Test proposed through `mcp__rk2__propose_test`, and every
send uses `mcp__rk2__http_request`. Work only with a Program-owned provider
sandbox, test mode, or a Program-supplied signed fixture. Do not obtain endpoint
secrets, replay live customer events, create real charges or send events to an
unapproved endpoint.

## 1. Bind one endpoint, event and authoritative state

Record the exact endpoint, provider, environment, event type, event identifier,
object identifier, signed fields, signature carrier, provider timestamp,
documented freshness rule, duplicate key and legal target transition. A test
and production endpoint are different verifiers even when their URLs look
similar. Do not infer one provider's signed representation from another's.

Identify a separate read route for the authoritative order, payment, balance or
ledger state. The receiver response is context; that read route is the verdict.
Acquire one genuine, unused sandbox delivery as the control. If the Program
cannot supply a valid delivery or signing fixture, record the gap and stop:
without a positive control, every rejection could be routing or configuration.

Use one fresh target object for the control and another for the variant. The
basic Test is: baseline state, genuine control delivery, state after, fresh-object
state, one changed delivery, state after. Difference only the fields naming the
expected transition, not volatile headers or timestamps.

## 2. Follow the provider's signed representation

### Stripe

Preserve the exact raw request body. Verify `Stripe-Signature` with the secret
for this endpoint and environment, including the signed timestamp and the
Program's configured tolerance. Official libraries use a five-minute default
tolerance; setting the tolerance to zero removes the recency check. A provider
retry is not necessarily byte-identical because Stripe can issue a new
signature and timestamp for each attempt. Treat the event id as the primary
duplicate key and also consider object id plus event type where the target's
business transition requires it. Do not read the second-resolution creation
field as a duplicate key: two distinct events can carry the same value.

One live scheme tag is defined, and a second tag rides along on test-mode
deliveries as a deliberately unverifiable value. Record which tags the
Program's supplied fixture carries, because a receiver that authenticates
whichever tag matches, rather than the one live tag, accepts a value the
provider never meant to be verifiable. Record also whether the fixture carries
two live-scheme values, which is what a secret currently rolling looks like.

### Adyen

For Standard webhooks, verify `additionalData.hmacSignature` over the documented
ordered, escaped field representation. For other webhook families, verify the
signature header over the raw body. The two families are signed over different
material, so establish which one this endpoint receives before calling any
reserialisation arm a bypass. Bind the HMAC key to the configured endpoint and
environment; a key is issued per endpoint and a move from test to live requires
a new one. During an approved rotation, test both the old and new key only
inside the documented overlap rather than assuming an instantaneous cutover.
Use the provider reference and event code together when the receiver's state
machine distinguishes several events for one payment.

Two Program-side redelivery primitives exist here and neither invents a
provider state: the queue retries an endpoint that does not answer inside the
documented response budget, and the operator console carries an explicit retry
control. Where the Program approves one, prefer it over hand-built duplicates,
because it produces the provider's own second delivery of an event the target
has already applied once.

### PayPal

Bind the transmission id, transmission time, configured webhook id, signature
algorithm, certificate location, signature and original body. The target may
verify locally or use PayPal's verification API; either path must authenticate
the same original delivery. Preserve the body bytes and apply the Program's
freshness rule. Deduplicate the transmission or event identifier while keeping
the business object's legal state transition authoritative. The listener's own
configured webhook identifier is the field that separates one listener from
another, and it never arrives in the delivery.

Two readings are specific to this provider. The certificate location arrives in
the delivery and the published guidance does not constrain which host it may
name, so establish whether the receiver pins that host: a verifier satisfied by
a certificate the caller chose is authenticating the caller. And no maintained
first-party library performs this verification, so the logic under test is
usually the target's own, which is where the arms of section 3 are most likely
to discriminate. Where the provider exposes an event read of its own, note
whether the receiver re-reads the event out of band before applying it; a
receiver that never does has only the delivery to go on.

Deduplication here is merchant engineering rather than a provider promise, so
establish the dedup store by resending an approved sandbox delivery rather than
assuming an identifier is unique. On the legacy notification family, the
postback verdict authenticates the message and says nothing about the completed
state, the already-processed identifier, the receiving account or the amount;
those four are the receiver's own checks and are where that family fails.

## 3. Signature and raw-body integrity

First deliver the genuine control and confirm the expected authoritative state
transition. On a fresh object, choose exactly one variant:

1. remove the signature carrier;
2. change one signature byte;
3. change one inert body byte without recomputing the signature;
4. use a signed test event for the wrong endpoint or environment, but only when
   the Program supplied that event for this comparison;
5. reserialize the same JSON with a harmless whitespace or key-order change;
6. present the signature under a scheme or algorithm tag the provider contract
   does not define as verifiable, leaving the digest otherwise well-formed; or
7. where the Program states that this environment has no verification secret
   configured, or supplies an empty one, sign with that empty value.

Arm 7 is a configuration reading and not a cryptographic one, so it is asked of
the Program before it is sent: a receiver that verifies against an unset secret
accepts a digest anyone can compute, and the operator has to confirm that the
unset state is the environment's real state rather than a test artefact. Park
it under `credential_needed` where the Program cannot answer.

The reserialisation arm establishes whether the verifier authenticates original
bytes or an application-parsed reconstruction, and it is only meaningful for a
family the provider signs over the body. It is not a requirement that a provider
accept reserialized JSON; the provider contract decides. A supported
`authentication.credential_verification` result requires the variant to move
the authoritative payment state while the valid control moves its own fresh
object. If the variant is acknowledged but leaves state unchanged, that is a
safe receiver policy, not a bypass. Stop after the first discriminating arm.

## 4. Freshness and exact replay

Use another genuine sandbox event and read state after its first application.
Then compare, one Test at a time:

- the exact same delivery inside the documented retry window;
- the exact same delivery after the documented freshness window;
- a genuine provider retry carrying the provider's fresh metadata; and
- a separately authenticated event that requests the same logical transition.

Record acceptance separately from application. A duplicate may legitimately
receive success while producing no second ledger entry, credit, entitlement or
state transition. A freshness defect exists only when the target applies a
delivery outside its own contract, not merely when it acknowledges it. If a
correctly authenticated replay applies twice, hand the observed duplicate
transition to the `race-conditions` Playbook for the business-logic claim; this
Playbook settles whether the incoming credential was verified.

## 5. Out-of-order and terminal-state delivery

Where the Program can generate signed sandbox fixtures, select the smallest
legal adjacent pair, such as authorised then captured, or captured then
refunded. Confirm that sequence on a fresh object. On another fresh object,
reverse only the pair or deliver a late predecessor after the terminal event.
Read the provider object and the target's order and ledger state after every
delivery.

Do not invent signatures, event types or impossible provider states. A receiver
that authenticates both events can still corrupt its local state by applying
them in arrival order. Preserve that evidence and hand it to `routing` for the
`business_logic.workflow_order` conclusion instead of calling it an
authentication failure.

## 6. An authentic event the receiver reads too generously

A verified delivery still carries fields the receiver may or may not read, and
the commonest disclosed defect in this family is not a forged signature at all:
it is a genuine event applied on the strength of the wrong field. This section
is asked only with Program-supplied sandbox events that already differ in the
field being read, never by editing a signed body.

Use the control from section 1, then one arm at a time:

- an event whose outer lifecycle field reads complete while the paid or
  captured field does not, against a control where both agree;
- an event that names an amount or currency below the order's own, where the
  Program can produce one, against the matching legitimate event;
- an event naming a receiving account, merchant or environment other than the
  one this order was created under; and
- an authentic event from a second configured provider or method, delivered
  against an order the target created through the first.

The verdict is the order, entitlement or ledger state, never the acknowledgement.
An order fulfilled from a delivery whose own fields say unpaid, understated or
foreign is a business-logic conclusion: file the amount reading as
`business_logic.quantity_or_price` and the source or lifecycle reading as
`business_logic.workflow_order` through `payment-workflows` and `routing`, and
keep this Playbook's own claim for the credential itself. Where an arm needs an
event the Program will not issue, record the untested arm in those words.

## 7. Claims, cleanup and stop conditions

Propose `authentication.credential_verification` only when a missing, modified,
wrong-context or otherwise invalid provider credential causes the authoritative
payment state to move and the genuine control establishes the route. Record
freshness, duplicate application and transition-order observations under the
business Playbooks that own those conclusions. Cite the exact provider contract,
endpoint environment, signature representation and state fields used.

Two neighbouring surfaces are deliberately not read here, and naming them is
how a hunter routes them instead of filing them as this class. Where the target
lets a caller choose the address a provider event is delivered to, that is an
outbound fetch the target makes and belongs to `webhooks` and
`ssrf-url-routing`. Where a caller can subscribe an endpoint on behalf of
another tenant, or read and rewrite another tenant's delivery configuration,
that is ownership of the configuration object and belongs to
`object-ownership`. Both are recorded and handed on, not settled here.

Reset sandbox objects, credits and local ledger fixtures when the Program
provides a reversible operation. Never print or store webhook secrets in a Test,
request note or claim. Refuse TLS relaxation, certificate substitution, live
provider events, real monetary effects, payout or chargeback creation, merchant
notifications and third-party endpoints. Park a receiver that lacks a genuine
control, an authoritative state read or a documented consistency window rather
than manufacturing certainty from status codes.
