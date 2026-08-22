"""The operator command line.

The CLI is an adapter: it parses arguments, calls one runtime operation and
renders its structured result. It holds no policy of its own, so the local UI
and the CLI can never develop different interpretations of the same state.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from redkraken import (
    __version__,
    artifact,
    backup,
    browser,
    callback,
    decisions,
    doctor,
    door,
    evaluation,
    evidence,
    execution,
    header,
    identity,
    isolation,
    legacy,
    migrate,
    oob,
    operator,
    panels,
    pg,
    program,
    proxy,
    replay,
    reporting,
    scope,
    state,
    tool,
    ui,
    validation,
)
from redkraken.outcome import (
    DATABASE_UNREACHABLE,
    INVALID_CONFIGURATION,
    Ledger,
    Report,
    render as _render,
    report,
)


#: Which environment variable holds the connection string for which command.
#: They are separate variables because they are separate roles: the whole point
#: of the role split is lost if one exported URL can do everything.
SUPERUSER_URL = "RK_SUPERUSER_URL"
MIGRATE_URL = "RK_MIGRATE_URL"
RESTORE_URL = "RK_RESTORE_URL"
DATABASE_URL = "RK_DATABASE_URL"
STATE_URL = "RK_STATE_URL"
#: The operator console's own connection, held as `rk2_human`. It is the only
#: role that may answer a question or lift a Halt, and it is deliberately not
#: reachable from `RK_DATABASE_URL`: a control verb the runtime could execute is
#: a control verb a model's tool call can reach through the runtime.
HUMAN_URL = "RK_HUMAN_URL"
#: The egress door's own connection, held as `rk2_proxy`. Named where the door
#: is, because `door.main` reads it inside a container this command never sees.
PROXY_DATABASE_URL = proxy.DATABASE_VARIABLE

DEFAULT_DATABASE = "rk2"

#: What `rk version` files under. A constant because the test that holds the
#: verb's answer against `--version` names it, and a command whose report is
#: filed under one string in one place and another in the other is two commands.
VERSION = "version"

#: Where the door listens when nobody says otherwise. Loopback because a
#: capability is bearer material and the runtime is on this machine; a fixed port
#: because the operator has to be able to name it in `RK_PROXY_URL` before the
#: process that will use it starts.
DEFAULT_PROXY_HOST = "127.0.0.1"
DEFAULT_PROXY_PORT = 8080


@dataclass(frozen=True)
class _Source:
    """Where one input comes from, in the three names it has.

    The flag, the variable and the name a refusal is filed under always travel
    together, and an operator reading a refusal has to be able to act on it: a
    report that named the wrong variable would send them to edit an environment
    the command never read. Which is also why `fact` is the name the operation
    itself files under and not a spelling invented here -- a path resolved as
    `ca_file` and refused as `trust_root` is one input under two names.
    """

    fact: str
    flag: str
    variable: str


SUPERUSER = _Source("connection_string", "--url", SUPERUSER_URL)
MIGRATION = _Source("connection_string", "--url", MIGRATE_URL)
RESTORATION = _Source("connection_string", "--url", RESTORE_URL)
RUNTIME = _Source("connection_string", "--url", DATABASE_URL)
AGENT = _Source("state_connection_string", "--state-url", STATE_URL)
FENCE = _Source("connection_string", "--url", PROXY_DATABASE_URL)
CONSOLE = _Source("connection_string", "--url", HUMAN_URL)

#: The operator's connection where it is a command's second string rather than
#: its only one. `rk ui serve` reads on the runtime's and acts on this one, so
#: it needs both spellings at once -- and a console that took the operator's
#: role under `--url` would be a console whose reads ran as the operator.
OPERATOR = _Source("console_connection_string", "--console-url", HUMAN_URL)

#: Where the door listens, which is neither a role nor a store. The capability
#: is sent to this address and to nothing else, and `proxy.endpoint` refuses any
#: spelling of it that is not plain HTTP on the loopback interface.
PROXY = _Source("proxy_url", "--proxy", proxy.PROXY_URL)

#: The two halves of the trust that lets the door see inside a tunnel. The
#: directory is the door's and holds a signing key; the file is the certificate
#: out of it, and is the only part anything else is given. Two names because an
#: installation that exported one for both would be exporting the key.
AUTHORITY = _Source("authority", "--authority", proxy.AUTHORITY_VARIABLE)
TRUST = _Source("trust_root", "--ca", proxy.CA_VARIABLE)

#: Where the bytes an exchange produced are written, which is a directory and
#: not a row. It has a variable of its own because an operator who moved the
#: database has not thereby moved the bytes.
ARTIFACTS = _Source("artifact_root", "--artifacts", artifact.ROOT_VARIABLE)

#: And the key those bytes are sealed with. Separate from the store for the
#: reason the store is separate from the connection string --
#: an operator who copied the bytes somewhere has not thereby copied the key,
#: and the sealed artifacts are worth exactly as much as that stays true.
KEYS = _Source("artifact_key", "--key", artifact.KEY_VARIABLE)

#: The image the registered offline tools live in. Its own variable rather than
#: the Agent's because they are its own image: one holds an SDK and resolves a
#: credential, and the other holds executables and must resolve nothing.
TOOLS = _Source("tool_image", "--image", tool.IMAGE_VARIABLE)

#: And the image a headless browser lives in. Its own for the same reason again:
#: a browser image holds a browser and nothing this harness registers as a tool,
#: and one variable for both would start whichever of them answered.
BROWSERS = _Source("browser_image", "--image", browser.IMAGE_VARIABLE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rk",
        description="Operate the RedKraken bug-bounty hunting harness.",
    )
    parser.add_argument("--version", action="version", version=f"rk {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    stated = commands.add_parser(
        "version",
        help="report this installation's version and the corpus revision behind it",
        description=(
            "What is installed here, as a report rather than a line of text. "
            "`--version` answers the same question for a person reading a "
            "terminal; this answers it in the shape every other command answers "
            "in, for the script that has to decide whether two machines are "
            "running the same harness. Reaches no database and no network."
        ),
    )
    stated.set_defaults(run=_version)

    diagnose = commands.add_parser(
        "doctor",
        help=f"report local runtime readiness and validate a configuration (${MIGRATE_URL})",
        description=(
            "Whether this machine can be trusted to run a Program: the "
            "interpreter and its declared requirements, the schema the database "
            "holds, the trust root and authority the door would issue from, the "
            "Agent network and its one peer, and whether the three shipped "
            "corpora still compile. Each subject beyond the interpreter is asked "
            "of what this machine describes -- a connection string, a "
            "certificate, an Agent boundary -- and a subject nothing describes "
            "is reported as undescribed rather than as healthy. Reads only: it "
            "starts no container, mints no certificate and writes no row."
        ),
    )
    _add_url(diagnose, MIGRATION)
    diagnose.add_argument(
        "--config",
        type=Path,
        metavar="path",
        help="a Program configuration file to validate",
    )
    diagnose.set_defaults(run=_doctor)

    runner = commands.add_parser(
        "run",
        help=f"create or resume the Program a configuration names (${DATABASE_URL})",
    )
    _add_url(runner, RUNTIME)
    runner.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the Program configuration to run under",
    )
    runner.add_argument(
        "--accept-change",
        action="store_true",
        help=(
            "record a new configuration revision when the policy has changed; "
            "without it a changed policy is refused rather than adopted"
        ),
    )
    # The second string, added by hand for the reason `rk state` adds its own:
    # `_add_url` also declares which role the command's single URL is, and this
    # command's single URL is the runtime's. Optional, because the string is
    # only needed when the machine is configured to run a Task at all.
    runner.add_argument(
        AGENT.flag,
        metavar="postgresql://...",
        help=(
            "the agent connection string the Mission packet is compiled on "
            f"(default: ${AGENT.variable}); needed only when {execution.IMAGE} "
            "and the rest of the Agent boundary are set"
        ),
    )
    _add_root(
        runner,
        "where the Artifact bytes live, so the Mission packet can carry the "
        f"readable head of each one (default: ${ARTIFACTS.variable})",
    )
    runner.set_defaults(run=_run)

    policy = commands.add_parser(
        "scope",
        help="compile a Program configuration and decide what it authorises",
        description=(
            "Compile the Scope Policy and answer questions about it. Reaches no "
            "database: a verdict is a function of the policy and the request, so "
            "this is the same decision the runtime makes. A denial is an answer "
            "and exits 0; a configuration that will not compile is refused."
        ),
    )
    policy.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the Program configuration to compile",
    )
    policy.add_argument(
        "--url",
        action="append",
        default=[],
        dest="urls",
        metavar="https://...",
        help="decide one request; repeatable",
    )
    policy.add_argument(
        "--host",
        action="append",
        default=[],
        dest="hosts",
        metavar="host[:port][/path]",
        help="decide one host as the projection would; repeatable",
    )
    policy.add_argument(
        "--subtree",
        action="append",
        default=[],
        dest="subtrees",
        metavar="domain",
        help="decide a whole domain as a wildcard seed; repeatable",
    )
    policy.add_argument(
        "--callback",
        action="append",
        default=[],
        dest="callbacks",
        metavar="host",
        help="decide whether an observed interaction arrived on a declared channel",
    )
    policy.add_argument(
        "--action",
        action="append",
        default=[],
        dest="actions",
        metavar="permission",
        help=(
            "ask about one rule of engagement; repeatable, and all five are "
            "reported when none is named"
        ),
    )
    policy.add_argument(
        "--discovery",
        action="append",
        default=[],
        dest="techniques",
        metavar="technique",
        help=(
            "ask about one discovery technique; repeatable, and all five are "
            "reported when none is named"
        ),
    )
    policy.set_defaults(run=_scope)

    inspect = commands.add_parser(
        "state",
        help=(
            "read one Program's records as the agent connection sees them "
            f"(${DATABASE_URL} and ${STATE_URL})"
        ),
    )
    _add_url(inspect, RUNTIME)
    # The second string is added here rather than through `_add_url`: it is the
    # only command with two, and the help has to say which role each one is.
    inspect.add_argument(
        AGENT.flag,
        metavar="postgresql://...",
        help=f"the agent connection string (default: ${AGENT.variable})",
    )
    inspect.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program to read",
    )
    inspect.add_argument(
        "--label",
        metavar="label",
        help="read one full record by its label instead of only the compact index",
    )
    inspect.add_argument(
        "--limit",
        type=int,
        default=state.DEFAULT_RECORDS,
        metavar="n",
        help=f"records per kind in the compact read (default: {state.DEFAULT_RECORDS})",
    )
    inspect.add_argument(
        "--bytes",
        dest="byte_limit",
        type=int,
        default=state.DEFAULT_BYTES,
        metavar="n",
        help=(
            "the size the record index must fit under; a full record asked for "
            f"by --label is returned whole (default: {state.DEFAULT_BYTES})"
        ),
    )
    inspect.set_defaults(run=_state)

    console = commands.add_parser(
        "ui",
        help="the local operator console, and the reads behind it",
    )
    console_operations = console.add_subparsers(
        dest="operation", required=True, metavar="operation"
    )

    serving = console_operations.add_parser(
        "serve",
        help=(
            "serve the local console over the reads and verbs of this surface "
            f"(${DATABASE_URL}, ${STATE_URL} and ${HUMAN_URL})"
        ),
        description=(
            "Open a console on this machine over the same operations `rk` "
            "already exposes. It holds no query of its own: every view is one "
            "of the reads below and every button is one of the operator verbs, "
            "so a page and a command cannot come to mean different things. "
            "Loopback only, and every form on it carries a token this process "
            "alone holds."
        ),
    )
    _add_url(serving, RUNTIME)
    # Two further strings, for the two roles the console is not. The reads run
    # as the runtime, the record index runs as the agent because that is whose
    # isolation it is describing, and the verbs run as the operator.
    serving.add_argument(
        AGENT.flag,
        metavar="postgresql://...",
        help=f"the agent connection string the record index is read on (default: ${STATE_URL})",
    )
    serving.add_argument(
        OPERATOR.flag,
        metavar="postgresql://...",
        help=f"the operator connection string the verbs run on (default: ${HUMAN_URL})",
    )
    serving.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the one Program this console is about",
    )
    serving.add_argument(
        "--host",
        default=ui.DEFAULT_HOST,
        metavar="address",
        help=f"the address to listen on (default: {ui.DEFAULT_HOST})",
    )
    serving.add_argument(
        "--port",
        type=int,
        default=ui.DEFAULT_PORT,
        metavar="port",
        help=f"the port to listen on (default: {ui.DEFAULT_PORT})",
    )
    serving.add_argument(
        "--limit",
        type=int,
        default=panels.DEFAULT_ROWS,
        metavar="n",
        help=f"rows per panel on the overview (default: {panels.DEFAULT_ROWS})",
    )
    serving.set_defaults(run=_ui_serve)

    reading = console_operations.add_parser(
        "read",
        help=f"print the console's panels as a report (${DATABASE_URL})",
        description=(
            "The operational reads the console is built on, in the shape every "
            "other command answers in. `rk state` is the model's read of its "
            "own records; this is the operator's read of everything that is not "
            "a record -- the Program's lifecycle and integrity, the slates, the "
            "runs, the leases, the budgets, the chains and the documents on "
            "file. Each panel is bounded and says how much it did not return."
        ),
    )
    _add_url(reading, RUNTIME)
    reading.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program to read",
    )
    reading.add_argument(
        "--panel",
        action="append",
        default=[],
        dest="panels",
        choices=panels.NAMES,
        metavar="name",
        help=(
            f"read one panel; repeatable, and all of {', '.join(panels.NAMES)} "
            "are read when none is named"
        ),
    )
    reading.add_argument(
        "--limit",
        type=int,
        default=panels.DEFAULT_ROWS,
        metavar="n",
        help=f"rows per panel (default: {panels.DEFAULT_ROWS})",
    )
    reading.set_defaults(run=_ui_read)

    listing = console_operations.add_parser(
        "forms",
        help=f"print the report forms a report may be asked for (${DATABASE_URL})",
        description=(
            "The report forms this installation carries, in the shape every "
            "other command answers in. The console's report page offers these as "
            "a chooser, and it is a read of the CLI's rather than a query of the "
            "page's own: a form belongs to the installation and not to a "
            "Program, so it takes no configuration and names nothing a Program "
            "holds."
        ),
    )
    _add_url(listing, RUNTIME)
    listing.set_defaults(run=_ui_forms)

    identities = commands.add_parser(
        "identity",
        help="seal operator-provided authentication material into a named Identity slot",
    )
    identity_operations = identities.add_subparsers(
        dest="operation", required=True, metavar="operation"
    )
    identity_provision = identity_operations.add_parser(
        "provision",
        help=(
            "replace one configured Identity's encrypted proxy-side session "
            f"(${DATABASE_URL})"
        ),
    )
    _add_url(identity_provision, RUNTIME)
    _add_key(identity_provision)
    identity_provision.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program and Identity label",
    )
    identity_provision.add_argument(
        "--identity",
        required=True,
        metavar="label",
        help="the stable configured Identity label to provision",
    )
    identity_provision.add_argument(
        "--from",
        dest="source",
        type=Path,
        required=True,
        metavar="path",
        help="a control-side JSON credential document; its values are never reported",
    )
    identity_provision.set_defaults(run=_identity_provision)

    headers = commands.add_parser(
        "header",
        help="seal the value behind a Program's required-header declaration",
    )
    header_operations = headers.add_subparsers(
        dest="operation", required=True, metavar="operation"
    )
    header_provision = header_operations.add_parser(
        "provision",
        help=(
            "replace the encrypted value the door injects for one required "
            f"header (${DATABASE_URL})"
        ),
    )
    _add_url(header_provision, RUNTIME)
    _add_key(header_provision)
    header_provision.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration declaring the Program and the required header",
    )
    header_provision.add_argument(
        "--header",
        required=True,
        metavar="name",
        help="the declared header name whose value is being provisioned",
    )
    header_provision.add_argument(
        "--from",
        dest="source",
        type=Path,
        required=True,
        metavar="path",
        help=(
            "a file holding the header value and nothing else; a file rather "
            "than an argument, which every process on this machine can read"
        ),
    )
    header_provision.set_defaults(run=_header_provision)

    callbacks = commands.add_parser(
        "callback",
        help="mint a correlator for a declared out-of-band channel, and admit what arrives",
    )
    callback_operations = callbacks.add_subparsers(
        dest="operation", required=True, metavar="operation"
    )

    callback_provision = callback_operations.add_parser(
        "provision",
        help=(
            "mint one correlator for one subject on one declared callback "
            f"channel (${DATABASE_URL})"
        ),
        description=(
            "Mints a correlator and prints the address to embed. The correlator "
            "is not a credential and holding it authorises nothing; it is what "
            "makes an arrival attributable to this Program and this subject, and "
            "it stops doing that when it expires. Only the digest is stored, so "
            "the address is printed once and cannot be read back."
        ),
    )
    _add_url(callback_provision, RUNTIME)
    callback_provision.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration declaring the Program and the callback channel",
    )
    callback_provision.add_argument(
        "--channel",
        required=True,
        metavar="name",
        help="the declared channel name to mint against",
    )
    callback_provision.add_argument(
        "--subject",
        required=True,
        metavar="label",
        help=(
            "the entity label an arrival would be an Observation about; a "
            "correlator has a subject because the Observation it produces has one"
        ),
    )
    callback_provision.add_argument(
        "--for",
        dest="lifetime",
        type=int,
        default=callback.DEFAULT_LIFETIME,
        metavar="seconds",
        help=(
            "how long the correlator stays live; an expired one confirms nothing "
            f"(default: {callback.DEFAULT_LIFETIME})"
        ),
    )
    callback_provision.add_argument(
        "--tool-run",
        dest="tool_run",
        metavar="uuid",
        help="bind the correlator to the Tool run that will carry it",
    )
    callback_provision.add_argument(
        "--test-run",
        dest="test_run",
        metavar="uuid",
        help="bind the correlator to the Test run that will carry it",
    )
    callback_provision.set_defaults(run=_callback_provision)

    callback_accept = callback_operations.add_parser(
        "accept",
        help=(
            "admit one interaction a listener recorded and promote it into an "
            f"Observation (${DATABASE_URL})"
        ),
        description=(
            "Takes an arrival the operator's own listener recorded. Contacts no "
            "callback provider and opens no socket: the bytes are read from a "
            "file and the admission decision is the database's. An arrival at a "
            "name no declared channel admits, or one carrying a correlator that "
            "is missing, expired, cleared or another Program's, is refused."
        ),
    )
    _add_url(callback_accept, RUNTIME)
    _add_root(callback_accept)
    callback_accept.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration declaring the Program and its callback channels",
    )
    callback_accept.add_argument(
        "--host",
        required=True,
        metavar="name",
        help="the name the interaction arrived at, which is where the correlator is",
    )
    callback_accept.add_argument(
        "--from",
        dest="source",
        type=Path,
        required=True,
        metavar="path",
        help="the exact inbound bytes the listener recorded; stored unmodified",
    )
    callback_accept.add_argument(
        "--peer",
        default="unknown",
        choices=callback.PEERS,
        help=(
            "what the listener could tell about the peer; a DNS query arrives "
            "from a resolver that may be nowhere near the target (default: unknown)"
        ),
    )
    callback_accept.add_argument(
        "--path",
        metavar="target",
        help=(
            "the request target the listener saw, for a channel that carries "
            "its correlator in the path rather than in a label; passed on "
            "exactly as received, and the correlator is its first segment"
        ),
    )
    callback_accept.add_argument(
        "--at",
        metavar="timestamp",
        help=(
            "when the listener recorded the arrival, ISO 8601 with an offset; "
            "the interactsh and tunnel record formats both carry one. Accepting "
            "the same recording again resolves to the arrival it already wrote "
            "rather than claiming the canary fired twice (default: now)"
        ),
    )
    callback_accept.set_defaults(run=_callback_accept)

    callback_clear = callback_operations.add_parser(
        "clear",
        help=f"end one correlator early, by id (${DATABASE_URL})",
        description=(
            "Ends a canary before it expires -- when the test that carried it "
            "is over, or when the payload turns out to have gone somewhere it "
            "should not have. Takes the correlator id `callback provision` "
            "printed, never the address that was embedded, and reports the "
            "channel and how many arrivals it had already admitted. Clearing "
            "one twice changes nothing the second time and says so, and an id "
            "this Program did not mint is answered as unknown rather than "
            "refused."
        ),
    )
    _add_url(callback_clear, RUNTIME)
    callback_clear.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration declaring the Program that minted the correlator",
    )
    callback_clear.add_argument(
        "--correlator",
        required=True,
        metavar="uuid",
        help="the correlator id to end; the address it was embedded in is not stored",
    )
    callback_clear.set_defaults(run=_callback_clear)

    out_of_band = commands.add_parser(
        "oob",
        help="publish engagement files on a bound out-of-band host, and bind its name",
    )
    oob_operations = out_of_band.add_subparsers(
        dest="operation", required=True, metavar="operation"
    )

    oob_serve = oob_operations.add_parser(
        "serve",
        help=(
            "publish one directory of engagement files on loopback, recording "
            f"every request (${DATABASE_URL})"
        ),
        description=(
            "Serves the files in $" + oob.ROOT_VARIABLE + "/<program-slug>/ over "
            "loopback until interrupted. The directory is read and checked "
            "before the socket is bound, so a root that fails any isolation "
            "rule is a refusal to start rather than a file quietly skipped. A "
            "request whose first path segment resolves a live correlator becomes "
            "an Interaction and an Observation; one that resolves nothing is "
            "answered 404 and logged, because there is nothing to attribute it to."
        ),
    )
    _add_url(oob_serve, RUNTIME)
    _add_root(oob_serve)
    oob_serve.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration declaring the Program and its callback channels",
    )
    oob_serve.add_argument(
        "--channel",
        required=True,
        metavar="name",
        help="the declared channel this directory is published for; its placement must be path",
    )
    oob_serve.add_argument(
        "--port",
        type=int,
        default=oob.DEFAULT_PORT,
        metavar="port",
        help=(
            "the loopback port to listen on; the tunnel on this machine is the "
            f"only thing that reaches it (default: {oob.DEFAULT_PORT})"
        ),
    )
    oob_serve.set_defaults(run=_oob_serve)

    oob_up = oob_operations.add_parser(
        "up",
        help=f"start a tunnel and bind the name it is given to a channel (${DATABASE_URL})",
        description=(
            "Runs `" + oob.TUNNEL_BINARY + " tunnel --url http://127.0.0.1:<port>`, "
            "reads the hostname out of its own output, stores that output as the "
            "binding's evidence and writes the binding. A binding whose tunnel "
            "process is gone is released first, because the name it held belongs "
            "to somebody else now. It refuses when the publisher is not running: "
            "a bound name in front of nothing is a name an agent will embed in a "
            "payload."
        ),
    )
    _add_url(oob_up, RUNTIME)
    _add_root(oob_up)
    oob_up.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration declaring the Program and its callback channels",
    )
    oob_up.add_argument(
        "--channel",
        required=True,
        metavar="name",
        help=(
            "the declared channel to bind the name to; its provider must be "
            + oob.QUICK_PROVIDER
        ),
    )
    oob_up.add_argument(
        "--port",
        type=int,
        default=oob.DEFAULT_PORT,
        metavar="port",
        help=f"the loopback port the publisher is on (default: {oob.DEFAULT_PORT})",
    )
    oob_up.add_argument(
        "--tunnel",
        default=oob.TUNNEL_BINARY,
        metavar="binary",
        help=(
            "the tunnel program to run, found the way the operator installed it "
            f"(default: {oob.TUNNEL_BINARY})"
        ),
    )
    oob_up.set_defaults(run=_oob_up)

    oob_status = oob_operations.add_parser(
        "status",
        help=f"print the name a channel is answering at, and what hangs off it (${DATABASE_URL})",
        description=(
            "The only supported way to learn the live name. Nothing in a "
            "configuration file holds it and no agent composes it: this reads "
            "the binding, so a name released this morning is absent here rather "
            "than embedded in a payload this afternoon."
        ),
    )
    _add_url(oob_status, RUNTIME)
    oob_status.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration declaring the Program and its callback channels",
    )
    oob_status.add_argument(
        "--channel",
        required=True,
        metavar="name",
        help="the declared channel to read the binding of",
    )
    oob_status.set_defaults(run=_oob_status)

    oob_down = oob_operations.add_parser(
        "down",
        help=f"release the name a channel is bound to (${DATABASE_URL})",
        description=(
            "Releases the binding. Every correlator minted against it is "
            "unreachable from that moment -- not by a sweep, but because it "
            "names a released binding -- and the verb says how many that was. "
            "The tunnel process is the operator's to stop."
        ),
    )
    _add_url(oob_down, RUNTIME)
    oob_down.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration declaring the Program and its callback channels",
    )
    oob_down.add_argument(
        "--channel",
        required=True,
        metavar="name",
        help="the declared channel to release the binding of",
    )
    oob_down.set_defaults(run=_oob_down)

    artifacts = commands.add_parser(
        "artifact", help="store, read and verify this Program's content-addressed artifacts"
    )
    verbs = artifacts.add_subparsers(dest="operation", required=True, metavar="operation")

    deposit = verbs.add_parser(
        "put",
        help=(
            "store one file by the hash of its bytes and record that this "
            f"Program holds it (${DATABASE_URL})"
        ),
    )
    _add_url(deposit, RUNTIME)
    _add_root(deposit)
    deposit.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program that will hold it",
    )
    deposit.add_argument(
        "--from",
        dest="source",
        type=Path,
        required=True,
        metavar="path",
        help="the file whose bytes are stored",
    )
    deposit.add_argument(
        "--kind",
        default="runtime",
        choices=artifact.KINDS,
        help="why this Program holds these bytes (default: runtime)",
    )
    deposit.add_argument(
        "--content-type",
        dest="content_type",
        metavar="type",
        help="what the bytes are, recorded beside them and never inferred from them",
    )
    deposit.set_defaults(run=_artifact_put)

    fetch = verbs.add_parser(
        "get",
        help=(
            "read one artifact by label, bounded, as the agent connection sees "
            f"it (${DATABASE_URL} and ${STATE_URL})"
        ),
    )
    _add_url(fetch, RUNTIME)
    fetch.add_argument(
        AGENT.flag,
        metavar="postgresql://...",
        help=f"the agent connection string (default: ${AGENT.variable})",
    )
    _add_root(fetch)
    fetch.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program to read as",
    )
    fetch.add_argument(
        "--label",
        required=True,
        metavar="label",
        help="the artifact's label; there is no way to ask for one by hash",
    )
    fetch.add_argument(
        "--offset",
        type=int,
        default=0,
        metavar="n",
        help="where the returned range starts (default: 0)",
    )
    fetch.add_argument(
        "--bytes",
        dest="byte_limit",
        type=int,
        default=artifact.DEFAULT_BYTES,
        metavar="n",
        help=(
            "how many bytes the range carries; what is left out is reported "
            f"rather than dropped (default: {artifact.DEFAULT_BYTES})"
        ),
    )
    fetch.set_defaults(run=_artifact_get)

    check = verbs.add_parser(
        "audit",
        help=(
            "read every artifact this Program holds and hold its hash against "
            f"its bytes (${DATABASE_URL})"
        ),
    )
    _add_url(check, RUNTIME)
    _add_root(check)
    check.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program whose holdings are checked",
    )
    check.set_defaults(run=_artifact_audit)

    close = verbs.add_parser(
        "seal",
        help=(
            "store one exchange as a redacted artifact and an encrypted wire "
            f"artifact (${DATABASE_URL})"
        ),
    )
    _add_url(close, RUNTIME)
    _add_root(close)
    _add_key(close)
    close.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program that will hold both views",
    )
    close.add_argument(
        "--wire",
        type=Path,
        required=True,
        metavar="path",
        help="the file whose bytes went over the wire; stored only encrypted",
    )
    close.add_argument(
        "--redacted",
        type=Path,
        required=True,
        metavar="path",
        help=(
            "the file the agent may see; stored as an ordinary artifact and the "
            "only one of the two that gets a label"
        ),
    )
    close.add_argument(
        "--content-type",
        dest="content_type",
        metavar="type",
        help="what the bytes are, recorded beside them and never inferred from them",
    )
    close.set_defaults(run=_artifact_seal)

    release = verbs.add_parser(
        "open",
        help=(
            "decrypt one wire artifact to a file, deliberately and audited "
            f"(${DATABASE_URL})"
        ),
    )
    _add_url(release, RUNTIME)
    _add_root(release)
    _add_key(release)
    release.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program whose wire artifact is opened",
    )
    release.add_argument(
        "--label",
        required=True,
        metavar="label",
        help=(
            "the agent-visible label of the pair; the wire view has no label of "
            "its own and there is no way to ask for one by hash"
        ),
    )
    release.add_argument(
        "--into",
        type=Path,
        required=True,
        metavar="path",
        help=(
            "where the plaintext is written, created for this user alone; an "
            "existing file is refused rather than overwritten"
        ),
    )
    release.add_argument(
        "--authorize",
        metavar="reason",
        help=(
            "why this is being opened, recorded in the audit log; without it the "
            "command refuses before it reads any key material"
        ),
    )
    release.set_defaults(run=_artifact_open)

    tools = commands.add_parser(
        "tool", help="run one registered offline tool and keep what it printed"
    )
    running = tools.add_subparsers(dest="operation", required=True, metavar="operation")

    invoke = running.add_parser(
        "run",
        help=(
            "run one registered offline tool for one agent run, bounded, and "
            f"file its output as artifacts (${DATABASE_URL})"
        ),
    )
    _add_url(invoke, RUNTIME)
    _add_root(invoke)
    invoke.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program this run belongs to",
    )
    invoke.add_argument(
        TOOLS.flag,
        dest="image",
        metavar="image",
        help=(
            "the image the registered executables live in; never pulled "
            f"implicitly (default: ${TOOLS.variable})"
        ),
    )
    invoke.add_argument(
        "--agent-run",
        dest="agent_run",
        required=True,
        metavar="label",
        help="the agent run this call is made for, by its label",
    )
    invoke.add_argument(
        "--tool",
        required=True,
        metavar="name",
        help="the registered tool to run; an unregistered name is refused by the registry",
    )
    invoke.add_argument(
        "--argument",
        dest="arguments",
        action="append",
        default=[],
        metavar="name=value",
        help=(
            "one argument the tool declares, repeatable; the registry decides "
            "which names exist and what each value may look like"
        ),
    )
    invoke.set_defaults(run=_tool_run)

    browsing = commands.add_parser(
        "browser", help="drive one browser mission through the door and file what it saw"
    )
    missions = browsing.add_subparsers(dest="operation", required=True, metavar="operation")

    mission = missions.add_parser(
        "run",
        help=(
            "walk one plan of browser steps for one agent run, behind the door, "
            f"and file its evidence as artifacts (${DATABASE_URL})"
        ),
    )
    _add_url(mission, RUNTIME)
    _add_root(mission)
    mission.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program this mission belongs to",
    )
    mission.add_argument(
        BROWSERS.flag,
        dest="image",
        metavar="image",
        help=(
            "the image a headless browser lives in; never pulled implicitly "
            f"(default: ${BROWSERS.variable})"
        ),
    )
    mission.add_argument(
        AUTHORITY.flag,
        dest="authority",
        type=Path,
        metavar="directory",
        help=(
            "the door's certificate authority, whose leaf key the browser is "
            "told to pin and to believe nothing else "
            f"(default: ${AUTHORITY.variable})"
        ),
    )
    mission.add_argument(
        "--agent-run",
        dest="agent_run",
        required=True,
        metavar="label",
        help="the agent run this mission is made for, by its label",
    )
    mission.add_argument(
        "--plan",
        type=Path,
        required=True,
        metavar="path",
        help=(
            "a JSON array of steps, each an action and its arguments; the "
            "registry decides which actions exist and what each takes"
        ),
    )
    mission.add_argument(
        "--identity",
        dest="identity",
        metavar="slot",
        help=(
            "the Identity the door is to present, by the slot this Program "
            "holds; the browser is never given its value"
        ),
    )
    mission.set_defaults(run=_browser_run)

    testing = commands.add_parser(
        "test", help="perform one Test through the replay Lane and settle what it claims"
    )
    replays = testing.add_subparsers(dest="operation", required=True, metavar="operation")

    replaying = replays.add_parser(
        "replay",
        help=(
            "run one Test specification -- setup, actions, cleanup -- behind the "
            f"door, and record the outcome its assertions derive (${DATABASE_URL})"
        ),
    )
    _add_url(replaying, RUNTIME)
    replaying.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program whose scope decides this Test",
    )
    replaying.add_argument(
        PROXY.flag,
        dest="proxy_url",
        metavar="http://127.0.0.1:port",
        help=f"where the door is listening (default: ${PROXY.variable})",
    )
    replaying.add_argument(
        TRUST.flag,
        dest="ca_file",
        type=Path,
        metavar="path",
        help=(
            "the door's certificate, which an https target is verified against "
            "and nothing else; the door reports it when it starts "
            f"(default: ${TRUST.variable})"
        ),
    )
    replaying.add_argument(
        "--agent-run",
        dest="agent_run",
        required=True,
        metavar="label",
        help="the agent run this replay is performed under, by its label",
    )
    replaying.add_argument(
        "--test",
        required=True,
        metavar="label",
        help="the Test to perform, by its label; its specification is already fixed",
    )
    replaying.add_argument(
        "--identity",
        dest="identity",
        metavar="slot",
        help=(
            "the Identity the door is to present, by the slot this Program "
            "holds; the value is never given to this process"
        ),
    )
    replaying.add_argument(
        "--impact",
        action="store_true",
        help=(
            "run a Test that states an impact: it needs a live operator grant, "
            "it records a demonstration rather than evidence, and it settles "
            "nothing about the claim the Finding rests on"
        ),
    )
    replaying.set_defaults(run=_test_replay)

    findings = commands.add_parser(
        "finding", help="what a candidate Finding has to survive to become a real one"
    )
    judgements = findings.add_subparsers(dest="operation", required=True, metavar="operation")

    judging = judgements.add_parser(
        "validate",
        help=(
            "reproduce one candidate Finding and have a blind session judge the "
            f"reproduction, which is all it is shown (${DATABASE_URL})"
        ),
        description=(
            "Three steps in one command: the claim is reopened and its Test is "
            "replayed through the door, the reproduction is served to a fresh "
            "top-level session as its whole world, and what that session answers "
            "is filed as input. What the Finding becomes is the database's "
            "decision, not this command's."
        ),
    )
    _add_url(judging, RUNTIME)
    judging.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program this Finding belongs to",
    )
    judging.add_argument(
        "--finding",
        required=True,
        metavar="label",
        help="the candidate Finding to validate, by its label",
    )
    judging.add_argument(
        "--agent-run",
        dest="agent_run",
        required=True,
        metavar="label",
        help=(
            "the agent run the reproducing replay is performed under, by its "
            "label; the validator's own session is opened by the command"
        ),
    )
    judging.add_argument(
        "--identity",
        dest="identity",
        metavar="slot",
        help=(
            "the Identity the door is to present while reproducing, by the slot "
            "this Program holds; the value is never given to this process"
        ),
    )
    judging.set_defaults(run=_finding_validate)

    sending = judgements.add_parser(
        "report",
        help=f"report one validated Finding, naming the rendering read (${HUMAN_URL})",
        description=(
            "The last step, and the only one no part of the runtime may take: "
            "`validated -> reported` is reserved for a human actor. The approval "
            "names the exact rendering the operator read, so what was approved "
            "stays the bytes that were approved even after the Finding is "
            "rendered again. Every emission gate stays where it is -- this lifts "
            "none of them, and a Finding any of them still blocks is refused "
            "with what the blocker said. `rk report finding` renders a document; "
            "this reports the Finding."
        ),
    )
    _add_url(sending, CONSOLE)
    _add_program(sending)
    sending.add_argument(
        "--label",
        required=True,
        metavar="label",
        help="the Finding to report, by its label",
    )
    sending.add_argument(
        "--rendering",
        required=True,
        metavar="uuid",
        help=(
            "the rendering being approved, as `rk report finding --record` "
            "printed it; a rendering of another Finding, or one the Finding has "
            "since moved out from under, is refused"
        ),
    )
    sending.add_argument(
        "--content-sha256",
        required=True,
        metavar="digest",
        help=(
            "the digest of the bytes being approved, as `rk report finding "
            "--record` printed it beside the rendering id. This is the "
            "confirmation: nothing follows a report, so the question is not "
            "whether the operator is sure but which document they read"
        ),
    )
    sending.add_argument(
        "--reason",
        required=True,
        metavar="text",
        help="why this is worth sending, in the operator's own words; recorded on the transition",
    )
    sending.set_defaults(run=_finding_report)

    clearing = judgements.add_parser(
        "clear-gate",
        help=f"lift one review gate on one Finding, and nothing else (${HUMAN_URL})",
        description=(
            "Two of the emission gates are a judgement rather than a fact: "
            "`known_issue`, where the program published a do-not-send list and "
            "whether this instance is what they meant is a reading of their "
            "words, and `duplicate`, where the report signature is coarser than "
            "a dedup key and two real reports can collide on it. An operator may "
            "overrule those two, one Finding at a time, while the gate is "
            "actually raised, and the sentence it was raising goes on the record "
            "beside their reason. The other seven blockers are things the "
            "database computed and are cleared by fixing what they were computed "
            "from. This reports nothing and approves nothing."
        ),
    )
    _add_url(clearing, CONSOLE)
    _add_program(clearing)
    clearing.add_argument(
        "--label",
        required=True,
        metavar="label",
        help="the Finding the gate is raised on, by its label",
    )
    # No `choices`: `review_gates` is the vocabulary, and a copy of it here would
    # be a second spelling of a closed set that a migration could move out from
    # under. A wrong code is refused by the database, which names the whole set
    # it read rather than the one this file was built believing in.
    clearing.add_argument(
        "--gate",
        required=True,
        metavar="code",
        help="the gate to lift, by the code `report_blockers` raises it under",
    )
    clearing.add_argument(
        "--reason",
        required=True,
        metavar="text",
        help="why this Finding is not the thing the gate is about",
    )
    clearing.set_defaults(run=_finding_clear_gate)

    playbooks = commands.add_parser(
        "playbook", help="grade a Playbook against fixtures it did not choose"
    )
    grading = playbooks.add_subparsers(dest="operation", required=True, metavar="operation")

    evaluating = grading.add_parser(
        "evaluate",
        help=(
            "run one Playbook against one synthetic fixture for the configured "
            "repeats and file each one, through the production Program, Agent "
            f"and Test seams (${DATABASE_URL})"
        ),
    )
    _add_url(evaluating, RUNTIME)
    evaluating.add_argument(
        "--playbook",
        required=True,
        metavar="path",
        help="the Playbook to grade, by its corpus path",
    )
    evaluating.add_argument(
        "--fixture",
        required=True,
        metavar="name",
        help=(
            "the fixture to grade it against, by directory name; the fixture's "
            "own ground truth decides which side of the Playbook's test it is on"
        ),
    )
    evaluating.add_argument(
        "--workspace",
        type=Path,
        required=True,
        metavar="path",
        help="an existing directory the per-repeat Program configurations are written into",
    )
    # The same second string `rk run` takes, for the same reason: each repeat is
    # a Program `program.run` opens, and the work inside it is this machine's
    # ordinary execution slice or nothing.
    evaluating.add_argument(
        AGENT.flag,
        metavar="postgresql://...",
        help=(
            "the agent connection string each repeat's Mission packet is "
            f"compiled on (default: ${AGENT.variable}); needed only when "
            f"{execution.IMAGE} and the rest of the Agent boundary are set"
        ),
    )
    # The same store `rk run` takes, and for the same reason it is not optional
    # to declare: each repeat is a Program whose Mission packet quotes the
    # readable head of every Artifact it can reach, and `_slice` below reads
    # this flag off the namespace whatever the command was. A parser that
    # omitted it would not make the store unnecessary; it would make the
    # evaluator raise on the machines that have one.
    _add_root(
        evaluating,
        "where the Artifact bytes live, so each repeat's Mission packet can "
        f"carry the readable head of each one (default: ${ARTIFACTS.variable})",
    )
    evaluating.set_defaults(run=_playbook_evaluate)

    costing = grading.add_parser(
        "cost",
        help=(
            "state what grading the shipped corpus costs before any of it runs: "
            "the Agent runs still owed at the text each Playbook ships, and the "
            f"budget they reserve (${DATABASE_URL})"
        ),
    )
    _add_url(costing, RUNTIME)
    costing.set_defaults(run=_playbook_cost)

    reports = commands.add_parser(
        "report", help="render what holds, for a Finding or for a kill chain"
    )
    forms = reports.add_subparsers(dest="operation", required=True, metavar="subject")

    rendering = _report_form(
        forms,
        "finding",
        "scope, subject, reproduction, baseline, variant and controls, the "
        "effects an observation witnessed and the impact a run demonstrated, "
        "limitations, evidence and remediation",
    )
    # Finding-side only, and absent rather than refused on the other:
    # `report_renderings.finding_id` is not nullable and an approval is a
    # transition of one Finding, so there is no row a chain report could be
    # filed as.
    rendering.add_argument(
        "--record",
        action="store_true",
        help=(
            "file the exact bytes as the rendering an approval may name; the "
            "source digest is computed by the database, not sent from here"
        ),
    )

    _report_form(
        forms,
        "chain",
        "what it starts from, whether it was composed from separate "
        "demonstrations or walked end to end by one run, its transitions "
        "and their evidence",
    ).set_defaults(record=False)

    bundles = commands.add_parser(
        "evidence",
        help="pack what holds into a bundle somebody else can check, and check one",
    )
    packing = bundles.add_subparsers(dest="operation", required=True, metavar="operation")

    packing_export = packing.add_parser(
        "export",
        help=f"write one Finding or chain as a redacted bundle (${DATABASE_URL})",
        description=(
            "Pack one Finding or chain: the rendered document, the projection it "
            "came from, the exchanges behind it and the Agent view of what "
            "crossed the wire, each under the hash of its bytes. Credentials, "
            "capabilities, cookies, secret headers and the sealed wire view are "
            "excluded and the exclusion is stated rather than left to be "
            "inferred; everything packed is redacted against every rule in "
            "`redaction_rules`. The verifier travels inside the bundle and is run "
            "over it before this command reports success."
        ),
    )
    _add_url(packing_export, RUNTIME)
    packing_export.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program this record belongs to",
    )
    packing_export.add_argument(
        "--subject",
        required=True,
        choices=sorted(evidence.GATHER),
        help="whether the label names a Finding or a kill chain",
    )
    packing_export.add_argument(
        "--label", required=True, metavar="label", help="the record to pack, by its label"
    )
    packing_export.add_argument(
        "--template",
        required=True,
        metavar="id",
        help="the form to render the document under, by its `report_templates` identifier",
    )
    packing_export.add_argument(
        "--out",
        type=Path,
        required=True,
        metavar="dir",
        help=(
            "where to write the bundle; it must not exist or must be empty, "
            "because a bundle written over another leaves files its manifest "
            "does not name"
        ),
    )
    _add_root(
        packing_export,
        help=(
            "where the artifact bytes to be redacted and packed live "
            f"(default: ${ARTIFACTS.variable})"
        ),
    )
    packing_export.set_defaults(run=_evidence_export)

    packing_verify = packing.add_parser(
        "verify",
        help="check one unpacked bundle, with no database and no configuration",
        description=(
            "Hold one bundle against its own manifest: every named file present "
            "and hashing to what was recorded, no file present that the manifest "
            "does not name, the manifest still what it says it is, and no "
            "redaction rule matching what survives in any packed file. The same "
            "check the bundle carries as `verify.py`, offered here so that an "
            "operator who has this repository need not go and find that copy."
        ),
    )
    packing_verify.add_argument(
        "bundle", type=Path, metavar="dir", help="the unpacked bundle to check"
    )
    packing_verify.set_defaults(run=_evidence_verify)

    legacy_import = commands.add_parser(
        legacy.COMMAND,
        help=f"read one redacted v1 export into this Program (${DATABASE_URL})",
        description=(
            "Read one v1 export an operator names: its configuration validated "
            "against this Program's scope and applied to nothing, its domains, "
            "hosts and applications converged onto the Surface, its findings "
            "rolled up to one hint per Property class family, and the artifacts "
            "it retained filed under their own hashes. v1 kept no Receipt, Tool "
            "Run or Agent run behind any of it, so no attempt, Hypothesis, "
            "Finding, Test run or pivot stamp is created and a `confirmed` or "
            "`exploited` label buys nothing: a record the export retained bytes "
            "for is accepted, and one without is an unverified proposal. Every "
            "record is reported as accepted, merged, demoted, skipped or "
            "redacted, and importing the same export twice reports the first "
            "import's answer."
        ),
    )
    _add_url(legacy_import, RUNTIME)
    legacy_import.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program the export is being read into",
    )
    # Required, with no default and nothing that derives one. An import that
    # could find its own input is an import that happens without anybody
    # deciding it should, which is what criterion 1 refuses.
    legacy_import.add_argument(
        "--from",
        dest="source",
        type=Path,
        required=True,
        metavar="dir",
        help="the export directory to read; it is never searched for or inferred",
    )
    _add_root(
        legacy_import,
        help=(
            "where the artifacts the export retained are filed "
            f"(default: ${ARTIFACTS.variable})"
        ),
    )
    legacy_import.set_defaults(run=_legacy_import)

    # Not `door`: the module by that name is what the subcommand two blocks down
    # calls, and a local shadowing it here is a parser being asked for a default.
    doors = commands.add_parser(
        "proxy", help="the egress door: run it, and spend one capability through it"
    )
    operations = doors.add_subparsers(dest="operation", required=True, metavar="operation")

    listener = operations.add_parser(
        "serve",
        help=(
            "run the egress fence until it is interrupted, as the proxy role "
            f"(${PROXY_DATABASE_URL})"
        ),
    )
    _add_url(listener, FENCE)
    _add_root(
        listener,
        help=(
            "where the transcripts of each exchange are filed, under the hash of "
            f"their bytes (default: ${ARTIFACTS.variable})"
        ),
    )
    _add_key(listener)
    listener.add_argument(
        "--host",
        default=DEFAULT_PROXY_HOST,
        metavar="address",
        help=(
            "which loopback interface to listen on; a capability is bearer "
            "material, so a routable one is refused rather than bound "
            f"(default: {DEFAULT_PROXY_HOST})"
        ),
    )
    listener.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PROXY_PORT,
        metavar="port",
        help=f"the port to listen on (default: {DEFAULT_PROXY_PORT})",
    )
    listener.add_argument(
        AUTHORITY.flag,
        dest="authority",
        type=Path,
        metavar="directory",
        help=(
            "where this run's certificate authority lives, which is what lets "
            "the door read inside a tunnel; without one a CONNECT is refused "
            f"rather than relayed (default: ${AUTHORITY.variable})"
        ),
    )
    listener.set_defaults(run=_proxy_serve)

    doorway = operations.add_parser(
        "door",
        help=(
            "start the door in a container, as the Agent network's one peer, so "
            "children have something to reach"
        ),
    )
    doorway.add_argument(
        "--egress",
        default=door.EGRESS,
        metavar="network",
        help=(
            "the second attachment, over which the door reaches the database and "
            "the internet; the Agent network carries no route to either "
            f"(default: {door.EGRESS})"
        ),
    )
    doorway.add_argument(
        "--timeout",
        type=float,
        default=door.START_TIMEOUT,
        metavar="seconds",
        help=(
            "how long the door gets to bind and open its fence before it is given "
            f"up on and taken away (default: {door.START_TIMEOUT:g})"
        ),
    )
    doorway.set_defaults(run=_proxy_door)

    spend = operations.add_parser(
        "request",
        help=(
            "open one Tool run, mint its capability and spend it on one request "
            f"through the door (${DATABASE_URL})"
        ),
    )
    _add_url(spend, RUNTIME)
    spend.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help="the configuration naming the Program whose scope decides this request",
    )
    spend.add_argument(
        PROXY.flag,
        dest="proxy_url",
        metavar="http://127.0.0.1:port",
        help=f"where the door is listening (default: ${PROXY.variable})",
    )
    spend.add_argument(
        TRUST.flag,
        dest="ca_file",
        type=Path,
        metavar="path",
        help=(
            "the door's certificate, which an https target is verified against "
            "and nothing else; the door reports it when it starts "
            f"(default: ${TRUST.variable})"
        ),
    )
    spend.add_argument(
        "--method",
        default="GET",
        metavar="verb",
        help="the HTTP method, which the authorized Tool run has to agree with (default: GET)",
    )
    spend.add_argument(
        "target",
        metavar="url",
        help=(
            "the absolute URL to request; decided against the compiled policy "
            "twice, once here and once at the door"
        ),
    )
    spend.set_defaults(run=_proxy_request)

    questions = commands.add_parser(
        "decision",
        help="tend the queue a gate verdict of `ask` leaves behind",
    )
    tending = questions.add_subparsers(dest="operation", required=True, metavar="operation")

    tend = tending.add_parser(
        "sweep",
        help=(
            "retire the questions whose deadline passed and deliver the "
            f"notifications that are due (${DATABASE_URL})"
        ),
    )
    _add_url(tend, RUNTIME)
    tend.add_argument(
        "--every",
        type=float,
        metavar="seconds",
        help=(
            "keep sweeping this often until interrupted; without it one pass is "
            "made and the command exits, which is what a timer wants"
        ),
    )
    tend.set_defaults(run=_decision_sweep)

    listing = tending.add_parser(
        "list",
        help=f"show the questions waiting on an operator (${HUMAN_URL})",
    )
    _add_url(listing, CONSOLE)
    listing.add_argument(
        "--program",
        metavar="slug",
        help="show one Program's questions; without it, every Program's",
    )
    listing.add_argument(
        "--closed",
        action="store_true",
        help="also show the questions somebody has already closed",
    )
    listing.set_defaults(run=_decision_list)

    answering = tending.add_parser(
        "answer",
        help=f"approve or deny one question (${HUMAN_URL})",
    )
    _add_url(answering, CONSOLE)
    _add_program(answering)
    answering.add_argument("label", metavar="label", help="the question, as `rk decision list` cites it")
    verdict = answering.add_mutually_exclusive_group(required=True)
    verdict.add_argument(
        "--approve",
        action="store_true",
        help=(
            "let the call the question was filed about proceed; refused if the "
            "request no longer classifies the way it did when it was asked"
        ),
    )
    verdict.add_argument(
        "--deny", action="store_true", help="refuse it, and abandon the Task behind it"
    )
    answering.add_argument(
        "--reason",
        required=True,
        metavar="text",
        help=(
            "why, in the operator's own words; recorded against the decision and "
            "never handed to a model"
        ),
    )
    answering.add_argument(
        "--grant-hours",
        type=float,
        default=operator.DEFAULT_GRANT_HOURS,
        metavar="hours",
        help=(
            "how long an approval stays good for "
            f"(default: {operator.DEFAULT_GRANT_HOURS:g})"
        ),
    )
    answering.set_defaults(run=_decision_answer)

    withdrawing = tending.add_parser(
        "supersede",
        help=f"withdraw one question instead of answering it (${HUMAN_URL})",
    )
    _add_url(withdrawing, CONSOLE)
    _add_program(withdrawing)
    withdrawing.add_argument("label", metavar="label", help="the question to withdraw")
    withdrawing.add_argument(
        "--reason",
        required=True,
        metavar="text",
        help="why it is being withdrawn rather than answered",
    )
    withdrawing.set_defaults(run=_decision_supersede)

    halting = commands.add_parser(
        "halt",
        help=f"Halt a Program: no egress and no new work until it is lifted (${HUMAN_URL})",
    )
    _add_url(halting, CONSOLE)
    _add_program(halting)
    halting.add_argument(
        "--reason", required=True, metavar="text", help="why the Program is being Halted"
    )
    halting.set_defaults(run=_halt)

    lift = commands.add_parser(
        "resume",
        help=(
            "lift a Halt; the runtime recovers what it has to at the next "
            f"`rk run` (${HUMAN_URL})"
        ),
    )
    _add_url(lift, CONSOLE)
    _add_program(lift)
    lift.add_argument(
        "--reason", required=True, metavar="text", help="why it is safe to start again"
    )
    lift.set_defaults(run=_resume)

    database = commands.add_parser("db", help="create, migrate, verify and move the database")
    operations = database.add_subparsers(dest="operation", required=True, metavar="operation")

    provision = operations.add_parser(
        "provision",
        help=f"create the roles, the database and the extension (superuser; ${SUPERUSER_URL})",
    )
    _add_url(provision, SUPERUSER)
    provision.add_argument(
        "--database",
        default=DEFAULT_DATABASE,
        metavar="name",
        help=f"the database to create (default: {DEFAULT_DATABASE})",
    )
    provision.set_defaults(run=_provision)

    migrate_ = operations.add_parser(
        "migrate", help=f"apply every pending migration, then verify (${MIGRATE_URL})"
    )
    _add_url(migrate_, MIGRATION)
    _add_root(
        migrate_,
        help=(
            "the store the closing gate holds every recorded artifact against "
            f"(default: ${ARTIFACTS.variable})"
        ),
    )
    migrate_.set_defaults(run=_migrate)

    verify = operations.add_parser(
        "verify", help=f"run every registered integrity check (${MIGRATE_URL})"
    )
    _add_url(verify, MIGRATION)
    _add_root(
        verify,
        help=(
            "also hold every recorded artifact against the bytes filed under it; "
            f"no registered check can open a file (default: ${ARTIFACTS.variable})"
        ),
    )
    verify.set_defaults(run=_verify)

    status = operations.add_parser(
        "status", help=f"report what is applied and what is pending (${MIGRATE_URL})"
    )
    _add_url(status, MIGRATION)
    status.set_defaults(run=_status)

    dump = operations.add_parser("dump", help=f"write a full archive (${MIGRATE_URL})")
    _add_url(dump, MIGRATION)
    dump.add_argument("--to", type=Path, required=True, metavar="path", help="where to write it")
    _add_root(
        dump,
        help=(
            f"the artifact bytes to carry beside the archive, as <path>{backup.STORE_SUFFIX}; "
            "a database that references any and no store given is refused "
            f"(default: ${ARTIFACTS.variable})"
        ),
    )
    dump.set_defaults(run=_dump)

    restore = operations.add_parser(
        "restore", help=f"restore an archive into an empty database (${RESTORE_URL})"
    )
    _add_url(restore, RESTORATION)
    restore.add_argument("--from", dest="archive", type=Path, required=True, metavar="path")
    _add_root(
        restore,
        help=(
            f"where to unpack <path>{backup.STORE_SUFFIX} before the gate runs "
            f"(default: ${ARTIFACTS.variable})"
        ),
    )
    restore.set_defaults(run=_restore)

    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    return arguments.run(arguments)


def _add_url(parser: argparse.ArgumentParser, source: _Source) -> None:
    parser.add_argument(
        source.flag,
        metavar="postgresql://...",
        help=f"the connection string (default: ${source.variable})",
    )
    parser.set_defaults(url_source=source)


def _report_form(
    forms: argparse._SubParsersAction, subject: str, about: str
) -> argparse.ArgumentParser:
    """One `rk report` subcommand, up to what only one of the two subjects has.

    A builder rather than two longhand parsers because the difference between
    them is one flag and one sentence: everything else -- the connection, the
    Program, the label, the form, where the bytes go, whether prose is offered
    -- is the same question asked about a different row.
    """
    form = forms.add_parser(
        subject,
        help=f"render one {subject} (${DATABASE_URL})",
        description=(
            f"Render one {subject}: {about}. The document is a projection "
            "of state and nothing else: equal rows in any order render the "
            "same bytes, and a record that has not earned a report is "
            "refused rather than rendered with the missing parts left out."
        ),
    )
    _add_url(form, RUNTIME)
    form.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="path",
        help=f"the configuration naming the Program this {subject} belongs to",
    )
    form.add_argument(
        "--label",
        required=True,
        metavar="label",
        help=f"the {subject} to render, by its label",
    )
    form.add_argument(
        "--template",
        required=True,
        metavar="id",
        help=(
            "the form to render it under, by the `report_templates` identifier "
            "that holds it; a form for the other subject is refused rather "
            "than rendered empty"
        ),
    )
    form.add_argument(
        "--out",
        type=Path,
        metavar="path",
        help=(
            "where to write the document; written over if it exists, because "
            "a rendering is a pure function of the source and the form. "
            "Without one the command still reports the bytes and their hash"
        ),
    )
    form.add_argument(
        "--narrative",
        type=Path,
        metavar="path",
        help=(
            "a JSON object of section identifier to one authored paragraph. "
            "Off unless named, and a paragraph stating anything the "
            "projection does not is refused"
        ),
    )
    form.set_defaults(run=_report, subject=subject)
    return form


def _add_program(parser: argparse.ArgumentParser) -> None:
    """The Program every operator verb names, as the slug an operator typed.

    Required, and never defaulted to "the only one open": a machine running two
    campaigns would then have a Halt whose target depended on which one happened
    to be closed at the time.
    """
    parser.add_argument(
        "--program",
        required=True,
        metavar="slug",
        help="the Program, by the name its configuration gives it",
    )


def _add_root(parser: argparse.ArgumentParser, help: str | None = None) -> None:
    parser.add_argument(
        ARTIFACTS.flag,
        type=Path,
        metavar="dir",
        help=help or f"where the artifact bytes live (default: ${ARTIFACTS.variable})",
    )


def _add_key(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        KEYS.flag,
        dest="key",
        type=Path,
        metavar="path",
        help=(
            "the file holding the root secret, readable by its owner alone and "
            f"kept outside the database (default: ${KEYS.variable})"
        ),
    )


def _doctor(arguments: argparse.Namespace) -> int:
    """Diagnose this machine, on the environment this process was given.

    The connection string is optional here where every other database command
    requires one: a machine with no database configured is a machine `rk doctor`
    still has four other answers for, and refusing the whole command over a
    missing variable would withhold them.
    """
    diagnosis = doctor.diagnose(
        arguments.config,
        environment=os.environ,
        database_url=arguments.url or os.environ.get(MIGRATE_URL),
    )
    print(json.dumps(diagnosis.as_dict(), indent=2))
    return diagnosis.exit_code


def _scope(arguments: argparse.Namespace) -> int:
    return _render(
        scope.diagnose(
            arguments.config,
            urls=tuple(arguments.urls),
            hosts=tuple(arguments.hosts),
            subtrees=tuple(arguments.subtrees),
            callbacks=tuple(arguments.callbacks),
            actions=tuple(arguments.actions),
            techniques=tuple(arguments.techniques),
        )
    )


def _run(arguments: argparse.Namespace) -> int:
    """Open the Program, and work one Task where this machine can run one.

    Three outcomes rather than two. A machine that describes no Agent boundary
    gets the command every earlier ticket had -- open, report, stop -- because
    that is still a correct use of it. A machine that describes half a boundary
    is refused by name: a missing image or proxy container is an operator
    mistake, and defaulting past one would start a child somewhere nobody chose.
    """
    ledger = Ledger()
    slice_ = _slice(ledger, arguments, arguments.config)
    if ledger.violations:
        return _render(report(program.COMMAND, ledger))
    return _with_settings(
        arguments,
        program.COMMAND,
        lambda settings: program.run(
            settings,
            arguments.config,
            accept_change=arguments.accept_change,
            execute=None if slice_ is None else slice_.attempt,
        ),
    )


def _playbook_evaluate(arguments: argparse.Namespace) -> int:
    """Grade one Playbook against one fixture, through the seams `rk run` uses.

    The slice is built by the same helper and refused by the same rule, which is
    criterion 6 in one line: an evaluation on a machine that describes no Agent
    boundary opens its Programs and attempts nothing, exactly as a run against a
    real target would. What it files then is zeroes, and the verdict follows from
    them -- `untested` while a fixture in the binding has no run at this text,
    and `fail` once they all do -- rather than from a result invented to fill the
    repeats with.

    The same boundary goes to the evaluator as well as to the work, because it
    decides where the fixture is served: a child that talks through the door has
    no route to loopback, so a machine that describes a boundary grades over the
    door and one that does not grades over loopback. `evaluation.route` is where
    that reads, and the run says which one it took.
    """
    ledger = Ledger()
    slice_ = _slice(ledger, arguments)
    if ledger.violations:
        return _render(report(evaluation.RUN, ledger))
    return _with_settings(
        arguments,
        evaluation.RUN,
        lambda settings: evaluation.evaluate(
            settings,
            arguments.workspace,
            playbook=arguments.playbook,
            fixture_name=arguments.fixture,
            work=_nothing if slice_ is None else slice_.attempt,
            boundary=None if slice_ is None else slice_.boundary,
        ),
    )


def _playbook_cost(arguments: argparse.Namespace) -> int:
    """State the corpus campaign's cost, and the route it would be run over.

    The boundary is read for the same reason `rk playbook evaluate` reads it and
    the agent connection is not read at all: no Program is opened here, so there
    is nothing for the agent role to hold, but which route the campaign would
    take decides whether the runs it is about to pay for measure anything.
    """
    ledger = Ledger()
    boundary = _boundary(ledger)
    if ledger.violations:
        return _render(report(evaluation.COST, ledger))
    return _with_settings(
        arguments,
        evaluation.COST,
        lambda settings: evaluation.cost(settings, boundary=boundary),
    )


def _nothing(ledger: Ledger, connection: pg.Connection, program_id: str) -> dict:
    """The work a machine with no Agent boundary does inside an open Program.

    `program.run` takes `execute=None` for this, but an evaluation cannot: the
    marker that keeps this Program out of promotion evidence is written by the
    wrapper around `execute`, and a Program opened with no callback at all would
    be an unmarked one. So the callback is always passed and this is its floor --
    the Program is opened and marked, and nothing is attempted in it.
    """
    ledger.hold(
        "task",
        f"nothing was attempted in {program_id}: this machine describes no Agent boundary",
    )
    return {}


def _boundary(ledger: Ledger) -> isolation.AgentContainer | None:
    """The Agent boundary this machine describes, or nothing.

    A boundary described in part is a refusal rather than nothing, and the
    difference matters to every caller: a machine that describes none has asked
    for the path where children are not started, and one that describes half of
    one has asked for children and mis-said how to contain them.
    """
    if not execution.requested(os.environ):
        return None
    boundary, missing = execution.boundary(os.environ)
    if boundary is None:
        ledger.fail(
            "agent_boundary",
            "the Agent boundary is described in part: " + ", ".join(missing) + " "
            + ("is" if len(missing) == 1 else "are")
            + " unset, and no child is started without all of them",
            code=INVALID_CONFIGURATION,
            source=f"environment:{missing[0]}",
        )
    return boundary


def _slice(
    ledger: Ledger,
    arguments: argparse.Namespace,
    configuration: Path | None = None,
) -> execution.Slice | None:
    """The execution slice this machine is configured for, or nothing.

    The configuration is a parameter and not read off `arguments`, because only
    one of the two callers has one: `rk run` names a Program file and
    `rk playbook evaluate` names a workspace and a fixture. A slice built
    without it claims a `perform` Task and refuses it by name, which is the
    honest answer -- the replay resolves the Program from that file.
    """
    boundary = _boundary(ledger)
    if boundary is None:
        return None
    agent = _url(ledger, AGENT, arguments.state_url, program.COMMAND)
    if agent is None:
        return None
    # The store is not required. A machine that names none still offers,
    # claims and runs; its packet says `not_staged` for every Artifact rather
    # than quoting one, which is the same answer it gives for an Artifact whose
    # bytes are elsewhere.
    #
    # Nor is the tool image, and for the reason `rk tool run` offers rather than
    # requires one: a machine that has not described where the registered tools
    # are still runs every child, and the two tool-run tools answer that there
    # is nothing to run one with. The door is this boundary, because a tool that
    # declares the proxy adapter is put on the Agent topology and there is no
    # second one to put it on.
    image = tool.image_from_environment()
    return execution.Slice(
        boundary=boundary,
        state=agent,
        artifacts=artifact.root_from_environment(arguments.artifacts),
        tools=None if image is None else isolation.ToolContainer(image=image, door=boundary),
        configuration=configuration,
        # Read and not refused, for the reason the store and the image are not
        # refused: this is the address one kind needs, and a machine with no
        # `perform` Task to claim is fully configured without it. The refusal
        # belongs where the capability would be spent, and says so there.
        proxy_url=os.environ.get(PROXY.variable),
    )


def _state(arguments: argparse.Namespace) -> int:
    """Two connection strings, because the read is about two roles.

    The Program is resolved on the runtime connection and its records are read
    on the agent's, which cannot resolve one. A single URL doing both would be
    a single role doing both, and the isolation this command reports would be
    a description of an arrangement that was not in force while it read.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, state.COMMAND)
    agent = _url(ledger, AGENT, arguments.state_url, state.COMMAND)
    if runtime is None or agent is None:
        return _render(report(state.COMMAND, ledger))
    return _render(
        _guarded(
            state.COMMAND,
            lambda: state.read(
                runtime,
                agent,
                arguments.config,
                label=arguments.label,
                per_kind=arguments.limit,
                byte_limit=arguments.byte_limit,
            ),
        )
    )


def _ui_read(arguments: argparse.Namespace) -> int:
    """The console's own reads, printed instead of rendered.

    One connection, because these are the runtime's reads. The console adds two
    more to them -- the agent's, to show the record index as a model gets it,
    and the operator's, to run a verb -- and neither is needed to print a panel.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, panels.COMMAND)
    if runtime is None:
        return _render(report(panels.COMMAND, ledger))
    return _render(
        _guarded(
            panels.COMMAND,
            lambda: panels.read(
                runtime,
                arguments.config,
                names=tuple(arguments.panels) or panels.NAMES,
                limit=arguments.limit,
            ),
        )
    )


def _ui_forms(arguments: argparse.Namespace) -> int:
    """The report forms the console's chooser offers, as a read of the CLI's.

    One connection, the runtime's, because the console asks this as the runtime:
    the chooser is a read like the panels and not a verb, so it must have a CLI
    read behind it or it would be the one query the console holds of its own.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, panels.FORMS_COMMAND)
    if runtime is None:
        return _render(report(panels.FORMS_COMMAND, ledger))
    return _render(_guarded(panels.FORMS_COMMAND, lambda: panels.forms(runtime)))


def _ui_serve(arguments: argparse.Namespace) -> int:
    """Three connection strings, because the console is three roles at once.

    Which is the reason they are three arguments and not one. A console given a
    single URL would run its reads as whatever role could also lift a Halt, and
    the isolation every page on it describes would be a description of an
    arrangement that was not in force while it rendered.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, ui.COMMAND)
    agent = _url(ledger, AGENT, arguments.state_url, ui.COMMAND)
    human = _url(ledger, OPERATOR, arguments.console_url, ui.COMMAND)
    if runtime is None or agent is None or human is None:
        return _render(report(ui.COMMAND, ledger))
    return _render(
        _guarded(
            ui.COMMAND,
            lambda: ui.serve(
                runtime,
                agent,
                human,
                arguments.config,
                host=arguments.host,
                port=arguments.port,
                limit=arguments.limit,
            ),
        )
    )


def _identity_provision(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, identity.COMMAND)
    key = _key(ledger, arguments.key)
    if runtime is None or key is None:
        return _render(report(identity.COMMAND, ledger))
    return _render(
        _guarded(
            identity.COMMAND,
            lambda: identity.provision(
                runtime,
                arguments.config,
                arguments.identity,
                arguments.source,
                key_path=key,
            ),
        )
    )


def _header_provision(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, header.COMMAND)
    key = _key(ledger, arguments.key)
    if runtime is None or key is None:
        return _render(report(header.COMMAND, ledger))
    return _render(
        _guarded(
            header.COMMAND,
            lambda: header.provision(
                runtime,
                arguments.config,
                arguments.header,
                arguments.source,
                key_path=key,
            ),
        )
    )


def _callback_provision(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, callback.PROVISION)
    if runtime is None:
        return _render(report(callback.PROVISION, ledger))
    return _render(
        _guarded(
            callback.PROVISION,
            lambda: callback.provision(
                runtime,
                arguments.config,
                arguments.channel,
                arguments.subject,
                lifetime=arguments.lifetime,
                tool_run=arguments.tool_run,
                test_run=arguments.test_run,
            ),
        )
    )


def _callback_accept(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, callback.ACCEPT)
    root = _root(ledger, arguments.artifacts)
    if runtime is None or root is None:
        return _render(report(callback.ACCEPT, ledger))
    return _render(
        _guarded(
            callback.ACCEPT,
            lambda: callback.accept(
                runtime,
                arguments.config,
                arguments.host,
                arguments.source,
                root=root,
                peer=arguments.peer,
                at=arguments.at,
                path=arguments.path,
            ),
        )
    )


def _callback_clear(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, callback.CLEAR)
    if runtime is None:
        return _render(report(callback.CLEAR, ledger))
    return _render(
        _guarded(
            callback.CLEAR,
            lambda: callback.clear(runtime, arguments.config, arguments.correlator),
        )
    )


def _oob_serve(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, oob.SERVE)
    root = _root(ledger, arguments.artifacts)
    if runtime is None or root is None:
        return _render(report(oob.SERVE, ledger))
    return _render(
        _guarded(
            oob.SERVE,
            lambda: oob.serve(
                runtime,
                arguments.config,
                arguments.channel,
                store=root,
                port=arguments.port,
            ),
        )
    )


def _oob_up(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, oob.UP)
    root = _root(ledger, arguments.artifacts)
    if runtime is None or root is None:
        return _render(report(oob.UP, ledger))
    return _render(
        _guarded(
            oob.UP,
            lambda: oob.up(
                runtime,
                arguments.config,
                arguments.channel,
                store=root,
                port=arguments.port,
                binary=arguments.tunnel,
            ),
        )
    )


def _oob_status(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, oob.STATUS)
    if runtime is None:
        return _render(report(oob.STATUS, ledger))
    return _render(
        _guarded(
            oob.STATUS,
            lambda: oob.status(runtime, arguments.config, arguments.channel),
        )
    )


def _oob_down(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, oob.DOWN)
    if runtime is None:
        return _render(report(oob.DOWN, ledger))
    return _render(
        _guarded(
            oob.DOWN,
            lambda: oob.down(runtime, arguments.config, arguments.channel),
        )
    )


def _artifact_put(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, artifact.PUT)
    root = _root(ledger, arguments.artifacts)
    if runtime is None or root is None:
        return _render(report(artifact.PUT, ledger))
    return _render(
        _guarded(
            artifact.PUT,
            lambda: artifact.put(
                runtime,
                arguments.config,
                arguments.source,
                root=root,
                kind=arguments.kind,
                content_type=arguments.content_type,
            ),
        )
    )


def _artifact_get(arguments: argparse.Namespace) -> int:
    """Two connection strings and a directory, because the read is about all three.

    The Program is resolved on the runtime connection and the label on the
    agent's, for the reason `rk state` gives. The bytes are neither connection's:
    the database holds a hash, and whether the hash is still true of what is on
    disk is a question only this process can ask.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, artifact.GET)
    agent = _url(ledger, AGENT, arguments.state_url, artifact.GET)
    root = _root(ledger, arguments.artifacts)
    if runtime is None or agent is None or root is None:
        return _render(report(artifact.GET, ledger))
    return _render(
        _guarded(
            artifact.GET,
            lambda: artifact.get(
                runtime,
                agent,
                arguments.config,
                root=root,
                label=arguments.label,
                offset=arguments.offset,
                limit=arguments.byte_limit,
            ),
        )
    )


def _tool_run(arguments: argparse.Namespace) -> int:
    """A connection, a store, an image and the arguments, and none of them guessed.

    The door is offered rather than required. A tool whose registry row says it
    has no network never looks at it, so a machine that has not described an
    Agent boundary can still run every tool registered today; one that declares
    the proxy adapter and finds nothing there is refused by name inside the
    runtime rather than quietly run with no route.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, tool.RUN)
    root = _root(ledger, arguments.artifacts)
    image = tool.image_from_environment(arguments.image)
    if image is None:
        ledger.fail(
            TOOLS.fact,
            f"no tool image: pass {TOOLS.flag} or set {TOOLS.variable}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{TOOLS.variable}",
        )
    given = _pairs(ledger, arguments.arguments)
    if runtime is None or root is None or image is None or given is None:
        return _render(report(tool.RUN, ledger))
    door, _ = execution.boundary(os.environ)
    return _render(
        _guarded(
            tool.RUN,
            lambda: tool.run(
                runtime,
                arguments.config,
                root=root,
                image=image,
                agent_run=arguments.agent_run,
                offline_tool=arguments.tool,
                arguments=given,
                door=door,
            ),
        )
    )


def _browser_run(arguments: argparse.Namespace) -> int:
    """A connection, a store, an image, an authority, a door and a plan.

    The door is required rather than offered, which is the one place this differs
    from `rk tool run`: a browser that found no boundary described would be a
    browser with a route to the internet, and the whole of this command is that
    it has exactly one route and the door is it.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, browser.RUN)
    root = _root(ledger, arguments.artifacts)
    image = browser.image_from_environment(arguments.image)
    if image is None:
        ledger.fail(
            BROWSERS.fact,
            f"no browser image: pass {BROWSERS.flag} or set {BROWSERS.variable}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{BROWSERS.variable}",
        )
    authority = _path(AUTHORITY, arguments.authority)
    if authority is None:
        ledger.fail(
            AUTHORITY.fact,
            f"no certificate authority: pass {AUTHORITY.flag} or set {AUTHORITY.variable}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{AUTHORITY.variable}",
        )
    steps = _plan(ledger, arguments.plan)
    door, missing = execution.boundary(os.environ)
    if missing:
        ledger.fail(
            "boundary",
            "no Agent boundary is described, and a browser has no other route: "
            + ", ".join(missing),
            code=INVALID_CONFIGURATION,
            source=f"environment:{missing[0]}",
        )
    if (
        runtime is None or root is None or image is None
        or authority is None or steps is None or door is None
    ):
        return _render(report(browser.RUN, ledger))
    return _render(
        _guarded(
            browser.RUN,
            lambda: browser.run(
                runtime,
                arguments.config,
                root=root,
                image=image,
                authority=authority,
                agent_run=arguments.agent_run,
                steps=steps,
                identity_slot=arguments.identity,
                door=door,
            ),
        )
    )


def _test_replay(arguments: argparse.Namespace) -> int:
    """A connection, a door and a Test.

    No image and no boundary, unlike `rk browser run`: a replay is the runtime
    performing a specification rather than an agent being given a machine to
    decide on, so the only thing it needs beside the database is the address the
    capability may be spent at.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, replay.RUN)
    endpoint = _proxy(ledger, arguments.proxy_url)
    if runtime is None or endpoint is None:
        return _render(report(replay.RUN, ledger))
    return _render(
        _guarded(
            replay.RUN,
            lambda: replay.run(
                runtime,
                arguments.config,
                agent_run=arguments.agent_run,
                test=arguments.test,
                identity_slot=arguments.identity,
                proxy_url=endpoint,
                ca_file=_path(TRUST, arguments.ca_file),
                verbs=replay.IMPACT if arguments.impact else replay.DETECTION,
            ),
        )
    )


def _finding_validate(arguments: argparse.Namespace) -> int:
    """A connection and a boundary.

    The door's address and its certificate are not arguments here, unlike
    `rk test replay`: this command starts a session as well as a replay, so it
    already has to be told the whole boundary, and the boundary states both. Two
    ways to say where the door is would be two things to keep in step.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, validation.RUN)
    if runtime is None:
        return _render(report(validation.RUN, ledger))
    return _render(
        _guarded(
            validation.RUN,
            lambda: validation.run(
                runtime,
                arguments.config,
                finding=arguments.finding,
                agent_run=arguments.agent_run,
                environment=os.environ,
                identity_slot=arguments.identity,
            ),
        )
    )


def _report(arguments: argparse.Namespace) -> int:
    """One connection and nothing else.

    No boundary, no door and no artifact store: a report is a projection of what
    the database already holds, so the one thing this command has to be told is
    where that is. `--record` is a flag on the Finding form only; the chain form
    defaults it false, so this reads one namespace and not two shapes.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, reporting.RUN)
    if runtime is None:
        return _render(report(reporting.RUN, ledger))
    return _render(
        _guarded(
            reporting.RUN,
            lambda: reporting.run(
                runtime,
                arguments.config,
                subject=arguments.subject,
                label=arguments.label,
                template=arguments.template,
                narrative_path=arguments.narrative,
                out=arguments.out,
                record=arguments.record,
            ),
        )
    )


def _evidence_export(arguments: argparse.Namespace) -> int:
    """A connection and a store, because a bundle carries bytes as well as rows.

    No door, no key and no image: the packaged artifacts are the Agent view,
    which is filed in the store as itself, and a sealed wire artifact is never
    reached -- so a command able to unseal one would be a capability this
    operation has no use for.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, evidence.EXPORT)
    root = _root(ledger, arguments.artifacts)
    if runtime is None or root is None:
        return _render(report(evidence.EXPORT, ledger))
    return _render(
        _guarded(
            evidence.EXPORT,
            lambda: evidence.export(
                runtime,
                arguments.config,
                subject=arguments.subject,
                label=arguments.label,
                template=arguments.template,
                out=arguments.out,
                root=root,
            ),
        )
    )


def _evidence_verify(arguments: argparse.Namespace) -> int:
    """One directory and nothing else, which is the point of the verifier."""
    return _render(_guarded(evidence.VERIFY, lambda: evidence.verify(arguments.bundle)))


def _legacy_import(arguments: argparse.Namespace) -> int:
    """A connection and a store, because an export carries bytes as well as rows.

    No key: an import files what the export retained as itself, and bytes that
    arrived from another harness are not sealed wire material this one could
    have a key for.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, legacy.COMMAND)
    root = _root(ledger, arguments.artifacts)
    if runtime is None or root is None:
        return _render(report(legacy.COMMAND, ledger))
    return _render(
        _guarded(
            legacy.COMMAND,
            lambda: legacy.run(runtime, arguments.config, arguments.source, root=root),
        )
    )


def _plan(ledger: Ledger, path: Path) -> list | None:
    """The steps an operator wrote, as a document rather than as a shape.

    Nothing here decides whether a step is acceptable -- that is the registry's,
    and a second opinion in the adapter would be a second place to keep in step.
    What is decided here is only that the file is readable and holds a JSON array
    at all, because the alternative is a refusal from the database quoting a type
    error at an operator who mistyped a filename.
    """
    try:
        document = json.loads(Path(path).read_bytes())
    except OSError as error:
        ledger.fail(
            "plan", f"{path} cannot be read: {error}",
            code=INVALID_CONFIGURATION, source="argument:--plan",
        )
        return None
    except ValueError as error:
        ledger.fail(
            "plan", f"{path} is not readable JSON: {error}",
            code=INVALID_CONFIGURATION, source="argument:--plan",
        )
        return None
    if not isinstance(document, list):
        ledger.fail(
            "plan", f"{path} holds {type(document).__name__}, not an array of steps",
            code=INVALID_CONFIGURATION, source="argument:--plan",
        )
        return None
    return document


def _pairs(ledger: Ledger, given: list[str]) -> dict[str, str] | None:
    """`name=value` arguments as a mapping, or a refusal naming the one at fault.

    Nothing here decides whether a name or a value is acceptable -- that is the
    registry's, and a second opinion in the adapter would be a second place to
    keep in step. What is decided here is only that the operator wrote a pair at
    all, and that they did not write the same name twice: a repeated name would
    otherwise silently keep one of the two values.
    """
    pairs: dict[str, str] = {}
    for item in given:
        name, separator, value = item.partition("=")
        if not separator or not name:
            ledger.fail(
                "arguments",
                f"{item} is not a name=value pair",
                code=INVALID_CONFIGURATION,
                source="argument:--argument",
            )
            return None
        if name in pairs:
            ledger.fail(
                "arguments",
                f"the argument {name} is given more than once",
                code=INVALID_CONFIGURATION,
                source="argument:--argument",
            )
            return None
        pairs[name] = value
    return pairs


def _artifact_audit(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, artifact.AUDIT)
    root = _root(ledger, arguments.artifacts)
    if runtime is None or root is None:
        return _render(report(artifact.AUDIT, ledger))
    return _render(
        _guarded(
            artifact.AUDIT,
            lambda: artifact.audit(runtime, arguments.config, root=root),
        )
    )


def _artifact_seal(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, artifact.SEAL)
    root = _root(ledger, arguments.artifacts)
    key = _key(ledger, arguments.key)
    if runtime is None or root is None or key is None:
        return _render(report(artifact.SEAL, ledger))
    return _render(
        _guarded(
            artifact.SEAL,
            lambda: artifact.seal_wire(
                runtime,
                arguments.config,
                arguments.wire,
                arguments.redacted,
                root=root,
                key=key,
                content_type=arguments.content_type,
            ),
        )
    )


def _artifact_open(arguments: argparse.Namespace) -> int:
    """The one adapter that hands a report back without the thing it produced.

    What was decrypted is in the file `--into` names. The report says its path,
    its length and its hash, which is what an operator needs to find it and what
    a log may carry.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, artifact.OPEN)
    root = _root(ledger, arguments.artifacts)
    key = _key(ledger, arguments.key)
    if runtime is None or root is None or key is None:
        return _render(report(artifact.OPEN, ledger))
    return _render(
        _guarded(
            artifact.OPEN,
            lambda: artifact.open_wire(
                runtime,
                arguments.config,
                root=root,
                key=key,
                label=arguments.label,
                into=arguments.into,
                authorize=arguments.authorize,
            ),
        )
    )


def _proxy_serve(arguments: argparse.Namespace) -> int:
    """The one command that does not return until an operator stops it.

    Its report is written when the listener closes, which is the only moment it
    has anything final to say. What an operator needs before then is on the
    socket: the door answers every request, refused or served, with a decision
    header and the name of the record it wrote.
    """
    ledger = Ledger()
    settings = _url(ledger, FENCE, arguments.url, proxy.SERVE)
    root = _root(ledger, arguments.artifacts)
    if settings is None or root is None:
        return _render(report(proxy.SERVE, ledger))
    authority = _path(AUTHORITY, arguments.authority)
    key = artifact.key_from_environment(arguments.key)
    return _render(
        _guarded(
            proxy.SERVE,
            lambda: proxy.serve(
                settings,
                root=root,
                host=arguments.host,
                port=arguments.port,
                authority=authority,
                key=key,
            ),
        )
    )


def _proxy_door(arguments: argparse.Namespace) -> int:
    """The one command that starts something and returns while it is still running.

    Everything it needs is already in the environment, because everything it
    needs is what `rk run` will read there too: a command with flags of its own
    for the image, the network or the proxy URL would be a second place those
    could be said, and the day the two disagreed the boundary would verify
    against a door no child was pointed at.
    """
    return _render(
        _guarded(
            door.COMMAND,
            lambda: door.start(os.environ, egress=arguments.egress, timeout=arguments.timeout),
        )
    )


def _proxy_request(arguments: argparse.Namespace) -> int:
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, proxy.REQUEST)
    endpoint = _proxy(ledger, arguments.proxy_url)
    if runtime is None or endpoint is None:
        return _render(report(proxy.REQUEST, ledger))
    ca_file = _path(TRUST, arguments.ca_file)
    return _render(
        _guarded(
            proxy.REQUEST,
            lambda: proxy.send(
                runtime,
                arguments.config,
                arguments.target,
                proxy_url=endpoint,
                method=arguments.method,
                ca_file=ca_file,
            ),
        )
    )


def _version(arguments: argparse.Namespace) -> int:
    """What is installed, without asking anything else what it thinks.

    A corpus that will not load is a violation rather than a silence: an
    installation whose migrations are unreadable is one an operator has to be
    told about, and `rk version` is the first command they run.
    """
    del arguments
    ledger = Ledger()
    migrations, refusals = migrate.load()
    if refusals:
        ledger.refuse("corpus", f"{len(refusals)} refused migration file(s)", refusals)
        return _render(report(VERSION, ledger, version=__version__))
    ledger.hold("corpus", f"{len(migrations)} migration(s) readable")
    return _render(
        report(
            VERSION,
            ledger,
            version=__version__,
            schema=migrations[-1].identity if migrations else None,
            corpus=len(migrations),
            corpus_sha256=migrate.revision(migrations),
        )
    )


def _decision_sweep(arguments: argparse.Namespace) -> int:
    """The one command whose useful run is usually the one that did nothing.

    A sweep that retires no question and delivers no notification is the queue
    in the state it should be in, so the report says how many passes it made
    rather than only what it changed -- otherwise a sweeper that never ran and a
    sweeper with nothing to do write the same document.
    """
    ledger = Ledger()
    runtime = _url(ledger, RUNTIME, arguments.url, decisions.COMMAND)
    if runtime is None:
        return _render(report(decisions.COMMAND, ledger))
    return _render(
        _guarded(
            decisions.COMMAND,
            lambda: decisions.sweep(runtime, every=arguments.every),
        )
    )


def _decision_list(arguments: argparse.Namespace) -> int:
    return _with_settings(
        arguments,
        operator.LIST,
        lambda console: operator.queue(
            console, slug=arguments.program, closed=arguments.closed
        ),
    )


def _decision_answer(arguments: argparse.Namespace) -> int:
    return _with_settings(
        arguments,
        operator.ANSWER,
        lambda console: operator.answer(
            console,
            arguments.program,
            arguments.label,
            approve=arguments.approve,
            reason=arguments.reason,
            grant_hours=arguments.grant_hours,
        ),
    )


def _decision_supersede(arguments: argparse.Namespace) -> int:
    return _with_settings(
        arguments,
        operator.SUPERSEDE,
        lambda console: operator.supersede(
            console, arguments.program, arguments.label, reason=arguments.reason
        ),
    )


def _finding_report(arguments: argparse.Namespace) -> int:
    return _with_settings(
        arguments,
        operator.REPORT,
        lambda console: operator.report_finding(
            console,
            arguments.program,
            arguments.label,
            arguments.rendering,
            arguments.content_sha256,
            reason=arguments.reason,
        ),
    )


def _finding_clear_gate(arguments: argparse.Namespace) -> int:
    return _with_settings(
        arguments,
        operator.CLEAR,
        lambda console: operator.clear_gate(
            console, arguments.program, arguments.label, arguments.gate, reason=arguments.reason
        ),
    )


def _halt(arguments: argparse.Namespace) -> int:
    return _with_settings(
        arguments,
        operator.HALT,
        lambda console: operator.halt(console, arguments.program, reason=arguments.reason),
    )


def _resume(arguments: argparse.Namespace) -> int:
    return _with_settings(
        arguments,
        operator.RESUME,
        lambda console: operator.resume(console, arguments.program, reason=arguments.reason),
    )


def _provision(arguments: argparse.Namespace) -> int:
    return _with_settings(
        arguments,
        "db provision",
        lambda settings: migrate.provision(
            settings,
            arguments.database,
            passwords=migrate.passwords_from_environment(),
        ),
    )


def _migrate(arguments: argparse.Namespace) -> int:
    # Not refused when absent, for `_verify`'s reason: the gate has an answer
    # either way, and an operator with no store still has a corpus to apply.
    store = artifact.root_from_environment(arguments.artifacts)
    return _with_settings(
        arguments, "db migrate", lambda settings: migrate.migrate(settings, store=store)
    )


def _verify(arguments: argparse.Namespace) -> int:
    # Not refused when absent, unlike `rk artifact`: the gate has an answer
    # either way, and which one it gave is in the report. Refusing here would
    # make an operator who has no store unable to run the gate at all.
    store = artifact.root_from_environment(arguments.artifacts)
    return _with_settings(
        arguments, "db verify", lambda settings: migrate.verify(settings, store=store)
    )


def _status(arguments: argparse.Namespace) -> int:
    return _with_settings(arguments, "db status", migrate.status)


def _dump(arguments: argparse.Namespace) -> int:
    # Absent is a question the operation answers rather than one refused here:
    # a database that references no artifact has a whole backup without a store,
    # and one that references any does not. Only the command can tell which.
    store = artifact.root_from_environment(arguments.artifacts)
    return _with_settings(
        arguments, "db dump", lambda settings: backup.dump(settings, arguments.to, store=store)
    )


def _restore(arguments: argparse.Namespace) -> int:
    store = artifact.root_from_environment(arguments.artifacts)
    return _with_settings(
        arguments,
        "db restore",
        lambda settings: backup.restore(settings, arguments.archive, store=store),
    )


def _with_settings(
    arguments: argparse.Namespace,
    command: str,
    operation: Callable[[pg.Settings], Report],
) -> int:
    """Resolve the connection string, run one operation and render its report.

    A connection string that cannot be read is reported in the same shape as
    everything else rather than as a traceback: an operator scripting these
    commands parses one document whether the run reached the database or not.
    """
    ledger = Ledger()
    settings = _url(ledger, arguments.url_source, arguments.url, command)
    if settings is None:
        return _render(report(command, ledger))
    return _render(_guarded(command, lambda: operation(settings)))


def _guarded(command: str, operation: Callable[[], Report]) -> Report:
    """Run one operation, reporting a database that stops answering part-way.

    Each operation classifies the failures it goes looking for; this is the
    boundary for the ones nobody can enumerate — a backend restart, a pooler
    dropping an idle socket — which arrive at whichever statement happened to be
    next.
    """
    try:
        return operation()
    except pg.ConnectionError_ as error:
        return _refusal(command, "connection", str(error), DATABASE_UNREACHABLE)
    except pg.DatabaseError as error:
        return _refusal(command, "database", str(error), INVALID_CONFIGURATION)


def _refusal(command: str, name: str, detail: str, code: str) -> Report:
    ledger = Ledger()
    ledger.fail(name, f"the command stopped part-way: {detail}", code=code, source="database")
    return report(command, ledger)


def _root(ledger: Ledger, given: Path | None) -> Path | None:
    """The artifact store, from the argument or from the variable behind it.

    Refused rather than defaulted. A default would file bytes somewhere nobody
    chose, and the next run with a different working directory would report a
    store that had lost every artifact in it.
    """
    root = artifact.root_from_environment(given)
    if root is None:
        ledger.fail(
            ARTIFACTS.fact,
            f"no artifact store: pass {ARTIFACTS.flag} or set {ARTIFACTS.variable}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{ARTIFACTS.variable}",
        )
    return root


def _proxy(ledger: Ledger, given: str | None) -> str | None:
    """Where the capability is allowed to go, from the argument or the variable.

    Refused rather than defaulted, for the same reason as the store and a sharper
    one: a default would be an address this installation did not choose, and the
    thing that would be sent to it is bearer material. Whether the address is one
    a capability may travel to at all is `proxy.endpoint`'s question, asked by the
    operation before it opens anything.
    """
    url = given or os.environ.get(PROXY.variable)
    if not url:
        ledger.fail(
            PROXY.fact,
            f"no proxy endpoint: pass {PROXY.flag} or set {PROXY.variable}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{PROXY.variable}",
        )
        return None
    return url


def _path(source: _Source, given: Path | None) -> Path | None:
    """One optional path, from the argument or from the variable behind it.

    No ledger, because absence is not a refusal here: a door with no authority
    refuses tunnels and says so, and a request that needs a trust root and has
    none is refused by the operation that knows it needs one. Failing in this
    function instead would make an operator name a certificate to send one plain
    HTTP request.
    """
    value = given or os.environ.get(source.variable)
    return Path(value) if value else None


def _key(ledger: Ledger, given: Path | None) -> seal.Location | None:
    """The key file, from the argument or from the variable behind it.

    Refused rather than defaulted, and for a sharper version of the store's
    reason: a default would be a key material path this installation did not
    choose, which either does not exist or belongs to something else. Whether the
    file is one this process will use is `seal.load_root`'s question; this only
    establishes that an operator named one.
    """
    key = artifact.key_from_environment(given)
    if key is None:
        ledger.fail(
            KEYS.fact,
            f"no key material: pass {KEYS.flag} or set {KEYS.variable}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{KEYS.variable}",
        )
    return key


def _url(
    ledger: Ledger, source: _Source, given: str | None, command: str
) -> pg.Settings | None:
    """One connection string, from the argument or from the variable behind it."""
    url = given or os.environ.get(source.variable)
    if not url:
        ledger.fail(
            source.fact,
            f"no connection string: pass {source.flag} or set {source.variable}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{source.variable}",
        )
        return None
    try:
        return pg.settings_from_url(url, application_name=f"rk {command}")
    except ValueError as error:
        # The parser's own words, which name the unsupported parameter but never
        # echo the string: a connection string carries a password.
        ledger.fail(
            source.fact,
            f"the connection string cannot be used: {error}",
            code=INVALID_CONFIGURATION,
            source=(
                f"argument:{source.flag}" if given else f"environment:{source.variable}"
            ),
        )
        return None
