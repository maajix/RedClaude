# agent-browser is not adopted: it keeps its own books; its Skill text is kept

agent-browser is a Rust CLI from Vercel Labs that drives Chrome over CDP through
a persistent daemon, and publishes seven Skills describing how an agent should
use it. Ticket 89 asked whether it and its Skills buy this harness anything the
browser slice it already has does not. The prose does. The binary does not.
Adopt the instructions, decline the dependency.

What it is, before it is judged. `vercel-labs/agent-browser`, Apache-2.0,
"Copyright 2025 Vercel, Inc.", version 0.34.0. The npm package is a Node shim
whose postinstall downloads a platform binary from GitHub Releases, and
`agent-browser install` then downloads a Chrome for Testing build. It speaks CDP
directly from Rust against a vendored copy of the protocol JSON. The daemon is
not a separate artifact: the same binary re-executes itself with
`AGENT_BROWSER_DAEMON` set and listens on a Unix domain socket named for the
session, with a one-hour idle timeout that `AGENT_BROWSER_IDLE_TIMEOUT_MS=0`
disables.

Two of the three hard questions resolved in its favour, and the one that was
expected to kill it did not. The fence holds: `--proxy` becomes
`--proxy-server=` verbatim in the Chromium argv, `--args` passes arbitrary flags
through untouched -- `args.extend(user_args)` is the last line of the builder --
so the SPKI pin this repository already uses is reachable the same way it always
was. And the capability header is the same gap ADR 0004 recorded and the same
shim closes it: agent-browser cannot put `Proxy-Authorization: RedKraken <hex>`
on the hop, because its only credential path is `Fetch.continueWithAuth` with a
username and a password and Chromium picks the scheme -- but ticket 31's
loopback shim is an ordinary proxy and agent-browser cannot tell it from any
other. The daemon question, which was the one carbonyl never had to answer, also
resolves: on Unix the rendezvous is a filesystem path in a directory we name,
`batch` collapses a whole plan into the one argv `isolation.run_tool` accepts,
and a container that goes away takes the daemon with it. Their own
`vercel-sandbox` Skill is that pattern under another name.

The question it fails is the third one, and it fails on the thing this
repository exists to protect. `check_browser_runs` holds the requests the driver
counted against the Receipts the door wrote, per Tool run, and that check means
something only because the thing counting is the thing making the requests.
agent-browser counts too -- `network requests`, `network request <id>`,
`network har start/stop` -- but its log is session-scoped, not step-scoped,
and `browser_step_results.network_requests` is a per-step integer inside the
result digest. To keep the check we would have to drive
`network requests --clear` between steps and believe what came back, which is
a second bookkeeper for
egress reporting on itself. The fence half of the accounting survives -- every
byte still crosses the shim and the door, and the Receipts stay ours -- but the
half that catches bytes leaving another way would be comparing a number
agent-browser produced against a number we produced. Their own trust-boundaries
reference is candid about which side of that line it stands on:
`--allowed-domains` is "browser-level containment, not an operating-system
firewall", to be combined "with host, container, or network egress controls when
you require a boundary below the browser process". This harness already is that
control.

Set against that: an npm postinstall that fetches a release binary and a Chrome
download on the path an unattended campaign depends on, a fifty-verb surface
where the registry has ten, an unrestricted `eval` where probes are registered
with declared verdicts, and a process whose default shape is a shared session
that outlives the conversation -- their own core Skill warns that the unnamed
session "is shared with every other agent on the machine and it persists across
conversations, so working in it can hijack another agent's page mid-task". That
is a sound warning about a default this repository does not have and should not
acquire.

The text is a different matter and is the cheaper half the ticket suspected it
would be. Four things in `skill-data/core/SKILL.md` and
`references/trust-boundaries.md` are better written than what
`skills/browser-evidence/SKILL.md` says today, and none of them is about Rust:
that refs go stale the moment the page changes and the instruction is to
re-snapshot, not to be careful; that "agents fail more often from bad waits than
from bad selectors", followed by a short list of which wait to pick after a
page-changing action; a troubleshooting section written as symptom, cause, next
command; and an enumeration -- not a principle -- of every channel whose output
is untrusted, from snapshot text through console messages to network response
bodies and error overlays. `derive-client` adds one sentence worth carrying
whole: "Driving a browser is the right tool for the first visit and the wrong
tool for the hundredth", and a record-twice discipline that is our twin-fixture
reasoning arrived at from the other direction. All of it is Apache-2.0, so a
rewritten Skill may carry it as long as it carries the notice and says what it
changed.

Whether the context saving is real is not settled here and was not measured. The
claim is "~200-400 tokens instead of parsing raw HTML" for an accessibility-tree
snapshot with compact refs. If that survives a measurement against what
`capture_dom` files today, the finding is about an output format and not about a
binary, and the response is a compact snapshot action of our own inside the
closed action set -- not a dependency.

## What each side can do

Ticket 89's second criterion, as a table rather than as a preference. The left
column is what ticket 31 built and this repository runs today.

| Capability | redKraken browser slice (ticket 31) | agent-browser 0.34.0 |
|---|---|---|
| Engine | `/headless-shell/headless-shell` in a container image the repo controls | Chrome for Testing, downloaded by `agent-browser install`; `--engine lightpanda` alternative; `AGENT_BROWSER_EXECUTABLE_PATH` can point elsewhere |
| Protocol | CDP over a websocket framed by hand in `browser_driver.py` | CDP direct from Rust (vendored protocol JSON); WebDriver for Safari/iOS |
| Runtime dependencies | none -- `pyproject.toml` `dependencies = []`, held by a startup assertion | prebuilt Rust binary fetched from GitHub Releases at npm postinstall; Chrome download; `certutil`/`libnss3-tools` for `--ca-cert` |
| Process model | one container, one `run_tool` invocation, one plan, container removed on exit | client + persistent daemon, one per session name; default 1 h idle timeout; `batch` collapses many commands into one invocation |
| Addressing | none -- nothing outside the container can speak to it | Unix domain socket `<socket_dir>/<session>.sock` (TCP 127.0.0.1 on Windows); `--namespace` scopes it |
| Action set | closed: `navigate`, `wait_for`, `fill`, `inject`, `click`, `assert_text`, `assert_absent`, `probe`, `capture_dom`, `screenshot`; arguments validated per action by the registry | open: 50+ commands -- navigation, snapshot, click/fill/type/select/check/upload/drag, find by role/text/label/testid, waits, tabs, frames, dialogs, cookies, storage, files, eval, a11y audit, React introspection, video recording, diffing, dashboard, MCP server |
| Page reading | serialised DOM stored as a content-addressed Artifact | accessibility-tree snapshot with `@eN` refs (`snapshot -i/-u/-c/-d/-s/--json`), `read`, `get text/html/attr/value/title/url/count` |
| Element addressing | CSS selector supplied by the plan | `@eN` refs (fresh per snapshot), `find role/text/label/placeholder/testid/first/nth`, raw CSS |
| Screenshot | viewport PNG to Artifact | viewport, `--full`, `--annotate` (numbered labels keyed to refs), plus video (`record start/stop`) |
| Arbitrary JS | only registered probes with declared verdicts; a probe touching `document.cookie`/`localStorage`/`sessionStorage`/`indexedDB` is refused by `check_browser_runs` | `eval` / `eval --stdin` / `eval -b <base64>`, unrestricted unless `--action-policy` denies it |
| Egress fence | `--internal` network, single peer (the door), DNS blackholed, `--proxy-bypass-list=<-loopback>` so even loopback goes through the shim | `--proxy-server` via `--proxy`; `--allowed-domains` in-browser filter, documented as *not* an OS firewall |
| TLS trust | `--ignore-certificate-errors-spki-list=<leaf SPKI pin>` -- trusts exactly the door's leaf | `--ca-cert` (Linux, NSS import, hostname+validity checks kept) or `--ignore-https-errors` (blanket). SPKI pin only via `--args` passthrough (**SPIKE**) |
| Capability header on the proxy hop | loopback shim adds `Proxy-Authorization: RedKraken <hex>` and `X-RedKraken-Program` to the `CONNECT` and to absolute-form requests, and strips any client-supplied copy | not possible natively: `Fetch.continueWithAuth` + username/password only; `--headers` is origin-scoped end-to-end. Needs the same shim |
| Identity / credentials | injected by the door; nothing in the container holds a cookie, a header or a key | local encrypted auth vault (`~/.agent-browser/auth/`, AES-256-GCM), credential provider plugins, `cookies set --curl`, `state save/load` |
| Request accounting | per-step `network_requests` written by our driver; `check_browser_runs()` holds `sum(network_requests)` against `count(receipts)` per `tool_run_id` and flags a navigate that loaded with no Receipt | session-scoped `network requests` log and HAR export; no per-step attribution; `network requests --clear` would have to be driven between steps to synthesise one |
| Evidence model | plan digest over identity slot + ordered steps; result digest over declared outcome keys only (small integer, boolean, or lowercase word -- so timestamps, nonces, uuids and hashes are structurally unspellable); DOM/screenshot/console/probe output become Artifacts linked to Receipts | stdout text, `--json`, PNG/WebM files, `.har` files. No digest, no attribution to a Receipt, no notion of a run that "did not close" |
| Determinism between two runs of one plan | guaranteed by construction -- same `plan_sha256`, differing `result_digest` is a fact about the target | not a design goal |
| Halt / budget interaction | the run is one bounded `run_tool` with five ceilings; a Halt stops it because there is nothing that outlives the call | the daemon outlives the command by design; stopping it means an explicit `close`, an `--idle-timeout`, or killing the container |
| Skill / instruction corpus | `src/redkraken/skills/browser-evidence/SKILL.md`, one of six, with `bb:` role, tool-group and evidence-profile frontmatter | seven Skills served by the CLI at the installed version; `npx skills add vercel-labs/agent-browser` |
| Offline installability | the image is built once and the driver is copied in as an input at run time | two network fetches at install time (release binary, Chrome for Testing) |
| Licence | this repository's | Apache-2.0, (c) 2025 Vercel, Inc. |

## Consequences

- **The browser slice stands as it is.** Ticket 31's proxied `headless-shell`,
  driven over hand-framed CDP with `dependencies = []`, remains the only browser
  this harness drives. No npm package, no Rust binary and no daemon enters the
  tree.
- **`skills/browser-evidence/SKILL.md` gains what the reading taught, in our
  verbs.** Ref staleness has no analogue in a step list, but the wait
  discipline, the symptom-cause-command troubleshooting shape, and the
  enumerated untrusted-output channels do. Any rewrite names `navigate`,
  `wait_for`, `fill`, `inject`, `click`, `assert_text`, `assert_absent`,
  `probe`, `capture_dom`, `screenshot` and nothing else, tells an Agent to run
  only what the roster grants, and carries the Apache-2.0 attribution and a
  statement of change.
- **The shim finding is confirmed a second time and should stop being
  re-derived.** ADR 0004 said Chromium does not send `Proxy-Authorization` on
  its own, whatever build it is. agent-browser is the second Chromium-derived
  tool for which that is true, and its answer -- `--proxy` at a loopback shim --
  is the same one. A third evaluation should start here.
- **A compact page representation is a real idea and is ours to build if it
  pays.** If a token measurement shows an accessibility-tree snapshot beats a
  serialised DOM for the same facts, that is a new action in the registry with
  its own declared outcome keys, not a reason to adopt a CLI.
- **Nothing was added to the tree, so nothing new can fail.** The one thing that
  changes is a Skill file. This decision is recorded here rather than in code,
  which is the honest form for a result that is "we looked, and the useful part
  was the writing".
