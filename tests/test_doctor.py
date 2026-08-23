import contextlib
import hashlib
import importlib.metadata
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from redkraken import doctor, execution, isolation, playbook, proxy
from redkraken.doctor import Requirements
from redkraken.outcome import (
    EXIT_BUILD_MISMATCH,
    EXIT_DATABASE_UNREACHABLE,
    EXIT_INVALID_CONFIGURATION,
    EXIT_INVALID_CORPUS,
    EXIT_MISSING_DEPENDENCY,
    EXIT_OK,
    EXIT_UNSUPPORTED_VERSION,
    Ledger,
)
from tests.fixtures import VALID, scratch, write


#: The token the setup wizard installs, as a sentinel no assertion here prints.
#: Ticket 146: what a diagnosis may report about a setup token is the path, the
#: property that failed and the remedy, and never the value.
SENTINEL = "RK-SYNTHETIC-SETUP-TOKEN-2f7c"


def token_file(value: str = SENTINEL, *, mode: int = 0o600) -> Path:
    """A setup token installed the way `tools/setup-agent-oauth.sh` installs one."""
    directory = scratch() / "redkraken"
    directory.mkdir(mode=0o700)
    path = directory / "claude-oauth-token"
    path.write_text(value, encoding="utf-8")
    path.chmod(mode)
    return path


@contextlib.contextmanager
def described(token: Path | None = None, **engine):
    """A machine describing a full boundary and a trust root that is current.

    The certificate is a file rather than a certificate: what `doctor` asks of
    it is whether it exists and whether `tls.spent` says it is finished, and
    minting a real one to answer the second question would make every boundary
    test wait on `openssl`. The `isolation` calls each test wants stubbed are
    passed by name, because the ones it does not stub would inspect containers
    that do not exist on the machine running the suite.

    A boundary comes with a setup token, because since ticket 146 that is what
    a child authenticates with: a machine describing one and holding no token is
    a machine no run starts on, which is a case rather than the default.
    """
    certificate = scratch() / "ca.pem"
    certificate.write_text("-- not read, `spent` is the answer --", encoding="utf-8")
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(doctor.tls, "spent", lambda path: False))
        for name, stub in engine.items():
            stack.enter_context(mock.patch.object(doctor.isolation, name, stub))
        yield {
            execution.IMAGE: "rk-agent:test",
            execution.NETWORK: "rk-agent-net",
            execution.PROXY_CONTAINER: "rk-proxy",
            execution.PROXY_URL: "http://rk-proxy:8080",
            execution.CERTIFICATE: str(certificate),
            isolation.OAUTH_TOKEN_VARIABLE: str(
                token_file() if token is None else token
            ),
        }


def detail(diagnosis, name: str) -> str:
    return next(item.detail for item in diagnosis.assertions if item.name == name)


def installed_distribution() -> tuple[str, str] | None:
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        if name and distribution.version:
            return name, distribution.version
    return None


class ReadinessTest(unittest.TestCase):
    def test_ready_runtime_and_configuration_report_success(self):
        diagnosis = doctor.diagnose(write(VALID))

        self.assertTrue(diagnosis.ok)
        self.assertEqual(EXIT_OK, diagnosis.exit_code)
        self.assertEqual((), diagnosis.violations)
        self.assertTrue(all(assertion.ok for assertion in diagnosis.assertions))
        self.assertEqual("acme-web", diagnosis.as_dict()["configuration"]["program_name"])

    def test_readiness_is_reported_without_a_configuration(self):
        diagnosis = doctor.diagnose(None)

        self.assertTrue(diagnosis.ok)
        self.assertIsNone(diagnosis.as_dict()["configuration"])
        self.assertIn("configuration", [assertion.name for assertion in diagnosis.assertions])

    def test_result_names_versions_and_is_serialisable(self):
        report = doctor.diagnose(write(VALID)).as_dict()

        self.assertEqual(1, report["schema_version"])
        self.assertEqual("doctor", report["command"])
        self.assertEqual(doctor.supported_python(), report["supported_python"])
        self.assertEqual(".".join(str(part) for part in sys.version_info[:3]), report["python_version"])
        self.assertEqual(report, json.loads(json.dumps(report)))

    def test_the_build_it_is_running_is_reported(self):
        report = doctor.diagnose(None).as_dict()

        # The suite runs from a source checkout, so there is no manifest to have
        # drifted from; doctor still reports what the module tree hashes to.
        self.assertIs(report["build"]["source"], True)
        self.assertEqual(64, len(report["build"]["digest"]))

    def test_diagnostic_output_carries_hashes_but_no_references(self):
        rendered = json.dumps(doctor.diagnose(write(VALID)).as_dict())
        configuration = json.loads(rendered)["configuration"]

        self.assertEqual(64, len(configuration["source_sha256"]))
        self.assertEqual(64, len(configuration["canonical_sha256"]))
        self.assertNotIn("slot://identity/member", rendered)
        self.assertNotIn("slot://header/bounty-id", rendered)


class DistinctOutcomeTest(unittest.TestCase):
    def test_invalid_configuration_is_its_own_outcome(self):
        diagnosis = doctor.diagnose(write(VALID.replace('[program]\n', '[program]\nowner = "someone"\n')))

        self.assertEqual(EXIT_INVALID_CONFIGURATION, diagnosis.exit_code)
        self.assertEqual(["config:program.owner"], [item.source for item in diagnosis.violations])
        self.assertIsNone(diagnosis.as_dict()["configuration"])

    def test_unsupported_configuration_version_is_its_own_outcome(self):
        diagnosis = doctor.diagnose(write(VALID.replace("schema_version = 1", "schema_version = 2")))

        self.assertEqual(EXIT_UNSUPPORTED_VERSION, diagnosis.exit_code)

    def test_unsupported_interpreter_is_its_own_outcome(self):
        diagnosis = doctor.diagnose(None, python_version=(3, 15, 0))

        self.assertEqual(EXIT_UNSUPPORTED_VERSION, diagnosis.exit_code)
        self.assertEqual(["runtime:python"], [item.source for item in diagnosis.violations])
        self.assertIn("3.15.0", diagnosis.violations[0].detail)

    def test_interpreter_below_the_supported_range_is_refused(self):
        diagnosis = doctor.diagnose(None, python_version=(3, 13, 9))

        self.assertEqual(EXIT_UNSUPPORTED_VERSION, diagnosis.exit_code)

    def test_a_version_that_says_nothing_is_refused_rather_than_ignored(self):
        """An empty version is a stated fact about the interpreter, not an absent one."""
        diagnosis = doctor.diagnose(None, python_version=())

        self.assertEqual(EXIT_UNSUPPORTED_VERSION, diagnosis.exit_code)

    def test_a_build_that_is_not_its_manifest_is_its_own_outcome(self):
        # A fabricated install whose disk has drifted from its manifest: no
        # wheel and no git checkout, the failure reached through the command.
        root = scratch()
        (root / "artifact.py").write_text("print('drift')\n", encoding="utf-8")
        manifest = {
            "schema_version": 1,
            "revision": "b" * 40,
            "dirty": False,
            "built_at": "2026-08-17T00:00:00Z",
            "modules": {"artifact.py": hashlib.sha256(b"print('shipped')\n").hexdigest()},
        }
        (root / "_build.json").write_text(json.dumps(manifest), encoding="utf-8")

        diagnosis = doctor.diagnose(None, build_anchor=root)

        self.assertEqual(EXIT_BUILD_MISMATCH, diagnosis.exit_code)
        self.assertEqual(["build:artifact.py"], [item.source for item in diagnosis.violations])

    def test_missing_runtime_module_is_its_own_outcome(self):
        diagnosis = doctor.diagnose(
            None, requirements=Requirements(modules=("redkraken_absent_module",))
        )

        self.assertEqual(EXIT_MISSING_DEPENDENCY, diagnosis.exit_code)
        self.assertEqual(
            ["runtime:module:redkraken_absent_module"],
            [item.source for item in diagnosis.violations],
        )

    def test_missing_declared_distribution_is_its_own_outcome(self):
        diagnosis = doctor.diagnose(
            None, requirements=Requirements(distributions=(("redkraken-absent", "1.0.0"),))
        )

        self.assertEqual(EXIT_MISSING_DEPENDENCY, diagnosis.exit_code)
        self.assertEqual(
            ["runtime:distribution:redkraken-absent"],
            [item.source for item in diagnosis.violations],
        )
        self.assertIn("is not installed", diagnosis.violations[0].detail)

    def test_declared_distribution_version_must_match(self):
        installed = installed_distribution()
        if installed is None:
            self.skipTest("no installed distribution to compare against")
        name, version = installed

        diagnosis = doctor.diagnose(
            None, requirements=Requirements(distributions=((name, "0.0.0"),))
        )

        self.assertEqual(EXIT_MISSING_DEPENDENCY, diagnosis.exit_code)
        self.assertIn("0.0.0", diagnosis.violations[0].detail)
        self.assertIn(version, diagnosis.violations[0].detail)

    def test_declared_distribution_at_its_pinned_version_is_ready(self):
        installed = installed_distribution()
        if installed is None:
            self.skipTest("no installed distribution to compare against")

        diagnosis = doctor.diagnose(None, requirements=Requirements(distributions=(installed,)))

        self.assertEqual(EXIT_OK, diagnosis.exit_code)


class AggregationTest(unittest.TestCase):
    def test_every_violation_is_reported_and_the_runtime_outranks_the_operator(self):
        diagnosis = doctor.diagnose(
            write(VALID.replace("requests = 5000", "requests = 0")),
            python_version=(3, 15, 0),
        )

        self.assertEqual(EXIT_UNSUPPORTED_VERSION, diagnosis.exit_code)
        self.assertEqual(
            ["config:budgets.requests", "runtime:python"],
            sorted(item.source for item in diagnosis.violations),
        )

    def test_a_failed_assertion_accompanies_every_violation(self):
        diagnosis = doctor.diagnose(
            None, requirements=Requirements(modules=("redkraken_absent_module", "json"))
        )

        self.assertEqual(
            {"module:json": True, "module:redkraken_absent_module": False},
            {
                assertion.name: assertion.ok
                for assertion in diagnosis.assertions
                if assertion.name.startswith("module:")
            },
        )



class SubjectTest(unittest.TestCase):
    """Story 12's other four subjects, each asked of what a machine describes."""

    def test_a_machine_that_describes_nothing_is_told_that_it_described_nothing(self):
        diagnosis = doctor.diagnose(None)

        self.assertTrue(diagnosis.ok)
        self.assertEqual("no connection string supplied", detail(diagnosis, "database"))
        self.assertIn("no trust root described", detail(diagnosis, "proxy_trust_root"))
        self.assertEqual("no Agent boundary described", detail(diagnosis, "agent_boundary"))

    def test_the_doctor_matches_the_configured_program_to_the_running_door(self):
        ledger = Ledger()
        connection = mock.Mock()
        connection.execute.return_value.rows = [("00000000-0000-4000-8000-1",)]
        opened = mock.MagicMock()
        opened.__enter__.return_value = connection
        with described() as environment, \
             mock.patch.object(doctor.pg, "connect", return_value=opened), \
             mock.patch.object(doctor.door, "preflight", return_value="matched"):
            doctor._assert_door_program(
                ledger,
                environment,
                "postgresql://runtime@db/rk2hunt21",
                {"program_name": "rk2hunt21"},
            )

        self.assertEqual([], list(ledger.violations))
        self.assertEqual(
            "matched",
            next(item.detail for item in ledger.assertions if item.name == "door_preflight"),
        )

    def test_the_doctor_refuses_a_program_absent_from_the_runtime_database(self):
        ledger = Ledger()
        connection = mock.Mock()
        connection.execute.return_value.rows = []
        opened = mock.MagicMock()
        opened.__enter__.return_value = connection
        with described() as environment, mock.patch.object(
            doctor.pg, "connect", return_value=opened
        ):
            doctor._assert_door_program(
                ledger,
                environment,
                "postgresql://runtime@db/rk2hunt21",
                {"program_name": "rk2hunt21"},
            )

        self.assertEqual(["door"], [item.source for item in ledger.violations])

    def test_a_connection_string_this_client_cannot_use_is_refused(self):
        diagnosis = doctor.diagnose(None, database_url="mysql://rk@127.0.0.1/rk")

        self.assertEqual(EXIT_INVALID_CONFIGURATION, diagnosis.exit_code)
        self.assertIn(
            "must be postgresql://", " ".join(item.detail for item in diagnosis.violations)
        )

    def test_a_database_nothing_answers_on_is_refused_rather_than_held(self):
        # Port 1 on the loopback interface: refused immediately, so this asks
        # the unreachable path without a server and without a wait.
        diagnosis = doctor.diagnose(None, database_url="postgresql://rk@127.0.0.1:1/rk")

        self.assertEqual(EXIT_DATABASE_UNREACHABLE, diagnosis.exit_code)
        self.assertIn("db status", detail(diagnosis, "database"))

    def test_the_program_that_issues_certificates_is_named_when_it_is_absent(self):
        with mock.patch.object(doctor.shutil, "which", lambda name: None):
            diagnosis = doctor.diagnose(None)

        self.assertEqual(EXIT_MISSING_DEPENDENCY, diagnosis.exit_code)
        self.assertIn("openssl is not on PATH", detail(diagnosis, "certificate_tool"))

    def test_a_trust_root_that_is_not_a_file_is_refused(self):
        directory = scratch()

        diagnosis = doctor.diagnose(
            None, environment={proxy.CA_VARIABLE: str(directory / "absent.pem")}
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, diagnosis.exit_code)
        self.assertIn("not a readable file", detail(diagnosis, "proxy_trust_root"))

    def test_a_trust_root_at_the_end_of_its_life_is_refused_before_a_run_needs_it(self):
        certificate = scratch() / "ca.pem"
        certificate.write_text("-- not read, `spent` is the answer --", encoding="utf-8")

        with mock.patch.object(doctor.tls, "spent", lambda path: True):
            diagnosis = doctor.diagnose(
                None, environment={proxy.CA_VARIABLE: str(certificate)}
            )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, diagnosis.exit_code)
        self.assertIn("end of its life", detail(diagnosis, "proxy_trust_root"))

    def test_a_current_trust_root_and_a_real_authority_directory_hold(self):
        directory = scratch()
        certificate = directory / "ca.pem"
        certificate.write_text("-- not read --", encoding="utf-8")

        with mock.patch.object(doctor.tls, "spent", lambda path: False):
            diagnosis = doctor.diagnose(
                None,
                environment={
                    proxy.CA_VARIABLE: str(certificate),
                    proxy.AUTHORITY_VARIABLE: str(directory),
                },
            )

        self.assertTrue(diagnosis.ok)
        self.assertIn("is current", detail(diagnosis, "proxy_trust_root"))
        self.assertIn("can hold", detail(diagnosis, "proxy_authority"))

    def test_a_diagnosis_never_mints_the_authority_it_reports_on(self):
        directory = scratch()

        diagnosis = doctor.diagnose(
            None, environment={proxy.AUTHORITY_VARIABLE: str(directory)}
        )

        self.assertTrue(diagnosis.ok)
        self.assertEqual([], list(directory.iterdir()))

    def test_a_boundary_described_in_part_names_what_is_missing(self):
        diagnosis = doctor.diagnose(
            None, environment={execution.IMAGE: "rk-agent:test"}
        )

        self.assertEqual(EXIT_INVALID_CONFIGURATION, diagnosis.exit_code)
        self.assertIn(execution.NETWORK, detail(diagnosis, "agent_boundary"))

    def test_a_boundary_with_no_container_engine_is_a_missing_dependency(self):
        def absent(name):
            raise isolation.Unavailable(f"the configured container engine is not on PATH: {name}")

        with described(engine_for=absent) as environment:
            diagnosis = doctor.diagnose(None, environment=environment)

        self.assertEqual(EXIT_MISSING_DEPENDENCY, diagnosis.exit_code)
        self.assertIn("not on PATH", detail(diagnosis, "agent_boundary"))

    def test_a_network_holding_a_peer_other_than_the_door_is_refused(self):
        def crowded(engine, network, proxy_container, proxy_host):
            raise isolation.Unavailable("the Agent network has peers other than the proxy: rk-old")

        with described(
            engine_for=lambda name: f"/usr/bin/{name}", one_peer=crowded
        ) as environment:
            diagnosis = doctor.diagnose(None, environment=environment)

        self.assertEqual(EXIT_INVALID_CONFIGURATION, diagnosis.exit_code)
        self.assertIn("rk-old", detail(diagnosis, "agent_boundary"))

    def test_a_boundary_that_holds_is_reported_as_the_one_peer_it_is(self):
        asked = []

        with described(
            engine_for=lambda name: f"/usr/bin/{name}",
            one_peer=lambda *seen: asked.append(seen),
        ) as environment:
            diagnosis = doctor.diagnose(None, environment=environment)

        self.assertTrue(diagnosis.ok)
        self.assertEqual([("/usr/bin/docker", "rk-agent-net", "rk-proxy", "rk-proxy")], asked)
        self.assertIn("holds rk-proxy alone", detail(diagnosis, "agent_boundary"))

    def test_a_corpus_that_no_longer_compiles_is_refused_here_and_not_mid_run(self):
        def broken():
            raise playbook.PlaybookError("skill_unknown", "recon/dns", "names skill sweep")

        diagnosis = doctor.diagnose(None, corpora=(("playbooks", broken),))

        self.assertEqual(EXIT_INVALID_CORPUS, diagnosis.exit_code)
        self.assertIn("skill_unknown", detail(diagnosis, "catalogue:playbooks"))

    def test_the_shipped_corpora_are_compiled_and_counted(self):
        diagnosis = doctor.diagnose(None)

        for name in ("playbooks", "skills", "fixtures"):
            with self.subTest(corpus=name):
                counted, _, word = detail(diagnosis, f"catalogue:{name}").partition(" ")
                self.assertEqual("compiled", word)
                self.assertGreater(int(counted), 0)


class AgentCredentialTest(unittest.TestCase):
    """Ticket 146: the question the launch used to ask a Task's attempt for.

    `rk2hunt7` spent three attempts on `Exception: Claude Code returned an error
    result: success` and then one on `an Agent credential the child cannot
    write`, and `attempts_exhausted` retired the Task. Every case here is the
    same predicate asked before a run rather than by one.
    """

    def credential(self, diagnosis) -> str:
        return detail(diagnosis, "agent_credential")

    def test_a_machine_that_starts_no_children_is_asked_for_no_token(self):
        diagnosis = doctor.diagnose(None, environment={})

        self.assertTrue(diagnosis.ok)
        self.assertEqual("no Agent boundary described", self.credential(diagnosis))

    def test_a_boundary_with_a_token_this_operator_alone_can_read_holds(self):
        with described(
            engine_for=lambda name: f"/usr/bin/{name}", one_peer=lambda *seen: None
        ) as environment:
            diagnosis = doctor.diagnose(None, environment=environment)

        self.assertTrue(diagnosis.ok)
        self.assertIn("holds a setup token", self.credential(diagnosis))
        self.assertNotIn(SENTINEL, json.dumps(diagnosis.as_dict()))

    def test_a_boundary_holding_no_token_is_refused_before_a_run_spends_an_attempt(self):
        absent = scratch() / "redkraken"
        absent.mkdir(mode=0o700)
        with described(
            token=absent / "claude-oauth-token",
            engine_for=lambda name: f"/usr/bin/{name}",
            one_peer=lambda *seen: None,
        ) as environment:
            diagnosis = doctor.diagnose(None, environment=environment)

        self.assertEqual(EXIT_INVALID_CONFIGURATION, diagnosis.exit_code)
        self.assertIn("no Claude setup token", self.credential(diagnosis))
        self.assertIn("setup-agent-oauth.sh", self.credential(diagnosis))

    def test_a_credential_owned_by_neither_contained_id_is_refused_by_the_doctor(self):
        """Ticket 146's own criterion, in the mode `rk2hunt7` measured.

        `660`, owned by the supervisor and by no group the child is in, with no
        other-write bit: no arm of `writable_by_the_child` matched it and the
        launch refused it after the claim. It is refused here now, and for the
        reason that outlives the mount -- a token another local account can read
        is a live Anthropic token this operator does not hold alone.
        """
        path = token_file(mode=0o660)
        status = path.stat()
        self.assertNotEqual(isolation.UID, status.st_uid)
        self.assertNotEqual(isolation.GID, status.st_gid)
        self.assertFalse(status.st_mode & 0o002)

        with described(
            token=path,
            engine_for=lambda name: f"/usr/bin/{name}",
            one_peer=lambda *seen: None,
        ) as environment:
            diagnosis = doctor.diagnose(None, environment=environment)

        self.assertEqual(EXIT_INVALID_CONFIGURATION, diagnosis.exit_code)
        self.assertIn("group or world", self.credential(diagnosis))

    def test_a_token_old_enough_to_expire_mid_hunt_offers_the_wizard_again(self):
        path = token_file()
        aged = time.time() - (isolation.OAUTH_TOKEN_DAYS + 1) * 86400
        os.utime(path, (aged, aged))

        with described(
            token=path,
            engine_for=lambda name: f"/usr/bin/{name}",
            one_peer=lambda *seen: None,
        ) as environment:
            diagnosis = doctor.diagnose(None, environment=environment)

        # A warning and not a refusal: a token that still works is one an
        # operator may finish the hunt on.
        self.assertTrue(diagnosis.ok)
        self.assertIn(f"{isolation.OAUTH_TOKEN_DAYS + 1} days ago", self.credential(diagnosis))
        self.assertIn("setup-agent-oauth.sh", self.credential(diagnosis))

    def test_a_relative_override_is_refused_rather_than_resolved(self):
        with described(
            engine_for=lambda name: f"/usr/bin/{name}", one_peer=lambda *seen: None
        ) as environment:
            environment[isolation.OAUTH_TOKEN_VARIABLE] = "claude-oauth-token"
            diagnosis = doctor.diagnose(None, environment=environment)

        self.assertEqual(EXIT_INVALID_CONFIGURATION, diagnosis.exit_code)
        self.assertIn("absolute", self.credential(diagnosis))


class NoSideEffectTest(unittest.TestCase):
    def test_diagnosis_writes_nothing_beside_the_configuration(self):
        directory = scratch()
        source = directory / "program.toml"
        source.write_text(VALID, encoding="utf-8")
        before = source.read_bytes()

        doctor.diagnose(source)

        self.assertEqual(["program.toml"], [entry.name for entry in directory.iterdir()])
        self.assertEqual(before, source.read_bytes())


if __name__ == "__main__":
    unittest.main()
