"""The six roles, what each may call, and the gate that decides one call.

This module is the roster. It states, in one place, every property that
distinguishes one role from another -- how it runs, who may start it, which
task kinds it executes, its model, effort and turn ceiling, the built-in tools
and tool groups it holds, the Skills it may execute and how many of it may run
at once -- and it compiles that statement at import, against the tool inventory
the SDK/CLI pair was observed to have. A roster that named a tool the pair does
not serve would not fail loudly: `tools=["Nonexistent"]` is accepted and
silently produces no tool, so a typo in a listed tool is a role quietly missing
one, and a typo in a *prohibition* is a prohibition that never applied. The
inventory is what makes both of those a startup error instead.

The second half is the enforcement point, and the separation is the design.
`AgentDefinition.tools` and `ClaudeAgentOptions.allowed_tools` narrow what a
model can see; they are not a boundary, because the permission mode this
runtime uses is `bypassPermissions` and a visible tool under that mode is a
tool that runs. `Gate.decide` is the boundary: it attributes the call to
exactly one role, checks what that role was compiled to hold, and returns a
denial the launch turns into `permissionDecision: "deny"`. That decision is the
one the permission mode cannot overrule, which is why the enforced list lives
here rather than in the options value.

Nothing in this module imports the SDK, touches the network or reads the
environment. It is a pure function of the constants below and the pinned
measurement, so the same decision is reachable from a test, from a review and
from the running child, and `tests/test_agent.py` can keep asserting that
`_launch` is the only module that constructs the SDK.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from importlib import resources
from typing import Any


#: The observed inventory this roster is closed against, and the digest that
#: makes it evidence rather than a list somebody edited. Produced by
#: `tools/probe_tool_inventory.py` against the pair in `_startup.KNOWN_RUNTIME`.
INVENTORY = "measurements/tool-inventory-sdk-0.2.132-cli-2.1.224.json"
INVENTORY_SHA256 = "50a8d08ed1be62b93f7ad5e1a76d127ebd28eaee84aac3dd5d7b7f2cd503f296"

#: How a role runs. A `session` is a top-level query the runtime drives itself,
#: a `subagent` is reached through the delegation tool, and a `renderer` is not
#: a model at all. These are migration 0019's `roles.runs_as` values; the
#: schema and this file are two statements of one roster and must agree.
SESSION = "session"
SUBAGENT = "subagent"
RENDERER = "renderer"
RUNS_AS = (SESSION, SUBAGENT, RENDERER)

#: Who may start a role. `runtime` is this harness; anything else is a role
#: name, and the only role that starts another is the orchestrator.
RUNTIME = "runtime"

#: The task-kind vocabulary of migration 0019. Held here so the compile can
#: check the mapping is total and injective without a database.
TASK_KINDS = ("recon", "hunt", "analyze", "validate", "report")

#: The delegation tool, and the older name of the same tool. The pair announces
#: `Task` in its init frame and has been observed to spell the same tool `Agent`
#: in permission denials, so the gate resolves one to the other before deciding
#: rather than holding a list that half of the CLI's spellings miss.
DELEGATION = "Task"
ALIASES = {"Agent": DELEGATION}

#: The argument that names what a delegation would start.
SUBAGENT_TYPE = "subagent_type"

#: The argument that names what a `Skill` call would execute.
SKILL = "Skill"
SKILL_NAME = "skill"

#: The tables no model-facing tool may write, whatever its group. "Nothing an
#: agent returns is true before promotion", and promotion is a runtime step, so
#: a tool that reached one of these would be an agent writing canonical truth
#: directly. `verdicts` is the one exception and it is not a general one: the
#: validator's closed verdict tool writes it, which `_check_contracts` allows
#: for that direction and for no other.
#:
#: Every name here is a relation the migration corpus creates, and
#: `tests/test_roster.py` holds the list to the corpus. A prohibition naming a
#: table that does not exist is the same defect as a grant naming a tool the
#: pair does not serve: it reads as a closed door and is a door that was never
#: in the wall.
CANONICAL = (
    "entities",
    "domains",
    "hosts",
    "services",
    "applications",
    "endpoints",
    "parameters",
    "technologies",
    "identities",
    "relationships",
    "hypotheses",
    "hypothesis_evidence",
    "findings",
    "finding_evidence",
    "finding_hypotheses",
    "observations",
    "tasks",
    "tests",
    "playbooks",
)

#: The staging tables a proposal is allowed to reach, which is the whole write
#: surface of an executing role. Two rather than one: what the agent claimed
#: and, beside it, every element the runtime refused with the reason it can
#: prove. `proposal.stage` writes both in the same transaction, so declaring
#: only the first would be a contract that describes half of what it does.
STAGING = ("proposals", "proposal_drops")

#: The label prefixes the database assigns, from `label_prefixes` in migration
#: 0015 and the three later migrations that add one. A label is the prefix and
#: a decimal with nothing between them -- `H7`, `EP12`, `R903` -- because that
#: is what `next_label()` returns, and a contract pattern that says otherwise
#: is a gate that denies every label the database has ever issued.
#:
#: Entities are the awkward kind and deliberately so: `entities.label` is keyed
#: off the row's `type`, so "an entity label" is one of eight prefixes rather
#: than one, and there is no prefix that means "entity".
LABEL_PREFIXES = {
    "domain": "DOM",
    "host": "HST",
    "service": "SVC",
    "application": "APP",
    "endpoint": "EP",
    "parameter": "PRM",
    "technology": "TEC",
    "identity": "IDN",
    "hypotheses": "H",
    "observations": "O",
    "receipts": "R",
    "tool_runs": "TR",
    "tasks": "T",
    "agent_runs": "AR",
    "tests": "TST",
    "findings": "F",
    "proposals": "PR",
    "pending_decisions": "D",
    "artifact_references": "AF",
    "callback_interactions": "CB",
}

#: `entities.type`, from migration 0003's check constraint. The eight kinds a
#: Surface row can be, which is also the eight label prefixes an entity label
#: can carry.
ENTITY_TYPES = (
    "application",
    "domain",
    "endpoint",
    "host",
    "identity",
    "parameter",
    "service",
    "technology",
)

#: `hypotheses.status`, from migration 0007's check constraint. Six, and
#: `retest_due` is not among them: migration 0007 calls it "re-entry, not a
#: sixth state" and spells it as a transition back to `testable`.
HYPOTHESIS_STATUSES = (
    "proposed",
    "testable",
    "testing",
    "supported",
    "refuted",
    "inconclusive",
)

#: Names for the runtime's own choice of tenant. Every canonical table is
#: program-scoped and the program is bound in the handler from runtime
#: configuration, so an argument that named one would be the agent choosing
#: which Program it is working in. These are refused wherever they appear,
#: including inside an otherwise opaque payload: a Program identifier is the
#: one thing ticket 19's sixth criterion names by itself, and no element a
#: model proposes has a reason to spell one.
FORBIDDEN_SELECTORS = frozenset(
    {
        "program",
        "program_id",
        "tenant",
        "tenant_id",
        "database",
        "dbname",
        "dsn",
        "connection_string",
    }
)

#: Credential material and raw SQL: names for something the runtime would
#: *act on* if a handler read it. Refused in every argument the runtime
#: interprets, and only there -- see `_forbidden_argument` for why an opaque
#: payload is the one place these are allowed to appear.
FORBIDDEN_INSTRUCTIONS = frozenset(
    {
        "schema",
        "sql",
        "statement",
        "api_key",
        "apikey",
        "token",
        "auth_token",
        "authorization",
        "credential",
        "credentials",
        "password",
        "secret",
    }
)

#: Argument names no model-facing tool may declare, whatever the tool. Checked
#: on the call as well as on the contracts, because a built-in tool has no
#: contract here and still takes arguments.
FORBIDDEN_ARGUMENTS = FORBIDDEN_SELECTORS | FORBIDDEN_INSTRUCTIONS

#: How deep the argument scan goes. A bound rather than a budget: it exists so
#: a pathological document cannot make the gate the slow part of a tool call,
#: and every contract on this surface is far shallower than this.
DEPTH = 8

#: The directions a model-facing tool can have. There is no `commit` among
#: them, and that absence is the point: claiming a Task, promoting a proposal
#: and changing epistemic state are the runtime's, so the strongest thing this
#: surface can do to canonical state is `request` that the runtime do it.
READ = "read"
PROPOSE = "propose"
REQUEST = "request"
JUDGE = "judge"
ACT = "act"
DIRECTIONS = (READ, PROPOSE, REQUEST, JUDGE, ACT)

#: The value shapes an argument may declare. Small and closed, so `kind` is a
#: property the gate checks rather than a note about one.
KINDS = ("string", "integer", "array", "object", "boolean")

#: The rules the gate can refuse under, as the identifiers a denial carries.
#: One per distinguishable finding, because an operator reading a denial should
#: learn which property was violated and not merely that one was.
UNATTRIBUTED = "R-ROLE"
IMPERSONATION = "R-AGENTID"
UNLISTED_TOOL = "R-TOOL"
UNKNOWN_AGENT_TYPE = "R-AGENTTYPE"
SESSION_ROLE = "R-SESSIONROLE"
OVERFLOW = "R-CAP"
FORBIDDEN_ARGUMENT = "R-ARGNAME"
INVALID_ARGUMENT = "R-ARGVALUE"
UNGRANTED_SKILL = "R-SKILL"


class RosterError(ValueError):
    """The roster does not compile, or does not match the observed inventory."""


@dataclass(frozen=True, slots=True)
class Argument:
    """One argument of one model-facing tool, and what constrains its value.

    An argument is authority, so the roster states the shape of every one
    rather than leaving it to the handler. `free_text` is the explicit
    admission that this roster constrains nothing about a value; it is allowed
    only where `OPEN_ARGUMENTS` says why, and never on a tool the validator can
    reach.
    """

    kind: str
    required: bool = False
    enum: tuple[str, ...] = ()
    pattern: str | None = None
    items_pattern: str | None = None
    bounds: tuple[int, int] | None = None
    free_text: bool = False

    @property
    def constrained(self) -> bool:
        return bool(self.enum or self.pattern or self.items_pattern or self.bounds)

    def schema(self) -> dict:
        """This argument as JSON Schema, which is the earliest place it binds.

        The CLI validates a tool call against the served schema before
        `PreToolUse` runs, so a value refused here never reaches the gate and
        never reaches a handler. The gate checks the same properties again
        afterwards, and that is deliberate: the schema is the pair's promise
        and the gate is ours.
        """
        body: dict = {"type": self.kind}
        if self.enum:
            body["enum"] = list(self.enum)
        if self.pattern:
            body["pattern"] = self.pattern
        if self.bounds:
            body["minimum"], body["maximum"] = self.bounds
        if self.items_pattern and self.kind == "object":
            # A pattern over an object's *keys*, which is what a header name is.
            body["propertyNames"] = {"pattern": self.items_pattern}
        elif self.items_pattern:
            body["items"] = {"type": "string", "pattern": self.items_pattern}
        return body


@dataclass(frozen=True, slots=True)
class Contract:
    """One model-facing tool: its group, its direction and its whole surface.

    `reads` and `writes` name canonical and staging tables. They are here so
    the compile can hold a read tool to reading -- a `read` that declares a
    write is a proposal wearing a getter's name -- and so the one tool that
    reaches a canonical table is visible as the one tool that does.
    """

    group: str
    direction: str
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    arguments: Mapping[str, Argument] = field(default_factory=dict)

    def schema(self) -> dict:
        """The closed JSON Schema this tool is served with.

        Closed by `additionalProperties: false`, which is the whole point. Every
        name in `FORBIDDEN_ARGUMENTS` is absent from `properties` -- the compile
        refuses a contract that declares one -- so a call carrying `program_id`
        is rejected by the schema before the handler exists to be confused by
        it, and so is any other invented field a model might try.
        """
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                name: argument.schema() for name, argument in self.arguments.items()
            },
            "required": sorted(
                name for name, argument in self.arguments.items() if argument.required
            ),
        }


@dataclass(frozen=True, slots=True)
class Role:
    """One role, stated completely enough that nothing else has to decide it."""

    name: str
    runs_as: str
    invocable_by: tuple[str, ...]
    task_kinds: tuple[str, ...]
    model: str | None
    effort: str | None
    max_turns: int
    builtin_tools: tuple[str, ...]
    tool_groups: tuple[str, ...]
    skills: tuple[str, ...]
    max_concurrent: int
    #: Migration 0019's column of the same name. True where the role's real
    #: ceiling is the number of free Identity leases rather than the number
    #: above: two hunters sharing one upstream slot is the session mixing the
    #: Identity model exists to prevent. The clamp itself is the scheduler's,
    #: which is the only party that knows how many leases are free.
    clamp_to_identity_leases: bool = False

    @property
    def executes_tasks(self) -> bool:
        """Migration 0019's column: a role holds a task kind, or it does not."""
        return bool(self.task_kinds)

    @property
    def delegated(self) -> bool:
        """Reached through the delegation tool rather than started by the runtime."""
        return self.runs_as == SUBAGENT

    @property
    def rendered(self) -> bool:
        """Not an agent at all: no model, no turn, no tool."""
        return self.runs_as == RENDERER

    @property
    def tools(self) -> frozenset[str]:
        """Everything this role may call, built-in and served, as one set."""
        members = (member for group in self.tool_groups for member in TOOL_GROUPS[group])
        return frozenset(self.builtin_tools) | frozenset(members)

    @property
    def visible_tools(self) -> list[str]:
        """The built-in tools this role's options value offers, in a stable order.

        Visibility, not authority. It is here so the options value and the gate
        are derived from one statement rather than agreeing by inspection, and
        so a role's frame is the role's real surface: a tool the gate would
        deny is not offered, and the model does not spend a turn discovering
        that.
        """
        return sorted(self.builtin_tools)

    def allowed_tools(self, served: Iterable[str]) -> list[str]:
        """This role's tools, intersected with what one launch actually serves.

        Two lists rather than one, because they answer different questions: the
        roster says what the role may call and the launch says what exists to
        be called. Naming a tool no server provides would be an entry that can
        never be exercised, and serving a tool the roster withholds would be a
        tool the gate has to deny at every call instead of one nobody offered.
        """
        return sorted(self.tools.intersection(served))


#: The tool groups. What this partition fixes is which *class* of authority a
#: role may hold. Move a member between groups and a role's authority changes,
#: which is why the group is the unit a role holds rather than the tool.
#:
#: `state.read` and `state.propose` are served today, by `_launch.server`. The
#: rest are contracts the compile enforces and later tickets implement, and a
#: role holding one of those groups holds nothing until then: `allowed_tools`
#: intersects the roster with what the launch actually serves.
TOOL_GROUPS: dict[str, tuple[str, ...]] = {
    "state.read": (
        "mcp__rk2__get_attack_surface",
        "mcp__rk2__get_hypotheses",
        "mcp__rk2__get_evidence",
        "mcp__rk2__get_receipts",
        "mcp__rk2__get_artifact",
    ),
    "state.propose": ("mcp__rk2__submit_mission_result",),
    # Scheduling as the orchestrator sees it, which is not scheduling as the
    # runtime does it. "The runtime decides what may be chosen; the orchestrator
    # decides which; the runtime commits the claim" -- so the model reads a
    # slate and picks from it, and every other member is a request the runtime
    # is free to refuse. There is no `promote` here at all: promotion is the
    # runtime step that turns a raw result into canonical rows, and a model-
    # facing verb for it would be the agent promoting its own conclusions.
    "sched.pick": (
        "mcp__rk2__get_slate",
        "mcp__rk2__pick_task",
        "mcp__rk2__request_validation",
        "mcp__rk2__request_report",
        "mcp__rk2__park_for_human",
    ),
    "net.request": ("mcp__rk2__http_request",),
    "exec.tool_run": ("mcp__rk2__run_tool", "mcp__rk2__run_skill_script"),
    "validate.judge": ("mcp__rk2__get_validation_packet", "mcp__rk2__submit_verdict"),
}

#: Where an unconstrained value is allowed, and why. Two entries, both
#: deliberate: a question whose recipient is a human rather than another agent,
#: and the six element lists of the staging packet, whose contents become
#: canonical only through the runtime's promotion step and whose observations
#: are dropped when the receipt they cite does not exist. Nothing else on this
#: surface takes a value the roster cannot describe.
#:
#: `completion_claim` is deliberately not here. It is the one member of that
#: packet the runtime reads a field out of, so its keys are closed like any
#: other interpreted argument's.
OPEN_ARGUMENTS = {
    "mcp__rk2__park_for_human": ("question",),
    "mcp__rk2__submit_mission_result": (
        "observations",
        "new_entities",
        "relationships",
        "hypotheses",
        "evidence",
        "suggested_tasks",
    ),
}


def _label(*prefixes: str) -> str:
    """The pattern one of these label prefixes and a decimal will match.

    `next_label()` in migration 0002 returns `prefix || counter::text`: no
    separator and no zero padding, so `H7` and `H4096` are both well formed and
    `H-0007` is not a label this system has ever issued. The digit ceiling is
    generous rather than meaningful -- it is there so the pattern is bounded,
    not because a Program is expected to reach nine digits of anything.
    """
    return "^(" + "|".join(sorted(prefixes)) + ")[0-9]{1,9}$"


#: An entity label is any of the eight `entities.type` prefixes, because
#: `assign_entity_label` keys the prefix off the row's type. There is no single
#: prefix that means "entity", which is why this is built rather than written.
_ENTITY_LABEL = _label(*(LABEL_PREFIXES[kind] for kind in ENTITY_TYPES))
_HASH = "^[0-9a-f]{64}$"

#: The largest page a bounded read may be asked for. The handler bounds the
#: response by serialized bytes as well, so this is the coarse half of the
#: ceiling and the byte budget is the half that binds.
_PAGE = (1, 200)

# The view each read comes through, then the canonical relations behind it.
# The child has no database: `packet.compile` runs these on the supervisor's
# `rk2_state` connection before the container starts, and the handler answers
# out of the document that produced. So the first name is the relation actually
# queried and the rest are what it is a view of -- which is the shape
# `get_artifact` already had, and the reason it is the shape here.
CONTRACTS: dict[str, Contract] = {
    "mcp__rk2__get_attack_surface": Contract(
        "state.read",
        READ,
        reads=("v_records", "entities", "domains", "hosts", "services", "applications",
               "endpoints", "parameters", "technologies", "identities"),
        arguments={
            "entity_type": Argument("string", enum=ENTITY_TYPES),
            "limit": Argument("integer", bounds=_PAGE),
        },
    ),
    "mcp__rk2__get_hypotheses": Contract(
        "state.read",
        READ,
        reads=("v_records", "hypotheses", "entities"),
        arguments={
            "subject_label": Argument("string", pattern=_ENTITY_LABEL),
            "status": Argument("string", enum=HYPOTHESIS_STATUSES),
            "limit": Argument("integer", bounds=_PAGE),
        },
    ),
    "mcp__rk2__get_evidence": Contract(
        "state.read",
        READ,
        reads=("v_evidence", "hypothesis_evidence", "finding_evidence", "observations"),
        arguments={
            "hypothesis_label": Argument("string", pattern=_label("H")),
            "finding_label": Argument("string", pattern=_label("F")),
            "limit": Argument("integer", bounds=_PAGE),
        },
    ),
    # Nothing is required, for the reason `get_artifact` requires nothing: the
    # same verb lists and fetches. Labels fetch those Receipts; no labels lists
    # the ones this packet reached. Without the listing a Receipt is reachable
    # only by a label quoted on an evidence edge, so a staged Receipt that no
    # edge cites is a row the child was given and cannot name -- which is the
    # defect this ticket already fixed once, for Artifacts.
    "mcp__rk2__get_receipts": Contract(
        "state.read",
        READ,
        reads=("v_records", "receipts"),
        arguments={
            "receipt_labels": Argument("array", items_pattern=_label("R")),
            "limit": Argument("integer", bounds=_PAGE),
        },
    ),
    # By label, not by hash. `v_artifacts` says why on the view itself: "the
    # hash is reported and is never an argument: a verb taking one would read
    # across Programs whenever the caller could guess the bytes". The store is
    # one content-addressed namespace shared by every Program, so a hash
    # argument is a lookup key an agent can construct without ever having been
    # told the Artifact exists.
    # Nothing is required, because the same verb lists and fetches. A label
    # fetches that Artifact; no label lists the ones this packet reached, which
    # is the only way a child learns a label exists -- the Receipt records it
    # reads carry agent-side hashes, and a hash is not something it may ask by.
    "mcp__rk2__get_artifact": Contract(
        "state.read",
        READ,
        reads=("v_artifacts", "artifact_references", "artifacts"),
        arguments={
            "artifact_label": Argument(
                "string", pattern=_label(LABEL_PREFIXES["artifact_references"])
            ),
            "range": Argument("string", pattern="^[0-9]+-[0-9]+$"),
        },
    ),
    # The six element lists Spec section 13 names -- "proposed Entities,
    # Relationships, Observations, Hypotheses, evidence edges, suggested Tasks
    # and a completion claim". This declaration is the closed set: an element
    # list that is not here is refused by the served schema before any handler
    # sees it, and `proposal_drops.element_path` points into it by these names.
    # `completion_claim` is the one element the runtime reads a field out of --
    # `proposal.Result.completion` clamps `status` to the three words the
    # column takes -- so it is the one element whose keys are closed here. The
    # element lists stay open because a proposal is raw model output and the
    # runtime decides what grounds; the claim is not raw output, it is an
    # answer to a question this schema asked.
    "mcp__rk2__submit_mission_result": Contract(
        "state.propose",
        PROPOSE,
        writes=STAGING,
        arguments={
            "observations": Argument("array", required=True, free_text=True),
            "new_entities": Argument("array", free_text=True),
            "relationships": Argument("array", free_text=True),
            "hypotheses": Argument("array", free_text=True),
            "evidence": Argument("array", free_text=True),
            "suggested_tasks": Argument("array", free_text=True),
            "completion_claim": Argument(
                "object", required=True, items_pattern="^(status|note)$"
            ),
        },
    ),
    "mcp__rk2__get_slate": Contract(
        "sched.pick", READ, reads=("tasks", "task_slate")
    ),
    # A pick, not a claim. The row it writes is the orchestrator's choice; the
    # claim transaction that re-evaluates every filter and moves the Task is the
    # runtime's, and it REFUSES a choice that has gone stale rather than falling
    # through to the next slate entry -- ticket 23's "off-Slate, expired, stale,
    # cross-Program and no-longer-ready choices are refused", which this comment
    # said the opposite of before that ticket built the claim. Falling through
    # is what the runtime does when nobody chose at all.
    "mcp__rk2__pick_task": Contract(
        "sched.pick",
        REQUEST,
        writes=("task_picks",),
        arguments={"task_label": Argument("string", required=True, pattern=_label("T"))},
    ),
    "mcp__rk2__request_validation": Contract(
        "sched.pick",
        REQUEST,
        writes=("validation_queue",),
        arguments={
            "finding_label": Argument("string", required=True, pattern=_label("F"))
        },
    ),
    # No arguments. `report_queue` is one row per Program with a state and a
    # timestamp and nothing to narrow by, so an argument here would be a filter
    # the table cannot honour.
    "mcp__rk2__request_report": Contract(
        "sched.pick",
        REQUEST,
        writes=("report_queue",),
    ),
    "mcp__rk2__park_for_human": Contract(
        "sched.pick",
        REQUEST,
        writes=("pending_decisions",),
        arguments={
            "task_label": Argument("string", required=True, pattern=_label("T")),
            "question_code": Argument(
                "string",
                required=True,
                enum=(
                    "scope_ambiguous",
                    "destructive_action",
                    "third_party_impact",
                    "credential_needed",
                    "policy_unclear",
                ),
            ),
            "question": Argument("string", free_text=True),
        },
    ),
    "mcp__rk2__http_request": Contract(
        "net.request",
        ACT,
        writes=("receipts", "artifacts", "artifact_refs"),
        arguments={
            "method": Argument(
                "string",
                required=True,
                enum=("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"),
            ),
            "url": Argument("string", required=True, pattern="^https?://"),
            "headers": Argument("object", items_pattern="^[A-Za-z][A-Za-z0-9-]{0,63}$"),
            "body_artifact_hash": Argument("string", pattern=_HASH),
            "identity_slot": Argument("string", pattern="^[a-z][a-z0-9_]{0,30}$"),
        },
    ),
    "mcp__rk2__run_tool": Contract(
        "exec.tool_run",
        ACT,
        writes=("tool_runs", "artifacts", "artifact_refs"),
        arguments={
            # An enum, because an open binary name is an unbounded set of
            # programs, and an unbounded set on a tool that starts a process is
            # the arbitrary process creation this surface does not have.
            "tool": Argument(
                "string",
                required=True,
                enum=("ffuf", "nuclei", "sqlmap", "jq", "httpx", "katana"),
            ),
            "argv": Argument("array", required=True, items_pattern="^[^\\x00]{0,512}$"),
            "input_artifact_hashes": Argument("array", items_pattern=_HASH),
        },
    ),
    "mcp__rk2__run_skill_script": Contract(
        "exec.tool_run",
        ACT,
        writes=("tool_runs", "artifacts", "artifact_refs"),
        arguments={
            "skill_name": Argument("string", required=True, pattern="^[a-z0-9][a-z0-9-]{0,63}$"),
            "script": Argument("string", required=True, pattern="^[a-z0-9_.-]{1,64}$"),
            "input_artifact_hashes": Argument("array", items_pattern=_HASH),
        },
    ),
    "mcp__rk2__get_validation_packet": Contract(
        "validate.judge",
        READ,
        reads=("findings", "hypotheses", "tests", "test_runs", "receipts"),
        arguments={
            "finding_label": Argument("string", required=True, pattern=_label("F"))
        },
    ),
    # The one direction that writes a row of its own rather than asking for
    # one. A verdict is the validator's output, not an edit to the Finding it
    # is about: what the Finding's status becomes is still the runtime's step,
    # taken from this row and from a holding replay of the Finding's own Test.
    "mcp__rk2__submit_verdict": Contract(
        "validate.judge",
        JUDGE,
        writes=("verdicts",),
        arguments={
            "finding_label": Argument("string", required=True, pattern=_label("F")),
            "verdict": Argument(
                "string", required=True, enum=("confirmed", "refuted", "insufficient")
            ),
            "failed_assertion_ids": Argument("array", items_pattern="^A-[0-9]{3}$"),
        },
    ),
}

#: Built-in tools no role holds, each with the reason it holds none. Together
#: with the roles below this partitions the observed inventory exactly: a tool
#: that is neither granted nor refused here is a tool this roster has not
#: classified, and the compile refuses rather than defaulting it either way.
FORBIDDEN_BUILTINS: dict[str, str] = {
    "Bash": "a shell is arbitrary process creation; exec.tool_run is the enumerated form",
    "Read": "a path argument reaches the container's own credential file and its skills",
    "Write": "an agent that writes files can rewrite a skill or a compiled view",
    "Edit": "same",
    "NotebookEdit": "same",
    "WebFetch": "a second egress path whose output carries no proxy receipt",
    "WebSearch": "egress that never enters the container's network at all",
    "Workflow": "step-list execution is a workflow engine this harness does not have",
    "ReportFindings": "reporting authority belongs to the deterministic renderer",
    "TaskCreate": "task lifecycle belongs to the scheduler",
    "TaskUpdate": "same",
    "TaskStop": "same",
    "TaskGet": "same",
    "TaskList": "same",
    "TaskOutput": "same",
    "CronCreate": "scheduling authority belongs to the runtime",
    "CronDelete": "same",
    "CronList": "same",
    "ScheduleWakeup": "the harness has no auto-wake",
    "SendMessage": "human and inter-agent contact is the pending-decision path",
    "DesignSync": "no such surface in this system",
    "EnterWorktree": "filesystem topology is the runtime's, not the model's",
    "ExitWorktree": "same",
    "ToolSearch": "every schema is materialised at turn one so the frame is the role's real surface",
}

ROLES: dict[str, Role] = {
    "orchestrator": Role(
        name="orchestrator",
        runs_as=SESSION,
        invocable_by=(RUNTIME,),
        # It picks tasks; it never holds one. Migration 0019 says the same
        # thing with an empty row set in `role_task_kinds`.
        task_kinds=(),
        model="opus",
        effort="xhigh",
        max_turns=400,
        builtin_tools=(DELEGATION,),
        # No net.request and no exec.tool_run: the orchestrator never touches a
        # target. No Skill: a technique is executed by the role that holds the
        # task, and the SDK reads an empty skill list as every skill, so the
        # tool is absent rather than granted with a bound that does not bind.
        tool_groups=("state.read", "sched.pick"),
        skills=(),
        max_concurrent=1,
    ),
    "recon": Role(
        name="recon",
        runs_as=SUBAGENT,
        invocable_by=("orchestrator",),
        task_kinds=("recon",),
        model="opus",
        effort="medium",
        max_turns=60,
        builtin_tools=(SKILL,),
        tool_groups=("state.read", "state.propose", "net.request", "exec.tool_run"),
        skills=("recon-surface", "recon-endpoints"),
        # Two recons on one surface collide on the same deduplication cell.
        max_concurrent=1,
    ),
    "web_hunter": Role(
        name="web_hunter",
        runs_as=SUBAGENT,
        invocable_by=("orchestrator",),
        task_kinds=("hunt",),
        model="opus",
        effort="high",
        max_turns=120,
        builtin_tools=(SKILL,),
        tool_groups=("state.read", "state.propose", "net.request", "exec.tool_run"),
        skills=("access-control", "injection", "business-logic", "auth-session"),
        max_concurrent=2,
        # Clamped further at run time by the number of free identity leases:
        # two hunters sharing one upstream slot is the session mixing that the
        # identity model exists to prevent. Migration 0019 carries the same
        # `true`, and the clamp itself is the scheduler's.
        clamp_to_identity_leases=True,
    ),
    "js_analyst": Role(
        name="js_analyst",
        runs_as=SUBAGENT,
        invocable_by=("orchestrator",),
        task_kinds=("analyze",),
        model="opus",
        effort="high",
        max_turns=80,
        builtin_tools=(SKILL,),
        # No net.request: an analyst that fetches is a hunter with the wrong
        # quota. Its inputs are content-addressed artifacts, which arrive
        # through state.read and are analysed through exec.tool_run, so the
        # record of what it looked at is a row rather than a claim.
        tool_groups=("state.read", "state.propose", "exec.tool_run"),
        skills=("js-bundle-analysis", "source-map-recovery"),
        max_concurrent=2,
    ),
    "validator": Role(
        name="validator",
        runs_as=SESSION,
        invocable_by=(RUNTIME,),
        task_kinds=("validate",),
        model="opus",
        # A validator false negative costs more than the tokens the effort buys.
        effort="max",
        max_turns=30,
        # Not one built-in, and not one state read either: the packet is its
        # whole world, and a second tool is a second thing in it.
        builtin_tools=(),
        tool_groups=("validate.judge",),
        # A Skill is technique. The validator judges.
        skills=(),
        max_concurrent=1,
    ),
    "reporter": Role(
        name="reporter",
        runs_as=RENDERER,
        invocable_by=(RUNTIME,),
        task_kinds=("report",),
        # Not an agent. Migration 0019 refuses a renderer that spent a token.
        model=None,
        effort=None,
        max_turns=0,
        builtin_tools=(),
        tool_groups=(),
        skills=(),
        max_concurrent=1,
    ),
}

#: A cap across roles as well as within them. The per-role numbers can each be
#: under their own ceiling while the sum is more concurrent work than one
#: program's budget or one machine's containers can carry.
#:
#: The default, and only the default -- which is why it is not named for the
#: cap. The number that governs a run is
#: `scheduler_weights.max_concurrent_subagents`, a column on the one active
#: weights row an operator versions for the whole scheduler, which the runtime
#: reads with the claim and hands to `Gate`. This roster is a compile-time
#: document and cannot state a runtime value, so what it states is the schema's
#: own `DEFAULT 3`, held equal to it by `SchemaAgreementTest`.
DEFAULT_SUBAGENTS = 3


@dataclass(frozen=True, slots=True)
class Call:
    """One tool call, as much of it as a decision needs.

    `agent_id` and `agent_type` are the pair the CLI puts on a tool-lifecycle
    hook when the call came from inside a delegated agent, and their absence is
    how a call from the session itself is recognised. They are taken together:
    one without the other is a call this runtime cannot attribute, which is a
    denial rather than a guess.
    """

    tool: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    agent_type: str | None = None
    ticket: str | None = None


@dataclass(frozen=True, slots=True)
class Denial:
    """Why one call was refused, in the words an operator and a model both get."""

    rule: str
    tool: str
    role: str | None
    reason: str

    def as_dict(self) -> dict[str, str | None]:
        return {"rule": self.rule, "tool": self.tool, "role": self.role, "reason": self.reason}

    def __str__(self) -> str:
        return f"{self.rule}: {self.reason}"


class Gate:
    """The enforcement point for one session, and the counter behind it.

    One instance per Agent run. It holds the session's role, the agent
    identities it has seen and how many delegations are outstanding, and it is
    deliberately the only thing in this runtime that can answer "may this
    call happen": the options value narrows what is offered, and this decides
    what is allowed.

    Every decision is recorded. A denial that were merely returned would leave
    the run's evidence saying a tool was not served without saying it was
    refused, and the difference between "the model did not ask" and "the model
    asked and was refused" is most of what this gate is for.

    `subagent_cap` is the cross-role cap, taken here rather than read from a
    constant: it is `scheduler_weights.max_concurrent_subagents`, which the
    runtime read to claim the Task and passes on, so an operator who raises it
    raises what the scheduler offers and what this refuses in one edit. What
    this counts is not what that column counts on the scheduler's side, and the
    two are worth keeping apart: this is the delegations outstanding inside one
    orchestrator session, which is the SDK's concurrency and this machine's
    containers, while the scheduler counts `claimed` and `running` subagent
    Tasks across the Program, which outlives any one session. This population
    is a subset of that one, which is why one number bounds both.
    """

    def __init__(self, role: str, subagent_cap: int = DEFAULT_SUBAGENTS) -> None:
        if role not in ROLES:
            raise RosterError(f"{role} is not a roster role")
        # The schema's own `CHECK (max_concurrent_subagents >= 1)`, restated
        # where the number is spent. A session that may hold no delegation is
        # not a stricter cap, it is a role that cannot do its work at all, and
        # a run started under one would spend its turns being refused.
        if subagent_cap < 1:
            raise RosterError(
                f"{subagent_cap} is not a concurrency a session can run at"
            )
        self.role = ROLES[role]
        self.subagent_cap = subagent_cap
        self.denials: list[Denial] = []
        self._bindings: dict[str, str] = {}
        self._outstanding: dict[str, str] = {}
        self._admitted = 0

    @property
    def outstanding(self) -> int:
        """How many delegations this session has admitted and not released."""
        return len(self._outstanding)

    def decide(self, call: Call) -> Denial | None:
        """Nothing when the call is within the caller's compiled authority."""
        denial = self._decide(call)
        if denial is not None:
            self.denials.append(denial)
        return denial

    def bind(self, agent_id: str, agent_type: str) -> Denial | None:
        """Record what a started agent is, or refuse to record it twice as two.

        The CLI announces a delegated agent before its first tool call, which
        is what makes `agent_id` an attribution rather than a claim: a later
        call arriving with the same identity and a different type is denied
        against this record instead of being believed.
        """
        recorded = self._bindings.setdefault(agent_id, agent_type)
        if recorded != agent_type:
            denial = _impersonation(DELEGATION, agent_id, recorded, agent_type)
            self.denials.append(denial)
            return denial
        return None

    def release(self, ticket: str) -> None:
        """Give back one admitted delegation slot. Idempotent, by key."""
        self._outstanding.pop(ticket, None)

    def _decide(self, call: Call) -> Denial | None:
        role, denial = self._caller(call)
        if denial is not None:
            return denial
        assert role is not None

        tool = ALIASES.get(call.tool, call.tool)
        if tool not in role.tools:
            return Denial(
                UNLISTED_TOOL, tool, role.name, f"{role.name} was not granted {tool}"
            )

        forbidden = _forbidden_argument(call.arguments, _opaque(tool))
        if forbidden is not None:
            return Denial(
                FORBIDDEN_ARGUMENT,
                tool,
                role.name,
                f"no tool on this surface takes {forbidden}",
            )

        # The contract is the tool's whole surface, so a call that does not fit
        # it is refused here rather than by the handler. Without this the enum
        # on `run_tool.tool` would be a description of the handler's own check,
        # and a roster that only describes is a roster the gate does not carry.
        fault = _argument_fault(tool, call.arguments)
        if fault is not None:
            return Denial(INVALID_ARGUMENT, tool, role.name, fault)

        if tool == SKILL:
            return self._skill(role, call)
        if tool == DELEGATION:
            return self._delegation(role, call)
        return None

    def _caller(self, call: Call) -> tuple[Role | None, Denial | None]:
        """Which role is making this call, or why it belongs to no single one."""
        identity, kind = call.agent_id, call.agent_type
        if identity is None and kind is None:
            return self.role, None
        if identity is None or kind is None:
            return None, Denial(
                UNATTRIBUTED,
                call.tool,
                None,
                "a delegated call carries both an agent id and an agent type",
            )
        if kind not in ROLES or not ROLES[kind].delegated:
            return None, Denial(
                UNATTRIBUTED,
                call.tool,
                None,
                f"{kind} is not a role this runtime delegates to",
            )
        # An identity the runtime never saw start is a claim, not an
        # attribution, whatever type it carries. `SubagentStart` is what makes
        # the difference, so a call that arrives before one is refused rather
        # than believed and recorded.
        recorded = self._bindings.get(identity)
        if recorded is None:
            return None, Denial(
                UNATTRIBUTED,
                call.tool,
                None,
                f"agent {identity} called before the runtime saw it start",
            )
        if recorded != kind:
            return None, _impersonation(call.tool, identity, recorded, kind)
        return ROLES[kind], None

    def _skill(self, role: Role, call: Call) -> Denial | None:
        """A Skill call is bounded by the role's grants, not by the tool."""
        name = call.arguments.get(SKILL_NAME)
        if name not in role.skills:
            return Denial(
                UNGRANTED_SKILL,
                SKILL,
                role.name,
                f"{role.name} was not granted the skill {name!r}",
            )
        return None

    def _delegation(self, role: Role, call: Call) -> Denial | None:
        """Who may be started, by whom, and how many at once."""
        wanted = call.arguments.get(SUBAGENT_TYPE)
        target = ROLES.get(wanted) if isinstance(wanted, str) else None
        if target is None:
            return Denial(
                UNKNOWN_AGENT_TYPE,
                DELEGATION,
                role.name,
                f"{wanted!r} is not a roster role",
            )
        if not target.delegated:
            return Denial(
                SESSION_ROLE,
                DELEGATION,
                role.name,
                f"{target.name} runs as a {target.runs_as} and is started by the runtime",
            )
        if role.name not in target.invocable_by:
            return Denial(
                UNKNOWN_AGENT_TYPE,
                DELEGATION,
                role.name,
                f"{role.name} may not start {target.name}",
            )
        return self._admit(role, target, call)

    def _admit(self, role: Role, target: Role, call: Call) -> Denial | None:
        """Count the delegation in, or refuse it because the count is at cap."""
        ticket = call.ticket
        if ticket is not None and ticket in self._outstanding:
            return None
        running = sum(1 for held in self._outstanding.values() if held == target.name)
        if running >= target.max_concurrent:
            return Denial(
                OVERFLOW,
                DELEGATION,
                role.name,
                f"{target.name} is at its concurrency of {target.max_concurrent}",
            )
        if self.outstanding >= self.subagent_cap:
            return Denial(
                OVERFLOW,
                DELEGATION,
                role.name,
                f"this session is at its concurrency of {self.subagent_cap}",
            )
        # A monotonic key rather than the current count: two admissions either
        # side of a release would otherwise be counted once, and the ceiling
        # would be one delegation wider than it says.
        self._admitted += 1
        self._outstanding[ticket or f"{target.name}#{self._admitted}"] = target.name
        return None


def _forbidden_argument(arguments: Any, opaque: Collection[str] = ()) -> str | None:
    """The first argument name on this surface that may not exist, at any depth.

    Nested rather than top-level because the names that matter are the ones a
    handler would read, and a handler reads a member of an object as readily as
    it reads a top-level key.

    `opaque` names the arguments the contract declared `free_text`, and inside
    those only `FORBIDDEN_SELECTORS` is refused. The distinction is what the
    runtime does with the value. An interpreted argument named `password` is a
    credential being handed to a tool. The same name inside a proposal payload
    is an agent *reporting* one -- an Observation of an exposed credential is
    the core output of a bug bounty hunter, and scanning the payload for the
    word would make the one finding class this harness exists to produce the
    one it structurally cannot submit. A Program identifier stays refused
    everywhere, because no element a model proposes has a reason to name a
    tenant and ticket 19's sixth criterion names that case by itself.

    Nothing is opaque unless a contract said so, so a built-in tool -- which
    has no contract here -- is scanned in full.
    """
    if not isinstance(arguments, Mapping):
        return _scan(arguments, FORBIDDEN_ARGUMENTS, 1)
    for name, value in arguments.items():
        if isinstance(name, str) and name.strip().lower() in FORBIDDEN_ARGUMENTS:
            return name
        within = FORBIDDEN_SELECTORS if name in opaque else FORBIDDEN_ARGUMENTS
        found = _scan(value, within, 1)
        if found is not None:
            return found
    return None


def _scan(value: Any, names: Collection[str], depth: int) -> str | None:
    """The first key of this document that is one of `names`.

    The depth bound is not a correctness limit: every contract on this surface
    is two levels deep at most, so a document deeper than the bound is already
    not a call any contract describes. It exists so a pathological payload
    cannot make the gate the slow part of a tool call.
    """
    if depth >= DEPTH:
        return None
    if isinstance(value, Mapping):
        for name, inner in value.items():
            if isinstance(name, str) and name.strip().lower() in names:
                return name
            found = _scan(inner, names, depth + 1)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = _scan(item, names, depth + 1)
            if found is not None:
                return found
    return None


def _impersonation(tool: str, identity: str, recorded: str, claimed: str) -> Denial:
    """One sentence for one finding, wherever the gate reaches it.

    `bind` sees it when `SubagentStart` announces the same identity twice as
    two roles; `_caller` sees it when a call arrives claiming a role that
    identity was not started as. It is the same violation seen from two hooks,
    so it is one denial with one wording and one role field.
    """
    return Denial(
        IMPERSONATION,
        tool,
        recorded,
        f"agent {identity} was started as {recorded} and now claims {claimed}",
    )


def _opaque(tool: str) -> frozenset[str]:
    """Which of this tool's arguments the roster declared it constrains nothing about.

    A built-in tool has no contract here, so nothing of it is opaque and the
    name scan runs over the whole call.
    """
    contract = CONTRACTS.get(tool)
    if contract is None:
        return frozenset()
    return frozenset(
        name for name, argument in contract.arguments.items() if argument.free_text
    )


def _argument_fault(tool: str, arguments: Mapping[str, Any]) -> str | None:
    """The first way this call does not fit the contract, or nothing.

    A built-in tool has no contract here and is not constrained by this: `Task`
    and `Skill` carry their own rules, and every other built-in a role holds is
    already the empty set.
    """
    contract = CONTRACTS.get(tool)
    if contract is None:
        return None
    for name in arguments:
        if name not in contract.arguments:
            return f"{tool} takes no argument named {name!r}"
    for name, argument in contract.arguments.items():
        if name not in arguments:
            if argument.required:
                return f"{tool} requires {name}"
            continue
        fault = _value_fault(argument, arguments[name])
        if fault is not None:
            return f"{tool}.{name} {fault}"
    return None


def _value_fault(argument: Argument, value: Any) -> str | None:
    """One value against one argument's declared shape."""
    if not _is_kind(argument.kind, value):
        return f"is not {argument.kind}"
    if argument.enum and value not in argument.enum:
        return f"is not one of: {', '.join(argument.enum)}"
    if argument.pattern is not None and not re.search(argument.pattern, value):
        return f"does not match {argument.pattern}"
    if argument.items_pattern is not None:
        # An object's members are constrained by their names -- a header set is
        # the case that matters, and its names are what the roster can bound.
        members = value.keys() if isinstance(value, Mapping) else value
        for member in members:
            if not isinstance(member, str) or not re.search(argument.items_pattern, member):
                return f"contains {member!r}, which does not match {argument.items_pattern}"
    if argument.bounds is not None:
        low, high = argument.bounds
        measure = value if isinstance(value, int) else len(value)
        if not low <= measure <= high:
            return f"is outside {low}-{high}"
    return None


def _is_kind(kind: str, value: Any) -> bool:
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        # A bool is an int in Python and is not one here: a flag arriving where
        # a count belongs is the confusion this check exists to catch.
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "string":
        return isinstance(value, str)
    if kind == "array":
        return isinstance(value, (list, tuple))
    return isinstance(value, Mapping)


def inventory() -> Mapping[str, Any]:
    """The observed tool inventory, read once and checked against its digest."""
    return _INVENTORY


def granted_builtins() -> frozenset[str]:
    """Every built-in tool some role holds. The other half of the partition."""
    return frozenset(tool for role in ROLES.values() for tool in role.builtin_tools)


def _load_inventory() -> Mapping[str, Any]:
    data = resources.files(__package__).joinpath(INVENTORY).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != INVENTORY_SHA256:
        raise RosterError(f"tool inventory digest changed: {digest}")
    try:
        measured = json.loads(data)
    except json.JSONDecodeError as error:
        raise RosterError(f"tool inventory is not JSON: {error}") from error
    if not isinstance(measured, Mapping) or measured.get("schema_version") != 1:
        raise RosterError("unsupported tool inventory schema_version")
    for key in ("builtin_tools", "agent_types", "effort_levels", "permission_modes"):
        value = measured.get(key)
        if not isinstance(value, list) or not all(isinstance(name, str) for name in value):
            raise RosterError(f"tool inventory {key} must be an array of strings")
    models = measured.get("models")
    if not isinstance(models, Mapping) or not all(
        isinstance(alias, str) and isinstance(resolved, str)
        for alias, resolved in models.items()
    ):
        raise RosterError("tool inventory models must be an object of strings")
    return measured


def _check_inventory(measured: Mapping[str, Any]) -> None:
    """Every built-in name this roster uses is one the pair actually serves.

    Both halves matter and they fail differently. A role naming a tool the pair
    does not serve silently holds one tool fewer than the roster says, because
    an unknown name in `tools` is dropped rather than rejected. A prohibition
    naming one is worse: it reads as a closed door and is a door that was never
    in the wall.
    """
    observed = set(measured["builtin_tools"])
    granted = granted_builtins()
    forbidden = set(FORBIDDEN_BUILTINS)

    overlap = sorted(granted & forbidden)
    if overlap:
        raise RosterError(f"granted and forbidden at once: {overlap}")
    unknown = sorted((granted | forbidden) - observed)
    if unknown:
        raise RosterError(f"not in the observed inventory: {unknown}")
    unclassified = sorted(observed - granted - forbidden)
    if unclassified:
        raise RosterError(f"observed but neither granted nor forbidden: {unclassified}")
    if not all(reason for reason in FORBIDDEN_BUILTINS.values()):
        raise RosterError("every forbidden built-in states why it is forbidden")

    for alias, target in ALIASES.items():
        if target not in observed:
            raise RosterError(f"the alias {alias} resolves to the unobserved {target}")
        if alias in observed:
            raise RosterError(f"{alias} is served under its own name and is not an alias")

    shared = sorted(set(measured["agent_types"]) & set(ROLES))
    if shared:
        raise RosterError(f"roster roles collide with built-in agent types: {shared}")


def _check_roles(measured: Mapping[str, Any]) -> None:
    """Each role, against the shape its `runs_as` and the SDK's vocabulary allow."""
    efforts = set(measured["effort_levels"])
    models = measured["models"]
    for name, role in ROLES.items():
        if name != role.name:
            raise RosterError(f"{name} is filed under another name")
        if role.runs_as not in RUNS_AS:
            raise RosterError(f"{name}: {role.runs_as} is not a way to run")
        if not role.invocable_by:
            raise RosterError(f"{name}: a role nothing may start is a role that never runs")
        for caller in role.invocable_by:
            if caller != RUNTIME and caller not in ROLES:
                raise RosterError(f"{name}: {caller} is neither the runtime nor a role")
        if role.delegated and RUNTIME in role.invocable_by:
            raise RosterError(f"{name}: a subagent is reached through the delegation tool")
        if not role.delegated and tuple(role.invocable_by) != (RUNTIME,):
            raise RosterError(f"{name}: only the runtime starts a {role.runs_as}")
        if role.max_concurrent < 1:
            raise RosterError(f"{name}: a role runs at least once at a time")
        for group in role.tool_groups:
            if group not in TOOL_GROUPS:
                raise RosterError(f"{name}: {group} is not a tool group")
        if len(set(role.tool_groups)) != len(role.tool_groups):
            raise RosterError(f"{name}: a group is granted twice")

        if role.rendered:
            # Not an agent. The schema says the same with a check constraint
            # that refuses a renderer holding a model, an effort or a token.
            if (role.model, role.effort, role.max_turns) != (None, None, 0):
                raise RosterError(f"{name}: a renderer runs no model, no effort and no turn")
            if role.builtin_tools or role.tool_groups or role.skills:
                raise RosterError(f"{name}: a renderer holds no tool and no skill")
            continue
        # An alias, against what the pair was measured to resolve it to. A role
        # naming one the pair does not know would still start -- on some other
        # model, and without saying which.
        if role.model not in models:
            raise RosterError(f"{name}: {role.model} is not a model alias this pair resolves")
        if role.effort not in efforts:
            raise RosterError(f"{name}: {role.effort} is not an effort this SDK accepts")
        if role.max_turns < 1:
            raise RosterError(f"{name}: a model session takes at least one turn")
        if SKILL in role.builtin_tools and not role.skills:
            # An empty grant list is read as every skill, so a role holding the
            # tool with nothing granted has the widest surface of all.
            raise RosterError(f"{name}: holds Skill with no skill granted")
        if role.skills and SKILL not in role.builtin_tools:
            raise RosterError(f"{name}: was granted skills it has no tool to execute")
        if DELEGATION in role.builtin_tools and role.runs_as != SESSION:
            raise RosterError(f"{name}: only a session delegates")


def _check_task_kinds() -> None:
    """The role-to-kind mapping is the schema's: total on kinds, injective."""
    owner: dict[str, str] = {}
    for name, role in ROLES.items():
        for kind in role.task_kinds:
            if kind not in TASK_KINDS:
                raise RosterError(f"{name}: {kind} is not a task kind")
            if kind in owner:
                raise RosterError(f"{kind} is executed by both {owner[kind]} and {name}")
            owner[kind] = name
    orphaned = sorted(set(TASK_KINDS) - set(owner))
    if orphaned:
        raise RosterError(f"task kinds no role executes: {orphaned}")


def _check_contracts() -> None:
    """Every group member has a contract, and every contract keeps its promises.

    The four rules that run through the surface are checked here rather than
    described: nothing takes a program or a credential, a read writes nothing,
    no direction reaches a canonical table, and nothing the validator can reach
    takes a value this roster does not constrain. The last is what keeps a
    validator blind -- there is no field on its surface that a hunter's sentence
    would fit in, so the packet builder is not the only thing standing between
    the two.
    """
    members = [member for group in TOOL_GROUPS.values() for member in group]
    if len(set(members)) != len(members):
        raise RosterError("a tool is a member of two groups")
    if set(members) != set(CONTRACTS):
        difference = sorted(set(members) ^ set(CONTRACTS))
        raise RosterError(f"groups and contracts disagree about: {difference}")

    for name, contract in CONTRACTS.items():
        if TOOL_GROUPS.get(contract.group) is None or name not in TOOL_GROUPS[contract.group]:
            raise RosterError(f"{name}: is not a member of the group it declares")
        if contract.direction not in DIRECTIONS:
            raise RosterError(f"{name}: {contract.direction} is not a direction")
        if contract.direction == READ and contract.writes:
            raise RosterError(f"{name}: a read tool that writes is a proposal named as a getter")
        if contract.direction == PROPOSE and (
            "proposals" not in contract.writes or not set(contract.writes) <= set(STAGING)
        ):
            raise RosterError(f"{name}: a proposal writes staging and nothing else")
        if contract.direction == REQUEST and not contract.writes:
            raise RosterError(f"{name}: a request writes the row the runtime reads")
        if contract.direction == JUDGE and set(contract.writes) != {"verdicts"}:
            raise RosterError(f"{name}: a judgement writes its verdict and nothing else")
        if contract.direction == ACT and not contract.writes:
            raise RosterError(f"{name}: an act that records nothing leaves no receipt")
        # Nothing an agent returns is true before promotion, and promotion is a
        # runtime step. A model-facing tool that wrote one of these would be the
        # agent writing canonical truth directly, whatever its group says.
        canonical = sorted(set(contract.writes) & set(CANONICAL))
        if canonical:
            raise RosterError(f"{name}: writes canonical state directly: {canonical}")
        if "verdicts" in contract.writes and contract.direction != JUDGE:
            raise RosterError(f"{name}: a verdict row is a judgement's and no other's")
        for argument_name, argument in contract.arguments.items():
            _check_argument(name, contract, argument_name, argument)


def _check_argument(tool: str, contract: Contract, name: str, argument: Argument) -> None:
    if name.strip().lower() in FORBIDDEN_ARGUMENTS:
        raise RosterError(f"{tool}: no contract may declare {name}")
    if argument.kind not in KINDS:
        raise RosterError(f"{tool}.{name}: {argument.kind} is not a value shape")
    if argument.free_text == argument.constrained:
        raise RosterError(f"{tool}.{name}: is either constrained or declared unconstrained")
    if argument.free_text and name not in OPEN_ARGUMENTS.get(tool, ()):
        raise RosterError(f"{tool}.{name}: an unconstrained argument states why it is one")
    if argument.free_text and contract.group == "validate.judge":
        raise RosterError(f"{tool}.{name}: the validator's surface takes no free text")
    for expression in (argument.pattern, argument.items_pattern):
        if expression is not None:
            try:
                re.compile(expression)
            except re.error as error:
                raise RosterError(f"{tool}.{name}: {error}") from error
    if argument.bounds is not None and argument.bounds[0] > argument.bounds[1]:
        raise RosterError(f"{tool}.{name}: bounds are the wrong way round")


def _check_authority() -> None:
    """The three sentences the ticket makes about who holds what, as checks."""
    orchestrator = ROLES["orchestrator"]
    if not {"sched.pick", "state.read"}.issubset(orchestrator.tool_groups):
        raise RosterError("the orchestrator schedules and reads state")
    if {"net.request", "exec.tool_run"} & set(orchestrator.tool_groups):
        raise RosterError("the orchestrator does not contact targets")
    if orchestrator.skills or SKILL in orchestrator.builtin_tools:
        raise RosterError("the orchestrator executes no technique")

    validator = ROLES["validator"]
    if tuple(validator.tool_groups) != ("validate.judge",) or validator.builtin_tools:
        raise RosterError("the validator holds only its judgement surface")

    # Scheduling stays runtime authority, which here means one role that never
    # executes a task does the choosing and the executing roles do not.
    for name, role in ROLES.items():
        if "sched.pick" in role.tool_groups and role.executes_tasks:
            raise RosterError(f"{name}: executes tasks and chooses which tasks run")
        if "state.propose" in role.tool_groups and "sched.pick" in role.tool_groups:
            raise RosterError(f"{name}: proposes results and schedules the work they justify")


def _compile() -> Mapping[str, Any]:
    """Run every check once, at import, so a bad roster is not a running one."""
    measured = _load_inventory()
    _check_inventory(measured)
    _check_roles(measured)
    _check_task_kinds()
    _check_contracts()
    _check_authority()
    return measured


_INVENTORY = _compile()
