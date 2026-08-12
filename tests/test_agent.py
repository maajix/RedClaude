import ast
import asyncio
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
import uuid
from pathlib import Path
from unittest import mock

from redkraken import _launch, _startup, agent, isolation, tls
from redkraken.outcome import EXIT_STARTUP_REFUSED, STARTUP_REFUSED
from tests import ROOT, control_upstream, fixtures
from tests.fixtures import EXPORTED, docker, unlatched


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

#: Why the launch tests are conditional too. There is one launch mechanism and
#: it is a container, so a machine with no engine can assert every rule in this
#: module and start nothing. Opt-in rather than detected, so a suite that ran
#: green never quietly meant "no child was started": a machine that is meant to
#: prove the contained child says so.
LIVE = os.environ.get("RK_TEST_CONTAINERS") == "1"
NEEDS_CONTAINERS = "set RK_TEST_CONTAINERS=1 to run the contained Agent child"

#: Where the model API answers inside the run network, and how long a peer has
#: to start answering before the run that needs it is abandoned.
UPSTREAM_PORT = 18443
UPSTREAM_READY = 30.0

#: Where the repository is mounted in the upstream peer. It is the repository
#: rather than the application because the upstream is a test fixture: it
#: imports `tests.fixtures`, which the wheel does not carry.
REPOSITORY = "/opt/rk2-repo"
AUTHORITY = "/opt/rk2-authority"

#: A child that reads the managed settings locations this suite names instead of
#: the platform's. The rebinding is done in the child because that is the only
#: place it means anything: `_launch.run` reads `agent.MANAGED_SETTINGS` when the
#: child runs, so a supervisor-side patch would patch another process's idea of
#: where settings live. The alternative is writing to `/etc` on the machine
#: running the suite, which is not one.
SETTINGS_CHILD = """
import sys
from pathlib import Path
from redkraken import _launch, agent
agent.MANAGED_SETTINGS = (Path(sys.argv[1]),)
raise SystemExit(_launch.main())
"""

#: A child that gets as far as init and is answered there by a transport this
#: suite holds. The transport is the one thing about this phase a launch cannot
#: arrange honestly: on the measured runtime pair, no input makes the real CLI
#: report a key source other than `none` without a credential vector the
#: pre-spawn phase has already refused. Everything else is the real thing -- a
#: process, the environment and filesystem it was given, `_launch.run` in the
#: order it runs, and the refusal written where a child writes one.
INIT_CHILD = """
import asyncio, json, sys
from pathlib import Path
from redkraken import _launch, agent


class Stream:
    def __init__(self, messages):
        self.messages = list(messages)
        self.closed = 0

    def __call__(self, **_):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)

    async def aclose(self):
        self.closed += 1


def announcement(**data):
    return _launch.SystemMessage(_launch.INIT, data)


FAMILIES = {
    "absent": [],
    "first_message": [_launch.SystemMessage("compact_boundary", {})],
    "unexpected": [announcement(apiKeySource="ANTHROPIC_API_KEY")],
    "unreported": [announcement()],
}

stream = Stream(FAMILIES[sys.argv[1]])
status = 0
try:
    asyncio.run(_launch.run(json.loads(sys.stdin.read()), transport=stream))
except agent.StartupRefusal as refusal:
    print(json.dumps({_launch.REFUSAL: refusal.as_dict()}), file=sys.stderr, flush=True)
    status = agent.REFUSED
Path(sys.argv[2]).write_text(json.dumps({"closed": stream.closed}), encoding="utf-8")
raise SystemExit(status)
"""

#: A supervisor that refuses one Agent run and then asks for another. `_spawn`
#: is replaced rather than a container started, because what is under test is
#: the supervisor's memory rather than the child: the second run must be refused
#: with nothing spawned, and the only way to see that nothing was spawned is to
#: hold the thing that would have spawned it.
LATCH_CHILD = """
import json, sys
from redkraken import _startup, agent
from tests import fixtures

spawned = []
raised = []
refusing = sys.argv[1] == "present"


def spawn(request, job):
    spawned.append(request.agent_run_id)
    if refusing:
        raise agent.StartupRefusal(
            [{"code": "credential_vector", "vector": "ANTHROPIC_API_KEY",
              "source": "env:ANTHROPIC_API_KEY", "effect": "off_subscription_auth"}],
            "pre_spawn", *_startup.KNOWN_RUNTIME)
    return request.agent_run_id


agent._spawn = spawn
status = 0
for index in (1, 2):
    try:
        agent.agent_run(agent.AgentRunRequest(
            agent_run_id="agent-run-%d" % index,
            objective="Say nothing.",
            container=fixtures.boundary(),
        ))
    except agent.StartupRefusal as refusal:
        raised.append(type(refusal).__name__)
        status = agent.diagnostics(refusal).exit_code
print(json.dumps({"spawned": spawned, "raised": raised}))
raise SystemExit(status)
"""


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


def job(launch_workspace, **overrides) -> dict:
    """One job document, as the supervisor writes it to the child's input."""
    fields = {
        "agent_run_id": "agent-run-1",
        "objective": "Say nothing.",
        "model": None,
        "max_turns": 3,
        "workspace": str(launch_workspace),
    }
    fields.update(overrides)
    return fields


def launched(
    environment: dict, arguments: tuple = ("-m", agent.CHILD), workspace=None
) -> subprocess.CompletedProcess[str]:
    """One real child launch: a job on standard input, one environment around it.

    A process rather than a call into `_launch`, because the assertion's subject
    is the environment and the filesystem a launch actually got. An in-process
    version would assess this interpreter's, which is the one thing a test
    cannot arrange honestly.
    """
    return subprocess.run(
        [sys.executable, "-P", *arguments],
        input=json.dumps(job(workspace or fixtures.scratch())),
        env={
            "PATH": os.environ.get("PATH", ""),
            isolation.IMPORT_PATH: str(ROOT / "src"),
            **environment,
        },
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


class Stream:
    """A transport that answers a fixed script and counts its own closing.

    Deliberately not an async generator: an exhausted generator cannot tell
    `the runtime closed me` from `I ran out`, and what an init refusal has to
    prove is the first one.
    """

    def __init__(self, *messages) -> None:
        self.messages = list(messages)
        self.closed = 0

    def __call__(self, **_):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)

    async def aclose(self) -> None:
        self.closed += 1


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
        workspace = fixtures.scratch()

        launch = agent.launch_directory(workspace, "agent-run-1")
        settings = agent.write_settings(launch)

        self.assertEqual(workspace.resolve() / "agent-run-1", launch)
        self.assertEqual(agent.PRIVATE, launch.stat().st_mode & 0o777)
        self.assertEqual(launch / agent.SETTINGS, settings)
        self.assertEqual(0o600, settings.stat().st_mode & 0o777)
        self.assertEqual(agent.SETTINGS_DOCUMENT, json.loads(settings.read_text()))

    def test_a_run_identifier_that_is_not_one_component_is_refused(self):
        for identifier in ("../escape", "nested/run", ".", "", "sub/../../out"):
            with self.subTest(identifier=identifier):
                with self.assertRaises(ValueError):
                    agent.launch_directory(fixtures.scratch(), identifier)


class RequestTest(unittest.TestCase):
    """What a run cannot be asked for without."""

    def test_a_run_cannot_be_asked_for_without_a_boundary_to_run_it_in(self):
        # There is no default. A request that could omit the boundary would be
        # a request that could run on the supervisor's own machine, with the
        # supervisor's own home -- which is where the CLI resolves the
        # operator's own subscription -- and a route to any target it can name.
        with self.assertRaises(TypeError):
            agent.AgentRunRequest(agent_run_id="agent-run-1", objective="Say nothing.")


class AssertionTest(unittest.TestCase):
    """Everything about a launch that is decided before the launch happens."""

    def setUp(self):
        self.cli = executable()
        self.launch = agent.launch_directory(fixtures.scratch(), "agent-run-1")
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
        self.job = job(fixtures.scratch())

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

    def test_a_real_child_that_refused_is_read_back_as_the_refusal_it_made(self):
        """The two halves joined, on a machine with no engine at all.

        `ReadbackTest` above reads stderr this suite wrote and `ChildTest`
        refuses in-process; this is a child that is a process, refusing for
        itself, whose actual standard error the supervisor's own reader turns
        back into a refusal. A container would prove the same join and prove it
        only where docker is, which is not everywhere the refusal has to hold.
        """
        child = launched({"ANTHROPIC_API_KEY": EXPORTED})

        self.assertEqual(agent.REFUSED, child.returncode, child.stderr)
        refusal = agent._refusal(child.stderr)
        self.assertEqual("pre_spawn", refusal.phase)
        self.assertIn("credential_vector", codes(refusal.violations))
        if not INSTALLED:
            # No SDK is an unmeasured runtime, and it is refused rather than
            # resolved from `PATH`: nothing the child wrote names a second
            # executable to have tried.
            self.assertIn(agent.UNMEASURED_RUNTIME, codes(refusal.violations))
        # And the value that caused it never crossed back out.
        self.assertNotIn(EXPORTED, child.stderr + child.stdout)


@unittest.skipIf(not INSTALLED, NEEDS_SDK)
class OptionsTest(unittest.TestCase):
    """The one options value, built the way a child builds it."""

    def test_the_one_options_value_is_the_one_that_was_assessed(self):
        launch = agent.launch_directory(fixtures.scratch(), "agent-run-1")
        agent.write_settings(launch)
        runtime = _launch.runtime_facts()

        value = _launch.options_for(
            job(launch.parent), runtime, _launch.server(_launch.Surface()), launch
        )

        self.assertEqual((), agent.assess(value, {}, runtime, launch_dir=launch,
                                          managed_settings=()))
        self.assertEqual(str(agent.bundled_executable(runtime)), value.cli_path)
        self.assertEqual([agent.TOOL], value.allowed_tools)


@unittest.skipUnless(LIVE, NEEDS_CONTAINERS)
class ContainedChildTest(unittest.TestCase):
    """One real child, in the boundary, against a model API that is a peer.

    The far end is `fixtures.ControlUpstream` rather than Anthropic, so the
    session is real in every respect the assertion is about -- container,
    network, process, environment, settings, bundled executable, init
    handshake, tool surface -- and costs nothing, needs no subscription and
    cannot reach a target.

    It is a container rather than a thread on loopback because it has to be:
    `isolation.run` verifies that the proxy named in the URL is the one other
    peer on an internal network, and an internal network is exactly what the
    test process is not on.
    """

    @classmethod
    def setUpClass(cls):
        if shutil.which("docker") is None:
            raise unittest.SkipTest("docker is not on PATH")
        if docker("image", "inspect", fixtures.AGENT_IMAGE, check=False).returncode:
            raise unittest.SkipTest(
                f"the local Agent test image is absent: {fixtures.AGENT_IMAGE}"
            )

        suffix = uuid.uuid4().hex[:12]
        cls.network = f"rk2-agent-{suffix}"
        cls.upstream = f"rk2-upstream-{suffix}"
        cls.root = Path(tempfile.mkdtemp(prefix="rk2-contained-"))
        cls.authority = tls.authority(cls.root / "authority")
        try:
            docker("network", "create", "--internal", cls.network)
            cls._serve()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "upstream", ""):
            docker("rm", "--force", cls.upstream, check=False)
        if getattr(cls, "network", ""):
            docker("network", "rm", cls.network, check=False)
        root = getattr(cls, "root", None)
        if root is not None:
            shutil.rmtree(root, ignore_errors=True)

    @classmethod
    def _serve(cls) -> None:
        """Start the model API as a peer, and wait for it to be one."""
        docker(
            "run",
            "--detach",
            "--rm",
            "--pull",
            "never",
            "--name",
            cls.upstream,
            "--network",
            cls.network,
            "--mount",
            f"type=bind,src={ROOT},dst={REPOSITORY},readonly",
            "--mount",
            f"type=bind,src={cls.authority.directory},dst={AUTHORITY}",
            "--env",
            f"PYTHONPATH={REPOSITORY}/src:{REPOSITORY}",
            "--entrypoint",
            "",
            fixtures.AGENT_IMAGE,
            "python3",
            "-m",
            control_upstream.__name__,
            agent.TOOL,
            AUTHORITY,
            str(UPSTREAM_PORT),
        )
        deadline = time.monotonic() + UPSTREAM_READY
        while time.monotonic() < deadline:
            if control_upstream.LISTENING in docker("logs", cls.upstream, check=False).stdout:
                return
            time.sleep(0.2)
        raise AssertionError(docker("logs", cls.upstream, check=False).stderr)

    def boundary(self, **overrides) -> isolation.AgentContainer:
        """The boundary an Agent child runs in, with everything it needs in it."""
        fields = {
            "network": self.network,
            "proxy_container": self.upstream,
            "proxy_url": f"http://{self.upstream}:{UPSTREAM_PORT}",
            "certificate": self.authority.certificate,
            "application": ROOT / "src",
            "sdk": self.installed_sdk(),
            "home": self.home(),
        }
        fields.update(overrides)
        return fixtures.boundary(**fields)

    def installed_sdk(self) -> Path | None:
        """Where this machine keeps the SDK, so the container can be measured."""
        if _launch.claude_agent_sdk is None:
            return None
        return Path(_launch.claude_agent_sdk.__file__).resolve().parent.parent

    def home(self) -> Path:
        """A home of this run's own, holding a credential that is not one.

        Writable by the container's unprivileged user rather than by this one:
        the CLI keeps session state in it, and a home the child cannot write is
        a session that never starts. The mode is wide because there is no other
        way to hand a directory to uid 65534 without being root, and it is
        contained anyway: the directory lives under this run's own private
        scratch root, and the credential in it is a literal.
        """
        home = fixtures.subscription(fixtures.scratch() / "home")
        home.chmod(0o777)
        return home

    def requests_seen(self) -> list[tuple[str, str]]:
        """What arrived at the far end, read back across the boundary."""
        seen = []
        for line in docker("logs", self.upstream).stdout.splitlines():
            host, tab, request = line.partition("\t")
            if tab:
                seen.append((host, request))
        return seen

    @unittest.skipIf(not INSTALLED, NEEDS_SDK)
    def test_a_contained_child_starts_clean_and_opens_its_tool_surface_exactly_once(self):
        result = agent.agent_run(
            agent.AgentRunRequest(
                agent_run_id="agent-run-1",
                objective=(
                    f"Call the {agent.READY} tool, then say "
                    f"{fixtures.ControlUpstream.SPOKEN}."
                ),
                container=self.boundary(),
                max_turns=3,
                timeout=300.0,
            )
        )

        self.assertEqual(_startup.KNOWN_RUNTIME, (result.sdk_version, result.cli_version))
        self.assertEqual(agent.EXPECTED_KEY_SOURCE, result.api_key_source)
        self.assertEqual(1, result.tool_ready)
        self.assertEqual((agent.READY,), result.tools_served)
        self.assertEqual(fixtures.ControlUpstream.SPOKEN, result.text)
        self.assertEqual(("end_turn", 2), (result.stop_reason, result.answers))
        # Every byte the child sent went through the runtime's door, to the one
        # host the door presents a certificate for -- and the door was the only
        # peer it had. A floor rather than a count of completions: the CLI makes
        # background requests of its own, and how many is not this ticket's
        # business.
        seen = self.requests_seen()
        self.assertEqual({"api.anthropic.com"}, {host for host, _ in seen})
        self.assertGreaterEqual(
            sum(1 for _, line in seen if line.startswith("POST /v1/messages")), result.answers
        )

    def test_the_boundary_an_agent_child_runs_in_has_no_path_to_a_target(self):
        """Measured in the Agent child's own boundary, not inherited from one.

        `tests/test_isolation.py` proves the topology of a container built to
        prove topology. This is the container an Agent child actually runs in --
        the same `AgentContainer`, with the application, the SDK and the home
        mounted -- so what is asserted is that adding the three things a child
        needs to exist did not add a way out, and that the only home inside is
        the one the runtime mounted.
        """
        probe = r"""
import json, os, socket

def reaches(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.6):
            return True
    except OSError:
        return False

def resolves(host):
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return True
    except OSError:
        return False

print(json.dumps({
    'model_api': resolves('api.anthropic.com'),
    'internet_tcp': reaches('1.1.1.1', 443),
    'peer': reaches(%r, %d),
    'home': sorted(os.listdir(os.environ['HOME'])),
    'application': sorted(os.listdir(%r))[:1],
}))
""" % (self.upstream, UPSTREAM_PORT, isolation.APPLICATION)

        result = isolation.run(
            self.boundary(), (isolation.INTERPRETER, "-c", probe), timeout=30
        )

        self.assertEqual(0, result.returncode, result.stderr)
        facts = json.loads(result.stdout)
        # The model API is not a name this child can resolve, let alone reach:
        # every request it makes goes to the door, which is the only peer, and
        # the door is what holds a certificate for that name.
        self.assertFalse(facts["model_api"])
        self.assertFalse(facts["internet_tcp"])
        self.assertTrue(facts["peer"])
        self.assertEqual([".claude", ".claude.json"], facts["home"])
        self.assertEqual(["redkraken"], facts["application"])

    def test_a_boundary_without_the_measured_sdk_refuses_in_the_caller(self):
        # The child is measured against what was mounted, not against what the
        # supervisor's own interpreter happens to have installed. Nothing
        # mounted is an unmeasured runtime, and it refuses before a transport.
        with unlatched(), self.assertRaises(agent.StartupRefusal) as raised:
            agent.agent_run(
                agent.AgentRunRequest(
                    agent_run_id="agent-run-1",
                    objective="Say nothing.",
                    container=self.boundary(sdk=None),
                    timeout=120.0,
                )
            )

        self.assertEqual("pre_spawn", raised.exception.phase)
        self.assertEqual([agent.UNMEASURED_RUNTIME], codes(raised.exception.violations))


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

        runtime = _launch.runtime_facts()

        result = asyncio.run(
            _launch.run(
                job(fixtures.scratch(), max_turns=1),
                environment={},
                runtime=runtime,
                transport=transport,
            )
        )

        # Two openings, and `Surface.ready` is `opened == 1`: the tools stopped
        # answering the moment the second announcement arrived.
        self.assertEqual(2, result["tool_ready"])
        self.assertEqual([], result["tools_served"])


class VectorChildTest(unittest.TestCase):
    """Every vector an operator can leave lying about, through a real launch.

    The rules themselves are `AssertionTest`'s, and they are asserted on inputs
    a function was handed. What a child adds is the only thing a pure function
    cannot say: that the environment and the files being measured are the ones
    the launch actually got, that it refuses before it uses either, and that
    what it writes back names the vector and never carries the value.

    Each case is compared against `_startup.evaluate_inputs` for the same
    symbolic input, so the child and the measured credential matrix are held to
    one answer rather than to two that happen to agree.
    """

    def refused(self, child) -> agent.StartupRefusal:
        """The refusal one child made, and the evidence it started nothing."""
        self.assertEqual(agent.REFUSED, child.returncode, child.stderr)
        self.assertEqual("", child.stdout.strip())
        self.assertNotIn(EXPORTED, child.stderr + child.stdout)
        refusal = agent._refusal(child.stderr)
        self.assertIsNotNone(refusal, child.stderr)
        self.assertEqual("pre_spawn", refusal.phase)
        return refusal

    def credentials(self, refusal: agent.StartupRefusal) -> list[dict]:
        """The records the matrix decides, apart from what it could not measure.

        An interpreter without the SDK also reports an unmeasured runtime, and
        that is a fact about the machine the suite is running on rather than
        about the vector under test.
        """
        return [
            record for record in refusal.violations if record["code"] == "credential_vector"
        ]

    def settings_child(self, document: object) -> agent.StartupRefusal:
        """One child whose managed settings location holds this document."""
        settings = fixtures.scratch() / "managed-settings.json"
        settings.write_text(
            document if isinstance(document, str) else json.dumps(document), encoding="utf-8"
        )
        self.settings = settings
        return self.refused(launched({}, arguments=("-c", SETTINGS_CHILD, str(settings))))

    def test_every_watched_variable_refuses_the_launch_that_inherited_it(self):
        for name in _startup.WATCHED_ENV_VECTORS:
            with self.subTest(vector=name):
                refusal = self.refused(launched({name: EXPORTED}))

                self.assertEqual(
                    _startup.evaluate_inputs({"environment": {name: EXPORTED}})["violations"],
                    self.credentials(refusal),
                )

    def test_a_settings_helper_and_a_settings_variable_are_read_where_they_load(self):
        # Every watched name again, in the other place a launch can inherit one.
        # A document's `env` block is exported by the CLI into the process the
        # CLI starts, so a vector named there is the same vector arriving by a
        # route the process environment cannot be searched for.
        exported = [
            (f"{name}, exported by a document the runtime never asked for",
             {"env": {name: EXPORTED}})
            for name in _startup.WATCHED_ENV_VECTORS
        ]
        for description, document in (
            *exported,
            ("a helper the CLI would run for a key", {"apiKeyHelper": "/usr/local/bin/key"}),
            (
                "both at once, in the file the runtime never asked for",
                {"apiKeyHelper": "/usr/local/bin/key", "env": {"ANTHROPIC_AUTH_TOKEN": EXPORTED}},
            ),
        ):
            with self.subTest(description):
                refusal = self.settings_child(document)

                self.assertEqual(
                    _startup.evaluate_inputs(
                        {
                            "settings": [
                                {
                                    "kind": "managed",
                                    "path": str(self.settings),
                                    "document": document,
                                }
                            ]
                        }
                    )["violations"],
                    self.credentials(refusal),
                )

    def test_a_managed_document_that_cannot_be_read_refuses_rather_than_being_skipped(self):
        for description, document in (
            ("a document that stops halfway", '{"apiKeyHelper": '),
            ("a document that is not an object", "[]"),
            ("an env member that is not one", '{"env": "ANTHROPIC_API_KEY=k"}'),
        ):
            with self.subTest(description):
                refusal = self.settings_child(document)

                self.assertIn(agent.SETTINGS_UNREADABLE, codes(refusal.violations))
                self.assertIn(
                    f"settings:managed:{self.settings}#document", sources(refusal.violations)
                )

    @unittest.skipIf(not INSTALLED, NEEDS_SDK)
    def test_each_unexpected_init_refuses_in_the_child_that_read_it(self):
        # The fourth vector family, through a launch like the other three. What
        # `INIT_CHILD` supplies is the transport and nothing else, because a
        # measured CLI cannot be made to answer this way -- see its note.
        for family, source in (
            ("absent", "init:absent"),
            ("first_message", "init:first_message"),
            ("unexpected", "init:apiKeySource"),
            ("unreported", "init:apiKeySource"),
        ):
            with self.subTest(family):
                evidence = fixtures.scratch() / "transport.json"
                child = launched(
                    {}, arguments=("-c", INIT_CHILD, family, str(evidence))
                )

                self.assertEqual(agent.REFUSED, child.returncode, child.stderr)
                self.assertEqual("", child.stdout.strip())
                refusal = agent._refusal(child.stderr)
                self.assertIsNotNone(refusal, child.stderr)
                self.assertEqual("init", refusal.phase)
                self.assertEqual([source], sources(refusal.violations))
                # The child closed the transport before writing the refusal, so
                # the run it could not corroborate was not still going when the
                # supervisor was told about it.
                self.assertEqual(
                    {"closed": 1}, json.loads(evidence.read_text(encoding="utf-8"))
                )


@unittest.skipIf(not INSTALLED, NEEDS_SDK)
class InitRefusalTest(unittest.TestCase):
    """The phase only a running CLI can fail, and what is left when it does.

    The seam rather than a child, and one level in from
    `VectorChildTest.test_each_unexpected_init_refuses_in_the_child_that_read_it`,
    which launches the same four families as processes. What is left after a
    refusal -- a surface that never opened, a transport that was closed -- is
    state inside the run, and this is where it can be read.
    """

    def corroborate(self, stream: Stream) -> agent.StartupRefusal:
        """What `_corroborate` refuses, with the surface it never opened."""
        self.surface = _launch.Surface()
        with self.assertRaises(agent.StartupRefusal) as raised:
            asyncio.run(_launch._corroborate(stream, self.surface, _launch.runtime_facts()))
        return raised.exception

    def announcement(self, **data) -> object:
        return _launch.SystemMessage(_launch.INIT, data)

    def test_each_unexpected_init_refuses_and_names_what_it_read(self):
        for description, stream, source in (
            ("a run that ended without announcing itself", Stream(), "init:absent"),
            (
                "work produced before the runtime had assessed it",
                Stream(_launch.SystemMessage("compact_boundary", {})),
                "init:first_message",
            ),
            (
                "a key resolved from somewhere this runtime did not expect",
                Stream(self.announcement(apiKeySource="ANTHROPIC_API_KEY")),
                "init:apiKeySource",
            ),
            (
                "an announcement that reports no source at all",
                Stream(self.announcement()),
                "init:apiKeySource",
            ),
        ):
            with self.subTest(description):
                refusal = self.corroborate(stream)

                self.assertEqual("init", refusal.phase)
                self.assertEqual([source], sources(refusal.violations))
                self.assertEqual(_startup.KNOWN_RUNTIME[0], refusal.sdk_version)

    def test_an_init_refusal_serves_no_tool_and_leaves_no_transport_running(self):
        stream = Stream(self.announcement(apiKeySource="ANTHROPIC_API_KEY"))

        self.corroborate(stream)

        # Zero, not one-and-closed: the surface opens after corroboration, so a
        # refusal there is a run in which no tool was ever callable.
        self.assertEqual((0, []), (self.surface.opened, self.surface.served))
        self.assertEqual(1, stream.closed)

    def test_the_launch_that_reaches_init_refuses_there_and_returns_nothing(self):
        stream = Stream(self.announcement(apiKeySource="ANTHROPIC_API_KEY"))

        with self.assertRaises(agent.StartupRefusal) as raised:
            asyncio.run(
                _launch.run(
                    job(fixtures.scratch(), max_turns=1),
                    environment={},
                    runtime=_launch.runtime_facts(),
                    transport=stream,
                )
            )

        self.assertEqual("init", raised.exception.phase)
        self.assertEqual([agent.AUTH_SOURCE_UNEXPECTED], codes(raised.exception.violations))
        self.assertEqual(1, stream.closed)


class LatchTest(unittest.TestCase):
    """PH2-17: a process that has refused starts no further Agent run.

    Two processes, because the latch is process state and a test that reset it
    would be testing something else. What the supervisor does with the second
    request is the whole claim: it is refused with the violations the first one
    measured, nothing is spawned for it, and the process exits on the class the
    refusal belongs to rather than on an unclassified error.
    """

    def supervise(self, credential: str) -> tuple[int, dict]:
        """One supervisor process, asked for two Agent runs."""
        child = subprocess.run(
            [sys.executable, "-P", "-c", LATCH_CHILD, credential],
            env={
                "PATH": os.environ.get("PATH", ""),
                isolation.IMPORT_PATH: os.pathsep.join((str(ROOT / "src"), str(ROOT))),
            },
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        self.assertNotEqual("", child.stdout.strip(), child.stderr)
        return child.returncode, json.loads(child.stdout)

    def test_a_refused_process_refuses_the_next_run_without_spawning_it(self):
        status, observed = self.supervise("present")

        self.assertEqual(EXIT_STARTUP_REFUSED, status)
        self.assertEqual(["agent-run-1"], observed["spawned"])
        self.assertEqual(["StartupRefusal", "Latched"], observed["raised"])

    def test_a_process_that_started_after_the_remediation_runs_both(self):
        status, observed = self.supervise("gone")

        self.assertEqual(0, status)
        self.assertEqual(["agent-run-1", "agent-run-2"], observed["spawned"])
        self.assertEqual([], observed["raised"])


class DiagnosticsTest(unittest.TestCase):
    """What an operator is told about a refusal, and what they are not."""

    def refusal(self, environment: dict) -> agent.StartupRefusal:
        violations = agent.assess(
            None, environment, {}, launch_dir=fixtures.scratch(), managed_settings=()
        )
        return agent.StartupRefusal(violations, "pre_spawn", *_startup.KNOWN_RUNTIME)

    def test_a_refusal_names_every_vector_its_phase_and_its_measured_effect(self):
        refusal = self.refusal({name: EXPORTED for name in _startup.WATCHED_ENV_VECTORS})

        rendered = agent.diagnostics(refusal).as_dict()

        self.assertFalse(rendered["ok"])
        self.assertEqual(EXIT_STARTUP_REFUSED, rendered["exit_code"])
        self.assertEqual("pre_spawn", rendered["phase"])
        self.assertEqual(_startup.KNOWN_RUNTIME[1], rendered["cli_version"])
        self.assertEqual(
            {STARTUP_REFUSED}, {violation["code"] for violation in rendered["violations"]}
        )
        self.assertEqual(
            sorted(f"env:{name}" for name in _startup.WATCHED_ENV_VECTORS),
            sorted(
                violation["source"]
                for violation in rendered["violations"]
                if violation["source"].startswith("env:")
            ),
        )
        for effect in ("off_subscription_auth", "startup_denial", "provider_reroute"):
            self.assertIn(effect, json.dumps(rendered))

    def test_no_rendering_of_a_refusal_carries_the_value_that_caused_it(self):
        rendered = agent.diagnostics(self.refusal({"ANTHROPIC_API_KEY": EXPORTED})).as_dict()

        self.assertNotIn(EXPORTED, json.dumps(rendered))


class RecordingTest(unittest.TestCase):
    """A refusal with nowhere to record it, and one that could not be recorded.

    Both are the same question asked from either side: a refusal before there is
    a Program is raised and written nowhere, and a run that names a Program the
    cleanup could not use is refused before it is started rather than after.
    """

    class Untouched:
        """A connection that fails the run if a refusal reaches a database."""

        def execute(self, *arguments):
            raise AssertionError("a refusal with no Program was recorded against one")

    def request(self, **overrides) -> agent.AgentRunRequest:
        fields = {
            "agent_run_id": str(uuid.uuid4()),
            "objective": "Say nothing.",
            "container": fixtures.boundary(),
        }
        fields.update(overrides)
        return agent.AgentRunRequest(**fields)

    def refusing(self):
        return mock.patch.object(
            agent,
            "_spawn",
            side_effect=agent.StartupRefusal(
                agent.uncorroborated(_launch.ABSENT), "init", *_startup.KNOWN_RUNTIME
            ),
        )

    def test_a_refusal_before_any_program_exists_is_raised_and_written_nowhere(self):
        with unlatched(), self.refusing():
            with self.assertRaises(agent.StartupRefusal):
                agent.agent_run(self.request(), self.Untouched())

    def test_a_run_whose_refusal_could_not_be_recorded_is_never_started(self):
        for description, overrides in (
            ("a Program that is not an identifier", {"program_id": "the-one-we-opened"}),
            ("a run that is not one", {"program_id": str(uuid.uuid4()), "agent_run_id": "run-1"}),
        ):
            with self.subTest(description):
                spawn = mock.patch.object(agent, "_spawn", side_effect=AssertionError("spawned"))
                with unlatched(), spawn:
                    with self.assertRaises(ValueError):
                        agent.agent_run(self.request(**overrides), self.Untouched())


if __name__ == "__main__":
    unittest.main()
