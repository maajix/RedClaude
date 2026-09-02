# Provider webhook contracts

This note fixes the provider-specific facts used by the projected method. The
target Program's configured contract remains authoritative; these sources do
not grant permission to use production events, secrets or endpoints.

Every claim below was re-read against the provider's own documentation on
2026-09-01 and the disagreements found in that pass are recorded inline, because
a contract note that quietly carries a wrong header name or a wrong signing
payload sends a hunter to refute the wrong thing.

## Stripe

- [Webhook delivery and verification](https://docs.stripe.com/webhooks?lang=node)
- [Verify manually](https://docs.stripe.com/webhooks#verify-manually)
- [Resolve webhook signature verification errors](https://docs.stripe.com/webhooks/signature?lang=node&locale=en-GB)

Stripe signs the original request body and carries the timestamp and signatures
in `Stripe-Signature`, whose value is a comma-separated list of `t=` and
scheme-tagged elements on one line. The signed string is the timestamp, a
literal full stop, and the raw body; the comparison is constant-time.

The endpoint secret is scoped to one endpoint, and test and live secrets
differ. During a roll the header can carry more than one `v1` element, because
Stripe signs with the retiring and the arriving secret for the overlap window.

`v1` is the only live scheme. `v0` is not a retired scheme and never verified
against anything: Stripe emits an additional deliberately fake `v0` element for
test-mode events. Two consequences for a reading. A `v0` element present is a
tell that the delivery is a test event, and a receiver that accepts any scheme
whose digest matches, rather than `v1` alone, has a downgrade the contract
itself invites a hunter to try.

Official libraries default to a five-minute tolerance and a tolerance of zero
removes the recency check. Retries may carry a new signature and timestamp.
Stripe's duplicate guidance is the event id, explicitly not `created`, whose
one-second granularity is not unique; for the rare split-event case Stripe adds
the object id together with the event type.

## Adyen

- [Verify HMAC signatures](https://docs.adyen.com/development-resources/webhooks/secure-webhooks/verify-hmac-signatures)
- [Troubleshoot webhooks: retries, queues and the response budget](https://docs.adyen.com/development-resources/webhooks/troubleshoot)

Standard webhooks (the Checkout and Classic payment notifications) carry the
HMAC in `additionalData.hmacSignature` and are signed over a constructed string
of named values from the parsed item, not over the byte stream. The raw body
rule belongs to the header-signed families (Banking, Management), where the
instruction is not to deserialise before validating. A note that states one rule
for both families is the commonest way to grade an Adyen receiver wrongly.

The HMAC key is linked to one endpoint, is configured under **Security** on the
endpoint rather than under the unrelated additional-settings page, and can be
generated at company scope as well as merchant scope through the Management
API. A new key is required when an endpoint moves from test to live. Adyen's own
rotation guidance asks a receiver to keep accepting the previous key for a
while, so a documented dual-key window exists and a retired key may still be
honoured inside it.

JSON and HTTP POST deliveries carry exactly one notification item; SOAP may
carry up to six. Acceptance is any 2XX and needs no body; the `[accepted]` body
is the legacy scheme. Two operator-visible redelivery primitives follow from the
same page and neither invents a provider state: a response that does not arrive
inside ten seconds marks the webhook failing and queues it for retry, and the
Customer Area carries an explicit retry control beside ignore. Automatic retries
run at nine, eighteen and twenty-seven seconds, then on a widening schedule out
to thirty days, with queues kept per endpoint.

Verification is local recomputation against `additionalData.hmacSignature`;
there is no hosted verify call. Adyen lists validators for Java, PHP, C#,
JavaScript, Ruby and Python. The Java class is `HMACValidator`, and the PHP
library entry point is `Adyen\Util\HmacSignature`, whose payment-webhook method
differs from the header-signed one, which is exactly the pairing a
misintegration gets backwards.

## PayPal

- [Integrate webhooks](https://developer.paypal.com/api/rest/webhooks/rest/)
- [Verify a webhook signature](https://developer.paypal.com/api/webhooks/v1/verify-webhook-signature-post/)
- [IPN handler guidance](https://developer.paypal.com/api/nvp-soap/ipn/ht-ipn/)

PayPal signs asymmetrically. Verification binds the transmission id, the
transmission time, the configured webhook id, the certificate URL, the
algorithm, the signature and the original event, and all seven are required by
the verification call, which answers `SUCCESS` or `FAILURE`. The webhook id
arrives from the listener's own subscription configuration and never from the
delivery, which is what makes it the field that separates one configured
listener from another.

The documentation says a receiver should cache the certificate and says nothing
about constraining which host it is fetched from. A listener that fetches
whatever URL the delivery names and verifies against that certificate can be
satisfied by a certificate the caller chose, so the certificate-origin question
is the highest-value reading this provider offers and it is a configuration
question rather than a cryptographic one.

PayPal publishes no inbound duplicate-detection contract. The event id is
described only as the id of the notification and is nowhere promised unique, so
a receiver's dedup store is merchant engineering rather than provider
guarantee, and a reading must establish it by resending rather than assume it.
Against that, PayPal does expose an event-details read, so a listener can
re-fetch the event server to server and confirm the provider holds it in the
state the delivery claimed; a receiver that never does is trusting the delivery
alone.

Classic IPN differs: the receiver posts the notification back and reads
`VERIFIED` or `INVALID`. PayPal documents, without enforcing at that step, that
a handler must also check the completed status, that the transaction id was not
already processed, that the recipient address is the merchant's own, and that
the amount and currency are the expected ones. Those four are documented and
unenforced, which is the shape most IPN defects take.

No maintained first-party library performs this verification today: the old PHP
SDK is archived and the current server SDKs carry no webhook verification at
all, so integrations hand-roll it. Bespoke verification is therefore the normal
case for this provider rather than the exception.

## Failure patterns on record

Each entry is a disclosed defect in a receiver, not in a provider, and each maps
to one arm of the projected method.

- Signature verification absent altogether on an endpoint whose URL is
  discoverable by a lower-privileged account, so a hand-written body with a
  plausible event type executes the flow:
  [n8n Stripe trigger, CVE-2026-21894](https://github.com/n8n-io/n8n/security/advisories/GHSA-jf52-3f2h-h9j5),
  and the older methodology write-up that names webhook endpoints as an
  under-tested surface,
  [Bypassing payments using webhooks](https://lightningsecurity.io/blog/bypassing-payments-using-webhooks/).
- A configured secret left empty, which makes the digest computable by anyone,
  compounded by fulfilling on session status without reading the paid state and
  by not checking that the order's payment method matched the callback source:
  [new-api, CVE-2026-41432](https://github.com/QuantumNous/new-api/security/advisories/GHSA-xff3-5c9p-2mr4).
- A verified notification applied without checking the amount or the receiving
  account it names:
  [Contact Form 7 PayPal and Stripe add-on, CVE-2026-9189](https://github.com/advisories/GHSA-vr4h-g9wj-2p4g).
- The caller choosing which environment validates the notification, so a
  sandbox verdict settles a live order:
  [WP Hotel Booking, CVE-2026-11901](https://github.com/advisories/GHSA-p429-p65m-q8hj),
  and the same shape a decade earlier in
  [paypal-ipn, CVE-2014-10067](https://github.com/advisories/GHSA-h698-r4hm-w94p).
- Payment fulfilled with no verification path at all:
  [WPForms PayPal Commerce, CVE-2026-4986](https://blog.himanshuanand.com/2026/07/reporter-11-10-people-found-the-wpforms-paypal-bug-before-me-cve-2026-4986/).
- A signature honoured with no freshness binding, so a captured delivery
  replays later:
  [GitLab hardening issue 587536](https://gitlab.com/gitlab-org/gitlab/-/issues/587536).
- Registration-side defects that belong to other Playbooks rather than this
  one, kept here so a hunter routes them rather than files them as credential
  verification: a callback target that reaches internal addresses directly or
  through a redirect
  ([243277](https://hackerone.com/reports/243277),
  [508459](https://hackerone.com/reports/508459)), and a subscription whose
  tenant is taken from the caller
  ([cross-tenant webhook plant](https://vokecyber.com/research/calcom-cross-tenant-webhook-plant)).
- The control set the arms are written against:
  [OWASP webhook security guidelines](https://github.com/OWASP/CheatSheetSeries/blob/master/cheatsheets_draft/Webhook_Security_Guidelines_Cheat_Sheet.md).

## Review rule

Re-open the official contract when the Playbook reaches `bb:stale_after`, when
the Program uses another provider or webhook family, or when its configured
freshness, key-rotation or duplicate policy differs from these defaults. The
`v0` scheme, the Adyen signing-string family split and the certificate-origin
question are the three facts that have already moved or been misread once, so
they are the three to re-read first.
