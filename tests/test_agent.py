import ast
import asyncio
import contextlib
import io
import json
import os
import types
import unittest

from redkraken import _launch, _startup, agent
from tests import ROOT, fixtures


PACKAGE = ROOT / "src" / "redkraken"

#: The one module allowed to reach the SDK, and the name it reaches for.
BOUNDARY = "_launch.py"
SDK = "claude_agent_sdk"

#: Why every SDK-shaped test in this module is conditional. The SDK is not a
#: declared dependency -- it is measured, not installed, and `rk doctor` would
#: have to lie about a machine that lacks it -- so a checkout without it runs
#: every rule in `assess` and skips only the tests that need a live transport.
INSTALLED = _launch.claude_agent_sdk is not None
NEEDS_SDK = f"{SDK} is not installed in this interpreter"
NEEDS_NO_SDK = f"{SDK} is installed, so this interpreter is a measured runtime"


def executable() -> str:
    """A file that exists and can be run, standing in for the bundled CLI."""
    path = fixtures.scratch() / "claude"
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    return str(path.resolve())


def measured(cli_path: str) -> dict:
    """Runtime facts that match the pair the credential matrix was measured on."""
    return {
        "sdk_version": _startup.KNOWN_RUNTIME[0],
        "cli_version": _startup.KNOWN_RUNTIME[1],
        "cli_path": cli_path,
    }


def options(launch, cli_path: str, **overrides) -> types.SimpleNamespace:
    """A stand-in for the SDK options value, contained on every field.

    `assess` reads the options value by duck typing, so this is the whole
    interface it uses. A namespace rather than the real class on purpose: the
    rules have to be exercisable on a machine with no SDK, which is the same
    machine that has to be able to prove the SDK's absence is a refusal.
    """
    fields = {
        "env": {},
        "setting_sources": [],
        "sandbox": None,
        "cwd": str(launch),
        "tools": [],
        "permission_mode": agent.PERMISSION_MODE,
        "allowed_tools": [agent.TOOL],
        "mcp_servers": {agent.SERVER: object()},
        "settings": str(launch / agent.SETTINGS),
        "cli_path": cli_path,
    }
    fields.update(overrides)
    return types.SimpleNamespace(**fields)


def request(**overrides) -> agent.AgentRunRequest:
    fields = {
        "agent_run_id": "agent-run-1",
        "objective": "Say nothing.",
        "workspace": fixtures.scratch(),
        "proxy_url": "http://127.0.0.1:1",
        "certificate": fixtures.scratch() / "root.pem",
        "home": fixtures.scratch() / "run-home",
    }
    fields.update(overrides)
    return agent.AgentRunRequest(**fields)


def codes(violations) -> list[str]:
    return [violation["code"] for violation in violations]


def sources(violations) -> list[str]:
    return [violation["source"] for violation in violations]


class BoundaryTest(unittest.TestCase):
    """The reason the startup assertion is an assertion and not a convention."""

    def test_only_the_launch_module_reaches_the_agent_sdk(self):
        reaching = set()
        for path in sorted(PACKAGE.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                imported = ()
                if isinstance(node, ast.Import):
                    imported = tuple(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported = (node.module or "",)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    # A dynamic import is still an import. The point of the
                    # boundary is that one module constructs sessions, and
                    # `importlib.import_module(SDK)` would defeat a check that
                    # only read `import` statements.
                    imported = (node.value,)
                if any(name == SDK or name.startswith(f"{SDK}.") for name in imported):
                    reaching.add(path.name)

        self.assertEqual({BOUNDARY}, reaching)
        self.assertEqual(f"{PACKAGE.name}.{BOUNDARY.removesuffix('.py')}", agent.CHILD)


class LaunchDirectoryTest(unittest.TestCase):
    def test_a_launch_directory_is_one_private_component_holding_one_document(self):
        made = request()

        launch = agent.launch_directory(made)
        settings = agent.write_settings(launch)

        self.assertEqual(made.workspace.resolve() / made.agent_run_id, launch)
        self.assertEqual(agent.PRIVATE, launch.stat().st_mode & 0o777)
        self.assertEqual(launch / agent.SETTINGS, settings)
        self.assertEqual(0o600, settings.stat().st_mode & 0o777)
        self.assertEqual(agent.SETTINGS_DOCUMENT, json.loads(settings.read_text()))

    def test_a_run_identifier_that_is_not_one_component_is_refused(self):
        for identifier in ("../escape", "nested/run", ".", "", "sub/../../out"):
            with self.subTest(identifier=identifier):
                with self.assertRaises(ValueError):
                    agent.launch_directory(request(agent_run_id=identifier))


class EnvironmentTest(unittest.TestCase):
    """What the child is told about the world, and what it is not told."""

    def test_the_child_environment_is_a_copied_list_plus_the_runtime_door(self):
        operator = {name: f"operator-{name}" for name in agent.INHERITED}
        operator.update(
            {name: "leaked" for name in _startup.WATCHED_ENV_VECTORS},
            ANTHROPIC_SMALL_FAST_MODEL="leaked",
            SSH_AUTH_SOCK="/leaked/agent.sock",
            AWS_PROFILE="leaked",
        )
        home = fixtures.scratch() / "run-home"

        child = agent.child_environment(
            operator, proxy_url="http://127.0.0.1:9", certificate="/run/root.pem", home=home
        )

        supplied = {agent.IMPORT_PATH, "HOME"}
        for family in (
            _startup.WATCHED_ENV_VECTORS,
            ("ANTHROPIC_SMALL_FAST_MODEL", "SSH_AUTH_SOCK", "AWS_PROFILE"),
        ):
            for name in family:
                self.assertNotIn(name, child)
        self.assertNotIn("HOME", agent.INHERITED)
        self.assertEqual(str(home), child["HOME"])
        self.assertEqual(str(ROOT / "src"), child[agent.IMPORT_PATH])
        self.assertEqual(
            {name for name in agent.INHERITED if name in operator} | supplied,
            set(child) - set(agent.tls.PROXY_VARIABLES) - set(agent.tls.BYPASS_VARIABLES)
            - set(agent.tls.TRUST_VARIABLES) - set(agent.tls.STORE_VARIABLES),
        )

    def test_the_child_has_no_route_out_that_the_runtime_does_not_own(self):
        child = agent.child_environment(
            dict(os.environ),
            proxy_url="http://127.0.0.1:9",
            certificate="/run/root.pem",
            home="/run/home",
        )

        for name in agent.tls.PROXY_VARIABLES:
            self.assertEqual("http://127.0.0.1:9", child[name])
        for name in agent.tls.BYPASS_VARIABLES + agent.tls.STORE_VARIABLES:
            self.assertEqual("", child[name])
        for name in agent.tls.TRUST_VARIABLES:
            self.assertEqual("/run/root.pem", child[name])

    def test_the_operator_home_never_crosses_and_a_run_cannot_be_asked_for_without_one(self):
        # Where the CLI looks for the operator's own subscription. A run gets
        # the home the request names or the request is not one -- there is no
        # default, so no launch can reach that credential by omission.
        child = agent.child_environment(
            {"HOME": "/home/operator"},
            proxy_url="http://x",
            certificate="/c",
            home="/run/home",
        )

        self.assertEqual("/run/home", child["HOME"])
        with self.assertRaises(TypeError):
            agent.child_environment({}, proxy_url="http://x", certificate="/c")
        with self.assertRaises(TypeError):
            agent.AgentRunRequest(
                agent_run_id="agent-run-1",
                objective="Say nothing.",
                workspace=fixtures.scratch(),
                proxy_url="http://x",
                certificate=fixtures.scratch() / "root.pem",
            )


class AssertionTest(unittest.TestCase):
    """Everything about a launch that is decided before the launch happens."""

    def setUp(self):
        self.cli = executable()
        self.launch = agent.launch_directory(request())
        agent.write_settings(self.launch)
        self.runtime = measured(self.cli)

    def assess(self, options_value, environment=None, runtime=None, managed=()):
        return agent.assess(
            options_value,
            {} if environment is None else environment,
            self.runtime if runtime is None else runtime,
            launch_dir=self.launch,
            managed_settings=managed,
        )

    def test_a_contained_launch_on_the_measured_runtime_has_nothing_to_refuse(self):
        self.assertEqual((), self.assess(options(self.launch, self.cli)))

    def test_an_unmeasured_runtime_refuses_and_names_no_executable_to_fall_back_to(self):
        # Version drift and an executable that is not there are one finding,
        # because they fail for one reason: the file this launch would run is
        # not the file the credential matrix was measured against. No entry
        # here names a second place to look -- an unmeasured runtime that fell
        # back to `PATH` would run whichever `claude` the operator installed.
        unmeasured = {
            "nothing installed": {"sdk_version": None, "cli_version": None, "cli_path": None},
            "sdk drift": measured(self.cli) | {"sdk_version": "0.2.133"},
            "cli drift": measured(self.cli) | {"cli_version": "2.1.225"},
            "absent executable": measured(str(fixtures.scratch() / "gone" / "claude")),
            "a directory": measured(str(fixtures.scratch())),
        }

        for case, runtime in unmeasured.items():
            with self.subTest(case=case):
                violations = self.assess(options(self.launch, self.cli), runtime=runtime)

                self.assertEqual([agent.UNMEASURED_RUNTIME], codes(violations))
                self.assertEqual(["runtime:sdk-cli"], sources(violations))
                self.assertNotIn("claude", json.dumps(violations))

        for case in ("nothing installed", "absent executable", "a directory"):
            with self.subTest(case=case):
                self.assertIsNone(agent.bundled_executable(unmeasured[case]))

    def test_a_readable_file_that_cannot_be_executed_is_not_a_bundled_cli(self):
        unreadable = fixtures.scratch() / "claude"
        unreadable.write_text("", encoding="utf-8")
        unreadable.chmod(0o600)

        self.assertIsNone(agent.bundled_executable(measured(str(unreadable))))

    def test_a_launch_that_does_not_name_the_measured_executable_is_refused(self):
        for named in (None, "claude", "/usr/bin/claude", executable()):
            with self.subTest(cli_path=named):
                violations = self.assess(options(self.launch, named))

                self.assertEqual([agent.INVALID_LAUNCH], codes(violations))
                self.assertEqual(["launch:cli_path"], sources(violations))

    def test_each_widening_of_the_child_is_refused_by_the_field_that_widened_it(self):
        widenings = {
            "launch:env": {"env": {"ANTHROPIC_API_KEY": "late"}},
            "launch:setting_sources": {"setting_sources": ["user", "project"]},
            "launch:sandbox": {"sandbox": {"enabled": True}},
            "launch:cwd": {"cwd": str(fixtures.scratch())},
            "launch:builtin_tools": {"tools": ["Bash"]},
            # What the child may call. `bypassPermissions` is only contained
            # while the roster is the runtime's own one tool, so a roster that
            # grew is refused by the same rule that lets the mode stand.
            "launch:permission_mode": {"permission_mode": "acceptEdits"},
            "launch:allowed_tools": {"allowed_tools": [agent.TOOL, "Bash"]},
            "launch:mcp_servers": {"mcp_servers": {agent.SERVER: object(), "other": object()}},
        }

        for source, override in widenings.items():
            with self.subTest(source=source):
                violations = self.assess(options(self.launch, self.cli, **override))

                self.assertEqual([agent.INVALID_LAUNCH], codes(violations))
                self.assertEqual([source], sources(violations))

    def test_every_refusal_is_reported_at_once_rather_than_one_per_attempt(self):
        violations = self.assess(
            options(self.launch, self.cli, env={"x": "y"}, tools=["Bash"]),
            {"ANTHROPIC_API_KEY": "set", "CLAUDE_CODE_USE_BEDROCK": "1"},
        )

        self.assertEqual(
            ["credential_vector", "credential_vector", agent.INVALID_LAUNCH,
             agent.INVALID_LAUNCH],
            codes(violations),
        )
        self.assertEqual(
            ["env:ANTHROPIC_API_KEY", "env:CLAUDE_CODE_USE_BEDROCK",
             "launch:builtin_tools", "launch:env"],
            sources(violations),
        )

    def test_the_options_value_is_not_interpreted_against_an_unmeasured_runtime(self):
        violations = self.assess(
            None, {"ANTHROPIC_AUTH_TOKEN": "set"}, runtime={"cli_path": None}
        )

        self.assertEqual(["credential_vector", agent.UNMEASURED_RUNTIME], codes(violations))
        self.assertEqual(["env:ANTHROPIC_AUTH_TOKEN", "runtime:sdk-cli"], sources(violations))

    def test_a_credential_vector_names_its_variable_and_effect_and_never_its_value(self):
        violations = self.assess(options(self.launch, self.cli), {"ANTHROPIC_BASE_URL": "http://x"})

        self.assertEqual(
            [{"code": "credential_vector", "vector": "ANTHROPIC_BASE_URL",
              "source": "env:ANTHROPIC_BASE_URL", "effect": "destination_override"}],
            list(violations),
        )
        self.assertNotIn("http://x", json.dumps(violations))

    def test_an_empty_api_key_is_the_only_measured_variable_that_is_not_a_vector(self):
        clean = options(self.launch, self.cli)

        self.assertEqual((), self.assess(clean, {"ANTHROPIC_API_KEY": ""}))
        self.assertEqual(
            ["credential_vector"], codes(self.assess(clean, {"ANTHROPIC_AUTH_TOKEN": ""}))
        )

    def test_a_settings_document_the_runtime_does_not_own_is_refused_unread(self):
        elsewhere = fixtures.scratch() / agent.SETTINGS
        elsewhere.write_text(json.dumps({"env": {"ANTHROPIC_API_KEY": "outside"}}), encoding="utf-8")

        for declared in (str(elsewhere), str(self.launch), "settings.json",
                         str(self.launch / "other.json")):
            with self.subTest(settings=declared):
                violations = self.assess(options(self.launch, self.cli, settings=declared))

                self.assertEqual([agent.INVALID_LAUNCH], codes(violations))
                self.assertEqual(["launch:settings"], sources(violations))
                self.assertNotIn("outside", json.dumps(violations))

    def test_a_managed_settings_file_is_read_whether_or_not_the_runtime_asked_for_it(self):
        managed = fixtures.scratch() / "managed-settings.json"
        managed.write_text(json.dumps({"apiKeyHelper": "/bin/echo key"}), encoding="utf-8")

        violations = self.assess(options(self.launch, self.cli), managed=(managed,))

        self.assertEqual(["credential_vector"], codes(violations))
        self.assertEqual("apiKeyHelper", violations[0]["vector"])
        self.assertEqual("off_subscription_auth", violations[0]["effect"])

    def test_a_settings_file_that_cannot_be_read_refuses_rather_than_being_skipped(self):
        for text in ("{not json", json.dumps([1, 2]), json.dumps({"env": "nope"})):
            with self.subTest(text=text):
                managed = fixtures.scratch() / "managed-settings.json"
                managed.write_text(text, encoding="utf-8")

                violations = self.assess(options(self.launch, self.cli), managed=(managed,))

                self.assertEqual([agent.SETTINGS_UNREADABLE], codes(violations))
                self.assertTrue(violations[0]["source"].startswith("settings:managed:"))

    def test_an_environment_that_is_not_a_mapping_refuses_rather_than_being_assumed_empty(self):
        violations = self.assess(options(self.launch, self.cli), ["ANTHROPIC_API_KEY=set"])

        self.assertEqual([agent.INVALID_LAUNCH], codes(violations))
        self.assertEqual(["launch:environment"], sources(violations))


class CorroborationTest(unittest.TestCase):
    """The one question the pre-spawn phase cannot answer for itself."""

    def test_the_init_message_must_report_that_no_key_was_resolved(self):
        self.assertEqual((), agent.corroboration("none"))
        for reported in ("ANTHROPIC_API_KEY", "apiKeyHelper", "temporary", None, ""):
            with self.subTest(api_key_source=reported):
                violations = agent.corroboration(reported)

                self.assertEqual([agent.AUTH_SOURCE_UNEXPECTED], codes(violations))
                self.assertEqual(["init:apiKeySource"], sources(violations))

    def test_a_session_that_never_announced_itself_is_a_different_finding(self):
        for reason in (_launch.PREMATURE, _launch.ABSENT):
            with self.subTest(reason=reason):
                violations = agent.uncorroborated(reason)

                self.assertEqual([agent.INIT_UNCORROBORATED], codes(violations))
                self.assertEqual([f"init:{reason}"], sources(violations))


class RefusalTest(unittest.TestCase):
    def test_a_refusal_carries_records_with_one_shape_and_a_known_phase(self):
        violation = {"code": "credential_vector", "vector": "ANTHROPIC_API_KEY",
                     "source": "env:ANTHROPIC_API_KEY", "effect": "off_subscription_auth"}

        refusal = agent.StartupRefusal([violation], "pre_spawn", "0.2.132", "2.1.224")

        self.assertEqual(
            {"phase": "pre_spawn", "sdk_version": "0.2.132", "cli_version": "2.1.224",
             "violations": [violation]},
            refusal.as_dict(),
        )
        self.assertIn("ANTHROPIC_API_KEY", str(refusal))

    def test_a_refusal_without_a_phase_or_a_well_formed_record_is_not_a_refusal(self):
        good = {"code": "c", "vector": None, "source": "s", "effect": "e"}
        for violations, phase in (
            ([], "pre_spawn"),
            ([good], "started"),
            ([{"code": "c"}], "init"),
            ([good | {"extra": 1}], "init"),
        ):
            with self.subTest(violations=violations, phase=phase):
                with self.assertRaises(ValueError):
                    agent.StartupRefusal(violations, phase)


class SurfaceTest(unittest.TestCase):
    def test_the_tool_surface_serves_nothing_until_it_has_opened_exactly_once(self):
        surface = _launch.Surface()

        self.assertFalse(surface.ready)
        with self.assertRaises(_launch.Closed):
            surface.serve(agent.READY)

        surface.open()
        surface.serve(agent.READY)

        self.assertTrue(surface.ready)
        self.assertEqual([agent.READY], surface.served)

        surface.open()

        self.assertFalse(surface.ready)
        with self.assertRaises(_launch.Closed):
            surface.serve(agent.READY)


class ChildTest(unittest.TestCase):
    """The child's own order of operations, without a supervisor around it."""

    def setUp(self):
        self.launch = agent.launch_directory(request())
        agent.write_settings(self.launch)
        self.job = {
            "agent_run_id": "agent-run-1",
            "objective": "Say nothing.",
            "model": None,
            "max_turns": 3,
            "launch_dir": str(self.launch),
            "settings": str(self.launch / agent.SETTINGS),
        }

    def transport(self, **_):
        raise AssertionError("a transport was constructed for a refused launch")

    def test_an_unmeasured_runtime_refuses_before_a_transport_is_constructed(self):
        with self.assertRaises(agent.StartupRefusal) as raised:
            asyncio.run(
                _launch.run(
                    self.job,
                    environment={},
                    runtime={"sdk_version": None, "cli_version": None, "cli_path": None},
                    transport=self.transport,
                )
            )

        self.assertEqual("pre_spawn", raised.exception.phase)
        self.assertEqual([agent.UNMEASURED_RUNTIME], codes(raised.exception.violations))

    def test_a_credential_vector_in_the_inherited_environment_refuses_the_same_way(self):
        with self.assertRaises(agent.StartupRefusal) as raised:
            asyncio.run(
                _launch.run(
                    self.job,
                    environment={"ANTHROPIC_API_KEY": "inherited"},
                    runtime={"sdk_version": None, "cli_version": None, "cli_path": None},
                    transport=self.transport,
                )
            )

        self.assertIn("credential_vector", codes(raised.exception.violations))

    @unittest.skipIf(INSTALLED, NEEDS_NO_SDK)
    def test_a_refused_child_reports_its_refusal_on_standard_error_and_exits_ex_config(self):
        errors = io.StringIO()

        with contextlib.redirect_stderr(errors):
            status = _launch.main(io.StringIO(json.dumps(self.job)))

        self.assertEqual(agent.REFUSED, status)
        reported = json.loads(errors.getvalue())[_launch.REFUSAL]
        self.assertEqual("pre_spawn", reported["phase"])
        self.assertEqual([agent.UNMEASURED_RUNTIME], codes(reported["violations"]))


class ReadbackTest(unittest.TestCase):
    """What the supervisor is willing to believe about a child it did not watch."""

    def report(self, document) -> str:
        return f"a warning line\n{json.dumps(document)}\n"

    def test_a_well_formed_refusal_on_standard_error_is_raised_as_the_refusal(self):
        violation = {"code": agent.UNMEASURED_RUNTIME, "vector": None,
                     "source": "runtime:sdk-cli", "effect": agent.UNVERIFIABLE}

        refusal = agent._refusal(
            self.report({_launch.REFUSAL: {"phase": "init", "sdk_version": "0.2.132",
                                           "cli_version": "2.1.224",
                                           "violations": [violation]}})
        )

        self.assertEqual("init", refusal.phase)
        self.assertEqual((violation,), refusal.violations)

    def test_a_malformed_refusal_is_not_turned_into_one(self):
        good = {"code": "c", "vector": None, "source": "s", "effect": "e"}
        for reported in (
            {"phase": "init", "violations": []},
            {"phase": "elsewhere", "violations": [good]},
            {"phase": "init", "violations": [{"code": "c"}]},
            {"phase": "init", "violations": "everything"},
            "refused",
        ):
            with self.subTest(reported=reported):
                self.assertIsNone(agent._refusal(self.report({_launch.REFUSAL: reported})))

        self.assertIsNone(agent._refusal(self.report({"result": "ok"})))
        self.assertIsNone(agent._refusal("not a document at all"))

    def test_the_last_document_a_child_wrote_is_the_one_that_is_read(self):
        stream = 'noise\n{"answers": 1}\nmore noise\n{"answers": 2}\n[1, 2]\n'

        self.assertEqual({"answers": 2}, agent._last_document(stream))
        self.assertIsNone(agent._last_document("\n  \n"))


@unittest.skipIf(INSTALLED, NEEDS_NO_SDK)
class UnmeasuredSupervisorTest(unittest.TestCase):
    """One real child, on an interpreter the credential matrix does not cover."""

    def test_a_child_that_refuses_raises_the_refusal_in_the_caller(self):
        with self.assertRaises(agent.StartupRefusal) as raised:
            agent.agent_run(request(timeout=120.0))

        self.assertEqual("pre_spawn", raised.exception.phase)
        self.assertEqual([agent.UNMEASURED_RUNTIME], codes(raised.exception.violations))


@unittest.skipIf(not INSTALLED, NEEDS_SDK)
class RealChildTest(unittest.TestCase):
    """One real child, one real transport, and a model API on loopback.

    The far end is `fixtures.ControlUpstream` rather than Anthropic, so the
    session is real in every respect the assertion is about -- process,
    environment, settings, bundled executable, init handshake, tool surface --
    and costs nothing, needs no subscription and cannot reach a target.
    """

    def test_a_real_child_starts_clean_and_opens_its_tool_surface_exactly_once(self):
        upstream = fixtures.ControlUpstream(agent.TOOL)
        self.addCleanup(upstream.stop)
        home = fixtures.subscription(fixtures.scratch() / "home")

        result = agent.agent_run(
            request(
                objective=f"Call the {agent.READY} tool, then say {upstream.SPOKEN}.",
                proxy_url=upstream.url,
                certificate=upstream.certificate,
                home=home,
                max_turns=3,
                timeout=300.0,
            )
        )

        self.assertEqual(_startup.KNOWN_RUNTIME, (result.sdk_version, result.cli_version))
        self.assertEqual(agent.EXPECTED_KEY_SOURCE, result.api_key_source)
        self.assertEqual(1, result.tool_ready)
        self.assertEqual((agent.READY,), result.tools_served)
        self.assertEqual(upstream.SPOKEN, result.text)
        self.assertEqual(("end_turn", 2), (result.stop_reason, result.answers))
        # Every byte the child sent went through the runtime's door, to the one
        # host the door presents a certificate for. A floor rather than a count
        # of completions: the CLI makes background requests of its own, and the
        # number of them is not this ticket's business.
        self.assertEqual({"api.anthropic.com"}, {host for host, _ in upstream.seen})
        self.assertGreaterEqual(upstream.completions, result.answers)

    def test_the_one_options_value_is_the_one_that_was_assessed(self):
        launch = agent.launch_directory(request())
        agent.write_settings(launch)
        job = {
            "launch_dir": str(launch),
            "settings": str(launch / agent.SETTINGS),
            "model": None,
            "max_turns": 3,
            "objective": "Say nothing.",
        }
        runtime = _launch.runtime_facts()

        value = _launch.options_for(job, runtime, _launch.server(_launch.Surface()))

        self.assertEqual((), agent.assess(value, {}, runtime, launch_dir=launch,
                                          managed_settings=()))
        self.assertEqual(str(agent.bundled_executable(runtime)), value.cli_path)
        self.assertEqual([agent.TOOL], value.allowed_tools)


@unittest.skipIf(not INSTALLED, NEEDS_SDK)
class AnnouncementTest(unittest.TestCase):
    """What the runtime does with a CLI that announces itself more than once."""

    def test_a_child_announced_twice_counts_both_and_serves_nothing_after(self):
        # Unreachable from a CLI that behaves, and that is the point: the
        # criterion is `exactly once`, so the count has to be able to say two.
        announced = _launch.SystemMessage(
            _launch.INIT, {"apiKeySource": agent.EXPECTED_KEY_SOURCE}
        )

        async def transport(**_):
            yield announced
            yield announced

        launch = agent.launch_directory(request())
        agent.write_settings(launch)
        runtime = _launch.runtime_facts()
        job = {
            "launch_dir": str(launch),
            "settings": str(launch / agent.SETTINGS),
            "objective": "Say nothing.",
            "model": None,
            "max_turns": 1,
        }

        result = asyncio.run(_launch.run(job, environment={}, runtime=runtime,
                                         transport=transport))

        # Two openings, and `Surface.ready` is `opened == 1`: the tools stopped
        # answering the moment the second announcement arrived.
        self.assertEqual(2, result["tool_ready"])
        self.assertEqual([], result["tools_served"])


if __name__ == "__main__":
    unittest.main()
