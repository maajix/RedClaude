# 69 — Publish engagement files on an out-of-band host whose name changes

**What to build:** An out-of-band endpoint the harness owns end to end: a bounded directory of engagement files a target can fetch, a tunnel that gives it a public name, and a channel declaration that survives the name changing every time the tunnel is restarted.

**Blocked by:** 14 — Accept one explicitly configured callback Observation; 67 — Give an inbound arrival its own identity.

**Status:** ready-for-agent

- [ ] A target can fetch a file the operator put in one directory, over a public name, and nothing else on the machine is reachable.
- [ ] That fetch becomes an Interaction and an Observation attributed to a subject, without an external OOB provider being involved.
- [ ] The public name is a record in the database, not a string in a configuration file, and an agent reads the live one or gets nothing.
- [ ] Restarting the tunnel the next day releases the old name and every correlator minted against it, and no verb hands out a name that is no longer bound.
- [ ] Starting the publisher over a directory that fails any isolation rule refuses to start.

## Why

Two limits of the interactsh channels the 2026-08-12 live run used. Neither is a
defect in ticket 14; both are things a hosted endpoint would fix.

- **A canary cannot carry a payload.** An XXE against a target that resolves
  external entities needs a DTD the target can fetch. interactsh answers a fixed
  body, so the exploit file has to live somewhere else, and "somewhere else" was a
  hand-rolled Python server behind a tunnel, outside the harness and outside the
  record.
- **The fetch of that file is itself evidence and was not recorded.** A file host
  in front of a target sees exactly the thing the OOB channel exists to see: an
  inbound request caused by our payload. It should produce an Observation for the
  same reason an interactsh hit does.

The operator's stated preference is a Cloudflare tunnel, for the control it gives.
Measured against a live quick tunnel on 2026-08-12:

| Fact | Measured |
| --- | --- |
| Name | `https://homeless-sustainable-consultation-preferred.trycloudflare.com`, printed once in cloudflared's own log |
| Wildcard subdomains | none: a quick tunnel is one hostname |
| Lifetime | the process. A restart gets a different name |
| Path and query | forwarded verbatim, including `/<32 hex>/x.dtd?q=1` |
| Peer address | `Cf-Connecting-Ip` and `X-Forwarded-For`, both the real client address |
| Host header | the tunnel hostname |

## The two things that have to change

### 1. A correlator that is not a DNS label

`callback_correlator_label` takes the label immediately beneath the channel
endpoint. A host with no wildcard cannot vary its labels, so on a quick tunnel
every arrival would carry no correlator and be refused -- correctly, and
uselessly. What a tunnel does give is the path, verbatim, to a server we wrote.

So a channel gains a **placement**: `label` (today's behaviour, the only one a
`dns` channel may have) or `path`, where the correlator is the first path segment
and everything after it is the payload's business:

    https://<endpoint>/<correlator>/exploit.dtd

`callback_correlator_from_path(p_path)` is the mirror of
`callback_correlator_label`, with the same three answers: the segment, NULL for a
request that names none, NULL for anything it must not match. The attribution
trigger asks whichever question the channel's placement names, and it stays the
one place the question is asked.

### 2. An endpoint that is not in the policy

`program_callback_channels.host` is immutable with its scope version, which is
right: an operator's declaration should not drift. A tunnel name is not a
declaration, it is a fact about today, so it does not belong in the compiled
policy at all -- putting it there would change `policy_sha256` every morning and
make the Program's identity depend on Cloudflare's word list.

A channel therefore declares a **provider** instead of a host:

```toml
[[callback]]
name = "oob-files"
kind = "http"
provider = "cloudflare-quick"   # or "static", which keeps today's `host`
placement = "path"
```

and the live name lives in a new append-only table:

    callback_channel_bindings(
        id, program_id, scope_version, channel_name,
        provider, endpoint_host, bound_at, released_at,
        evidence_sha256)          -- the tunnel's own startup output, stored

`callback_correlators` gains `binding_id`, NOT NULL for a channel whose provider
is dynamic. That is what makes yesterday's correlator dead on its own terms: it
names a binding that is released, so `resolve_callback_correlator` does not
return it and the trigger refuses an arrival claiming it. Nothing has to remember
to clean up.

Admission reads the endpoint from the live binding rather than from
`program_callback_channels.host`, which is NULL for these channels.

A dynamic channel compiles to **no egress rule**. Today an `http` channel adds
one so the door may reach the endpoint; our own file host is inbound only, and an
egress rule whose host changes daily is a hole with a schedule.

## The publisher

`rk oob serve --config <path> --channel <name>`: one directory, published, with
every request treated as evidence.

Isolation, all of it fail-closed at startup rather than per request:

- The root is `$RK_OOB_ROOT/<program-slug>/` and refuses to be anything else --
  not a symlink, not containing one, not a parent of the configuration, not
  `$HOME`, not a directory holding a `.git`.
- Every file in it must carry an allowlisted suffix (`.dtd .xml .xsl .svg .txt
  .json .html .js`) and be a regular file. One that does not is a refusal to
  start, not a file quietly skipped: an operator who put something else in there
  is an operator who does not know what is published.
- `GET` and `HEAD`. No listing, no dotfiles, no path segment inside the file name,
  a resolved path whose parent must be the root, and a size ceiling.
- Bound to loopback. The tunnel process on this machine is the only thing that
  reaches it.

Every request is answered and then recorded:

- A request whose first segment resolves a live correlator becomes an Interaction
  and an Observation through `record_callback_interaction`, with the raw request
  bytes as the artifact, `Cf-Connecting-Ip` as the peer and the tunnel's `Host`
  header checked against the binding.
- A request that resolves nothing is answered 404 and written to the publisher's
  log only. There is nothing to attribute it to, and a row that named no
  correlator would be an unattributable claim about a target.

The file the correlator's directory serves is the same file for every correlator:
the segment addresses the canary, not the content. That keeps one exploit file
usable across subjects without an operator maintaining a copy per correlator.

## Lifecycle

- `rk oob up` starts `cloudflared tunnel --url http://127.0.0.1:<port>`, reads the
  hostname out of its output, stores that output as the binding's evidence, and
  writes the binding. It refuses when the publisher is not running: a bound name
  in front of nothing is a name an agent will embed in a payload.
- `rk oob status` prints the live endpoint, its binding, and how many correlators
  hang off it. This is the only supported way to learn the name -- the point of
  the ticket is that nothing hardcodes it.
- `rk oob down` releases the binding. Every correlator minted against it is dead
  by the FK above, and the verb says how many that was.
- On start, a binding whose tunnel process is gone is released before anything
  else happens. A pause overnight and a restart in the morning is the ordinary
  path, and the old name must not survive it.

## The upgrade path, stated once

A quick tunnel is ephemeral, rate-limited and gives one name. A **named** tunnel
on a Cloudflare-hosted zone gives a stable hostname and a wildcard record, which
would restore label placement and let a DNS channel work as well. That is
`provider = "cloudflare-named"` with a credentials file, and it changes nothing
above: the binding table, the placement column and the publisher are the same. It
is not in this ticket because `yconlab.de` is at Hetzner, so it is a zone move
first and a feature second.
