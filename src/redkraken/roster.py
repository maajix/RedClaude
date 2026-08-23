"""The seven roles, what each may call, and the gate that decides one call.

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
from dataclasses import dataclass, field, replace
from importlib import resources
from types import MappingProxyType
from typing import Any

from . import playbook as playbooks_module
from . import skill as skills_module


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

#: The one role that chooses rather than executes. Named because two other
#: modules have to start it by name -- the runtime opens a session as it, and
#: the checks below say what it may hold -- and a role spelled out at each of
#: those is a role that can be renamed in two places out of three.
ORCHESTRATOR = "orchestrator"

#: The other role the runtime starts by name, for the same reason. 037 opens a
#: validator session directly rather than through a claim, because a validator
#: judges one Finding somebody asked about rather than whichever Task the
#: ranking preferred.
VALIDATOR = "validator"

#: The task-kind vocabulary of migration 0019. Held here so the compile can
#: check the mapping is total and injective without a database.
TASK_KINDS = ("recon", "hunt", "analyze", "perform", "conclude", "validate", "report")

#: The delegation tool, and the older name of the same tool. The pair announces
#: `Task` in its init frame and has been observed to spell the same tool `Agent`
#: in permission denials, so the gate resolves one to the other before deciding
#: rather than holding a list that half of the CLI's spellings miss.
DELEGATION = "Task"
ALIASES = {"Agent": DELEGATION}

#: The argument that names what a delegation would start.
SUBAGENT_TYPE = "subagent_type"

#: The whole of what a delegation may say. `Task` is a built-in and so has no
#: `Contract` here to be closed against -- `CONTRACTS` is the set of schemas
#: this runtime serves, and this is a tool the CLI serves -- so the closed set
#: is stated here and enforced by `_delegation` instead. Everything else the
#: bundled CLI ships on that tool decides something the roster already decided:
#: `model` overrides the row a child is assessed against, `isolation` is the
#: filesystem topology `FORBIDDEN_BUILTINS` bans `EnterWorktree` for, and
#: `run_in_background` returns at launch rather than at completion, which would
#: free the cap's slot while the delegation it counted was still running.
DELEGATION_ARGUMENTS = frozenset({"description", "prompt", SUBAGENT_TYPE})

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

# The vocabularies a proposed element is measured against, restated from the
# migration corpus that declares them. Every one is a closed set the database
# already refuses outside of -- a check constraint on the column promotion
# writes, or a reference table promotion looks the value up in -- and until now
# the only place a child could learn one was a sentence in a tool description.
# Four hunts against real targets lost 30, 24, 14 and 11 elements to drops
# written after the run had ended, and the widest of them started at a word:
# one `kind` of "website" took an Application, two Endpoints, four
# Relationships, seventeen Observations, three Hypotheses and three evidence
# edges down with it, because everything after it named it by ref.
#
# A word outside one of these is not a claim promotion might yet accept; it is a
# word this system has no row for, and `unknown_kind` is the only answer
# promotion can give it. So these are not the roster deciding what a proposal
# says -- that is still promotion's, and `OPEN_ARGUMENTS` still holds -- they
# are the words a proposal can be spelled in. `tests/test_roster.py` holds every
# one of them to the corpus, because a vocabulary stated in two places is a
# vocabulary that goes stale in one of them.

#: `applications.kind`, from migration 0003's check constraint.
APPLICATION_KINDS = ("web", "api", "spa", "graphql", "websocket")

#: `parameters.location`, from the same file. There is no `form` and no `json`:
#: both are a body.
PARAMETER_LOCATIONS = ("query", "body", "path", "header", "cookie")

#: `parameters.value_class`, which 20260926T010000Z closed at the column after
#: finding that promotion stored whatever it was handed. Optional on the row and
#: so optional in an element; what it may not be is a tenth word.
PARAMETER_VALUE_CLASSES = (
    "uuid",
    "integer_id",
    "opaque_id",
    "url",
    "file",
    "email",
    "number",
    "path",
    "serialized",
)

#: The one `identities.class` an agent may propose. The column admits three --
#: 20260929T020000Z retired a fourth -- and the two this omits both require a
#: `secret_ref`, which is credential material the operator places and no model
#: proposes. `promote_proposal` says so in a sentence and refuses the element;
#: this says the same thing one step earlier. It is deliberately the proposable
#: set rather than the column's, because a served schema is a promise about
#: calls and not an inventory of rows.
IDENTITY_CLASSES = ("anonymous",)

#: `relationships.type`, as 20260829T000000Z last amended it. Which ordered pair
#: of Entity types each one admits is `relationship_directions` and is not here:
#: an element names its two ends by ref or by label, so nothing in the payload
#: says what types are being joined and no schema over that payload could check
#: the pair. That half of the rule stays prose, and is the reason the prose
#: still exists.
RELATIONSHIP_TYPES = (
    "resolves_to",
    "serves",
    "runs",
    "owns",
    "member_of",
    "redirects_to",
    "embeds",
    "same_as",
)

#: `observation_kinds`, and the `allowed_provenance` array each row carries.
#: The keys are the vocabulary the schema serves; the values are the second
#: rule, which the schema cannot serve -- whether a kind may stand on a Receipt
#: or on a Tool run is a relation between two fields of one element, and the
#: description states it in words. They are held here anyway so that the
#: sentence has something the corpus test can measure it against.
OBSERVATION_KINDS = {
    "artifact_captured": ("receipt", "tool_run"),
    "callback_interaction": ("callback",),
    "content_match": ("tool_run",),
    "credential_effect": ("receipt",),
    "endpoint_discovered": ("receipt", "tool_run"),
    "error_detail": ("receipt", "tool_run"),
    "header_policy_observed": ("receipt", "tool_run"),
    "identity_established": ("receipt",),
    "parameter_discovered": ("receipt", "tool_run"),
    "reflected_input": ("receipt", "tool_run"),
    "response_differential": ("receipt",),
    "response_invariant": ("receipt",),
    "state_change": ("receipt",),
    "technology_identified": ("receipt", "tool_run"),
    "timing_differential": ("receipt",),
    "transport_parameters_observed": ("receipt",),
}

#: `property_classes.id`, every row the corpus seeds. Written flat rather than
#: as eight families, because the family is the part of the id before the dot
#: and a second structure saying so is a second thing to keep true; the corpus
#: test derives the families back out and checks them against
#: `property_class_families`. Long, and that is the point: a hunter picking the
#: nearest of fifty-seven declared classes is doing what the vocabulary is for,
#: while a hunter inventing a fifty-eighth loses the Hypothesis and every
#: evidence edge that named it.
PROPERTY_CLASSES = (
    "authentication.credential_verification",
    "authentication.factor_enforcement",
    "authentication.federation_trust",
    "authentication.recovery_flow",
    "authorization.channel_subscription",
    "authorization.edge_rule",
    "authorization.function_access",
    "authorization.object_ownership",
    "authorization.parallel_route",
    "authorization.state_transition",
    "authorization.tenant_isolation",
    "authorization.token_scope",
    "business_logic.quantity_or_price",
    "business_logic.replay",
    "business_logic.workflow_order",
    "information_disclosure.artifact_exposure",
    "information_disclosure.cached_response",
    "information_disclosure.client_storage",
    "information_disclosure.credential_material",
    "information_disclosure.dependency_manifest",
    "information_disclosure.error_detail",
    "information_disclosure.excess_field",
    "information_disclosure.identifier_oracle",
    "information_disclosure.log_record",
    "information_disclosure.undeclared_field",
    "information_disclosure.workload_metadata",
    "injection.client_channel",
    "injection.client_path",
    "injection.command",
    "injection.document_parser",
    "injection.foreign_resource",
    "injection.formula",
    "injection.markup",
    "injection.model_instruction",
    "injection.object_graph",
    "injection.parameter_precedence",
    "injection.path",
    "injection.query_field",
    "injection.query_language",
    "injection.query_operator",
    "injection.request_forgery",
    "injection.stored_file",
    "injection.template",
    "injection.url_authority",
    "rate_limiting.per_identity",
    "rate_limiting.per_origin",
    "rate_limiting.resource_cost",
    "session_handling.cookie_scope",
    "session_handling.cross_origin_read",
    "session_handling.csrf",
    "session_handling.fixation",
    "session_handling.lifetime",
    "transport.certificate_trust",
    "transport.datagram_transport",
    "transport.header_policy",
    "transport.request_framing",
    "transport.tls_configuration",
)

#: `hypothesis_evidence.polarity` and `.role`, from migration 0007. A refutation
#: is evidence, which is why `refutes` is a polarity and not a failure to file.
EVIDENCE_POLARITIES = ("supports", "refutes")
EVIDENCE_ROLES = ("baseline", "variant", "control", "context")

#: The three parts of a claim's rationale, from `rk2_rationale_keys()`, which
#: `hypotheses_rationale_shape` checks the column against. Named here because
#: the column is `jsonb` and every other field of a `hypotheses` element is
#: text: a run told only that a rationale answers mechanism, expectation and
#: falsifier writes all three into one paragraph, which is what `rk2hunt6`
#: measured on 2026-08-22 -- four claims filed, four dropped `malformed_field`
#: citing "rationale is not an object", and nine evidence edges dropped behind
#: them for citing a claim that no longer existed.
RATIONALE_KEYS = ("mechanism", "expectation", "falsifier")

#: The vocabularies a Test specification is written in, from the `rk2_test_*`
#: functions in `20260815T000000Z__a_test_runs_through_the_replay_lane.sql`.
#: Functions rather than seeded rows or a CHECK list, because the shape rule is
#: itself a function and a CHECK cannot read a table -- so the corpus test reads
#: these out of the function bodies. The drift two statements of one vocabulary
#: can develop is the same drift wherever the first one is written down.
#:
#: `TEST_ACTION_ROLES` is three words where `EVIDENCE_ROLES` is four, and the
#: word that is missing is why both exist. `context` is evidence that arrived
#: alongside the answer; an action exists to settle the question, so
#: `rk2_test_roles` admits no context action and a specification stating one is
#: refused for it.
TEST_PRECONDITION_KINDS = (
    "scope_holds",
    "risk_accepted",
    "identity_leased",
    "budget_allows",
    "target_state",
)
TEST_ACTION_ROLES = ("baseline", "variant", "control")
TEST_ASSERTION_KINDS = (
    "status_equals",
    "status_differs",
    "body_equals",
    "body_differs",
)

#: The one kind of action this runtime performs. A vocabulary of one word rather
#: than a constant, for ticket 35's stated reason: `kind` is on every action so
#: that the set widens in one place on the day an offline tool can be performed
#: under a Tool run that already exists.
TEST_ACTION_KINDS = ("request",)

#: What a request inside a specification may be, from `rk2_test_request_problem`.
#: The same seven `mcp__rk2__http_request` offers, stated a second time on
#: purpose: that enum is what the door will send, this one is what the
#: specification checker will store, and they are two authorities that agree
#: today rather than one authority read twice. The corpus test holds this tuple
#: to the checker and not to the other enum.
TEST_REQUEST_METHODS = ("GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE")

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

#: Names for the runtime's own launch and session configuration: the third
#: noun in story 95, beside credentials and environment variables. Every one of
#: these is decided by the roster or by the launcher and re-checked against the
#: roster before a child starts, so an argument spelling one is a model
#: choosing what it was started as. The built-in delegation tool is the case
#: that makes this concrete -- the bundled CLI ships `model`, `isolation` and
#: `run_in_background` on it -- and a built-in has no contract here to be
#: closed against, so the name is refused wherever it appears instead.
FORBIDDEN_SETTINGS = frozenset(
    {
        "env",
        "environment",
        "setting_sources",
        "settings",
        "cwd",
        "working_directory",
        "sandbox",
        "permission_mode",
        "isolation",
        "model",
        "effort",
        "max_turns",
    }
)

#: Argument names no model-facing tool may declare, whatever the tool. Checked
#: on the call as well as on the contracts, because a built-in tool has no
#: contract here and still takes arguments.
FORBIDDEN_ARGUMENTS = FORBIDDEN_SELECTORS | FORBIDDEN_INSTRUCTIONS | FORBIDDEN_SETTINGS

#: How deep the argument scan goes before it refuses to keep reading. It
#: exists so a pathological document cannot make the gate the slow part of a
#: tool call, and it sits far below Python's own recursion limit so a nested
#: payload cannot end the scan by ending the interpreter. Reaching it is a
#: denial and not a pass: a document whose remainder went unread is exactly
#: where a Program identifier would be put. It is set well clear of anything a
#: contract describes -- the deepest is two levels -- so that refusing at it
#: refuses only documents no call was ever going to be.
DEPTH = 16

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


class _Deeper(Exception):
    """The scan reached `DEPTH` with a document still below it.

    Raised rather than returned because `_forbidden_argument` answers with the
    name it found, and "I stopped before the bottom" is not a name. The gate
    turns it into a refusal.
    """


@dataclass(frozen=True, slots=True)
class Argument:
    """One argument of one model-facing tool, and what constrains its value.

    An argument is authority, so the roster states the shape of every one
    rather than leaving it to the handler. `free_text` is the explicit
    admission that this roster constrains nothing about a value; it is allowed
    only where `OPEN_ARGUMENTS` says why, and never on a tool the validator can
    reach.

    `element` is the one thing that sits beside `free_text` rather than against
    it, and it is deliberately not counted by `constrained`. An open argument is
    open about what it *carries*: any key, any depth, no required field, and the
    gate reads an instruction word inside it as the hunter's own report rather
    than as an instruction. Naming the closed vocabulary a particular field of a
    particular element is drawn from takes none of that back -- it says which
    words exist, not which claims are true -- so the two are orthogonal and an
    argument may hold both.
    """

    kind: str
    required: bool = False
    enum: tuple[str, ...] = ()
    pattern: str | None = None
    items_pattern: str | None = None
    values_pattern: str | None = None
    bounds: tuple[int, int] | None = None
    free_text: bool = False
    #: The named fields of one element of an array, each a declared `Argument`
    #: of its own. Spelled `element` and not `items` because this codebase calls
    #: these the element lists, and because `items_pattern` already spends the
    #: other word on an array of labels.
    element: Mapping[str, "Argument"] | None = None
    #: Field names an element of this array may not carry, refused by the schema
    #: rather than by promotion. The element object stays open -- it has a dozen
    #: honest fields and only a handful are named here -- so this is the way to
    #: say that one particular key belongs somewhere else. Ticket 155: a run put
    #: its evidence edges inside the claims they support, the promotion reads
    #: the top-level `evidence` list and nothing else, and every claim of that
    #: run was dropped for having no support, after the run had ended and where
    #: it could not be told. One place is the whole of the fix: a key that has
    #: another home is refused as it is sent, which the model sees as a rejected
    #: call it can correct and re-send inside the same run.
    refuses: tuple[str, ...] = ()

    @property
    def constrained(self) -> bool:
        return bool(
            self.enum
            or self.pattern
            or self.items_pattern
            or self.values_pattern
            or self.bounds
        )

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
            low, high = self.bounds
            if self.kind == "string":
                # `minimum` and `maximum` are JSON Schema's number vocabulary
                # and say nothing about a string. The gate measures a string by
                # its length, so the schema has to bound the same thing in the
                # words a validator reads, or the promise and the check are two
                # different rules wearing one declaration.
                body["minLength"], body["maxLength"] = low, high
            elif self.kind == "array":
                # And the same sentence about an array, which `_value_fault`
                # also measures by `len`. A Test states between three and
                # thirty-two actions; written as `minimum` that rule would be a
                # number vocabulary applied to a list, which every validator
                # ignores -- so the pair would serve a promise it never checks
                # and the gate would refuse a call the schema said was fine.
                body["minItems"], body["maxItems"] = low, high
            else:
                body["minimum"], body["maximum"] = low, high
        if self.items_pattern and self.kind == "object":
            # A pattern over an object's *keys*, which is what a header name is.
            body["propertyNames"] = {"pattern": self.items_pattern}
        elif self.items_pattern:
            body["items"] = {"type": "string", "pattern": self.items_pattern}
        if self.values_pattern:
            # And one over what those keys carry. A well-formed name says
            # nothing about its value, and on an argument that is put on a
            # wire the value is the half that can carry a second request.
            body["additionalProperties"] = {"type": "string", "pattern": self.values_pattern}
        if self.element is not None:
            # Three things are absent from this subschema and each absence is
            # the decision. No `required`, so an element that leaves a field out
            # is still a well-formed call: a missing field costs that one
            # element at promotion, and refusing the call for it would cost
            # every other element sent beside it. No
            # `additionalProperties: false`, because the
            # fields named here are a handful of the dozen a typed element
            # carries and closing the object would refuse every honest one. No
            # `type: object` either, for the same reason as the first: a string
            # where an element belongs is dropped by promotion today and there
            # is nothing to gain by ending the whole submission over it.
            #
            # What is left is the half that is worth refusing loudly. A value
            # outside one of these enums is refused by the CLI before
            # `PreToolUse` runs, which the model sees as a rejected tool call it
            # can correct and re-send inside the same run -- where the same
            # value reaching promotion is a `proposal_drops` row written after
            # the run has ended, taking every later element that pointed at the
            # dropped one with it.
            named = {name: shape.schema() for name, shape in self.element.items()}
            # `items` is JSON Schema's word for what is in a list and says
            # nothing about an object, so an object-shaped argument declares its
            # fields directly. The one that exists is a claim's `rationale`,
            # whose column is `jsonb` where every other field of that element is
            # text -- and `type: object` comes from `kind` above, which is the
            # half that stops a paragraph being sent where three fields belong.
            if self.kind == "object":
                body["properties"] = named
            else:
                body["items"] = {"properties": named}
        if self.refuses:
            # `not` over `required` rather than `additionalProperties: false` or
            # a boolean subschema: the element has to stay open, and this is the
            # spelling every validator in the draft handles. It says the one
            # thing meant -- an element of this list does not carry these names
            # -- and says nothing about the fields it does carry.
            refusal = {"not": {"required": sorted(self.refuses)}}
            if self.kind == "object":
                body.update(refusal)
            else:
                body["items"] = {**body.get("items", {}), **refusal}
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
    max_concurrent: int
    #: Migration 0019's column of the same name. True where the role's real
    #: ceiling is the number of free Identity leases rather than the number
    #: above: two hunters sharing one upstream slot is the session mixing the
    #: Identity model exists to prevent. The clamp itself is the scheduler's,
    #: which is the only party that knows how many leases are free.
    clamp_to_identity_leases: bool = False
    #: Derived, not written: `_check_skills` fills this from the Skill corpus at
    #: import, and the table below states no skill at all. Which role may load
    #: which Skill is a property of the Skill -- it is the `bb:roles` line in its
    #: own frontmatter -- and stating it here as well would be a second list that
    #: agrees with the first until somebody adds a skill and forgets. A field
    #: with a default rather than a property, because the value is a fact about
    #: the corpus that one walk establishes and every later reader shares; a
    #: property would recompute it per read from a corpus this class cannot see.
    skills: tuple[str, ...] = ()

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
        # The sixth is the same authority and not a new one: it reads the same
        # Program's rows through the same views under the same role, and the
        # only thing it does that the five above cannot is read a row written
        # after the packet was compiled. A group of its own would have said the
        # opposite -- that reading a row minted five seconds ago is a different
        # kind of permission from reading one minted five minutes ago -- and
        # nothing about scope, isolation or bounding makes that true.
        "mcp__rk2__refresh_packet",
    ),
    # What a role that executes work may say about state it is not allowed to
    # write. The first member is the whole of one run's reading; the second is
    # the one claim that reading can amount to. Both are here rather than in
    # `sched.pick` because deciding that something is worth reporting belongs
    # to the party that did the hunting, and `_check_authority` keeps the two
    # groups off the same role -- so a role that proposes a Finding is never
    # also the role that schedules the work the Finding would justify.
    #
    # The third member is the out-of-band half of the same authority. A
    # correlator is state the run does not write -- `mint_callback_correlator`
    # writes it, under the runtime's role, against a channel the operator
    # declared -- and what the model contributes is which subject it is about.
    # It is here rather than in `net.request` because the door is not involved:
    # the correlator travels out inside a request the model composes, and the
    # arrival comes back to a listener that is nobody's tool call.
    #
    # The fourth member is the same authority as the second, one step earlier in
    # the same chain. A Finding rests on a supported claim; a claim reaches
    # `supported` only through a Test run; and a Test run replays a `tests` row
    # nothing this surface could write. So the role that holds a testable claim
    # asks for the specification the same way it asks for the Finding -- the
    # runtime decides, out of rows the runtime wrote -- and the two asks sit in
    # one group because they are one role's account of one piece of work.
    "state.propose": (
        "mcp__rk2__submit_mission_result",
        "mcp__rk2__propose_finding",
        "mcp__rk2__mint_callback",
        "mcp__rk2__propose_test",
    ),
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
#:
#: The six lists are still here now that they carry an `Argument.element`, and
#: that is not an oversight. Being open is what `_opaque` reads them by, and
#: what it decides is that `secret` and `password` inside an Observation are the
#: hunter's report of what it found rather than an attempt to send one. A
#: closed vocabulary for `kind` does not make an element list any less the place
#: an exposed credential gets written down.
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

#: What one declared argument of one registered tool is called, which is
#: `offline_tool_arguments.name`'s own check constraint. A name outside it is a
#: name the registry has no row for, and refusing it here means a tool call the
#: gate passed is a tool call the registry can at least look up.
_ARGUMENT_NAME = "^[a-z][a-z0-9_]{0,31}$"

#: The largest page a bounded read may be asked for. The handler bounds the
#: response by serialized bytes as well, so this is the coarse half of the
#: ceiling and the byte budget is the half that binds.
_PAGE = (1, 200)

#: The named fields of one element of each of the six lists, and the vocabulary
#: each of those fields is drawn from. Keyed by the argument name so that the
#: contract below reads as six lists rather than six shapes, and so that
#: `proposal_drops.element_path` and this table are indexed the same way.
#:
#: Only the fields whose vocabulary is closed. `fqdn`, `base_url`,
#: `path_template`, `statement` and the rest of what promotion reads are absent,
#: because a schema that named them without constraining them would be
#: documentation in the wrong place -- the description is where a field name a
#: model has to guess belongs.
#:
#: A field whose value is one name: a ref this result minted, or the label of a
#: row this Program already holds. Bounded rather than drawn from a vocabulary
#: because there is no vocabulary -- eight Entity types spell their labels
#: differently and a ref is whatever the model called it. What the declaration
#: buys is the *field name*, which is the half ticket 164 found missing: an
#: element's subject, its ends and its sentence were named in the tool's prose
#: and nowhere else, so a paragraph added beside that prose was enough to make a
#: recon run stop writing them and every Observation it sent be dropped.
_NAME = Argument("string", bounds=(1, 200))

#: `new_entities` is one list for eight Entity types, so its shape is the union
#: of four fields no two of those types share: `kind` is an Application's,
#: `location` and `value_class` are a Parameter's, `class` is an Identity's.
#: That union is only safe while it stays a union -- a later type that spelled
#: `kind` differently would silently narrow the other one -- and the corpus test
#: is what would notice.
_ELEMENTS: dict[str, Mapping[str, Argument]] = {
    "new_entities": {
        "type": Argument("string", enum=ENTITY_TYPES),
        "kind": Argument("string", enum=APPLICATION_KINDS),
        "location": Argument("string", enum=PARAMETER_LOCATIONS),
        "value_class": Argument("string", enum=PARAMETER_VALUE_CLASSES),
        "class": Argument("string", enum=IDENTITY_CLASSES),
    },
    "relationships": {
        "type": Argument("string", enum=RELATIONSHIP_TYPES),
        "src_ref": _NAME,
        "src_label": _NAME,
        "dst_ref": _NAME,
        "dst_label": _NAME,
    },
    "observations": {
        "kind": Argument("string", enum=tuple(OBSERVATION_KINDS)),
        "subject_ref": _NAME,
        "subject_label": _NAME,
        # The sentence, under the one name promotion reads it by. Bounded at
        # what the column takes, so a sentence too long to store is refused
        # while the run is there to shorten it rather than stored cut in half.
        "summary": Argument("string", bounds=(1, 2000)),
    },
    "hypotheses": {
        "property_class": Argument("string", enum=PROPERTY_CLASSES),
        "subject_ref": _NAME,
        "subject_label": _NAME,
        # The one field in this table whose column is not text. `type: object`
        # is the half that matters: a run that writes a paragraph here has its
        # whole claim dropped after the run has ended, where a schema refuses
        # the call while the run is still there to correct it.
        # Each part is bounded rather than left open, and the lower bound is
        # the load-bearing half: `rk2_gradable_claims` will not grade a claim
        # whose mechanism, expectation or falsifier is empty, so a part sent
        # empty is a claim that promotes and then sits at `proposed` forever.
        "rationale": Argument(
            "object",
            element={
                key: Argument("string", bounds=(1, 2000)) for key in RATIONALE_KEYS
            },
        ),
    },
    "evidence": {
        "polarity": Argument("string", enum=EVIDENCE_POLARITIES),
        "role": Argument("string", enum=EVIDENCE_ROLES),
        "observation_ref": _NAME,
        "observation_label": _NAME,
        "hypothesis_ref": _NAME,
        "hypothesis_label": _NAME,
    },
    "suggested_tasks": {
        "kind": Argument("string", enum=TASK_KINDS),
        "subject_ref": _NAME,
        "subject_label": _NAME,
    },
}

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
        # `callback_interactions` joined the list with ticket 98's
        # `callback_label`: an arrival is now named on this view like a Receipt
        # and a Tool run are, so the table it is named out of is a table this
        # read reaches. What the read reaches of it is the label and nothing
        # else -- `observed_host` carries the correlator, and the table's own
        # comment is where that is said.
        reads=(
            "v_evidence",
            "hypothesis_evidence",
            "finding_evidence",
            "observations",
            "callback_interactions",
        ),
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
    # The one read that goes to the database rather than to the snapshot, and
    # the reason it exists is that every read above it answers from a document
    # compiled before this container started. `packet.compile` runs once, on the
    # supervisor's `rk2_state` connection; the act tools mint rows into the
    # database that document was taken of. So a Receipt label an exchange just
    # handed back resolves to `not_staged` and an Artifact label to
    # `no_such_artifact` -- not because the row is missing but because the
    # photograph is older than the row.
    #
    # By label, and that is the design decision rather than an ergonomic one.
    # One run of the `authentication` Playbook mints 78 labels whose rows weigh
    # 33,974 bytes, and the whole packet ceiling is 32,768, so "refresh
    # everything I have minted" is a question with no honest answer at any
    # ceiling. Three arrays, one per kind of row a run can mint while it is
    # going, and `packet.REFRESH_BYTES` bounds what one answer to them weighs.
    #
    # Nothing here reaches further into an Artifact than the compile did. A
    # refresh restages a head at the same `DEFAULT_EXCERPT`, because a refresh
    # that staged more would be a way to read a whole response body 4 KB at a
    # time; reading past that is `exec.tool_run`'s job, where the answer is a
    # bounded summary rather than a window into a context.
    "mcp__rk2__refresh_packet": Contract(
        "state.read",
        READ,
        reads=(
            "v_records",
            "receipts",
            "tool_runs",
            "v_artifacts",
            "artifact_references",
            "artifacts",
        ),
        arguments={
            "receipt_labels": Argument("array", items_pattern=_label("R")),
            "artifact_labels": Argument(
                "array", items_pattern=_label(LABEL_PREFIXES["artifact_references"])
            ),
            # The third kind, and the one no other read on this surface takes.
            # A `tool_run` label is handed back by both tool-run tools and until
            # now resolved to nothing at all, because no Contract read
            # `tool_runs`. This one does; what it does not do is list them,
            # which is ticket 129's, so the only way to reach a Tool run here is
            # to name one the runtime already told this run about. `TR` and not
            # `T`: `T` is a Task, and a pattern that admitted one would let a
            # child ask the `tool_runs` kind of `v_records` for a name that kind
            # never carries.
            "tool_run_labels": Argument(
                "array", items_pattern=_label(LABEL_PREFIXES["tool_runs"])
            ),
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
    #
    # And they stay open while carrying `_ELEMENTS`, which is the distinction
    # that decision turns on rather than an exception to it. "The runtime
    # decides what grounds" is about judgement: whether a Receipt supports a
    # reading, whether a claim is worth a row, whether a proposal is true. None
    # of that moves. What `_ELEMENTS` states is the opposite kind of fact -- the
    # set of words a field can be spelled in -- and promotion holds no opinion
    # about a word outside it: `unknown_kind` is the only answer it has, and it
    # writes that answer into `proposal_drops` after the run that made the
    # mistake has already ended. Four hunts promoted zero Hypotheses between
    # them, and every rule they broke was already written out in this tool's
    # description at the time they broke it. Prose served once at schema time is
    # not read again while a thirty-element payload is being composed; an enum
    # in the schema is checked against every element that carries the field.
    #
    # The cost is real and is the reason the shape is as thin as it is. The CLI
    # validates against the served schema before `PreToolUse` runs, so a value
    # outside an enum fails the whole call rather than losing one element, and a
    # run that cannot get its result accepted files nothing at all. That is why
    # no field of an element is `required`, why the element object is not
    # closed, and why only fields with a genuinely closed vocabulary are named:
    # everything that is merely *probably* wrong is left to promotion, where it
    # costs one element, and only what is *certainly* refused is refused here,
    # where it costs a retry the model can actually make.
    "mcp__rk2__submit_mission_result": Contract(
        "state.propose",
        PROPOSE,
        writes=STAGING,
        arguments={
            "observations": Argument(
                "array", required=True, free_text=True, element=_ELEMENTS["observations"]
            ),
            "new_entities": Argument(
                "array", free_text=True, element=_ELEMENTS["new_entities"]
            ),
            "relationships": Argument(
                "array", free_text=True, element=_ELEMENTS["relationships"]
            ),
            "hypotheses": Argument(
                "array", free_text=True, element=_ELEMENTS["hypotheses"],
                # An edge lives in `evidence` and nowhere else. Ticket 155.
                refuses=("evidence",),
            ),
            "evidence": Argument("array", free_text=True, element=_ELEMENTS["evidence"]),
            "suggested_tasks": Argument(
                "array", free_text=True, element=_ELEMENTS["suggested_tasks"]
            ),
            "completion_claim": Argument(
                "object", required=True, items_pattern="^(status|note)$"
            ),
        },
    ),
    # The one thing a hunting role may ask the runtime to write down about what
    # its work amounted to, and the reason it is an ask. `findings` is a
    # canonical table, so no contract may name it in `writes` and the compile
    # refuses one that does -- which is the rule that decides the shape of this
    # tool rather than a rule it has to work around. The child says which claim
    # it believes is a Finding; `open_finding` decides whether it is, out of
    # rows the runtime itself wrote, and answers what it decided.
    #
    # Three arguments and not four. The proposal names a claim, a class and a
    # title, and it does not name the run that settled the claim, because there
    # is no name for one: `test_runs` carries no label and a packet publishes
    # Entities, Hypotheses, evidence edges, Receipts and Artifacts and no Test
    # at all, so a run argument would be a field no child could fill. Nothing
    # is given up by leaving it out. The settling run is pinned by the claim --
    # the transition from `testing` to `supported` cites one Receipt and that
    # Receipt belongs to one run -- so naming the Hypothesis names the run, and
    # a proposal that named any other run would be refused for naming it.
    "mcp__rk2__propose_finding": Contract(
        "state.propose",
        REQUEST,
        writes=("finding_proposals",),
        arguments={
            "hypothesis_label": Argument("string", required=True, pattern=_label("H")),
            # A pattern rather than an enum, which is the opposite of the choice
            # `run_tool` makes about its own binaries and is right for the same
            # reason that one is. A binary is a program this harness starts and
            # the closed list is the authority; a vulnerability class is a word
            # from a seeded table that later tickets add rows to, and an enum
            # here would be a second copy of that table which goes stale the
            # first time somebody extends it. The eighth arm of
            # `rk2_finding_refusal` answers an unknown class by naming it, so
            # the vocabulary refuses out of the table that declares it.
            "vulnerability_class": Argument(
                "string", required=True, pattern="^[a-z][a-z0-9_]{2,63}$"
            ),
            # The one field on a Finding that a person reads and no rule reads,
            # so what is stated about it is how long it may be and nothing else.
            # A shape would be this roster deciding how a finding is written up.
            "title": Argument("string", required=True, bounds=(1, 200)),
        },
    ),
    # The row the tool above rests on, and the reason it is a tool at all.
    #
    # THE SHAPE DECISION, AND THE ONE IT WAS TAKEN AGAINST. Ticket 141 named two
    # candidates: this -- the model that holds the claim authors the
    # specification through a Contract shaped like `propose_finding` -- or the
    # runtime derives one from the Playbook the Task was selected under. The
    # second is not available. `playbook_selections` has never held a row in this
    # tree (ticket 101), so a derivation-only answer ships a producer nothing
    # exercises, which is the defect this ticket is about rather than a fix for
    # it. The two are not exclusive: a derivation can be added later and will
    # write the same rows through the same verb, because what decides whether a
    # `tests` row exists is `propose_test` and not its caller.
    #
    # WHY THIS IS AN ASK AND NOT A WRITE. `tests` is in `CANONICAL`, so
    # `_check_contracts` refuses any contract naming it in `writes` -- which is
    # the rule that decides this shape rather than one it works around, exactly
    # as it decided `propose_finding`'s. What this writes is `test_proposals`,
    # the audit row beside `tests`, and `propose_test` decides whether a Test
    # comes of it. A specification is a program this harness will execute against
    # somebody else's system, so "the agent wrote it" and "the runtime stored it"
    # have to be two events with a decision between them.
    #
    # WHY THE PARTS ARE ARGUMENTS RATHER THAN ONE OBJECT. A single `spec` object
    # would be one free-text argument -- there is no `element` for an object --
    # and `OPEN_ARGUMENTS` would have to say why the most consequential document
    # on this surface is the one the roster describes least. Five arrays name the
    # five parts `rk2_test_spec_problem` closes, so a sixth part is refused by
    # `additionalProperties: false` before it reaches the sentence that would
    # refuse it, and each part's closed vocabulary is served as an enum the CLI
    # checks before `PreToolUse` runs.
    #
    # Five and not seven. A stored specification may also carry `impact` and
    # `pivot`, and neither is an argument here, because neither is a plan: an
    # impact block is what an operator's grant is measured against (ticket 38
    # authorizes impact before it is proved) and a pivot block claims a
    # capability out of `capabilities` (ticket 39). A model that could write
    # either would be a model authorizing its own impact and minting its own
    # capability, which is the same class of thing as writing `tests` directly.
    #
    # AND WHY ONLY THE VOCABULARIES ARE SERVED. Everything else the shape rule
    # says -- that a url is absolute and canonical, that an action is numbered by
    # its position, that no two assertions share an identifier, that a Test
    # carries all three roles -- stays where the sentence is. This is the
    # opposite of the trade `submit_mission_result` makes and it is the same
    # reasoning: there, a rule the schema cannot see costs one element in a
    # `proposal_drops` row written after the run ended, so refusing early is
    # worth a retry. Here the answer arrives while the run is still going and
    # names which of the thirty rules broke, which is strictly more than a
    # rejected call quoting a regex can say. A word from a closed list is the one
    # thing a model cannot derive from a refusal it has not had yet, so that is
    # the half the schema carries.
    "mcp__rk2__propose_test": Contract(
        "state.propose",
        REQUEST,
        writes=("test_proposals",),
        arguments={
            "hypothesis_label": Argument("string", required=True, pattern=_label("H")),
            # Not required, and empty is a specification that states no
            # precondition rather than one that forgot to. The shape rule admits
            # an empty array in every part and the handler sends `[]` for a part
            # left out, so "absent" and "empty" are one thing here and the digest
            # cannot depend on which spelling a model used.
            "preconditions": Argument(
                "array",
                bounds=(0, 16),
                element={
                    "kind": Argument("string", enum=TEST_PRECONDITION_KINDS),
                    # A precondition is prose under a typed word, so the length
                    # is the whole of what is stated about the prose.
                    "detail": Argument("string", bounds=(1, 500)),
                },
            ),
            "setup": Argument(
                "array",
                bounds=(0, 16),
                element={
                    "method": Argument("string", enum=TEST_REQUEST_METHODS),
                    # The url's length and not its shape. `rk2_test_request_problem`
                    # answers a relative url, a lower-case method, a path that
                    # resolves elsewhere and a `%2e` in four different sentences,
                    # each naming the position it found the fault in, and a
                    # pattern here would replace all four with a rejected call.
                    # A length is the one rule whose sentence adds nothing.
                    "url": Argument("string", bounds=(1, 2000)),
                },
            ),
            "actions": Argument(
                "array",
                required=True,
                bounds=(3, 32),
                element={
                    # Carried by the model and checked against its position,
                    # because a plan read in one order and numbered in another is
                    # a plan whose assertions point at requests nobody planned.
                    "ordinal": Argument("integer", bounds=(1, 32)),
                    "role": Argument("string", enum=TEST_ACTION_ROLES),
                    "kind": Argument("string", enum=TEST_ACTION_KINDS),
                    "method": Argument("string", enum=TEST_REQUEST_METHODS),
                    "url": Argument("string", bounds=(1, 2000)),
                },
            ),
            "assertions": Argument(
                "array",
                required=True,
                bounds=(1, 32),
                element={
                    # 035's spelling, restated here for the reason
                    # `submit_verdict.failed_assertion_ids` restates it: a
                    # validator names a failed assertion by this identifier, so
                    # an identifier a Test could be authored with and a verdict
                    # could not name would be a failure nobody can report.
                    "id": Argument("string", pattern="^[a-z][a-z0-9-]{2,62}$"),
                    "kind": Argument("string", enum=TEST_ASSERTION_KINDS),
                    "action": Argument("integer", bounds=(1, 32)),
                    "against": Argument("integer", bounds=(1, 32)),
                    "status": Argument("integer", bounds=(100, 599)),
                },
            ),
            "cleanup": Argument(
                "array",
                bounds=(0, 16),
                element={
                    "method": Argument("string", enum=TEST_REQUEST_METHODS),
                    "url": Argument("string", bounds=(1, 2000)),
                },
            ),
        },
    ),
    # The name a step plants in somebody else's system, and the one verb on this
    # surface whose evidence arrives without anybody here having asked for it.
    # Every other Observation is a request this installation made and a Receipt
    # the door wrote for it; an out-of-band interaction is a request the TARGET
    # made, at a name we published, and the only thing tying it back to a
    # Program is the correlator that travelled out in a payload.
    #
    # A request rather than a read, because it mints: `callback_correlators`
    # gains a row, keyed to the live scope version and to the Tool run this
    # child's egress goes out on, and that row is what will admit an arrival
    # later. Two arguments and both of them are names the child can already
    # read -- the channel the Program declared and the Entity the canary is
    # about -- because everything else about a correlator is the channel's
    # business and not the model's. The runtime mints the correlator itself,
    # the runtime decides how long it lives, and the Program's one declared
    # channel is the only one it may be minted on. A correlator planted in
    # somebody else's system is a durable artefact whose lifetime we do not
    # control, so the parts a model could get wrong are the parts it is not
    # given.
    "mcp__rk2__mint_callback": Contract(
        "state.propose",
        REQUEST,
        writes=("callback_correlators",),
        arguments={
            # `program_callback_channels.name`'s own check constraint, restated
            # so that a name no channel could ever carry is refused by the
            # schema rather than by a query that finds nothing.
            "channel": Argument("string", required=True, pattern="^[a-z0-9][a-z0-9-]{0,62}$"),
            # Any Entity label, because a correlator's subject is whatever the
            # canary is a question about -- the endpoint that fetches, the
            # parameter that was reflected, the application that parsed. The
            # database re-asks that the Entity is this Program's.
            "subject_label": Argument("string", required=True, pattern=_ENTITY_LABEL),
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
    # The name a model calls this by and the name the runtime opens the Tool run
    # under are two different names, and every per-call risk rule is written
    # against the second. This surface serves `mcp__rk2__http_request`;
    # `execution._authorize` opens the run under `proxy.TOOL`, which is
    # `mcp__rk2__net_request`, and `call_risk_rules` names that one in all three
    # of `net_unsafe_method`, `net_host_out_of_scope` and
    # `net_borrowed_identity`. A ticket that opened a Tool run per agent call
    # under the served name would silently stop all three firing, and nothing
    # would fail while it did: the static floor still covers the served name
    # through the `mcp__rk2__*` glob, so the run would keep its class and only
    # the escalations would go quiet. Ticket 97 records the hazard here, where a
    # reader meets the served name, rather than leaving it to be rediscovered.
    "mcp__rk2__http_request": Contract(
        "net.request",
        ACT,
        # Ticket 106 changed what this answers and deliberately changed nothing
        # here. The two Artifact labels an exchange now hands back come off
        # `artifact_refs` rows that `register_proxy_artifacts` and
        # `hold_receipt_transcripts()` were already writing under this
        # declaration, in the Receipt's own transaction; the declaration was
        # never the thing that was missing. A contract states what a call
        # touches, and this call touched all three before and after.
        writes=("receipts", "artifacts", "artifact_refs"),
        arguments={
            "method": Argument(
                "string",
                required=True,
                enum=("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"),
            ),
            "url": Argument("string", required=True, pattern="^https?://"),
            # Names, and what those names carry. The value pattern ends at
            # `\Z` rather than `$` because `$` also matches before a trailing
            # newline, and a trailing newline is exactly the character a header
            # value would smuggle a second request in with.
            "headers": Argument(
                "object",
                items_pattern="^[A-Za-z][A-Za-z0-9-]{0,63}\\Z",
                values_pattern="^[\\x20-\\x7e]{0,1024}\\Z",
            ),
            # The bytes after the headers. This argument was withheld until
            # ticket 96 with the reason "the child has no store, so it cannot
            # name a body the door could send", and half of that sentence was
            # about a store the child still does not have: what changed is that
            # a bounded string is a body the child can spell itself, so nothing
            # has to be named out of a store for the door to send one.
            #
            # A string and not an object, and that is the decision this
            # argument is. The gate walks every container argument at every
            # depth and refuses `password`, `token`, `secret`, `authorization`
            # and a dozen other names, while `_scan` returns immediately for
            # anything that is not a Mapping, a list or a tuple. An object body
            # carrying a username and a password is the most ordinary POST in
            # web testing and the gate would deny it; a string body is never
            # scanned at all. What the string costs is that the model spells
            # its own encoding, which is the same thing that makes a multipart
            # boundary or a deliberately malformed document expressible.
            #
            # `bounds` alone makes the argument constrained, so no
            # `OPEN_ARGUMENTS` entry is spent here. The ceiling is 64 KiB and
            # it is an argument ceiling: these bytes are written by a model
            # into a model's context, and the number that bounds them has
            # nothing to do with the door's own 32 MiB, which is how much of a
            # target's answer this harness will hold in memory to hash and
            # store. Two different questions, two numbers, stated apart.
            #
            # `Content-Type` is not here because it is a header and the header
            # argument above already constrains it, which also keeps "send a
            # body with no Content-Type at all" expressible. `Content-Length`
            # is not here and never will be: the door strips the length that
            # arrives and re-measures the bytes it forwards, so an argument for
            # it would be a promise the door drops.
            "body": Argument("string", bounds=(0, 65536)),
            # No identity, and ticket 97 makes that a settled rule rather than
            # the "not yet" it used to be: `identity_slot` is a property of the
            # Tool run, never an argument, and this contract goes on refusing
            # it. The refusal is the ordinary one -- the schema is closed and
            # `_argument_fault` answers "takes no argument named
            # 'identity_slot'" -- so nothing here has to be spelled to make it
            # hold. What is spelled is why declaring one would be wrong, since
            # the name is in no forbidden list and only a written decision
            # stands between a later ticket and adding it.
            #
            # The door has no parameter to receive one.
            # `resolve_egress_identity(p_capability)` takes the capability and
            # reads the slot out of `tool_runs.args` for the run that
            # capability resolves to; `authorize_identity_egress_request` takes
            # the capability, the method, the address and whether there is a
            # body, and nothing else. And the door could not record one either:
            # `rk2_proxy` holds no privilege of any kind on `tool_runs`, whose
            # INSERT and UPDATE belong to `rk2_owner` and `rk2_runtime` alone.
            # A slot arriving at call time would have nowhere to go.
            #
            # Above that, it is the field a human already answered about.
            # `gate_tool_call` and `current_request_digest` each take a Tool run
            # id and nothing else, and the digest an approval is keyed on is
            # `canonical_request(tr.tool, tr.args, ...)`. The same request with
            # the slot empty is `constrained` under the static floor; with a
            # slot named it is `approval_required` under
            # `call_risk_rules:net_borrowed_identity`, asking
            # `credential_needed`. A slot named after that row was written moves
            # neither the class nor the key, so the argument's whole effect
            # would be a model acting as a real account holder outside the
            # answer a person gave.
            #
            # And one Tool run is many exchanges. `receipts.tool_run_id` is a
            # plain foreign key with no unique index over it, and subresources
            # and redirects share one capability by design, so every Receipt
            # under a run resolves the same slot. An argument would be a
            # per-call answer to a question the row answers once.
            #
            # The field is broken in the other direction, and that defect is not
            # this roster's to fix: `execution._authorize` opens every egress
            # Tool run with the slot hardcoded empty, so no agent-issued request
            # carries an Identity at all. Declaring an argument here would not
            # move it one step closer to carrying one.
        },
    ),
    "mcp__rk2__run_tool": Contract(
        "exec.tool_run",
        ACT,
        writes=("tool_runs", "artifacts", "artifact_refs"),
        arguments={
            # An enum, because an open binary name is an unbounded set of
            # programs, and an unbounded set on a tool that starts a process is
            # the arbitrary process creation this surface does not have. The
            # members are the registry's own `offline_tools` names -- the ones
            # that are a binary rather than a Skill script, which is the other
            # tool below -- because the call is opened by
            # `open_offline_tool_run` and a name this enum admitted and the
            # registry did not would be a refusal one layer too late.
            "tool": Argument(
                "string",
                required=True,
                enum=("jq", "js_map", "js_parse", "js_routes"),
            ),
            # Named, not free. `offline_tool_arguments` declares every argument
            # of every registered tool -- its position, its flag, whether it
            # takes an Artifact or a literal, and what a literal may match --
            # and an argv would be a second, weaker statement of the same thing
            # that the registry would then have to take apart again.
            "arguments": Argument(
                "object",
                required=True,
                items_pattern=_ARGUMENT_NAME,
                values_pattern="^[^\\x00]{0,512}$",
            ),
        },
    ),
    "mcp__rk2__run_skill_script": Contract(
        "exec.tool_run",
        ACT,
        writes=("tool_runs", "artifacts", "artifact_refs"),
        arguments={
            "skill_name": Argument("string", required=True, pattern="^[a-z0-9][a-z0-9-]{0,63}$"),
            "script": Argument("string", required=True, pattern="^[a-z0-9_.-]{1,64}$"),
            "arguments": Argument(
                "object",
                required=True,
                items_pattern=_ARGUMENT_NAME,
                values_pattern="^[^\\x00]{0,512}$",
            ),
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
            # 035's own spelling for an assertion identifier, not a shape
            # invented here. `rk2_test_spec_problem` refuses a Test whose
            # assertion is identified any other way, so a pattern of this
            # roster's own would have closed the argument against every
            # identifier a Test can actually carry.
            "failed_assertion_ids": Argument(
                "array", items_pattern="^[a-z][a-z0-9-]{2,62}$"
            ),
        },
    ),
}

#: The one tool that starts a registered binary, and the closed set of binaries
#: it starts, read off its contract rather than restated. A skill's
#: `bb:runtime-tools` line is checked against exactly this, so the corpus and
#: the gate cannot come to hold different opinions about which tools exist.
RUN_TOOL = "mcp__rk2__run_tool"
RUN_TOOL_GROUP = CONTRACTS[RUN_TOOL].group
RUN_TOOL_NAMES: tuple[str, ...] = CONTRACTS[RUN_TOOL].arguments["tool"].enum

#: The other half of that group: the registered program a child names by the
#: Skill it holds and the script in it rather than by the registry's own name
#: for the row. Spelled here beside `RUN_TOOL` because the supervisor's handler
#: dispatches on the pair, and a verb spelled in the handler would be a second
#: place this surface is named.
RUN_SKILL_SCRIPT = "mcp__rk2__run_skill_script"

#: The third verb the supervisor answers across that same pipe, and the only one
#: of the three that writes rather than runs. Spelled here for `RUN_TOOL`'s
#: reason and for one more: it is the tool whose absence from that dispatch was
#: the wiring audit's worst finding, so the name the supervisor matches on is
#: taken from the roster that declares it rather than typed a second time.
PROPOSE_FINDING = "mcp__rk2__propose_finding"

#: The verb one step earlier in the same chain, spelled here for the same
#: reason. The supervisor dispatches on it, and a `tests` row is what the
#: proposal above ultimately rests on: without this one there is no Test to run,
#: no run to settle the claim, and nothing for `open_finding` to be asked about.
PROPOSE_TEST = "mcp__rk2__propose_test"

#: And the fourth, spelled here for the same reason as the three above: the
#: supervisor dispatches on the verb, and a verb typed into the dispatch would
#: be this surface named in a second place.
MINT_CALLBACK = "mcp__rk2__mint_callback"

#: The fifth, and the first read among them. Every other state read is answered
#: inside the container out of the document the child was launched with; this one
#: crosses the pipe because the rows it is about were written after that document
#: was compiled, and the side that can see them is the side with a connection.
REFRESH_PACKET = "mcp__rk2__refresh_packet"

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
        # Two recons on one surface collide on the same deduplication cell.
        max_concurrent=1,
    ),
    "web_hunter": Role(
        name="web_hunter",
        runs_as=SUBAGENT,
        invocable_by=("orchestrator",),
        # Two kinds, and the second is ticket 156's. A hunter is the role that
        # already looks at a target and decides what a weakness in it is
        # called, and it already holds `state.propose` -- so `propose_finding`
        # is a tool it has and had no Task that would ever put it in front of a
        # settled claim. `role_task_kinds` is UNIQUE on kind and PRIMARY KEY on
        # (role, kind): one role per kind, several kinds per role.
        task_kinds=("hunt", "conclude"),
        model="opus",
        effort="high",
        max_turns=120,
        builtin_tools=(SKILL,),
        tool_groups=("state.read", "state.propose", "net.request", "exec.tool_run"),
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
        # A Skill is technique. The validator judges, so it holds no Skill tool
        # and the corpus names it in no `bb:roles` line.
        tool_groups=("validate.judge",),
        max_concurrent=1,
    ),
    "performer": Role(
        name="performer",
        runs_as=RENDERER,
        invocable_by=(RUNTIME,),
        task_kinds=("perform",),
        # Not an agent either, and for a stronger reason than the reporter's:
        # a replay walks a specification a hunt already authored, action by
        # action, and the one thing it must not do is decide. Ticket 152.
        model=None,
        effort=None,
        max_turns=0,
        builtin_tools=(),
        tool_groups=(),
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
        max_concurrent=1,
    ),
}

#: Which role runs a Task of each kind, as one lookup rather than a walk over
#: every role's `task_kinds`. Filled by `_check_task_kinds` at import, because
#: it is that check that makes the mapping a function at all: the kind side is
#: total and injective, so exactly one role answers for each kind and a
#: dispatcher has nothing left to choose. Migration 0019's `role_task_kinds` is
#: the same statement with a unique index on `kind`, and the claim reads it to
#: decide the role -- so this is what a runtime checks the claim's answer
#: against, never a second place to decide it.
#:
#: Published read-only over the dictionary the check fills, because everything
#: else this module publishes is a tuple and a caller that could write to this
#: one would be editing the compiled roster from outside the compile.
_ROLE_FOR_KIND: dict[str, str] = {}
ROLE_FOR_KIND: Mapping[str, str] = MappingProxyType(_ROLE_FOR_KIND)

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

        try:
            forbidden = _forbidden_argument(call.arguments, _opaque(tool))
        except _Deeper:
            # The one call the scan cannot answer for. Refused rather than
            # admitted, because what it carries below the bound is unread, and
            # unread is the state a smuggled Program identifier wants the gate
            # to be in.
            return Denial(
                INVALID_ARGUMENT,
                tool,
                role.name,
                f"nests deeper than the {DEPTH} levels the gate reads",
            )
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
        """What may be said, who may be started, by whom, and how many at once.

        The argument set is closed first, because a delegation that overrode
        the model or backgrounded itself would be admitted against a roster it
        had already stepped out of, and the cap it was counted under would be
        given back before the child it counted had finished.
        """
        for name in call.arguments:
            if name not in DELEGATION_ARGUMENTS:
                return Denial(
                    FORBIDDEN_ARGUMENT,
                    DELEGATION,
                    role.name,
                    f"{DELEGATION} takes no argument named {name!r}",
                )
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

    Every contract on this surface is two levels deep at most, so a document
    deeper than `DEPTH` is already not a call any contract describes, and the
    scan stops rather than following it down. It stops by raising: a scan that
    returned `None` there would report "no forbidden name in this document"
    about a document it had not finished reading, and nine wrappers around a
    `program_id` would be a way through the one rule ticket 19 names by itself.
    """
    if not isinstance(value, (Mapping, list, tuple)):
        return None
    if depth >= DEPTH:
        raise _Deeper(depth)
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
    if argument.values_pattern is not None and isinstance(value, Mapping):
        # And by what they hold, for the same reason the names are bounded: a
        # header value that can hold a line break is a header set that can hold
        # a request the caller never declared.
        for name, member in value.items():
            if not isinstance(member, str) or not re.search(argument.values_pattern, member):
                return (
                    f"carries {name!r} as {member!r}, "
                    f"which does not match {argument.values_pattern}"
                )
    if argument.bounds is not None:
        low, high = argument.bounds
        measure = value if isinstance(value, int) else len(value)
        if not low <= measure <= high:
            return f"is outside {low}-{high}"
    if argument.element is not None and isinstance(value, (list, tuple)):
        # The gate's half of the element shape, checked for the reason every
        # other property here is checked twice: the schema is the pair's promise
        # and this is ours. An element that is not an object, or that leaves a
        # field out, is passed over rather than refused -- the subschema does
        # not ask for either, and promotion is where a shapeless element stops
        # being a candidate.
        for one in value:
            if not isinstance(one, Mapping):
                continue
            for member, shape in argument.element.items():
                if member not in one:
                    continue
                fault = _value_fault(shape, one[member])
                if fault is not None:
                    return f"carries {member!r}, which {fault}"
    if argument.element is not None and isinstance(value, Mapping):
        # The same half again for an object that names its fields, which is a
        # claim's `rationale` and nothing else today. A field left out is passed
        # over here as it is above: the subschema does not require it and the
        # grading is what refuses a claim missing one, at a point where refusing
        # it costs that claim rather than the whole submission.
        for member, shape in argument.element.items():
            if member not in value:
                continue
            fault = _value_fault(shape, value[member])
            if fault is not None:
                return f"carries {member!r}, which {fault}"
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
            # tool with nothing granted has the widest surface of all. Only this
            # direction is asked here: the other one -- a grant on a role with no
            # tool to load it -- is `_check_skills`' `has no tool to load a skill
            # with`, which runs first and is where the grant comes from, so a
            # second refusal here could never fire.
            raise RosterError(f"{name}: holds Skill with no skill granted")
        if DELEGATION in role.builtin_tools and role.runs_as != SESSION:
            raise RosterError(f"{name}: only a session delegates")


def _check_skills(corpus: Mapping[str, skills_module.Skill]) -> None:
    """The Skill corpus, against the authority the roles already hold.

    `skill` decides whether a `SKILL.md` is well-formed; this decides whether a
    well-formed one fits. The split is deliberate: the corpus module knows what
    a skill looks like and nothing about roles, which is what lets this one
    import it rather than the other way round.

    Five rules, and they are criterion 4 of the ticket in order. A skill names
    only roles that exist and can execute one at all. A skill needs only tool
    groups its every role already holds -- so instructions never reach for
    authority the compile did not grant, and there is no "the skill requested
    it" path that could grant it. A runtime tool it names is one `run_tool`
    accepts, reached through the group that serves `run_tool`. An
    `allowed-tools` line is a *narrowing* of what the skill itself declared, so
    it can subtract and has nothing to add with. And nothing on that line is a
    forbidden built-in, which is the one rule that would still matter if the
    others were somehow satisfied: a skill that could put `Bash` in front of a
    model has widened the runtime whatever its groups say.

    It rewrites each `Role` with the tuple it derived, for `_check_task_kinds`'
    reason: it is this walk that makes the mapping a mapping, and building it
    anywhere else would be a second place for the corpus and the roster to
    disagree.
    """
    granted: dict[str, list[str]] = {name: [] for name in ROLES}
    for name, one in sorted(corpus.items()):
        # What the skill says about itself first, so a skill naming a group
        # that does not exist is reported as that rather than as every role
        # failing to hold it.
        unknown = sorted(set(one.tool_groups) - set(TOOL_GROUPS))
        if unknown:
            raise RosterError(f"skill {name}: {unknown} is not a tool group")
        forbidden = sorted(set(one.allowed_tools) & set(FORBIDDEN_BUILTINS))
        if forbidden:
            raise RosterError(f"skill {name}: allowed-tools exposes {forbidden}")
        if one.runtime_tools:
            # A runtime tool is run through `run_tool`, whose `tool` argument is
            # a closed enum. A skill naming something outside it is instructing
            # a model to make a call the gate will refuse, which is a corpus
            # that compiles and cannot be followed.
            stranger = sorted(set(one.runtime_tools) - set(RUN_TOOL_NAMES))
            if stranger:
                raise RosterError(f"skill {name}: {stranger} is not a tool run_tool runs")
            if RUN_TOOL_GROUP not in one.tool_groups:
                raise RosterError(f"skill {name}: names runtime tools without {RUN_TOOL_GROUP}")

        # The tools this skill's own declaration reaches, which is what an
        # `allowed-tools` line has to be a subset of. Built from the groups
        # rather than from what the roles hold: a role's other groups are
        # authority this skill did not ask for, and a line that reached into
        # them would be widening in every sense but the arithmetic one.
        declared = {member for group in one.tool_groups for member in TOOL_GROUPS[group]}
        for role_name in one.roles:
            role = ROLES.get(role_name)
            if role is None:
                raise RosterError(f"skill {name}: {role_name} is not a roster role")
            if role.rendered:
                raise RosterError(f"skill {name}: {role_name} runs no model to read it")
            if SKILL not in role.builtin_tools:
                raise RosterError(f"skill {name}: {role_name} has no tool to load a skill with")
            missing = sorted(set(one.tool_groups) - set(role.tool_groups))
            if missing:
                raise RosterError(f"skill {name}: {role_name} does not hold {missing}")
            declared |= set(role.builtin_tools)
            granted[role_name].append(name)

        widening = sorted(set(one.allowed_tools) - declared)
        if widening:
            raise RosterError(f"skill {name}: allowed-tools widens to {widening}")

    # Published only once every rule has held. A partial write would leave the
    # roster describing a corpus that was refused, and `_compile` runs at import
    # where there is nobody to catch the exception and put it back.
    for name, role in ROLES.items():
        ROLES[name] = replace(role, skills=tuple(sorted(granted[name])))


def loadable(one: playbooks_module.Playbook) -> bool:
    """Whether some single role can load every Skill this Playbook names.

    Published rather than left inline in the check below, because the corpus
    gates outside ask the same question by name and two spellings of one rule
    are two rules the day somebody edits one of them. It reads `ROLES` as it
    stands, so it answers about the roster that is loaded rather than about the
    one on disk.
    """
    return any(set(one.skills) <= set(role.skills) for role in ROLES.values())


def _check_playbooks(corpus: Mapping[str, playbooks_module.Playbook]) -> None:
    """The Playbook corpus, against the Skills the roles can actually load.

    Same split as `_check_skills` and for the same reason: `playbook` knows what
    a `playbook.md` looks like and nothing about roles, which is what lets this
    import it rather than the other way round.

    Two rules. A Playbook names Skills that exist -- a name that is not in the
    corpus is a technique nobody wrote, and the selection stage would hand a
    model instructions referring to it. And some single role can load all of
    them at once: a Playbook is executed inside one Agent run, so Skills
    spread across two roles are not a Playbook that runs, they are two halves
    that never meet. Both are refusals rather than warnings because the
    alternative is dead corpus, and dead corpus is worse than an absent Playbook
    -- it looks like the question is covered.

    It runs after `_check_skills`, which is what filled `Role.skills`.
    """
    for name, one in sorted(corpus.items()):
        unknown = sorted(set(one.skills) - set(skills_module.SKILLS))
        if unknown:
            raise RosterError(f"playbook {name}: {unknown} is not a skill")
        if not loadable(one):
            raise RosterError(f"playbook {name}: no role loads {list(one.skills)} at once")


def _check_task_kinds() -> None:
    """The role-to-kind mapping is the schema's: total on kinds, injective.

    It publishes `ROLE_FOR_KIND` as it goes rather than beside it. The two
    properties are exactly what makes the mapping a lookup -- injective, so
    there is one answer, and total, so there is one for every kind -- and a
    dictionary built anywhere else would collapse a duplicate silently into the
    answer this check exists to refuse.
    """
    _ROLE_FOR_KIND.clear()
    for name, role in ROLES.items():
        for kind in role.task_kinds:
            if kind not in TASK_KINDS:
                raise RosterError(f"{name}: {kind} is not a task kind")
            if kind in _ROLE_FOR_KIND:
                raise RosterError(
                    f"{kind} is executed by both {_ROLE_FOR_KIND[kind]} and {name}"
                )
            _ROLE_FOR_KIND[kind] = name
    orphaned = sorted(set(TASK_KINDS) - set(_ROLE_FOR_KIND))
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
    # An object that names its fields is constrained by naming them, and that
    # is not what `constrained` counts. `constrained` is about the *value* an
    # argument carries, which is why `element` on an array stays orthogonal to
    # `free_text` -- an open list is open about what it carries whether or not
    # one field of it is drawn from a vocabulary. An object element is the one
    # place the two meet: a claim's `rationale` has no vocabulary of its own and
    # is not open either, and what binds it is the three fields it is made of.
    constrained = argument.constrained or (
        argument.kind == "object" and argument.element is not None
    )
    if argument.free_text == constrained:
        raise RosterError(f"{tool}.{name}: is either constrained or declared unconstrained")
    if argument.free_text and name not in OPEN_ARGUMENTS.get(tool, ()):
        raise RosterError(f"{tool}.{name}: an unconstrained argument states why it is one")
    if argument.free_text and contract.group == "validate.judge":
        raise RosterError(f"{tool}.{name}: the validator's surface takes no free text")
    if argument.values_pattern is not None and argument.kind != "object":
        raise RosterError(f"{tool}.{name}: only an object's members have values")
    for expression in (argument.pattern, argument.items_pattern, argument.values_pattern):
        if expression is not None:
            try:
                re.compile(expression)
            except re.error as error:
                raise RosterError(f"{tool}.{name}: {error}") from error
    if argument.bounds is not None and argument.bounds[0] > argument.bounds[1]:
        raise RosterError(f"{tool}.{name}: bounds are the wrong way round")
    if argument.element is not None:
        if argument.kind not in ("array", "object"):
            raise RosterError(f"{tool}.{name}: only an array or an object has elements")
        if argument.items_pattern is not None:
            raise RosterError(f"{tool}.{name}: an array of labels has no element fields")
        # Each field checked as the argument it is, which is what makes the
        # nesting worth having: a field named `token` or `model` is refused by
        # `FORBIDDEN_ARGUMENTS` here exactly as a top-level argument would be,
        # and a field declared with no vocabulary at all is refused for being
        # neither constrained nor declared open. An element shape that
        # constrained nothing would be a subschema that promised something and
        # said nothing.
        for member, shape in argument.element.items():
            _check_argument(tool, contract, member, shape)


def _check_authority() -> None:
    """The three sentences the ticket makes about who holds what, as checks."""
    orchestrator = ROLES[ORCHESTRATOR]
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
    # Contracts first: they are what makes `TOOL_GROUPS` a partition of tools
    # that exist, and the two checks after them measure the corpus and the
    # roles against it. Asked in the other order, a group holding a tool
    # nothing serves would be reported as a skill reaching for a tool nobody
    # holds, which is a true sentence about the wrong table.
    _check_contracts()
    # Before `_check_roles`, which asks whether each role's skill list and its
    # `Skill` tool agree -- and the list it asks about is the one this fills.
    _check_skills(skills_module.SKILLS)
    _check_roles(measured)
    # After `_check_skills`, which is what derived the `Role.skills` this reads.
    _check_playbooks(playbooks_module.PLAYBOOKS)
    _check_task_kinds()
    _check_authority()
    return measured


_INVENTORY = _compile()
