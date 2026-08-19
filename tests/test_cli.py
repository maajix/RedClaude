import argparse
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import redkraken
from redkraken import cli, evaluation, execution, migrate, operator, pg, verifier
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
    export,
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


def leaves(parser: argparse.ArgumentParser | None = None, path: str = "") -> dict:
    """Every command the surface offers, by the words that reach it.

    Read off the parser rather than listed here, because a list written by hand
    is a list that agrees with the surface on the day it was written. That means
    argparse's internals: `_actions` and `_SubParsersAction` are the only way to
    walk a parser tree, and a test that audits a surface has to walk it.
    """
    parser = parser if parser is not None else cli.build_parser()
    subcommands = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ]
    if not subcommands:
        return {path: parser}
    found = {}
    for action in subcommands:
        for name, child in action.choices.items():
            found.update(leaves(child, f"{path} {name}".strip()))
    return found


def flags(parser: argparse.ArgumentParser) -> set[str]:
    """Every long option one command accepts."""
    return {
        string
        for action in parser._actions
        for string in action.option_strings
        if string.startswith("--")
    }


def required(parser: argparse.ArgumentParser) -> set[str]:
    """Every long option one command refuses to run without."""
    return {
        string
        for action in parser._actions
        if action.required
        for string in action.option_strings
        if string.startswith("--")
    }


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

    def test_the_verb_answers_with_the_corpus_revision_behind_the_installation(self):
        """Ticket 59 criterion 2: a read that carries a revision and a digest.

        Two machines running the same version of the package can be running
        different databases, so the number that decides whether they agree is
        the corpus digest and not the version string.
        """
        result = run("version")
        migrations, refused = migrate.load()

        self.assertEqual(EXIT_OK, result.returncode, result.stderr)
        document = json.loads(result.stdout)
        self.assertEqual((), refused)
        self.assertEqual(redkraken.__version__, document["version"])
        self.assertEqual(migrate.revision(migrations), document["corpus_sha256"])
        self.assertEqual(len(migrations), document["corpus"])
        self.assertEqual(migrations[-1].identity, document["schema"])
        self.assertTrue(document["ok"])

    def test_both_spellings_of_the_question_report_one_version(self):
        """`--version` is for a person and `version` is for a script, and a
        machine that answered them differently would be two installations."""
        document = json.loads(run("version").stdout)

        self.assertEqual(run("--version").stdout.strip(), f"rk {document['version']}")
        self.assertEqual(cli.VERSION, document["command"])

    def test_the_first_command_an_operator_runs_touches_nothing(self):
        observed = observe("version")

        self.assertEqual([], observed["events"])
        self.assertEqual(EXIT_OK, observed["exit"])


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


class DecisionCommandTest(unittest.TestCase):
    """`rk decision sweep`, up to the point where a database is needed.

    The runtime's connection string, because the queue is the runtime's: the
    door holds `rk2_proxy`, which cannot reach a single one of these tables, and
    that is why the sweep is a command of its own rather than a thread inside
    the fence.
    """

    def test_the_sweep_reads_the_runtime_connection_string(self):
        result = run("decision", "sweep")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("decision sweep", report["command"])
        self.assertEqual(
            [("invalid_configuration", "environment:RK_DATABASE_URL")],
            [(item["code"], item["source"]) for item in report["violations"]],
        )

    def test_a_decision_command_without_an_operation_is_a_usage_error(self):
        result = run("decision")

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("usage: rk decision", result.stderr)

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        result = run("decision", "sweep", "--url", "postgresql://rk2@127.0.0.1:1/rk2")

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.returncode)
        self.assertEqual("decision sweep", json.loads(result.stdout)["command"])

    def test_a_sweep_that_reached_nothing_still_says_how_many_passes_it_made(self):
        # A sweeper that never ran and a sweeper with nothing to do write the
        # same document otherwise, and only one of them means the queue is being
        # tended.
        result = run("decision", "sweep", "--url", "postgresql://rk2@127.0.0.1:1/rk2")

        self.assertEqual(0, json.loads(result.stdout)["passes"])

    def test_the_connection_string_is_never_echoed_back(self):
        url = "postgresql://rk2:s3cr3t-sentinel@127.0.0.1:1/rk2"

        result = run("decision", "sweep", "--url", url)

        self.assertNotIn("s3cr3t-sentinel", result.stdout)
        self.assertNotIn("s3cr3t-sentinel", result.stderr)


class OperatorCommandTest(unittest.TestCase):
    """The five commands a person runs, up to the point where a database is needed.

    All five read `RK_HUMAN_URL` and nothing else. That is the ticket's fourth
    criterion as an operator meets it: the connection that answers a question or
    lifts a Halt is a role the runtime cannot become, so exporting the runtime's
    URL has to be a refusal naming the variable this one wanted rather than a
    command that quietly runs as the wrong role.
    """

    def test_every_operator_command_reads_the_operator_variable(self):
        naming = {
            ("decision", "list"): (),
            ("decision", "answer"): ("--program", "p", "D1", "--approve", "--reason", "x"),
            ("decision", "supersede"): ("--program", "p", "D1", "--reason", "x"),
            ("halt",): ("--program", "p", "--reason", "x"),
            ("resume",): ("--program", "p", "--reason", "x"),
        }
        observed = {}
        for command, rest in naming.items():
            report = json.loads(run(*command, *rest).stdout)
            observed[report["command"]] = report["violations"][0]["source"]

        self.assertEqual(
            {
                "decision list": "environment:RK_HUMAN_URL",
                "decision answer": "environment:RK_HUMAN_URL",
                "decision supersede": "environment:RK_HUMAN_URL",
                "halt": "environment:RK_HUMAN_URL",
                "resume": "environment:RK_HUMAN_URL",
            },
            observed,
        )

    def test_an_answer_without_a_verdict_is_a_usage_error(self):
        # Neither verdict is a default. An operator who typed neither has not
        # said what they decided, and the safe guess would be the one that ends
        # a Task nobody meant to end.
        result = run("decision", "answer", "--program", "p", "D1", "--reason", "x")

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("--approve", result.stderr)

    def test_a_verdict_cannot_be_both_at_once(self):
        result = run(
            "decision", "answer", "--program", "p", "D1",
            "--approve", "--deny", "--reason", "x",
        )

        self.assertEqual(EXIT_USAGE, result.returncode)

    def test_every_verb_that_changes_something_requires_a_reason(self):
        for command in (
            ("decision", "answer", "--program", "p", "D1", "--deny"),
            ("decision", "supersede", "--program", "p", "D1"),
            ("halt", "--program", "p"),
            ("resume", "--program", "p"),
        ):
            with self.subTest(command=command):
                result = run(*command)

                self.assertEqual(EXIT_USAGE, result.returncode)
                self.assertIn("--reason", result.stderr)

    def test_a_verb_that_names_no_program_is_a_usage_error(self):
        # Never defaulted to "the only one open": a machine running two
        # campaigns would have a Halt whose target depended on which of them
        # happened to be closed at the time.
        result = run("halt", "--reason", "x")

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("--program", result.stderr)

    def test_the_queue_may_be_asked_for_without_naming_a_program(self):
        # Reading is the one thing an operator does before they know which
        # Program is stopped.
        result = run("decision", "list", "--url", "postgresql://rk2@127.0.0.1:1/rk2")

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.returncode)
        self.assertEqual("decision list", json.loads(result.stdout)["command"])

    def test_the_connection_string_is_never_echoed_back(self):
        url = "postgresql://rk2:s3cr3t-sentinel@127.0.0.1:1/rk2"

        result = run("halt", "--program", "p", "--reason", "x", "--url", url)

        self.assertNotIn("s3cr3t-sentinel", result.stdout)
        self.assertNotIn("s3cr3t-sentinel", result.stderr)

    def test_the_reason_an_operator_wrote_is_not_echoed_into_a_refusal(self):
        # Criterion 6 as the CLI meets it: the words are for the decision record
        # and the report is a document other things read.
        result = run(
            "decision", "answer", "--program", "p", "D1", "--deny",
            "--reason", "s3cr3t-context-sentinel",
            "--url", "postgresql://rk2@127.0.0.1:1/rk2",
        )

        self.assertNotIn("s3cr3t-context-sentinel", result.stdout)
        self.assertNotIn("s3cr3t-context-sentinel", result.stderr)


class IdentityCommandTest(unittest.TestCase):
    """Identity provisioning is an explicit operator adapter, never a net tool input."""

    def test_provisioning_names_every_control_side_input_without_echoing_values(self):
        marker = "rk2-cli-credential-2fd3b1"
        material = scratch() / "identity.json"
        material.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "origins": [
                        {
                            "url": "https://app.example.com/",
                            "headers": [
                                {"name": "Authorization", "value": f"Bearer {marker}"}
                            ],
                            "cookies": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = run(
            "identity",
            "provision",
            "--config", str(write(VALID)),
            "--identity", "member",
            "--from", str(material),
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        rendered = json.loads(result.stdout)
        self.assertEqual("identity provision", rendered["command"])
        self.assertEqual(
            ["environment:RK_ARTIFACT_KEY", "environment:RK_DATABASE_URL"],
            sorted(item["source"] for item in rendered["violations"]),
        )
        self.assertNotIn(marker, result.stdout)
        self.assertNotIn(marker, result.stderr)

    def test_the_credential_document_and_identity_label_are_required(self):
        missing_material = run(
            "identity", "provision", "--config", str(write(VALID)), "--identity", "member"
        )
        missing_identity = run(
            "identity",
            "provision",
            "--config", str(write(VALID)),
            "--from", str(write("{}", "identity.json")),
        )

        self.assertEqual(EXIT_USAGE, missing_material.returncode)
        self.assertEqual(EXIT_USAGE, missing_identity.returncode)


class HeaderCommandTest(unittest.TestCase):
    """`rk header provision`, which is the same adapter over a shorter secret."""

    def test_provisioning_names_every_control_side_input_without_echoing_the_value(self):
        marker = "rk2-cli-bounty-identifier-6b1f04"
        value = scratch() / "bounty-id.txt"
        value.write_text(marker, encoding="utf-8")

        result = run(
            "header",
            "provision",
            "--config", str(write(VALID)),
            "--header", "X-Bounty-Id",
            "--from", str(value),
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        rendered = json.loads(result.stdout)
        self.assertEqual("header provision", rendered["command"])
        self.assertEqual(
            ["environment:RK_ARTIFACT_KEY", "environment:RK_DATABASE_URL"],
            sorted(item["source"] for item in rendered["violations"]),
        )
        self.assertNotIn(marker, result.stdout)
        self.assertNotIn(marker, result.stderr)

    def test_the_value_file_and_the_header_name_are_required(self):
        missing_value = run(
            "header", "provision", "--config", str(write(VALID)), "--header", "X-Bounty-Id"
        )
        missing_name = run(
            "header",
            "provision",
            "--config", str(write(VALID)),
            "--from", str(write("x", "bounty-id.txt")),
        )

        self.assertEqual(EXIT_USAGE, missing_value.returncode)
        self.assertEqual(EXIT_USAGE, missing_name.returncode)


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


class ToolCommandTest(unittest.TestCase):
    """`rk tool run`, up to the point where a database and an engine are needed.

    Four inputs, and the fourth is the image. It is named the way the store is
    named -- a flag, or a variable behind it, and a refusal when neither -- for
    the reason the Agent boundary gives about its own: a default would be
    whatever the operator's machine happened to have, and which build of a tool
    ran is half of what its output means.
    """

    def arguments(self, *extra: str) -> tuple[str, ...]:
        return (
            "tool", "run",
            "--config", str(write(VALID)),
            "--agent-run", "AR1",
            "--tool", "jq",
            *extra,
        )

    def test_the_image_and_the_store_are_named_alongside_the_connection(self):
        result = run(*self.arguments())

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("tool run", report["command"])
        self.assertEqual(
            [
                "environment:RK_ARTIFACT_ROOT",
                "environment:RK_DATABASE_URL",
                "environment:RK_TOOL_IMAGE",
            ],
            sorted(item["source"] for item in report["violations"]),
        )

    def test_a_run_without_an_agent_run_or_a_tool_is_a_usage_error(self):
        for missing in ("--agent-run", "--tool"):
            with self.subTest(missing):
                given = [item for item in self.arguments() if item != missing]
                result = run(*[item for item in given if item not in ("AR1", "jq")])

                self.assertEqual(EXIT_USAGE, result.returncode)
                self.assertIn(missing, result.stderr)

    def test_an_argument_that_is_not_a_name_and_a_value_is_refused_by_name(self):
        # The registry decides which names exist and what a value may look like.
        # This is the one thing it cannot decide, because a string with no `=` in
        # it does not reach the registry as an argument at all. It is refused the
        # way every other malformed value here is -- a report on stdout naming the
        # flag at fault -- rather than as a usage error, which is what argparse
        # answers when a flag is missing or unknown, before any value is read.
        result = run(
            *self.arguments(
                "--argument", "filter",
                "--artifacts", str(scratch()),
                "--image", "rk-tools:selftest",
                "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            )
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual(
            ["argument:--argument"],
            [item["source"] for item in report["violations"]],
        )
        self.assertIn("filter is not a name=value pair", result.stdout)

    def test_the_same_argument_twice_keeps_neither_value(self):
        result = run(
            *self.arguments(
                "--argument", "filter=.host",
                "--argument", "filter=.ports",
                "--artifacts", str(scratch()),
                "--image", "rk-tools:selftest",
                "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            )
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        self.assertIn("given more than once", result.stdout)

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        result = run(
            *self.arguments(
                "--argument", "filter=.host",
                "--artifacts", str(scratch()),
                "--image", "rk-tools:selftest",
                "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            )
        )

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.returncode)
        self.assertEqual("tool run", json.loads(result.stdout)["command"])

    def test_the_connection_string_is_never_echoed_back(self):
        result = run(
            *self.arguments(
                "--artifacts", str(scratch()),
                "--image", "rk-tools:selftest",
                "--url", "postgresql://rk2:s3cr3t-runtime@127.0.0.1:1/rk2",
            )
        )

        self.assertNotIn("s3cr3t-runtime", result.stdout)
        self.assertNotIn("s3cr3t-runtime", result.stderr)

    def test_a_refused_configuration_reaches_no_engine_and_writes_nothing(self):
        source = write(VALID.replace("requests = 5000", "requests = 0"))
        root = scratch() / "artifacts"

        observed = observe(
            "tool", "run",
            "--config", str(source),
            "--agent-run", "AR1",
            "--tool", "jq",
            "--argument", "filter=.host",
            "--artifacts", str(root),
            "--image", "rk-tools:selftest",
            "--url", "postgresql://rk2@127.0.0.1:1/rk2",
        )

        self.assertEqual([], observed["events"])
        self.assertEqual(EXIT_INVALID_CONFIGURATION, observed["exit"])
        self.assertFalse(root.exists())


class ReplayCommandTest(unittest.TestCase):
    """`rk test replay`, up to the point where a database and a door are needed.

    A replay names two things by label and nothing by value: which agent run
    performs it and which Test it performs. The specification is already stored
    and already digested, so there is no plan file, no method and no url on this
    command line -- an operator who could pass one could perform a request the
    Test never stated, under a Receipt the Test would then be credited with.

    The door is named the way `rk proxy request` names it, because it is the same
    fence and the same secret travelling to it.
    """

    def arguments(self, *extra: str) -> tuple[str, ...]:
        return (
            "test", "replay",
            "--config", str(write(SCOPED)),
            "--agent-run", "AR1",
            "--test", "T1",
            *extra,
        )

    def test_the_door_is_named_alongside_the_connection(self):
        result = run(*self.arguments())

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("test replay", report["command"])
        self.assertEqual(
            ["environment:RK_DATABASE_URL", "environment:RK_PROXY_URL"],
            [item["source"] for item in report["violations"]],
        )

    def test_a_replay_without_a_run_a_test_or_a_configuration_is_a_usage_error(self):
        for missing, value in (("--agent-run", "AR1"), ("--test", "T1"), ("--config", None)):
            with self.subTest(missing):
                given = [
                    item
                    for item in self.arguments()
                    if item != missing and item != value and not item.endswith(".toml")
                ]

                result = run(*given)

                self.assertEqual(EXIT_USAGE, result.returncode)
                self.assertIn(missing, result.stderr)
        self.assertEqual(EXIT_USAGE, run("test").returncode)

    def test_a_capability_may_not_be_sent_anywhere_but_the_loopback_interface(self):
        # The same refusal `rk proxy request` makes, for the same reason: this
        # command holds one plaintext capability and the endpoint decides where
        # it is allowed to go. Refused before the configuration is read.
        for endpoint, why in (
            ("http://proxy.example.net:8080", "not on this machine"),
            ("https://127.0.0.1:8080", "not plain HTTP"),
            ("127.0.0.1:8080", "not a URL at all"),
        ):
            with self.subTest(why):
                result = run(
                    *self.arguments(
                        "--url", "postgresql://rk2@127.0.0.1:1/rk2",
                        "--proxy", endpoint,
                    )
                )

                self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
                self.assertEqual(
                    ["environment:RK_PROXY_URL"],
                    [item["source"] for item in json.loads(result.stdout)["violations"]],
                )

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        result = run(
            *self.arguments(
                "--url", "postgresql://rk2@127.0.0.1:1/rk2",
                "--proxy", "http://127.0.0.1:8080",
            )
        )

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.returncode)
        self.assertEqual("test replay", json.loads(result.stdout)["command"])

    def test_the_connection_string_is_never_echoed_back(self):
        result = run(
            *self.arguments(
                "--url", "postgresql://rk2:s3cr3t-runtime@127.0.0.1:1/rk2",
                "--proxy", "http://127.0.0.1:8080",
            )
        )

        self.assertNotIn("s3cr3t-runtime", result.stdout)
        self.assertNotIn("s3cr3t-runtime", result.stderr)

    def test_a_refused_configuration_reaches_no_door_and_opens_no_connection(self):
        observed = observe(
            "test", "replay",
            "--config", str(write(SCOPED.replace("requests = 100", "requests = 0"))),
            "--agent-run", "AR1",
            "--test", "T1",
            "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            "--proxy", "http://127.0.0.1:1",
        )

        self.assertEqual([], observed["events"])
        self.assertEqual(EXIT_INVALID_CONFIGURATION, observed["exit"])


class EvidenceCommandTest(unittest.TestCase):
    """`rk evidence`, and the asymmetry between its two operations.

    `export` needs a connection and a store, because a bundle carries rows and
    bytes. `verify` needs a directory. That difference is the whole argument of
    the ticket -- a check only the party being checked can run is not a check --
    so it is asserted here on the command line rather than left to the module.
    """

    def exporting(self, *extra: str) -> tuple[str, ...]:
        return (
            "evidence", "export",
            "--config", str(write(VALID)),
            "--subject", "finding",
            "--label", "F-0007",
            "--template", "hackerone-v1",
            "--out", str(scratch() / "bundle"),
            *extra,
        )

    def bundle(self) -> Path:
        """One well-formed bundle on disk, written the way the exporter writes."""
        where = scratch() / "bundle"
        where.mkdir()
        (where / "report.md").write_bytes(b"# F-0007\n")
        shipped = Path(verifier.__file__).read_bytes()
        (where / verifier.VERIFIER).write_bytes(shipped)
        document = {
            "schema": verifier.SCHEMA,
            "required": ["report.md", verifier.VERIFIER],
            "files": [
                {"path": "report.md", "bytes": 9, "sha256": verifier.digest(b"# F-0007\n")},
                {
                    "path": verifier.VERIFIER,
                    "bytes": len(shipped),
                    "sha256": verifier.digest(shipped),
                },
            ],
            "redaction_rules": [],
        }
        (where / verifier.MANIFEST).write_text(
            json.dumps(
                document
                | {
                    "digest": verifier.manifest_digest(document),
                    verifier.PACKAGING: {"exported_at": "2026-08-16T00:00:00Z"},
                },
                sort_keys=True,
            )
        )
        return where

    def test_the_store_is_named_alongside_the_connection_when_neither_is_set(self):
        result = run(*self.exporting())

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("evidence export", report["command"])
        self.assertEqual(
            ["environment:RK_ARTIFACT_ROOT", "environment:RK_DATABASE_URL"],
            [item["source"] for item in report["violations"]],
        )

    def test_an_export_missing_any_of_what_it_packs_is_a_usage_error(self):
        for missing in ("--config", "--subject", "--label", "--template", "--out"):
            with self.subTest(missing):
                given = list(self.exporting())
                at = given.index(missing)

                result = run(*given[:at], *given[at + 2:])

                self.assertEqual(EXIT_USAGE, result.returncode)
                self.assertIn(missing, result.stderr)
        self.assertEqual(EXIT_USAGE, run("evidence").returncode)

    def test_there_is_no_subject_beyond_the_two_that_can_be_rendered(self):
        """`--subject` decides which Receipts a bundle is about, and the two
        gatherers are named in SQL. A third value would reach a `KeyError`
        rather than a refusal."""
        result = run(*self.exporting()[:4], "--subject", "program", "--label", "P1")

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("--subject", result.stderr)

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        result = run(
            *self.exporting(
                "--url", "postgresql://rk2@127.0.0.1:1/rk2",
                "--artifacts", str(scratch()),
            )
        )

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.returncode)
        self.assertEqual("evidence export", json.loads(result.stdout)["command"])

    def test_the_connection_string_is_never_echoed_back(self):
        result = run(
            *self.exporting(
                "--url", "postgresql://rk2:s3cr3t-runtime@127.0.0.1:1/rk2",
                "--artifacts", str(scratch()),
            )
        )

        self.assertNotIn("s3cr3t-runtime", result.stdout)
        self.assertNotIn("s3cr3t-runtime", result.stderr)

    def test_a_destination_that_already_holds_a_bundle_is_refused(self):
        result = run(
            *self.exporting()[:-1],
            str(self.bundle()),
            "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            "--artifacts", str(scratch()),
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        self.assertEqual(
            ["argument:--out"],
            [item["source"] for item in json.loads(result.stdout)["violations"]],
        )

    def test_a_bundle_is_checked_with_no_connection_string_and_no_configuration(self):
        result = run("evidence", "verify", str(self.bundle()))

        self.assertEqual(EXIT_OK, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("evidence verify", report["command"])
        self.assertTrue(report["bundle"]["verified"])

    def test_a_bundle_that_was_edited_is_refused_by_the_same_command(self):
        where = self.bundle()
        (where / "report.md").write_bytes(b"# F-0008\n")

        result = run("evidence", "verify", str(where))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        self.assertEqual(
            ["file_hash_mismatch"],
            json.loads(result.stdout)["bundle"]["problems"],
        )

    def test_verifying_a_bundle_reaches_nothing_and_changes_nothing(self):
        """The property that makes the shipped copy and this subcommand the same
        check. A verify that opened a socket or wrote a file would be doing
        something a recipient's copy could not do."""
        observed = observe("evidence", "verify", str(self.bundle()))

        self.assertEqual([], observed["events"])
        self.assertEqual(EXIT_OK, observed["exit"])

    def test_the_copy_in_the_bundle_runs_under_a_python_that_has_no_package(self):
        """The whole argument of the ticket, run rather than read.

        `test_verifier` asks the module's source what it imports. This runs the
        copy a recipient actually receives, from a directory that is not this
        repository, under an interpreter told nothing about `redkraken` -- and
        holds the answer against what `rk evidence verify` said about the same
        bundle. A recipient who cannot reproduce that answer has a report and
        not evidence.
        """
        where = self.bundle()

        theirs = subprocess.run(
            [sys.executable, str(where / verifier.VERIFIER), str(where)],
            cwd=str(where.parent),
            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            capture_output=True,
            check=False,
        )
        ours = run("evidence", "verify", str(where))

        self.assertEqual(EXIT_OK, theirs.returncode, theirs.stderr)
        self.assertEqual(EXIT_OK, ours.returncode, ours.stderr)
        answer = json.loads(theirs.stdout)
        self.assertTrue(answer["ok"])
        self.assertEqual(json.loads(ours.stdout)["bundle"]["files"], answer["files"])

    def test_verify_takes_one_directory_and_no_flags(self):
        self.assertEqual(EXIT_USAGE, run("evidence", "verify").returncode)
        self.assertEqual(
            EXIT_USAGE, run("evidence", "verify", str(self.bundle()), "--config", "x").returncode
        )


class ImportCommandTest(unittest.TestCase):
    """`rk import`, up to the point where a database is needed.

    Criterion 1 is a property of this command line and of nothing else: "import
    accepts only an explicit operator-selected export ... and never crawls live
    engagement directories implicitly". There is no default for `--from`, no
    environment variable behind it and no configuration key that supplies one,
    so the cases below are what an operator who did not name a directory gets.
    """

    def importing(self, *extra: str, source: Path | None = None) -> tuple[str, ...]:
        return (
            "import",
            "--config", str(write(VALID)),
            "--from", str(source or export()),
            *extra,
        )

    def test_the_store_is_named_alongside_the_connection_when_neither_is_set(self):
        result = run(*self.importing())

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("import", report["command"])
        self.assertEqual(
            ["environment:RK_ARTIFACT_ROOT", "environment:RK_DATABASE_URL"],
            [item["source"] for item in report["violations"]],
        )

    def test_an_export_is_named_or_there_is_no_import(self):
        for missing in ("--config", "--from"):
            with self.subTest(missing):
                given = list(self.importing())
                at = given.index(missing)

                result = run(*given[:at], *given[at + 2:])

                self.assertEqual(EXIT_USAGE, result.returncode)
                self.assertIn(missing, result.stderr)

    def test_nothing_supplies_an_export_directory_that_was_not_typed(self):
        """The other half of the same criterion. `--from` having no default is
        only a refusal if no environment variable stands in for it either."""
        result = subprocess.run(
            [sys.executable, "-m", "redkraken", "import", "--config", str(write(VALID))],
            cwd=str(ROOT),
            env=environment()
            | {
                "RK_IMPORT_FROM": str(export()),
                "RK_EXPORT": str(export()),
                "RK_ARTIFACT_ROOT": str(scratch()),
                "RK_DATABASE_URL": "postgresql://rk2@127.0.0.1:1/rk2",
            },
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("--from", result.stderr)

    def test_a_directory_that_is_not_an_export_is_refused_before_a_connection(self):
        result = run(
            *self.importing(
                "--url", "postgresql://rk2@127.0.0.1:1/rk2",
                "--artifacts", str(scratch()),
                source=scratch(),
            )
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        violations = json.loads(result.stdout)["violations"]
        self.assertEqual(["argument:--from"], [item["source"] for item in violations])
        self.assertIn("manifest.json", violations[0]["detail"])

    def test_an_export_taken_from_another_program_is_refused_before_a_connection(self):
        """Criterion 5's isolation at the coarse end, and the cheapest place to
        see it: the manifest names the engagement, the configuration names the
        Program, and an import across the two is the whole cross-Program
        failure. It is asked before the connection because a refusal that needed
        a database would not be available to an operator checking a file."""
        result = run(
            *self.importing(
                "--url", "postgresql://rk2@127.0.0.1:1/rk2",
                "--artifacts", str(scratch()),
                source=export(program="another-engagement"),
            )
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        violations = json.loads(result.stdout)["violations"]
        self.assertEqual(["argument:--from"], [item["source"] for item in violations])
        self.assertIn("another-engagement", violations[0]["detail"])
        self.assertIn("acme-web", violations[0]["detail"])

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        result = run(*self.importing("--url", "postgresql://rk2@127.0.0.1:1/rk2",
                                     "--artifacts", str(scratch())))

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.returncode)
        self.assertEqual("import", json.loads(result.stdout)["command"])

    def test_the_connection_string_is_never_echoed_back(self):
        result = run(
            *self.importing(
                "--url", "postgresql://rk2:s3cr3t-runtime@127.0.0.1:1/rk2",
                "--artifacts", str(scratch()),
            )
        )

        self.assertNotIn("s3cr3t-runtime", result.stdout)
        self.assertNotIn("s3cr3t-runtime", result.stderr)


class PlaybookCommandTest(unittest.TestCase):
    """`rk playbook evaluate`, up to the point where a database is needed.

    Three inputs and no configuration file, which is the shape of the thing: an
    evaluation writes the Program documents it runs rather than being handed
    one. An operator who could pass a configuration here could grade a Playbook
    against a target of their own choosing and file the result as a test run.

    The fixture is named and never described, for the same reason. Ground truth,
    class binding and subject come out of the corpus the database digested, so
    the only thing this command line can decide is which fixture -- not what it
    is supposed to prove.
    """

    #: Both in the corpora the database digests -- `src/redkraken/playbooks/`
    #: and `src/redkraken/fixtures/` -- so the refusals below are about the
    #: connection and not about either name.
    PLAYBOOK = "playbooks/object-ownership/playbook.md"
    FIXTURE = "object-ownership-pair"

    def arguments(self, *extra: str) -> tuple[str, ...]:
        return (
            "playbook", "evaluate",
            "--playbook", self.PLAYBOOK,
            "--fixture", self.FIXTURE,
            "--workspace", str(scratch()),
            *extra,
        )

    def test_the_store_is_the_only_thing_named_by_the_environment(self):
        result = run(*self.arguments())

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("playbook evaluate", report["command"])
        self.assertEqual(
            ["environment:RK_DATABASE_URL"],
            [item["source"] for item in report["violations"]],
        )

    def test_an_evaluation_without_a_playbook_a_fixture_or_a_workspace_is_a_usage_error(self):
        for missing, value in (
            ("--playbook", self.PLAYBOOK),
            ("--fixture", self.FIXTURE),
            ("--workspace", None),
        ):
            with self.subTest(missing):
                given = [
                    item
                    for item in self.arguments()
                    if item != missing and item != value and not item.startswith("/")
                ]

                result = run(*given)

                self.assertEqual(EXIT_USAGE, result.returncode)
                self.assertIn(missing, result.stderr)
        self.assertEqual(EXIT_USAGE, run("playbook").returncode)

    def test_a_fixture_outside_the_corpus_is_refused_before_a_connection_is_opened(self):
        # The corpus is compiled into this process, so the name can be answered
        # without the database -- and is, because an evaluation that connected
        # first would hold a runtime connection open while deciding it had
        # nothing to grade.
        observed = observe(
            *self.arguments(
                "--fixture", "the-one-that-proves-my-playbook",
                "--url", "postgresql://rk2@127.0.0.1:1/rk2",
            )
        )

        self.assertEqual([], observed["events"])
        self.assertEqual(EXIT_INVALID_CONFIGURATION, observed["exit"])

    def test_the_same_facts_are_answered_on_a_path_that_files_nothing(self):
        result = run(*self.arguments("--url", "postgresql://rk2@127.0.0.1:1/rk2"))

        report = json.loads(result.stdout)
        self.assertEqual(
            ["fixture", "playbook", "repeats", "route", "runs", "verdict"],
            sorted(set(report) & set(evaluation.FACTS)),
        )
        self.assertEqual([], report["runs"])
        self.assertIsNone(report["verdict"])

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        result = run(*self.arguments("--url", "postgresql://rk2@127.0.0.1:1/rk2"))

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.returncode)
        self.assertEqual("playbook evaluate", json.loads(result.stdout)["command"])

    def test_the_connection_string_is_never_echoed_back(self):
        result = run(
            *self.arguments("--url", "postgresql://rk2:s3cr3t-runtime@127.0.0.1:1/rk2")
        )

        self.assertNotIn("s3cr3t-runtime", result.stdout)
        self.assertNotIn("s3cr3t-runtime", result.stderr)


class PlaybookCostCommandTest(unittest.TestCase):
    """`rk playbook cost`: what the corpus campaign costs, before it is started.

    Ticket 84 wants the cost stated before the run, so this takes no argument at
    all beyond the store it reads: the number is a property of the corpus the
    database digested and the policy it carries, and an operator who could pass
    a repeat count or a Playbook list could state a cost the campaign then does
    not honour.
    """

    def test_the_store_is_the_only_thing_named_by_the_environment(self):
        result = run("playbook", "cost")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("playbook cost", report["command"])
        self.assertEqual(
            ["environment:RK_DATABASE_URL"],
            [item["source"] for item in report["violations"]],
        )

    def test_the_same_facts_are_answered_on_a_path_that_counts_nothing(self):
        result = run("playbook", "cost", "--url", "postgresql://rk2@127.0.0.1:1/rk2")

        report = json.loads(result.stdout)
        self.assertEqual(
            ["envelope_tokens", "playbooks", "programs", "repeats", "route", "tokens"],
            sorted(set(report) & set(evaluation.COST_FACTS)),
        )
        self.assertEqual([], report["playbooks"])
        self.assertEqual(0, report["programs"])
        self.assertEqual(0, report["tokens"])

    def test_a_database_nobody_answers_at_is_its_own_class(self):
        result = run("playbook", "cost", "--url", "postgresql://rk2@127.0.0.1:1/rk2")

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, result.returncode)
        self.assertEqual("playbook cost", json.loads(result.stdout)["command"])

    def test_the_connection_string_is_never_echoed_back(self):
        result = run(
            "playbook", "cost", "--url", "postgresql://rk2:s3cr3t-runtime@127.0.0.1:1/rk2"
        )

        self.assertNotIn("s3cr3t-runtime", result.stdout)
        self.assertNotIn("s3cr3t-runtime", result.stderr)

    def test_a_boundary_described_in_part_is_refused_before_the_store_is_read(self):
        """The half-described boundary `_slice` refuses, asked of the command
        that opens no Program: a cost stated for the door route on a machine
        that cannot reach the door is a cost for a campaign that will not run."""
        result = subprocess.run(
            [sys.executable, "-m", "redkraken", "playbook", "cost"],
            cwd=str(ROOT),
            env={**environment(), execution.IMAGE: "rk2-agent:test"},
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual("playbook cost", report["command"])
        self.assertEqual(
            ["environment:RK_AGENT_NETWORK"],
            [item["source"] for item in report["violations"]],
        )


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


class OperatorSurfaceTest(unittest.TestCase):
    """Ticket 59: the command surface, audited as a surface.

    Every other case in this file asks one command whether it does its job. This
    asks the whole set the questions that are only answerable about the set: that
    each area the ticket names has a verb, that the shapes an operation must not
    have are absent everywhere rather than in the commands somebody remembered,
    and that the two connections stay two -- the operator's verbs are exactly the
    ones held as a person, and nothing a model reaches names a Program.

    Read off `build_parser` rather than from a list, so a verb added later is
    audited by being added.
    """

    #: Each area the ticket's first criterion names, and the verbs that cover it.
    #: Spelled out because the criterion is a list of areas and an area with no
    #: verb is the failure it is written to catch.
    AREAS = {
        "version": ("version",),
        "doctor": ("doctor",),
        "migrate": ("db migrate",),
        "run/resume": ("run", "resume"),
        "Program lifecycle": ("run", "scope", "halt", "resume"),
        "compact/full reads": ("state",),
        "Halt/clear": ("halt", "resume"),
        "pending decisions": (
            "decision sweep", "decision list", "decision answer", "decision supersede",
        ),
        "integrity": ("db verify", "artifact audit", "evidence verify"),
        "import": ("import",),
        "validation": ("finding validate",),
        "report": ("report finding", "report chain", "finding report", "finding clear-gate"),
        "evidence export": ("evidence export",),
    }

    #: The shapes criterion 4 forbids, as the flags they would arrive as. A
    #: generic operation is generic in its argument: `--sql` and `--query` are
    #: raw SQL, `--patch` and `--set` are an arbitrary edit, the credential three
    #: are a secret by value rather than by `slot://` reference, and `--receipt`
    #: is a hand-written record of an exchange that never happened.
    FORBIDDEN = (
        "--sql", "--query", "--patch", "--set", "--where",
        "--password", "--secret", "--token", "--credential",
        "--receipt", "--exec", "--eval",
    )

    #: Every flag the surface takes, as it stands. A list of names to avoid can
    #: only catch the shapes somebody thought of, and criterion 4 is a claim
    #: about all of them -- so the set itself is pinned, and a flag added later
    #: fails this until it is written down. What the failure asks for is a
    #: reading: is the new argument a value this command needs, or a way to say
    #: something the database was supposed to decide.
    SURFACE = (
        "--accept-change", "--action", "--agent-run", "--approve", "--argument",
        "--artifacts", "--at", "--authority", "--authorize", "--bytes", "--ca",
        "--callback", "--channel", "--closed", "--config", "--console-url",
        "--content-sha256", "--content-type", "--correlator", "--database", "--deny",
        "--discovery", "--egress", "--every", "--finding", "--fixture", "--for",
        "--from", "--gate", "--grant-hours", "--header", "--help", "--host",
        "--identity", "--image", "--impact", "--into", "--key", "--kind", "--label",
        "--limit", "--method", "--narrative", "--offset", "--out", "--panel", "--path",
        "--peer", "--plan", "--playbook", "--port", "--program", "--proxy", "--reason",
        "--record", "--redacted", "--rendering", "--state-url", "--subject",
        "--subtree", "--template", "--test", "--test-run", "--timeout", "--to",
        "--tool", "--tool-run", "--tunnel", "--url", "--wire", "--workspace",
    )

    @classmethod
    def setUpClass(cls):
        cls.commands = leaves()
        cls.operator_verbs = {
            operator.LIST, operator.ANSWER, operator.SUPERSEDE,
            operator.HALT, operator.RESUME, operator.REPORT, operator.CLEAR,
        }

    def test_every_area_the_ticket_names_has_a_verb_that_covers_it(self):
        for area, verbs in self.AREAS.items():
            with self.subTest(area):
                self.assertEqual([], [verb for verb in verbs if verb not in self.commands])

    def test_the_operator_verbs_are_exactly_the_ones_held_as_a_person(self):
        """Criterion 5's "human-only", asked of the surface instead of the database.

        `rk2_human` is the only role the control verbs are granted to, so a verb
        wired to any other connection string is a verb that cannot work -- and a
        verb on that connection that is not one of the seven would be a route to
        the operator's role from something that is not the operator's console.
        """
        self.assertEqual(
            self.operator_verbs,
            {
                name
                for name, parser in self.commands.items()
                if parser.get_default("url_source") is cli.CONSOLE
            },
        )

        # And the one command that holds the operator's connection without
        # being one of the verbs. 60's console renders those same seven as
        # forms and calls the same functions, so it is given the connection they
        # run on -- under a flag of its own, because its reads are the
        # runtime's and a single URL doing both would run them as the operator.
        # A second name here would be a second process that can lift a Halt.
        self.assertEqual(
            {"ui serve"},
            {
                name
                for name, parser in self.commands.items()
                if cli.OPERATOR.flag in flags(parser)
            },
        )

    def test_a_program_is_named_only_where_a_person_names_it(self):
        """Criterion 4's last clause. Everything a model reaches is bound to one
        Program by `rk2.program_id` and by the configuration it was started
        under; a selector argument would let a compromised run pick another."""
        self.assertEqual(
            self.operator_verbs,
            {name for name, parser in self.commands.items() if "--program" in flags(parser)},
        )

    def test_no_command_takes_sql_a_patch_or_a_credential_by_value(self):
        for name, parser in self.commands.items():
            with self.subTest(name):
                self.assertEqual(
                    [], sorted(flags(parser) & set(self.FORBIDDEN))
                )

    def test_the_surface_takes_the_arguments_it_is_written_down_as_taking(self):
        """The same criterion as a closed question rather than an open one.

        The list above says which shapes are forbidden, which is only ever the
        ones somebody thought to forbid: `--filter` and `--json` and `--expr`
        are all a query language arriving under a name nobody wrote down. So
        this asks the other way round -- these are the arguments the surface
        takes -- and the next flag is a line in this test before it is a flag.
        """
        taken = set()
        for parser in self.commands.values():
            taken |= flags(parser)

        self.assertEqual(sorted(self.SURFACE), sorted(taken))

    def test_every_operator_mutation_carries_the_sentence_behind_it(self):
        """Criterion 3 where the risk is a decision rather than a resource.

        The reason is required and not defaulted, because these six are the
        writes an audit reads afterwards, and a reason argparse supplied would be
        a record of nobody's judgement.
        """
        for name in sorted(self.operator_verbs - {operator.LIST}):
            with self.subTest(name):
                self.assertIn("--reason", required(self.commands[name]))
                self.assertIn("--program", required(self.commands[name]))

    def test_the_mutations_that_can_undo_a_guarantee_ask_before_they_do(self):
        """Criterion 3 where the risk is a resource. Each of these is a rule of
        the harness suspended on purpose, so each says so in its own word rather
        than happening because a command was run twice."""
        for name, word in (
            ("run", "--accept-change"),
            ("artifact open", "--authorize"),
            ("decision answer", "--grant-hours"),
            (operator.REPORT, "--content-sha256"),
        ):
            with self.subTest(name):
                self.assertIn(word, flags(self.commands[name]))

        # And the one of the four that is not optional. `reported` is terminal in
        # `transition_rules` and a clearance cannot be withdrawn, so there is no
        # step after this one to notice at -- which makes an unasked-for
        # confirmation the wrong shape. The digest is required, and it is the
        # digest rather than a word because "are you sure" can be answered
        # without having read anything.
        self.assertIn("--content-sha256", required(self.commands[operator.REPORT]))

    def test_every_command_has_a_handler_and_help_that_names_it(self):
        """Criterion 6, over the whole surface: a command whose help does not
        print is a command an operator cannot learn from the terminal."""
        for name, parser in self.commands.items():
            with self.subTest(name):
                self.assertTrue(callable(parser.get_default("run")))
                self.assertTrue(parser.format_help().startswith(f"usage: rk {name}"))

    def test_a_command_missing_what_it_needs_is_a_usage_error(self):
        result = run("finding", "report")

        self.assertEqual(EXIT_USAGE, result.returncode)
        self.assertIn("usage: rk finding report", result.stderr)


if __name__ == "__main__":
    unittest.main()
