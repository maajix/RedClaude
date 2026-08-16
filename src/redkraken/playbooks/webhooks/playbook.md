---
description: Ask whether a URL the caller supplies is one the server itself will fetch, by pointing it at a correlator the runtime minted and waiting for the interaction to arrive out of band.
bb:category: injection
bb:outputs: ["injection.request_forgery"]
bb:triggers_all: ["state_changing_method", "url_valued_parameter"]
bb:skills: ["compare-responses", "handle-untrusted-content"]
bb:risk: approval_required
bb:effects: mutates_object
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-02-15
bb:provenance: Written for ticket 49 as the v2 replacement for v1's webhooks pack, against the request-forgery leaf of the ticket 18 vocabulary; v1 shipped a README for this topic and no reference text, so nothing is attached.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_differential", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "callback_interaction", "polarity": "supports", "min_count": 1}]
---

# Ask whether the server goes where it is told

A webhook registration, a callback URL, an avatar imported from a link and a
"fetch this document" field are the same shape: the caller supplies a URL and
the server makes a request to it. The class is about that request, and the only
thing that proves it happened is the request arriving somewhere the runtime is
watching.

This Playbook is deliberately built around that arrival. A response that took
longer, an error mentioning a connection, a body that changed -- all of those
are consistent with a fetch and equally consistent with a validator that parsed
the URL and rejected it. Nearly every invalid report of this class is one of
those three read as the fetch.

## 1. Name the parameter and mint a correlator

The subject is a state-changing endpoint with a parameter the recorded surface
types as a URL. Read which parameter that is from the surface rather than
guessing it from the field name.

Ask the runtime for a correlator for this subject. The host it names is a
channel this Program declared, and the correlator is what ties an arrival back
to this one call. A URL pointing anywhere else -- a public interaction service,
a host you control personally -- is out of scope and produces nothing this
system can file.

## 2. Establish the control: something the server cannot fetch

Send the request once with the parameter set to a URL on a host that cannot
resolve, and store the answer. Then send it once with the correlator URL, and
store that answer too.

The control is the pair. If the server answers both identically and immediately,
it is not fetching either: it is storing a string. If the unresolvable host
produces a different answer -- slower, an error, a different status -- then
something on the server side tried to resolve it, and the difference is what
attributes the later arrival to this parameter rather than to a scheduler that
fetches everything.

## 3. Wait for the arrival, and only for as long as you declared

A webhook is often delivered by a queue rather than in the request, so the
arrival can be seconds or minutes behind the response. Decide the window before
sending and record it.

An arrival is the finding. No arrival inside the declared window is not a
refutation on its own -- it is the absence of one -- and this Playbook says so
in step 5 rather than dressing it up.

## 4. Read anything that came back as untrusted content

If the response carries the fetched body, follow `handle-untrusted-content`
before quoting it. It is a document from a host chosen in this request, which is
the definition of content that is not the target's.

Run `compare-responses` over the control answer and the correlator answer and
cite what the script returns.

## 5. State the claim, and state what would refute it

The Hypothesis is `injection.request_forgery` on the endpoint. It is supported
when an interaction carrying this correlator arrived on the declared channel and
the control pair shows the difference is attributable to this parameter. It is
refuted when the correlator answer is invariant against the control answer and
nothing arrived: the server took the string and did nothing with it.

Everything else is inconclusive, and the largest inconclusive case is the one
worth naming: nothing arrived, but the answers differed. That is a server doing
something with the URL -- validating it, resolving it, refusing it -- and which
of those it is has not been established. Record the observation and leave the
claim unmade.

Where the fetch reaches is a further question this Playbook does not ask. A
correlator that arrived says the server made a request; it does not say what
else it can reach, and an internal address is the scheduler's next Task rather
than this claim's second half.

## 6. Leave the target as close to how you found it as this can

This Playbook writes, and says so: its trigger is a state-changing method and
its two calls in step 2 are two of them. A registration it created is a
registration it removes, through the endpoint the surface records for that, and
a removal that fails is recorded rather than retried.

That is why `bb:effects` is `mutates_object` and the risk floor is
`approval_required`. A run that reasons its way to `read_only` because it only
meant to look has described its intention rather than its requests.

Beyond the two calls it declares, nothing: it does not walk an address range
through the parameter, does not follow a redirect chain by hand, and does not
send the request again because the window closed empty.
