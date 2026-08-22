---
description: Ask whether the authority a route validates is the authority it fetches, by sending two arms whose URLs differ only in which of two hosts the Program controls sits after the userinfo, and differencing the two stored responses against a baseline that was itself invariant.
bb:category: injection
bb:outputs: ["injection.url_authority"]
bb:triggers_all: ["authenticated_endpoint", "read_method", "url_valued_parameter"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-04-15
bb:provenance: Written for ticket 54 as the v2 replacement for v1's ssrf-url-routing pack against a new url_authority leaf added by ticket 54; the pack's four pages are attached as maintainer references and their metadata endpoints, their port sweeps, their rebinding races and their internal-range wordlists are refused by step 7.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "response_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["dns-rebinding.md", "open-redirection.md", "pdf-generators.md", "ssrf.md"]
---

# Ask whether the checker and the fetcher read the same URL

A route that fetches a URL a caller supplied has two pieces of code reading that
URL: the one that decides whether it is allowed, and the one that opens the
connection. The defect in this class is always that they disagree about which
part of the string is the host.

The subject is an authenticated read endpoint carrying a parameter a recon pass
typed as a URL. The question is whether the authority the route fetched is the
authority it validated, and the whole reading is six requests -- every one of
them pointed at a host the Program itself controls.

## 1. Name the two hosts you are allowed to point at

Before anything is sent, write down two names, and this reading may use no
others:

* the Program's declared out-of-band channel. Call `mcp__rk2__mint_callback`
  with the channel name and this endpoint's label, and embed the address it
  returns exactly as given. That address is one hostname and it gives this
  reading one of its two names, never both: the publisher behind a channel
  serves a single host, so there is no second label under it to vary
* a target the Program owns and has marked as a controlled fetch destination

Both must serve a distinct, marked document, so a response can say which one was
reached. If the Program declares only one of the two, this Playbook has one name
and its two arms have nothing to differ by, so it cannot read the route and says
so. It does not substitute a host that merely looks harmless, and it does not
invent a second name beneath the channel.

Then read the parameter from the state view, and read what the route is allowed
to fetch: the vendor, the manual host, the image origin, whatever an ordinary
request names. That allowed host is what the arms will put in front of the `@`.

## 2. Establish the baseline, twice

Send the request through `mcp__rk2__http_request`, with the parameter carrying an
ordinary, allowed URL. Then send it again, unchanged. Both go out as whichever
Identity the Task was opened under: the step does not choose it and there is no
argument for it.

Two identical requests, for the reason every comparison here starts with two.
Record what the route does with a URL it accepts: whether the fetched document
comes back, whether it comes back summarised, whether only a status does. That
decides whether step 5 has anything to read.

## 3. Send the two arms

Two more requests. Both carry the allowed host where a checker that reads the
string prefix will find it, and one of the two controlled hosts where a parser
will find it:

    https://<allowed-host>@<controlled-a>/rk-probe
    https://<allowed-host>@<controlled-b>/rk-probe

Two arms rather than one, and both pointed at hosts the Program controls, because
the comparison needs two answers that differ from each other for a reason the
route caused. A single arm that returns something has nothing to be compared
with.

Where userinfo is filtered, three other confusions are available, each still
pointed only at the two controlled hosts:

* a backslash before the `@`, which several parsers split on and several do not
* the allowed host as the left label of a controlled domain the Program owns,
  where the checker compares a prefix rather than a suffix
* an allowed URL that answers a redirect to a controlled host, where the checker
  runs before the redirect and the fetcher follows it

Say which confusion was used. Interleave with the baseline, hold everything else
constant, and send two rounds of the pair.

## 4. Send the arm that is plainly allowed

One more request: the ordinary allowed URL from step 2, sent again beside the
arms. It must still answer the way it did.

That is this class's control. It says the route still fetches, that the
difference the arms showed is the authority and not the route falling over, and
that the two arms' refusal -- if that is what came back -- is a refusal of the
authority rather than of the whole reading.

## 5. Difference the stored bytes

Run `compare-responses` over the two arms, then over the control arm and the
baseline. Cite what the script returns.

Arm against arm is the differential: two URLs identical but for which controlled
host follows the `@`, two different documents, and the fetcher used the authority
the caller wrote. The marker in each controlled document is what names which one
was reached, and it belongs in the observation.

A route that refuses both arms with the identical body is refuting the
Hypothesis, whether the refusal is a 403, a 400 or an empty preview.

## 6. State the claim, and state what would refute it

The Hypothesis is `injection.url_authority` on the endpoint. It is supported when
the two arms differ from each other in both rounds, each answer carries the
marker of the controlled host it named, the baseline was invariant, and the
plainly allowed arm still worked. It is refuted when the two arms are invariant
against each other against a stable baseline -- one parser answered once, and the
thing that was checked is the thing that was fetched.

Anything else is inconclusive, and the commonest inconclusive here is the route
that fetches without telling the caller anything: no body, no status difference,
no timing separation. That is not a failure of this reading and it is not an
invitation to reach further.

Three neighbours are close.

* Where the question is whether a request reaches a host at all, answered by an
  arrival at a correlator rather than by a response, the class is
  `injection.request_forgery` and the Playbook is `webhooks`. A blind fetcher
  belongs there, not here.
* Where the caller's URL decides where a *browser* is sent rather than where the
  server fetches, the class is `client_side.navigation` and the Playbook is
  `routing`.
* Where the served document loads a script from a host the target does not
  claim, the class is `injection.foreign_resource` and the Playbook is
  `external-resources`.

Cite the two Artifacts and the difference the script returned.

## 7. The ceiling, restated at the end

Step 1 declared the half of this that binds every request -- the two hosts this
reading may name, written down before anything was sent. The rest is here.

This Playbook is `read_only` and its baseline is a session that stays stable. It
sends six requests to the one endpoint the Task names, and every URL in every one
of them names either the route's own allowed host or a host the Program
controls.

It does not point the target at a cloud metadata address, at loopback, at a
link-local address, at an RFC 1918 range, at a Kubernetes or Consul service
address, or at any host on the target's side of a boundary. It does not sweep
ports, sweep names, or read a response's timing to guess what is behind a
firewall. It does not race a DNS answer. It does not contact a third party the
Program never named -- not a public URL shortener, not a paste site, not another
company's API, and not somebody else's callback service.

The four attached references are largely about exactly those techniques. Each one
says why it is out: the property is that the checker and the fetcher disagreed
about the authority, and two hosts the Program owns prove that completely.
Discovering what is reachable behind the target is a different question, and it
is one an operator authorises, not one a reading takes.
