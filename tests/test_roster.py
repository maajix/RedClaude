import dataclasses
import hashlib
import json
import re
import unittest
from unittest import mock

from redkraken import roster, skill
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

    def test_the_inventory_says_what_each_alias_a_role_names_resolves_to(self):
        # What a role names is an alias; what it runs is what the pair resolves
        # that alias to, and the second is the one that had to be measured.
        models = roster.inventory()["models"]

        self.assertEqual("claude-opus-5", models["opus"])
        for name, role in roster.ROLES.items():
            with self.subTest(role=name):
                self.assertTrue(role.rendered or role.model in models)

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
            json.dumps(
                {**roster.inventory(), "models": ["opus"]}
            ).encode(),
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
        # role would run with one tool fewer than the roster says it has and
        # nothing would say so.
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
        # Broken through the corpus, because the corpus is where the grants are
        # stated: a role's `skills` is filled from it and cannot be set here.
        thinned = {
            name: one for name, one in skill.SKILLS.items() if "recon" not in one.roles
        }
        # `patch.dict` with nothing to change, because `_check_skills` writes
        # the grants onto `ROLES` and the compile below fails after it: without
        # a snapshot the roster would stay thinned for every test after this.
        with mock.patch.dict(roster.ROLES), mock.patch.object(skill, "SKILLS", thinned):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("no skill granted", str(raised.exception))

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
        groups = {
            **roster.TOOL_GROUPS,
            "net.request": ("mcp__rk2__http_request", "mcp__rk2__get_receipts"),
        }
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
            roster.CONTRACTS["mcp__rk2__pick_task"],
            arguments={"task_label": roster.Argument("string", required=True)},
        )
        with mock.patch.dict(roster.CONTRACTS, {"mcp__rk2__pick_task": contract}):
            with self.compiling():
                roster._compile()

    def test_a_bounded_string_is_constrained_and_needs_no_open_declaration(self):
        # The mirror of the case above. `bounds` is one of the things
        # `constrained` reads, so a string carrying one is a declared shape
        # rather than free text and `OPEN_ARGUMENTS` has nothing to say about
        # it -- which is the property a bounded string argument rests on.
        contract = dataclasses.replace(
            roster.CONTRACTS["mcp__rk2__pick_task"],
            arguments={"task_label": roster.Argument("string", bounds=(1, 65536))},
        )
        self.assertTrue(contract.arguments["task_label"].constrained)
        with mock.patch.dict(roster.CONTRACTS, {"mcp__rk2__pick_task": contract}):
            roster._compile()

    def test_a_contract_that_writes_a_canonical_table_is_refused(self):
        # The rule that keeps promotion the runtime's. A tool reaching one of
        # these would be an agent writing canonical truth directly, and the
        # group it was filed under would not change that.
        for table in ("findings", "hypotheses", "tasks"):
            with self.subTest(table=table):
                contract = dataclasses.replace(
                    roster.CONTRACTS["mcp__rk2__pick_task"], writes=(table,)
                )
                with mock.patch.dict(roster.CONTRACTS, {"mcp__rk2__pick_task": contract}):
                    with self.compiling() as raised:
                        roster._compile()
                self.assertIn("writes canonical state directly", str(raised.exception))

    def test_a_verdict_written_by_anything_but_a_judgement_is_refused(self):
        contract = dataclasses.replace(
            roster.CONTRACTS["mcp__rk2__request_validation"], writes=("verdicts",)
        )
        with mock.patch.dict(roster.CONTRACTS, {"mcp__rk2__request_validation": contract}):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("a judgement's and no other's", str(raised.exception))

    def test_a_direction_this_roster_does_not_have_is_refused(self):
        for direction in ("commit", "write", ""):
            with self.subTest(direction=direction):
                contract = dataclasses.replace(
                    roster.CONTRACTS["mcp__rk2__get_slate"], direction=direction
                )
                with mock.patch.dict(roster.CONTRACTS, {"mcp__rk2__get_slate": contract}):
                    with self.compiling() as raised:
                        roster._compile()
                self.assertIn("is not a direction", str(raised.exception))

    def test_an_argument_shape_the_gate_cannot_check_is_refused(self):
        # `kind` is load-bearing: the gate types a value against it, so a shape
        # nothing implements would be an argument nothing checks.
        contract = dataclasses.replace(
            roster.CONTRACTS["mcp__rk2__get_slate"],
            arguments={"limit": roster.Argument("number", bounds=(1, 5))},
        )
        with mock.patch.dict(roster.CONTRACTS, {"mcp__rk2__get_slate": contract}):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("is not a value shape", str(raised.exception))

    def test_a_value_pattern_on_something_with_no_values_is_refused(self):
        # `values_pattern` binds what an object's members hold. On a string it
        # would bind nothing while reading as a constraint, which is the one
        # way an argument can look checked and be open.
        contract = dataclasses.replace(
            roster.CONTRACTS["mcp__rk2__get_slate"],
            arguments={"note": roster.Argument("string", values_pattern="^[a-z]+\\Z")},
        )
        with mock.patch.dict(roster.CONTRACTS, {"mcp__rk2__get_slate": contract}):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("only an object's members have values", str(raised.exception))

    def test_a_model_alias_the_pair_does_not_resolve_is_refused(self):
        # An alias is a request. A role naming one the pair does not know would
        # still start -- on some other model, and without saying which.
        with mock.patch.dict(roster.ROLES, altered("recon", model="claude-3")):
            with self.compiling() as raised:
                roster._compile()
        self.assertIn("is not a model alias this pair resolves", str(raised.exception))

    def test_an_unconstrained_argument_nobody_declared_is_refused(self):
        contract = dataclasses.replace(
            roster.CONTRACTS["mcp__rk2__pick_task"],
            arguments={"note": roster.Argument("string", free_text=True)},
        )
        with mock.patch.dict(roster.CONTRACTS, {"mcp__rk2__pick_task": contract}):
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

    def test_no_tool_names_the_environment_or_the_settings_a_launch_was_given(self):
        """Story 95's third noun, beside credentials and environment variables.

        Every name here is decided by the roster or by the launcher and then
        re-checked against the roster before a child starts, so an argument
        spelling one would be the model choosing what it was started as. The
        contracts are asked by the loop above; this asks the surface a built-in
        arrives on, which has no contract to be closed against.
        """
        self.assertLessEqual(
            {"env", "environment", "settings", "cwd", "model", "isolation"},
            roster.FORBIDDEN_SETTINGS,
        )
        self.assertLessEqual(roster.FORBIDDEN_SETTINGS, roster.FORBIDDEN_ARGUMENTS)
        for name in sorted(roster.FORBIDDEN_SETTINGS):
            with self.subTest(argument=name):
                self.assertEqual(name, roster._forbidden_argument({name: "x"}))

    def test_no_tool_creates_a_process_the_roster_did_not_enumerate(self):
        # `Bash` is forbidden to every role, and the constrained form that
        # replaces it takes a binary from a closed list rather than a name.
        self.assertIn("Bash", roster.FORBIDDEN_BUILTINS)
        self.assertNotIn("Bash", roster.granted_builtins())

        runner = roster.CONTRACTS["mcp__rk2__run_tool"]
        self.assertTrue(runner.arguments["tool"].enum)
        self.assertFalse(runner.arguments["tool"].free_text)

    def test_no_model_facing_tool_writes_canonical_state_at_all(self):
        # Nothing an agent returns is true before promotion, and promotion is a
        # runtime step -- so there is no model-facing verb for it, not a
        # narrow one. The strongest thing on this surface asks the runtime.
        for name, contract in roster.CONTRACTS.items():
            with self.subTest(tool=name):
                self.assertEqual((), tuple(set(contract.writes) & set(roster.CANONICAL)))
                self.assertIn(contract.direction, roster.DIRECTIONS)
        self.assertNotIn("commit", roster.DIRECTIONS)
        self.assertNotIn(
            "mcp__rk2__promote",
            {member for group in roster.TOOL_GROUPS.values() for member in group},
        )

    def test_the_one_row_this_surface_decides_is_the_validators_verdict(self):
        # The exception, and it is not a general one: a verdict is the
        # validator's own output, and what the Finding's status becomes is
        # still a runtime step taken from this row and a holding replay.
        writers = {
            name for name, contract in roster.CONTRACTS.items() if "verdicts" in contract.writes
        }

        self.assertEqual({"mcp__rk2__submit_verdict"}, writers)
        self.assertEqual(roster.JUDGE, roster.CONTRACTS["mcp__rk2__submit_verdict"].direction)

    def test_a_proposal_reaches_staging_and_stops_there(self):
        proposal = roster.CONTRACTS["mcp__rk2__submit_mission_result"]

        # Both staging tables, because `proposal.stage` writes both in one
        # transaction: a contract naming only `proposals` would describe a
        # write the runtime does not make on its own.
        self.assertEqual(roster.STAGING, proposal.writes)
        self.assertEqual(("proposals", "proposal_drops"), roster.STAGING)
        for name, role in roster.ROLES.items():
            with self.subTest(role=name):
                self.assertFalse(
                    {"state.propose", "sched.pick"}.issubset(role.tool_groups),
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
        self.assertIn("mcp__rk2__get_slate", orchestrator.tools)
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
                if role.delegated:
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
        self.assertIsNone(self.gate.decide(call(agent_read())))
        self.assertEqual([], self.gate.denials)

    def test_a_tool_the_role_does_not_hold_is_denied(self):
        for tool in ("Bash", "Read", "WebFetch", "mcp__rk2__http_request"):
            with self.subTest(tool=tool):
                denial = self.denied(self.gate, call(tool))
                self.assertEqual(roster.UNLISTED_TOOL, denial.rule)
                self.assertEqual("orchestrator", denial.role)

    def test_a_delegation_says_only_what_the_roster_reads(self):
        """Story 93: built-in delegation cannot escape the roster.

        The bundled CLI ships three further fields on this tool, and each one
        undoes something the roster decided: `model` overrides the row the
        launch is assessed against, `isolation` chooses a filesystem topology,
        and `run_in_background` returns at launch rather than at completion,
        which frees the cap's slot while the child is still running.
        """
        self.assertIsNone(
            self.gate.decide(
                roster.Call(
                    tool=roster.DELEGATION,
                    arguments={
                        "description": "hunt this",
                        "prompt": "the objective",
                        roster.SUBAGENT_TYPE: "web_hunter",
                    },
                    ticket="admitted",
                )
            )
        )
        for name, value in (
            ("model", "opus"),
            ("isolation", "worktree"),
            ("run_in_background", True),
            ("anything_else", 1),
        ):
            with self.subTest(argument=name):
                denial = self.denied(
                    roster.Gate("orchestrator"),
                    roster.Call(
                        tool=roster.DELEGATION,
                        arguments={roster.SUBAGENT_TYPE: "web_hunter", name: value},
                        ticket=name,
                    ),
                )
                self.assertEqual(roster.FORBIDDEN_ARGUMENT, denial.rule)
                self.assertIn(name, denial.reason)

    def test_a_backgrounded_delegation_cannot_hand_its_slot_back_early(self):
        """The cap consequence of the argument above, asked as the count.

        `PostToolUse` fires when the tool returns, and a backgrounded `Task`
        returns at launch. Admitting one would release its slot while the child
        ran, so the ceiling would be as wide as the session cared to make it.
        """
        gate = roster.Gate("orchestrator")
        for attempt in range(roster.ROLES["web_hunter"].max_concurrent + 3):
            gate.decide(
                roster.Call(
                    tool=roster.DELEGATION,
                    arguments={
                        roster.SUBAGENT_TYPE: "web_hunter",
                        "run_in_background": True,
                    },
                    ticket=f"backgrounded-{attempt}",
                )
            )
            gate.release(f"backgrounded-{attempt}")

        self.assertEqual(0, gate.outstanding)
        self.assertEqual(
            [roster.FORBIDDEN_ARGUMENT] * (roster.ROLES["web_hunter"].max_concurrent + 3),
            [denial.rule for denial in gate.denials],
        )

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
                    roster.Call(tool=agent_read(), agent_id=identity, agent_type=kind),
                )
                self.assertEqual(roster.UNATTRIBUTED, denial.rule)

    def test_a_call_claiming_a_session_role_as_its_type_is_denied(self):
        # `validator` is a roster role and is not one anything delegates to, so
        # a call wearing it is a call from nothing this runtime started.
        denial = self.denied(
            self.gate,
            roster.Call(tool=agent_read(), agent_id="agent-1", agent_type="validator"),
        )

        self.assertEqual(roster.UNATTRIBUTED, denial.rule)

    def test_a_call_from_an_agent_the_runtime_never_saw_start_is_denied(self):
        # `SubagentStart` is what makes an agent id an attribution rather than
        # a claim, so a call that arrives without one is refused rather than
        # believed and recorded. Fail-closed: a hook this runtime stopped
        # registering would close the gate, not open it.
        unannounced = roster.Call(tool=agent_read(), agent_id="agent-9", agent_type="recon")

        denial = self.denied(self.gate, unannounced)
        self.assertEqual(roster.UNATTRIBUTED, denial.rule)
        self.assertIn("before the runtime saw it start", denial.reason)

        self.gate.bind("agent-9", "recon")
        self.assertIsNone(self.gate.decide(unannounced))

    def test_a_delegated_call_is_decided_against_its_own_roles_tools(self):
        self.gate.bind("agent-1", "recon")
        self.gate.bind("agent-2", "js_analyst")
        recon = roster.Call(
            tool="mcp__rk2__http_request",
            arguments={"method": "GET", "url": "https://example.test/"},
            agent_id="agent-1",
            agent_type="recon",
        )
        self.assertIsNone(self.gate.decide(recon))

        # The same call from the analyst, which holds no network group.
        analyst = dataclasses.replace(recon, agent_id="agent-2", agent_type="js_analyst")
        denial = self.denied(self.gate, analyst)
        self.assertEqual((roster.UNLISTED_TOOL, "js_analyst"), (denial.rule, denial.role))

    def test_an_agent_that_changes_what_it_is_between_calls_is_denied(self):
        self.gate.bind("agent-1", "recon")

        self.assertIsNone(self.gate.bind("agent-1", "recon"))
        announced = self.gate.bind("agent-1", "web_hunter")
        self.assertEqual(roster.IMPERSONATION, announced.rule)

        claimed = roster.Call(
            tool="mcp__rk2__http_request", agent_id="agent-1", agent_type="web_hunter"
        )
        called = self.denied(self.gate, claimed)
        self.assertEqual(roster.IMPERSONATION, called.rule)
        # One violation seen from two hooks is one denial: the same sentence
        # and the same role, so an operator reading two records reads one fact.
        self.assertEqual(
            (announced.role, announced.reason), (called.role, called.reason)
        )
        self.assertEqual("recon", called.role)

    def test_a_builtin_agent_type_is_not_a_role_and_is_denied(self):
        # The hole this closes: the pair ships agent types of its own, and one
        # of them started through the delegation tool would be a session with
        # no roster row and therefore nothing to decide it against.
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
        self.assertEqual(roster.DEFAULT_SUBAGENTS, self.gate.outstanding)

        denial = self.denied(self.gate, self.delegating("recon", "d"))
        self.assertEqual(roster.OVERFLOW, denial.rule)
        self.assertIn("this session", denial.reason)

    def test_a_lowered_cap_refuses_a_delegation_the_default_would_admit(self):
        # PH2-73. The ceiling is `scheduler_weights.max_concurrent_subagents`,
        # which the runtime reads with the claim and gives to the gate, so the
        # gate refuses at whatever the scheduler offered under. `web_hunter`
        # runs two at a time, so nothing but the session's own cap refuses the
        # second one here.
        gate = roster.Gate("orchestrator", 1)
        self.assertIsNone(gate.decide(self.delegating("web_hunter", "a")))

        denial = self.denied(gate, self.delegating("web_hunter", "b"))
        self.assertEqual(roster.OVERFLOW, denial.rule)
        self.assertIn("this session", denial.reason)

    def test_a_raised_cap_admits_the_delegation_the_default_would_refuse(self):
        # The other direction, which is the one that used to end in a claimed
        # Task with no child: the scheduler offers a fourth subagent, the
        # orchestrator delegates it, and a gate holding its own constant denies
        # it. Every target here is inside its own role's ceiling of two, so the
        # session's cap is the only thing that could refuse any of them.
        admitted = (("web_hunter", "a"), ("web_hunter", "b"),
                    ("js_analyst", "c"), ("js_analyst", "d"))
        self.assertGreater(len(admitted), roster.DEFAULT_SUBAGENTS)
        gate = roster.Gate("orchestrator", len(admitted))

        for target, ticket in admitted:
            self.assertIsNone(gate.decide(self.delegating(target, ticket)))

        denial = self.denied(gate, self.delegating("recon", "e"))
        self.assertEqual(roster.OVERFLOW, denial.rule)
        self.assertIn(str(len(admitted)), denial.reason)

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

    def test_a_delegation_with_no_ticket_still_holds_a_slot_of_its_own(self):
        # The key a ticketless admission gets has to be new every time. Keyed
        # by the current count, an admission either side of a release would
        # take the key the released one had, and two running hunters would be
        # counted as one.
        ticketless = roster.Call(
            tool=roster.DELEGATION, arguments={roster.SUBAGENT_TYPE: "web_hunter"}
        )
        self.assertIsNone(self.gate.decide(ticketless))
        self.assertIsNone(self.gate.decide(self.delegating("web_hunter", "a")))
        self.gate.release("a")
        self.assertIsNone(self.gate.decide(ticketless))

        self.assertEqual(2, self.gate.outstanding)
        self.assertEqual(roster.OVERFLOW, self.denied(self.gate, ticketless).rule)

    def test_an_argument_naming_a_program_or_a_credential_is_denied_at_any_depth(self):
        for arguments in (
            {"program_id": "p"},
            {"filter": {"tenant": "other"}},
            {"batch": [{"nested": {"api_key": "x"}}]},
            {"headers": {"Authorization": "Bearer x"}},
        ):
            with self.subTest(arguments=arguments):
                denial = self.denied(
                    self.gate, roster.Call(tool=agent_read(), arguments=arguments)
                )
                self.assertEqual(roster.FORBIDDEN_ARGUMENT, denial.rule)

    def test_an_observation_about_a_credential_is_not_read_as_one_being_passed(self):
        # The two sets are not one set. A Program selector is refused wherever
        # it appears, because a call that carries one is a call trying to
        # choose its own Program. An instruction word is refused only in an
        # argument the runtime interprets -- inside a free-text element it is
        # the hunter's own report, and "an exposed password" is the output this
        # harness exists to produce, not an attempt to send one.
        hunter = roster.Gate("web_hunter")
        hunter.bind("agent-1", "web_hunter")

        def submitting(**observation) -> roster.Call:
            return roster.Call(
                tool="mcp__rk2__submit_mission_result",
                arguments={
                    "observations": [observation],
                    "completion_claim": {"status": "complete"},
                },
                agent_id="agent-1",
                agent_type="web_hunter",
            )

        self.assertIsNone(
            hunter.decide(submitting(note="password reflected", secret="AKIA...", sql="' OR 1=1"))
        )
        for leaked in ({"program_id": "other"}, {"where": {"tenant": "other"}}):
            with self.subTest(observation=leaked):
                denial = self.denied(hunter, submitting(**leaked))
                self.assertEqual(roster.FORBIDDEN_ARGUMENT, denial.rule)

    def test_a_call_that_does_not_fit_its_contract_is_denied(self):
        # The contract is the tool's whole surface, so the enum on `run_tool`
        # is a rule the gate carries rather than a description of a handler's
        # own check. Every one of these is a call the CLI would have dispatched.
        hunter = roster.Gate("web_hunter")
        hunter.bind("agent-1", "web_hunter")

        def hunting(name: str, **arguments) -> roster.Call:
            return roster.Call(
                tool=name, arguments=arguments, agent_id="agent-1", agent_type="web_hunter"
            )

        self.assertIsNone(
            hunter.decide(
                hunting("mcp__rk2__run_tool", tool="jq", arguments={"filter": ".", "input": "A1"})
            )
        )
        for one_call in (
            # A binary the roster did not enumerate.
            hunting("mcp__rk2__run_tool", tool="bash", arguments={}),
            # A required argument that is not there.
            hunting("mcp__rk2__run_tool", tool="jq"),
            # An argument no contract declares.
            hunting("mcp__rk2__run_tool", tool="jq", arguments={}, shell=True),
            # A value of the wrong shape.
            hunting("mcp__rk2__run_tool", tool="jq", arguments="filter ."),
            # A key that is not a name any registry row could carry.
            hunting("mcp__rk2__run_tool", tool="jq", arguments={"Filter": "."}),
            # A string that does not match the pattern its argument declares.
            hunting("mcp__rk2__http_request", method="GET", url="file:///etc/passwd"),
            # A string that is not a label the database has ever issued -- and
            # in particular, a hash, which is what this argument used to take.
            hunting("mcp__rk2__get_artifact", artifact_label="a" * 64),
            # A member of an array that does not match the item pattern.
            hunting("mcp__rk2__get_receipts", receipt_labels=["R1", "not-a-label"]),
            # A header name outside the shape the roster bounds them to.
            hunting(
                "mcp__rk2__http_request",
                method="GET",
                url="https://x",
                headers={"X Bad Name": "v"},
            ),
            # A header value carrying a request of its own.
            hunting(
                "mcp__rk2__http_request",
                method="GET",
                url="https://x",
                headers={"X-Trace": "a\r\nX-Injected: b"},
            ),
            # And the trailing newline that `$` would have let through, which
            # is the same smuggling with the second line still to come.
            hunting(
                "mcp__rk2__http_request",
                method="GET",
                url="https://x",
                headers={"X-Trace": "a\n"},
            ),
            # The two arguments this contract used to declare and the runtime
            # never served: a body the child has no store to name, and an
            # identity the runtime chose before the child started.
            hunting(
                "mcp__rk2__http_request",
                method="GET",
                url="https://x",
                body_artifact_hash="a" * 64,
            ),
            hunting(
                "mcp__rk2__http_request",
                method="GET",
                url="https://x",
                identity_slot="operator",
            ),
            # A number outside its bounds.
            hunting("mcp__rk2__get_attack_surface", limit=0),
        ):
            with self.subTest(arguments=dict(one_call.arguments)):
                denial = self.denied(hunter, one_call)
                self.assertEqual(roster.INVALID_ARGUMENT, denial.rule)
                self.assertEqual("web_hunter", denial.role)

    def test_a_flag_where_a_count_belongs_is_not_an_integer(self):
        # `True` is an `int` in Python and is not one here.
        self.assertIsNotNone(
            roster._value_fault(roster.Argument("integer", bounds=(1, 200)), True)
        )

    def test_a_bounded_string_is_refused_by_its_length_and_not_by_its_value(self):
        # The gate measures a string by `len` whatever the served schema said,
        # and that half was always right. It is asserted here because the
        # schema now says `maxLength`: the two are one statement, and this is
        # the sentence the served document was corrected to repeat.
        bounded = roster.Argument("string", bounds=(1, 8))

        self.assertIsNone(roster._value_fault(bounded, "a" * 8))
        self.assertEqual("is outside 1-8", roster._value_fault(bounded, "a" * 9))
        self.assertEqual("is outside 1-8", roster._value_fault(bounded, ""))

    def test_a_builtin_tool_is_not_argument_checked_against_a_contract_it_has_none_of(self):
        # True of the contract check and only of it: `CONTRACTS` is the set of
        # schemas this runtime serves, and `Task` is served by the CLI. The
        # closed set for it is `DELEGATION_ARGUMENTS`, and the gate carries it,
        # so the same call is still refused a layer further in.
        self.assertIsNone(roster._argument_fault(roster.DELEGATION, {"anything": 1}))
        self.assertIsNotNone(
            roster.Gate("orchestrator").decide(
                call(roster.DELEGATION, subagent_type="web_hunter", anything=1)
            )
        )

    def test_a_document_the_scan_cannot_read_to_the_bottom_is_denied(self):
        # The bound is not a way through. Stopping at it used to answer "no
        # forbidden name here" about a document the scan had not finished, so
        # a `program_id` under one wrapper more than the bound was neither
        # seen nor refused -- and a free-text element declares no shape, so
        # the wrappers cost the caller nothing.
        document = {"api_key": "x"}
        for _ in range(roster.DEPTH + 2):
            document = {"next": document}

        with self.assertRaises(roster._Deeper):
            roster._forbidden_argument(document)

        denial = self.denied(self.gate, roster.Call(tool=agent_read(), arguments=document))
        self.assertEqual(roster.INVALID_ARGUMENT, denial.rule)
        self.assertIn(f"deeper than the {roster.DEPTH} levels", denial.reason)

    def test_a_program_selector_wrapped_past_the_bound_is_denied_inside_free_text(self):
        # The case the bound made reachable, on the surface that made it cheap:
        # `observations` is `free_text`, so its served schema is `{"type":
        # "array"}` and nothing objects to the wrappers on the way down.
        hunter = roster.Gate("web_hunter")
        hunter.bind("agent-1", "web_hunter")
        smuggled = {"program_id": "other-program"}
        for _ in range(roster.DEPTH):
            smuggled = {"a": smuggled}

        denial = self.denied(
            hunter,
            roster.Call(
                tool="mcp__rk2__submit_mission_result",
                arguments={
                    "observations": [smuggled],
                    "completion_claim": {"status": "complete"},
                },
                agent_id="agent-1",
                agent_type="web_hunter",
            ),
        )
        self.assertEqual(roster.INVALID_ARGUMENT, denial.rule)
        self.assertIn(f"deeper than the {roster.DEPTH} levels", denial.reason)

    def test_an_element_as_deep_as_a_real_one_is_still_admitted(self):
        # The bound refuses now, so it has to sit clear of anything a hunter
        # would actually file. This is deeper than any contract describes and
        # is still read to the bottom rather than refused.
        hunter = roster.Gate("web_hunter")
        hunter.bind("agent-1", "web_hunter")

        self.assertIsNone(
            hunter.decide(
                roster.Call(
                    tool="mcp__rk2__submit_mission_result",
                    arguments={
                        "observations": [
                            {
                                "note": "reflected",
                                "request": {
                                    "headers": {"Cookie": {"parsed": {"session": ["a", "b"]}}}
                                },
                            }
                        ],
                        "completion_claim": {"status": "complete"},
                    },
                    agent_id="agent-1",
                    agent_type="web_hunter",
                )
            )
        )

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

    def test_a_gate_cannot_be_made_for_a_concurrency_that_holds_nothing(self):
        # The schema's own `CHECK (max_concurrent_subagents >= 1)`, asked where
        # the number is spent. A session that may hold no delegation is not a
        # stricter cap, it is an orchestrator that cannot do its work, and the
        # honest place to say so is before the run is started.
        for subagent_cap in (0, -1):
            with self.subTest(subagent_cap=subagent_cap):
                with self.assertRaises(roster.RosterError):
                    roster.Gate("orchestrator", subagent_cap)


class SurfaceIntersectionTest(unittest.TestCase):
    """What a launch offers, against what the roster grants."""

    def test_the_enforced_list_is_the_roles_tools_intersected_with_what_is_served(self):
        # Naming a tool no server provides would be an entry that can never be
        # exercised; serving one the roster withholds would be a tool the gate
        # denies at every call instead of one nobody offered.
        orchestrator, validator = roster.ROLES["orchestrator"], roster.ROLES["validator"]

        self.assertEqual([agent_read()], orchestrator.allowed_tools([agent_read()]))
        self.assertEqual([], validator.allowed_tools([agent_read()]))
        self.assertEqual([], orchestrator.allowed_tools([]))

    def test_what_a_role_is_shown_is_never_wider_than_what_it_holds(self):
        for name, role in roster.ROLES.items():
            with self.subTest(role=name):
                self.assertTrue(set(role.visible_tools).issubset(role.tools))

    def test_a_visible_tool_is_still_denied_when_the_roster_withholds_it(self):
        # The claim the deny canary proves against a running child, stated here
        # against the decision itself: what the model can see and what the
        # permission mode allows are not what decides.
        gate = roster.Gate("js_analyst")

        self.assertEqual(
            roster.UNLISTED_TOOL, gate.decide(call("mcp__rk2__http_request")).rule
        )


class SchemaAgreementTest(unittest.TestCase):
    """The roster and migration 0019 are two statements of one thing.

    The migration is generated from a roster and the database enforces its
    copy, so the two drifting apart is a scheduler admitting a role this file
    would refuse. Read as text rather than through a connection: the claim is
    that the two documents agree, and that is true with or without a database.
    """

    ROWS = re.compile(
        r"\('(?P<role>\w+)', '(?P<runs_as>\w+)', "
        r"ARRAY\['(?P<invocable_by>\w+)'\]::text\[\], "
        r"(?P<executes_tasks>true|false), (?P<max_concurrent>\d+), (?P<clamp>true|false)\)"
    )
    KINDS = re.compile(r"\('(?P<role>\w+)', '(?P<kind>\w+)'\)")
    #: PH2-71's `UPDATE roles ... FROM (VALUES ...)`. A second file because the
    #: two columns were added after 019 was applied and a migration cannot be
    #: edited once it has a recorded checksum, so the roster's statement of a
    #: role is spread over two documents and this test is what keeps that from
    #: mattering. A seventh role has to be written into both, and a seventh
    #: written into only one fails here rather than at its first claim.
    MODEL_AND_EFFORT = re.compile(
        r"\('(?P<role>\w+)', +'(?P<model>[\w.-]+)', +'(?P<effort>\w+)'\)"
    )
    #: 019's cross-role cap, which is the only one of these numbers this file
    #: does not own: `scheduler_weights` is a versioned row an operator moves.
    DEFAULT_SUBAGENTS = re.compile(
        r"max_concurrent_subagents smallint NOT NULL DEFAULT (?P<cap>\d+)"
    )

    @classmethod
    def setUpClass(cls):
        migrations = ROOT / "src" / "redkraken" / "migrations"
        cls.sql = (migrations / "0019_role_kinds.sql").read_text(encoding="utf-8")
        cls.model_and_effort_sql = (
            migrations / "20260813T200000Z__a_role_runs_at_the_rosters_model_and_effort.sql"
        ).read_text(encoding="utf-8")

    def statement(self, prefix: str, sql: str | None = None) -> str:
        text = self.sql if sql is None else sql
        start = text.index(prefix)
        return text[start : text.index(";", start)]

    def test_every_role_row_the_schema_carries_is_this_rosters_row(self):
        rows = self.ROWS.finditer(self.statement("INSERT INTO roles"))
        stated = {}
        for row in rows:
            role = roster.ROLES[row["role"]]
            stated[row["role"]] = (
                row["runs_as"],
                (row["invocable_by"],),
                row["executes_tasks"] == "true",
                int(row["max_concurrent"]),
                row["clamp"] == "true",
            )
            with self.subTest(role=row["role"]):
                self.assertEqual(
                    stated[row["role"]],
                    (
                        role.runs_as,
                        role.invocable_by,
                        role.executes_tasks,
                        role.max_concurrent,
                        role.clamp_to_identity_leases,
                    ),
                )
        self.assertEqual(set(roster.ROLES), set(stated))

    def test_every_role_runs_at_the_model_and_effort_this_roster_gives_it(self):
        # PH2-71. The scheduler used to decide both from `runs_as`, so three of
        # the five agent roles ran at a model and an effort this file does not
        # state. They are a roster row now, and this is the assertion that keeps
        # them one statement: a roster edit the migration does not follow fails
        # here rather than in a claim nobody is watching.
        stated = {}
        for row in self.MODEL_AND_EFFORT.finditer(
            self.statement("UPDATE roles r SET", self.model_and_effort_sql)
        ):
            role = roster.ROLES[row["role"]]
            stated[row["role"]] = (row["model"], row["effort"])
            with self.subTest(role=row["role"]):
                # `None` is the renderer, which is not an agent at all. The
                # column is NOT NULL because every other role's number is a
                # fact, so 'none' is how the schema says "has none" -- the same
                # spelling `agent_runs` has used since 019.
                self.assertEqual(
                    stated[row["role"]],
                    (role.model or "none", role.effort or "none"),
                )
        self.assertEqual(set(roster.ROLES), set(stated))

    def test_the_default_session_ceiling_is_the_schemas_own_default(self):
        # PH2-73. What governs a run is the weights row, which the runtime
        # reads with the claim and hands the gate; this constant is only what a
        # gate built without one falls back to. The two being one number is
        # what makes that fallback the schema's answer rather than a second
        # opinion about a value an operator versions for the whole scheduler.
        stated = self.DEFAULT_SUBAGENTS.search(self.sql)

        self.assertIsNotNone(stated, "019 no longer states a default subagent cap")
        self.assertEqual(roster.DEFAULT_SUBAGENTS, int(stated["cap"]))

    def test_the_task_kind_mapping_is_the_schemas(self):
        mapped = {
            row["kind"]: row["role"]
            for row in self.KINDS.finditer(self.statement("INSERT INTO role_task_kinds"))
        }
        owned = {
            kind: name for name, role in roster.ROLES.items() for kind in role.task_kinds
        }

        self.assertEqual(mapped, owned)
        self.assertEqual(set(roster.TASK_KINDS), set(mapped))


class ContractSchemaTest(unittest.TestCase):
    """The schema a tool is served with, which binds before any handler runs.

    The CLI validates a call against the served JSON Schema before `PreToolUse`
    fires, so this is the earliest place an argument is refused -- earlier than
    the gate, and earlier than the handler that would otherwise have to decide
    what an unexpected key meant. The gate checks the same properties again
    afterwards, which is two checks of one statement rather than two statements.
    """

    def test_every_served_schema_is_closed(self):
        for name, contract in roster.CONTRACTS.items():
            with self.subTest(tool=name):
                schema = contract.schema()
                self.assertEqual("object", schema["type"])
                self.assertFalse(schema["additionalProperties"])

    def test_no_served_schema_admits_a_program_or_a_credential(self):
        # The compile already refuses a contract declaring one. This is the
        # same claim read off the document the pair is actually handed.
        for name, contract in roster.CONTRACTS.items():
            with self.subTest(tool=name):
                properties = set(contract.schema()["properties"])
                self.assertEqual(set(), properties & roster.FORBIDDEN_ARGUMENTS)

    def test_the_required_list_is_exactly_the_arguments_declared_required(self):
        for name, contract in roster.CONTRACTS.items():
            with self.subTest(tool=name):
                self.assertEqual(
                    sorted(
                        argument
                        for argument, spec in contract.arguments.items()
                        if spec.required
                    ),
                    contract.schema()["required"],
                )

    def test_a_constrained_argument_carries_its_constraint_into_the_schema(self):
        surface = roster.CONTRACTS["mcp__rk2__get_attack_surface"].schema()
        receipts = roster.CONTRACTS["mcp__rk2__get_receipts"].schema()
        artifact = roster.CONTRACTS["mcp__rk2__get_artifact"].schema()

        self.assertEqual(list(roster.ENTITY_TYPES), surface["properties"]["entity_type"]["enum"])
        # A header set is bounded on both halves: the names by `propertyNames`
        # and what those names carry by `additionalProperties`, because a value
        # that may hold a line break is a value that may hold a second request.
        request = roster.CONTRACTS["mcp__rk2__http_request"].schema()["properties"]["headers"]
        self.assertEqual({"pattern": "^[A-Za-z][A-Za-z0-9-]{0,63}\\Z"}, request["propertyNames"])
        self.assertEqual(
            {"type": "string", "pattern": "^[\\x20-\\x7e]{0,1024}\\Z"},
            request["additionalProperties"],
        )
        self.assertEqual(
            {"type": "string", "pattern": roster._label("R")},
            receipts["properties"]["receipt_labels"]["items"],
        )
        # Nothing is required: the same verb lists and fetches, and the list is
        # the only way a child learns a label to fetch by.
        self.assertEqual([], artifact["required"])
        # The rule `v_artifacts` states on itself, enforced where a model first
        # meets it: the schema takes a label and has no property a hash fits.
        self.assertEqual(
            {"type": "string", "pattern": roster._label("AF")},
            artifact["properties"]["artifact_label"],
        )
        self.assertEqual(
            set(),
            {name for name in artifact["properties"] if "hash" in name},
        )

    def test_a_bounded_string_says_length_and_a_bounded_count_says_value(self):
        # `minimum` and `maximum` are JSON Schema's number vocabulary, and on a
        # string they name a rule that cannot apply to the value the pair is
        # about to send. The gate refuses that value by its length, so a schema
        # written in the number words would be the promise and the check asking
        # two different questions of one declaration.
        body = roster.Argument("string", bounds=(1, 65536)).schema()

        self.assertEqual(1, body["minLength"])
        self.assertEqual(65536, body["maxLength"])
        self.assertNotIn("minimum", body)
        self.assertNotIn("maximum", body)
        # And the half that was always right, which is every bounded argument
        # this roster ships: a `limit` is bounded by what it counts to.
        limit = roster.CONTRACTS["mcp__rk2__get_attack_surface"].schema()["properties"]["limit"]

        self.assertEqual(roster._PAGE, (limit["minimum"], limit["maximum"]))
        self.assertNotIn("minLength", limit)
        self.assertNotIn("maxLength", limit)

    def test_the_one_result_takes_every_element_list_the_spec_names(self):
        # Spec section 13: "proposed Entities, Relationships, Observations,
        # Hypotheses, evidence edges, suggested Tasks and a completion claim".
        # A list the schema does not declare is not deferred -- `submit` is the
        # only outbound verb, and `additionalProperties: false` denies the call
        # rather than dropping the key.
        schema = roster.CONTRACTS["mcp__rk2__submit_mission_result"].schema()

        self.assertEqual(
            {
                "new_entities",
                "relationships",
                "observations",
                "hypotheses",
                "evidence",
                "suggested_tasks",
                "completion_claim",
            },
            set(schema["properties"]),
        )

    def test_an_argument_open_by_declaration_is_still_a_declared_argument(self):
        # `free_text` says this roster constrains nothing about the *value*. It
        # does not say the key is optional to declare: an undeclared key is
        # refused by `additionalProperties` whatever the value would have been.
        schema = roster.CONTRACTS["mcp__rk2__submit_mission_result"].schema()

        for argument in roster.OPEN_ARGUMENTS["mcp__rk2__submit_mission_result"]:
            with self.subTest(argument=argument):
                self.assertIn(argument, schema["properties"])
        self.assertFalse(schema["additionalProperties"])

    def test_a_label_pattern_matches_the_labels_the_database_issues(self):
        # `next_label()` is `prefix || counter::text`: no separator, no padding.
        pattern = re.compile(roster._label("H"))

        for label in ("H1", "H7", "H4096"):
            with self.subTest(label=label):
                self.assertRegex(label, pattern)
        for label in ("H", "H-0007", "h1", "HH1", "H1x"):
            with self.subTest(label=label):
                self.assertNotRegex(label, pattern)


class RelationAgreementTest(unittest.TestCase):
    """Every relation the roster names is one the schema corpus creates.

    The roster's refusals are stated in relation names -- `CANONICAL` is what no
    model-facing contract may write, and `reads`/`writes` are what each one
    touches. A name with no table behind it makes those refusals unfalsifiable:
    a contract declaring `writes=("entites",)` would pass the compile check that
    is meant to stop exactly that write.
    """

    RELATION = re.compile(
        r"CREATE (?:OR REPLACE )?(?:UNLOGGED |MATERIALIZED )?(?:TABLE|VIEW)"
        r"(?: IF NOT EXISTS)? ([a-z_][a-z0-9_]*)"
    )

    #: Names the corpus does not create yet. Empty since ticket 23 created
    #: `task_picks`, which was the only one; kept, because the exemption being
    #: by name is what makes adding one an edit to this list rather than a
    #: silent widening.
    PENDING: frozenset[str] = frozenset()

    @classmethod
    def setUpClass(cls):
        corpus = ROOT / "src" / "redkraken" / "migrations"
        cls.created = {
            name
            for migration in sorted(corpus.glob("*.sql"))
            for name in cls.RELATION.findall(migration.read_text(encoding="utf-8"))
        }

    def named(self) -> dict[str, set[str]]:
        """Every relation name in the roster, and where each one was named."""
        where: dict[str, set[str]] = {}
        for name in roster.CANONICAL:
            where.setdefault(name, set()).add("CANONICAL")
        for tool, contract in roster.CONTRACTS.items():
            for relation in contract.reads:
                where.setdefault(relation, set()).add(f"{tool}.reads")
            for relation in contract.writes:
                where.setdefault(relation, set()).add(f"{tool}.writes")
        return where

    def test_every_relation_the_roster_names_is_one_the_corpus_creates(self):
        for name, sites in sorted(self.named().items()):
            if name in self.PENDING:
                continue
            with self.subTest(relation=name, named_by=sorted(sites)):
                self.assertIn(name, self.created)

    def test_every_relation_exempted_here_still_does_not_exist(self):
        # A pending name that quietly started existing would leave an exemption
        # standing for a check that could now be made. `task_picks` did start
        # existing, under ticket 23, and the exemption came out with it.
        for name in self.PENDING:
            with self.subTest(relation=name):
                self.assertNotIn(name, self.created)
                self.assertIn(name, self.named())


def agent_read() -> str:
    """One tool a launch serves, spelled the way the CLI spells it.

    Every argument of this one is optional, so a bare call is a call the gate
    can only refuse for a reason the test is actually about.
    """
    return "mcp__rk2__get_attack_surface"


if __name__ == "__main__":
    unittest.main()
