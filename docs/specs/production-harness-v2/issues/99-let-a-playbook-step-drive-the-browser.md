# 99 — Let a playbook step drive the browser

**What to build:** A Contract that opens a browser mission, and the actions the
sixteen client-side techniques need that the registered ten cannot express. The
lane is built and paid for; no model can reach it.

**Blocked by:** nothing. The lane exists end to end under an operator's hand, so
nothing in this ticket waits on another capability.

**Status:** ready-for-agent

- [x] A Playbook step can open a browser mission by a tool call. Today the only
      entry point is the operator CLI -- `_browser_run` at `cli.py:2629` behind
      the parser at `cli.py:1135-1201`, which requires `--plan` as a JSON file
      on disk, `--agent-run`, `--image` and `--authority`. No browser Contract
      exists in `roster.CONTRACTS` (`roster.py:592-845`), and the migration
      already names the tool the run would be opened under:
      `20260814T040000Z__a_browser_mission_runs_behind_the_door.sql:732` returns
      the constant `mcp__rk2__browse`.
- [x] `skills/browser-evidence/SKILL.md:63` stops being false. It tells the
      model "Start the mission through `mcp__rk2__run_tool`", and that tool's
      enum is closed to four offline binaries -- `("jq", "js_map", "js_parse",
      "js_routes")` at `roster.py:784` -- so every one of the sixteen techniques
      in research file `06` is written for a Skill whose first instruction
      cannot be followed.
- [x] The Contract grants no capability the lane does not already have. The plan
      shape is at least as narrow as `browser_action_arguments`, the plan digest
      is taken before the run and checked against the result digest, and the
      `ROLES` table (`roster.py:902-997`) says which roles may open one. Every
      ceiling and the closed action set become load-bearing from the day a model
      can reach them: `navigate` and `click` both carry `reaches_network`, and
      `click` carries `submits` (`…20260814T040000Z…:188-207`), which the
      migration calls the whole of how a mission acquires POST.
- [x] The Skill says that response headers are already on the record, which
      costs a paragraph and no code: the `message/http` transcript behind
      `response_agent_sha` carries CSP, CSP-Report-Only, COOP, COEP, CORP,
      Permissions-Policy, `Service-Worker-Allowed` and `Vary` per response,
      already hashed (`proxy.py:317`, `proxy.py:789-798`). The honest caveat is
      stated with it: `Set-Cookie` and the target's authentication headers are
      wire-only and absent from that view (`proxy.py:348-357`), so a
      cookie-prefix reading says it is reading the request side and the target's
      behaviour rather than the raw header.
- [ ] A `probe` row declares its own outcome keys the way an action already
      does, so a step's digest-visible answer can be `verdict=reflected,
      sink=url_attribute` rather than one word. Every value stays a word from
      `rk2_browser_outcome_word` (`…20260814T040000Z…:710-718`: a boolean, a
      number of at most five digits, or a lowercase identifier), so the digest
      still cannot be made to carry a timestamp, a nonce or per-run noise, and
      the probe's full JSON stays an Artifact (`browser_driver.py:639-645`).
- [ ] A `read_client_state` action exists over a closed `kind` set --
      `local_storage`, `session_storage`, `indexeddb_names`, `cookies`,
      `service_workers`, `message_listeners` -- and it plants nothing, sends
      nothing and changes no state. Cookies return name, domain, path,
      `httpOnly`, `secure`, `sameSite` and prefix and **never a value**, because
      the door strips `Set-Cookie` from the agent view on purpose
      (`proxy.py:348-357`) and an Identity's value is injected at the door and
      never handed to the browser (`browser.py:8-11`, `cli.py:1193-1199`); a jar
      read that returned values would put back exactly what those two lines
      remove. The check that faults a probe touching `document.cookie` or the
      storages narrows to probes rather than being relaxed: the new action is
      the sanctioned path and probes stay out.
- [ ] `navigate` admits a fragment. The migration refused one because the
      Receipt would not match, and `_classified` already matches on host and
      path alone (`browser.py:466-480`), so classifying the URL without its
      fragment is what the code does today. Without it every fragment-source DOM
      XSS reading is unavailable.
- [ ] A `send_message` action posts one registry-owned body to the page from the
      same origin, the way `inject` types a registry-owned payload
      (`browser_driver.py:565-568`) -- and it does not ship before the probe
      outcome keys and the client-state read, because without a listener
      inventory it is a message sent into the dark. It is the first action that
      fabricates an event the target did not cause, and the body is owned by a
      migration exactly as a probe's payload is.
- [ ] **The execution oracle is decided in this ticket rather than assumed.**
      The research verdict is "it works, and its added value is narrower than it
      looks": for markup injected into the document the mission is looking at,
      `markup_injection` already answers "did the parser build an element" by
      reading the DOM, without any element acting. The oracle earns its keep
      only where that read cannot go -- a cross-origin frame, a document the
      mission navigated away from, a CSS `url()` sink with no element to count,
      and clobbering impact. If it is built it is a second registry probe with a
      **relative same-origin path marker** (a blocked Receipt stores no
      transcript and the query survives only as a digest, `proxy.py:743`, while
      the path is stored verbatim), its answer arrives as a Receipt and not as a
      verdict, and a negative from it is inconclusive rather than a refutation,
      because CSP or a lazy-loaded element can stop a fetch that markup would
      otherwise have caused. It is also an ADR-level decision and not a
      migration nobody discusses: the current probe is justified in as many
      words -- `rk-probe` has "no script, no attribute a browser acts on and no
      content, so planting it changes what the document IS without changing what
      it DOES" -- and an element that fetches does something.
- [x] **The isolation gap the research names is recorded where a reader of this
      lane finds it.** Chromium runs `--no-sandbox` (`browser_driver.py:115-119`)
      because the container drops every capability and the two together need a
      capability set it does not have, so with the OS sandbox off a renderer
      compromise is code running as uid 65534 and the container is the only
      boundary left. That container is hardened -- `--cap-drop ALL`,
      `no-new-privileges=true`, `--read-only`, `--user 65534:65534`,
      `--pull never`, `--entrypoint ""`, `--rm` (`isolation.py:166-208`) -- and
      **no seccomp profile that would let Chromium's own sandbox start exists
      anywhere in this tree**, which was searched for and found only in the
      research file. Playwright's own Docker guidance names that file as the
      thing needed to run Chromium with a sandbox. Restoring it is the one
      hardening step this lane has not taken, and this ticket either takes it or
      names the ticket that will.
- [x] What is refused stays refused and each refusal keeps its reason: no
      `Page.setBypassCSP`, no `Runtime.addBinding` page-to-driver channel, no
      in-browser request interception, no action that hosts a second origin, and
      no model-authored JavaScript in the page -- the last because an expression
      the model wrote "could read `document.cookie`, it could fetch whatever it
      liked from the page's own origin, and it could return whatever verdict it
      wanted the run to record", which the migration says at
      `…20260814T040000Z…:275-290` and which is the sentence capability E will
      be tempted by.

## Why

Capabilities D and E in
`docs/research/playbook-state-of-the-art/09-capability-matrix.md` -- 22
techniques for a Contract that starts a mission and 19 for a wider action and
probe set, overlapping on all sixteen techniques of file `06`. The matrix
records the state as **present but unreachable from a playbook step**: ten
actions in `browser_driver.py:502-661`, the registry, the driver and the
operator verb all built, and no Contract anywhere.

The ranked additions and the two decisions above are
`docs/research/harness-capabilities/13-browser-capability.md`, sections
"Proposed additions", "The execution oracle question" and "Isolation and
egress". Its ranking is by refused bug classes per unit of new power, and it
notes that the first two additions grant no new power at all.

## Comments

**2026-08-24 -- Arbeitsblock 3 built the Contract half and parked the rest.**

Six of the eleven criteria are done. `mcp__rk2__browse` is a Contract of its own
group `exec.browser_run`, held by `web_hunter` alone, whose single argument is
`steps`: one to thirty-two objects whose `action` is one of the registered ten
and whose `arguments` are a bounded object. The Identity slot is not an argument
-- the supervisor passes the one the Task claimed -- and the roster states a
floor that `open_browser_run` then narrows per action, so nothing here can widen
what the lane already refused. `browser.mission` is the operator path's own core,
extracted and shared, so the CLI verb and the tool call open, gate, perform, file
and close through one body of code and differ only in the actor they record.

Five criteria are not done, and they are the ones that add power: probe outcome
keys, `read_client_state`, a fragment on `navigate`, `send_message`, and the
execution-oracle decision. Arbeitsblock 3 is bounded to offering the existing
lane through a closed Contract with no authority growth, so none of them was
started. The ticket stays `ready-for-agent` for exactly those five.

The isolation criterion was answered by naming the ticket rather than by taking
the work: ticket 174 owns the seccomp profile, and `browser_driver.py` says so
beside the `--no-sandbox` flag itself.

`check_wiring`'s register moved with the work: the `W10 browser-evidence` row is
gone -- the Skill names a tool that runs a browser now, and its repetition
paragraph names `compare-responses`, the one program `web_hunter` is actually
granted -- and four W5 rows arrived in its place. A mission mints a
`browser_run`, a `browser_step`, a `browser_step_result` and a
`tool_run_artifact` label, and no read verb takes any of them back. Those are
the W4 rows for the same four relations seen from the other side, so they are
owed to ticket 129 with the read they are waiting for.
