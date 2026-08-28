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

    def test_a_finding_is_asked_for_because_it_may_not_be_written(self):
        """PH2-102: the rule that decided the shape of this tool.

        `findings` is canonical, the compile refuses a contract that names one,
        and the test above proves it does. So the strongest thing this surface
        can do about a Finding is ask -- and what the ask leaves behind is the
        audit row `open_finding` writes whether it opened one or refused.
        """
        request = roster.CONTRACTS["mcp__rk2__propose_finding"]

        self.assertEqual(roster.REQUEST, request.direction)
        self.assertEqual(("finding_proposals",), request.writes)
        self.assertNotIn("findings", request.writes)
        self.assertIn("findings", roster.CANONICAL)
        self.assertNotIn("finding_proposals", roster.CANONICAL)

    def test_a_proposal_names_the_run_that_settled_the_claim_by_naming_the_claim(self):
        """The three fields, and the reason the fourth is not one of them.

        `test_runs` carries no label and a packet publishes no Test, so a run
        argument would be a field no child could fill. It is not needed: the
        transition from `testing` to `supported` cites one Receipt and that
        Receipt belongs to one run, so the claim names the run.
        """
        request = roster.CONTRACTS["mcp__rk2__propose_finding"]

        self.assertEqual(
            {"hypothesis_label", "vulnerability_class", "title"}, set(request.arguments)
        )
        self.assertNotIn("test_runs", roster.LABEL_PREFIXES)
        for name, declared in request.arguments.items():
            with self.subTest(argument=name):
                self.assertTrue(declared.required)
                self.assertTrue(declared.constrained)
                self.assertFalse(declared.free_text)

    def test_the_vulnerability_word_is_the_tables_and_not_a_copy_of_the_table(self):
        # An enum here would be a second copy of `vulnerability_classes` that
        # goes stale the first time a migration adds a row. The eighth arm of
        # `rk2_finding_refusal` answers an unknown class by naming it, which is
        # the vocabulary refusing out of the table that declares it.
        declared = roster.CONTRACTS["mcp__rk2__propose_finding"].arguments["vulnerability_class"]

        self.assertEqual((), declared.enum)
        self.assertTrue(declared.pattern)
        self.assertTrue(re.compile(declared.pattern).match("idor"))
        self.assertFalse(re.compile(declared.pattern).match("Idor"))

    def test_a_correlator_is_asked_for_and_the_name_in_it_is_not_an_argument(self):
        """PH2-98: the three things about a canary a model does not decide.

        The name, because a correlator is only attributable while nothing
        outside the runtime and the payload has seen it; the lifetime, because a
        name planted in somebody else's system outlives the run that planted it;
        and the channel, because a Program declares one and the verb refuses to
        pick between two. What is left is the two names the child can already
        read off its own packet.
        """
        request = roster.CONTRACTS["mcp__rk2__mint_callback"]

        self.assertEqual(roster.REQUEST, request.direction)
        self.assertEqual(("callback_correlators",), request.writes)
        self.assertEqual({"channel", "subject_label"}, set(request.arguments))
        for name in ("correlator", "lifetime", "expires_at", "address"):
            with self.subTest(argument=name):
                self.assertNotIn(name, request.arguments)
                self.assertNotIn(name, request.schema()["properties"])
        for name, declared in request.arguments.items():
            with self.subTest(argument=name):
                self.assertTrue(declared.required)
                self.assertTrue(declared.constrained)
                self.assertFalse(declared.free_text)

    def test_the_channel_argument_is_the_shape_a_channel_name_can_have(self):
        # `program_callback_channels.name`'s own check constraint, restated so
        # that a name no channel could carry is refused by the closed schema
        # rather than by a query that finds nothing.
        declared = roster.CONTRACTS["mcp__rk2__mint_callback"].arguments["channel"]

        self.assertTrue(re.compile(declared.pattern).match("oob"))
        self.assertFalse(re.compile(declared.pattern).match("OOB"))
        self.assertFalse(re.compile(declared.pattern).match("-oob"))
        self.assertFalse(re.compile(declared.pattern).match("oob.example"))

    def test_an_exchange_declares_the_rows_the_labels_it_answers_come_off(self):
        """PH2-106: the ticket that changed the answer and not the declaration.

        The two Artifact labels an exchange hands back are `artifact_refs` rows
        that `register_proxy_artifacts` and `hold_receipt_transcripts()` were
        already writing under this contract, in the Receipt's own transaction.
        So the declaration is the same one it was, and the test is here because
        the temptation the ticket had to refuse is visible from here: a label in
        the answer looks like something a caller should be able to ask for, and
        an argument for one would be an argument to a tool that fetches.
        """
        exchange = roster.CONTRACTS["mcp__rk2__http_request"]

        self.assertEqual(("receipts", "artifacts", "artifact_refs"), exchange.writes)
        self.assertEqual({"method", "url", "headers", "body"}, set(exchange.arguments))
        for name in ("artifact_label", "request_artifact", "response_artifact"):
            with self.subTest(argument=name):
                self.assertNotIn(name, exchange.schema()["properties"])

    def test_the_refresh_takes_the_three_kinds_of_label_a_run_mints(self):
        """PH2-107: the read that is asked by label because it cannot be asked otherwise.

        Three arrays and no fourth, and the reason is arithmetic rather than
        taste: the rows one `authentication` run mints weigh 33,974 bytes against
        a 32,768-byte packet ceiling, so "everything I have made" was never a
        question this could answer. What a child may name is what the runtime
        already told it about.

        `TR` and not `T` for the third one. `T` is a Task label and this reads
        the `tool_run` kind of `v_records`, so a pattern that admitted a Task
        label would let a child ask that kind for a name it never carries.
        """
        refresh = roster.CONTRACTS[roster.REFRESH_PACKET]

        self.assertEqual(roster.READ, refresh.direction)
        self.assertEqual((), refresh.writes)
        self.assertEqual(
            {"receipt_labels", "artifact_labels", "tool_run_labels"},
            set(refresh.arguments),
        )
        for argument, holds, refuses in (
            ("receipt_labels", "R7", "TR7"),
            ("artifact_labels", "AF7", "A7"),
            ("tool_run_labels", "TR7", "T7"),
        ):
            with self.subTest(argument=argument):
                pattern = re.compile(refresh.arguments[argument].items_pattern)
                self.assertRegex(holds, pattern)
                self.assertNotRegex(refuses, pattern)

    def test_the_refresh_is_the_read_authority_and_not_a_new_one(self):
        # It reads the same Program's rows through the same views under the same
        # role as the five reads beside it. A group of its own would have said
        # that reading a row minted five seconds ago is a different kind of
        # permission from reading one minted five minutes ago.
        holding = [
            name for name, tools in roster.TOOL_GROUPS.items()
            if roster.REFRESH_PACKET in tools
        ]

        self.assertEqual(["state.read"], holding)
        self.assertEqual("state.read", roster.CONTRACTS[roster.REFRESH_PACKET].group)

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

    def test_only_a_role_that_hunts_may_ask_for_a_finding(self):
        """PH2-102: who decides that something is worth reporting.

        The party that did the hunting, which is why the request is in
        `state.propose` and not in `sched.pick`. The orchestrator never touches
        a target and the validator judges a Finding somebody else opened, so
        neither is the party -- and `_check_authority` already keeps the two
        groups off one role, so a role that asks for a Finding is never the role
        that schedules the work the Finding would justify.
        """
        asking = {
            name for name, role in roster.ROLES.items()
            if "mcp__rk2__propose_finding" in role.tools
        }

        self.assertEqual({"recon", "web_hunter", "js_analyst"}, asking)
        for name in sorted(asking):
            with self.subTest(role=name):
                self.assertTrue(roster.ROLES[name].executes_tasks)
                self.assertNotIn("sched.pick", roster.ROLES[name].tool_groups)

    def test_only_a_role_that_hunts_may_plant_a_correlator(self):
        """PH2-98: the same partition, for the out-of-band half of it.

        A canary is planted by the party that is sending requests at the target,
        which is why the mint is in `state.propose` beside the Finding ask
        rather than in `sched.pick`. The orchestrator never touches a target and
        the validator judges what somebody else found, so neither is the party.
        """
        minting = {
            name for name, role in roster.ROLES.items()
            if "mcp__rk2__mint_callback" in role.tools
        }

        self.assertEqual({"recon", "web_hunter", "js_analyst"}, minting)
        for name in sorted(minting):
            with self.subTest(role=name):
                self.assertTrue(roster.ROLES[name].executes_tasks)
                self.assertNotIn("sched.pick", roster.ROLES[name].tool_groups)

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
            # The body under the spelling it was withheld under. Ticket 96 gave
            # this contract a `body`, and it is a string the child writes itself
            # rather than a hash into a store the child still does not have, so
            # the hash form names nothing and is denied for the ordinary reason:
            # no contract declares it.
            hunting(
                "mcp__rk2__http_request",
                method="GET",
                url="https://x",
                body_artifact_hash="a" * 64,
            ),
            # A body one byte past the ceiling the contract states.
            hunting(
                "mcp__rk2__http_request",
                method="POST",
                url="https://x",
                body="b" * 65537,
            ),
            # A body of the shape the gate cannot scan. An object here would be
            # walked for a forbidden name and a string never is, which is why
            # the argument is a string; the schema and the gate agree about that
            # rather than the gate quietly accepting what the schema refuses.
            hunting(
                "mcp__rk2__http_request",
                method="POST",
                url="https://x",
                body={"note": "hello"},
            ),
            # And the identity, which ticket 97 settled is not withheld pending
            # a decision but refused as a rule: the slot is a property of the
            # Tool run the runtime opened, and there is nothing at call time for
            # an argument to change.
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

    #: A role added after 019 was applied, which is the only shape a seventh
    #: can have: 019 has a recorded checksum, so the row cannot be written into
    #: it, and by the time a later migration runs the model, effort and skill
    #: columns exist -- so the row states all nine at once rather than being
    #: inserted here and updated there. Ticket 152's `performer` is the first.
    LATER_ROWS = re.compile(
        r"\('(?P<role>\w+)', '(?P<runs_as>\w+)', "
        r"ARRAY\['(?P<invocable_by>\w+)'\]::text\[\], "
        r"(?P<executes_tasks>true|false), (?P<max_concurrent>\d+), (?P<clamp>true|false),\s*"
        r"'(?P<model>[\w.-]+)', '(?P<effort>\w+)', (?P<loads_skills>true|false)\)"
    )

    #: A clamp a later migration turns on. A role added after 019 states its
    #: clamp in the row that creates it; a role that was already there and
    #: starts acting as an account has that said in an UPDATE instead, and a
    #: test reading only INSERTs would let the schema and this module disagree
    #: for exactly as long as nobody looked -- which is how ticket 191 left
    #: `recon` clamped in the database and unclamped here.
    CLAMP_UPDATE = re.compile(
        r"UPDATE roles SET clamp_to_identity_leases = (?P<clamp>true|false)\s*"
        r"WHERE role = '(?P<role>\w+)'"
    )

    @classmethod
    def setUpClass(cls):
        migrations = ROOT / "src" / "redkraken" / "migrations"
        cls.sql = (migrations / "0019_role_kinds.sql").read_text(encoding="utf-8")
        cls.model_and_effort_sql = (
            migrations / "20260813T200000Z__a_role_runs_at_the_rosters_model_and_effort.sql"
        ).read_text(encoding="utf-8")
        #: Every migration after 019. The roster's statement in the schema is the
        #: whole corpus and not one file, and reading only the file the first six
        #: are in is how a seventh role could be added to this module and to the
        #: database and still be reported as missing from both.
        cls.later = [
            path.read_text(encoding="utf-8")
            for path in sorted(migrations.glob("*.sql"))
            if path.name != "0019_role_kinds.sql"
        ]

    def added_rows(self, pattern: re.Pattern) -> list[re.Match]:
        """Every row a later migration adds, wherever in the corpus it is."""
        found = []
        for text in self.later:
            start = 0
            while True:
                where = text.find("INSERT INTO roles", start)
                if where < 0:
                    break
                found += list(pattern.finditer(text[where : text.index(";", where)]))
                start = text.index(";", where)
        return found

    def clamp_updates(self) -> dict[str, bool]:
        """Every later change to the clamp, which is not shipped in a row."""
        found: dict[str, bool] = {}
        for text in self.later:
            for match in self.CLAMP_UPDATE.finditer(text):
                found[match["role"]] = match["clamp"] == "true"
        return found

    def added_mappings(self) -> list[re.Match]:
        """Every role/kind pair a later migration adds."""
        found = []
        for text in self.later:
            start = 0
            while True:
                where = text.find("INSERT INTO role_task_kinds", start)
                if where < 0:
                    break
                found += list(self.KINDS.finditer(text[where : text.index(";", where)]))
                start = text.index(";", where)
        return found

    def statement(self, prefix: str, sql: str | None = None) -> str:
        text = self.sql if sql is None else sql
        start = text.index(prefix)
        return text[start : text.index(";", start)]

    def test_every_role_row_the_schema_carries_is_this_rosters_row(self):
        rows = [
            *self.ROWS.finditer(self.statement("INSERT INTO roles")),
            *self.added_rows(self.LATER_ROWS),
        ]
        clamped = self.clamp_updates()
        stated = {}
        for row in rows:
            role = roster.ROLES[row["role"]]
            stated[row["role"]] = (
                row["runs_as"],
                (row["invocable_by"],),
                row["executes_tasks"] == "true",
                int(row["max_concurrent"]),
                clamped.get(row["role"], row["clamp"] == "true"),
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
        for row in [
            *self.MODEL_AND_EFFORT.finditer(
                self.statement("UPDATE roles r SET", self.model_and_effort_sql)
            ),
            # A role added after PH2-71 states its model and effort in the row
            # that creates it, because by then the two columns exist and are
            # NOT NULL. One vocabulary, two spellings, and this is where they
            # are read as one.
            *self.added_rows(self.LATER_ROWS),
        ]:
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
            for row in [
                *self.KINDS.finditer(self.statement("INSERT INTO role_task_kinds")),
                *self.added_mappings(),
            ]
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

    def test_a_bounded_list_says_how_many_items_it_takes(self):
        # The third measure and the same rule as the two above. `minimum` on an
        # array names a property of a number, and every validator ignores it --
        # so a Test's "between three and thirty-two actions" written that way
        # would be a promise the pair never checks, in front of a gate that
        # refuses on it. `_value_fault` measures an array by `len`, so the
        # schema says the same thing in the word a validator reads.
        actions = roster.CONTRACTS["mcp__rk2__propose_test"].schema()["properties"]["actions"]

        self.assertEqual((3, 32), (actions["minItems"], actions["maxItems"]))
        self.assertNotIn("minimum", actions)
        self.assertNotIn("minLength", actions)

    def test_a_request_may_declare_a_body_and_it_is_a_bounded_string(self):
        """Ticket 96's first criterion, read off the document the pair is served.

        A string and not an object, and the reason is the gate rather than
        taste: the forbidden-name scan returns immediately for anything that is
        not a mapping, a list or a tuple, so an object body would be walked for
        an `Authorization` key and the most ordinary login form in web testing
        would be denied for containing the word. A string is never walked, and a
        body is the one argument whose contents are the subject of the test
        rather than an instruction to this harness.
        """
        schema = roster.CONTRACTS["mcp__rk2__http_request"].schema()
        body = schema["properties"]["body"]

        self.assertEqual(
            {"type": "string", "minLength": 0, "maxLength": 65536}, body
        )
        # Not required, because most requests have none, and an empty string is
        # a body a caller chose to send rather than one it left out.
        self.assertNotIn("body", schema["required"])
        # The two framing headers stay out of the contract. `Content-Type` is
        # not here because it is a header and the contract already takes those;
        # `Content-Length` is not here and is not a header a caller may set,
        # because it is the door's measurement of the door's own document.
        self.assertNotIn("content_type", schema["properties"])
        self.assertNotIn("content_length", schema["properties"])

    def test_a_body_within_its_bounds_is_a_call_the_gate_allows(self):
        # The denial list two tests up says which bodies are refused. This is
        # the other half, and without it a contract that declared `body` and a
        # gate that denied every one of them would pass this file.
        hunter = roster.Gate("web_hunter")
        hunter.bind("agent-1", "web_hunter")

        for sent in ("", "u=admin&p=hunter2", "b" * 65536):
            with self.subTest(length=len(sent)):
                self.assertIsNone(
                    hunter.decide(
                        roster.Call(
                            tool="mcp__rk2__http_request",
                            arguments={
                                "method": "POST",
                                "url": "https://target.example.test/login",
                                "headers": {"Content-Type": "application/x-www-form-urlencoded"},
                                "body": sent,
                            },
                            agent_id="agent-1",
                            agent_type="web_hunter",
                        )
                    )
                )

    def test_no_tool_on_this_surface_declares_an_identity(self):
        """Ticket 97's settlement, asked of the whole surface rather than of one tool.

        The decision is that `identity_slot` is a property of the Tool run and
        never an argument, and the name is in no forbidden list, so the only
        thing standing between a later ticket and declaring one is that
        decision. Written here so the decision has somewhere to fail.

        Every contract and not just the request tool. `run_tool` and
        `run_skill_script` open Tool runs of their own, and a slot declared on
        either of them would be the same mistake reached by another door.
        """
        for tool, contract in roster.CONTRACTS.items():
            with self.subTest(tool=tool):
                self.assertNotIn("identity_slot", contract.arguments)
                self.assertNotIn("identity_slot", contract.schema()["properties"])

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


class VocabularyAgreementTest(unittest.TestCase):
    """Every closed vocabulary the roster serves is the one the corpus declares.

    The roster now states, in `APPLICATION_KINDS` and the tuples beside it, sets
    of words the database is the authority on: some are a check constraint on
    the column promotion writes, some are the rows of a reference table its walk
    looks the value up in. Restating them is what puts them in the served schema,
    where a model can be refused for a word outside one instead of losing the
    element to a `proposal_drops` row after its run has ended -- and restating
    them is also how they go stale, because two statements of one vocabulary
    agree until somebody edits one.

    So this reads the corpus and not a server, for the reason `RelationAgreement`
    above reads the corpus: the migrations are what create the database, they are
    in the tree, and a check that needs PostgreSQL is a check that is skipped in
    the loop where these constants are actually edited. What it costs is that
    this parses SQL rather than querying it, which is why the extraction is
    anchored on the statement -- `CREATE TABLE <table>` or `ALTER TABLE <table>`
    for a constraint, `INSERT INTO <table>` for a seed -- rather than on the
    words themselves. A vocabulary the parser cannot find comes back empty and
    fails, which is the safe direction to be wrong in.
    """

    LITERAL = re.compile(r"'([^']*)'")

    @classmethod
    def setUpClass(cls):
        corpus = ROOT / "src" / "redkraken" / "migrations"
        cls.migrations = [
            path.read_text(encoding="utf-8") for path in sorted(corpus.glob("*.sql"))
        ]

    @classmethod
    def balanced(cls, text: str, opening: int) -> str:
        """The text inside the parenthesis that opens at `opening`.

        A count rather than a lazy regex, because every list this reads is
        nested: `CHECK (value_class IS NULL OR value_class IN (...))` closes two
        parentheses and a pattern stopping at the first one would read half a
        vocabulary as the whole of it.
        """
        depth = 0
        for index in range(opening, len(text)):
            if text[index] == "(":
                depth += 1
            elif text[index] == ")":
                depth -= 1
                if depth == 0:
                    return text[opening:index]
        raise AssertionError("the corpus has an unbalanced parenthesis")

    @classmethod
    def constraint(cls, table: str, column: str) -> tuple[str, ...]:
        """`column`'s vocabulary as the last statement about `table` states it.

        The last and not the first: 20260929T020000Z drops and re-adds
        `identities_class_check` to retire a value, so the answer is the one the
        migrations arrive at rather than the one they start from.
        """
        found: tuple[str, ...] = ()
        for text in cls.migrations:
            statements = []
            created = re.search(rf"CREATE TABLE {table}\s*\(", text)
            if created is not None:
                statements.append(cls.balanced(text, created.end() - 1))
            for altered in re.finditer(rf"ALTER TABLE {table}\b", text):
                statements.append(text[altered.end():text.index(";", altered.end())])
            for statement in statements:
                for check in re.finditer(r"CHECK\s*\(", statement):
                    # Only a check this column leads. 0021 constrains
                    # `entities.scope_selector` with a clause that reads
                    # `OR type IN ('identity','technology')`, which is a true
                    # sentence about two of the eight types and would be read
                    # here as the whole vocabulary.
                    body = cls.balanced(statement, check.end() - 1)
                    if not re.match(rf"\(\s*{column}\b", body):
                        continue
                    listed = re.search(rf"\b{column} IN \(", body)
                    if listed is not None:
                        found = tuple(
                            cls.LITERAL.findall(cls.balanced(body, listed.end() - 1))
                        )
        return found

    @classmethod
    def seeded(cls, table: str) -> list[list[str]]:
        """The literals leading each row every `INSERT INTO table` seeds.

        Leading, because that is where the identifiers are and what follows them
        is a description carrying doubled quotes and commas of its own. A row
        begins a line -- every seed in this corpus is written that way -- so the
        rows are the lines opening with a parenthesis, and the statement ends at
        the first line closing with a semicolon.
        """
        rows: list[list[str]] = []
        for text in cls.migrations:
            lines = text.splitlines()
            for number, line in enumerate(lines):
                if f"INSERT INTO {table} " not in line:
                    continue
                head = line.split("VALUES", 1)
                if len(head) == 2 and head[1].strip():
                    rows += [cls.LITERAL.findall(one) for one in head[1].split("), (")]
                    continue
                for follow in lines[number + 1:]:
                    if follow.lstrip().startswith("("):
                        rows.append(cls.LITERAL.findall(follow))
                    if follow.rstrip().endswith(";"):
                        break
        return rows

    @classmethod
    def returned(cls, function: str) -> tuple[str, ...]:
        """The array literal one no-argument `rk2_test_*()` function returns.

        A third extraction beside `constraint` and `seeded`, because these
        vocabularies are declared a third way and had to be. `rk2_test_spec_problem`
        is an IMMUTABLE function, so the words it checks against cannot be rows in
        a table it would have to select from, and they are not a CHECK on a column
        either because the thing they constrain is a key inside a jsonb document.
        They are `SELECT ARRAY[...]` bodies, and this reads them where they are
        written.

        The bracket is closed by a scan for `]` rather than by `balanced`, which
        counts parentheses. Every one of these bodies is a flat list of string
        literals with no bracket inside it, and a body that stopped being one
        would come back short and fail, which is the safe direction.
        """
        found: tuple[str, ...] = ()
        for text in cls.migrations:
            for created in re.finditer(rf"CREATE FUNCTION {function}\(\)", text):
                body = text[created.end() : text.index("$fn$;", created.end())]
                opened = body.index("ARRAY[")
                found = tuple(cls.LITERAL.findall(body[opened : body.index("]", opened)]))
        return found

    @classmethod
    def methods(cls) -> tuple[str, ...]:
        """The methods `rk2_test_request_problem` will store a request under.

        Not an `ARRAY` body like the four above. This one is written inline as
        the `NOT IN` list of the guard that refuses everything else, because the
        function that reads the vocabulary is the function that refuses on it.
        So it is read where it is written, anchored on the statement.
        """
        found: tuple[str, ...] = ()
        for text in cls.migrations:
            for created in re.finditer(r"CREATE FUNCTION rk2_test_request_problem\(", text):
                body = text[created.end() : text.index("$fn$;", created.end())]
                listed = body.index("NOT IN")
                found = tuple(
                    cls.LITERAL.findall(cls.balanced(body, body.index("(", listed)))
                )
        return found

    def test_the_entity_vocabularies_are_the_columns_the_corpus_checks(self):
        for constant, table, column in (
            (roster.ENTITY_TYPES, "entities", "type"),
            (roster.APPLICATION_KINDS, "applications", "kind"),
            (roster.PARAMETER_LOCATIONS, "parameters", "location"),
            (roster.PARAMETER_VALUE_CLASSES, "parameters", "value_class"),
            (roster.RELATIONSHIP_TYPES, "relationships", "type"),
            (roster.EVIDENCE_POLARITIES, "hypothesis_evidence", "polarity"),
            (roster.EVIDENCE_ROLES, "hypothesis_evidence", "role"),
            (roster.HYPOTHESIS_STATUSES, "hypotheses", "status"),
            (roster.SEVERITY_BANDS, "severity_statements", "severity"),
            (roster.SEVERITY_BASES, "severity_statements", "basis"),
        ):
            with self.subTest(column=f"{table}.{column}"):
                self.assertEqual(set(constant), set(self.constraint(table, column)))

    def test_the_only_identity_class_an_agent_proposes_is_one_the_column_takes(self):
        # A subset and not an equality, and the one vocabulary here that is.
        # `IDENTITY_CLASSES` states what may be *sent*, which is narrower than
        # what the column holds: the other two classes carry a `secret_ref` the
        # operator places, and `promote_proposal` refuses an element naming one.
        # What this can still catch is the failure that matters -- the column
        # losing the word the schema tells every hunter to use.
        declared = set(self.constraint("identities", "class"))

        self.assertTrue(declared)
        self.assertLessEqual(set(roster.IDENTITY_CLASSES), declared)
        self.assertIn("anonymous", roster.IDENTITY_CLASSES)

    def test_the_task_kinds_are_the_rows_the_scheduler_seeds(self):
        self.assertEqual(
            set(roster.TASK_KINDS), {row[0] for row in self.seeded("task_kinds")}
        )

    def test_every_observation_kind_carries_the_provenance_its_row_allows(self):
        # Both halves of the row. The keys are what the schema serves as an
        # enum; the values are what the description states in a sentence, and a
        # sentence with nothing measuring it is how this vocabulary came to be
        # wrong in prose in the first place.
        seeded = {}
        for row in self.seeded("observation_kinds"):
            # `'{receipt,tool_run}'` in most rows and `ARRAY['receipt']` in the
            # one 0025 adds. Two spellings of one array, flattened to the words.
            seeded[row[0]] = tuple(
                word
                for literal in row[2:]
                for word in literal.strip("{}").split(",")
                if word
            )

        self.assertEqual(dict(roster.OBSERVATION_KINDS), seeded)

    def test_every_property_class_is_seeded_and_sits_in_a_seeded_family(self):
        seeded = {row[0]: row[1] for row in self.seeded("property_classes")}

        self.assertEqual(set(roster.PROPERTY_CLASSES), set(seeded))
        # The family is the part before the dot, which is what lets the roster
        # hold one flat tuple instead of a mapping. True of every seeded row and
        # asserted rather than assumed, because a class whose family_id did not
        # match its prefix would make the flat tuple a lossy restatement.
        self.assertEqual(
            {identifier.split(".")[0] for identifier in roster.PROPERTY_CLASSES},
            {row[0] for row in self.seeded("property_class_families")},
        )
        for identifier, family in sorted(seeded.items()):
            with self.subTest(property_class=identifier):
                self.assertEqual(family, identifier.split(".")[0])

    def test_the_test_specification_vocabularies_are_the_ones_the_corpus_declares(self):
        # The four the shape rule reads out of its own helpers, and the one it
        # writes inline. `propose_test` serves all five as enums, so a word this
        # roster offered and `rk2_test_spec_problem` did not know would be a
        # specification refused by a sentence after the model had already been
        # told the word was allowed.
        for constant, function in (
            (roster.TEST_ACTION_ROLES, "rk2_test_roles"),
            (roster.TEST_PRECONDITION_KINDS, "rk2_test_precondition_kinds"),
            (roster.TEST_ASSERTION_KINDS, "rk2_test_assertion_kinds"),
        ):
            with self.subTest(function=function):
                declared = self.returned(function)
                self.assertTrue(declared, f"{function} declares no vocabulary")
                self.assertEqual(set(constant), set(declared))
        self.assertEqual(set(roster.TEST_REQUEST_METHODS), set(self.methods()))
        # And the one word an action's `kind` may be. Not a vocabulary function,
        # because 035 states it as a literal comparison -- so this is read as the
        # literal it is, and a corpus that widened it without widening the roster
        # would leave the model unable to say the new word.
        self.assertEqual(("request",), roster.TEST_ACTION_KINDS)
        self.assertTrue(
            any(
                "<> 'request' THEN" in text
                for text in self.migrations
            ),
            "no migration states the one kind of action a Test performs",
        )

    def test_the_concluding_vocabularies_are_the_rows_the_corpus_seeds(self):
        # Ticket 103's three, and the first of them is deliberately not the
        # whole of its table. `IMPACT_CLASSES` is the three of six whose risk
        # class is not `deny`; the other three can be approved by nobody, so a
        # schema offering the word would be a door painted on a wall. Both
        # halves are asserted, because a test reading only the three that are
        # there would still pass on the day a forbidden class was added to the
        # served schema -- which is the one failure this constant exists to
        # stop.
        decision = {row[0]: row[1] for row in self.seeded("risk_classes")}
        seeded = self.seeded("impact_classes")

        self.assertTrue(seeded, "impact_classes seeds no vocabulary")
        self.assertEqual(
            set(roster.IMPACT_CLASSES),
            {row[0] for row in seeded if decision[row[1]] != "deny"},
        )
        for impact_class in (row[0] for row in seeded if decision[row[1]] == "deny"):
            with self.subTest(impact_class=impact_class):
                self.assertNotIn(impact_class, roster.IMPACT_CLASSES)

        # The two report vocabularies are their whole tables. Every seeded row
        # is a word a composition may say, and the effect's row is what
        # `compute_finding_cvss` reads the vector out of -- so a word the roster
        # withheld would be an impact this harness can hold and never score.
        for constant, table in (
            (roster.REPORT_EFFECTS, "report_effects"),
            (roster.REPORT_MECHANISMS, "report_mechanisms"),
        ):
            with self.subTest(table=table):
                declared = {row[0] for row in self.seeded(table)}
                self.assertTrue(declared, f"{table} seeds no vocabulary")
                self.assertEqual(set(constant), declared)

    def test_the_browser_vocabulary_is_the_registry_the_door_seeds(self):
        # Ticket 99: the twelve actions and the step ceiling belong to the
        # registry migrations, not to this side. `open_browser_run` refuses a
        # thirteenth action and a thirty-third step in the database, so a roster
        # naming a word the registry does not seed serves a step every mission
        # loses at the door, and a roster dropping one hides an action the door
        # still runs.
        def seedings(table: str) -> list[str]:
            """Every `INSERT INTO table`, with its column list and rows.

            Not `seeded` above, which reads the literals following `VALUES` on
            the line the statement opens. Both browser seeds write the column
            list on a line of its own, so that helper finds nothing here.
            """
            opened = [
                text[text.index(f"INSERT INTO {table}"):]
                for text in self.migrations
                if f"INSERT INTO {table}" in text
            ]
            self.assertTrue(opened, f"{table} is never seeded")
            return [text[:text.index(";")] for text in opened]

        actions = "\n".join(seedings("browser_actions"))
        self.assertEqual(
            set(roster.BROWSER_ACTIONS),
            {
                self.LITERAL.findall(line)[0]
                for line in actions.splitlines()
                if line.lstrip().startswith("(")
                and self.LITERAL.findall(line)
            },
        )

        # The ceiling is one row of one table and carries no literal at all, so
        # the column list is what says which of its numbers the steps are.
        [ceilings] = seedings("browser_ceilings")
        columns = [
            name.strip()
            for name in self.balanced(ceilings, ceilings.index("(")).lstrip("(").split(",")
        ]
        said = self.balanced(
            ceilings, ceilings.index("(", ceilings.index("VALUES"))
        ).lstrip("(")
        self.assertEqual(
            roster.BROWSER_STEPS[-1],
            int(said.split(",")[columns.index("max_steps")]),
        )

    def test_every_element_field_the_schema_closes_names_a_corpus_vocabulary(self):
        # The wiring itself, so that a seventh element list, a fifth entity field
        # or a later Contract's element cannot be added with a tuple nothing
        # above measures. Every enum any served schema carries under `items` is
        # one of the constants those tests hold to the corpus, and no other.
        held = {
            roster.ENTITY_TYPES,
            roster.APPLICATION_KINDS,
            roster.PARAMETER_LOCATIONS,
            roster.PARAMETER_VALUE_CLASSES,
            roster.IDENTITY_CLASSES,
            roster.RELATIONSHIP_TYPES,
            tuple(roster.OBSERVATION_KINDS),
            roster.PROPERTY_CLASSES,
            roster.EVIDENCE_POLARITIES,
            roster.EVIDENCE_ROLES,
            roster.TASK_KINDS,
            roster.TEST_PRECONDITION_KINDS,
            roster.TEST_ACTION_ROLES,
            roster.TEST_ACTION_KINDS,
            roster.TEST_ASSERTION_KINDS,
            roster.TEST_REQUEST_METHODS,
            roster.IMPACT_CLASSES,
            roster.REPORT_EFFECTS,
            roster.REPORT_MECHANISMS,
            roster.BROWSER_ACTIONS,
        }

        # Only the fields that close a vocabulary. An element field may instead
        # be bounded -- an ordinal, a status, the length of a url -- and a bound
        # is not a word list for this test to hold to the corpus.
        declared = [
            (tool, name, field, shape)
            for tool, contract in roster.CONTRACTS.items()
            for name, argument in contract.arguments.items()
            if argument.element is not None
            for field, shape in argument.element.items()
            if shape.enum
        ]
        self.assertTrue(declared)
        for tool, name, field, shape in declared:
            with self.subTest(element=f"{tool}.{name}[].{field}"):
                self.assertIn(shape.enum, held)

    def test_a_claims_rationale_is_the_three_fields_the_column_admits(self):
        """Ticket 144: four claims were dropped for writing one paragraph here.

        `rk2hunt6` on 2026-08-22 was the first hunt in this tree where a model
        proposed a Hypothesis at all, and all four it proposed were dropped
        `malformed_field` citing "rationale is not an object". Every part was
        answered and answered well; the three were in one string because the
        served schema said `rationale` was a field and did not say it was three.

        So the keys are held to `rk2_rationale_keys()`, which is the same value
        `hypotheses_rationale_shape` checks the column against -- a fourth key
        added there and not here is a part a run cannot send, and a key dropped
        there and not here is a whole claim refused at the door for a field the
        column no longer takes.
        """
        declared = self.returned("rk2_rationale_keys")
        self.assertTrue(declared, "rk2_rationale_keys declares no vocabulary")
        self.assertEqual(set(roster.RATIONALE_KEYS), set(declared))

        rationale = roster._ELEMENTS["hypotheses"]["rationale"]
        self.assertEqual("object", rationale.kind)
        self.assertEqual(set(declared), set(rationale.element or {}))
        # `type: object` is what the drop was about, so the rendered subschema
        # is asserted rather than the constant behind it.
        self.assertEqual(
            {
                "type": "object",
                "properties": {
                    key: {"type": "string", "minLength": 1, "maxLength": 2000}
                    for key in declared
                },
            },
            rationale.schema(),
        )

    def test_the_gate_refuses_a_rationale_the_column_would_refuse(self):
        """The gate's half of the same promise, checked the way it is served."""
        rationale = roster._ELEMENTS["hypotheses"]["rationale"]
        whole = {key: "a sentence" for key in roster.RATIONALE_KEYS}

        self.assertIsNone(roster._value_fault(rationale, whole))
        self.assertEqual(
            "is not object", roster._value_fault(rationale, "one paragraph")
        )
        self.assertEqual(
            "carries 'falsifier', which is outside 1-2000",
            roster._value_fault(rationale, {**whole, "falsifier": ""}),
        )


def agent_read() -> str:
    """One tool a launch serves, spelled the way the CLI spells it.

    Every argument of this one is optional, so a bare call is a call the gate
    can only refuse for a reason the test is actually about.
    """
    return "mcp__rk2__get_attack_surface"


if __name__ == "__main__":
    unittest.main()
