import ast
import asyncio
import contextlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import rk


HERE = Path(__file__).resolve().parent


class FakeOptions:
    instances = []

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        for name, default in (
            ("env", {}),
            ("setting_sources", []),
            ("sandbox", None),
            ("settings", None),
            ("cwd", None),
            ("cli_path", None),
        ):
            if not hasattr(self, name):
                setattr(self, name, default)
        self.instances.append(self)


class FakeMessage:
    pass


class FakeSystemMessage:
    def __init__(self, source="none", *, subtype="init", include_source=True):
        self.subtype = subtype
        self.data = {"apiKeySource": source} if include_source else {}


class FakeAssistantMessage:
    def __init__(self):
        self.usage = {}


class FakeResultMessage:
    def __init__(self):
        self.usage = {}
        self.num_turns = 0
        self.stop_reason = "end_turn"
        self.total_cost_usd = 0
        self.model_usage = {}
        self.result = ""


def _fake_sdk() -> types.ModuleType:
    sdk = types.ModuleType("claude_agent_sdk")

    class HookMatcher:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def tool(*_args, **_kwargs):
        return lambda function: function

    def create_sdk_mcp_server(**kwargs):
        return kwargs

    async def query(**_kwargs):
        if False:
            yield None

    sdk.AssistantMessage = FakeAssistantMessage
    sdk.ClaudeAgentOptions = FakeOptions
    sdk.HookMatcher = HookMatcher
    sdk.ResultMessage = FakeResultMessage
    sdk.SystemMessage = FakeSystemMessage
    sdk.create_sdk_mcp_server = create_sdk_mcp_server
    sdk.query = query
    sdk.tool = tool
    sdk.__file__ = str(HERE / "fake-sdk/__init__.py")
    return sdk


def _load_child():
    module_name = "ticket03_agent_child"
    sys.modules.pop(module_name, None)
    spec = __import__("importlib.util").util.spec_from_file_location(
        module_name, HERE / "agent_child.py"
    )
    module = __import__("importlib.util").util.module_from_spec(spec)
    with patch.dict(sys.modules, {"claude_agent_sdk": _fake_sdk()}):
        spec.loader.exec_module(module)
    return module


def _runtime(cli_path: Path, sdk="0.2.132", cli="2.1.224"):
    return {"sdk_version": sdk, "cli_version": cli, "cli_path": cli_path}


def _job(runtime_dir: Path):
    return {
        "prompt": "fixture prompt",
        "model": None,
        "max_turns": 1,
        "cap": 100,
        "program": "program",
        "agent_run_id": "run-1",
        "task_id": None,
        "ct": "unused",
        "db": "unused",
        "agent_port": 18830,
        "vuln_port": 18831,
        "run_dir": str(runtime_dir.parent),
        "launch_dir": str(runtime_dir),
        "identity_entity_ids": {},
    }


class ParentLaunchContractTest(unittest.TestCase):
    def test_agent_run_builds_the_only_child_environment(self):
        captured = []

        def fake_spawn(request, job, environment):
            self.assertTrue(Path(job["launch_dir"]).is_dir())
            captured.append((request, job, environment))
            return {"ok": True}

        source_environment = {
            "PATH": "/bin",
            "HOME": "/fixture/home",
            "LANG": "C.UTF-8",
            "ANTHROPIC_API_KEY": "must-not-cross",
            "HTTP_PROXY": "http://ambient.invalid",
            "RK_CONTROL_PROXY_URL": "http://control-proxy:8080",
            "RK_CONTROL_CA_FILE": "/runtime/ca.pem",
        }
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            rk, "RUN", Path(temporary)
        ), patch.object(rk, "_spawn_agent_process", side_effect=fake_spawn), patch.dict(
            os.environ, source_environment, clear=True
        ):
            request = rk.AgentRunRequest(
                program="program",
                agent_run_id="run-1",
                task_id=None,
                prompt="fixture prompt",
            )
            self.assertEqual({"ok": True}, rk.agent_run(request))

        self.assertEqual(1, len(captured))
        _, job, environment = captured[0]
        self.assertEqual(
            {
                "PATH": "/bin",
                "HOME": "/fixture/home",
                "LANG": "C.UTF-8",
                "HTTP_PROXY": "http://control-proxy:8080",
                "HTTPS_PROXY": "http://control-proxy:8080",
                "NO_PROXY": "",
                "SSL_CERT_FILE": "/runtime/ca.pem",
                "NODE_EXTRA_CA_CERTS": "/runtime/ca.pem",
                "REQUESTS_CA_BUNDLE": "/runtime/ca.pem",
            },
            environment,
        )
        self.assertNotIn("ANTHROPIC_API_KEY", environment)
        self.assertNotIn("RK_CONTROL_PROXY_URL", environment)

    def test_request_rejects_launch_overrides(self):
        with self.assertRaises(TypeError):
            rk.AgentRunRequest(
                program="program",
                agent_run_id="run-1",
                task_id=None,
                prompt="fixture prompt",
                cli_path="/caller/claude",
            )
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            rk, "RUN", Path(temporary)
        ), self.assertRaises(ValueError):
            rk.agent_run(rk.AgentRunRequest(
                program="program", agent_run_id="..", task_id=None,
                prompt="fixture prompt",
            ))

    def test_child_refusal_is_the_external_error(self):
        violation = {
            "code": "invalid_launch", "vector": None,
            "source": "launch:env", "effect": "unverifiable",
        }
        with self.assertRaises(rk.StartupRefusal) as caught:
            rk._child_result("", json.dumps({"startup_refusal": {
                "phase": "init", "sdk_version": "0.2.132",
                "cli_version": "2.1.224", "violations": [violation],
            }}))
        self.assertEqual((violation,), caught.exception.violations)
        self.assertEqual("init", caught.exception.phase)
        self.assertEqual("0.2.132", caught.exception.sdk_version)
        self.assertEqual("2.1.224", caught.exception.cli_version)

    def test_agent_run_closes_only_structured_startup_refusals(self):
        violation = {
            "code": "invalid_launch", "vector": None,
            "source": "launch:env", "effect": "unverifiable",
        }
        request = rk.AgentRunRequest(
            program="11111111-1111-7111-8111-111111111111",
            agent_run_id="07000000-0000-7000-8000-000000000002",
            task_id="07000000-0000-7000-8000-000000000001",
            prompt="fixture prompt",
        )
        refusal = rk.StartupRefusal(
            [violation], "pre_spawn", "0.2.132", "2.1.224"
        )
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            rk, "RUN", Path(temporary)
        ), patch.object(
            rk, "_spawn_agent_process", side_effect=refusal
        ), patch.object(rk, "one", return_value="t") as sql:
            with self.assertRaises(rk.StartupRefusal):
                rk.agent_run(request)
        statement = sql.call_args.args[0]
        self.assertIn("close_startup_refusal", statement)
        self.assertIn("pre_spawn", statement)
        self.assertNotIn("fixture prompt", statement)

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            rk, "RUN", Path(temporary)
        ), patch.object(
            rk, "_spawn_agent_process", side_effect=RuntimeError("plain stderr")
        ), patch.object(rk, "one") as sql:
            with self.assertRaises(RuntimeError):
                rk.agent_run(request)
        sql.assert_not_called()


class ChildLaunchContractTest(unittest.TestCase):
    def setUp(self):
        FakeOptions.instances.clear()
        self.child = _load_child()

    def _clean_runtime(self, temporary: str):
        cli = Path(temporary) / "sdk/_bundled/claude"
        cli.parent.mkdir(parents=True)
        cli.write_text("fixture")
        cli.chmod(0o755)
        return _runtime(cli)

    def test_tool_capability_stays_out_of_serialized_state(self):
        capability = "ab" * 32
        sql = []
        queries = []

        def execute(statement, *_args, **_kwargs):
            sql.append(statement)

        def one(statement, *_args, **_kwargs):
            queries.append(statement)
            return json.dumps({
                "decision": "allow", "risk_class": "constrained",
                "rule": "tool_risk_classes", "approval": None,
                "capability": capability,
            })

        self.child.JOB = _job(Path("/tmp/unused"))
        self.child.INIT_CORROBORATED = True
        with patch.object(self.child, "_sql", side_effect=execute), patch.object(
            self.child, "_one", side_effect=one
        ):
            result = asyncio.run(self.child.pre_tool({
                "tool_name": "mcp__rk2__state_read",
                "tool_input": {"view": "scope"},
                "tool_use_id": "toolu-capability",
            }, None, None))

        self.assertEqual({}, result)
        self.assertIn("authorize_tool_run", queries[0])
        self.assertNotIn("gate_tool_call", queries[0])
        self.assertEqual([capability], list(self.child.CAPABILITIES.values()))
        self.assertNotIn(capability, json.dumps(self.child.STATE))
        self.assertNotIn(capability, "".join(sql))

    def test_clean_run_assesses_and_transports_the_same_options_once(self):
        calls = []
        assessed = []

        async def transport(*, prompt, options):
            calls.append((prompt, options))
            yield FakeSystemMessage()
            yield FakeResultMessage()

        with tempfile.TemporaryDirectory() as temporary:
            runtime_dir = Path(temporary) / "run"
            runtime_dir.mkdir()
            self.child.JOB = _job(runtime_dir)
            runtime = self._clean_runtime(temporary)
            original = self.child._assess_launch

            def assess(options, *args, **kwargs):
                assessed.append(options)
                return original(options, *args, **kwargs)

            with patch.object(self.child, "MANAGED_SETTINGS", ()), patch.object(
                self.child, "_assess_launch", side_effect=assess
            ):
                result = asyncio.run(
                    self.child._run(
                        environment={},
                        runtime=runtime,
                        options_type=FakeOptions,
                        transport=transport,
                    )
                )

        self.assertEqual("end_turn", result["stop_reason"])
        self.assertEqual(1, len(FakeOptions.instances))
        self.assertEqual(1, len(calls))
        self.assertIs(assessed[0], calls[0][1])
        options = calls[0][1]
        self.assertEqual({}, options.env)
        self.assertEqual([], options.setting_sources)
        self.assertIsNone(options.sandbox)
        self.assertIsNone(options.settings)
        self.assertEqual(str(runtime_dir.resolve()), options.cwd)
        self.assertEqual(str(runtime["cli_path"].resolve()), options.cli_path)

    def test_violation_constructs_no_transport_and_does_not_render_values(self):
        calls = []

        async def transport(**_kwargs):
            calls.append(True)
            yield FakeSystemMessage()

        with tempfile.TemporaryDirectory() as temporary:
            runtime_dir = Path(temporary) / "run"
            runtime_dir.mkdir()
            self.child.JOB = _job(runtime_dir)
            runtime = self._clean_runtime(temporary)
            with patch.object(self.child, "MANAGED_SETTINGS", ()):
                with self.assertRaises(rk.StartupRefusal) as caught:
                    asyncio.run(
                        self.child._run(
                            environment={"ANTHROPIC_AUTH_TOKEN": "never-render-this"},
                            runtime=runtime,
                            options_type=FakeOptions,
                            transport=transport,
                        )
                    )

        self.assertEqual([], calls)
        self.assertNotIn("never-render-this", str(caught.exception))
        self.assertEqual("env:ANTHROPIC_AUTH_TOKEN", caught.exception.violations[0]["source"])

    def test_environment_is_reassessed_for_each_run(self):
        calls = []

        async def transport(**_kwargs):
            calls.append(True)
            yield FakeSystemMessage()

        with tempfile.TemporaryDirectory() as temporary:
            runtime_dir = Path(temporary) / "run"
            runtime_dir.mkdir()
            self.child.JOB = _job(runtime_dir)
            runtime = self._clean_runtime(temporary)
            with patch.object(self.child, "MANAGED_SETTINGS", ()):
                asyncio.run(
                    self.child._run(
                        environment={}, runtime=runtime,
                        options_type=FakeOptions, transport=transport,
                    )
                )
                with self.assertRaises(rk.StartupRefusal):
                    asyncio.run(
                        self.child._run(
                            environment={"ANTHROPIC_API_KEY": "mutated"},
                            runtime=runtime,
                            options_type=FakeOptions,
                            transport=transport,
                        )
                    )
        self.assertEqual([True], calls)

    def test_pre_tool_is_closed_until_init_is_corroborated(self):
        self.child.JOB = _job(Path("/tmp/unused"))
        with patch.object(self.child, "_sql") as sql:
            result = asyncio.run(self.child.pre_tool({
                "tool_name": "mcp__rk2__net_request",
                "tool_input": {"url": "http://fixture.invalid/"},
                "tool_use_id": "before-init",
            }, None, None))
        self.assertEqual("deny", result["hookSpecificOutput"]["permissionDecision"])
        sql.assert_not_called()

    def test_init_must_be_first_and_exact_before_any_tool_run(self):
        cases = {
            "absent": [],
            "wrong_first": [FakeResultMessage()],
            "missing_source": [FakeSystemMessage(include_source=False)],
            "other_source": [FakeSystemMessage("apiKeyHelper")],
        }
        with tempfile.TemporaryDirectory() as temporary:
            runtime_dir = Path(temporary) / "run"
            runtime_dir.mkdir()
            self.child.JOB = _job(runtime_dir)
            runtime = self._clean_runtime(temporary)
            for name, stream in cases.items():
                closed = []

                async def transport(**_kwargs):
                    try:
                        for message in stream:
                            yield message
                    finally:
                        closed.append(True)

                with self.subTest(name=name), patch.object(
                    self.child, "MANAGED_SETTINGS", ()
                ), patch.object(self.child, "_sql") as sql:
                    with self.assertRaises(rk.StartupRefusal) as caught:
                        asyncio.run(self.child._run(
                            environment={}, runtime=runtime,
                            options_type=FakeOptions, transport=transport,
                        ))
                    self.assertEqual("init", caught.exception.phase)
                    self.assertEqual({
                        "code": "auth_source_unexpected", "vector": None,
                        "source": "init:apiKeySource", "effect": "unverifiable",
                    }, caught.exception.violations[0])
                    self.assertFalse(self.child.INIT_CORROBORATED)
                    sql.assert_not_called()
                    self.assertTrue(closed)

    def test_all_watched_vectors_and_helper_refuse_before_transport(self):
        vectors = {
            "ANTHROPIC_API_KEY": "off_subscription_auth",
            "ANTHROPIC_AUTH_TOKEN": "off_subscription_auth",
            "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR": "startup_denial",
            "CLAUDE_CODE_USE_BEDROCK": "provider_reroute",
            "CLAUDE_CODE_USE_VERTEX": "provider_reroute",
            "CLAUDE_CODE_USE_FOUNDRY": "provider_reroute",
            "ANTHROPIC_BASE_URL": "destination_override",
        }
        with tempfile.TemporaryDirectory() as temporary:
            runtime_dir = Path(temporary) / "run"
            runtime_dir.mkdir()
            self.child.JOB = _job(runtime_dir)
            runtime = self._clean_runtime(temporary)
            for vector, effect in vectors.items():
                called = []

                async def transport(**_kwargs):
                    called.append(True)
                    yield FakeSystemMessage()

                with self.subTest(vector=vector), patch.object(
                    self.child, "MANAGED_SETTINGS", ()
                ), self.assertRaises(rk.StartupRefusal) as caught:
                    asyncio.run(self.child._run(
                        environment={vector: "synthetic"}, runtime=runtime,
                        options_type=FakeOptions, transport=transport,
                    ))
                self.assertEqual("pre_spawn", caught.exception.phase)
                self.assertEqual([], called)
                self.assertEqual({
                    "code": "credential_vector", "vector": vector,
                    "source": f"env:{vector}", "effect": effect,
                }, caught.exception.violations[0])

            managed = Path(temporary) / "managed.json"
            managed.write_text('{"apiKeyHelper":"synthetic-helper"}')
            called = []

            async def transport(**_kwargs):
                called.append(True)
                yield FakeSystemMessage()

            with patch.object(self.child, "MANAGED_SETTINGS", (managed,)), \
                 self.assertRaises(rk.StartupRefusal) as caught:
                asyncio.run(self.child._run(
                    environment={}, runtime=runtime,
                    options_type=FakeOptions, transport=transport,
                ))
            self.assertEqual([], called)
            self.assertEqual({
                "code": "credential_vector", "vector": "apiKeyHelper",
                "source": f"settings:managed:{managed.resolve()}#apiKeyHelper",
                "effect": "off_subscription_auth",
            }, caught.exception.violations[0])

    def test_main_renders_refusal_only_to_stderr_and_exits_78(self):
        violation = {
            "code": "unmeasured_runtime", "vector": None,
            "source": "runtime:sdk-cli", "effect": "unverifiable",
        }
        runtime = {"sdk_version": None, "cli_version": None, "cli_path": None}
        with tempfile.TemporaryDirectory() as temporary:
            job = _job(Path(temporary))
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(sys, "argv", ["agent_child.py", json.dumps(job)]), \
                 patch.object(self.child, "_runtime_facts", return_value=runtime), \
                 patch.object(
                     self.child.anyio, "run",
                     side_effect=rk.StartupRefusal([violation]),
                 ), contextlib.redirect_stdout(stdout), \
                 contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as caught:
                    self.child.main()

        self.assertEqual(78, caught.exception.code)
        self.assertEqual("", stdout.getvalue())
        rendered = json.loads(stderr.getvalue())
        self.assertEqual({
            "phase": "pre_spawn", "sdk_version": None, "cli_version": None,
            "violations": [violation],
        }, rendered["startup_refusal"])

    def test_settings_fail_closed_and_sources_stay_fixed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            root.mkdir()
            runtime = self._clean_runtime(temporary)

            cases = {
                "inline": ("{}", "invalid_launch"),
                "relative": ("settings.json", "invalid_launch"),
                "missing": (str(root / "missing.json"), "settings_unreadable"),
                "unreadable": (str(root / "directory.json"), "settings_unreadable"),
                "malformed": (str(root / "malformed.json"), "settings_unreadable"),
                "non_object": (str(root / "array.json"), "settings_unreadable"),
                "env_non_object": (str(root / "env-array.json"), "settings_unreadable"),
            }
            (root / "directory.json").mkdir()
            (root / "malformed.json").write_text("{")
            (root / "array.json").write_text("[]")
            (root / "env-array.json").write_text('{"env": []}')

            for name, (settings, code) in cases.items():
                with self.subTest(name=name):
                    options = FakeOptions(
                        env={}, setting_sources=[], sandbox=None,
                        settings=settings, cwd=str(root), cli_path=str(runtime["cli_path"]),
                    )
                    violations = self.child._assess_launch(
                        options, {}, runtime, managed_settings=()
                    )
                    self.assertIn(code, {item["code"] for item in violations})

            project = root / ".claude/settings.json"
            project.parent.mkdir()
            project.write_text('{"apiKeyHelper": "ignored"}')
            options = FakeOptions(
                env={}, setting_sources=[], sandbox=None, settings=None,
                cwd=str(root), cli_path=str(runtime["cli_path"]),
            )
            self.assertEqual((), self.child._assess_launch(options, {}, runtime, managed_settings=()))

            explicit = root / "settings.json"
            explicit.write_text('{"apiKeyHelper": "refuse"}')
            options.settings = str(explicit)
            violations = self.child._assess_launch(
                options, {}, runtime, managed_settings=()
            )
            self.assertEqual("apiKeyHelper", violations[0]["vector"])
            self.assertIn("settings:explicit:", violations[0]["source"])

            managed = Path(temporary) / "managed.json"
            managed.write_text('{"apiKeyHelper": "refuse"}')
            options.settings = None
            violations = self.child._assess_launch(
                options, {}, runtime, managed_settings=(managed,)
            )
            self.assertEqual("apiKeyHelper", violations[0]["vector"])
            self.assertIn("settings:managed:", violations[0]["source"])

    def test_runtime_launch_and_vector_problems_are_aggregated_stably(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            root.mkdir()
            malformed = root / "settings.json"
            malformed.write_text("{")
            options = FakeOptions(
                env={"unexpected": "value"},
                setting_sources=["project"],
                sandbox={"enabled": True},
                settings=str(malformed),
                cwd=str(root / "other"),
                cli_path="/caller/claude",
            )
            violations = self.child._assess_launch(
                options,
                {"ANTHROPIC_API_KEY": "do-not-render"},
                _runtime(Path(temporary) / "missing", sdk="9.9.9", cli="9.9.9"),
                managed_settings=(),
                runtime_dir=root,
            )

        self.assertEqual("credential_vector", violations[0]["code"])
        self.assertEqual(
            sorted(
                violations[1:], key=lambda item: (item["code"], item["source"])
            ),
            list(violations[1:]),
        )
        self.assertTrue(
            {"invalid_launch", "settings_unreadable", "unmeasured_runtime"}
            <= {item["code"] for item in violations}
        )
        self.assertTrue(all(
            item["vector"] is None and item["effect"] == "unverifiable"
            for item in violations[1:]
        ))
        self.assertEqual(
            ["runtime:sdk-cli"],
            [item["source"] for item in violations
             if item["code"] == "unmeasured_runtime"],
        )
        self.assertNotIn("do-not-render", json.dumps(violations))


class StaticLaunchBoundaryTest(unittest.TestCase):
    def test_only_agent_child_imports_and_constructs_the_sdk(self):
        offenders = []
        for path in sorted(HERE.glob("*.py")):
            if path.name.startswith("test_"):
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [alias.name for alias in node.names]
                    if isinstance(node, ast.ImportFrom) and node.module:
                        names.append(node.module)
                    if any(name.startswith("claude_agent_sdk") for name in names):
                        offenders.append(path.name)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in {"ClaudeAgentOptions", "query"}:
                        offenders.append(path.name)
        self.assertEqual({"agent_child.py"}, set(offenders))

    def test_hunter_roster_has_no_raw_process_or_credential_operation(self):
        tree = ast.parse((HERE / "agent_child.py").read_text())
        tool_names = {
            node.decorator_list[0].args[0].value
            for node in tree.body
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.decorator_list
            and isinstance(node.decorator_list[0], ast.Call)
            and isinstance(node.decorator_list[0].func, ast.Name)
            and node.decorator_list[0].func.id == "tool"
        }
        self.assertEqual({"state_read", "net_request", "propose_finding"}, tool_names)
        forbidden = {"bash", "credential", "environment", "process", "settings", "shell"}
        self.assertTrue(all(not forbidden.intersection(name.split("_")) for name in tool_names))


if __name__ == "__main__":
    unittest.main()
