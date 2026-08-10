# 11 — Close direct-egress, DNS, redirect and subresource bypasses

**What to build:** Prove that every target exchange caused from the agent topology is independently reauthorized by the proxy, including redirects and browser-style subresources.

**Blocked by:** 10 — Send HTTPS through the same capability path.

**Status:** needs-triage

- [ ] Inside the real agent container, raw internet TCP, external DNS, target networks, provisioning ports and control ports are unreachable while the proxy remains reachable.
- [x] The proxy resolves and pins the actual destination and rechecks scope after DNS resolution rather than trusting the requested hostname alone.
- [x] Redirect targets are canonicalized and scope-checked independently before following them.
- [x] Each subresource exchange resolves the live capability independently and receives its own Receipt under the parent Tool run.
- [ ] Capability expiry, Tool run closure, Lease loss and Program Halt between parent and child requests stop the next exchange before target contact.
- [x] Negative fixtures count target contacts so every refused bypass proves that no request arrived.

## Comments

Implemented on branch `implementation/startup-assertion` in commit `096196e` on
2026-08-10. **The first and fifth criteria are not ticked and this ticket is not
resolved**, which is why the status is `needs-triage` rather than `resolved`: see
the last section.

Before this change the door decided a *name* and dialled whatever a resolver
handed back. Everything between those two acts was trust: the request that was
authorised and the socket that was opened were related only by the assumption
that one lookup answers the same thing twice. That is the whole of the rebinding
bypass, and it is the gap tickets 09 and 10 both recorded as "nothing pins the
address that was decided against".

The order is now **decide (name), resolve, check routability, decide (address),
dial**, and each step is a place a request stops. `resolve` is the only lookup;
`destination` collapses duplicate answers, keeps the resolver's order and refuses
the whole name if *any* address it gave is off the public internet; the address
that will be dialled goes back to the database as a second decision; and only
then does `connect` open a socket, to that address, with the host name carried
separately for TLS and for the `Host` header.

### What is asserted, and by what

`tests/test_proxy.py` grows from 41 to 63.

`AddressTest` is the seven that need neither socket nor decision. Fourteen
addresses named one refusal class at a time -- unspecified, loopback, both
spellings of a mapped loopback, link-local including `169.254.169.254`,
multicast, the three private ranges and carrier-grade NAT, and a string that is
not an address at all -- because the sentence in the blocked Receipt is what an
operator reads to tell a hostile target from a misconfigured Program.
`224.0.0.1` is why the multicast arm exists: `is_global` answers yes for it. The
rebinding arm is `test_a_name_that_answers_with_one_bad_address_answers_for_all_of_them`,
which refuses `(93.184.216.34, 127.0.0.1)` and pins **both** in the record: a row
naming only the offending address would not show that a public answer was on
offer beside it, which is the shape of the attack. Two more assert that a name
answering with nothing is `target unresolved` with nothing pinned, and two that a
`Location` is canonicalised against the request it came in -- `../admin` and
`/v1/%2e%2e/admin` both become `http://a.example.test/admin` -- or recorded as
nothing at all when it is a scheme this fence cannot follow.

`RedirectTest` and `CrossHostRedirectTest` are three tests run twice, once
against a target that redirects to a path on itself and once against a second
target on another port, because a redirect that leaves the host is the case where
"the client comes back through the door" stops being obvious. A followed redirect
is two exchanges with two Receipts, the parent's `notes` names where it pointed,
and a capability that stopped resolving between the two hops stops the second one
with the second target's `seen` list empty.

`RefusalTest` is three on which of two things the second decision refused. That
decision resolves the capability again before it looks at an address, so a Tool
run that closed since the first decision arrives there rather than at the gate;
both refusals carry `23514`, so the text is what separates them, and a Receipt
reading `address refused` for a lapsed lease sends an auditor to look at an
address that was never the problem.

`ExchangeTest` gains six against a real target: the address decided is the
address dialled, the Receipt names every address the name answered with, a name
is **not resolved at all** for a request that was going to be refused -- DNS is
itself egress, and a lookup for a refused request is a lookup an operator has to
explain -- a name resolving off the public internet opens no socket, a name
resolving to nothing is refused with no address named, and an address the Program
withdrew is refused between the two acts with the target's count still zero.

`ProxyEgressTest` in `tests/test_database.py` grows from 20 to 25, and the fence
in them is the real `rk2_proxy` against a real PostgreSQL. Setup resolves every
name to `93.184.216.34` and dials the loopback port the fixture listens on, so
the address that was decided and the socket that was opened are visibly two
facts. The five are: the allowed row names the resolved address; an address
`SCOPED` withdraws is refused with nothing dialled; a name answering `127.0.0.1`
or `169.254.169.254` is refused by the door in both cases; four exchanges on one
capability leave four Receipts under one Tool run, two allowed and two blocked,
which is criterion 4 read out of the rows; and a task lease that lapses between
two requests stops the second before contact.

`tests/test_cli.py` moves one number: the address exclusion added to `SCOPED`
compiles to four more rules, two ports by two protocols.

Offline the suite is 522 tests green with 14 skipped, up from 500; against the
scratch PostgreSQL 18 cluster it is **662 tests, green, nothing skipped**, up
from 635, and `python3 -m compileall -q src/redkraken tests` is clean.

### Decisions worth naming

**A lookup is egress, so it happens after the first decision.** The name is
decided against the policy before the resolver is called, and the address is
decided after. Resolving first would be simpler and would mean a refused request
had already sent a query naming the target to whatever server the host is
configured with. `test_a_name_is_not_resolved_for_a_request_that_was_going_to_be_refused`
is the assertion, and it reads the resolver's own call list rather than the
Receipt.

**One bad address refuses the whole name.** Not "dial the good one". Which half
of a split answer gets used would then be the choice of whoever runs the zone, on
a lookup this door does not repeat, and the record would show a public address
for a request that could still have gone to `169.254.169.254` on a retry. Both
addresses go in `pinned` so the refusal can be read back as what it was.

**The second decision is a SECURITY DEFINER function.** `rk2_proxy` has no
`SELECT` on `program_scope_rules` and must not gain one: the runtime role's read
surface is ticket 66's subject, and a role that can read every rule can enumerate
a Program's scope without spending anything. `authorize_egress_address` resolves
the capability, validates the protocol and port, shape-checks the address, and
calls `scope_class_of` inside the definer. The migration's fence check now
carries a `proxy_can_read_the_scope_rules` rule that fails if that grant ever
appears, and the migration ends asserting the function grant exists, the table
grant does not, and the fence reports zero problems.

**Only `excluded` refuses, and nothing comes back.** A policy written in names
answers `unlisted` about nearly every address there is, so refusing on anything
but an explicit withdrawal would make the address check a second, stricter scope
that no Program author wrote. And the function returns no class: the Receipt
records what a request was allowed **as**, and that is the class the name earned.
A column filled with `unlisted` on every row would be a fact about the policy
language, not about the request.

**The door does not follow redirects.** Following one would be an exchange the
client never asked for, against a target the client never named, and §7's whole
subresource rule is that each exchange earns its own verdict. So the client
follows, and comes back through the same fence, where the new URL is a new
request with its own capability check, its own resolution and its own Receipt.
What the door owes is the *link*: `notes` on the parent says `redirect to <url>`,
canonicalised, because without it the child Receipt names a URL nobody asked for
and an auditor cannot tell a followed redirect from an agent inventing a target.

**`pinned_ips` names all of them, dialled first.** The check that let the request
through was made of the whole answer set, so a record naming only the address
that was used could not be read back as evidence that the rest were looked at.
Blocked rows carry it too, which is what makes "no socket was opened towards
this" a fact in the row rather than an inference from its absence.

**Four refusal reasons, and they are not interchangeable.** `target unresolved`
is no answer and pins nothing. `address refused` is an answer this door will not
dial, and pins it. `target unreachable` is a socket that failed after the request
was authorised, which is the target's state and not the fence's verdict.
`capability refused` is the first decision -- and now also a capability that
lapsed between the two, which is the one thing the review pass changed.

### What review changed

Both axes were run over the staged change. They were run in this thread rather
than as the two parallel sub-agents the skill describes, because this session was
started with instructions not to spawn agents; the axes were kept separate and
neither report was reranked against the other.

Standards found no hard violation and three judgement calls. One was real and is
fixed: `Fence.authorize_address` mapped every `pg.DatabaseError` to
`Refused("address refused")`, and the same function raises `egress capability
refused` for a Tool run that closed since the gate. So a lapsed lease would have
been filed under an address that was never the problem -- the detail carried the
truth and the `reason` column, which is the one an auditor filters on, did not.
`_refusal` now separates them on the server's own message, and `RefusalTest`
asserts both directions plus the detail surviving either way.

Spec found the two unticked criteria below and no scope creep.

### Raised by review and deliberately not built here

- **Criterion 1 is not built, and that is why this ticket is not resolved.**
  "Inside the real agent container, raw internet TCP, external DNS, target
  networks, provisioning ports and control ports are unreachable while the proxy
  remains reachable" needs two things this repository does not have: a container
  for the agent, and a network namespace with no route out but the door's.
  Nothing under `src/redkraken/` starts a child process at all -- ticket 16 is
  "start clean real agent child", and it is where the topology is born. It is
  also the routing half of ticket 10's third criterion, recorded there as
  unfinished for the same reason. What a maintainer has to decide is whether this
  criterion moves to 16 or whether both tickets reopen when 16 lands. Everything
  asserted here is asserted at the door, which is the correct place for it and is
  not the same sentence: a client that ignores the proxy still reaches a target's
  TCP port from this machine.
- **Criterion 5 is three of four.** Capability expiry, Tool run closure and Lease
  loss all stop the next exchange before contact, and they stop it for one
  reason: `resolve_egress_capability` requires the Tool run running and unexpired,
  the agent run open, the Program open and -- when the run carries a task -- that
  task still `claimed` or `running` with an unexpired lease. The live test moves
  one lease's expiry into the past between two requests on one capability, and
  asserts the door opened no socket for the second while the Tool run, the Agent
  run and the capability itself are all still exactly as they were.
  **Program Halt has no schema concept anywhere in this branch**: there is no
  halt state on `programs`, no halt table and nothing that could be asserted
  without inventing the mechanism. Ticket 13 is "enforce Halt and request budget
  at egress", and it owns that. The box stays unticked rather than being ticked
  for three quarters.
- **Only the address that will be dialled goes to the second decision.** The
  others are checked for routability and recorded, but a name answering with two
  public addresses where the *second* is withdrawn by scope is not refused. It is
  also not contacted, because the door dials the first and does not retry, so the
  gap is between what the record shows and what was decided rather than in what
  crossed the fence. Refusing the whole name on any withdrawn address would match
  the routability rule's posture and cost one round trip per address; it is worth
  doing when something asks for it.
- **`connect` now takes five parameters and the fifth is the address.** Ticket 10
  declined folding the first four into `scope.Request` -- the dialler is handed
  what it needs to open a socket and nothing else, and a `Request` would hand the
  outbound side a path and a query it has no business seeing. The address makes
  that argument stronger rather than weaker: it is precisely the field a `Request`
  does not have, and it is there so the name is not resolved a second time.
- **The resolver is a seam and not a policy.** `resolve` is `getaddrinfo`, so
  which server answers, whether DNSSEC was checked and whether the answer was
  cached are the host's configuration and not this door's. Pinning makes the
  answer *auditable*; it does not make it trustworthy. A resolver the harness
  runs itself is a real question and belongs with the container topology.
- **The wire view is still NULL and no budget is counted.** Unchanged from
  tickets 09 and 10: this door injects nothing, so there is no second view of the
  bytes (ticket 12), and it enforces authority rather than quantity (ticket 13).
