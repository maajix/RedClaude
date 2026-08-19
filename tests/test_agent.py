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

from redkraken import _launch, _startup, agent, document, isolation, packet, proxy
from redkraken import roster, skill, tls
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

#: The role a launch runs as when the subject is Skills. `fixtures.ROLE` holds
#: none and never will -- the orchestrator may not load instructions -- so a
#: Skill test cannot use it, and this is the role with the widest grant, which
#: is the longest list a check reading the whole list can read.
SKILLED = "web_hunter"

#: The served read the contained child is scripted to call. Any one of the six
#: would do; this is the one whose arguments are all optional, so the call the
#: model is told to make is a call the CLI's schema check cannot reject first.
READ = "mcp__rk2__get_attack_surface"

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
            role=fixtures.ROLE,
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


def matchers(*events) -> dict:
    """A stand-in for the hook registration, shaped the way `_gated` reads it."""
    return {
        event: [types.SimpleNamespace(matcher=None, hooks=[lambda *_: None])]
        for event in events
    }


def options(launch, cli_path: str, role: str = fixtures.ROLE, **overrides):
    """A stand-in for the SDK options value, contained on every field.

    `assess` reads the options value by duck typing, so this is the whole
    interface it uses. A namespace rather than the real class on purpose: the
    rules have to be exercisable on a machine with no SDK, which is the same
    machine that has to be able to prove the SDK's absence is a refusal.

    Every field the roster decides is read from the roster here too, so a test
    that wants a launch which disagrees with it has to say which field and by
    how much rather than inheriting the disagreement from a literal.

    The Skills are staged as a side effect, because for them the directory is
    part of the launch being described: `assess` asks whether every granted
    name is on disk, and a stand-in that named the grants without writing them
    would be a launch no child could have run.
    """
    compiled = roster.ROLES[role]
    agent.stage_skills(launch, role)
    fields = {
        "env": {},
        "skills": list(compiled.skills),
        "setting_sources": agent.setting_sources(compiled),
        "sandbox": None,
        "cwd": str(launch),
        "tools": compiled.visible_tools,
        "permission_mode": agent.PERMISSION_MODE,
        "allowed_tools": compiled.allowed_tools(agent.SERVED),
        "mcp_servers": {agent.SERVER: object()},
        "settings": str(launch / agent.SETTINGS),
        "cli_path": cli_path,
        "model": compiled.model,
        "effort": compiled.effort,
        "max_turns": compiled.max_turns,
        "hooks": matchers(*agent.GATE_EVENTS),
    }
    fields.update(overrides)
    return types.SimpleNamespace(**fields)


def job(launch_workspace, **overrides) -> dict:
    """One job document, as the supervisor writes it to the child's input."""
    fields = {
        "agent_run_id": "agent-run-1",
        "objective": "Say nothing.",
        "role": fixtures.ROLE,
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


def instruction(name: str) -> str:
    """One line of a skill's own text, long enough to be nobody else's.

    Derived rather than quoted: what it is used for is proving that the
    instructions reached the model, and a phrase copied into a test goes stale
    the first time somebody edits the skill. Out of the body and never the
    frontmatter, because a skill's description is in the system prompt of every
    session that was *offered* the skill -- a line from there would be carried
    by a run that loaded nothing. Lines carrying a quote or a backslash are
    skipped because the thing searched is a JSON document, where both are
    escaped and neither would match itself.
    """
    _, body = document.frontmatter(
        skill.SkillError, name, skill.INSTRUCTIONS,
        skill.SKILLS[name].source.decode("utf-8"),
    )
    lines = body.splitlines()
    return max((one for one in lines if '"' not in one and "\\" not in one), key=len)


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

    def assess(
        self, options_value, environment=None, runtime=None, managed=(), role=fixtures.ROLE
    ):
        return agent.assess(
            options_value,
            {} if environment is None else environment,
            self.runtime if runtime is None else runtime,
            launch_dir=self.launch,
            role=role,
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

    def test_a_role_with_no_served_tool_is_refused_before_a_model_is_started(self):
        # `reporter` runs no model at all, so there is nothing here for it to be
        # assessed as. `validator` was refused beside it until 037 served
        # `validate.judge`: a launch would have started a model at its own
        # effort with no verdict tool to reach, and the one thing it could have
        # produced is prose. The five roles that hold a served tool still
        # launch, which is what makes this a refusal of one row and one typo
        # rather than of the roster.
        for role in ("reporter", "no_such_role"):
            with self.subTest(role=role):
                violations = self.assess(options(self.launch, self.cli), role=role)

                self.assertEqual([agent.INVALID_LAUNCH], codes(violations))
                self.assertEqual(["launch:role"], sources(violations))

        for role in ("orchestrator", "recon", "web_hunter", "js_analyst", "validator"):
            with self.subTest(role=role):
                self.assertEqual(
                    (),
                    self.assess(options(self.launch, self.cli, role=role), role=role),
                )

    def test_each_widening_of_the_child_is_refused_by_the_field_that_widened_it(self):
        widenings = {
            "launch:env": {"env": {"ANTHROPIC_API_KEY": "late"}},
            "launch:setting_sources": {"setting_sources": ["user", "project"]},
            "launch:sandbox": {"sandbox": {"enabled": True}},
            "launch:cwd": {"cwd": str(fixtures.scratch())},
            "launch:builtin_tools": {"tools": ["Bash"]},
            # What the child may call. `bypassPermissions` is only contained
            # while the roster is the runtime's own tools, so a roster that
            # grew is refused by the same rule that lets the mode stand.
            "launch:permission_mode": {"permission_mode": "acceptEdits"},
            "launch:allowed_tools": {"allowed_tools": [*agent.SERVED, "Bash"]},
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
        served = agent.BARE[agent.SERVED[0]]

        self.assertFalse(surface.ready)
        with self.assertRaises(_launch.Closed):
            surface.serve(served)

        surface.open()
        surface.serve(served)

        self.assertTrue(surface.ready)
        self.assertEqual([served], surface.served)

        surface.open()

        self.assertFalse(surface.ready)
        with self.assertRaises(_launch.Closed):
            surface.serve(served)


@contextlib.contextmanager
def packaged():
    """The SDK's two constructors, recorded instead of imported.

    `claude_agent_sdk.tool` returns an `SdkMcpTool` carrying exactly the name,
    description, input schema and handler it was given, and
    `create_sdk_mcp_server` collects those into one server value. Standing in
    for both is what lets the handlers be exercised on a checkout with no SDK --
    and what the handlers do is this application's code, not the pair's: refuse
    while the surface is closed, rename the one wire argument that is a Python
    builtin, and answer from the packet.

    The launch itself is still measured against the real SDK. This substitutes
    two decorators, not the runtime pair, and every rule in `assess` is
    untouched by it.
    """
    served: dict[str, types.SimpleNamespace] = {}

    def stand_in(name: str, description: str, schema: dict):
        def decorator(handler):
            served[name] = types.SimpleNamespace(
                name=name, description=description, input_schema=schema, handler=handler
            )
            return served[name]

        return decorator

    def collect(*, name, version, tools):
        return types.SimpleNamespace(name=name, version=version, tools=tools)

    with (
        mock.patch.object(_launch, "tool", stand_in, create=True),
        mock.patch.object(_launch, "create_sdk_mcp_server", collect, create=True),
    ):
        yield served


class MissionTest(unittest.TestCase):
    """One Mission result per run, and the count that makes a second visible."""

    def test_the_first_submission_is_accepted_and_kept_as_it_arrived(self):
        mission = _launch.Submission()

        answer = mission.submit({"completion_claim": {"status": "partial"}})

        self.assertTrue(answer["accepted"])
        self.assertEqual(1, answer["attempts"])
        self.assertEqual({"completion_claim": {"status": "partial"}}, mission.result)

    def test_a_second_submission_is_refused_rather_than_merged_or_overwritten(self):
        # A later contradiction is the run arguing with its own output. The
        # first is what it proposed.
        mission = _launch.Submission()
        mission.submit({"observations": ["first"]})

        answer = mission.submit({"observations": ["second"]})

        self.assertFalse(answer["accepted"])
        self.assertEqual("already_submitted", answer["reason"])
        self.assertEqual(2, answer["attempts"])
        self.assertEqual({"observations": ["first"]}, mission.result)

    def test_the_answer_does_not_tell_the_model_anything_was_staged(self):
        # Nothing is staged yet: the row is written by the runtime after this
        # process ends and after provenance is checked. A handler saying
        # otherwise would be promising something it is not the one to do.
        answer = _launch.Submission().submit({})

        self.assertNotIn("staged", json.dumps(answer).replace("staging", ""))

    def test_a_run_that_submitted_nothing_has_nothing_to_carry_back(self):
        mission = _launch.Submission()

        self.assertFalse(mission.submitted)
        self.assertIsNone(mission.result)
        self.assertEqual(0, mission.attempts)

    def test_the_tries_cross_back_beside_the_result_rather_than_only_the_result(self):
        # One result and two attempts is a model that argued with its own
        # output and was refused. That is a fact about the run, so it travels
        # with the run rather than staying in the transcript.
        mission = _launch.Submission()
        mission.submit({"observations": []})
        mission.submit({"observations": []})

        carried = agent.AgentRunResult(
            agent_run_id="ar",
            role=fixtures.ROLE,
            sdk_version=None,
            cli_version=None,
            api_key_source=agent.EXPECTED_KEY_SOURCE,
            tool_ready=1,
            tools_served=(),
            denials=(),
            answers=1,
            stop_reason="end_turn",
            text="",
            mission_result=mission.result,
            mission_attempts=mission.attempts,
        ).as_dict()

        self.assertEqual({"observations": []}, carried["mission_result"])
        self.assertEqual(2, carried["mission_attempts"])


class JudgementTest(unittest.TestCase):
    """The one packet a validator may read, and the one answer it latches.

    Criterion 4: the whole output of a validation session is a word and a list
    of assertion identifiers, and it is produced once. The database decides what
    the Finding becomes -- these are the properties of the thing handed to it.
    """

    PACKET = {
        "finding": {"label": "F1", "status": "validating", "severity": "high"},
        "test": {"assertions": [{"id": "the-variant-is-served", "kind": "status_equals"}]},
    }

    def judgement(self, packet_document=None) -> _launch.Judgement:
        return _launch.Judgement(
            self.PACKET if packet_document is None else packet_document
        )

    def test_the_packet_is_served_back_exactly_as_the_job_carried_it(self):
        # Unchanged is the property. `rk2_validation_packet` selected these
        # fields through a column allowlist a migration states, and a handler
        # that summarised, reordered or annotated them would be a second
        # selection nothing checked.
        judged = self.judgement()

        answer = judged.read({"finding_label": "F1"})

        self.assertTrue(answer["served"])
        self.assertEqual("F1", answer["finding"])
        self.assertEqual(self.PACKET, answer["packet"])
        self.assertEqual(1, judged.reads)

    def test_a_session_given_no_packet_serves_nothing_rather_than_an_empty_one(self):
        # A run that was started to judge nothing is every run but a validator's.
        # An empty document served as a document would be a model asked to judge
        # a Finding out of no evidence at all.
        judged = _launch.Judgement()

        self.assertIsNone(judged.finding)
        self.assertEqual({"served": False, "reason": "no_packet"}, judged.read({}))

    def test_a_finding_this_session_was_not_given_is_refused_with_the_one_it_was(self):
        # Named rather than silent, so a model that misread its own packet can
        # correct itself while it is still running.
        judged = self.judgement()

        answer = judged.read({"finding_label": "F9"})

        self.assertFalse(answer["served"])
        self.assertEqual("other_finding", answer["reason"])
        self.assertEqual("F1", answer["finding"])
        self.assertNotIn("packet", answer)

    def test_the_answer_is_a_verdict_and_the_assertions_it_says_did_not_hold(self):
        judged = self.judgement()

        answer = judged.judge(
            {
                "finding_label": "F1",
                "verdict": "refuted",
                "failed_assertion_ids": ["the-variant-is-served"],
            }
        )

        self.assertTrue(answer["accepted"])
        self.assertEqual(1, answer["attempts"])
        self.assertEqual(
            {
                "finding_label": "F1",
                "verdict": "refuted",
                "failed_assertion_ids": ["the-variant-is-served"],
            },
            judged.answer,
        )

    def test_a_second_verdict_is_refused_rather_than_replacing_the_first(self):
        # The distinction `Choice` is on the other side of. A session that
        # answers `insufficient` and then `confirmed` about a document that did
        # not change in between is a session reasoning from having already
        # answered, which is exactly what the blindness exists to keep out.
        judged = self.judgement()
        judged.judge({"finding_label": "F1", "verdict": "insufficient"})

        answer = judged.judge({"finding_label": "F1", "verdict": "confirmed"})

        self.assertFalse(answer["accepted"])
        self.assertEqual("already_judged", answer["reason"])
        self.assertEqual(2, answer["attempts"])
        self.assertEqual("insufficient", judged.answer["verdict"])

    def test_a_verdict_about_another_finding_latches_nothing_and_leaves_the_turn_open(self):
        # Refused and not counted as the answer: the session still has its one
        # answer to give, which is what makes naming the right label useful.
        judged = self.judgement()

        answer = judged.judge({"finding_label": "F9", "verdict": "confirmed"})

        self.assertFalse(answer["accepted"])
        self.assertEqual("other_finding", answer["reason"])
        self.assertEqual("F1", answer["finding"])
        self.assertIsNone(judged.answer)

        self.assertTrue(judged.judge({"finding_label": "F1", "verdict": "confirmed"})["accepted"])

    def test_an_answer_with_no_failed_assertions_carries_an_empty_list_and_not_nothing(self):
        # `record_verdict` takes a `text[]`, and a confirmed verdict naming
        # nothing is the ordinary case. Absent and empty would be two spellings
        # of it for the runtime to tell apart.
        judged = self.judgement()

        judged.judge({"finding_label": "F1", "verdict": "confirmed"})

        self.assertEqual([], judged.answer["failed_assertion_ids"])

    def test_the_answer_does_not_tell_the_model_the_finding_became_anything(self):
        # `MissionTest`'s property for the other latch. The row and the
        # Finding's status are one transaction the runtime opens after this
        # process ends, and it rebuilds the packet first: an answer accepted
        # here may still be filed as stale there.
        judged = self.judgement()

        answer = judged.judge({"finding_label": "F1", "verdict": "confirmed"})

        self.assertNotIn("validated", json.dumps(answer))
        self.assertNotIn("recorded", json.dumps(answer))

    def test_a_run_that_judged_nothing_has_nothing_to_carry_back(self):
        judged = self.judgement()

        self.assertIsNone(judged.answer)
        self.assertEqual(0, judged.attempts)

    def test_the_tries_cross_back_beside_the_verdict_rather_than_only_the_verdict(self):
        judged = self.judgement()
        judged.judge({"finding_label": "F1", "verdict": "confirmed"})
        judged.judge({"finding_label": "F1", "verdict": "refuted"})

        carried = agent.AgentRunResult(
            agent_run_id="ar",
            role=fixtures.ROLE,
            sdk_version=None,
            cli_version=None,
            api_key_source=agent.EXPECTED_KEY_SOURCE,
            tool_ready=1,
            tools_served=(),
            denials=(),
            answers=1,
            stop_reason="end_turn",
            text="",
            verdict=judged.answer,
            verdict_attempts=judged.attempts,
        ).as_dict()

        self.assertEqual("confirmed", carried["verdict"]["verdict"])
        self.assertEqual(2, carried["verdict_attempts"])

    def test_a_packet_whose_finding_has_no_label_is_a_packet_nobody_can_judge(self):
        # The label is what both handlers check against, so a document that
        # carries none is one where every call would be `other_finding`. It is
        # answered as no packet at all rather than as a packet with a hole.
        for shape in ({}, {"finding": "F1"}, {"finding": {}}, {"finding": {"label": ""}}):
            with self.subTest(packet=shape):
                judged = self.judgement(shape)

                self.assertIsNone(judged.finding)
                self.assertEqual("no_packet", judged.read({"finding_label": "F1"})["reason"])

    def test_the_job_field_is_read_as_nothing_where_it_is_not_a_document(self):
        # A malformed field leaves a session with no packet rather than raising:
        # the runtime reads that back as a validation nobody answered, where a
        # raise would be a run that never started over a field most runs do not
        # carry at all.
        for stated in (None, "F1", ["finding"], 7):
            with self.subTest(judgement=stated):
                self.assertIsNone(_launch._judged(stated))

        self.assertEqual({"finding": {}}, _launch._judged({"finding": {}}))


class ServedToolTest(unittest.TestCase):
    """What the child offers the model, and what each handler does with a call."""

    def served(self, stack, reader=None, mission=None, door=None, judgement=None):
        surface = _launch.Surface()
        offered = stack.enter_context(packaged())
        _launch.server(
            surface,
            reader or packet.Reader(packet.Packet()),
            mission or _launch.Submission(),
            door,
            judgement=judgement,
        )
        return surface, offered

    def test_the_offered_tools_are_exactly_the_ones_the_roster_serves(self):
        with contextlib.ExitStack() as stack:
            _, offered = self.served(stack)

        self.assertEqual(sorted(agent.BARE.values()), sorted(offered))

    def test_the_contracts_no_launch_serves_are_the_five_the_runtime_answers_for(self):
        """The declared surface is wider than the served one, and by how much.

        Four of these are a decision rather than a gap: the runtime asks for a
        validation, files a report, parks a Tool run for a human and runs an
        offline tool, each on its own connection, so the model-facing contract
        is a name the roster keeps for the risk rules and the allowlists rather
        than a handler anybody built. `run_skill_script` is the one nothing
        answers -- a Skill's scripts run under `skill.check` in CI and nowhere
        during a run -- and ticket 87 owes it. Pinned as a list because a sixth
        entry appearing here is a tool some role holds and no child can call.
        """
        self.assertEqual(
            [
                "mcp__rk2__park_for_human",
                "mcp__rk2__request_report",
                "mcp__rk2__request_validation",
                "mcp__rk2__run_skill_script",
                "mcp__rk2__run_tool",
            ],
            sorted(set(roster.CONTRACTS) - set(agent.SERVED)),
        )

    def test_every_tool_is_offered_with_its_roster_schema_and_one_description(self):
        # The schema is the pair's promise and the gate is ours, so the served
        # document has to be the roster's own -- a second copy here would be a
        # second contract, and the gate would be checking the other one.
        with contextlib.ExitStack() as stack:
            _, offered = self.served(stack)

        for name, packaged_tool in offered.items():
            with self.subTest(tool=name):
                contract = roster.CONTRACTS[f"mcp__{agent.SERVER}__{name}"]
                self.assertEqual(contract.schema(), packaged_tool.input_schema)
                self.assertFalse(packaged_tool.input_schema["additionalProperties"])
                self.assertTrue(packaged_tool.description.strip())

    def answer(self, packaged_tool, arguments: dict) -> dict:
        wire = asyncio.run(packaged_tool.handler(arguments))
        self.assertEqual("text", wire["content"][0]["type"])
        return json.loads(wire["content"][0]["text"])

    def test_no_tool_answers_before_the_surface_has_opened(self):
        # A state read answered before init would be a read served by a child
        # whose authentication this runtime had not corroborated.
        with contextlib.ExitStack() as stack:
            _, offered = self.served(stack)

            for name, packaged_tool in offered.items():
                with self.subTest(tool=name):
                    with self.assertRaises(_launch.Closed):
                        asyncio.run(packaged_tool.handler({}))

    def test_a_read_is_answered_from_the_packet_the_run_was_started_with(self):
        document = packet.Packet(
            revision=5,
            sections={
                "surface": packet.Section(
                    name="surface",
                    total=3,
                    rows=(
                        packet.Row(
                            section="surface",
                            label="EP1",
                            revision=5,
                            digest="0" * 64,
                            record={"kind": "entity", "label": "EP1", "type": "endpoint"},
                        ),
                    ),
                )
            },
        )
        with contextlib.ExitStack() as stack:
            surface, offered = self.served(stack, reader=packet.Reader(document))
            surface.open()

            answer = self.answer(offered["get_attack_surface"], {})

        self.assertEqual(5, answer["revision"])
        self.assertEqual(["EP1"], [row["label"] for row in answer["records"]])
        self.assertEqual([{"reason": "packet_bound", "count": 2}], answer["omitted"])

    def test_the_wire_name_that_is_a_python_builtin_is_renamed_on_the_way_in(self):
        document = packet.Packet(
            sections={
                "artifacts": packet.Section(
                    name="artifacts",
                    total=1,
                    rows=(
                        packet.Row(
                            section="artifacts",
                            label="AF1",
                            revision=0,
                            digest="a" * 64,
                            record={
                                "kind": "artifact",
                                "label": "AF1",
                                "sha256": "a" * 64,
                                "byte_size": 11,
                            },
                        ),
                    ),
                )
            },
            excerpts={"AF1": "hello world"},
        )
        with contextlib.ExitStack() as stack:
            surface, offered = self.served(stack, reader=packet.Reader(document))
            surface.open()

            answer = self.answer(
                offered["get_artifact"], {"artifact_label": "AF1", "range": "0-5"}
            )

        self.assertEqual("hello", answer["records"][0]["content"])
        self.assertIn("range", _launch._schema("get_artifact")["properties"])

    def test_a_mission_result_is_accumulated_in_the_child_and_written_by_nobody_here(self):
        mission = _launch.Submission()
        with contextlib.ExitStack() as stack:
            surface, offered = self.served(stack, mission=mission)
            surface.open()

            answer = self.answer(
                offered["submit_mission_result"], {"observations": [{"summary": "seen"}]}
            )

        self.assertTrue(answer["accepted"])
        self.assertEqual({"observations": [{"summary": "seen"}]}, mission.result)

    def test_a_validation_packet_is_served_from_the_job_and_from_no_other_read(self):
        # Criterion 3 seen from the child: the document is held, not fetched.
        # There is no database on this side of the boundary and no second call
        # that could reach one, so what the session may consider is what
        # `open_validation_session` recorded the digest of.
        judgement = _launch.Judgement({"finding": {"label": "F1"}, "test": {"actions": []}})
        with contextlib.ExitStack() as stack:
            surface, offered = self.served(stack, judgement=judgement)
            surface.open()

            answer = self.answer(offered["get_validation_packet"], {"finding_label": "F1"})

        self.assertTrue(answer["served"])
        self.assertEqual({"finding": {"label": "F1"}, "test": {"actions": []}}, answer["packet"])

    def test_a_verdict_is_latched_in_the_child_and_decided_by_nobody_here(self):
        judgement = _launch.Judgement({"finding": {"label": "F1"}})
        with contextlib.ExitStack() as stack:
            surface, offered = self.served(stack, judgement=judgement)
            surface.open()

            answer = self.answer(
                offered["submit_verdict"],
                {
                    "finding_label": "F1",
                    "verdict": "confirmed",
                    "failed_assertion_ids": [],
                },
            )
            refused = self.answer(
                offered["submit_verdict"], {"finding_label": "F1", "verdict": "refuted"}
            )

        self.assertTrue(answer["accepted"])
        self.assertEqual("already_judged", refused["reason"])
        self.assertEqual("confirmed", judgement.answer["verdict"])

    def test_a_run_that_was_given_no_finding_still_serves_both_tools_and_judges_none(self):
        # The allowlist is the role's and not the job's -- `net.request`'s
        # reason -- so the tools exist for every run and answer honestly on the
        # ones that were started to judge nothing.
        with contextlib.ExitStack() as stack:
            surface, offered = self.served(stack)
            surface.open()

            served = self.answer(offered["get_validation_packet"], {"finding_label": "F1"})
            judged = self.answer(
                offered["submit_verdict"], {"finding_label": "F1", "verdict": "confirmed"}
            )

        self.assertEqual("no_packet", served["reason"])
        self.assertEqual("other_finding", judged["reason"])

    def test_every_call_that_was_answered_is_on_the_surfaces_record(self):
        with contextlib.ExitStack() as stack:
            surface, offered = self.served(stack)
            surface.open()

            self.answer(offered["get_hypotheses"], {})
            self.answer(offered["get_receipts"], {"receipt_labels": ["R1"]})

        self.assertEqual(["get_hypotheses", "get_receipts"], surface.served)


class RequestToolTest(unittest.TestCase):
    """The one call that leaves the boundary, and every way it does not.

    The handler decides nothing about whether a request is allowed -- the
    capability was minted against a Tool run before this process started and
    the door re-decides the request that arrives. What it does decide is how a
    refusal is reported, and the whole of this class is that: a run with no
    capability, a target that will not canonicalise, a door that does not
    answer and a door that answers no are four different facts, and a handler
    that flattened them would leave a model guessing which one it hit.
    """

    door = agent.Egress(
        capability="c0ffee" * 10 + "cafe",
        program_id="11111111-1111-4111-8111-111111111111",
        proxy_url="http://rk2-proxy:18080",
        certificate="/run/redkraken-ca.pem",
    )

    def served(self, stack, door=None):
        surface = _launch.Surface()
        offered = stack.enter_context(packaged())
        _launch.server(
            surface, packet.Reader(packet.Packet()), _launch.Submission(), door
        )
        surface.open()
        return offered["http_request"]

    def answer(self, packaged_tool, arguments: dict) -> dict:
        wire = asyncio.run(packaged_tool.handler(arguments))
        return json.loads(wire["content"][0]["text"])

    @contextlib.contextmanager
    def spending(self, answer=None, error: Exception | None = None):
        """`proxy.spend` recorded rather than performed."""
        calls: list[tuple[tuple, dict]] = []

        def stand_in(*positional, **keyword):
            calls.append((positional, keyword))
            if error is not None:
                raise error
            return answer or proxy.Answer(
                status=200, body=b"hello", receipt="RC1", decision=None, detail=None
            )

        with mock.patch.object(_launch.proxy, "spend", stand_in):
            yield calls

    def test_a_run_with_no_capability_says_so_and_sends_nothing(self):
        with contextlib.ExitStack() as stack:
            handler = self.served(stack, door=None)
            with self.spending() as calls:
                answer = self.answer(handler, {"method": "GET", "url": "https://x.test/"})

        self.assertFalse(answer["served"])
        self.assertEqual(_launch.NO_CAPABILITY, answer["reason"])
        self.assertEqual([], calls)

    def test_the_capability_is_spent_on_the_door_the_job_named(self):
        with contextlib.ExitStack() as stack:
            handler = self.served(stack, door=self.door)
            with self.spending() as calls:
                answer = self.answer(handler, {"method": "GET", "url": "http://x.test/a"})

        (listener, url), keyword = calls[0]
        self.assertEqual(("rk2-proxy", 18080), listener)
        self.assertEqual("http://x.test/a", url)
        self.assertEqual(self.door.capability, keyword["capability"])
        self.assertEqual(self.door.program_id, keyword["program_id"])
        self.assertEqual("GET", keyword["method"])
        self.assertTrue(answer["served"])
        self.assertEqual(200, answer["status"])
        self.assertEqual("RC1", answer["receipt"])
        self.assertEqual("hello", answer["body"])

    def test_the_headers_the_call_named_are_what_the_capability_is_spent_with(self):
        # `headers` is declared on the contract, so it reaches the wire: a
        # declared argument the runtime drops is a promise the schema cannot
        # keep. A call that names none sends none, which is the shape every
        # request had before this one was threaded through.
        with contextlib.ExitStack() as stack:
            handler = self.served(stack, door=self.door)
            with self.spending() as calls:
                self.answer(
                    handler,
                    {
                        "method": "GET",
                        "url": "http://x.test/a",
                        "headers": {"X-Trace": "abc"},
                    },
                )
                self.answer(handler, {"method": "GET", "url": "http://x.test/a"})

        self.assertEqual({"X-Trace": "abc"}, calls[0][1]["headers"])
        self.assertEqual({}, calls[1][1]["headers"])

    def test_a_header_no_client_will_put_on_a_wire_is_reported_as_a_refusal(self):
        # What `http.client` raises for a value with a line break in it. The
        # gate refuses those first, so arriving here means the request cannot
        # be sent at all -- and the difference between that and a door that did
        # not answer is a difference the model is told rather than a traceback
        # inside a handler that reports nothing.
        with contextlib.ExitStack() as stack:
            handler = self.served(stack, door=self.door)
            with self.spending(error=ValueError("Invalid header value b'a\\r\\nb'")):
                answer = self.answer(
                    handler,
                    {"method": "GET", "url": "http://x.test/a", "headers": {"X-T": "a\r\nb"}},
                )

        self.assertFalse(answer["served"])
        self.assertEqual(_launch.UNUSABLE_TARGET, answer["reason"])
        self.assertIn("Invalid header value", answer["detail"])

    def test_a_plain_target_needs_no_trust_and_a_tls_one_loads_it(self):
        loaded: list[Path] = []

        def stand_in(certificate):
            loaded.append(Path(certificate))
            return "an ssl context"

        with contextlib.ExitStack() as stack:
            handler = self.served(stack, door=self.door)
            stack.enter_context(mock.patch.object(_launch.tls, "trust", stand_in))
            with self.spending() as calls:
                self.answer(handler, {"method": "GET", "url": "http://x.test/"})
                self.answer(handler, {"method": "GET", "url": "https://x.test/"})

        self.assertIsNone(calls[0][1]["trust"])
        self.assertEqual("an ssl context", calls[1][1]["trust"])
        self.assertEqual([Path(self.door.certificate)], loaded)

    def test_a_body_larger_than_the_excerpt_is_cut_and_says_it_was(self):
        long = b"a" * (packet.DEFAULT_EXCERPT + 100)
        with contextlib.ExitStack() as stack:
            handler = self.served(stack, door=self.door)
            with self.spending(
                answer=proxy.Answer(200, long, "RC1", None, None)
            ):
                answer = self.answer(handler, {"method": "GET", "url": "http://x.test/"})

        self.assertEqual(packet.DEFAULT_EXCERPT, len(answer["body"]))
        self.assertEqual(len(long), answer["byte_size"])
        self.assertTrue(answer["truncated"])

    def test_bytes_that_are_not_text_are_replaced_rather_than_raised(self):
        with contextlib.ExitStack() as stack:
            handler = self.served(stack, door=self.door)
            with self.spending(answer=proxy.Answer(200, b"\xff\xfe", "RC1", None, None)):
                answer = self.answer(handler, {"method": "GET", "url": "http://x.test/"})

        self.assertEqual("��", answer["body"])

    def test_a_door_that_refused_reports_the_refusal_rather_than_a_failure(self):
        # 407 with a decision is this fence saying no. The request did not
        # happen, the Receipt proves it did not, and a handler reporting it as
        # an unreachable target would have the model retry a policy decision.
        with contextlib.ExitStack() as stack:
            handler = self.served(stack, door=self.door)
            with self.spending(
                answer=proxy.Answer(407, b"", "RC2", "out_of_scope", "not in policy")
            ):
                answer = self.answer(handler, {"method": "GET", "url": "http://x.test/"})

        self.assertFalse(answer["served"])
        self.assertEqual("out_of_scope", answer["decision"])
        self.assertEqual("RC2", answer["receipt"])
        self.assertNotIn("reason", answer)

    def test_a_target_that_will_not_canonicalise_never_reaches_the_door(self):
        with contextlib.ExitStack() as stack:
            handler = self.served(stack, door=self.door)
            with self.spending() as calls:
                answer = self.answer(handler, {"method": "GET", "url": "gopher://x.test/"})

        self.assertFalse(answer["served"])
        self.assertEqual(_launch.UNUSABLE_TARGET, answer["reason"])
        self.assertEqual([], calls)

    def test_a_door_address_that_is_not_an_address_is_the_same_answer(self):
        broken = agent.Egress(
            capability=self.door.capability,
            program_id=self.door.program_id,
            proxy_url="https://rk2-proxy:18080",
        )
        with contextlib.ExitStack() as stack:
            handler = self.served(stack, door=broken)
            with self.spending() as calls:
                answer = self.answer(handler, {"method": "GET", "url": "http://x.test/"})

        self.assertEqual(_launch.UNUSABLE_TARGET, answer["reason"])
        self.assertEqual([], calls)

    def test_a_certificate_that_cannot_be_read_is_not_a_traceback(self):
        with contextlib.ExitStack() as stack:
            handler = self.served(stack, door=self.door)
            stack.enter_context(
                mock.patch.object(_launch.tls, "trust", side_effect=OSError("no such file"))
            )
            with self.spending() as calls:
                answer = self.answer(handler, {"method": "GET", "url": "https://x.test/"})

        self.assertEqual(_launch.UNUSABLE_TARGET, answer["reason"])
        self.assertEqual([], calls)

    def test_a_door_that_does_not_answer_is_reported_as_the_door(self):
        with contextlib.ExitStack() as stack:
            handler = self.served(stack, door=self.door)
            with self.spending(error=OSError("connection refused")):
                answer = self.answer(handler, {"method": "GET", "url": "http://x.test/"})

        self.assertFalse(answer["served"])
        self.assertEqual(_launch.DOOR_UNREACHABLE, answer["reason"])
        self.assertIn("connection refused", answer["detail"])

    def test_the_call_is_on_the_surfaces_record_however_it_ended(self):
        with contextlib.ExitStack() as stack:
            surface = _launch.Surface()
            offered = stack.enter_context(packaged())
            _launch.server(surface, packet.Reader(packet.Packet()), _launch.Submission())
            surface.open()

            self.answer(offered["http_request"], {"method": "GET", "url": "http://x.test/"})

        self.assertEqual(["http_request"], surface.served)


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

    def test_the_gate_the_child_builds_refuses_at_the_cap_the_job_carried(self):
        # PH2-73. The number is `scheduler_weights.max_concurrent_subagents`,
        # and it arrives on the job because this process cannot ask for it: the
        # container's one network reaches the capability proxy and no database.
        capped = job(fixtures.scratch(), subagent_cap=5)
        gate = _launch._gate(fixtures.ROLE, capped.get("subagent_cap"))

        self.assertEqual(5, gate.subagent_cap)

    def test_a_job_that_carries_no_cap_gets_the_rosters_default(self):
        # A job written before the number travelled, not a value this process
        # prefers to the one the claim read.
        self.assertEqual(roster.DEFAULT_SUBAGENTS, _launch._subagent_cap(None))

    def test_a_cap_the_roster_refuses_leaves_the_child_with_no_gate(self):
        # The same answer an unknown role gets, and for the same reason: no
        # gate is no options value, and a launch that cannot be described is
        # one `assess` refuses field by field rather than one that crashes.
        # A cap that is not a number at all is the same refusal: this process
        # cannot read what the claim sent, and guessing would be the second
        # statement of the number this ticket exists to have one of.
        for stated in (0, -1, "three", object()):
            with self.subTest(subagent_cap=stated):
                self.assertIsNone(_launch._gate(fixtures.ROLE, stated))

    def test_a_job_that_carries_no_ceiling_leaves_the_run_unbounded(self):
        # PH2-25. Nothing stated is no ceiling, not a default: a Program with no
        # total and no per-run number reserved nothing, and inventing a bound
        # here would stop a run the scheduler admitted without one.
        self.assertIsNone(_launch._token_cap(None))
        self.assertEqual(60000, _launch._token_cap(60000))

    def test_a_ceiling_this_process_cannot_read_fails_the_run(self):
        # Unlike the subagent cap, which degrades to the roster's default: a cap
        # that cannot be read can still be refused, but a ceiling that cannot be
        # read can only be ignored, and ignoring it is running unbounded.
        for stated in ("sixty thousand", object(), [60000]):
            with self.subTest(token_cap=stated):
                with self.assertRaises((TypeError, ValueError)):
                    _launch._token_cap(stated)

    def test_every_read_the_model_was_charged_for_counts_as_input(self):
        # A cached read is cheaper, not free. A ceiling that ignored the cache
        # is one a long session walks straight through.
        self.assertEqual(
            (600, 20),
            _launch._usage(
                {
                    "input_tokens": 100,
                    "cache_read_input_tokens": 300,
                    "cache_creation_input_tokens": 200,
                    "output_tokens": 20,
                }
            ),
        )

    def test_a_message_that_reports_no_usage_spends_nothing(self):
        # A message with no usage block still happened, and so does a block with
        # fields missing from it.
        self.assertEqual((0, 0), _launch._usage(None))
        self.assertEqual((0, 0), _launch._usage({}))
        self.assertEqual((7, 0), _launch._usage({"input_tokens": 7}))

    def test_usage_this_process_cannot_read_is_not_quietly_zero(self):
        # The same reason `_token_cap` raises: a quiet zero here is a running
        # sum that never grows, which is the ceiling silently switched off.
        for stated in ("40 tokens", 4200, [{"input_tokens": 1}]):
            with self.subTest(usage=stated):
                with self.assertRaises(TypeError):
                    _launch._usage(stated)

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

    def built(self, role: str = fixtures.ROLE):
        launch = agent.launch_directory(fixtures.scratch(), "agent-run-1")
        agent.write_settings(launch)
        # The same three steps `_launch.run` takes before it asserts, in the
        # same order: a launch whose Skills are not on disk is one the
        # assertion refuses, so a fixture that skipped this would be testing a
        # directory no child ever runs in.
        agent.stage_skills(launch, role)
        runtime = _launch.runtime_facts()
        value = _launch.options_for(
            job(launch.parent, role=role),
            runtime,
            _launch.server(_launch.Surface(), packet.Reader(packet.Packet()), _launch.Submission()),
            launch,
            roster.Gate(role),
        )
        return value, runtime, launch

    def test_the_one_options_value_is_the_one_that_was_assessed(self):
        value, runtime, launch = self.built()

        self.assertEqual((), agent.assess(value, {}, runtime, launch_dir=launch,
                                          role=fixtures.ROLE, managed_settings=()))
        self.assertEqual(str(agent.bundled_executable(runtime)), value.cli_path)
        self.assertEqual(
            sorted(roster.ROLES[fixtures.ROLE].tools.intersection(agent.SERVED)),
            value.allowed_tools,
        )

    def test_every_field_the_roster_decides_is_read_from_the_roster(self):
        # The point is not that these are good numbers. It is that there is one
        # place they come from: a launch whose turn ceiling or model came from
        # the job document would be a second roster, and the assertion checking
        # them against the first would be checking a copy against itself.
        for name, role in roster.ROLES.items():
            if role.rendered:
                continue
            with self.subTest(role=name):
                value, _, _ = self.built(name)
                self.assertEqual(role.model, value.model)
                self.assertEqual(role.effort, value.effort)
                self.assertEqual(role.max_turns, value.max_turns)
                self.assertEqual(sorted(role.builtin_tools), value.tools)
                self.assertEqual(
                    sorted(role.tools.intersection(agent.SERVED)), value.allowed_tools
                )
                # The grants, and what it takes to read them. A role that loads
                # no Skill opens no settings location at all, which is what
                # every launch here opened before there were Skills.
                self.assertEqual(list(role.skills), value.skills)
                self.assertEqual(
                    ["project"] if role.skills else [], value.setting_sources
                )

    def test_the_gate_is_registered_on_every_event_it_needs(self):
        value, _, _ = self.built()

        self.assertEqual(set(agent.GATE_EVENTS), set(value.hooks))
        for event, registered in value.hooks.items():
            with self.subTest(event=event):
                # No matcher narrows by tool name. A matcher is a filter on
                # which calls reach the gate, and a gate some calls do not
                # reach is a gate with a hole shaped like a tool name.
                self.assertEqual([None], [matcher.matcher for matcher in registered])
                self.assertTrue(all(matcher.hooks for matcher in registered))

    def test_every_granted_skill_is_on_disk_where_the_cli_will_look_for_it(self):
        for name, role in roster.ROLES.items():
            if role.rendered or not role.skills:
                continue
            with self.subTest(role=name):
                _, _, launch = self.built(name)
                for granted in role.skills:
                    staged = launch / skill.STAGED / granted / skill.INSTRUCTIONS
                    self.assertEqual(skill.SKILLS[granted].source, staged.read_bytes())

    def test_a_grant_with_no_instructions_behind_it_is_refused_rather_than_started(self):
        """A name the gate would admit and the CLI could not answer.

        This is the failure the staging step exists to prevent, so it is
        provoked by undoing exactly that step and nothing else: the roster
        still grants the skill, the options value still names it, and the file
        the CLI reads is gone.
        """
        value, runtime, launch = self.built(SKILLED)
        granted = roster.ROLES[SKILLED].skills[0]
        (launch / skill.STAGED / granted / skill.INSTRUCTIONS).unlink()

        self.assertIn(
            "launch:skills_staged",
            sources(agent.assess(value, {}, runtime, launch_dir=launch,
                                 role=SKILLED, managed_settings=())),
        )

    def test_a_launch_naming_a_skill_its_role_was_not_granted_is_refused(self):
        value, runtime, launch = self.built(SKILLED)
        ungranted = sorted(set(skill.SKILLS) - set(roster.ROLES[SKILLED].skills))
        value.skills = sorted([*roster.ROLES[SKILLED].skills, ungranted[0]])

        self.assertIn(
            "launch:skills",
            sources(agent.assess(value, {}, runtime, launch_dir=launch,
                                 role=SKILLED, managed_settings=())),
        )

    def test_a_launch_that_would_read_the_operators_own_settings_is_refused(self):
        """`project` is the runtime's own directory. `user` is somebody's home.

        The widening a Skill grant needs is one location and it is the launch
        directory, so both of the SDK's own defaults are refused here: the pair
        it substitutes when nothing is set, and the source that is not this
        runtime's whichever role asks for it.
        """
        for opened in (["user", "project"], ["user"], ["local"], None):
            for role in (fixtures.ROLE, SKILLED):
                with self.subTest(setting_sources=opened, role=role):
                    value, runtime, launch = self.built(role)
                    value.setting_sources = opened

                    self.assertIn(
                        "launch:setting_sources",
                        sources(agent.assess(value, {}, runtime, launch_dir=launch,
                                             role=role, managed_settings=())),
                    )

    def test_a_launch_without_the_gate_is_refused_rather_than_started(self):
        value, runtime, launch = self.built()
        for hooks in ({}, None, matchers("PreToolUse")):
            with self.subTest(hooks=hooks):
                value.hooks = hooks
                self.assertIn(
                    "launch:hooks",
                    sources(agent.assess(value, {}, runtime, launch_dir=launch,
                                         role=fixtures.ROLE, managed_settings=())),
                )


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
            cls._serve(cls.upstream, cls.network, READ)
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
    def _serve(
        cls,
        name: str,
        network: str,
        tool: str,
        arguments: dict | None = None,
        marker: str = "",
    ) -> None:
        """Start the model API as a peer, and wait for it to be one.

        Parameterised by what the scripted model asks for, because a run whose
        subject is a *denial* needs the model to ask for the thing that is
        denied, and a run whose subject is the tool surface needs it to ask for
        the tool. One peer per script: the boundary verifies that the proxy it
        was pointed at is the one other container on the network, so a second
        script is a second network rather than a second container.
        """
        docker(
            "run",
            "--detach",
            "--rm",
            "--pull",
            "never",
            "--name",
            name,
            "--network",
            network,
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
            tool,
            AUTHORITY,
            str(UPSTREAM_PORT),
            *((json.dumps(arguments),) if arguments is not None else ()),
            *((marker,) if marker else ()),
        )
        deadline = time.monotonic() + UPSTREAM_READY
        while time.monotonic() < deadline:
            if control_upstream.LISTENING in docker("logs", name, check=False).stdout:
                return
            time.sleep(0.2)
        raise AssertionError(docker("logs", name, check=False).stderr)

    @contextlib.contextmanager
    def scripted(self, tool: str, arguments: dict, marker: str = ""):
        """A boundary of this test's own, whose model asks for one named call.

        Yields the boundary and the peer behind it. Both, because what some of
        these runs assert is what arrived at the far end, and the far end is a
        container: reading it back means holding its name.
        """
        suffix = uuid.uuid4().hex[:12]
        network, upstream = f"rk2-canary-{suffix}", f"rk2-canary-upstream-{suffix}"
        docker("network", "create", "--internal", network)
        try:
            self._serve(upstream, network, tool, arguments, marker)
            yield self.boundary(
                network=network,
                proxy_container=upstream,
                proxy_url=f"http://{upstream}:{UPSTREAM_PORT}",
            ), upstream
        finally:
            docker("rm", "--force", upstream, check=False)
            docker("network", "rm", network, check=False)

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

        The credential file is widened for the same reason and by the same
        rule: `isolation` mounts it in place and refuses a launch whose child
        could not rewrite it, so a file left at whatever this machine's umask
        produced is a contained run that never starts here and does start on
        the next machine.
        """
        home = fixtures.subscription(fixtures.scratch() / "home")
        home.chmod(0o777)
        (home / ".claude").chmod(0o777)
        (home / ".claude" / ".credentials.json").chmod(0o666)
        return home

    def carried(self, upstream: str) -> int:
        """How many requests to that peer carried the line it was watching for."""
        return sum(
            1
            for line in docker("logs", upstream).stdout.splitlines()
            if fixtures.CARRIED in line
        )

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
                    f"Call the {READ} tool, then say "
                    f"{fixtures.ControlUpstream.SPOKEN}."
                ),
                container=self.boundary(),
                role=fixtures.ROLE,
                timeout=300.0,
            )
        )

        self.assertEqual(_startup.KNOWN_RUNTIME, (result.sdk_version, result.cli_version))
        self.assertEqual(agent.EXPECTED_KEY_SOURCE, result.api_key_source)
        self.assertEqual(1, result.tool_ready)
        self.assertEqual((agent.BARE[READ],), result.tools_served)
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

    @unittest.skipIf(not INSTALLED, NEEDS_SDK)
    def test_a_child_stops_itself_at_the_ceiling_its_claim_reserved(self):
        """PH2-25, where the ceiling is actually enforced: in the loop.

        Nothing in the objective mentions a budget, because criterion 5 says a
        prompt instruction is not an enforcement. The session ends because the
        process summing the turns stopped reading them, and the word it ends
        with is one `agent_runs.stop_reason` already accepts.
        """
        result = agent.agent_run(
            agent.AgentRunRequest(
                agent_run_id="agent-run-1",
                objective=f"Say {fixtures.ControlUpstream.SPOKEN}.",
                container=self.boundary(),
                role=fixtures.ROLE,
                timeout=300.0,
                token_cap=1,
            )
        )

        self.assertEqual("budget", result.stop_reason)
        self.assertEqual(1, result.answers)
        self.assertGreater(result.input_tokens + result.output_tokens, 1)

    @unittest.skipIf(not INSTALLED, NEEDS_SDK)
    def test_a_tool_the_child_can_see_and_run_is_still_refused_by_the_gate(self):
        """The deny canary: what the options value says is not what decides.

        Everything that would let this call through is deliberately left open.
        `Task` is in the role's own `tools`, so the model can see it and the
        CLI will dispatch it -- and it is *not* in the options value's
        `allowed_tools`, which holds only the roster's own served tools, so
        this call is
        also the demonstration that the list the launch hands the SDK is not
        the boundary. The permission mode is `bypassPermissions`, so there is
        no prompt and nothing consulted. The subagent type is one the pair
        genuinely ships, so it is a type the CLI could start. The only thing
        standing between the model and a session with no roster row is
        `Gate.decide`, and this is the run that proves it is enough -- in the
        child, through the real hook, not against the decision function.
        """
        started = "Explore"
        self.assertIn(started, roster.inventory()["agent_types"])
        # The widening this refutes, stated as the two lists it happens between.
        role = roster.ROLES[fixtures.ROLE]
        self.assertIn(roster.DELEGATION, role.visible_tools)
        self.assertNotIn(roster.DELEGATION, role.allowed_tools(agent.SERVED))
        # A complete call, on purpose. The CLI validates a tool's input against
        # its schema before the hook runs, so an incomplete one is rejected
        # upstream of the gate and would prove nothing about the gate: dropping
        # `description` here was observed to produce a run with no denial in it.
        delegation = {
            "description": "explore the workspace",
            "prompt": "Explore this workspace.",
            "subagent_type": started,
        }
        with self.scripted(roster.DELEGATION, delegation) as (boundary, _):
            result = agent.agent_run(
                agent.AgentRunRequest(
                    agent_run_id="agent-run-canary",
                    objective=f"Delegate to the {started} agent.",
                    container=boundary,
                    role=fixtures.ROLE,
                    timeout=300.0,
                )
            )

        self.assertEqual(
            [(roster.UNKNOWN_AGENT_TYPE, roster.DELEGATION, fixtures.ROLE)],
            [(record["rule"], record["tool"], record["role"]) for record in result.denials],
        )
        self.assertIn(started, result.denials[0]["reason"])
        # The child kept going and finished a turn, so what is being asserted
        # is a refused call inside a live session rather than a session that
        # failed to start -- and no tool was served on the way through.
        self.assertEqual((), result.tools_served)
        self.assertEqual(fixtures.ControlUpstream.SPOKEN, result.text)
        self.assertEqual("end_turn", result.stop_reason)

    @unittest.skipIf(not INSTALLED, NEEDS_SDK)
    def test_a_contained_child_loads_the_skill_its_role_was_granted(self):
        """The whole join, in a real child: roster grant, staged file, loaded text.

        A grant is four things agreeing -- the roster row, the names in the
        options value, the directory the launch wrote, and the settings
        location that makes the CLI read it -- and every one of them can be
        asserted in-process while the model still gets nothing. So this is
        asserted where it cannot be faked: the far end reports the skill's own
        line arriving in a request the child sent up, which it can only do
        after the CLI found the instructions and put them in the conversation.
        """
        granted = roster.ROLES[SKILLED].skills[0]
        with self.scripted("Skill", {"skill": granted}, instruction(granted)) as (
            boundary,
            upstream,
        ):
            result = agent.agent_run(
                agent.AgentRunRequest(
                    agent_run_id="agent-run-skill",
                    objective=(
                        f"Load the {granted} skill, then say "
                        f"{fixtures.ControlUpstream.SPOKEN}."
                    ),
                    container=boundary,
                    role=SKILLED,
                    timeout=300.0,
                )
            )

            self.assertGreaterEqual(self.carried(upstream), 1)

        # The gate saw the call and admitted it, which is the other half: a run
        # where nothing was denied and nothing was loaded would look the same
        # from the outside as one where the hook never fired.
        self.assertEqual((), result.denials)
        self.assertEqual(fixtures.ControlUpstream.SPOKEN, result.text)
        self.assertEqual("end_turn", result.stop_reason)

    @unittest.skipIf(not INSTALLED, NEEDS_SDK)
    def test_a_child_cannot_load_a_skill_its_role_was_not_granted(self):
        """The same call under a role that does not hold the name.

        Nothing about the corpus changes -- this installation carries the
        skill, and another role loads it -- so what refuses is the launch: the
        role's own row granted it nothing by that name, so nothing by that name
        was staged, and the CLI answers a name it has no directory for by
        refusing rather than by reading one. The run finishes anyway, which is
        what makes the absence of the line evidence rather than a crash.
        """
        ungranted = roster.ROLES[SKILLED].skills[0]
        role = "recon"
        self.assertNotIn(ungranted, roster.ROLES[role].skills)

        with self.scripted("Skill", {"skill": ungranted}, instruction(ungranted)) as (
            boundary,
            upstream,
        ):
            result = agent.agent_run(
                agent.AgentRunRequest(
                    agent_run_id="agent-run-ungranted",
                    objective=(
                        f"Load the {ungranted} skill, then say "
                        f"{fixtures.ControlUpstream.SPOKEN}."
                    ),
                    container=boundary,
                    role=role,
                    timeout=300.0,
                )
            )

            self.assertEqual(0, self.carried(upstream))

        self.assertEqual(fixtures.ControlUpstream.SPOKEN, result.text)
        self.assertEqual("end_turn", result.stop_reason)

    def test_the_boundary_an_agent_child_runs_in_has_no_path_to_a_target(self):
        """Measured in the Agent child's own boundary, not inherited from one.

        `tests/test_isolation.py` proves the topology of a container built to
        prove topology. This is the container an Agent child actually runs in --
        the same `AgentContainer`, with the application, the SDK and the home
        mounted -- so what is asserted is that adding the three things a child
        needs to exist did not add a way out, and that the only home inside is
        the one the runtime mounted.
        """
        probe = fixtures.PROBE + """
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
                    role=fixtures.ROLE,
                    timeout=120.0,
                )
            )

        self.assertEqual("pre_spawn", raised.exception.phase)
        self.assertEqual([agent.UNMEASURED_RUNTIME], codes(raised.exception.violations))


class BoundsTest(unittest.TestCase):
    """What a run is told it may spend, before it spends any of it.

    The enforcement is older than the statement and did not change: the loop
    still breaks the turn the token ceiling is crossed. What changed is that
    the run now knows the number while it can still act on it.
    """

    def test_every_ceiling_that_was_set_is_named_and_the_others_are_not(self):
        self.assertEqual(
            "This run may spend 40000 token(s), counted across every turn, 12 turn(s), "
            "3 subagent(s) at once.\n"
            "It ends when you submit the result, or when a ceiling is reached.\n\n",
            _launch.stated(
                packet.Bounds(
                    tokens=40000,
                    turns=12,
                    subagents=3,
                    stop_conditions=("you submit the result", "a ceiling is reached"),
                )
            ),
        )

    def test_a_ceiling_nobody_set_is_not_reported_as_one(self):
        # `None` is a Program that reserved nothing, which is not a budget of
        # zero and must not read as one.
        self.assertEqual(
            "This run may spend 8 turn(s).\n\n",
            _launch.stated(packet.Bounds(turns=8)),
        )

    def test_a_run_with_no_bounds_says_nothing_about_them(self):
        self.assertEqual("", _launch.stated(packet.Bounds()))

    @unittest.skipIf(not INSTALLED, NEEDS_SDK)
    def test_the_child_reads_its_bounds_before_it_reads_its_objective(self):
        seen: list[str] = []

        async def transport(*, prompt, **_):
            seen.append(prompt)
            yield _launch.SystemMessage(
                _launch.INIT, {"apiKeySource": agent.EXPECTED_KEY_SOURCE}
            )

        bounded = job(
            fixtures.scratch(),
            objective="Say nothing.",
            packet=packet.Packet(
                bounds=packet.Bounds(tokens=40000, stop_conditions=("you stop",))
            ).as_dict(),
        )
        asyncio.run(
            _launch.run(
                bounded, environment={}, runtime=_launch.runtime_facts(), transport=transport
            )
        )

        self.assertEqual(
            "This run may spend 40000 token(s), counted across every turn.\n"
            "It ends when you stop.\n\nSay nothing.",
            seen[0],
        )


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
                job(fixtures.scratch()),
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
                    job(fixtures.scratch()),
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
            None,
            environment,
            {},
            launch_dir=fixtures.scratch(),
            role=fixtures.ROLE,
            managed_settings=(),
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
            "role": fixtures.ROLE,
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

    def test_the_job_carries_the_cap_the_caller_claimed_the_task_under(self):
        # PH2-73's seam. The scheduler ranked and claimed under the weights
        # row's number, so the gate inside the child has to refuse at that one
        # -- and the only way it reaches the child is on the job.
        written = {}
        spawn = mock.patch.object(
            agent, "_spawn", side_effect=lambda request, job: written.update(job)
        )

        with unlatched(), spawn:
            agent.agent_run(self.request(subagent_cap=5))

        self.assertEqual(5, written["subagent_cap"])

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
