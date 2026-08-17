# Transport attacks: the whole page is refused, and this is the argument

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The transport audit. Run testssl.sh or sslscan against the host and read the
report: which protocol versions the endpoint still negotiates, which cipher
suites it offers, whether the certificate matches the name, when it expires, who
signed it, whether the chain is complete, whether HSTS is set and preloaded,
whether the renegotiation extension is present. Then the named attacks --
Heartbleed for the memory read, POODLE and BEAST against block ciphers in the
older versions, CRIME and BREACH against compression, downgrade dances that get a
peer to accept something weaker than it prefers.

## Why the Playbook refuses all of it

**The harness cannot observe the transport.** Every request this corpus sends
goes through the scope proxy, and 018 records the consequence plainly: no
transport-layer claim can be settled through it. The proxy terminates and
re-establishes; what a Playbook sees is a decoded exchange, not the handshake the
target performed. A reading that reported a cipher suite would be reporting the
proxy's, and a receipt that says something the reading could not have seen is
worse than no receipt.

**Scanning the endpoint is out of scope.** testssl.sh and sslscan work by opening
many connections and offering deliberately restricted parameters. That is a
scanner against a port, which criterion 3 of the ticket that authored
`deployment` excludes: scoped web and API ingress, nothing underneath it.

**The named attacks are memory disclosure and forced downgrade.** Heartbleed
returns whatever is adjacent in the process's memory -- other people's sessions,
other people's request bodies. A downgrade forces a peer to accept parameters it
was configured to avoid. Neither has a `read_only` version.

**The findings mostly are not the Program's anyway.** A terminating front end,
a load balancer or a CDN sets these parameters, they are frequently outside the
scope grant, and they are usually already known to the operator from their own
monitoring.

## What the Playbook kept

Nothing technical. What it kept is the boundary, and step 7 states it: this
Playbook does not renegotiate, downgrade, offer a weaker cipher or ask what the
certificate says.

What is worth carrying from the page is one framing. A transport audit is a
question about the deployment rather than about the application, and `deployment`
is the Playbook for questions about the deployment. So this is the natural place
for a reading to drift into, which is exactly why the ceiling has to name it.

## If the transport genuinely matters

Say so and stop. A verdict of `inconclusive` that names the missing capability --
"the scope proxy prevents any observation of the handshake" -- routes to an
operator who can run the audit outside this harness, with their own tooling,
against a target they have confirmed is in scope.

That is a better outcome than a claim the evidence cannot carry. It is also the
only honest one available here.
