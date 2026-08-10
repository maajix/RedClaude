import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import redkraken
from redkraken import pg
from redkraken.outcome import (
    EXIT_DATABASE_UNREACHABLE,
    EXIT_INVALID_CONFIGURATION,
    EXIT_OK,
    EXIT_UNSUPPORTED_VERSION,
    EXIT_USAGE,
)
from tests import ROOT, SOURCE
from tests.fixtures import (
    SCOPE_ENTITIES,
    SCOPE_REFUSALS,
    SCOPE_REQUESTS,
    SCOPED,
    VALID,
    scratch,
    write,
)


#: Records the effects `rk doctor` promises never to have, rather than raising
#: inside the hook, so a failure names the event that happened.
DRIVER = """
import json, os, sys

observed = []


REACHING_OUT = (
    "socket.", "urllib.", "http.client", "ftplib.", "smtplib.",
    "subprocess.", "os.exec", "os.system", "os.spawn", "os.posix_spawn", "os.fork",
)

#: Ways to change the file system that never open anything, so the `open`
#: branch below would not see them.
CHANGING = (
    "os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.chmod", "os.chown",
    "os.symlink", "os.link", "os.truncate", "os.utime",
)


def hook(event, arguments):
    if event.startswith(REACHING_OUT) or event in CHANGING:
        observed.append(event)
    elif event == "open":
        mode, flags = arguments[1], arguments[2]
        written = (
            any(character in mode for character in "wxa+")
            if mode
            else bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
        )
        if written:
            observed.append("open:" + str(arguments[0]))


sys.addaudithook(hook)

from redkraken.cli import main

code = main(sys.argv[1:])
loaded = sorted({getattr(module, "__file__", None) or "" for module in sys.modules.values()})
sys.stderr.write(json.dumps({"exit": code, "events": observed, "loaded": loaded}))
"""


def environment() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(SOURCE),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def run(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "redkraken", *arguments],
        cwd=str(cwd or ROOT),
        env=environment(),
        text=True,
        capture_output=True,
        check=False,
    )


def observe(*arguments: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", DRIVER, *arguments],
        cwd=str(ROOT),
        env=environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stderr)


class VersionTest(unittest.TestCase):
    def test_version_is_reported_in_a_stable_form(self):
        result = run("--version")

        self.assertEqual(EXIT_OK, result.returncode, result.stderr)
        self.assertEqual(f"rk {redkraken.__version__}\n", result.stdout)


class DoctorCommandTest(unittest.TestCase):
    def test_valid_configuration_reports_readiness(self):
        result = run("doctor", "--config", str(write(VALID)))

        self.assertEqual(EXIT_OK, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual("acme-web", report["configuration"]["program_name"])
        self.assertEqual([], report["violations"])

    def test_readiness_is_reported_without_a_configuration(self):
        result = run("doctor")

        self.assertEqual(EXIT_OK, result.returncode, result.stderr)
        self.assertIsNone(json.loads(result.stdout)["configuration"])

    def test_invalid_configuration_exits_three(self):
        result = run("doctor", "--config", str(write(VALID.replace("[budgets]\n", "[budgets]\nspend = 1\n"))))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        self.assertEqual(
            [{"code": "invalid_configuration", "source": "config:budgets.spend", "detail": "unknown key"}],
            report["violations"],
        )

    def test_absent_configuration_file_exits_three(self):
        result = run("doctor", "--config", str(scratch() / "absent.toml"))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)

    def test_a_directory_is_not_a_configuration(self):
        result = run("doctor", "--config", str(scratch()))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        self.assertIn("not a regular file", result.stdout)

    def test_unsupported_configuration_version_exits_four(self):
        result = run("doctor", "--config", str(write(VALID.replace("schema_version = 1", "schema_version = 9"))))

        self.assertEqual(EXIT_UNSUPPORTED_VERSION, result.returncode)
        self.assertEqual(
            ["unsupported_version"],
            [violation["code"] for violation in json.loads(result.stdout)["violations"]],
        )

    def test_missing_command_is_a_usage_error(self):
        result = run()

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("usage: rk", result.stderr)

    def test_unknown_command_is_a_usage_error(self):
        result = run("hunt")

        self.assertEqual(EXIT_USAGE, result.returncode)


class ScopeCommandTest(unittest.TestCase):
    """`rk scope`: the compiled policy, asked through the operator's own adapter.

    The whole fixture matrix goes through one invocation, because the ticket's
    last criterion is that the CLI and the runtime decide alike. `tests.test_scope`
    puts the same matrix through the evaluator and `tests.test_database` puts it
    through `scope_class_of`; a disagreement is a bug in one of the three, and
    without the shared matrix it would be a bug nobody could see.
    """

    @classmethod
    def setUpClass(cls):
        arguments = ["scope", "--config", str(write(SCOPED))]
        for url, _, _ in SCOPE_REQUESTS:
            arguments += ["--url", url]
        for url, _ in SCOPE_REFUSALS:
            arguments += ["--url", url]
        for kind, selector, port, path, _, _ in SCOPE_ENTITIES:
            flag = "--host" if kind == "host" else "--subtree"
            spelling = selector + (f":{port}" if port else "") + ("" if path == "/" else path)
            arguments += [flag, spelling]
        cls.result = run(*arguments)
        assert cls.result.returncode == EXIT_OK, cls.result.stderr
        cls.report = json.loads(cls.result.stdout)

    def decided(self, url: str) -> dict:
        return next(item for item in self.report["requests"] if item["url"] == url)

    def projected(self, kind: str, selector: str, port: int | None, path: str) -> dict:
        return next(
            item
            for item in self.report["entities"]
            if (item["selector_kind"], item["selector"], item["port"], item["path"])
            == (kind, selector, port, path)
        )

    def test_the_command_reports_the_compiled_policy(self):
        policy = self.report["policy"]

        self.assertEqual("matrix-web", policy["program"])
        self.assertEqual(18, policy["rules"])
        self.assertEqual(64, len(policy["policy_sha256"]))
        self.assertEqual(["X-Bounty-Id"], policy["required_headers"])

    def test_every_request_in_the_matrix_is_decided_as_the_matrix_says(self):
        for url, scope_class, reason in SCOPE_REQUESTS:
            with self.subTest(url):
                decision = self.decided(url)
                self.assertEqual(scope_class, decision["scope_class"])
                self.assertEqual(reason, decision["reason"])

    def test_every_refused_url_in_the_matrix_is_denied_for_the_stated_reason(self):
        for url, reason in SCOPE_REFUSALS:
            with self.subTest(url):
                decision = self.decided(url)
                self.assertEqual("denied", decision["scope_class"])
                self.assertEqual(reason, decision["reason"])

    def test_every_entity_in_the_matrix_is_projected_as_the_matrix_says(self):
        for kind, selector, port, path, scope_class, reason in SCOPE_ENTITIES:
            with self.subTest(f"{kind}:{selector}:{port}:{path}"):
                decision = self.projected(kind, selector, port, path)
                self.assertEqual(scope_class, decision["scope_class"])
                self.assertEqual(reason, decision["reason"])

    def test_a_denial_is_an_answer_rather_than_a_refusal(self):
        # Denials are the majority of the matrix and the command still exits 0:
        # `ok` is about whether the question could be answered.
        self.assertTrue(self.report["ok"])
        self.assertEqual(EXIT_OK, self.report["exit_code"])
        self.assertEqual([], self.report["violations"])
        self.assertIn(
            "denied", {decision["scope_class"] for decision in self.report["requests"]}
        )

    def test_all_five_permissions_and_all_five_techniques_are_reported_unasked(self):
        self.assertEqual(
            {"availability_impact", "credential_use", "mutation", "pivoting",
             "sensitive_data_access"},
            {item["subject"] for item in self.report["permissions"]},
        )
        self.assertEqual(
            {"adjacent_host", "certificate_transparency", "dns_enumeration",
             "reverse_ip", "virtual_host"},
            {item["subject"] for item in self.report["discovery"]},
        )
        self.assertEqual(
            [False] * 5, [item["allowed"] for item in self.report["discovery"]]
        )

    def test_no_required_header_value_reaches_the_operator_s_terminal(self):
        self.assertIn("X-Bounty-Id", self.result.stdout)
        self.assertNotIn("slot://", self.result.stdout)

    def test_a_refused_configuration_is_reported_in_the_scope_shape(self):
        result = run("scope", "--config", str(write(SCOPED.replace("[budgets]", "[budget]"))))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        self.assertIsNone(report["policy"])
        self.assertEqual([], report["requests"])

    def test_a_configuration_that_parses_and_does_not_compile_is_refused(self):
        result = run(
            "scope",
            "--config",
            str(write(SCOPED.replace('host = "api.example.net"', 'host = "127.0.0.1"'))),
            "--url",
            "https://app.example.com/",
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertIsNone(report["policy"])
        self.assertEqual(
            ["scope:scope.include[1].host"],
            [violation["source"] for violation in report["violations"]],
        )

    def test_a_permission_this_grammar_has_no_word_for_is_refused(self):
        result = run("scope", "--config", str(write(SCOPED)), "--action", "exfiltration")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual(
            ["argument:exfiltration"],
            [violation["source"] for violation in report["violations"]],
        )

    def test_a_discovery_technique_this_grammar_has_no_word_for_is_refused(self):
        result = run("scope", "--config", str(write(SCOPED)), "--discovery", "port_scan")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)

    def test_a_scope_question_without_a_configuration_is_a_usage_error(self):
        result = run("scope", "--url", "https://app.example.com/")

        self.assertEqual(EXIT_USAGE, result.returncode)

    def test_an_observed_interaction_is_matched_against_the_declared_channels(self):
        result = run(
            "scope",
            "--config",
            str(write(SCOPED)),
            "--callback",
            "abc123.dns.example.org",
            "--callback",
            "elsewhere.test",
        )

        self.assertEqual(EXIT_OK, result.returncode)
        callbacks = json.loads(result.stdout)["callbacks"]
        self.assertEqual(["egress_support", "denied"], [item["scope_class"] for item in callbacks])
        self.assertEqual("oob-dns", callbacks[0]["channel"])

    def test_the_command_reaches_no_database(self):
        # No RK_* variable is set for these runs, and none is asked for: a scope
        # question is a function of the configuration and nothing else.
        loaded = observe("scope", "--config", str(write(SCOPED)), "--url", "https://app.example.com/")

        self.assertEqual(0, loaded["exit"])
        self.assertEqual([], [event for event in loaded["events"] if event[0] == "socket.connect"])


class DatabaseCommandTest(unittest.TestCase):
    """The database commands, up to the point where a database is needed.

    `run` supplies an environment with no `RK_*` variables in it, so every case
    here is one an operator meets before anything is opened.
    """

    def test_a_missing_connection_string_names_the_variable_that_holds_it(self):
        result = run("db", "migrate")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("db migrate", report["command"])
        self.assertEqual(
            [("invalid_configuration", "environment:RK_MIGRATE_URL")],
            [(item["code"], item["source"]) for item in report["violations"]],
        )

    def test_each_command_reads_the_variable_for_its_own_role(self):
        # Separate variables because they are separate roles: the role split is
        # lost if one exported URL can run every command.
        observed = {}
        moving = {"dump": ("--to", "/x/archive.dump"), "restore": ("--from", "/x/archive.dump")}
        for operation in ("provision", "migrate", "verify", "status", "dump", "restore"):
            report = json.loads(run("db", operation, *moving.get(operation, ())).stdout)
            observed[operation] = report["violations"][0]["source"]

        self.assertEqual(
            {
                "provision": "environment:RK_SUPERUSER_URL",
                "migrate": "environment:RK_MIGRATE_URL",
                "verify": "environment:RK_MIGRATE_URL",
                "status": "environment:RK_MIGRATE_URL",
                "dump": "environment:RK_MIGRATE_URL",
                "restore": "environment:RK_RESTORE_URL",
            },
            observed,
        )

    def test_a_connection_string_this_client_cannot_honour_is_refused(self):
        result = run("db", "status", "--url", "mysql://rk2@localhost/rk2")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("argument:--url", report["violations"][0]["source"])
        self.assertIn("must be postgresql://", report["violations"][0]["detail"])

    def test_an_unsupported_connection_parameter_is_refused_rather_than_ignored(self):
        # A silently dropped sslmode is a downgrade, so an unknown one is a stop.
        result = run("db", "status", "--url", "postgresql://rk2@localhost/rk2?sslcert=/x")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        self.assertIn("unsupported connection parameter", result.stdout)

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        # Port 1 is not a PostgreSQL server on any machine this runs on.
        result = run("db", "status", "--url", "postgresql://rk2@127.0.0.1:1/rk2")

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.returncode)
        self.assertEqual(
            ["database_unreachable"],
            [item["code"] for item in json.loads(result.stdout)["violations"]],
        )

    def test_the_connection_string_is_never_echoed_back(self):
        url = "postgresql://rk2:s3cr3t-sentinel@127.0.0.1:1/rk2"

        result = run("db", "status", "--url", url)

        self.assertNotIn("s3cr3t-sentinel", result.stdout)
        self.assertNotIn("s3cr3t-sentinel", result.stderr)

    def test_a_database_command_without_an_operation_is_a_usage_error(self):
        result = run("db")

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("usage: rk db", result.stderr)

    def test_moving_an_archive_requires_being_told_where(self):
        self.assertEqual(EXIT_USAGE, run("db", "dump").returncode)
        self.assertEqual(EXIT_USAGE, run("db", "restore").returncode)

    def test_the_gate_can_be_asked_about_the_artifact_store_and_is_not_refused_without_one(self):
        # Unlike `rk artifact`, which has nothing to do without a store. The gate
        # has an answer either way, and refusing here would leave an operator who
        # keeps no artifacts unable to run it at all.
        without = run("db", "verify")
        with_store = run("db", "verify", "--artifacts", str(scratch() / "artifacts"))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, without.returncode)
        self.assertEqual(EXIT_INVALID_CONFIGURATION, with_store.returncode)
        self.assertEqual(
            ["environment:RK_MIGRATE_URL"],
            [item["source"] for item in json.loads(without.stdout)["violations"]],
        )
        self.assertEqual(
            ["environment:RK_MIGRATE_URL"],
            [item["source"] for item in json.loads(with_store.stdout)["violations"]],
        )


class RunCommandTest(unittest.TestCase):
    """`rk run`, up to the point where a database is needed.

    The command's own connection string, because it is the runtime's: the role
    that opens a Program is the one the model's tool calls run through, and it
    is not the role that migrated the schema.
    """

    def test_a_missing_connection_string_names_the_variable_that_holds_it(self):
        result = run("run", "--config", str(write(VALID)))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("run", report["command"])
        self.assertEqual(
            [("invalid_configuration", "environment:RK_DATABASE_URL")],
            [(item["code"], item["source"]) for item in report["violations"]],
        )

    def test_a_run_without_a_configuration_is_a_usage_error(self):
        result = run("run", "--url", "postgresql://rk2_runtime@127.0.0.1:1/rk2")

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("--config", result.stderr)

    def test_a_refused_configuration_is_reported_in_the_run_shape(self):
        source = write(VALID.replace("[budgets]\n", "[budgets]\nspend = 1\n"))

        result = run("run", "--config", str(source), "--url", "postgresql://rk2@127.0.0.1:1/rk2")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertIsNone(report["program_id"])
        self.assertEqual("refused", report["stop_reason"])
        self.assertEqual(["config:budgets.spend"], [item["source"] for item in report["violations"]])

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        result = run(
            "run", "--config", str(write(VALID)), "--url", "postgresql://rk2@127.0.0.1:1/rk2"
        )

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.returncode)
        self.assertEqual("run", json.loads(result.stdout)["command"])

    def test_the_connection_string_is_never_echoed_back(self):
        result = run(
            "run",
            "--config", str(write(VALID)),
            "--url", "postgresql://rk2:s3cr3t-sentinel@127.0.0.1:1/rk2",
        )

        self.assertNotIn("s3cr3t-sentinel", result.stdout)
        self.assertNotIn("s3cr3t-sentinel", result.stderr)

    def test_a_refused_configuration_reaches_no_database_at_all(self):
        # Criterion 5, at the CLI: a run refused by the operator's own file
        # cannot have changed a database, because it never opened a socket.
        source = write(VALID.replace("requests = 5000", "requests = 0"))

        observed = observe(
            "run", "--config", str(source), "--url", "postgresql://rk2@127.0.0.1:1/rk2"
        )

        self.assertEqual([], observed["events"])
        self.assertEqual(EXIT_INVALID_CONFIGURATION, observed["exit"])


class StateCommandTest(unittest.TestCase):
    """`rk state`, up to the point where a database is needed.

    Two connection strings, and they are not interchangeable. The Program is
    resolved as the runtime and its records are read as the agent, which cannot
    resolve one -- so a missing second string is a refusal rather than a
    fallback to the first.
    """

    def test_both_connection_strings_are_named_when_neither_is_set(self):
        result = run("state", "--config", str(write(VALID)))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("state", report["command"])
        self.assertEqual(
            ["environment:RK_DATABASE_URL", "environment:RK_STATE_URL"],
            [item["source"] for item in report["violations"]],
        )

    def test_the_agent_connection_string_has_no_fallback(self):
        result = run(
            "state",
            "--config", str(write(VALID)),
            "--url", "postgresql://rk2_runtime@127.0.0.1:1/rk2",
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        self.assertEqual(
            ["environment:RK_STATE_URL"],
            [item["source"] for item in json.loads(result.stdout)["violations"]],
        )

    def test_a_read_without_a_configuration_is_a_usage_error(self):
        result = run("state", "--url", "postgresql://rk2_runtime@127.0.0.1:1/rk2")

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("--config", result.stderr)

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        result = run(
            "state",
            "--config", str(write(VALID)),
            "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            "--state-url", "postgresql://rk2_state@127.0.0.1:1/rk2",
        )

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.returncode)
        self.assertEqual("state", json.loads(result.stdout)["command"])

    def test_neither_connection_string_is_ever_echoed_back(self):
        result = run(
            "state",
            "--config", str(write(VALID)),
            "--url", "postgresql://rk2:s3cr3t-runtime@127.0.0.1:1/rk2",
            "--state-url", "postgresql://rk2_state:s3cr3t-agent@127.0.0.1:1/rk2",
        )

        for secret in ("s3cr3t-runtime", "s3cr3t-agent"):
            with self.subTest(secret):
                self.assertNotIn(secret, result.stdout)
                self.assertNotIn(secret, result.stderr)

    def test_a_refused_configuration_reaches_no_database_at_all(self):
        source = write(VALID.replace("requests = 5000", "requests = 0"))

        observed = observe(
            "state",
            "--config", str(source),
            "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            "--state-url", "postgresql://rk2_state@127.0.0.1:1/rk2",
        )

        self.assertEqual([], observed["events"])
        self.assertEqual(EXIT_INVALID_CONFIGURATION, observed["exit"])


class ArtifactCommandTest(unittest.TestCase):
    """`rk artifact`, up to the point where a database is needed.

    Three inputs rather than two, and the third is not a connection string. The
    database holds a hash and the filesystem holds the bytes, so a store that
    was never named is a refusal: defaulting to somewhere would file bytes
    somewhere nobody chose and report an empty store the next time the command
    ran from a different directory.
    """

    def test_the_store_is_named_alongside_the_connection_when_neither_is_set(self):
        result = run("artifact", "audit", "--config", str(write(VALID)))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("artifact audit", report["command"])
        self.assertEqual(
            ["environment:RK_ARTIFACT_ROOT", "environment:RK_DATABASE_URL"],
            [item["source"] for item in report["violations"]],
        )

    def test_a_read_names_both_connection_strings_and_the_store(self):
        result = run("artifact", "get", "--config", str(write(VALID)), "--label", "AF1")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        self.assertEqual(
            [
                "environment:RK_ARTIFACT_ROOT",
                "environment:RK_DATABASE_URL",
                "environment:RK_STATE_URL",
            ],
            [item["source"] for item in json.loads(result.stdout)["violations"]],
        )

    def test_a_read_without_a_label_is_a_usage_error(self):
        result = run(
            "artifact",
            "get",
            "--config", str(write(VALID)),
            "--artifacts", str(scratch()),
        )

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("--label", result.stderr)

    def test_there_is_no_way_to_ask_for_an_artifact_by_hash(self):
        result = run(
            "artifact",
            "get",
            "--config", str(write(VALID)),
            "--label", "AF1",
            "--sha256", "0" * 64,
            "--artifacts", str(scratch()),
        )

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("--sha256", result.stderr)

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        payload = scratch() / "body.txt"
        payload.write_bytes(b"stored by nobody")

        result = run(
            "artifact",
            "put",
            "--config", str(write(VALID)),
            "--from", str(payload),
            "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            "--artifacts", str(scratch()),
        )

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.returncode)
        self.assertEqual("artifact put", json.loads(result.stdout)["command"])

    def test_neither_connection_string_is_ever_echoed_back(self):
        result = run(
            "artifact",
            "get",
            "--config", str(write(VALID)),
            "--label", "AF1",
            "--url", "postgresql://rk2:s3cr3t-runtime@127.0.0.1:1/rk2",
            "--state-url", "postgresql://rk2_state:s3cr3t-agent@127.0.0.1:1/rk2",
            "--artifacts", str(scratch()),
        )

        for secret in ("s3cr3t-runtime", "s3cr3t-agent"):
            with self.subTest(secret):
                self.assertNotIn(secret, result.stdout)
                self.assertNotIn(secret, result.stderr)

    def test_a_refused_configuration_reaches_no_database_and_writes_nothing(self):
        source = write(VALID.replace("requests = 5000", "requests = 0"))
        payload = scratch() / "body.txt"
        payload.write_bytes(b"never stored")
        root = scratch() / "artifacts"

        observed = observe(
            "artifact",
            "put",
            "--config", str(source),
            "--from", str(payload),
            "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            "--artifacts", str(root),
        )

        self.assertEqual([], observed["events"])
        self.assertEqual(EXIT_INVALID_CONFIGURATION, observed["exit"])
        self.assertFalse(root.exists())


class SealCommandTest(unittest.TestCase):
    """`rk artifact seal` and `rk artifact open`, up to the database.

    A fourth input, and it is the one that matters: the key file. It is named the
    way the store is named -- a flag, or a variable behind it, and a refusal when
    neither -- because an operator who moved the artifacts has not thereby moved
    the key, and the sealed half is worth exactly what that separation is worth.
    """

    def files(self) -> tuple[Path, Path, Path]:
        home = scratch()
        wire = home / "wire.txt"
        wire.write_bytes(b"Authorization: Bearer sk-live-not-in-a-log\r\n")
        redacted = home / "redacted.txt"
        redacted.write_bytes(b"Authorization: [redacted]\r\n")
        key = home / "artifact.key"
        key.write_bytes(bytes(range(32)))
        key.chmod(0o600)
        return wire, redacted, key

    def test_the_key_is_named_alongside_the_store_and_the_connection(self):
        wire, redacted, _ = self.files()

        result = run(
            "artifact",
            "seal",
            "--config", str(write(VALID)),
            "--wire", str(wire),
            "--redacted", str(redacted),
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("artifact seal", report["command"])
        self.assertEqual(
            [
                "environment:RK_ARTIFACT_KEY",
                "environment:RK_ARTIFACT_ROOT",
                "environment:RK_DATABASE_URL",
            ],
            sorted(item["source"] for item in report["violations"]),
        )

    def test_sealing_needs_both_views_named(self):
        wire, _, key = self.files()

        result = run(
            "artifact",
            "seal",
            "--config", str(write(VALID)),
            "--wire", str(wire),
            "--artifacts", str(scratch()),
            "--key", str(key),
        )

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("--redacted", result.stderr)

    def test_there_is_no_way_to_open_an_artifact_by_hash(self):
        _, _, key = self.files()

        result = run(
            "artifact",
            "open",
            "--config", str(write(VALID)),
            "--label", "AF1",
            "--sha256", "0" * 64,
            "--into", str(scratch() / "opened.bin"),
            "--artifacts", str(scratch()),
            "--key", str(key),
        )

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("--sha256", result.stderr)

    def test_opening_needs_somewhere_to_put_what_it_opened(self):
        # There is no "print it" form of this command, so `--into` is required
        # rather than defaulted to standard output.
        _, _, key = self.files()

        result = run(
            "artifact",
            "open",
            "--config", str(write(VALID)),
            "--label", "AF1",
            "--artifacts", str(scratch()),
            "--key", str(key),
        )

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("--into", result.stderr)

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        wire, redacted, key = self.files()

        result = run(
            "artifact",
            "seal",
            "--config", str(write(VALID)),
            "--wire", str(wire),
            "--redacted", str(redacted),
            "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            "--artifacts", str(scratch()),
            "--key", str(key),
        )

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.returncode)
        self.assertEqual("artifact seal", json.loads(result.stdout)["command"])

    def test_neither_the_wire_bytes_nor_the_connection_string_are_echoed_back(self):
        wire, redacted, key = self.files()

        result = run(
            "artifact",
            "seal",
            "--config", str(write(VALID)),
            "--wire", str(wire),
            "--redacted", str(redacted),
            "--url", "postgresql://rk2:s3cr3t-runtime@127.0.0.1:1/rk2",
            "--artifacts", str(scratch()),
            "--key", str(key),
        )

        for secret in ("s3cr3t-runtime", "sk-live-not-in-a-log"):
            with self.subTest(secret):
                self.assertNotIn(secret, result.stdout)
                self.assertNotIn(secret, result.stderr)

    def test_a_refused_configuration_reaches_no_database_and_writes_nothing(self):
        wire, redacted, key = self.files()
        source = write(VALID.replace("requests = 5000", "requests = 0"))
        root = scratch() / "artifacts"

        observed = observe(
            "artifact",
            "seal",
            "--config", str(source),
            "--wire", str(wire),
            "--redacted", str(redacted),
            "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            "--artifacts", str(root),
            "--key", str(key),
        )

        self.assertEqual([], observed["events"])
        self.assertEqual(EXIT_INVALID_CONFIGURATION, observed["exit"])
        self.assertFalse(root.exists())


class ProxyCommandTest(unittest.TestCase):
    """`rk proxy`, up to the point where a database or a door is needed.

    The two verbs read different variables because they are different roles on
    two sides of one fence: `serve` is the door and holds `rk2_proxy`, `request`
    is the thing being fenced and holds the runtime connection. An operator who
    exported one URL for both would be running a fence with the privileges of
    what it fences, so there is no variable that satisfies both.

    The third input is not a role at all. `RK_PROXY_URL` is where a capability is
    allowed to travel, and the refusals below are the Python half of "the runtime
    sends the plaintext capability only to the local proxy".
    """

    def test_each_side_of_the_fence_reads_the_variable_for_its_own_role(self):
        serving = json.loads(run("proxy", "serve").stdout)
        sending = json.loads(
            run("proxy", "request", "--config", str(write(SCOPED)), "http://app.example.com/").stdout
        )

        self.assertEqual("proxy serve", serving["command"])
        self.assertEqual(
            ["environment:RK_ARTIFACT_ROOT", "environment:RK_PROXY_DATABASE_URL"],
            [item["source"] for item in serving["violations"]],
        )
        self.assertEqual("proxy request", sending["command"])
        self.assertEqual(
            ["environment:RK_DATABASE_URL", "environment:RK_PROXY_URL"],
            [item["source"] for item in sending["violations"]],
        )

    def test_a_request_without_a_url_or_a_configuration_is_a_usage_error(self):
        self.assertEqual(EXIT_USAGE, run("proxy", "request", "--config", str(write(SCOPED))).returncode)
        self.assertEqual(EXIT_USAGE, run("proxy", "request", "http://app.example.com/").returncode)
        self.assertEqual(EXIT_USAGE, run("proxy").returncode)

    def test_a_capability_may_not_be_sent_anywhere_but_the_loopback_interface(self):
        # The refusal happens before the configuration is read and before any
        # connection is opened, because the endpoint decides where the one secret
        # this command holds is allowed to go.
        for endpoint, why in (
            ("http://proxy.example.net:8080", "not on this machine"),
            ("https://127.0.0.1:8080", "not plain HTTP"),
            ("127.0.0.1:8080", "not a URL at all"),
        ):
            with self.subTest(why):
                result = run(
                    "proxy",
                    "request",
                    "--config", str(write(SCOPED)),
                    "--url", "postgresql://rk2@127.0.0.1:1/rk2",
                    "--proxy", endpoint,
                    "http://app.example.com/",
                )

                self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
                self.assertEqual(
                    ["environment:RK_PROXY_URL"],
                    [item["source"] for item in json.loads(result.stdout)["violations"]],
                )

    def test_a_request_to_a_door_nobody_answers_at_reaches_no_database(self):
        # Port 1 on loopback is an address a capability may travel to and nothing
        # is listening on it. The order matters: the endpoint and the URL are
        # decided before a connection is opened, so this is still a refusal that
        # opened no Tool run and minted nothing.
        observed = observe(
            "proxy",
            "request",
            "--config", str(write(SCOPED.replace("requests = 100", "requests = 0"))),
            "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            "--proxy", "http://127.0.0.1:1",
            "http://app.example.com/",
        )

        self.assertEqual([], observed["events"])
        self.assertEqual(EXIT_INVALID_CONFIGURATION, observed["exit"])

    def test_a_url_this_proxy_cannot_carry_is_refused_before_the_database(self):
        # A URL that cannot be canonicalised has no scope answer at all, and an
        # https one with no trust root has no way to tell the door's certificate
        # from anybody else's. Both are the caller's to fix, and neither is worth
        # a connection: the refusal names the input to correct, and the https one
        # names the variable rather than the URL, because the URL is fine.
        for url, expected in (
            ("https://app.example.com/", "environment:RK_PROXY_CA_FILE"),
            ("ftp://app.example.com/", "argument:--url"),
            ("http://app..example.com/", "argument:--url"),
        ):
            with self.subTest(url):
                result = run(
                    "proxy",
                    "request",
                    "--config", str(write(SCOPED)),
                    "--url", "postgresql://rk2@127.0.0.1:1/rk2",
                    "--proxy", "http://127.0.0.1:8080",
                    url,
                )

                self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
                self.assertEqual(
                    [expected],
                    [item["source"] for item in json.loads(result.stdout)["violations"]],
                )

    def test_a_door_reports_the_certificate_an_agent_has_to_be_given(self):
        # The two flags are one arrangement: `--authority` is where the door
        # signs from, `--ca` is what the other side verifies against, and the
        # path that joins them is a fact of the report rather than something an
        # operator reconstructs. The database is unreachable here, which is after
        # the authority is made and is why the certificate is on the wire anyway.
        directory = scratch() / "authority"

        result = run(
            "proxy", "serve",
            "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            "--artifacts", str(scratch()),
            "--authority", str(directory),
            "--port", "0",
        )
        observed = json.loads(result.stdout)

        self.assertEqual(str(directory / "ca.pem"), observed["certificate"])
        self.assertIn("authority", [item["name"] for item in observed["assertions"]])
        self.assertTrue((directory / "ca.pem").exists())
        self.assertNotIn("PRIVATE KEY", result.stdout)

    def test_a_door_says_which_of_the_two_certificate_inputs_it_cannot_use(self):
        # Both refusals are the caller's to fix and neither is worth a
        # connection, and they name different inputs because they are different
        # mistakes: one is where the door signs, the other is what the runtime
        # believes.
        occupied = write("not a directory", "authority")
        junk = write("not a certificate", "ca.pem")

        serving = run(
            "proxy", "serve",
            "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            "--artifacts", str(scratch()),
            "--authority", str(occupied),
            "--port", "0",
        )
        sending = run(
            "proxy", "request",
            "--config", str(write(SCOPED)),
            "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            "--proxy", "http://127.0.0.1:1",
            "--ca", str(junk),
            "https://app.example.com/",
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, serving.returncode)
        self.assertEqual(
            ["argument:--authority"],
            [item["source"] for item in json.loads(serving.stdout)["violations"]],
        )
        self.assertEqual(EXIT_INVALID_CONFIGURATION, sending.returncode)
        self.assertEqual(
            ["argument:--ca"],
            [item["source"] for item in json.loads(sending.stdout)["violations"]],
        )

    def test_neither_connection_string_nor_capability_material_is_echoed_back(self):
        result = run(
            "proxy",
            "request",
            "--config", str(write(SCOPED)),
            "--url", "postgresql://rk2:s3cr3t-runtime@127.0.0.1:1/rk2",
            "--proxy", "http://127.0.0.1:1",
            "http://app.example.com/",
        )

        self.assertNotIn("s3cr3t-runtime", result.stdout)
        self.assertNotIn("s3cr3t-runtime", result.stderr)


class InterruptedCommandTest(unittest.TestCase):
    """A database that stops answering after the command has started.

    In process rather than through `run`, because the failure being tested is
    one no reachable server produces on demand: the operation is made to raise
    what a backend restart or a dropped idle socket raises.
    """

    def command(self, error: Exception) -> tuple[int, dict]:
        from unittest import mock

        from redkraken import cli

        with mock.patch.object(cli.migrate, "status", side_effect=error):
            with mock.patch("sys.stdout", new=io.StringIO()) as rendered:
                code = cli.main(["db", "status", "--url", "postgresql://rk2_migrate@127.0.0.1/rk2"])
        return code, json.loads(rendered.getvalue())

    def test_a_connection_lost_mid_command_is_reported_rather_than_raised(self):
        code, report = self.command(pg.ConnectionError_("127.0.0.1:5432/rk2 closed the connection"))

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, code)
        self.assertEqual("db status", report["command"])
        self.assertEqual(["database_unreachable"], [item["code"] for item in report["violations"]])
        self.assertIn("closed the connection", report["violations"][0]["detail"])

    def test_a_server_error_nobody_classified_is_reported_rather_than_raised(self):
        code, report = self.command(pg.DatabaseError({"C": "42501", "M": "permission denied"}))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, code)
        self.assertIn("permission denied", report["violations"][0]["detail"])


class ContainmentTest(unittest.TestCase):
    def test_diagnosis_creates_no_state_and_sends_no_traffic(self):
        source = write(VALID)

        observed = observe("doctor", "--config", str(source))

        self.assertEqual([], observed["events"])
        self.assertEqual(EXIT_OK, observed["exit"])
        self.assertEqual(["program.toml"], [entry.name for entry in source.parent.iterdir()])

    def test_refusal_creates_no_state_and_sends_no_traffic(self):
        observed = observe("doctor", "--config", str(write("schema_version = 4\n")))

        self.assertEqual([], observed["events"])
        self.assertEqual(EXIT_UNSUPPORTED_VERSION, observed["exit"])

    def test_no_module_is_loaded_from_a_nonproduction_tree(self):
        observed = observe("doctor", "--config", str(write(VALID)))

        outside = [
            name
            for name in observed["loaded"]
            if name and not Path(name).resolve().is_relative_to(SOURCE)
            and Path(name).resolve().is_relative_to(ROOT)
        ]
        self.assertEqual([], outside)

    def test_secret_bearing_references_never_reach_the_output(self):
        text = VALID.replace("slot://identity/member", "slot://identity/s3cr3t-sentinel")

        result = run("doctor", "--config", str(write(text)))

        self.assertEqual(EXIT_OK, result.returncode, result.stderr)
        self.assertNotIn("s3cr3t-sentinel", result.stdout)
        self.assertNotIn("s3cr3t-sentinel", result.stderr)

    def test_unparsable_configuration_is_refused_without_echoing_its_content(self):
        text = 'schema_version = 1\n[program]\nname = "acme"\ntoken "s3cr3t-sentinel"\n'

        result = run("doctor", "--config", str(write(text)))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        self.assertNotIn("s3cr3t-sentinel", result.stdout)
        self.assertNotIn("s3cr3t-sentinel", result.stderr)


if __name__ == "__main__":
    unittest.main()
