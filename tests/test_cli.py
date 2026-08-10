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
