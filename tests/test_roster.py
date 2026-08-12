import dataclasses
import hashlib
import json
import unittest
from unittest import mock

from redkraken import roster
from tests import ROOT


#: A role's fields, changed one at a time. The roster is a closed statement, so
#: the way to test a rule is to break exactly the property it is about and
#: recompile -- a hand-written roster in the test would be a second roster, and
#: a rule that passed on it would say nothing about the first.
def altered(name: str, **fields) -> dict:
    return {name: dataclasses.replace(roster.ROLES[name], **fields)}


def observed(**fields) -> dict:
    """The measured inventory with one fact about the pair changed."""
    return {**roster.inventory(), **fields}


def call(tool: str, **arguments) -> roster.Call:
    return roster.Call(tool=tool, arguments=arguments)


class InventoryTest(unittest.TestCase):
    """The measurement the roster is closed against, and the probe behind it."""

    def test_the_pinned_inventory_is_the_one_that_was_measured(self):
        # The digest is the whole reason this file is evidence. Recompiling
        # with a different one is what a hand-edited inventory looks like from
        # in here, and it is a refusal rather than a roster.
        with mock.patch.object(roster, "INVENTORY_SHA256", "0" * 64):
            with self.assertRaises(roster.RosterError) as raised:
                roster._load_inventory()
        self.assertIn("digest changed", str(raised.exception))

    def test_the_inventory_names_the_probe_that_produced_it_and_the_pair(self):
        measured = roster.inventory()
        probe = ROOT / measured["observation"]["probe"]

        self.assertTrue(probe.is_file(), f"{probe} does not exist")
        self.assertEqual(
            ("0.2.132", "2.1.224"),
            (measured["runtime"]["sdk_version"], measured["runtime"]["bundled_cli_version"]),
        )
        # More than one observation, because a list that was not the same twice
        # is not an inventory.
        self.assertGreaterEqual(measured["observation"]["repetitions"], 2)

    def test_the_inventory_is_the_file_on_disk_and_not_a_second_copy(self):
        source = ROOT / "src" / "redkraken" / roster.INVENTORY

        self.assertEqual(json.loads(source.read_text(encoding="utf-8")), roster.inventory())

    def test_an_inventory_this_module_cannot_read_is_not_used_anyway(self):
        # A file that matches its digest and is still not an inventory: the
        # digest says nobody edited it, not that this reader understands it.
        for broken in (
            b"{",
            b'{"schema_version": 2}',
            b'{"schema_version": 1, "builtin_tools": "Read"}',
            b'{"schema_version": 1, "builtin_tools": [1]}',
        ):
            with self.subTest(broken=broken):
                with self.assertRaises(roster.RosterError):
                    self.reading(broken)

    def reading(self, data: bytes):
        stored = mock.Mock(read_bytes=mock.Mock(return_value=data))
        with mock.patch.object(roster, "INVENTORY_SHA256", hashlib.sha256(data).hexdigest()):
            with mock.patch.object(
                roster.resources,
                "files",
                return_value=mock.Mock(joinpath=mock.Mock(return_value=stored)),
            ):
                return roster._load_inventory()


class CompileTest(unittest.TestCase):
    """What the roster refuses to be, checked by making it that and compiling."""

    def compiling(self):
        return self.assertRaises(roster.RosterError)

    def test_the_roster_this_runtime_ships_compiles(self):
        self.assertEqual(roster.inventory(), roster._compile())

    def test_a_grant_naming_a_tool_the_pair_does_not_serve_is_refused(self):
        # This is the silent failure the inventory exists for. An unknown name
        # in `tools` is dropped rather than rejected, so without this check the
        # role would run with one capability fewer than the roster says it has
        # and nothing would say so.
        with mock.patch.dict(roster.ROLES, altered("recon", builtin_tools=("Grep",))):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("not in the observed inventory", str(raised.exception))

    def test_a_prohibition_naming_a_tool_the_pair_does_not_serve_is_refused(self):
        # Worse than the grant: it reads as a closed door, and it is a door
        # that was never in the wall.
        with mock.patch.dict(roster.FORBIDDEN_BUILTINS, {"Glob": "a tool of another CLI"}):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("Glob", str(raised.exception))

    def test_a_tool_the_pair_serves_and_the_roster_ignores_is_refused(self):
        # The partition has to be exact in both directions. A CLI upgrade that
        # adds a tool is a roster that has not classified it, and defaulting
        # either way would be this file deciding by omission.
        for arrival in ("Grep", "PushNotification"):
            with self.subTest(arrival=arrival):
                measured = observed(builtin_tools=[*roster.inventory()["builtin_tools"], arrival])
                with self.compiling() as raised:
                    roster._check_inventory(measured)
                self.assertIn("neither granted nor forbidden", str(raised.exception))

    def test_a_tool_granted_and_forbidden_at_once_is_refused(self):
        with mock.patch.dict(roster.FORBIDDEN_BUILTINS, {roster.SKILL: "contradiction"}):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("granted and forbidden", str(raised.exception))

    def test_every_prohibition_states_why_it_is_one(self):
        with mock.patch.dict(roster.FORBIDDEN_BUILTINS, {"Bash": ""}):
            with self.compiling():
                roster._compile()

    def test_the_delegation_alias_has_to_resolve_to_a_tool_that_exists(self):
        for aliases in ({"Agent": "Delegate"}, {"Bash": roster.DELEGATION}):
            with self.subTest(aliases=aliases):
                with mock.patch.object(roster, "ALIASES", aliases):
                    with self.compiling():
                        roster._compile()

    def test_a_role_that_shares_a_name_with_a_builtin_agent_type_is_refused(self):
        # The delegation argument is one namespace. A role called `Explore`
        # would be a denial rule that reads as an allow rule to whoever writes
        # the next one.
        measured = observed(agent_types=[*roster.inventory()["agent_types"], "validator"])
        with self.compiling() as raised:
            roster._check_inventory(measured)
        self.assertIn("collide with built-in agent types", str(raised.exception))

    def test_an_effort_this_sdk_does_not_accept_is_refused(self):
        with mock.patch.dict(roster.ROLES, altered("validator", effort="maximum")):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("effort", str(raised.exception))

    def test_a_renderer_that_looks_like_an_agent_is_refused(self):
        for fields in (
            {"model": "opus"},
            {"max_turns": 1},
            {"builtin_tools": (roster.SKILL,)},
            {"tool_groups": ("state.read",)},
        ):
            with self.subTest(fields=fields):
                with mock.patch.dict(roster.ROLES, altered("reporter", **fields)):
                    with self.compiling():
                        roster._compile()

    def test_the_skill_tool_and_the_skill_grants_travel_together(self):
        # An empty grant list is read as every skill, so the tool with nothing
        # granted is the widest surface in the roster rather than the narrowest.
        with mock.patch.dict(roster.ROLES, altered("recon", skills=())):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("no skill granted", str(raised.exception))

        with mock.patch.dict(roster.ROLES, altered("orchestrator", skills=("injection",))):
            with self.compiling():
                roster._compile()

    def test_only_a_session_holds_the_delegation_tool(self):
        delegating = altered("recon", builtin_tools=(roster.SKILL, roster.DELEGATION))
        with mock.patch.dict(roster.ROLES, delegating):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("only a session delegates", str(raised.exception))

    def test_a_subagent_the_runtime_could_start_directly_is_refused(self):
        with mock.patch.dict(roster.ROLES, altered("recon", invocable_by=(roster.RUNTIME,))):
            with self.compiling():
                roster._compile()

    def test_the_task_kind_mapping_is_total_and_injective(self):
        with mock.patch.dict(roster.ROLES, altered("recon", task_kinds=())):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("no role executes", str(raised.exception))

        with mock.patch.dict(roster.ROLES, altered("js_analyst", task_kinds=("analyze", "hunt"))):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("executed by both", str(raised.exception))

    def test_a_group_member_without_a_contract_is_refused(self):
        groups = {**roster.TOOL_GROUPS, "state.propose": ("mcp__rk2__submit_anything",)}
        with mock.patch.object(roster, "TOOL_GROUPS", groups):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("groups and contracts disagree", str(raised.exception))

    def test_a_tool_in_two_groups_is_refused(self):
        groups = {**roster.TOOL_GROUPS, "net.request": ("mcp__rk2__http_request", "mcp__rk2__ready")}
        with mock.patch.object(roster, "TOOL_GROUPS", groups):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("two groups", str(raised.exception))

    def test_a_read_tool_that_writes_is_refused(self):
        contract = dataclasses.replace(
            roster.CONTRACTS["mcp__rk2__get_receipts"], writes=("receipts",)
        )
        with mock.patch.dict(roster.CONTRACTS, {"mcp__rk2__get_receipts": contract}):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("proposal named as a getter", str(raised.exception))

    def test_an_argument_that_is_neither_constrained_nor_declared_open_is_refused(self):
        contract = dataclasses.replace(
            roster.CONTRACTS["mcp__rk2__claim_task"],
            arguments={"task_label": roster.Argument("string", required=True)},
        )
        with mock.patch.dict(roster.CONTRACTS, {"mcp__rk2__claim_task": contract}):
            with self.compiling():
                roster._compile()

    def test_an_unconstrained_argument_nobody_declared_is_refused(self):
        contract = dataclasses.replace(
            roster.CONTRACTS["mcp__rk2__claim_task"],
            arguments={"note": roster.Argument("string", free_text=True)},
        )
        with mock.patch.dict(roster.CONTRACTS, {"mcp__rk2__claim_task": contract}):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("states why it is one", str(raised.exception))


class SurfaceTest(unittest.TestCase):
    """What the model-facing surface may not contain, whoever holds it."""

    def test_no_contract_takes_a_program_a_credential_or_raw_sql(self):
        # Program selection first. Every canonical table is program-scoped and
        # the program is bound in the handler from runtime configuration, so an
        # argument naming one would be the agent choosing its own tenant -- and
        # there is no spelling for it, which is stronger than a check that the
        # spelling is refused.
        for name, contract in roster.CONTRACTS.items():
            for argument in contract.arguments:
                with self.subTest(tool=name, argument=argument):
                    self.assertNotIn(argument.lower(), roster.FORBIDDEN_ARGUMENTS)

    def test_no_tool_creates_a_process_the_roster_did_not_enumerate(self):
        # `Bash` is forbidden to every role, and the constrained form that
        # replaces it takes a binary from a closed list rather than a name.
        self.assertIn("Bash", roster.FORBIDDEN_BUILTINS)
        self.assertNotIn("Bash", roster.builtin_grants())

        runner = roster.CONTRACTS["mcp__rk2__run_tool"]
        self.assertTrue(runner.arguments["tool"].enum)
        self.assertFalse(runner.arguments["tool"].free_text)

    def test_a_canonical_row_is_only_ever_written_by_a_commit(self):
        # An agent cannot write canonical state by acting or by proposing. The
        # two tools that reach these tables are the promotion verb and the
        # verdict, and both are decisions rather than observations.
        canonical = {"entities", "hypotheses", "findings", "observations", "verdicts"}
        reached = set()
        for name, contract in roster.CONTRACTS.items():
            if not canonical & set(contract.writes):
                continue
            with self.subTest(tool=name):
                self.assertEqual("commit", contract.direction)
                reached.add(name)

        self.assertEqual({"mcp__rk2__promote", "mcp__rk2__submit_verdict"}, reached)

    def test_a_proposal_reaches_staging_and_stops_there(self):
        proposal = roster.CONTRACTS["mcp__rk2__submit_mission_result"]

        self.assertEqual(("proposals",), proposal.writes)
        for name, role in roster.ROLES.items():
            with self.subTest(role=name):
                self.assertFalse(
                    {"state.propose", "sched.commit"}.issubset(role.tool_groups),
                    f"{name} promotes its own proposals",
                )

    def test_nothing_on_the_validators_surface_takes_free_text(self):
        for name in roster.TOOL_GROUPS["validate.judge"]:
            for argument, declared in roster.CONTRACTS[name].arguments.items():
                with self.subTest(tool=name, argument=argument):
                    self.assertFalse(declared.free_text)
                    self.assertTrue(declared.constrained)


class AuthorityTest(unittest.TestCase):
    """The three sentences about who holds what, read off the compiled roster."""

    def test_the_orchestrator_schedules_and_reads_and_touches_no_target(self):
        orchestrator = roster.ROLES["orchestrator"]

        self.assertEqual((), orchestrator.task_kinds)
        self.assertFalse(orchestrator.executes_tasks)
        self.assertIn("mcp__rk2__offer_slate", orchestrator.tools)
        self.assertIn("mcp__rk2__get_attack_surface", orchestrator.tools)
        self.assertNotIn("mcp__rk2__http_request", orchestrator.tools)
        self.assertNotIn("mcp__rk2__run_tool", orchestrator.tools)
        self.assertNotIn(roster.SKILL, orchestrator.builtin_tools)
        self.assertEqual((), orchestrator.skills)

    def test_the_validator_holds_its_judgement_surface_and_nothing_else(self):
        validator = roster.ROLES["validator"]

        self.assertEqual((), validator.builtin_tools)
        self.assertEqual(
            frozenset(roster.TOOL_GROUPS["validate.judge"]), validator.tools
        )
        # Blind by construction: nothing the orchestrator can say reaches it,
        # because the only channel into it takes one label.
        request = roster.CONTRACTS["mcp__rk2__request_validation"]
        self.assertEqual({"finding_label"}, set(request.arguments))

    def test_the_reporter_runs_no_model(self):
        reporter = roster.ROLES["reporter"]

        self.assertEqual(roster.RENDERER, reporter.runs_as)
        self.assertEqual((None, None, 0), (reporter.model, reporter.effort, reporter.max_turns))
        self.assertEqual(frozenset(), reporter.tools)

    def test_every_role_is_started_by_something_that_may_start_it(self):
        for name, role in roster.ROLES.items():
            with self.subTest(role=name):
                if role.runs_as == roster.SUBAGENT:
                    self.assertEqual(("orchestrator",), role.invocable_by)
                else:
                    self.assertEqual((roster.RUNTIME,), role.invocable_by)


class GateTest(unittest.TestCase):
    """One call at a time, and the rule each one is refused under."""

    def setUp(self):
        self.gate = roster.Gate("orchestrator")

    def denied(self, gate, one_call) -> roster.Denial:
        denial = gate.decide(one_call)
        self.assertIsNotNone(denial, f"{one_call.tool} was allowed")
        return denial

    def delegating(self, target: str, ticket: str) -> roster.Call:
        return roster.Call(
            tool=roster.DELEGATION,
            arguments={roster.SUBAGENT_TYPE: target},
            ticket=ticket,
        )

    def test_a_call_within_the_roles_grants_is_allowed_and_nothing_is_recorded(self):
        self.assertIsNone(self.gate.decide(call(agent_ready())))
        self.assertEqual([], self.gate.denials)

    def test_a_tool_the_role_does_not_hold_is_denied(self):
        for tool in ("Bash", "Read", "WebFetch", "mcp__rk2__http_request"):
            with self.subTest(tool=tool):
                denial = self.denied(self.gate, call(tool))
                self.assertEqual(roster.UNLISTED_TOOL, denial.rule)
                self.assertEqual("orchestrator", denial.role)

    def test_the_older_name_of_the_delegation_tool_is_the_same_tool(self):
        # The pair announces `Task` and has been observed to spell the same
        # tool `Agent` when it reports a denial. An allowlist that knew one
        # spelling would deny half the calls it should allow and allow half the
        # calls it should deny.
        denial = self.denied(self.gate, call("Agent", subagent_type="Explore"))

        self.assertEqual(roster.DELEGATION, denial.tool)
        self.assertEqual(roster.UNKNOWN_AGENT_TYPE, denial.rule)

    def test_a_call_the_runtime_cannot_attribute_to_one_role_is_denied(self):
        for identity, kind in (("agent-1", None), (None, "recon"), ("agent-1", "Explore")):
            with self.subTest(agent_id=identity, agent_type=kind):
                denial = self.denied(
                    self.gate,
                    roster.Call(tool=agent_ready(), agent_id=identity, agent_type=kind),
                )
                self.assertEqual(roster.UNATTRIBUTED, denial.rule)

    def test_a_call_claiming_a_session_role_as_its_type_is_denied(self):
        # `validator` is a roster role and is not one anything delegates to, so
        # a call wearing it is a call from nothing this runtime started.
        denial = self.denied(
            self.gate,
            roster.Call(tool=agent_ready(), agent_id="agent-1", agent_type="validator"),
        )

        self.assertEqual(roster.UNATTRIBUTED, denial.rule)

    def test_a_delegated_call_is_decided_against_its_own_roles_grants(self):
        recon = roster.Call(
            tool="mcp__rk2__http_request", agent_id="agent-1", agent_type="recon"
        )
        self.assertIsNone(self.gate.decide(recon))

        # The same call from the analyst, which holds no network group.
        analyst = roster.Call(
            tool="mcp__rk2__http_request", agent_id="agent-2", agent_type="js_analyst"
        )
        denial = self.denied(self.gate, analyst)
        self.assertEqual((roster.UNLISTED_TOOL, "js_analyst"), (denial.rule, denial.role))

    def test_an_agent_that_changes_what_it_is_between_calls_is_denied(self):
        self.gate.bind("agent-1", "recon")

        self.assertIsNone(self.gate.bind("agent-1", "recon"))
        denial = self.gate.bind("agent-1", "web_hunter")
        self.assertEqual(roster.IMPERSONATION, denial.rule)

        claimed = roster.Call(
            tool="mcp__rk2__http_request", agent_id="agent-1", agent_type="web_hunter"
        )
        self.assertEqual(roster.IMPERSONATION, self.denied(self.gate, claimed).rule)

    def test_a_builtin_agent_type_is_not_a_role_and_is_denied(self):
        # The hole this closes: the pair ships agent types of its own, and one
        # of them started through the delegation tool would be a session with
        # no roster row and therefore no allowlist at all.
        for built_in in roster.inventory()["agent_types"]:
            with self.subTest(agent_type=built_in):
                denial = self.denied(self.gate, self.delegating(built_in, built_in))
                self.assertEqual(roster.UNKNOWN_AGENT_TYPE, denial.rule)

    def test_a_role_the_runtime_starts_cannot_be_reached_by_delegation(self):
        for target in ("validator", "reporter", "orchestrator"):
            with self.subTest(target=target):
                denial = self.denied(self.gate, self.delegating(target, target))
                self.assertEqual(roster.SESSION_ROLE, denial.rule)

    def test_a_delegation_past_the_roles_own_ceiling_is_denied(self):
        for index in range(roster.ROLES["web_hunter"].max_concurrent):
            self.assertIsNone(self.gate.decide(self.delegating("web_hunter", f"t{index}")))

        denial = self.denied(self.gate, self.delegating("web_hunter", "one-too-many"))
        self.assertEqual(roster.OVERFLOW, denial.rule)
        self.assertIn("web_hunter", denial.reason)

    def test_a_delegation_past_the_sessions_ceiling_is_denied(self):
        admitted = [("web_hunter", "a"), ("web_hunter", "b"), ("js_analyst", "c")]
        for target, ticket in admitted:
            self.assertIsNone(self.gate.decide(self.delegating(target, ticket)))
        self.assertEqual(roster.GLOBAL_SUBAGENTS, self.gate.outstanding)

        denial = self.denied(self.gate, self.delegating("recon", "d"))
        self.assertEqual(roster.OVERFLOW, denial.rule)
        self.assertIn("this session", denial.reason)

    def test_a_finished_delegation_gives_its_slot_back_once(self):
        self.assertIsNone(self.gate.decide(self.delegating("recon", "a")))
        self.assertEqual(roster.OVERFLOW, self.denied(self.gate, self.delegating("recon", "b")).rule)

        self.gate.release("a")
        self.gate.release("a")

        self.assertEqual(0, self.gate.outstanding)
        self.assertIsNone(self.gate.decide(self.delegating("recon", "b")))

    def test_one_call_is_admitted_once_however_often_the_gate_sees_it(self):
        # A hook can fire more than once for one tool use. Counting the same
        # ticket twice would refuse the second recon that never started.
        for _ in range(3):
            self.assertIsNone(self.gate.decide(self.delegating("recon", "a")))
        self.assertEqual(1, self.gate.outstanding)

    def test_an_argument_naming_a_program_or_a_credential_is_denied_at_any_depth(self):
        for arguments in (
            {"program_id": "p"},
            {"filter": {"tenant": "other"}},
            {"batch": [{"nested": {"api_key": "x"}}]},
            {"headers": {"Authorization": "Bearer x"}},
        ):
            with self.subTest(arguments=arguments):
                denial = self.denied(
                    self.gate, roster.Call(tool=agent_ready(), arguments=arguments)
                )
                self.assertEqual(roster.FORBIDDEN_ARGUMENT, denial.rule)

    def test_an_argument_deeper_than_the_scan_is_not_searched_forever(self):
        document = {"api_key": "x"}
        for _ in range(roster.DEPTH + 2):
            document = {"next": document}

        self.assertIsNone(roster._forbidden_argument(document))

    def test_a_skill_the_role_was_not_granted_is_denied(self):
        gate = roster.Gate("recon")
        granted = roster.ROLES["recon"].skills[0]

        self.assertIsNone(gate.decide(call(roster.SKILL, skill=granted)))
        for name in ("injection", "", None):
            with self.subTest(skill=name):
                denial = self.denied(gate, call(roster.SKILL, skill=name))
                self.assertEqual(roster.UNGRANTED_SKILL, denial.rule)

    def test_every_denial_is_kept_as_the_runs_own_evidence(self):
        self.gate.decide(call("Bash"))
        self.gate.decide(self.delegating("Explore", "a"))

        self.assertEqual(
            [roster.UNLISTED_TOOL, roster.UNKNOWN_AGENT_TYPE],
            [denial.rule for denial in self.gate.denials],
        )
        for denial in self.gate.denials:
            self.assertEqual(
                {"rule", "tool", "role", "reason"}, set(denial.as_dict())
            )

    def test_a_gate_cannot_be_made_for_a_role_that_does_not_exist(self):
        for name in ("", "hunter", "Explore"):
            with self.subTest(role=name):
                with self.assertRaises(roster.RosterError):
                    roster.Gate(name)


class SurfaceIntersectionTest(unittest.TestCase):
    """What a launch offers, against what the roster grants."""

    def test_the_allowlist_is_the_grants_intersected_with_what_is_served(self):
        # Naming a tool no server provides would be an entry that can never be
        # exercised; serving one the roster withholds would be a tool the gate
        # denies at every call instead of one nobody offered.
        self.assertEqual(
            ["mcp__rk2__ready"], roster.allowed_tools("orchestrator", ["mcp__rk2__ready"])
        )
        self.assertEqual([], roster.allowed_tools("validator", ["mcp__rk2__ready"]))
        self.assertEqual([], roster.allowed_tools("orchestrator", []))

    def test_what_a_role_is_shown_is_never_wider_than_what_it_holds(self):
        for name, role in roster.ROLES.items():
            with self.subTest(role=name):
                self.assertTrue(set(roster.visible_tools(name)).issubset(role.tools))

    def test_a_visible_tool_is_still_denied_when_the_roster_withholds_it(self):
        # The claim the deny canary proves against a running child, stated here
        # against the decision itself: what the model can see and what the
        # permission mode allows are not what decides.
        gate = roster.Gate("js_analyst")

        self.assertEqual(
            roster.UNLISTED_TOOL, gate.decide(call("mcp__rk2__http_request")).rule
        )


def agent_ready() -> str:
    """The one tool a launch serves today, spelled the way the CLI spells it."""
    return "mcp__rk2__ready"


if __name__ == "__main__":
    unittest.main()
