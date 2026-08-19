# RedKraken

A local-first bug-bounty hunting harness for web and API targets. The operator
runs it on their own machine, against Programs they are authorised to test, and
keeps every artifact it produces.

This repository is being built one production increment at a time. Today it
installs as one Python application and exposes two stable commands: `rk
--version` and `rk doctor`.

## Requirements

- CPython `>=3.14,<3.15`. `pyproject.toml` and `rk doctor` declare the same
  range, and starting outside it is a refusal rather than a warning.
- No third-party Python production dependencies. The Python runtime is standard
  library only; any package added later is declared as an exact pin and verified
  at startup. Operations that invoke a system executable check it at the point
  of use: TLS interception requires `openssl`, database dump and restore require
  `pg_dump` and `pg_restore`, and Agent network isolation requires Docker.

## Install

From a clean checkout:

```sh
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/rk --version
```

Without network access, build against the interpreter's own setuptools instead
of a downloaded one:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --no-build-isolation --check-build-dependencies .
```

`--check-build-dependencies` keeps the pinned build requirement enforced on
this path too; without it, skipping build isolation also skips the check.

`rk` is then on the virtual environment's `PATH`. `python3 -m redkraken` runs
the identical command line from a source checkout, with `src` on `PYTHONPATH`.

## Check the machine

```sh
rk version
```

`rk version` reports what is installed: the package version, the last migration
in the corpus, how many there are, and a digest over all of them. Two machines
running the same package version can be running different schemas, so the digest
is the number that decides whether they agree. `rk --version` answers the same
question as one line for a person; this answers it in the shape every other
command answers in. It reaches no database and no network.

```sh
rk doctor
```

`rk doctor` reports whether this machine can be trusted to run a Program. It
reads; it creates no state, sends no traffic and starts no run. Its result is
JSON on stdout: the application version, the interpreter version and the
supported range, one entry per readiness assertion, and every violation it
found.

Give it a Program configuration to validate that too:

```sh
rk doctor --config program.toml
```

## The Agent boundary

Every command that starts a container -- `rk run`, `rk tool run`, `rk browser
run` -- reads the same five variables and refuses if any is unset. Nothing is
defaulted: an image name guessed here would start a child in whatever the guess
matched, and a proxy URL guessed here would point a child's only route at
whatever answers on that port.

| Variable | What it names |
| -------- | ------------- |
| `RK_AGENT_IMAGE` | The image children run in. Never pulled implicitly. |
| `RK_AGENT_NETWORK` | A Docker network created `--internal`, whose only peer is the door. |
| `RK_AGENT_PROXY_CONTAINER` | The door's container name on that network. |
| `RK_AGENT_PROXY_URL` | `http://<container>:<port>`, uncredentialed. Children get it as `HTTP_PROXY`, and the door binds the port it names. |
| `RK_PROXY_CA_FILE` | The certificate children verify every target against: `<authority>/ca.pem`. |

Three more are optional and absent by default, because absent is the contained
value: `RK_AGENT_APPLICATION`, `RK_AGENT_SDK` and `RK_AGENT_HOME` name the
application, the SDK and the home mounted inside a child. A container with no
home mounted has no credential at all rather than somebody else's. The home is a
template: each run is handed a copy of it, and the copy is removed when the run
ends, so what one child writes is never what the next child reads. The one
exception is `.claude/.credentials.json`, which is not copied but mounted from
the home itself, because the CLI writes a refreshed token where it read the old
one -- so it has to be a file the contained user can write, and a run that
refreshes is a refresh the next run resolves.

### Satisfying them

`rk proxy door` puts the production fence on the Agent network as its only
peer, and returns while it is still running. It takes no flags for the five
variables above -- a second place to say them is a day the boundary verifies
against a door no child was pointed at -- and reads three more of its own:

| Variable | What it names |
| -------- | ------------- |
| `RK_PROXY_DATABASE_URL` | The door's own connection, held as `rk2_proxy`. Not `RK_DATABASE_URL`: a fence running as the runtime is a fence with the privileges of the thing it fences. |
| `RK_ARTIFACT_ROOT` | Where exchanges are filed. |
| `RK_PROXY_AUTHORITY` | Where the door mints and keeps its signing material. |
| `RK_ARTIFACT_KEY` | Optional. A **file**, not an `op://` reference: resolving one inside the container would mean a service-account token inside the container. Without it, sealed responses are refused. |

The door runs as `65534:65534` with every capability dropped and a read-only
root filesystem, so both directories it writes have to be writable by that
user. It creates neither -- a directory this command made would be owned by the
operator, which is the state it refuses on the next line:

```sh
mkdir -p /var/lib/rk2/artifacts /var/lib/rk2/authority
sudo chown 65534:65534 /var/lib/rk2/artifacts /var/lib/rk2/authority

docker network create --internal rk2-agent
docker network create rk2-egress
export RK_AGENT_IMAGE=rk2-agent:local
export RK_AGENT_NETWORK=rk2-agent
export RK_AGENT_PROXY_CONTAINER=rk2-door
export RK_AGENT_PROXY_URL=http://rk2-door:18080
export RK_PROXY_CA_FILE=/var/lib/rk2/authority/ca.pem
export RK_PROXY_DATABASE_URL="postgres://rk2_proxy:...@host.docker.internal:5432/rk2"
export RK_ARTIFACT_ROOT=/var/lib/rk2/artifacts
export RK_PROXY_AUTHORITY=/var/lib/rk2/authority

rk proxy door
```

The door runs `python3 -m redkraken.door` inside `RK_AGENT_IMAGE`, from this
checkout mounted read-only, so that image needs a Python 3 and an `openssl` on
its `PATH` -- the second is what mints the authority. The connection string is
written from the container's point of view, which is why the example says
`host.docker.internal`: the door is given that name explicitly, because a
Postgres on this machine has no other spelling from inside a container.

Everything decidable without starting anything is decided first: the boundary
is described, both directories are writable by the user the door runs as, the
key is a file and not a reference, `RK_PROXY_CA_FILE` names the authority this
door will sign with, no container already holds the door's name, and both
networks are what they claim -- the Agent's internal and empty, the egress one
routable and empty. Then the door starts on its egress attachment alone -- so
it has a database to reach before it is anywhere a child could see it -- and
joins the Agent network only once it says it is serving.

The door is on two networks and the difference between them is the point. The
Agent network carries no route anywhere: no database, no internet, no host. The
second attachment carries both, and nothing but the door is on it, so a child
reaches the internet only by asking the door to go -- which is the same thing
as saying the fence sees every request. `--egress` names that second network
(`rk2-egress` by default) and `--timeout` how long the door gets to bind and
open its fence before it is given up on and taken away.

That second network is a network of the operator's own rather than the engine's
default `bridge`, and the door refuses to start on one that already has peers.
The door binds every interface it has, so a peer on the way out is a peer that
could reach the fence without a capability ever having been minted for it.

The door outlives the command that started it, and is not removed when it fails:
a door that vanished would take the only account of why with it. So `rk proxy
door` refuses to start where one already exists, and taking it away is the
operator's own `docker rm --force rk2-door`.

The command asserts the topology from out here, where an engine exists. A
process inside a container cannot enumerate the peers of the networks it is on,
and a door holding an engine socket would be a worse hole than the one this
closes -- so `python3 -m redkraken.door` run by hand somewhere else binds wide
on a network nobody vouched for. The door is only the door when `rk proxy door`
is what put it there.

`rk proxy serve` is the other door: the one an operator runs in a terminal, on
loopback. It refuses a routable bind, because what arrives at a listening fence
is bearer material anybody who can reach the port may spend. The contained door
is the one exception, and only because the whole of what can reach its port is
the child the capability was minted for.

## The Program configuration

A configuration is versioned and declarative. The schema is closed: an
unrecognised key is a refusal, not an ignored line. Absent permission is
denial, so a rule of engagement that is not set is off.

```toml
schema_version = 1

[program]
name = "acme-web"
platform = "hackerone"

[rules_of_engagement]
mutation = true

[budgets]
requests = 5000
tokens = 2000000
run_tokens = 40000
run_requests = 50
lane_tokens = 500000
lane_requests = 1000
concurrency = 2
burst = 500
window_seconds = 3600

[[scope.include]]
host = "app.example.com"
ports = [443]
protocols = ["https"]
paths = ["/api/"]

[[scope.exclude]]
host = "admin.example.com"
ports = [443]
protocols = ["https"]
paths = ["/"]

[[identity]]
name = "member"
slot_ref = "slot://identity/member"

[[required_header]]
name = "X-Bounty-Id"
value_ref = "slot://header/bounty-id"

[[callback]]
name = "oob-dns"
kind = "dns"
host = "oob.example.net"
```

The nine budget limits state three nested allowances, and the nesting is
checked: an Agent run is spent inside a Lane and a Lane inside the campaign, so
`run_tokens` above `lane_tokens` or `tokens`, or `run_requests` above
`lane_requests` or `requests`, is refused by name. Only the per-run ceiling is
compared upwards. A Lane allowed more than the campaign holds is slack rather
than a contradiction, because the campaign total binds first and the Lane never
does.

A scope entry names a hostname, an address, or a wildcard such as
`*.example.com`. An inclusion's wildcard must name at least two labels of its
own, so `*.com` is refused. That is a floor, not a public-suffix rule: `*.co.uk`
passes it, and how wide an inclusion may be remains the operator's judgement
against the Program. An exclusion has no floor, because breadth there withdraws
authority rather than claiming it. Hosts are compared in one spelling —
lowercased, without a trailing root dot, addresses in canonical form — so two
ways of writing the same Program produce the same hash, and a repeated rule
counts once.

A path names a prefix on the host that carries it. It begins with a single
forward slash, so the protocol-relative `//elsewhere.example/admin` is refused;
it holds no `..` segment and no unprintable character, so what is printed is
what was matched.

Opening a Program records one Application per inclusion and opens one `recon`
Task against each, so a campaign has something to rank on its first pass. A
protocol, a host, a port and a path prefix are an address, and an address is
what a Task can be sent to — which is why an inclusion naming two protocols is
two Applications, and why an inclusion naming a wildcard records nothing:
`*.example.com` names a set of hosts and no address. Both counts are reported
as `first_tasks`, and rerunning an unchanged configuration records nothing and
opens nothing, because the Task each subject already carries is the one being
resumed.

Secret material is never written into a configuration. An identity carries a
`slot_ref` and a required header carries a `value_ref`. Both name a
runtime-owned slot — the `slot://` scheme and nothing else, so a configuration
cannot smuggle its own credential in a URL — which the runtime resolves and the
proxy injects. A key that would hold a secret inline is refused by name.

Diagnostic output follows the same rule. It reports names, counts, controls,
versions and the two hashes that identify a configuration — `source_sha256`
over the file as written and `canonical_sha256` over its normalised content, so
reformatting does not change the policy's identity — and never a reference or a
header value.

## The operator console

```sh
rk ui serve --config program.toml
```

The console is the same operations this CLI already exposes, rendered as pages.
Every view is one of the reads — `rk ui read` for the Program's lifecycle and
integrity, its slates, runs, leases, budgets, findings, chains and the documents
on file; `rk state` for the model's own records; `rk decision list` for what is
waiting on a person; `rk report` for one rendering by label — and every button
is one of the operator verbs, so a page and a command cannot come to mean
different things. It holds no query of its own.

Three connection strings, because the console is three roles and not one. The
panels read as the runtime, the record index reads as the agent because that is
whose isolation it is describing, and halt, resume, the two queue verbs, the
report and the gate clearance run as the operator. A console given one string in
all three places renders every page and can lift nothing.

It listens on loopback, refuses a `Host` or `Origin` header that is not the
address it was given, and puts a token this process alone holds on every form,
so a page in another tab cannot submit a verb to it. There is no login, because
there is no remote: the authority is the operator connection string, and anyone
who can reach the socket already has the machine.

```sh
rk ui read --config program.toml
```

The same panels without a browser, in the shape every other command answers in.
Each one is bounded and says how many rows it did not return.

## Outcomes

`rk doctor` aggregates: it reports every violation it found, not the first, and
exits on the most fundamental one. A schema version this build cannot read is
the one exception, reported alone because it explains every other refusal such
a document would draw.

| Exit | Meaning |
| ---- | ------- |
| `0` | Ready. |
| `1` | A refusal this build cannot classify. |
| `2` | The command line could not be understood. |
| `3` | `invalid_configuration`: the configuration was refused. |
| `4` | `unsupported_version`: an interpreter or schema version is out of range. |
| `5` | `missing_dependency`: a required module or pinned distribution is absent. |

## Tests

The suite is standard library only and runs offline:

```sh
python3 -m unittest discover -q
python3 tools/check_baseline.py
python3 -m tools.check_dispositions
python3 -m tools.check_coverage
python3 -m tools.check_intake
```

The third is the migration ledger: for each of the 223 artifacts the census
froze, what became of it. A row either names something this checkout has and
cites the file that proves it works, or names the open migration ticket
committed to building it -- and fails the moment that ticket is marked resolved
with the thing still missing.

The fourth runs the third and then measures the shape of the answer, which no
single row can show: the 49 in-scope Playbooks are all present, loadable by one
role and registered in the schema at the exact text this checkout ships; the 73
operator references and 9 sink packs are each attached to one Skill or Playbook
that declares them and nothing sits loose in a `references/` directory; and the
52 retirements split by kind under a scope whose reversal is on record.

The fifth is the technique intake: one row per public source read, carrying its
digest, the Property class it maps to and what it produced. Producing nothing is
an outcome with a reason rather than a gap, a row cannot claim a fixture for a
class the schema records as not agent-makeable, and a fixture whose provenance
cites the intake ticket and which no row produced fails the gate.

The composed suite is the same modules with a server and a container engine
behind them. It needs a PostgreSQL 18 superuser URL and, for the container
cases, the two images:

```sh
RK_TEST_SUPERUSER_URL=postgres://postgres:...@127.0.0.1:5432/postgres \
RK_TEST_CONTAINERS=1 \
python3 -m unittest discover -q
```

Without `RK_TEST_SUPERUSER_URL` the database cases skip; without
`RK_TEST_CONTAINERS=1` the boundary cases skip. `RK_TEST_AGENT_IMAGE` and
`RK_TEST_BROWSER_IMAGE` name the images those cases run in.

## The release gate

The suites measure a checkout. The release gate measures the artifact:

```sh
python3 -m tools.release_gate --superuser-url postgres://postgres:...@127.0.0.1:5432/postgres
```

It exports `HEAD` with `git archive` into a scratch directory, installs it
there through the documented offline path, and then does everything else with
that installation rather than with this checkout. Six stages, in order, each
using what the one before it built:

* `export` — the commit and nothing lying next to it.
* `install` — the offline install, then what it left behind: only `redkraken`
  and `pip` in the environment, a distribution that declares no requirement of
  its own, none of the checkout-only directories inside the installed package or
  beside it (`docs`, `prototype`, `scratch`, `tmp`, `tests`, `tools`, `.git`,
  `.venv`), and `rk --version`, `rk version` and `rk doctor` all answering from
  a build the application recognises as its own.
* `database` — provision, migrate, status, verify, migrate again, run, read,
  dump, restore into a second database, verify that, and open the same Program
  on the restored copy to prove it resumes rather than starts over. The second
  migrate is the upgrade reading and it is judged on what it applied, not on
  whether it succeeded: an installation that reapplied the corpus over a current
  database reports the same `ok`.
* `topology` — the internal Agent network, a routable egress network and the
  door joined to both by `rk proxy door`, with the Agent network holding the
  door and nothing else.
* `privileges` — ticket 66's standing check on both databases, the migrated one
  and the restored one.
* `suites` — the offline suite and the composed suite, each twice, run from the
  export against the installed application. Twice because the second run is what
  proves the first left the server as it found it. A suite exits zero when it
  skips everything, so the counts are read too: both runs of a suite must select
  the same tests, and the composed run must skip fewer of them than the offline
  run did.

`--stage NAME` selects a stage (repeat it for several), `--keep` leaves the
build directory and the databases behind, and the two together are how a single
stage gets iterated on. A selection that names a stage whose input nothing built
is refused at once, naming the stage that builds it: `--root` then has to point
at a directory a kept run already left behind. `--keep` also leaves the
generated role passwords in `roles.json` under that directory, readable only by
the user that ran the gate; a kept root is a credential and should be removed
with the databases it belongs to.

Nothing the gate runs inherits the calling environment; every child gets `PATH`,
`HOME`, `TMPDIR` and `LANG` written from scratch, so neither a provider key nor
a database URL exported in the shell that starts it can reach the installation
being measured. The `topology` stage needs a container engine and the Agent
image, and fails rather than skipping when either is missing.

The superuser URL must point at a server that can be dropped: the gate creates,
drops and recreates `rk2_release_gate`, `rk2_release_gate_restored` and
`rk2_gate_suite`.

## The release audit

The gate measures the artifact. The audit measures the Spec:

```sh
python3 -m tools.check_audit
python3 -m tools.check_audit --run
```

`baseline/spec-verification.tsv` holds one row per requirement -- 230 user stories,
19 Implementation Decisions, 24 Testing Decisions, 9 Out-of-Scope constraints, the
6 release conditions under Further Notes and the 7 registered prototype
regressions -- and each row names the tickets that built it and the tests or gates
that check it. The column is `verification` rather than `evidence`: Evidence is
the role an observation plays for a claim, which `CONTEXT.md` reserves, and the
v1 ledger beside this one already spells the same idea the same way. The audit
reads the Spec, the tracker and that table together and refuses:

* a requirement with no row, a row for a requirement the Spec does not state, or
  a requirement stated twice, since the weaker of two answers is the one nobody
  reads;
* a row whose digest no longer matches the requirement's own text, so a story
  reworded after somebody mapped it stops matching;
* a row naming a ticket that does not exist or is not resolved, or verification
  that is neither a test this checkout can run nor a gate it ships -- a case
  holding no test is not one, because `unittest` loads it to an empty suite -- there is no
  third kind, which is how a citation to a document is refused rather than
  counted, and this gate may not be cited as its own evidence;
* a requirement whose evidence is *owed* -- `owed:64`, the open ticket that will
  produce it -- where that ticket is finished, does not exist, or where the
  release outcome has been resolved with the row still saying it. Two rows say it
  today: the final review and final acceptance are ticket 64's and 65's, and a
  map that cited something else for them would be citing something that does not
  check them;
* a Spec section nobody reads: the seven headings are frozen, so a requirement
  arriving under a new one is release-blocking rather than invisible;
* a ticket in 01 through 63 -- the ticket that wrote this gate included -- that
  is unresolved, blocked by unfinished work, or
  has no revision resolving it -- the commit that wrote its resolved status --
  and any acceptance box it left unticked without naming an open ticket that
  closes it;
* a dependency graph with a cycle, a blocker nobody wrote, or a resolved ticket
  with no path to the release outcome, which is what tickets raised beside the
  plan look like until whichever ticket owns their outcome names them;
* a named area of the release -- the runtime, the agents, the Skills, the 49
  Playbooks, the operator surface, the v1 import, long-session recovery and the
  first hunt -- holding no requirement at all, or holding requirements none of
  which is checked by that area's anchor;
* a registered prototype regression whose map does not name the tickets the
  registry says it requires.

`--run` then executes every cited test and every cited gate. A failure, an error
*and a skip* are all refusals: most of the live arms stand down without a
database or a container, and a citation that stood down proves nothing about the
requirement citing it. So the run mode is a composed-suite command -- it wants
`RK_TEST_SUPERUSER_URL`, `RK_TEST_CONTAINERS=1`, the two images and the Agent SDK
installed in the interpreter, exactly like the composed suite. It wants the SDK
at the one version the runtime is measured against, the pair `KNOWN_RUNTIME`
names; any other version is an unmeasured runtime, which every agent citation
refuses on purpose. The one skip it
accepts is the inverse case, and the suite says so in its own words: a test that
requires the runtime to be *absent* cannot run where this mode requires it to be
present. The one citation it does not run is `gate:tools.release_gate`, which
builds an install and provisions two databases and is reported as deferred.

Run it on an idle machine. The cited set includes the surface benchmarks, and a
benchmark measures wall time in the process the audit is already running
everything else in: on a loaded host a median drifts over its budget and the
audit reports the drift as a failed citation, which is the honest reading of a
measurement taken under load rather than a fault in the requirement.

What it does not measure is whether the cited evidence is any good; a test that
asserts nothing would satisfy it. That is the final code review's job. And it is
not one of the gates the release gate runs inside its export: it reads this
repository's history for the commit that resolved each ticket, and a tarball
committed once as a checkout would answer that with one synthetic revision for
every ticket in the plan.
