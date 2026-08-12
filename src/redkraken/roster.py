"""The six roles, what each may call, and the gate that decides one call.

This module is the roster. It states, in one place, every property that
distinguishes one role from another -- how it runs, who may start it, which
task kinds it executes, its model, effort and turn ceiling, the built-in tools
and capability groups it holds, the Skills it may execute and how many of it
may run at once -- and it compiles that statement at import, against the tool
inventory the SDK/CLI pair was observed to have. A roster that named a tool the
pair does not serve would not fail loudly: `tools=["Nonexistent"]` is accepted
and silently produces no tool, so a typo in a grant is a role quietly missing a
capability, and a typo in a *prohibition* is a prohibition that never applied.
The inventory is what makes both of those a startup error instead.

The second half is the enforcement point, and the separation is the design.
`AgentDefinition.tools` and `ClaudeAgentOptions.allowed_tools` narrow what a
model can see; they are not a boundary, because the permission mode this
runtime uses is `bypassPermissions` and a visible tool under that mode is a
tool that runs. `Gate.decide` is the boundary: it attributes the call to
exactly one role, checks that role's compiled grants, and returns a denial the
launch turns into `permissionDecision: "deny"`. That decision is the one the
permission mode cannot overrule, which is why the allowlist lives here rather
than in the options value.

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
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from importlib import resources
from typing import Any


#: The observed inventory this roster is closed against, and the digest that
#: makes it evidence rather than a list somebody edited. Produced by
#: `tools/probe_tool_inventory.py` against the pair in `_startup.KNOWN_RUNTIME`.
INVENTORY = "measurements/tool-inventory-sdk-0.2.132-cli-2.1.224.json"
INVENTORY_SHA256 = "eba17fab0d3b34e90760c74a4df3fe99cb454a4b7a3bca8d2e8c8b14815ee8ba"

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
#: rather than holding an allowlist that half of the CLI's spellings miss.
DELEGATION = "Task"
ALIASES = {"Agent": DELEGATION}

#: The argument that names what a delegation would start.
SUBAGENT_TYPE = "subagent_type"

#: The argument that names what a `Skill` call would execute.
SKILL = "Skill"
SKILL_NAME = "skill"

#: Argument names no model-facing tool may carry, whatever the tool. Program
#: selection is the first: every canonical table is program-scoped and the
#: program is bound in the handler from runtime configuration, so an argument
#: that named one would be the agent choosing its own tenant. The rest are
#: credential material and raw SQL, which have no legitimate spelling on this
#: surface. Checked on the call as well as on the contracts, because a built-in
#: tool has no contract here and still takes arguments.
FORBIDDEN_ARGUMENTS = frozenset(
    {
        "program",
        "program_id",
        "tenant",
        "tenant_id",
        "database",
        "dbname",
        "schema",
        "dsn",
        "connection_string",
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

#: How deep the argument scan goes. A bound rather than a budget: it exists so
#: a pathological document cannot make the gate the slow part of a tool call,
#: and every contract on this surface is far shallower than this.
DEPTH = 8

#: The rules the gate can refuse under, as the identifiers a denial carries.
#: One per distinguishable finding, because an operator reading a denial should
#: learn which property was violated and not merely that one was.
UNATTRIBUTED = "R-ROLE"
IMPERSONATION = "R-AGENTID"
UNLISTED_TOOL = "R-TOOL"
UNKNOWN_AGENT_TYPE = "R-AGENTTYPE"
SESSION_ROLE = "R-SESSIONROLE"
OVERFLOW = "R-CAP"
FORBIDDEN_ARGUMENT = "R-PROGRAM"
UNGRANTED_SKILL = "R-SKILL"


class RosterError(ValueError):
    """The roster does not compile, or does not match the observed inventory."""


@dataclass(frozen=True, slots=True)
class Argument:
    """One argument of one model-facing tool, and what constrains its value.

    An argument is a capability, so the roster states the shape of every one
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

    @property
    def executes_tasks(self) -> bool:
        """Migration 0019's column: a role holds a task kind, or it does not."""
        return bool(self.task_kinds)

    @property
    def tools(self) -> frozenset[str]:
        """Everything this role may call, built-in and served, as one set."""
        members = (member for group in self.tool_groups for member in TOOL_GROUPS[group])
        return frozenset(self.builtin_tools) | frozenset(members)


#: The capability groups. What this partition fixes is which *class* of
#: capability a role may hold; ticket 19 owns the handlers behind the names.
#: Move a member between groups and a role's authority changes, which is why
#: the group is the unit a role is granted rather than the tool.
TOOL_GROUPS: dict[str, tuple[str, ...]] = {
    # The one tool `_launch` serves today: it reports that the runtime's tool
    # surface opened, and nothing else. Ticket 19 replaces it with the bounded
    # state reads, at which point this group stops existing.
    "runtime.ready": ("mcp__rk2__ready",),
    "state.read": (
        "mcp__rk2__get_attack_surface",
        "mcp__rk2__get_hypotheses",
        "mcp__rk2__get_evidence",
        "mcp__rk2__get_receipts",
        "mcp__rk2__get_artifact",
    ),
    "state.propose": ("mcp__rk2__submit_mission_result",),
    "sched.commit": (
        "mcp__rk2__offer_slate",
        "mcp__rk2__claim_task",
        "mcp__rk2__promote",
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
#: and the staging packet, whose contents become canonical only through
#: `promote` and whose observations are dropped when the receipt they cite does
#: not exist. Nothing else on this surface takes a value the roster cannot
#: describe.
OPEN_ARGUMENTS = {
    "mcp__rk2__park_for_human": ("question",),
    "mcp__rk2__submit_mission_result": (
        "observations",
        "new_entities",
        "hypotheses",
        "evidence",
        "suggested_tasks",
        "completion_claim",
    ),
}

_LABEL = "^{}-[0-9]{{4}}$"
_HASH = "^[0-9a-f]{64}$"

CONTRACTS: dict[str, Contract] = {
    "mcp__rk2__ready": Contract("runtime.ready", "read"),
    "mcp__rk2__get_attack_surface": Contract(
        "state.read",
        "read",
        reads=("entities", "entity_endpoint", "entity_host", "entity_param"),
        arguments={
            "scope_label": Argument("string", pattern=_LABEL.format("S")),
            "kind": Argument("string", enum=("host", "endpoint", "param")),
            "limit": Argument("integer", bounds=(1, 200)),
        },
    ),
    "mcp__rk2__get_hypotheses": Contract(
        "state.read",
        "read",
        reads=("hypotheses", "hypothesis_near_matches"),
        arguments={
            "entity_label": Argument("string", pattern=_LABEL.format("E")),
            "status": Argument(
                "string",
                enum=(
                    "proposed",
                    "testable",
                    "testing",
                    "supported",
                    "refuted",
                    "inconclusive",
                    "retest_due",
                ),
            ),
            "limit": Argument("integer", bounds=(1, 200)),
        },
    ),
    "mcp__rk2__get_evidence": Contract(
        "state.read",
        "read",
        reads=("evidence", "observations"),
        arguments={
            "hypothesis_label": Argument("string", pattern=_LABEL.format("H")),
            "finding_label": Argument("string", pattern=_LABEL.format("F")),
        },
    ),
    "mcp__rk2__get_receipts": Contract(
        "state.read",
        "read",
        reads=("receipts",),
        arguments={
            "receipt_ids": Argument(
                "array", required=True, items_pattern="^R-[0-9]{6}$"
            )
        },
    ),
    "mcp__rk2__get_artifact": Contract(
        "state.read",
        "read",
        reads=("artifacts", "artifact_refs"),
        arguments={
            "artifact_hash": Argument("string", required=True, pattern=_HASH),
            "range": Argument("string", pattern="^[0-9]+-[0-9]+$"),
        },
    ),
    "mcp__rk2__submit_mission_result": Contract(
        "state.propose",
        "propose",
        writes=("proposals",),
        arguments={
            "observations": Argument("array", required=True, free_text=True),
            "new_entities": Argument("array", free_text=True),
            "hypotheses": Argument("array", free_text=True),
            "evidence": Argument("array", free_text=True),
            "suggested_tasks": Argument("array", free_text=True),
            "completion_claim": Argument("object", required=True, free_text=True),
        },
    ),
    "mcp__rk2__offer_slate": Contract(
        "sched.commit", "read", reads=("tasks", "task_slate")
    ),
    "mcp__rk2__claim_task": Contract(
        "sched.commit",
        "commit",
        writes=("tasks", "events"),
        arguments={"task_label": Argument("string", required=True, pattern=_LABEL.format("T"))},
    ),
    "mcp__rk2__promote": Contract(
        "sched.commit",
        "commit",
        writes=("entities", "hypotheses", "findings", "evidence", "observations", "events"),
        arguments={
            "proposal_label": Argument("string", required=True, pattern=_LABEL.format("P")),
            "decision": Argument("string", required=True, enum=("accept", "reject", "merge")),
            "merge_into_label": Argument("string", pattern="^[EHF]-[0-9]{4}$"),
        },
    ),
    "mcp__rk2__request_validation": Contract(
        "sched.commit",
        "commit",
        writes=("validation_queue", "events"),
        arguments={
            "finding_label": Argument("string", required=True, pattern=_LABEL.format("F"))
        },
    ),
    "mcp__rk2__request_report": Contract(
        "sched.commit",
        "commit",
        writes=("report_queue", "events"),
        arguments={"scope_label": Argument("string", pattern=_LABEL.format("S"))},
    ),
    "mcp__rk2__park_for_human": Contract(
        "sched.commit",
        "commit",
        writes=("pending_decisions", "events"),
        arguments={
            "task_label": Argument("string", required=True, pattern=_LABEL.format("T")),
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
        "act",
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
        "act",
        writes=("tool_runs", "artifacts", "artifact_refs"),
        arguments={
            # An enum, because an open binary name is an open allowlist, and an
            # open allowlist on a tool that starts a process is the arbitrary
            # process creation this surface does not have.
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
        "act",
        writes=("tool_runs", "artifacts", "artifact_refs"),
        arguments={
            "skill_name": Argument("string", required=True, pattern="^[a-z0-9][a-z0-9-]{0,63}$"),
            "script": Argument("string", required=True, pattern="^[a-z0-9_.-]{1,64}$"),
            "input_artifact_hashes": Argument("array", items_pattern=_HASH),
        },
    ),
    "mcp__rk2__get_validation_packet": Contract(
        "validate.judge",
        "read",
        reads=("findings", "hypotheses", "test_specs", "replay_runs", "receipts"),
        arguments={
            "finding_label": Argument("string", required=True, pattern=_LABEL.format("F"))
        },
    ),
    "mcp__rk2__submit_verdict": Contract(
        "validate.judge",
        "commit",
        writes=("verdicts", "events"),
        arguments={
            "finding_label": Argument("string", required=True, pattern=_LABEL.format("F")),
            "verdict": Argument(
                "string", required=True, enum=("confirmed", "refuted", "insufficient")
            ),
            "failed_assertion_ids": Argument("array", items_pattern="^A-[0-9]{3}$"),
        },
    ),
}

#: Built-in tools no role holds, each with the reason it holds none. Together
#: with the grants below this partitions the observed inventory exactly: a tool
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
        tool_groups=("runtime.ready", "state.read", "sched.commit"),
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
        tool_groups=("runtime.ready", "state.read", "state.propose", "net.request", "exec.tool_run"),
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
        tool_groups=("runtime.ready", "state.read", "state.propose", "net.request", "exec.tool_run"),
        skills=("access-control", "injection", "business-logic", "auth-session"),
        # Clamped further at run time by the number of free identity leases:
        # two hunters sharing one upstream slot is the session mixing that the
        # identity model exists to prevent.
        max_concurrent=2,
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
        tool_groups=("runtime.ready", "state.read", "state.propose", "exec.tool_run"),
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
        # Not one built-in, and not even the readiness probe: the packet is its
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
GLOBAL_SUBAGENTS = 3


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
    """

    def __init__(self, role: str) -> None:
        if role not in ROLES:
            raise RosterError(f"{role} is not a roster role")
        self.role = ROLES[role]
        self.denials: list[Denial] = []
        self._bindings: dict[str, str] = {}
        self._outstanding: dict[str, str] = {}

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
            denial = Denial(
                IMPERSONATION,
                DELEGATION,
                self.role.name,
                f"agent {agent_id} was started as {recorded} and now claims {agent_type}",
            )
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

        forbidden = _forbidden_argument(call.arguments)
        if forbidden is not None:
            return Denial(
                FORBIDDEN_ARGUMENT,
                tool,
                role.name,
                f"no tool on this surface takes {forbidden}",
            )

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
        if kind not in ROLES or ROLES[kind].runs_as != SUBAGENT:
            return None, Denial(
                UNATTRIBUTED,
                call.tool,
                None,
                f"{kind} is not a role this runtime delegates to",
            )
        recorded = self._bindings.get(identity)
        if recorded is not None and recorded != kind:
            return None, Denial(
                IMPERSONATION,
                call.tool,
                recorded,
                f"agent {identity} was started as {recorded} and now claims {kind}",
            )
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
        if target.runs_as != SUBAGENT:
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
        if self.outstanding >= GLOBAL_SUBAGENTS:
            return Denial(
                OVERFLOW,
                DELEGATION,
                role.name,
                f"this session is at its concurrency of {GLOBAL_SUBAGENTS}",
            )
        self._outstanding[ticket or f"{target.name}:{self.outstanding}"] = target.name
        return None


def _forbidden_argument(arguments: Any, depth: int = 0) -> str | None:
    """The first argument name on this surface that may not exist, at any depth.

    Nested rather than top-level because the names that matter are the ones a
    handler would read, and a handler reads a member of an object as readily as
    it reads a top-level key. The depth bound is not a correctness limit here:
    every contract on this surface is two levels deep at most, so a document
    deeper than the bound is already not a call any contract describes.
    """
    if depth >= DEPTH:
        return None
    if isinstance(arguments, Mapping):
        for name, value in arguments.items():
            if isinstance(name, str) and name.strip().lower() in FORBIDDEN_ARGUMENTS:
                return name
            found = _forbidden_argument(value, depth + 1)
            if found is not None:
                return found
    elif isinstance(arguments, (list, tuple)):
        for value in arguments:
            found = _forbidden_argument(value, depth + 1)
            if found is not None:
                return found
    return None


def inventory() -> Mapping[str, Any]:
    """The observed tool inventory, read once and checked against its digest."""
    return _INVENTORY


def builtin_grants() -> frozenset[str]:
    """Every built-in tool some role holds. The other half of the partition."""
    return frozenset(tool for role in ROLES.values() for tool in role.builtin_tools)


def visible_tools(role: str) -> list[str]:
    """The built-in tools a role's options value offers, in a stable order.

    Visibility, not authority. It is here so the options value and the gate are
    derived from one statement rather than agreeing by inspection, and so a
    role's frame is the role's real surface: a tool the gate would deny is not
    offered, and the model does not spend a turn discovering that.
    """
    return sorted(ROLES[role].builtin_tools)


def allowed_tools(role: str, served: Iterable[str]) -> list[str]:
    """The role's grants, intersected with what this launch actually serves.

    Two lists rather than one, because they answer different questions: the
    roster says what the role may call and the launch says what exists to be
    called. Naming a tool no server provides would be an allowlist entry that
    can never be exercised, and serving a tool the roster withholds would be a
    tool the gate has to deny at every call instead of one nobody offered.
    """
    grants = ROLES[role].tools
    return sorted(grants.intersection(served))


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
    return measured


def _check_inventory(measured: Mapping[str, Any]) -> None:
    """Every built-in name this roster uses is one the pair actually serves.

    Both halves matter and they fail differently. A grant naming a tool the
    pair does not serve is a role that silently has one capability fewer than
    the roster says, because an unknown name in `tools` is dropped rather than
    rejected. A prohibition naming one is worse: it reads as a closed door and
    is a door that was never in the wall.
    """
    observed = set(measured["builtin_tools"])
    granted = builtin_grants()
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
        if role.runs_as == SUBAGENT and RUNTIME in role.invocable_by:
            raise RosterError(f"{name}: a subagent is reached through the delegation tool")
        if role.runs_as != SUBAGENT and tuple(role.invocable_by) != (RUNTIME,):
            raise RosterError(f"{name}: only the runtime starts a {role.runs_as}")
        if role.max_concurrent < 1:
            raise RosterError(f"{name}: a role runs at least once at a time")
        for group in role.tool_groups:
            if group not in TOOL_GROUPS:
                raise RosterError(f"{name}: {group} is not a capability group")
        if len(set(role.tool_groups)) != len(role.tool_groups):
            raise RosterError(f"{name}: a group is granted twice")

        if role.runs_as == RENDERER:
            # Not an agent. The schema says the same with a check constraint
            # that refuses a renderer holding a model, an effort or a token.
            if (role.model, role.effort, role.max_turns) != (None, None, 0):
                raise RosterError(f"{name}: a renderer runs no model, no effort and no turn")
            if role.builtin_tools or role.tool_groups or role.skills:
                raise RosterError(f"{name}: a renderer holds no tool and no skill")
            continue
        if not role.model:
            raise RosterError(f"{name}: a role that runs a model names one")
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

    The three rules that run through the surface are checked here rather than
    described: nothing takes a program or a credential, a read writes nothing,
    and nothing the validator can reach takes a value this roster does not
    constrain. The last is what keeps a validator blind -- there is no field on
    its surface that a hunter's sentence would fit in, so the packet builder is
    not the only thing standing between the two.
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
        if contract.direction not in ("read", "propose", "commit", "act"):
            raise RosterError(f"{name}: {contract.direction} is not a direction")
        if contract.direction == "read" and contract.writes:
            raise RosterError(f"{name}: a read tool that writes is a proposal named as a getter")
        if contract.direction == "propose" and set(contract.writes) != {"proposals"}:
            raise RosterError(f"{name}: a proposal writes staging and nothing else")
        for argument_name, argument in contract.arguments.items():
            _check_argument(name, contract, argument_name, argument)


def _check_argument(tool: str, contract: Contract, name: str, argument: Argument) -> None:
    if name.strip().lower() in FORBIDDEN_ARGUMENTS:
        raise RosterError(f"{tool}: no contract may declare {name}")
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
    if not {"sched.commit", "state.read"}.issubset(orchestrator.tool_groups):
        raise RosterError("the orchestrator schedules and reads state")
    if {"net.request", "exec.tool_run"} & set(orchestrator.tool_groups):
        raise RosterError("the orchestrator does not contact targets")
    if orchestrator.skills or SKILL in orchestrator.builtin_tools:
        raise RosterError("the orchestrator executes no technique")

    validator = ROLES["validator"]
    if tuple(validator.tool_groups) != ("validate.judge",) or validator.builtin_tools:
        raise RosterError("the validator holds only its judgement surface")

    # Scheduling and promotion stay runtime authority, which here means one
    # role that never executes a task holds them and the executing roles do not.
    for name, role in ROLES.items():
        if "sched.commit" in role.tool_groups and role.executes_tasks:
            raise RosterError(f"{name}: executes tasks and commits scheduling")
        if "state.propose" in role.tool_groups and "sched.commit" in role.tool_groups:
            raise RosterError(f"{name}: proposes and promotes its own proposals")


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
