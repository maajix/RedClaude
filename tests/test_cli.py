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
from tests.fixtures import VALID, scratch, write


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
