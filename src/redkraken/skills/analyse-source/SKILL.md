---
description: Read a stored source Artifact and ground every route, parameter and endpoint in the bytes it came from. Use when a bundle, a source map or a configuration document has been stored and the question is what it says the application exposes.
bb:roles: ["js_analyst"]
bb:tool_groups: ["exec.tool_run", "state.propose", "state.read"]
bb:evidence_profile: successful_tool_run
bb:scripts: [{"name": "extract_paths.py", "description": "Path-shaped and URL-shaped string literals in one stored Artifact, as one JSON object. `paths` is what can ground; `literals` is what the build wrote, method and query string and all.", "checks": [{"artifacts": ["const r=[\"/api/v2/orders\",`/api/v2/orders/${id}`];fetch(\"https://cdn.example.com/app.js\");const t=\"not a path\";"], "stdout": {"literals": ["/api/v2/orders", "/api/v2/orders/${id}"], "paths": ["/api/v2/orders", "/api/v2/orders/${id}"], "scanned_literals": 4, "urls": ["https://cdn.example.com/app.js"]}}, {"artifacts": ["const re=/api/;let n=1;"], "stdout": {"literals": [], "paths": [], "scanned_literals": 0, "urls": []}}, {"artifacts": ["fetch(\"/api/orders?id=1&sort=asc\");const cdn=\"//cdn.example.com/app.js\";const root=\"/\";"], "stdout": {"literals": ["/api/orders?id=1&sort=asc"], "paths": ["/api/orders"], "scanned_literals": 3, "urls": []}}, {"artifacts": ["var E={repos:{get:[\"GET /repos/{owner}/{repo}\"]},actions:{listCaches:[\"GET /repos/{owner}/{repo}/actions/caches{?key,ref}\"]}};"], "stdout": {"literals": ["GET /repos/{owner}/{repo}", "GET /repos/{owner}/{repo}/actions/caches{?key,ref}"], "paths": ["/repos/{owner}/{repo}", "/repos/{owner}/{repo}/actions/caches"], "scanned_literals": 2, "urls": []}}]}]
bb:references: ["code-review.md", "sinks-csharp.md", "sinks-go.md", "sinks-java.md", "sinks-js.md", "sinks-kotlin.md", "sinks-php.md", "sinks-python.md", "sinks-ruby.md", "sinks-rust.md"]
bb:runtime-tools: ["jq"]
---

# Analyse a source Artifact

The analyst has no network. Its input is bytes that are already stored under
their hash, and its output is claims that point back at those bytes.

## 1. Take the Artifact by hash

Call `mcp__rk2__get_artifact` with the hash the Task names. That hash is what
every conclusion below will cite, and an Artifact you were not given is one this
Task has no provenance for.

Complete this step holding the hash and the bytes it names.

## 2. Extract with a tool, not by eye

Where the document is JSON -- a source map, a manifest, a configuration -- run
`jq` through `mcp__rk2__run_tool` over the stored Artifact.

Where it is not -- a bundle, a chunk, a template -- run `extract_paths.py`
through `mcp__rk2__run_skill_script` over the same Artifact. It answers with the
path-shaped and URL-shaped literals the file holds, and with how many strings it
looked at, so what comes back reads as the proportion it is.

It answers twice about the same literal and the difference is step 3's. `paths`
is the route with its method and its query string cut off, which is the spelling
a proposal has to use. `literals` is the string as the build wrote it, and the
query string in there is the parameter half of the surface: name it in the
finding, do not put it in the route.

Either way the run is recorded, its output is a new Artifact, and the extraction
is something a second party can repeat. Reading a route list out of a minified
bundle by eye produces a list nobody can check and that will not survive a
validator. Where neither fits the document, say what you read and quote it, so
the quote is checkable against the Artifact hash even though the extraction was
not.

## 3. Ground every proposed route

A route, parameter or endpoint proposed from source is a claim that these bytes
say so. Each one carries the Artifact hash and the Tool run that produced it.
A route that is in the framework's conventions rather than in the file is not
grounded, however likely it is.

Complete this step when every proposal cites the run that showed it.

## 4. Stop before reachability

Source says what the application refers to. It does not say what answers. An
endpoint found here is surface for somebody else to reach; asserting that it is
live, unauthenticated or exploitable is a claim that needs an exchange, and this
role has no way to make one.
