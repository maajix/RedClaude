---
description: Turn a scope root into typed, deduplicated Attack Surface. Use when a Program has hosts or roots nothing has been recorded against yet, or when a deploy changed and the recorded surface needs to be re-derived rather than trusted.
bb:roles: ["recon", "web_hunter"]
bb:tool_groups: ["exec.tool_run", "net.request", "state.propose", "state.read"]
bb:evidence_profile: allowed_receipt_only
bb:runtime-tools: ["jq", "js_map", "js_parse", "js_routes"]
---

# Enumerate a surface

Produce entities and relationships that later work can be scheduled against.
This step decides what exists. It does not decide what is wrong with it.

## 1. Read what is already recorded

Call `mcp__rk2__get_attack_surface` first. Every entity already there is one you
must not propose again under a second label; the deduplication cell is shared,
and a second row for one host is a second queue of work against the same thing.

Complete this step holding the set of roots this Task is for and the set of
entities already recorded under them.

## 2. Ask each root, and the places a server declares itself

Call `mcp__rk2__http_request` per root. Then ask that origin for `/robots.txt`,
`/sitemap.xml` and `/.well-known/security.txt`.

Those three are not guesses. Each is a location a published standard reserves,
which makes requesting one a question the server already agreed to answer, and
the answer is a list of paths the operator wrote down. Three requests per
origin, no more, and a 404 to all three is itself the answer.

Nothing else is requested by name. A path that merely sounds right is a guess,
and a Task that guesses is running a scanner one request at a time.

Complete this step holding, per root, four Receipts or the refusals that stand
in for them.

## 3. Follow what the answers named

An answer names more surface than it is. Request each named thing once:

* the `Location` of every 3xx, and then the `Location` of that answer, to the
  end of the chain;
* every script, stylesheet, manifest and document a stored body points at;
* every URL a `sitemap.xml` or a `robots.txt` listed.

One exchange per URL, and each one its own call: the Receipt is per exchange,
and an entity you cannot name a Receipt for is an entity you inferred.

One level and no further. What a bundle names inside itself is read, not
fetched, and reading it is `analyse-source`'s Task rather than this one's.
Depth here is how a surface walk turns into a crawl nobody bounded.

Scope is the proxy's decision, not yours. A blocked or deferred Receipt is a
control condition and is reported as one -- it is evidence about the boundary,
not a reason to try a different spelling of the same host.

Complete this step when every 3xx this Task received has had its `Location`
requested or refused, and every reference named by a body it stored has a
Receipt of its own.

## 4. Read the scripts you stored

A single-page application's routes are in its bundle and nowhere else. The
answer you already hold is the input: call `mcp__rk2__get_artifact` with no
label to list what this Task stored, and run `js_routes` through
`mcp__rk2__run_tool` over each Artifact that came back from a script.

`js_routes` reports only the paths that were handed to something that makes a
request, each with the call site and the byte offset that grounds it. That is
why it is the one to run: a bundle is full of path-shaped strings, and the ones
nothing calls are strings. Propose an endpoint for a route it returned and cite
the run; propose nothing for a string you read yourself.

Two more, where the first one earns them. `js_parse` names the source map the
bundle points at, and a map is a URL the answer named, so step 3 already says
what to do with it. `js_map` reads a map that came back and recovers the
originals inside it, which is where a route survives that the build minified
away.

Complete this step when every script Artifact this Task stored has been through
`js_routes`, or when there were none.

## 5. Type what came back

Every proposed entity carries the Receipt that showed it and the kind it is.
Where the response is JSON, run `jq` through `mcp__rk2__run_tool` over the
stored Artifact rather than reading the shape out of the body by eye: the run
is recorded, its output is an Artifact, and a route list nobody can re-derive
is a claim.

An endpoint proposed here carries its method and whether it answered without a
credential, because those two are what decide which later work is selectable at
all. An endpoint recorded with neither is surface nothing can be scheduled
against.

Complete this step when every proposed entity, relationship and observation
cites a Receipt or a Tool run that this Task actually produced.

## 6. Stop at the edge of enumeration

Do not test. A parameter that looks reflective, an endpoint that looks
unauthenticated and a header that looks stale are surface, and they are recorded
as surface. Proposing a hypothesis about one is the hunter's Task and the
scheduler's decision, and the evidence for it does not exist yet.
