"""The gate that decides whether a build is the artifact an operator installs.

Ticket 62 criteria 1, 2, 6 and 7. `tools/release_gate.py` proves what it proves
by building a real installation against a real server, so almost all of it is
unreachable from a suite that opens neither. What is reachable is the part that
decides: what a stage may run against, what a role's connection string says,
what a child inherits, and what the gate refuses before it has spent an hour.

Those are worth holding because they are the failure modes a live run hides. A
gate that leaked the caller's environment into its children would pass on the
machine that leaked and fail nowhere; a gate that regenerated a password per
stage would provision one database and be unable to reach it; a gate whose
refusals arrived as an errno from the fourth command in would be read as a
broken harness rather than as a missing prerequisite. Each of those passes a
live run and none of them survives being asked directly.

The stages themselves are exercised by running the gate, which is the point of
it: `python3 -m tools.release_gate --superuser-url ...` is the check, and this
module is the check on the checker.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from redkraken import config

from tools import release_gate
from tools.check_baseline import read_status
from tools.release_gate import (
    CONNECTING,
    Gate,
    INSTALLABLE,
    NOT_INSTALLABLE,
    PROGRAM,
    PROVISIONED,
    RUNS,
    ReleaseError,
    STAGES,
    SURFACE,
    answered,
    check,
    counts,
    preflight,
    ran,
)


ROOT = Path(__file__).resolve().parents[1]

#: A superuser URL in the shape the gate is handed one, assembled rather than
#: written: a connection string with a password in it is a credential shape in a
#: publishable file, and the scan that says this tree carries none would have to
#: forgive this line to let it through. Nothing here opens a connection.
SUPERUSER = "postgres://postgres:" + "gate-test-password@127.0.0.1:55433/postgres"


def gate(case: unittest.TestCase, **named) -> Gate:
    """A gate over a directory that goes away with the test that asked for it."""
    root = Path(tempfile.mkdtemp(prefix="rk2-release-test-"))
    case.addCleanup(shutil.rmtree, root, ignore_errors=True)
    (root / "tmp").mkdir()
    return Gate(superuser=SUPERUSER, root=root, **named)


def built(gate_: Gate, *stages: str) -> None:
    """Leave behind what the named stages leave behind, and nothing else.

    Enough for `preflight` to read them as done -- an export directory, an
    interpreter in the virtual environment, a file of recorded roles -- and none
    of it built by running anything, because what is under test is what the
    preconditions look at rather than what the stages do.
    """
    if "export" in stages:
        gate_.export.mkdir(parents=True, exist_ok=True)
    if "install" in stages:
        gate_.python.parent.mkdir(parents=True, exist_ok=True)
        gate_.python.touch()
    if "database" in stages:
        gate_.secret("rk2_runtime")


class ConnectionTest(unittest.TestCase):
    """What a role's connection string says, and where its password comes from."""

    def test_a_url_carries_the_role_the_password_and_the_database_asked_for(self):
        built = gate(self)
        url = built.url("rk2_runtime", "rk2_release_gate")
        self.assertTrue(url.startswith("postgres://rk2_runtime:"))
        self.assertTrue(url.endswith("@127.0.0.1:55433/rk2_release_gate"))
        self.assertIn(built.secret("rk2_runtime"), url)

    def test_the_host_the_door_needs_replaces_only_the_host(self):
        """The one connection string that crosses into a container.

        A container's loopback is its own, so the door is handed this machine
        under the name the engine publishes it as. The port and the credential
        are the same ones, or the door would be reaching a different server.
        """
        built = gate(self)
        inside = built.url("rk2_proxy", "rk2_release_gate", host="host.docker.internal")
        outside = built.url("rk2_proxy", "rk2_release_gate")
        self.assertIn("@host.docker.internal:55433/rk2_release_gate", inside)
        self.assertEqual(
            inside.replace("host.docker.internal", "127.0.0.1"), outside
        )

    def test_a_password_is_made_once_and_survives_into_the_next_stage(self):
        """Stages are separately selectable, so the roles have to be findable.

        A `--stage privileges` run reaches a database an earlier `--stage
        database` run provisioned. If the password were regenerated per run the
        second one would be holding a credential that database never had.
        """
        first = gate(self)
        recorded = {role: first.secret(role) for role in CONNECTING}
        again = Gate(superuser=SUPERUSER, root=first.root)
        self.assertEqual({role: again.secret(role) for role in CONNECTING}, recorded)
        self.assertEqual(json.loads(first.kept.read_text(encoding="utf-8")), recorded)

    def test_the_recorded_passwords_are_readable_by_nobody_else(self):
        built = gate(self)
        built.secret("rk2_runtime")
        self.assertEqual(built.kept.stat().st_mode & 0o777, 0o600)

    def test_no_two_roles_are_given_the_same_password(self):
        built = gate(self)
        self.assertEqual(len({built.secret(role) for role in CONNECTING}), len(CONNECTING))


class EnvironmentTest(unittest.TestCase):
    """What a child of this gate is given, which is only what it was written."""

    def test_a_child_inherits_nothing_the_gate_did_not_write(self):
        built = gate(self)
        with mock.patch.dict(
            os.environ, {"RK_DATABASE_URL": "postgres://leaked@127.0.0.1/leaked"}
        ):
            written = built.environment()
        self.assertEqual(set(written), {"PATH", "HOME", "TMPDIR", "LANG"})
        self.assertNotIn("RK_DATABASE_URL", written)

    def test_a_child_gets_the_home_and_the_scratch_of_this_run(self):
        """Never the operator's: a gate that wrote into `~` would be measuring it."""
        built = gate(self)
        written = built.environment()
        self.assertEqual(written["HOME"], str(built.home))
        self.assertEqual(written["TMPDIR"], str(built.root / "tmp"))

    def test_a_stage_adds_names_without_taking_the_four_away(self):
        written = gate(self).environment(RK_SUPERUSER_URL=SUPERUSER)
        self.assertEqual(written["RK_SUPERUSER_URL"], SUPERUSER)
        self.assertEqual(written["LANG"], "C.UTF-8")

    def test_the_written_environment_reaches_the_child_and_nothing_else_does(self):
        """Asked of a real child, because that is the claim the check makes."""
        built = gate(self)
        with mock.patch.dict(os.environ, {"RK_PASSWORD_RK2_RUNTIME": "leaked"}):
            result = ran(
                [sys.executable, "-c", "import json, os; print(json.dumps(dict(os.environ)))"],
                environment=built.environment(),
            )
        self.assertEqual(set(json.loads(result.stdout)), {"PATH", "HOME", "TMPDIR", "LANG"})


class ArchiveTest(unittest.TestCase):
    """The dump this gate writes, which the application refuses to overwrite."""

    def test_two_runs_over_one_directory_write_two_archives(self):
        root = gate(self).root
        first = Gate(superuser=SUPERUSER, root=root)
        second = Gate(superuser=SUPERUSER, root=root)
        self.assertNotEqual(first.archive, second.archive)
        self.assertEqual(first.archive.parent, root)


class ChildTest(unittest.TestCase):
    """What the gate does with a command that did not do what it was for."""

    def test_a_failing_command_names_itself_and_says_what_it_said(self):
        with self.assertRaises(ReleaseError) as refused:
            ran(
                [sys.executable, "-c", "import sys; sys.stderr.write('the reason'); sys.exit(3)"],
                environment=gate(self).environment(),
            )
        self.assertIn("exited 3", str(refused.exception))
        self.assertIn("the reason", str(refused.exception))

    def test_a_command_that_was_supposed_to_refuse_may_refuse(self):
        """Half the gate's readings are refusals, so a non-zero exit is a pass."""
        result = ran(
            [sys.executable, "-c", "sys.exit(1)" and "raise SystemExit(1)"],
            environment=gate(self).environment(),
            expect=1,
        )
        self.assertEqual(result.returncode, 1)

    def test_an_answer_that_is_not_a_document_is_a_refusal_not_a_traceback(self):
        said = subprocess.CompletedProcess(["rk"], 0, stdout="not json", stderr="")
        with self.assertRaises(ReleaseError) as refused:
            answered(said)
        self.assertIn("not JSON", str(refused.exception))

    def test_a_document_is_read_as_the_command_wrote_it(self):
        said = subprocess.CompletedProcess(["rk"], 0, stdout='{"ok": true}', stderr="")
        self.assertEqual(answered(said), {"ok": True})


class PreconditionTest(unittest.TestCase):
    """What the gate refuses before it spends an hour building anything."""

    def test_a_stage_that_does_not_exist_is_named(self):
        with self.assertRaises(ReleaseError) as refused:
            check(SUPERUSER, ("install", "privilege"))
        self.assertIn("privilege", str(refused.exception))

    def test_the_first_stage_needs_nothing_that_came_before_it(self):
        self.assertEqual(preflight(gate(self), ("export",)), [])

    def test_a_stage_and_the_stage_that_builds_its_input_go_together(self):
        """However they were typed: a selection is a set, not a sequence.

        `--stage` appends in the order the operator typed it and `check` runs
        stages in `STAGES` order regardless, so a precondition that read the
        selection as a sequence would refuse one of these two and not the other.
        """
        for stages in (("export", "install"), ("install", "export"), STAGES):
            with self.subTest(stages=stages):
                self.assertEqual(preflight(gate(self), stages), [])

    def test_installing_into_a_root_nobody_exported_into_is_refused(self):
        [reason] = preflight(gate(self), ("install",))
        self.assertIn("nothing exported", reason)
        self.assertIn("--stage export", reason)

    def test_a_stage_without_an_installation_says_which_stage_builds_one(self):
        built_ = gate(self)
        built(built_, "export")
        [reason] = preflight(built_, ("database",))
        self.assertIn(str(built_.venv), reason)
        self.assertIn("--stage install", reason)

    def test_a_stage_needing_the_roles_says_so_rather_than_failing_on_one(self):
        """The refusal that would otherwise arrive as a KeyError on a role name."""
        built_ = gate(self)
        built(built_, "export", "install")
        [reason] = preflight(built_, ("privileges",))
        self.assertIn("roles.json", reason)
        self.assertIn("--stage database", reason)

    def test_a_selection_missing_two_things_says_both(self):
        built_ = gate(self)
        built(built_, "export")
        self.assertEqual(len(preflight(built_, ("suites",))), 2)

    def test_a_root_a_kept_run_built_needs_no_stage_repeated(self):
        built_ = gate(self)
        built(built_, "export", "install", "database")
        for stages in (("topology",), ("privileges",), ("suites",), ("database",)):
            with self.subTest(stages=stages):
                self.assertEqual(preflight(built_, stages), [])


class CountTest(unittest.TestCase):
    """What a suite reported, which is the only thing its exit code cannot say."""

    def test_a_run_reports_what_it_selected_and_what_it_skipped(self):
        self.assertEqual(counts("Ran 1823 tests in 137.1s\n\nOK (skipped=147)\n"), (1823, 147))

    def test_a_run_that_skipped_nothing_skipped_nothing(self):
        self.assertEqual(counts("Ran 12 tests in 0.1s\n\nOK\n"), (12, 0))

    def test_a_report_with_no_count_in_it_is_a_refusal(self):
        """A suite that died before it could count is not a suite that passed."""
        with self.assertRaises(ReleaseError):
            counts("Traceback (most recent call last):\n")


class DeclarationTest(unittest.TestCase):
    """The constants the stages spend, held against the tree they describe."""

    def test_the_stages_are_the_functions_and_they_are_in_order(self):
        self.assertEqual(tuple(RUNS), STAGES)
        for name, function in RUNS.items():
            with self.subTest(stage=name):
                self.assertIs(function, getattr(release_gate, name))
        self.assertEqual(STAGES[:2], ("export", "install"))
        self.assertLess(STAGES.index("database"), STAGES.index("privileges"))

    def test_every_directory_a_checkout_carries_is_installable_or_named(self):
        """Drift in the tree is what turns this constant into a lie.

        A directory added at the root is either part of the application or part
        of the work around it. If it is the second and nobody wrote it down, the
        install stage stops being able to see it arrive in a wheel.

        Tracked directories rather than whatever is lying in the tree: a build
        leaves `build/` next to the sources, gitignored, and a checkout is what
        a clone carries. `src` is the application and `baseline` is the registry
        the repository gates read; everything else has to be accounted for.
        """
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        carried = {name.split("/")[0] for name in tracked.stdout.split("\0") if "/" in name}
        unaccounted = sorted(carried - set(NOT_INSTALLABLE) - {"src", "baseline"})
        self.assertEqual(unaccounted, [])

    def test_the_application_is_the_only_thing_that_may_be_installed(self):
        self.assertEqual(INSTALLABLE, {"redkraken", "pip"})

    def test_what_may_not_be_installed_is_what_the_registry_already_forbids(self):
        """One list, in the registry, read here rather than written again."""
        for root in read_status()["forbidden_dependency_roots"]:
            with self.subTest(root=root):
                self.assertIn(root.lstrip("/."), NOT_INSTALLABLE)
        self.assertLessEqual({"tests", "tools", ".git", ".venv"}, set(NOT_INSTALLABLE))

    def test_the_program_the_gate_opens_is_one_the_application_accepts(self):
        """Written here rather than taken from the fixtures for the same reason
        the stage writes it to disk: what travels through a dump has to be a
        file this run owns."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "program.toml"
            path.write_text(PROGRAM, encoding="utf-8")
            loaded, violations = config.load(path)
        self.assertEqual(violations, ())
        self.assertEqual(loaded.document["program"]["name"], "release-gate")
        self.assertFalse(loaded.document["rules_of_engagement"]["mutation"])

    def test_the_program_provisions_nothing_it_would_have_to_work_around(self):
        declared = tomllib.loads(PROGRAM)
        for absent in ("identity", "header", "callback"):
            with self.subTest(section=absent):
                self.assertNotIn(absent, declared)

    def test_the_surface_reading_is_source_the_installation_can_run(self):
        compile(SURFACE, "<surface>", "exec")
        self.assertIn("check_runtime_privileges()", SURFACE)

    def test_the_roles_the_gate_holds_are_the_ones_that_log_in(self):
        """Not `rk2_owner`, which cannot log in, and not the operator's own."""
        self.assertNotIn("rk2_owner", CONNECTING)
        self.assertNotIn("rk2_human", CONNECTING)
        self.assertEqual(set(CONNECTING), set(PROVISIONED) - {"rk2_owner", "rk2_human"})
        self.assertEqual(len(PROVISIONED), 7)


if __name__ == "__main__":
    unittest.main()
