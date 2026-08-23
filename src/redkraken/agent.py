"""The one door an Agent run is started through.

`agent_run` is the whole external surface of the Agent runtime. Everything the
child runs with -- the boundary it starts in, the directory it works in, the
settings document that loads, the executable that is spawned -- is decided here
and nowhere else, because the alternative is a caller that validates one
description of a launch and then starts a different one.

The startup assertion is why the split between this module and `_launch` looks
the way it does. `assess` is pure and takes the options value by duck typing,
so the rules can be exercised without an SDK, a credential or a process; the
child then hands the *same* options object it was assessed with to the
transport. Two values would be two configurations, and the second one would be
the one that ran.

There is one launch mechanism, and it is `isolation.run`: the child is a
process in a container attached to one internal network whose only peer is the
runtime's proxy. That is what makes the environment a positive list rather than
a filtered copy -- nothing about the operator's machine is in the child's
filesystem to be inherited in the first place -- and it is what makes "no
direct path to a target" a property of the network rather than a request made
of a cooperative client through proxy variables.

A refusal is durable, and it is final. `agent_run` closes the Agent run,
returns its Task to the queue with its attempt given back, releases what the
run held and emits the one occurrence Event before the refusal reaches the
caller. Then it latches: a process that has refused starts no further Agent
run. The latch is process state on purpose -- what a refusal measured is a fact
about the machine this process is running on, so the thing that clears it is a
restart, which measures the machine again.
"""

from __future__ import annotations

import json
import os
import secrets
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from redkraken import _startup, callback, capsule as capsule_module, isolation
from redkraken import packet as packet_module, pg, roster, skill
from redkraken import state as state_module, store, tool as tool_module
from redkraken.outcome import STARTUP_REFUSED, Ledger, Report, Violation, report


#: The module the child process runs as. Named rather than pathed, so a
#: checkout and an installed wheel start the same code. The interpreter that
#: runs it is `isolation.INTERPRETER`, because which interpreter exists is a
#: fact about the image and not about this module.
CHILD = "redkraken._launch"

#: What the child exits with when the startup assertion refused. `78` is
#: `EX_CONFIG`: the launch was not attempted because its configuration was
#: unusable, which is exactly what a refusal says.
REFUSED = 78

#: Where a refusal can happen, in the order the phases run. `pre_spawn` is
#: everything decidable before the SDK transport exists; `init` is the one
#: question only the running CLI can answer.
PHASES = ("pre_spawn", "init")

#: Settings the CLI loads whatever `setting_sources` says, so they are read
#: whether or not this runtime asked for them. Both platform locations are
#: inspected on every run; a machine that has neither contributes nothing.
MANAGED_SETTINGS = (
    Path("/etc/claude-code/managed-settings.json"),
    Path("/Library/Application Support/ClaudeCode/managed-settings.json"),
)

#: The one settings document a child may load, in the one directory the runtime
#: owns. A settings file anywhere else is refused rather than ignored: ignoring
#: it would mean the assertion had read a document the CLI had not.
SETTINGS = "settings.json"

#: And what the runtime writes in it. Empty on purpose -- the file exists to be
#: the only answer to "which settings loaded", not to configure anything.
SETTINGS_DOCUMENT: dict[str, dict] = {"env": {}}

#: The one settings *location* a launch ever opens, and only for a role that
#: loads a Skill. `project` is the directory the child runs in, which is the
#: launch directory: made by this runtime, written by this runtime, and holding
#: exactly what `stage_skills` put there. `user` is the operator's own home and
#: is never opened by anything here.
PROJECT = "project"

#: The permission bits on everything the runtime creates for one launch.
PRIVATE = 0o700

#: How long a child may run before the supervisor stops waiting.
TIMEOUT = 900.0

#: The hook events a launch must register, and what each one is for. Three of
#: the four exist so the fourth can be trusted: `PreToolUse` is the decision,
#: `SubagentStart` is what turns an agent id into an attribution rather than a
#: claim, and the two completions are what give an admitted delegation back. A
#: launch missing any of them is a launch whose gate counts up and never down.
GATE_EVENTS = ("PreToolUse", "SubagentStart", "PostToolUse", "PostToolUseFailure")

#: How much of a failed child's output is quoted back in the error that reports
#: it. A bound on the diagnostic, not on what the child produced.
DIAGNOSTIC = 1500

#: The name of the runtime's own MCP server, and the one tool it serves. Named
#: here rather than in `_launch` because the assertion checks them: a launch is
#: contained partly by what it may call, so what this server offers is a field
#: `assess` reads and not a detail of the module that builds the server.
SERVER = "rk2"
SERVER_VERSION = "0.1.0"

#: The three groups `_launch` builds handlers for: the bounded state reads, the
#: one outbound proposal and the one request that leaves the boundary. Named as
#: groups rather than as tools so that moving a tool between groups in the
#: roster moves it here too -- a served tool that had quietly changed authority
#: class would otherwise be a hole the compile cannot see.
#:
#: `net.request` is served for every role the roster grants it to, and whether a
#: particular run may spend it is not decided here: the handler answers a
#: refusal when its job carries no capability. Serving it conditionally would
#: make the allowlist a function of the job, and the assertion checks that
#: allowlist against the roster -- so a launch with no capability would refuse
#: to start rather than start with nothing to spend.
#:
#: `validate.judge` joins them with 037 and is the one group served to a role
#: that holds nothing else. Both of its tools answer out of the job document
#: rather than out of a connection, for the reason most served tools do: the
#: container's one network reaches the capability proxy, so a packet the runtime
#: did not send is a packet no handler can fetch.
#:
#: `exec.tool_run` is the exception to that last sentence and 087's whole
#: subject. Its two tools cannot be answered out of the job, because what they
#: do is start a second container and write a row; so they are answered back
#: across the pipe the child already has, by the supervisor, which is the side
#: holding the connection. Served unconditionally for `net.request`'s reason: a
#: supervisor with nothing to serve them with answers a refusal, and an
#: allowlist that varied with the job is an allowlist the assertion cannot check
#: against the roster.
SERVED_GROUPS = (
    "state.read", "state.propose", "net.request", "validate.judge", "exec.tool_run",
)

#: The one group served in part, and exactly which of its members. `sched.pick`
#: is five tools built by four tickets: the two here are the Slate the
#: orchestrator is offered and the choice it makes on it, and the other three --
#: validation, a report and parking for a human -- are requests their own
#: tickets serve. Naming the members is what keeps the difference visible: a
#: group is served whole unless there is a list saying which part, and the list
#: is checked below against the group it claims to be part of, so a tool that
#: later moved to another authority class fails the compile here rather than
#: arriving quietly on the orchestrator's allowlist.
SERVED_MEMBERS = {"sched.pick": ("mcp__rk2__get_slate", "mcp__rk2__pick_task")}

#: Everything this launch actually serves. The roster says what a role may
#: call; this says what exists to be called, and the allowlist a launch carries
#: is the intersection. It is derived rather than written because two hand-kept
#: lists is how a tool comes to be granted and not served.
SERVED = tuple(
    sorted(
        {name for group in SERVED_GROUPS for name in roster.TOOL_GROUPS[group]}
        | {name for group, part in SERVED_MEMBERS.items() for name in part}
    )
)

def _check_served_members() -> None:
    """A group served in part is served out of a group that has those tools.

    A function rather than a loop at module scope, which is `roster`'s own
    convention for the same kind of statement: the loop's variables would
    outlive it as module attributes, and a name this module exports by accident
    is one another module can come to read.
    """
    for group, members in SERVED_MEMBERS.items():
        if group in SERVED_GROUPS:
            raise roster.RosterError(f"{group} is served whole and in part")
        if not set(members) <= set(roster.TOOL_GROUPS.get(group, ())):
            raise roster.RosterError(
                f"{group} does not contain every tool this launch serves out of it"
            )


_check_served_members()

#: The bare tool names, which is what the MCP server registers. The SDK
#: prefixes `mcp__<server>__` on the way out, so these two lists are the same
#: list seen from either side of that prefix.
BARE = {name: name.removeprefix(f"mcp__{SERVER}__") for name in SERVED}

#: How the child answers permission questions. `bypassPermissions` is the
#: contained value here rather than the wide one: there is no human attached to
#: an Agent run, so a prompt is a hang. It is safe because it is not what
#: decides anything: the permission mode says whether a call is questioned, and
#: `roster.Gate` says whether it happens. The gate's denial is the one decision
#: this mode cannot overrule, which is why the allowlist lives in the roster.
PERMISSION_MODE = "bypassPermissions"

#: What the init message must report. `none` is the CLI's own word for "no key
#: was resolved", which on a subscription-authenticated run is the only answer
#: that corroborates the pre-spawn assertion.
EXPECTED_KEY_SOURCE = "none"

#: The vocabulary of a refusal that is not a credential vector. Each one names
#: something the runtime could not verify rather than something it measured, so
#: they carry no vector and the effect `unverifiable`.
UNMEASURED_RUNTIME = "unmeasured_runtime"
INVALID_LAUNCH = "invalid_launch"
SETTINGS_UNREADABLE = "settings_unreadable"
AUTH_SOURCE_UNEXPECTED = "auth_source_unexpected"
INIT_UNCORROBORATED = "init_uncorroborated"
UNVERIFIABLE = "unverifiable"

#: Why a call a child made across the tool channel was answered rather than
#: acted on. `unknown_call` is a verb this supervisor does not serve, which the
#: roster refuses before the call is ever made and which is stated here anyway
#: because the channel is a pipe and a pipe carries whatever is written to it.
#: `unreachable_state` is a database the supervisor could not reach. Both are
#: refusals rather than raises, for the channel's whole reason: a child left
#: waiting on a line that never comes ends at its deadline rather than with an
#: answer it could act on.
UNKNOWN_CALL = "unknown_call"
UNREACHABLE_STATE = "unreachable_state"
#: A supervisor that can write a row and cannot start a container. Its own
#: word rather than `_launch.NO_TOOLING`, because they are different states:
#: that one is a run with no supervisor at all, this one is a supervisor an
#: installation gave no tool image.
NO_TOOL_IMAGE = "no_tool_image"

#: The one thing crossing this channel that is not a tool a model can call. Every
#: other verb here is a `roster.CONTRACTS` name because a child asked for it by
#: name; this one completes the answer to a call the child already made, and no
#: model chooses to make it -- so it is spelled here, beside the dispatch that
#: reads it, rather than in the roster, which is the list of what a model may
#: say. The `mcp__rk2__` prefix is deliberately absent for the same reason: a
#: name in that shape is a tool, and the startup assertion compares that list to
#: the roster's.
NAME_TRANSCRIPTS = "rk2__name_transcripts"

#: How one refusal is made durable: the Program this session speaks for, and the
#: one call that closes the run. Everything the cleanup does -- the run, its
#: Task, the session binding, the Identity Leases and the Event -- happens
#: inside that call, so the cleanup is one statement and therefore one
#: transaction, and a repeat of it is one statement that finds nothing open.
BIND = "SELECT set_config('rk2.program_id', $1, false)"
CLOSE = "SELECT close_startup_refusal($1::uuid, $2, $3, $4, $5::jsonb)"

#: The proposal a child makes and this supervisor carries. `propose_finding`
#: resolves the Hypothesis label to the claim and to the run whose Receipt the
#: runtime cited when it settled that claim, then calls `open_finding` -- which
#: until ticket 102 held the only `INSERT INTO findings` in the corpus and had
#: no caller anywhere. The Agent run is this side's to fill in, because a child
#: naming its own provenance is a child naming which run it would like to be.
PROPOSE = "SELECT propose_finding($1, $2, $3, $4::uuid)"

#: The specification a child authors and this supervisor carries. `propose_test`
#: resolves the Hypothesis label to the claim, puts the document through
#: `rk2_test_spec_problem` and writes the `tests` row a replay runs -- the first
#: writer of that table any Agent run can reach. The Agent run is this side's to
#: fill in, for the reason it is on `PROPOSE` above.
PROPOSE_TEST = "SELECT propose_test($1, $2::jsonb, $3::uuid)"

#: The correlator a child asks for and this supervisor mints. The plaintext is
#: generated here and digested there -- `mint_callback_correlator` stores the
#: SHA-256 and keeps the name nowhere -- so this process and whatever payload
#: the child embeds it in are the only two places it exists. `secrets` rather
#: than anything the child can influence, and `callback.CORRELATOR_BYTES` rather
#: than a second number, because a correlator that is one DNS label is a rule
#: the callback module already states.
MINT_CALLBACK = "SELECT request_callback_correlator($1, $2, $3, $4::uuid)"

#: The two Artifact labels for one exchange, asked for by the Receipt label the
#: door already handed the child. `hold_receipt_transcripts()` wrote them in the
#: same transaction as the Receipt, so nothing is minted here and nothing waits:
#: what this asks is which labels those rows got. It is scoped inside the verb
#: rather than here, because `rk2_runtime`'s row level security is `USING (true)`
#: and a Receipt label is a small integer that exists under most Programs.
TRANSCRIPTS = "SELECT receipt_transcript_labels($1)"

#: The second thing crossing this channel that is not a `roster.CONTRACTS` call
#: made by a model -- except that this one is, and the difference is worth the
#: sentence. `refresh_packet` is a tool a child asks for by name, so it is
#: spelled in the roster like the other four; what is unusual is that it is a
#: read, and every other read is answered inside the container out of the
#: document the child was launched with. This one crosses because the rows it is
#: about were written after that document was compiled.
#:
#: Read as `rk2_state` rather than as `rk2_runtime`, on a connection of its own.
#: `v_records` is granted to `rk2_state` alone, and that is not an accident to
#: work around: `rk2_state`'s policies are `USING (program_id = rk2_program())`,
#: so which Program's rows a refresh can see is decided by row level security
#: rather than by a predicate this module remembers to write. The runtime
#: connection the other four arms hold sees every Program and scopes inside each
#: verb; a refresh answering whole rows is not a place to rely on remembering.
REFRESH_READ_ONLY = "SET TRANSACTION READ ONLY"


class StartupRefusal(RuntimeError):
    """The runtime would not start, or would not keep, this Agent run.

    Carries records rather than prose because the diagnostics an operator sees
    must name the variable, the file and the measured effect without ever
    carrying the value: a refusal that printed what it found would be a refusal
    that leaked the credential it refused.
    """

    def __init__(
        self,
        violations: Sequence[Mapping[str, object]],
        phase: str = "pre_spawn",
        sdk_version: str | None = None,
        cli_version: str | None = None,
    ) -> None:
        self.violations = tuple(dict(violation) for violation in violations)
        self.phase = phase
        self.sdk_version = sdk_version
        self.cli_version = cli_version
        if phase not in PHASES or not self.violations:
            raise ValueError("a startup refusal needs a known phase and at least one violation")
        if any(set(violation) != _startup.VIOLATION_KEYS for violation in self.violations):
            raise ValueError("a startup refusal violation is a code, vector, source and effect")
        super().__init__(
            f"startup refused in {phase}: "
            + json.dumps(self.violations, sort_keys=True, separators=(",", ":"))
        )

    def as_dict(self) -> dict:
        return {
            "phase": self.phase,
            "sdk_version": self.sdk_version,
            "cli_version": self.cli_version,
            "violations": [dict(violation) for violation in self.violations],
        }


class Latched(StartupRefusal):
    """The refusal this process already made, raised at a run it will not start.

    A subclass rather than an error of its own because it is not another
    finding: the violations are the ones that were measured, and a caller that
    knows what to do with a refusal knows what to do with this one. What it adds
    is which attempt it refused -- this one was never spawned, because the
    process that would have spawned it has already been told what it would find.
    """

    @classmethod
    def of(cls, refusal: StartupRefusal) -> "Latched":
        """The same measurement, raised again at the run it now refuses."""
        return cls(refusal.violations, refusal.phase, refusal.sdk_version, refusal.cli_version)


#: The refusal this process made, and the reason it will attempt no other run.
#: Module state, because what it remembers belongs to the process rather than to
#: any one request: a second run started from a process that has already
#: measured an exported key would be measured against the same key.
_LATCH: StartupRefusal | None = None


@dataclass(frozen=True, slots=True)
class Egress:
    """The one live capability a child may spend, and where to spend it.

    Everything a request through the door needs and nothing a request could be
    decided from. The capability is bearer material with about five minutes to
    live; the Program is what the door's control header claims; the address is
    the door as the *container* sees it, which is a name on an internal network
    rather than the loopback address the supervisor used.

    What is deliberately absent is the target. The capability was minted against
    one Tool run naming one URL, and the door re-decides every request that
    arrives under it against live policy -- subresources and redirects share one
    capability by design, and each still earns its own verdict. Putting the
    target here as well would read like a second gate, and it would be one this
    process could not enforce.
    """

    capability: str
    program_id: str
    proxy_url: str
    certificate: str = isolation.CA_FILE

    def as_dict(self) -> dict:
        return {
            "capability": self.capability,
            "program_id": self.program_id,
            "proxy_url": self.proxy_url,
            "certificate": self.certificate,
        }

    @classmethod
    def from_dict(cls, document: Mapping[str, object] | None) -> "Egress | None":
        """The block a job carried, or nothing when it carried no usable one.

        Nothing rather than a partial value, and nothing rather than an
        exception. A child cannot check a capability against anything -- it has
        no database and no second copy -- so the one thing it decides is whether
        it was given all three parts, and a job missing any of them is a run
        that may not reach a target. The handler says so when it is called,
        which is a refusal the model can read, rather than a crash mid-turn.
        """
        if not isinstance(document, Mapping):
            return None
        values = {
            name: str(document.get(name) or "")
            for name in ("capability", "program_id", "proxy_url")
        }
        if not all(values.values()):
            return None
        return cls(**values, certificate=str(document.get("certificate") or isolation.CA_FILE))


@dataclass(frozen=True, slots=True)
class Tooling:
    """What the supervisor needs to run a registered tool for a child.

    The other half of `Egress`, and the same argument.  A child cannot start a
    container and cannot write a row, so a tool call it makes is a thing the
    supervisor does on its behalf -- and these are the values the supervisor
    needs to do it that no other field of the request carries: which image holds
    the registered executables, where the Artifact store is, and how to reach
    the database.

    A door is not here.  A tool that declares the proxy adapter is put on the
    Agent topology by `isolation.ToolContainer`, and which of them may is the
    registry's `network` column rather than a caller's argument, so the value
    travels inside the container description where the registry's decision is
    already read.

    The connection settings rather than a connection, and that is the third
    part. The caller's own connection is being beaten on by a heartbeat thread
    for as long as the child runs, and two writers interleaved on one connection
    is two half-statements; so what travels is how to open a second one, and the
    answer opens it the first time a child actually asks for something.

    The image and the store are both or neither: an image with nowhere to file
    what a run produced is a run that could start and could not be kept. What
    they are no longer is required. When this record carried only the two
    tool-run verbs that was the same statement as "or none"; it now carries
    `propose_test`, `propose_finding` and `mint_callback`, which need a database
    and nothing else, and coupling them to a tool image meant an installation
    that named none could file neither a Test nor a Finding -- silently, since
    the child is answered `no_tooling` and the runtime records nothing. Measured
    across `rk2hunt7` through `rk2hunt10`: every hunt that called `propose_test`
    was answered by a channel that was never built.

    `state` is the fourth and it is optional, which is the one asymmetry here.
    It is how the agent-scoped role is reached, and it exists because ticket
    107's refresh reads `v_records`, which is granted to `rk2_state` alone and
    is scoped by row level security rather than by a predicate. Optional because
    a caller that does not pass it still gets every other tool: a run with no
    state settings can act, and what it cannot do is read back a row it wrote
    after it started. Making it required would have turned a missing setting
    into a run that could not start at all.
    """

    runtime: pg.Settings
    container: isolation.ToolContainer | None = None
    root: Path | None = None
    state: pg.Settings | None = None


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    """One Agent run, described completely enough to be started.

    `objective` is the whole of what the child is told to do, and that is all
    ticket 16 needs it to be: the compiled mission packet -- scope, budget,
    identity leases, allowed skills, stop conditions -- is ticket 18's, and it
    arrives here as more fields rather than a different door.

    `container` is required rather than optional, and it is the whole of what
    the child can reach: the network it is attached to, the proxy that is the
    only peer on it, the root it is told to trust, and the three directories
    that are mounted into it. A request that could omit it would be a request
    that could start a child on the supervisor's own machine, with the
    supervisor's own home and a direct route to any target it can name.

    `role` is required and is not a hint. It selects one row of `roster.ROLES`,
    and that row is the whole of what the child is: its model, its effort, its
    turn ceiling, the built-in tools it is offered, the served tools it may
    call, the Skills it may execute and how many of it may run at once. There
    is deliberately no way for a caller to set any of those individually --
    a request that could raise a worker's turn ceiling or hand it one more tool
    would be a second roster, and the one thing a roster cannot survive is a
    second one.

    `program_id` is what makes a refusal recordable, and it is optional for the
    one case where it cannot be given: every Event belongs to a Program, so a
    run started before any Program exists is a run whose refusal can only be
    raised and rendered.

    `packet` is everything the child may read, compiled before it starts. It is
    a field on the request rather than something the child fetches because the
    child cannot fetch: the container's one network reaches the capability
    proxy and nothing else, so a bounded read served inside it can only be
    served from what came in with the job. A request with no packet starts a
    child whose state reads all answer "nothing", which is the honest answer
    for a run the runtime compiled no state for.

    `egress` is the same argument about reaching outwards. The capability is
    minted by the database against a Tool run the runtime opened, so a child
    that could mint its own would be a child deciding what it may call. With
    none, the request tool is still served -- the roster decides that, not the
    job -- and it answers a refusal, which is the honest answer for a run
    nothing authorised a request for.

    `subagent_cap` is the one number this request does carry that the roster
    does not state, and for the reason the rest of them are not carried: it is
    not a roster value at all. `scheduler_weights.max_concurrent_subagents` is
    a column on the one active weights row, which an operator versions for the
    whole scheduler, so the caller that claimed the Task read it and passes it
    on, and the gate inside the child refuses at the same number the scheduler
    offered under. The default is the roster's, which is the schema's default,
    for a caller with no weights row to read.

    `token_cap` travels for the same reason and has no default worth writing:
    it is what the claim reserved out of the Program's capacity for this one
    run, so a caller that reserved nothing states nothing, and the child runs
    bounded by its turns alone. A number invented here would be a ceiling no
    Program's capacity was held against.

    `capsule` is what an orchestrator session resumes from, and it travels for
    the third time for the same reason: the child has no database, so what it
    was not given is what it cannot be shown. The Slate is a section of it --
    the bounded set of Tasks this run may choose between -- which is why there
    is no separate field for one: two fields carrying the same entries would be
    two answers to what a session was offered. None for every run that is
    executing a Task rather than choosing one, and a run with none has an empty
    Slate, which is the honest answer for a worker nobody offered a choice.

    `tooling` is the one field that does not travel to the child at all, and it
    is 087's. Where `egress` hands over a capability the child spends itself,
    this stays on the supervisor's side: a tool run is a container to start and a
    row to write, and the child has neither a Docker socket nor a database. So
    the job carries a flag saying whether the channel is open, the child calls
    across it, and the supervisor does the work on a connection of its own.
    None means the two tool-run tools are still served -- the
    roster decides that, not the job -- and answer a refusal, which is the
    honest answer for a run this installation described no tool image for.

    `judgement` is 037's document and travels for the same reason again, with
    one difference worth stating: it is not a bounded projection of a larger
    thing the child could otherwise reach. It is the whole world a validator
    session gets. `rk2_validation_packet` built it from a column allowlist and
    this field carries it unchanged, so what the session may consider is exactly
    what a migration permitted, rather than what a compiler here decided to
    include. None for every role that is not judging one, and a session with
    none is served nothing to judge.
    """

    agent_run_id: str
    objective: str
    container: isolation.AgentContainer
    role: str
    program_id: str | None = None
    packet: packet_module.Packet | None = None
    egress: Egress | None = None
    timeout: float = TIMEOUT
    subagent_cap: int = roster.DEFAULT_SUBAGENTS
    token_cap: int | None = None
    capsule: capsule_module.Capsule | None = None
    judgement: Mapping[str, object] | None = None
    tooling: Tooling | None = None


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    """What one child reported having done. Raw, and true of nothing yet.

    `tool_ready` is a count and not a flag: the criterion is that the tool
    surface opens exactly once, and a flag cannot tell one opening from three.
    `api_key_source` is what the CLI reported rather than what the runtime
    required, for the same reason -- both are evidence, and evidence is what
    Promotion consumes.

    `denials` is the same argument applied to the gate. A run whose evidence
    said only which tools were served would not distinguish a model that never
    asked for a forbidden one from a model that asked and was refused, and the
    second is the more interesting run of the two.

    `mission_result` is the raw submission, or nothing where the child never
    made one. Raw is the operative word: it has been through a closed schema
    and through the gate, and through nothing else. What its Observations cite
    is checked on the runtime's own connection, by `proposal.stage`, because
    the check reads canonical rows and the child cannot. Ticket 20 owns that
    call: it is the ticket that runs one Task from a compiled packet to a
    promoted Observation, and this pair of fields is the seam it writes to.

    `mission_attempts` is how many times the child called the tool, which is
    not how many results it got to make. One result and three attempts is a
    model that argued with its own output and was refused twice, and that is
    worth being able to see from the row rather than only from the transcript.

    `input_tokens` and `output_tokens` are what the session cost, and they are
    the numbers the reservation this run was claimed under is settled against.
    Zero is what a run that never reached the model reports, and it is a
    measurement rather than an absence: nothing was spent because nothing ran.

    `choice` is the Task label an orchestrator session named, and it is a
    report rather than a decision: this label is offered to `record_choice`,
    which asks the database whether the Slate still carries it and refuses it
    when it does not. Nothing with `pick_attempts` at zero is a session that
    chose nothing; nothing with attempts behind it is one whose calls carried
    no label to record.

    `verdict` is the same kind of report from a validator session: what one
    blind judgement answered, checked against a closed schema and against
    nothing else. What the Finding becomes is `record_verdict`'s decision, taken
    from the row that answer produces and from the reproduction the validation
    was opened against, so a session that answers `confirmed` about a replay
    that did not hold is a session whose answer is filed and acted on by nobody.
    `verdict_attempts` counts the calls for `mission_attempts`' reason.
    """

    agent_run_id: str
    role: str
    sdk_version: str | None
    cli_version: str | None
    api_key_source: str
    tool_ready: int
    tools_served: tuple[str, ...]
    denials: tuple[dict, ...]
    answers: int
    stop_reason: str | None
    text: str
    mission_result: Mapping[str, object] | None = None
    mission_attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    choice: str | None = None
    pick_attempts: int = 0
    verdict: Mapping[str, object] | None = None
    verdict_attempts: int = 0

    def as_dict(self) -> dict:
        return {
            "agent_run_id": self.agent_run_id,
            "role": self.role,
            "sdk_version": self.sdk_version,
            "cli_version": self.cli_version,
            "api_key_source": self.api_key_source,
            "tool_ready": self.tool_ready,
            "tools_served": list(self.tools_served),
            "denials": [dict(denial) for denial in self.denials],
            "answers": self.answers,
            "stop_reason": self.stop_reason,
            "text": self.text,
            "mission_result": (
                None if self.mission_result is None else dict(self.mission_result)
            ),
            "mission_attempts": self.mission_attempts,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "choice": self.choice,
            "pick_attempts": self.pick_attempts,
            "verdict": None if self.verdict is None else dict(self.verdict),
            "verdict_attempts": self.verdict_attempts,
        }


def agent_run(
    request: AgentRunRequest, connection: pg.Connection | None = None
) -> AgentRunResult:
    """Start one isolated Agent child and return what it reported.

    The only external launch interface. It describes the run, starts the child
    that asserts and then uses it, and turns a refused child into the whole of
    what that refusal means: the Agent run closed, its Task back in the queue
    with its attempt returned, what it held released, one `startup.refused`
    Event, and a process that will start no further run. It does not decide
    what the run should do, and the only state it writes is that cleanup.

    `connection` and `request.program_id` are optional together, because a
    refusal can happen where there is nothing to record it against -- a run
    started before any Program exists. When either is absent the refusal is
    raised and nothing is written; when both are given they are checked before
    the child is started, because a run whose refusal could not be recorded is
    a run that should not have been started.

    The launch directory is not made here. The filesystem the child works in is
    the container's, not this process's, so the runtime states where the
    directory goes and the child creates it there -- which is also the only way
    the directory the assertion reads can be the directory the CLI is given.
    """
    global _LATCH
    program_id = _recording_program(request, connection)
    serving = _serving(request)
    try:
        if _LATCH is not None:
            raise Latched.of(_LATCH)
        job = {
            "agent_run_id": request.agent_run_id,
            "objective": request.objective,
            "role": request.role,
            "workspace": isolation.WORKSPACE,
            "packet": (request.packet or packet_module.Packet()).as_dict(),
            "egress": None if request.egress is None else request.egress.as_dict(),
            "subagent_cap": request.subagent_cap,
            "token_cap": request.token_cap,
            "capsule": (request.capsule or capsule_module.Capsule()).as_dict(),
            "judgement": None if request.judgement is None else dict(request.judgement),
            # A flag rather than a block, because there is nothing in it for the
            # child: the image, the store and the connection are all on this
            # side. What the child needs to know is whether asking will be
            # answered, and a child that asked into a pipe nobody was reading
            # would wait there until the run's own deadline.
            "tooling": serving is not None,
        }
        # Ticket 146. The setup token travels on the child's own stdin, in the
        # document that is already private to it, and it is put in last so that
        # every other value above is decided without it. The key is absent
        # rather than null where this machine holds no token: a child popping a
        # key that is not there is a child that has been told there is none, and
        # the doctor is where an operator is told before a run finds out. It
        # goes nowhere else -- not into a Docker argument, a log, the database,
        # a Mission packet, the Program directory or an Artifact.
        token = isolation.oauth_token()
        if token:
            job["oauth_token"] = token
        return _spawn(request, job, serving)
    except StartupRefusal as refusal:
        # Latched first. The cleanup talks to a database, and a database that
        # is unreachable must not be the reason this process goes on to start
        # the run it has just refused.
        _LATCH = _LATCH or refusal
        if program_id is not None and connection is not None:
            try:
                close_refusal(connection, program_id, request.agent_run_id, refusal)
            except Exception as failure:
                # A cleanup that could not run is a row left open, which the
                # lease expiry is what reclaims. What must not happen is the
                # database's error replacing the refusal on the way out: the
                # caller would be told the run failed rather than that this
                # machine may not start one, and would exit as something else.
                raise refusal from failure
        raise
    finally:
        # Whatever the run did, the connection it may have opened is this
        # function's to close: the caller was never given one to close.
        if serving is not None:
            serving.close()


def close_refusal(
    connection: pg.Connection,
    program_id: str,
    agent_run_id: str,
    refusal: StartupRefusal,
) -> bool:
    """Make one refusal durable, and say whether this call was the one that did.

    Closes the Agent run, returns its Task to pending with the attempt it never
    spent, releases its Task and Identity Leases, unbinds its session and emits
    the one redacted `startup.refused` Event. `False` says there was nothing
    open to close -- a run that already finished, or one this Program does not
    own -- which is what a repeat of the cleanup finds, and why repeating it
    changes nothing rather than emitting a second Event.
    """
    connection.execute(BIND, (program_id,))
    closed = connection.execute(
        CLOSE,
        (
            agent_run_id,
            refusal.phase,
            refusal.sdk_version,
            refusal.cli_version,
            json.dumps(list(refusal.violations)),
        ),
    ).scalar()
    return bool(closed)


def diagnostics(refusal: StartupRefusal) -> Report:
    """One refusal as the outcome an operator reads and a caller exits on.

    Each record becomes a violation naming where the vector was found -- the
    variable, the settings file and key, the launch field, the init report --
    and the effect that was measured for it, and never the value: a diagnostic
    that printed what it found would publish the credential it refused.

    The report is the supervisor's rather than a command's, because the
    supervisor is what refuses; the command that prints it belongs to whatever
    later asks for an Agent run. What it fixes here is the status: a refused
    startup exits `EXIT_STARTUP_REFUSED`, so a caller can tell it from a run
    that started and went wrong.
    """
    ledger = Ledger()
    ledger.refuse(
        "startup_assertion",
        f"refused in {refusal.phase} by {len(refusal.violations)} vector(s)",
        [
            Violation(
                code=STARTUP_REFUSED,
                source=str(record["source"]),
                detail=f"{record['code']}, measured effect {record['effect']}",
            )
            for record in refusal.violations
        ],
    )
    return report(
        "agent run",
        ledger,
        phase=refusal.phase,
        sdk_version=refusal.sdk_version,
        cli_version=refusal.cli_version,
    )


def _recording_program(request: AgentRunRequest, connection: pg.Connection | None) -> str | None:
    """The Program a refusal of this run would be recorded against, if any.

    Asked before the child starts rather than in the refusal path. An
    identifier the cleanup could not use is a failure that would otherwise
    arrive at the one moment there is durable state to clean up and no way left
    to clean it.
    """
    if connection is None or request.program_id is None:
        return None
    for field, value in (
        ("program_id", request.program_id),
        ("agent_run_id", request.agent_run_id),
    ):
        try:
            uuid.UUID(str(value))
        except ValueError:
            raise ValueError(
                f"an agent run recorded against a Program needs a {field} that is a UUID"
            ) from None
    return request.program_id


def launch_directory(workspace: Path | str, agent_run_id: str) -> Path:
    """The runtime-owned directory this run works in, made private.

    The identifier is one path component and is checked to be one. A run
    identifier that could contain a separator would be a run that chooses where
    the runtime writes, and the settings document the assertion trusts lives in
    exactly this directory.
    """
    root = Path(workspace).resolve()
    launch = (root / agent_run_id).resolve()
    if launch.parent != root or launch == root:
        raise ValueError("an agent run identifier must be one path component")
    launch.mkdir(parents=True, exist_ok=True)
    launch.chmod(PRIVATE)
    return launch


def write_settings(launch: Path) -> Path:
    """Put the one settings document the child may load where it may load it."""
    settings = launch / SETTINGS
    settings.write_text(json.dumps(SETTINGS_DOCUMENT), encoding="utf-8")
    settings.chmod(0o600)
    return settings


def setting_sources(role: roster.Role) -> list[str]:
    """Which of the CLI's settings locations this role's launch opens.

    None for a role that loads no Skill, which is what every launch here opened
    before there were Skills: an empty list is a CLI reading nothing it was not
    handed. `project` for a role that does load one, because that is how the
    CLI finds a skill at all -- it reads the location off the working directory
    -- and a grant it cannot find is a grant the model cannot use.

    Opening it is not opening the operator's files. The directory is the one
    `launch_directory` made for this run, private and written only by this
    runtime, so what `project` names here is what the runtime itself staged.
    `user` would be the operator's home and is not in the list for any role.
    """
    return [PROJECT] if role.skills else []


def stage_skills(launch: Path, role: str) -> tuple[Path, ...]:
    """Put the Skills this role was granted where its child will load them.

    Written from the roster row the options value is built from, so the name
    the gate admits and the file the CLI reads come from one place. A role
    this roster does not have stages nothing rather than raising: `assess`
    refuses an unknown role by name, and failing here first would report a
    missing directory in place of the missing row that caused it.
    """
    granted = roster.ROLES.get(role)
    return () if granted is None else skill.stage(launch, granted.skills)


def assess(
    options: object,
    environment: Mapping[str, str],
    runtime: Mapping[str, object],
    *,
    launch_dir: Path | str,
    role: str,
    managed_settings: Sequence[Path] | None = None,
) -> tuple[dict, ...]:
    """Everything about this launch that can be decided before it happens.

    Takes the options value by duck typing so that the rules are reachable
    without the SDK installed, and so that the object the child assesses is the
    object the child then runs. Returns every violation it can see rather than
    the first, because an operator fixing one vector should be told about the
    other three in the same breath.

    `role` is what most of the option checks are checks *against*: this launch
    is contained by being one row of the roster, so the question is not whether
    the turn ceiling is reasonable but whether it is that role's. A role this
    roster does not have -- or one that runs no model, which this door cannot
    start -- is itself the refusal, and the option checks are skipped after it
    for the same reason they are skipped on an unmeasured runtime: they are
    statements about what a particular role's launch should look like, and
    there is no such role to compare against.

    `managed_settings` is a parameter so that the negative outcomes stay
    reachable from tests without writing to `/etc` on the machine running them.
    A launch supplies none: the CLI reads exactly the locations `MANAGED_SETTINGS`
    names, and a caller choosing them would be choosing what the assertion sees.
    Nothing rather than that tuple is the default, so the locations are the ones
    this module holds in the process that is asserting rather than the ones it
    held when some other process imported it.
    """
    launch = Path(launch_dir).resolve()
    managed = MANAGED_SETTINGS if managed_settings is None else managed_settings
    configuration: list[dict] = []

    unmeasured = _runtime_violations(options, runtime)
    configuration.extend(unmeasured)
    # A renderer is a role of this harness and not a session of this SDK. It
    # has no model, no turn and no tool, so there is nothing here for it to be
    # assessed as, and a door that started one would be a door that made it an
    # agent.
    #
    # A role whose enforced surface is empty is refused for the same reason. It
    # was the validator's case until 037 served `validate.judge`: a launch would
    # have started a model at its own effort for its own turn ceiling with no
    # verdict tool to reach, and what it could have produced is prose, which is
    # the one thing this runtime does not accept as a result. The check stays
    # because the condition is what it always was -- the intersection shrinking
    # to nothing is how the roster says a role's ticket has not landed yet, and
    # the door should say so rather than spend a run finding out.
    known = role in roster.ROLES and not roster.ROLES[role].rendered
    launchable = known and bool(roster.ROLES[role].allowed_tools(SERVED))
    if not launchable:
        configuration.append(_violation(INVALID_LAUNCH, "launch:role"))
    elif not any(violation["code"] == UNMEASURED_RUNTIME for violation in unmeasured):
        # Skipped rather than reported as failures on an unmeasured runtime.
        # Every one of those checks is a statement about what a field of *this*
        # SDK version does, and on a version this harness has not measured the
        # honest answer is that the options value was not interpreted at all.
        # The environment and the settings files are read either way: they are
        # facts about the machine, and an operator fixing the runtime pair
        # should learn about their exported key in the same breath.
        configuration.extend(_option_violations(options, launch, role))
    settings, settings_violations = _settings_documents(options, launch, managed)
    configuration.extend(settings_violations)

    if not isinstance(environment, Mapping):
        configuration.append(_violation(INVALID_LAUNCH, "launch:environment"))
        environment = {}
    try:
        credentials = _startup.evaluate_inputs(
            {
                "environment": dict(environment),
                "settings": settings,
                "setting_sources": [],
            }
        )["violations"]
    except _startup.ManifestError:
        credentials = []
        configuration.append(_violation(INVALID_LAUNCH, "launch:environment"))

    configuration.sort(key=lambda item: (item["code"], item["source"]))
    return tuple(credentials + configuration)


def corroboration(api_key_source: object) -> tuple[dict, ...]:
    """What the init message has to say, and the refusal when it does not.

    The one question the pre-spawn phase cannot answer. Everything before this
    is a statement about the inputs; this is the CLI reporting which credential
    it actually resolved, and a source this runtime did not expect means a key
    reached it by a path the measured matrix does not name.
    """
    if api_key_source == EXPECTED_KEY_SOURCE:
        return ()
    return (_violation(AUTH_SOURCE_UNEXPECTED, "init:apiKeySource"),)


def uncorroborated(reason: str) -> tuple[dict, ...]:
    """The refusal for a child that never gave the runtime an init to read.

    Kept apart from `corroboration` because they are different findings. That
    one says the CLI resolved a credential this runtime did not expect; this
    one says the CLI produced work before the runtime had assessed it, or ended
    without ever announcing itself -- in both cases nothing was measured, so
    there is no key source to report.
    """
    return (_violation(INIT_UNCORROBORATED, f"init:{reason}"),)


def _violation(code: str, source: str) -> dict:
    """One refusal that names a thing the runtime could not verify."""
    return {"code": code, "vector": None, "source": source, "effect": UNVERIFIABLE}


def _runtime_violations(options: object, runtime: Mapping[str, object]) -> list[dict]:
    """The SDK, the CLI it bundles, and the executable that will actually run.

    One violation covers all three, because they are one fact: this is not a
    runtime pair the credential matrix was measured against, so nothing below
    can be relied on. A missing executable counts as an unmeasured runtime for
    the same reason -- the version a package declares is not evidence about a
    file that is not there.
    """
    pair = (runtime.get("sdk_version"), runtime.get("cli_version"))
    executable = bundled_executable(runtime)
    if pair != _startup.KNOWN_RUNTIME or executable is None:
        return [_violation(UNMEASURED_RUNTIME, "runtime:sdk-cli")]
    if options is None:
        # There is no options value to name an executable, and whatever made
        # the launch undescribable has already said so. Adding a second
        # violation here would report one fault as two.
        return []
    if getattr(options, "cli_path", None) != str(executable):
        # Not a runtime violation but the same failure it prevents: an options
        # value that does not name the measured executable is one the SDK would
        # resolve from `PATH`.
        return [_violation(INVALID_LAUNCH, "launch:cli_path")]
    return []


def bundled_executable(runtime: Mapping[str, object]) -> Path | None:
    """The bundled CLI this launch would run, or nothing if there is not one."""
    declared = runtime.get("cli_path")
    if declared is None:
        return None
    try:
        executable = Path(str(declared)).resolve()
    except (OSError, TypeError, ValueError):
        return None
    if not executable.is_file() or not os.access(executable, os.X_OK):
        return None
    return executable


def _option_violations(options: object, launch: Path, role: str) -> list[dict]:
    """The fields of the options value that decide what the child can reach.

    Each one is a containment property rather than a preference: an SDK `env`
    that is not empty can add a watched variable after it was inspected, a
    sandbox merges settings this runtime did not write, and a working directory
    that is not the runtime's own is a directory the runtime does not own.

    The settings locations are the same property stated per role. A role that
    loads no Skill opens none, and a role that loads one opens `project` and
    only `project`, which is this launch's own directory -- so the widening a
    Skill grant needs is the narrowest one that lets the CLI read what the
    runtime staged, and `user` is out of reach either way. Which of the two a
    launch may be is `setting_sources`' answer and not this function's, because
    the value asserted and the value built have to come from one place.

    The Skills are the same shape again: the names the options value carries
    are the roster's grants, and each of them is a file on disk in the
    directory `project` names. A grant with no file is a name the gate admits
    and the CLI cannot answer, which is a launch that hands the model a tool
    call that was always going to fail.

    The rest are the roster, restated as a question about this options value.
    They are not asserted because a mismatch would be dangerous by itself --
    a turn ceiling of 60 on the orchestrator is merely wrong -- but because a
    launch that differs from the roster in any field is a launch some other
    thing decided, and the roster's whole claim is that nothing else does. The
    two tool lists are the sharp end: `tools` is what the model is shown and
    `allowed_tools` is what it may call unprompted, and neither may be wider
    than the compiled grants, because the permission mode is
    `bypassPermissions` and offering a tool under that mode is running it.

    Widening either one still would not widen the role's authority -- the gate
    denies from the roster and not from these lists -- but it would spend a
    turn on a call that was always going to be refused, and it would put a tool
    in a frame that is supposed to be the role's real surface.
    """
    served = getattr(options, "mcp_servers", None)
    expected = roster.ROLES[role]
    checks = {
        "env": getattr(options, "env", None) == {},
        "setting_sources": getattr(options, "setting_sources", None)
        == setting_sources(expected),
        "skills": getattr(options, "skills", None) == list(expected.skills),
        "skills_staged": all(
            (launch / skill.STAGED / name / skill.INSTRUCTIONS).is_file()
            for name in expected.skills
        ),
        "sandbox": getattr(options, "sandbox", "unset") is None,
        "cwd": getattr(options, "cwd", None) == str(launch) and launch.is_dir(),
        "builtin_tools": getattr(options, "tools", None) == expected.visible_tools,
        "permission_mode": getattr(options, "permission_mode", None) == PERMISSION_MODE,
        "allowed_tools": getattr(options, "allowed_tools", None)
        == expected.allowed_tools(SERVED),
        "mcp_servers": isinstance(served, Mapping) and set(served) == {SERVER},
        "model": getattr(options, "model", "unset") == expected.model,
        "effort": getattr(options, "effort", "unset") == expected.effort,
        "max_turns": getattr(options, "max_turns", None) == expected.max_turns,
        "hooks": _gated(options),
    }
    return [
        _violation(INVALID_LAUNCH, f"launch:{field}")
        for field, holds in checks.items()
        if not holds
    ]


def _gated(options: object) -> bool:
    """Whether this options value carries the gate on every event it needs.

    Checked structurally rather than by identity. What the assertion can see is
    that each event has at least one matcher that matches every tool and has a
    callback behind it; that the callback is the roster's is a fact about the
    module that built the value, and `_launch` is the only module that can.
    """
    hooks = getattr(options, "hooks", None)
    if not isinstance(hooks, Mapping) or set(hooks) != set(GATE_EVENTS):
        return False
    return all(
        any(
            getattr(matcher, "matcher", "unset") is None and getattr(matcher, "hooks", ())
            for matcher in hooks[event]
        )
        for event in GATE_EVENTS
    )


def _settings_documents(
    options: object, launch: Path, managed_settings: Sequence[Path]
) -> tuple[list[dict], list[dict]]:
    """Every settings document that will load, and what was wrong with reading it.

    The managed locations are read unconditionally because the CLI reads them
    unconditionally. The explicit one is read only when it is the canonical
    file in the runtime's own directory: a settings path anywhere else is
    refused, and refused before it is parsed, so a document the runtime does
    not own never contributes a symbolic setting.
    """
    documents: list[dict] = []
    violations: list[dict] = []
    loading = [
        (path, "managed") for path in map(Path, managed_settings) if path.exists()
    ]

    declared = getattr(options, "settings", None)
    if declared is not None:
        try:
            path = Path(str(declared))
            owned = path.is_absolute() and path.resolve() == launch / SETTINGS
        except (OSError, TypeError, ValueError):
            owned = False
        if owned:
            loading.append((path.resolve(), "explicit"))
        else:
            # Refused, and the managed locations still read. They load whatever
            # this one turned out to be, so an operator with a stray settings
            # path and an exported key in `/etc` learns about both at once.
            violations.append(_violation(INVALID_LAUNCH, "launch:settings"))

    for path, kind in loading:
        document, refusal = _read_settings(path, kind)
        (violations if refusal else documents).append(refusal or document)
    return documents, violations


def _read_settings(path: Path, kind: str) -> tuple[dict | None, dict | None]:
    """One settings file as a symbolic document, or the refusal to read it.

    A file that cannot be read and a file that is not the shape the evaluator
    understands are the same refusal: either way this runtime cannot say what
    the CLI will load from it, and a launch it cannot describe is one it does
    not start.
    """
    source = f"settings:{kind}:{path}#document"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, _violation(SETTINGS_UNREADABLE, source)
    if not isinstance(document, dict) or not isinstance(document.get("env", {}), dict):
        return None, _violation(SETTINGS_UNREADABLE, source)
    return {"kind": kind, "path": str(path), "document": document}, None


def _spawn(
    request: AgentRunRequest,
    job: Mapping[str, object],
    serving: Callable[[Mapping[str, object]], Mapping[str, object]] | None = None,
) -> AgentRunResult:
    """Run the child in its boundary, and read back its result or its refusal.

    `-P` because the child's import path is the runtime's statement about which
    application and which SDK this launch is measured against, and a working
    directory on that path is a second answer to a question that has one.

    The job ends in a newline because the child reads one line rather than a
    stream to its end: with `serving` the pipe stays open for the run's whole
    length, and a read to the end of it would be a read that never returns.
    """
    child = isolation.run(
        request.container,
        (isolation.INTERPRETER, "-P", "-m", CHILD),
        stdin=json.dumps(job) + "\n",
        timeout=request.timeout,
        answer=serving,
    )
    refusal = _refusal(child.stderr)
    if refusal is not None:
        raise refusal
    result = _last_document(child.stdout)
    if result is None:
        raise RuntimeError(
            f"the agent child exited {child.returncode} without a result: "
            + (child.stderr or child.stdout or "")[-DIAGNOSTIC:]
        )
    return AgentRunResult(
        agent_run_id=request.agent_run_id,
        role=request.role,
        sdk_version=result.get("sdk_version"),
        cli_version=result.get("cli_version"),
        api_key_source=str(result.get("api_key_source")),
        tool_ready=int(result.get("tool_ready") or 0),
        tools_served=tuple(result.get("tools_served") or ()),
        denials=tuple(
            dict(denial)
            for denial in (result.get("denials") or ())
            if isinstance(denial, Mapping)
        ),
        answers=int(result.get("answers") or 0),
        stop_reason=result.get("stop_reason"),
        text=str(result.get("text") or ""),
        mission_result=(
            dict(mission) if isinstance(mission := result.get("mission_result"), Mapping) else None
        ),
        mission_attempts=int(result.get("mission_attempts") or 0),
        input_tokens=int(result.get("input_tokens") or 0),
        output_tokens=int(result.get("output_tokens") or 0),
        # A label and nothing else. Anything that is not a non-empty string is
        # read as no choice at all rather than coerced into one: the caller
        # records what a session answered, and `str(None)` is a Task label
        # nothing offered and nothing will claim.
        choice=(
            choice if isinstance(choice := result.get("choice"), str) and choice else None
        ),
        pick_attempts=int(result.get("pick_attempts") or 0),
        verdict=(
            dict(answer) if isinstance(answer := result.get("verdict"), Mapping) else None
        ),
        verdict_attempts=int(result.get("verdict_attempts") or 0),
    )


def _serving(request: AgentRunRequest) -> "_Tools | None":
    """What answers this run's tool calls, or nothing if nothing can.

    Two things have to be true together and neither is the child's to know: this
    installation described a tool image, a store and a connection, and the run
    belongs to a Program. Nothing when either is missing, which is what closes
    the channel -- and the child is told the channel is closed rather than left
    to find out by asking into a pipe nobody is reading.
    """
    if request.tooling is None or request.program_id is None:
        return None
    return _Tools(request.tooling, request.program_id, request.agent_run_id)


class _Tools:
    """One child's tool calls, answered on a connection of this object's own.

    The dispatch is on the verb and it is closed. The roster has already refused
    every call that does not fit its contract, so what arrives here is a
    well-formed call to one of four tools, or the one ask that is not a tool;
    anything else is a child that has started making things up, and it is
    answered rather than executed.

    Two of the four start a container and the other two write a row, and they
    are answered here for the same reason: this is the side holding a
    connection. A child's one network reaches the capability proxy, so a
    proposal it could file itself would be a proposal filed by the party the row
    is about -- and a correlator it could mint itself would be a name the
    runtime never saw published.

    The fifth is a read and no model asks for it. An exchange through the door
    files two Artifacts and a Receipt in one transaction and answers the child
    with the Receipt label alone, so the labels for the bytes exist and are
    unreachable from inside the container. That is the same asymmetry as the
    other four -- the rows are here and the child is not -- and it is answered
    the same way.

    The sixth is a read a model does ask for, and it is the only arm here that
    does not run on this object's connection. `refresh_packet` hands back whole
    rows, and the role whose row level security decides which Program a row
    belongs to is `rk2_state`, not the `rk2_runtime` the other five hold. So it
    opens its own connection as that role, and every scoping question about it
    is answered by the server rather than by this module.

    The connection is opened at the first call and not before. Most runs ask for
    no tool at all, and a connection held open through every one of them would
    be one connection per child for a thing most children never do.
    """

    def __init__(self, tooling: Tooling, program_id: str, agent_run_id: str) -> None:
        self._tooling = tooling
        self._program_id = program_id
        self._agent_run_id = agent_run_id
        self._connection: pg.Connection | None = None

    def __call__(self, call: Mapping[str, object]) -> Mapping[str, object]:
        verb = str(call.get("verb") or "")
        if verb not in (
            roster.RUN_TOOL,
            roster.RUN_SKILL_SCRIPT,
            roster.PROPOSE_FINDING,
            roster.PROPOSE_TEST,
            roster.MINT_CALLBACK,
            roster.REFRESH_PACKET,
            NAME_TRANSCRIPTS,
        ):
            return {"served": False, "reason": UNKNOWN_CALL, "detail": f"{verb} is not served"}

        # Before the runtime connection rather than after it, because this is
        # the one verb here that never touches it. Opening one to answer a
        # refresh would be a connection opened for nothing, and on the failure
        # path it would be a refusal about a role the answer does not involve.
        #
        # The call itself rather than a field of it, because that is the frame
        # this side is handed. `Channel.call` writes `{**arguments, "verb": verb}`
        # and `isolation` passes that object straight through, so a contract's
        # arguments arrive beside the verb rather than under a key. `run_tool`
        # looks like the exception and is not: `arguments` is a declared
        # argument of that contract -- the arguments of the program being run --
        # and not the envelope this one would be read out of.
        if verb == roster.REFRESH_PACKET:
            return self._refresh(call)

        # The two verbs that need an image, before the connection rather than
        # after it: a machine with no image cannot serve them however well the
        # database answers, and opening a connection to say so would be a
        # connection opened for a refusal. The other three need the database and
        # not the image, which is the whole point of the split.
        if verb in (roster.RUN_TOOL, roster.RUN_SKILL_SCRIPT) and (
            self._tooling.container is None or self._tooling.root is None
        ):
            return {
                "served": False,
                "reason": NO_TOOL_IMAGE,
                "detail": "this installation describes no tool image and no Artifact "
                          "store, so there is nothing to run a registered tool with",
            }

        try:
            connection = self._open()
        except (pg.ConnectionError_, OSError) as error:
            return {"served": False, "reason": UNREACHABLE_STATE, "detail": str(error)}

        # The frame, not a field of it, for the reason written four paragraphs
        # up and contradicted here until 2026-08-22: `Channel.call` writes the
        # arguments beside the verb, so `call.get("arguments")` was None on
        # every real call and every Finding a child has ever proposed reached
        # `propose_finding` as three empty strings. Only `tests/test_agent.py`
        # ever sent a nested envelope, which is why nothing went red.
        if verb == roster.PROPOSE_FINDING:
            return self._propose(connection, call)

        if verb == roster.PROPOSE_TEST:
            return self._specify(connection, call)

        if verb == roster.MINT_CALLBACK:
            return self._callback(connection, call)

        if verb == NAME_TRANSCRIPTS:
            return self._transcripts(connection, call)

        if verb == roster.RUN_TOOL:
            named: str | None = str(call.get("tool") or "")
        else:
            # The registry resolves the pair, because the pair is the whole of
            # what a child may name: a Skill it holds and a script in it. A
            # script this harness has no enabled row for is the same refusal as
            # an unknown tool, in the same words.
            named = tool_module.script(
                connection, str(call.get("skill_name") or ""), str(call.get("script") or "")
            )
            if named is None:
                return {
                    "served": False,
                    "reason": tool_module.UNREGISTERED_TOOL,
                    "detail": f"{call.get('skill_name')}/{call.get('script')} "
                              "is not a Skill script this harness runs",
                }
        given = call.get("arguments")
        return tool_module.serve(
            connection,
            self._tooling.root,
            self._tooling.container,
            program_id=self._program_id,
            agent_run_id=self._agent_run_id,
            offline_tool=named,
            arguments=(
                {str(name): str(value) for name, value in given.items()}
                if isinstance(given, Mapping)
                else {}
            ),
            excerpt=packet_module.DEFAULT_EXCERPT,
        )

    def _propose(
        self, connection: pg.Connection, given: object
    ) -> Mapping[str, object]:
        """Carry one Finding proposal to the runtime and answer what it said.

        The three declared arguments and nothing else, because the two fields
        that matter most are not the child's to name: the Program is bound on
        the connection so that a runtime holding one connection open cannot be
        asked to open a Finding against another Program, and the Agent run is
        the one this object was built for.

        A refusal comes back as a refusal and not as an exception.
        `rk2_finding_refusal` answers with the sentence saying why, and that
        sentence is the record ticket 36 built; turning it into an exception
        would leave the child with a tool that failed and leave nobody with the
        reason. What is raised rather than answered is the database being
        unreachable or refusing the statement outright, which is not a verdict
        on the proposal at all and is reported as the state it is.
        """
        arguments = given if isinstance(given, Mapping) else {}
        try:
            connection.execute(BIND, (self._program_id,))
            answered = connection.execute(
                PROPOSE,
                (
                    str(arguments.get("hypothesis_label") or ""),
                    str(arguments.get("vulnerability_class") or ""),
                    str(arguments.get("title") or ""),
                    self._agent_run_id,
                ),
            ).scalar()
        except (pg.DatabaseError, pg.ConnectionError_, OSError) as error:
            return {"served": False, "reason": UNREACHABLE_STATE, "detail": str(error)}
        document = json.loads(str(answered))
        return document if isinstance(document, Mapping) else {}

    def _specify(
        self, connection: pg.Connection, given: object
    ) -> Mapping[str, object]:
        """Carry one Test specification to the runtime and answer what it said.

        Everything in the frame except the verb and the label, rather than a
        list of part names held here. `rk2_test_spec_problem` refuses a key it
        has no part for, by name, and it is the authority on which parts exist:
        a copy of that list on this side would be a second statement of the
        shape rule, free to drift the day a part is added.

        Key order does not reach the digest. `rk2_test_spec_digest` is taken
        over the `jsonb` rendering, whose keys are stored sorted, so two
        submissions of one specification collide on
        `tests_hypothesis_id_spec_sha256_key` however the child spelled them.

        A refusal comes back as a refusal, for the reason `_propose` gives: the
        sentence saying which of the thirty shape rules was broken is the whole
        product of the call, and an exception would leave the child with a tool
        that failed and nobody with the reason.
        """
        arguments = given if isinstance(given, Mapping) else {}
        specification = {
            str(name): value
            for name, value in arguments.items()
            if name not in ("verb", "hypothesis_label")
        }
        try:
            connection.execute(BIND, (self._program_id,))
            answered = connection.execute(
                PROPOSE_TEST,
                (
                    str(arguments.get("hypothesis_label") or ""),
                    json.dumps(specification),
                    self._agent_run_id,
                ),
            ).scalar()
        except (pg.DatabaseError, pg.ConnectionError_, OSError) as error:
            return {"served": False, "reason": UNREACHABLE_STATE, "detail": str(error)}
        document = json.loads(str(answered))
        return document if isinstance(document, Mapping) else {}

    def _callback(
        self, connection: pg.Connection, given: object
    ) -> Mapping[str, object]:
        """Mint one out-of-band correlator for this run and answer the address.

        The correlator is generated here rather than asked for or read back,
        which is the one thing this method does that the database could not do
        for itself. It is 128 bits of `secrets` in hex, which is a single DNS
        label with room to spare and is the shape `mint_callback_correlator`
        insists on; it is passed down, digested there and stored nowhere; and
        the only copy that survives this call is the address in the answer.
        There is no second chance to read it, which is the property a
        capability has and is here for the opposite reason -- not because a
        canary is dangerous to keep, but because a stored one is one more place
        a name the target can see could be learned from.

        Which Agent run is asking is this side's to fill in, like the Program
        bound on the connection: a child that named its own run would be naming
        which run it would like an arrival attributed to.

        A refusal comes back as a refusal, in `_propose`'s words and for its
        reason. What is raised rather than answered is the database being
        unreachable, which is not a verdict on the request at all.
        """
        arguments = given if isinstance(given, Mapping) else {}
        try:
            connection.execute(BIND, (self._program_id,))
            answered = connection.execute(
                MINT_CALLBACK,
                (
                    str(arguments.get("channel") or ""),
                    secrets.token_hex(callback.CORRELATOR_BYTES),
                    str(arguments.get("subject_label") or ""),
                    self._agent_run_id,
                ),
            ).scalar()
        except (pg.DatabaseError, pg.ConnectionError_, OSError) as error:
            return {"served": False, "reason": UNREACHABLE_STATE, "detail": str(error)}
        document = json.loads(str(answered))
        return document if isinstance(document, Mapping) else {}

    def _transcripts(
        self, connection: pg.Connection, given: object
    ) -> Mapping[str, object]:
        """Name the two Artifacts one exchange filed, for the Receipt it filed them under.

        The one arm here that mints nothing and decides nothing. The rows were
        written by `hold_receipt_transcripts()` in the same transaction as the
        Receipt, before the door had even answered the child, so this is a read
        of something already true -- which is why it costs the run nothing and
        why there is no refusal for it to make.

        One argument, and it is a label the child was just handed rather than
        one it composed. The Program is this side's, like everywhere else on
        this dispatch: a child naming the Program a Receipt label belongs to
        would be a child choosing which Program's exchange to read.

        What is raised rather than answered is the database being unreachable,
        in `_propose`'s words and for its reason -- and a run that gets that
        answer still holds its Receipt label, which is what it held before this
        ticket existed.

        The whole frame is read rather than an `arguments` field of it, because
        that is what the channel sends: `Channel.call` writes the arguments
        beside the verb, not under a key, and `isolation` hands this side that
        object unchanged.
        """
        arguments = given if isinstance(given, Mapping) else {}
        try:
            connection.execute(BIND, (self._program_id,))
            answered = connection.execute(
                TRANSCRIPTS, (str(arguments.get("receipt") or ""),)
            ).scalar()
        except (pg.DatabaseError, pg.ConnectionError_, OSError) as error:
            return {"served": False, "reason": UNREACHABLE_STATE, "detail": str(error)}
        document = json.loads(str(answered))
        return document if isinstance(document, Mapping) else {}

    def _refresh(self, given: object) -> Mapping[str, object]:
        """Read back the rows this run has minted since it started, by label.

        The answer to the defect ticket 107 names: a packet is compiled before
        the container starts, so every label the runtime hands a child while it
        runs -- an exchange's two Artifacts, a tool run's row and its streams --
        resolves to `not_staged` against the document the child is reading. The
        rows are here and the child is not, which is this dispatch's whole
        subject; what is different is that the answer is rows rather than a
        verdict.

        As `rk2_state`, on a connection opened for this call and closed with it.
        Not cached like the runtime one, and the reason is the transaction: the
        Program is bound with `set_config(..., true)`, which lasts exactly one
        transaction, and the read is `SET TRANSACTION READ ONLY`. A connection
        kept between calls would have to re-establish both every time anyway,
        and would spend the run holding a second connection open for something
        most runs do once.

        `assert_agent_connection` before anything is read, and it is not
        ceremony. It establishes that this connection cannot read the Program
        registry, which is what makes an absent label and another Program's
        label indistinguishable from here -- and a refresh answers by label, so
        that is precisely the distinction a child must not be able to draw.

        Which Program is this side's, as everywhere on this dispatch. There is
        no argument for it and there could not be: a child naming the Program
        whose Receipts it would like refreshed is a child choosing whose rows to
        read.

        The limits are the module's defaults rather than the configured weights
        row, and that is deliberate rather than an omission. What `limits` still
        decides here is the excerpt ceiling -- how much of an Artifact's head may
        be staged -- and `execution._packet_limits` reads only the byte and token
        columns, leaving the excerpt at that same default. Reading the row would
        make no difference to the one field that matters and would need the
        runtime connection this arm does not open.

        A refusal comes back as a refusal, in `_propose`'s words and for its
        reason: a run told it could not be refreshed still holds everything its
        packet was compiled with.

        The whole frame is read rather than an `arguments` field of it, for
        `_transcripts`' reason: the channel writes a contract's arguments beside
        the verb, and `verb` is not one of the three names read out of it.
        """
        arguments = given if isinstance(given, Mapping) else {}
        if self._tooling.state is None:
            return {
                "served": False,
                "reason": UNREACHABLE_STATE,
                "detail": "this run was started with no agent-scoped connection; "
                          "the packet it was launched with is unchanged",
            }
        named = {
            section: arguments.get(wire) or []
            for wire, section in packet_module.REFRESH_ARGUMENTS.items()
        }
        ledger = Ledger()
        try:
            session = pg.connect(self._tooling.state)
        except (pg.DatabaseError, pg.ConnectionError_, OSError) as error:
            return {"served": False, "reason": UNREACHABLE_STATE, "detail": str(error)}
        try:
            with session:
                if not state_module.assert_agent_connection(ledger, session):
                    return {
                        "served": False,
                        "reason": UNREACHABLE_STATE,
                        "detail": _refused(ledger),
                    }
                with session.transaction():
                    session.execute(REFRESH_READ_ONLY)
                    if not state_module.bind_agent_session(
                        ledger, session, self._program_id
                    ):
                        return {
                            "served": False,
                            "reason": UNREACHABLE_STATE,
                            "detail": _refused(ledger),
                        }
                    fragment, held = packet_module.refresh(
                        session, named, load=self._excerpts()
                    )
        except (pg.DatabaseError, pg.ConnectionError_, OSError) as error:
            return {"served": False, "reason": UNREACHABLE_STATE, "detail": str(error)}
        return {"packet": fragment.as_dict(), "held": held}

    def _excerpts(self) -> Callable[[str], bytes | None]:
        """How a refresh reads the head of an Artifact it just staged a row for.

        The store is content-addressed and this is the side that may address it
        that way; the child has no route to it at all, which is why a head
        travels inside the answer or not at all.

        Every failure answers `None` rather than raising, for
        `execution._excerpt_loader`'s reason: a hash the store does not hold and
        a hash whose bytes no longer match it are both "this Artifact has no
        readable head here", and a refresh that raised on one would lose every
        other row in the same answer over a single missing file.
        """
        keep = store.Store(self._tooling.root)

        def load(sha256: str) -> bytes | None:
            try:
                return keep.load(sha256)
            except (store.Missing, store.Corrupt, OSError):
                return None

        return load

    def _open(self) -> pg.Connection:
        if self._connection is None:
            self._connection = pg.connect(self._tooling.runtime)
        return self._connection

    def close(self) -> None:
        """Give back what a call opened, whether or not anything opened it."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None


def _refused(ledger: Ledger) -> str:
    """Why an assertion on the agent connection said no, in one sentence.

    The shared assertions report into a `Ledger` because their other callers are
    operator commands that print one. This dispatch answers a child rather than
    an operator, and a child can act on a sentence: the alternative was a second
    copy of "is this really the agent connection", which `state` says in as many
    words is the thing not to have.
    """
    return "; ".join(violation.detail for violation in ledger.violations)


def _refusal(stderr: str) -> StartupRefusal | None:
    """The refusal a child reported, if what it reported is a well-formed one.

    A malformed refusal record is not turned into a refusal. It would be a
    refusal this runtime invented from a broken child rather than one the
    assertion made, and the caller is better served by the unclassified error
    `_spawn` raises when there is no result either.
    """
    document = _last_document(stderr)
    if document is None or set(document) != {"startup_refusal"}:
        return None
    reported = document["startup_refusal"]
    if not isinstance(reported, Mapping):
        return None
    try:
        return StartupRefusal(
            reported.get("violations") or (),
            reported.get("phase") or "",
            reported.get("sdk_version"),
            reported.get("cli_version"),
        )
    except (TypeError, ValueError):
        return None


def _last_document(stream: str) -> dict | None:
    """The last JSON object on a stream, ignoring everything that is not one."""
    for line in reversed((stream or "").strip().splitlines()):
        if not line.startswith("{"):
            continue
        try:
            document = json.loads(line)
        except ValueError:
            continue
        if isinstance(document, dict):
            return document
    return None
