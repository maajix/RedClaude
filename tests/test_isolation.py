"""The real Agent-container routing boundary for PH2-10/11."""

from __future__ import annotations

import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from concurrent import futures
from pathlib import Path
from unittest import mock

from redkraken import _startup, browser_driver, isolation, tls
from tests import SOURCE, fixtures
from tests.fixtures import docker


LIVE = os.environ.get("RK_TEST_CONTAINERS") == "1"
REASON = "set RK_TEST_CONTAINERS=1 to run the disposable Docker isolation proof"


class ContainerEnvironmentTest(unittest.TestCase):
    """What a child is told about the world, and what it is not told.

    No engine required. The environment is the half of the boundary that is
    decidable without one, and the machine that has to prove nothing crosses is
    not always the machine that can start something for it not to cross into.
    """

    #: What a second `rk run` process does: takes the same claim and reports
    #: whether it got it. Run with this process's environment, because which
    #: directory the claims live in is read from it and two processes that
    #: disagreed about that would be two processes claiming different things.
    CLAIMANT = """
import json, sys
from redkraken import isolation

try:
    with isolation.held(sys.argv[1]):
        print(json.dumps({"held": True}), flush=True)
        sys.stdin.readline()
except isolation.Unavailable as refusal:
    print(json.dumps({"held": False, "refusal": str(refusal)}), flush=True)
"""

    def claimant(self, network: str) -> subprocess.Popen:
        """Start one, and take it and its pipes away when the case ends."""
        process = subprocess.Popen(
            [sys.executable, "-c", self.CLAIMANT, network],
            env={**os.environ, "PYTHONPATH": str(SOURCE)},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(process.stdout.close)
        self.addCleanup(process.stdin.close)
        self.addCleanup(process.kill)
        return process

    def test_a_second_process_cannot_claim_a_network_the_first_one_holds(self):
        """PH2-85 criterion 4: the claim is the kernel's, not this interpreter's.

        Two `rk run` processes on one machine is the case, so the second one
        here is a real process rather than a second call. It is refused while
        the first holds the claim, and gets it as soon as the first is gone --
        the second half matters as much: a claim that outlived the launch that
        took it would be an installation that can launch once.
        """
        network = f"rk2-claim-{uuid.uuid4().hex[:12]}"
        first = self.claimant(network)
        self.assertEqual({"held": True}, json.loads(first.stdout.readline()))

        with self.assertRaisesRegex(isolation.Unavailable, "holds the Agent network"):
            with isolation.held(network):
                pass

        first.stdin.write("\n")
        first.stdin.flush()
        self.assertEqual(0, first.wait(timeout=30))
        with isolation.held(network):
            pass

    def test_one_claim_is_per_network_rather_than_per_installation(self):
        """A claim on one network says nothing about another. `run_tool` builds
        a network per run for exactly this reason, and an installation that
        described two Agent networks would be two boundaries rather than one."""
        first = f"rk2-claim-{uuid.uuid4().hex[:12]}"
        second = f"rk2-claim-{uuid.uuid4().hex[:12]}"

        with isolation.held(first):
            with isolation.held(second):
                pass

    def test_a_run_gets_a_copy_of_the_home_and_the_copy_goes_when_it_does(self):
        """PH2-86 criteria 1 and 2, without an engine: the copy and its removal.

        The configured home is a template. A run is handed a copy of it with the
        modes it had -- `_mounts` decides whether the child can write its home
        from the mode it finds, so a copy that widened one would be answering a
        question the operator has already been asked -- and the copy is gone
        when the run is, which is the half that keeps a machine from filling up
        with the leftovers of runs nobody remembers.
        """
        template = Path(tempfile.mkdtemp(prefix="rk2-template-"))
        self.addCleanup(shutil.rmtree, template, ignore_errors=True)
        template.chmod(0o777)
        (template / "credential.json").write_text("seeded", encoding="utf-8")
        (template / "credential.json").chmod(0o666)

        with isolation.own_home(template) as home:
            self.assertNotEqual(template.resolve(), home)
            self.assertEqual("seeded", (home / "credential.json").read_text(encoding="utf-8"))
            self.assertEqual(0o777, home.stat().st_mode & 0o777)
            self.assertEqual(0o666, (home / "credential.json").stat().st_mode & 0o777)
            # What the run writes lands in the copy and never in the template.
            (home / "session").write_text("what this run did", encoding="utf-8")

        self.assertFalse(home.exists())
        self.assertEqual(["credential.json"], sorted(item.name for item in template.iterdir()))

    def test_a_home_with_no_template_stays_the_absent_one(self):
        """A container with no home mounted has no credential at all rather than
        somebody else's, which is the contained value -- so nothing is made."""
        with isolation.own_home(None) as home:
            self.assertIsNone(home)

    def test_a_home_too_large_to_copy_per_run_is_refused_before_anything_starts(self):
        """A home the size of an engagement is a directory pointed at the wrong
        thing, and copying it once per Agent run is a cost nobody asked for."""
        template = Path(tempfile.mkdtemp(prefix="rk2-template-"))
        self.addCleanup(shutil.rmtree, template, ignore_errors=True)
        template.chmod(0o777)
        with mock.patch.object(isolation, "HOME_CEILING", 1024):
            (template / "transcripts").write_bytes(b"x" * 2048)
            with self.assertRaisesRegex(isolation.Unavailable, "larger than one run may copy"):
                with isolation.own_home(template):
                    pass

    def test_the_operator_s_own_home_is_no_more_copyable_than_it_was_mountable(self):
        """The refusal that already covered the mount covers the template: the
        point of a home is that a credential is resolved from it, and a copy of
        the operator's is the operator's credential in a container."""
        with self.assertRaisesRegex(isolation.Unavailable, "carries the operator's home"):
            with isolation.own_home(Path(os.path.expanduser("~"))):
                pass

    def seeded(self) -> Path:
        """A template home holding a credential, as an operator's does."""
        template = Path(tempfile.mkdtemp(prefix="rk2-template-"))
        self.addCleanup(shutil.rmtree, template, ignore_errors=True)
        template.chmod(0o777)
        (template / ".claude").mkdir()
        (template / ".claude").chmod(0o777)
        credential = template / ".claude" / ".credentials.json"
        credential.write_text('{"claudeAiOauth": {"accessToken": "seeded"}}', encoding="utf-8")
        credential.chmod(0o666)
        return template

    def test_the_credential_crosses_neither_as_a_copy_nor_as_a_mount(self):
        """Ticket 146: the operator's own credential stops crossing at all.

        It used to be mounted out of the template, so that the CLI's refresh
        landed where the operator would read it next. That refresh is a rename,
        which breaks the link and leaves a file owned by the operator and
        unwritable by uid 65534 -- so the arrangement ends every installation it
        was built for. Nothing replaces it inside the boundary: the child is
        handed a setup token on its own stdin instead, and the file the operator
        seeded is left exactly where it is.
        """
        template = self.seeded()
        credential = template.resolve() / ".claude" / ".credentials.json"

        with isolation.own_home(template) as home:
            self.assertFalse((home / ".claude" / ".credentials.json").exists())
            self.assertTrue((home / ".claude").is_dir())
            mounts = isolation._mounts(
                fixtures.boundary(home=home), template / "authority.pem"
            )

        self.assertEqual([], [item for item in mounts if str(credential) in item])
        self.assertNotIn(
            f"{isolation.HOME_DIR}/{isolation.CREDENTIAL}", " ".join(mounts)
        )
        # And never deleted by anything here: it is the operator's file.
        self.assertTrue(credential.is_file())

    def test_a_credential_the_child_could_not_write_no_longer_ends_the_launch(self):
        """The refusal ticket 86 built is gone with the mount that needed it.

        `660 majix:majix` against a child running as `65534:65534` was exit 3 on
        every launch, and it was the right refusal for a file that had to be
        written inside the container. Nothing is written inside the container
        now, so this file is not the launch's business at all.
        """
        template = self.seeded()
        (template / ".claude" / ".credentials.json").chmod(0o660)

        mounts = isolation._mounts(fixtures.boundary(home=template), template / "authority.pem")

        self.assertTrue(any(str(template.resolve()) in item for item in mounts))

    def test_a_credentials_file_anywhere_else_under_a_home_is_the_run_s_own(self):
        """The credential is left behind by path, not by name: a file called the
        same thing further down a home is an ordinary file of the run's."""
        template = self.seeded()
        (template / "projects" / ".claude").mkdir(parents=True)
        (template / "projects" / ".claude" / ".credentials.json").write_text("x", encoding="utf-8")

        with isolation.own_home(template) as home:
            self.assertTrue((home / "projects" / ".claude" / ".credentials.json").is_file())

    def test_the_home_a_killed_run_left_behind_is_taken_away_by_the_next_launch(self):
        """`finally` does not run for a process that is killed, and what a killed
        run leaves here is a copy of a credential rather than an inert file.

        So a run holds its own copy open under a lock for as long as it has it,
        and the next launch removes every copy nothing is holding -- which is
        the difference between a leftover and a live run's home.
        """
        base = Path(tempfile.mkdtemp(prefix="rk2-homes-"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        homes = base / f"{isolation.HOMES}-{os.getuid()}"
        homes.mkdir(mode=0o700)
        killed = homes / "rk2-home-deadbeef"
        killed.mkdir()
        (killed / ".credentials.json").write_text("what the killed run had", encoding="utf-8")
        template = self.seeded()

        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(base)}):
            with isolation.own_home(template) as first:
                self.assertFalse(killed.exists())
                # And a copy a live run is holding is not a leftover: a second
                # launch sweeping while the first is running leaves it alone.
                with isolation.own_home(template) as second:
                    self.assertTrue(first.is_dir())
                    self.assertNotEqual(first, second)

        self.assertEqual([], sorted(homes.glob("rk2-home-*")))

    def test_a_copy_in_progress_is_already_claimed_against_the_next_sweep(self):
        """The window between making a home and holding it is a home nothing
        holds, and the next launch sweeps exactly what nothing holds.

        So the directory is made and locked before a byte goes into it. Proven
        by sweeping from inside the copy, which is the moment that window was:
        the copy that is being filled has to survive its own launch's sweep.
        """
        base = Path(tempfile.mkdtemp(prefix="rk2-homes-"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        homes = base / f"{isolation.HOMES}-{os.getuid()}"
        homes.mkdir(mode=0o700)
        template = self.seeded()
        copied = shutil.copytree

        def sweep_while_copying(*arguments, **options):
            # After the bytes and before this launch would have taken its lock,
            # which is the window the old order left open: a copy nothing holds
            # is what a sweep is for, and this copy is a live run's.
            answer = copied(*arguments, **options)
            isolation._sweep(homes)
            return answer

        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(base)}):
            with mock.patch.object(isolation.shutil, "copytree", sweep_while_copying):
                with isolation.own_home(template) as own:
                    self.assertTrue(own.is_dir())
                    self.assertTrue((own / ".claude").is_dir())

        self.assertEqual([], sorted(homes.glob("rk2-home-*")))

    def test_claims_kept_somewhere_that_is_not_this_user_s_own_are_refused(self):
        """The claims directory is where two `rk run` processes find each other.

        So a directory this user does not own -- or, as here, a symlink standing
        where it should be -- is somewhere another user can put a lock file, and
        a launch that took its claim there would be holding something nobody
        else is reading. `lstat` is what decides it, because a link is refused
        for what it is rather than for what it points at.
        """
        base = Path(tempfile.mkdtemp(prefix="rk2-claims-"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        elsewhere = base / "elsewhere"
        elsewhere.mkdir()
        (base / f"{isolation.LOCKS}-{os.getuid()}").symlink_to(elsewhere)

        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(base)}):
            with self.assertRaisesRegex(isolation.Unavailable, "not this user's own"):
                with isolation.held("rk2-agent-network"):
                    pass

    def test_a_claims_directory_anyone_else_could_read_is_tightened_first(self):
        """An existing directory is used rather than refused, at 0700 or not at all."""
        base = Path(tempfile.mkdtemp(prefix="rk2-claims-"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        directory = base / f"{isolation.LOCKS}-{os.getuid()}"
        directory.mkdir(mode=0o755)

        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(base)}):
            with isolation.held("rk2-agent-network"):
                pass

        self.assertEqual(0o700, directory.stat().st_mode & 0o777)

    def test_the_child_environment_is_a_copied_list_plus_the_runtime_door(self):
        operator = {name: f"operator-{name}" for name in isolation.INHERITED}
        operator.update(
            {name: "leaked" for name in _startup.WATCHED_ENV_VECTORS},
            ANTHROPIC_SMALL_FAST_MODEL="leaked",
            SSH_AUTH_SOCK="/leaked/agent.sock",
            AWS_PROFILE="leaked",
            PATH="/leaked/bin",
        )

        child = isolation.container_environment(
            fixtures.boundary(application=Path("/src"), sdk=Path("/sdk")), operator
        )

        for family in (
            _startup.WATCHED_ENV_VECTORS,
            ("ANTHROPIC_SMALL_FAST_MODEL", "SSH_AUTH_SOCK", "AWS_PROFILE", "PATH"),
        ):
            for name in family:
                self.assertNotIn(name, child)
        supplied = {"HOME", "TMPDIR", isolation.IMPORT_PATH}
        self.assertEqual(
            set(isolation.INHERITED) | supplied,
            set(child) - set(tls.PROXY_VARIABLES) - set(tls.BYPASS_VARIABLES)
            - set(tls.TRUST_VARIABLES) - set(tls.STORE_VARIABLES),
        )
        self.assertEqual(f"{isolation.APPLICATION}:{isolation.SDK}", child["PYTHONPATH"])

    def test_the_operator_home_never_crosses_and_neither_does_their_import_path(self):
        # Where the CLI looks for the operator's own subscription, and where an
        # interpreter looks for the SDK the assertion measures. Both are the
        # runtime's own, and neither has a source outside this function.
        child = isolation.container_environment(
            fixtures.boundary(), {"HOME": "/home/operator", "PYTHONPATH": "/home/operator/lib"}
        )

        self.assertEqual(isolation.HOME_DIR, child["HOME"])
        self.assertEqual(isolation.TMPDIR, child["TMPDIR"])
        self.assertNotIn(isolation.IMPORT_PATH, child)

    def test_the_child_has_no_route_out_that_the_runtime_does_not_own(self):
        child = isolation.container_environment(fixtures.boundary(), dict(os.environ))

        for name in tls.PROXY_VARIABLES:
            self.assertEqual("http://rk2-proxy:18080", child[name])
        for name in tls.BYPASS_VARIABLES + tls.STORE_VARIABLES:
            self.assertEqual("", child[name])
        for name in tls.TRUST_VARIABLES:
            self.assertEqual(isolation.CA_FILE, child[name])

    def contained(self) -> Path:
        """A directory the contained user could write, as a home has to be."""
        root = Path(tempfile.mkdtemp(prefix="rk2-mounts-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        root.chmod(0o777)
        return root

    def test_only_what_the_runtime_mounts_is_inside_and_the_signing_key_is_not(self):
        root = self.contained()
        authority = tls.authority(root / "authority")

        mounts = isolation._mounts(
            fixtures.boundary(application=root, sdk=root, home=root), authority.certificate
        )

        destinations = [
            item.partition("dst=")[2].partition(",")[0] for item in mounts if item != "--mount"
        ]
        self.assertEqual(
            [isolation.CA_FILE, isolation.APPLICATION, isolation.SDK, isolation.HOME_DIR],
            destinations,
        )
        # The application and the SDK are what a launch is measured as, and the
        # home is the one place a child may write. Nothing carries the signing
        # key that certificate was issued from.
        self.assertEqual(3, sum(1 for item in mounts if item.endswith(",readonly")))
        self.assertNotIn(str(authority.key), " ".join(mounts))

    def test_a_mount_that_is_not_a_directory_is_refused_before_launch(self):
        with self.assertRaisesRegex(isolation.Unavailable, "not a directory"):
            isolation._mounts(fixtures.boundary(home=Path("/etc/hostname")), Path("/etc/hostname"))

    def test_no_mount_may_carry_the_operator_home_however_it_is_named(self):
        # The caller names the host directories, so "the child resolves the
        # runtime's credential and not the operator's" is checked rather than
        # trusted. Read-only is no defence: reading is what a credential file is
        # for. A directory *under* the operator's home is fine and usual --
        # the checkout and the installed SDK normally live there.
        operator = Path(os.path.expanduser("~")).resolve()
        root = self.contained()

        for field in ("application", "sdk", "home"):
            for named in (operator, operator.parent):
                with self.subTest(field=field, named=str(named)):
                    with self.assertRaisesRegex(isolation.Unavailable, "operator's home"):
                        isolation._mounts(
                            fixtures.boundary(**{field: named}), root / "authority.pem"
                        )

        inside = operator / "redkraken-not-a-real-checkout"
        self.assertFalse(isolation._carries_operator_home(inside))

    def test_a_home_the_contained_user_could_not_write_is_refused_before_launch(self):
        private = Path(tempfile.mkdtemp(prefix="rk2-private-"))
        self.addCleanup(shutil.rmtree, private, ignore_errors=True)
        private.chmod(0o700)

        # The child runs as nobody, and a home it cannot write is a session that
        # never starts. Refused here rather than diagnosed from a CLI that
        # failed inside a container the run has already thrown away.
        with self.assertRaisesRegex(isolation.Unavailable, "cannot write"):
            isolation._mounts(fixtures.boundary(home=private), private / "authority.pem")

        # And a read-only mount is not asked the question at all: nothing writes
        # to the SDK, so a directory nobody can write to is the contained one.
        mounts = isolation._mounts(fixtures.boundary(sdk=private), private / "root.pem")

        self.assertIn(f"type=bind,src={private},dst={isolation.SDK},readonly", mounts)


PUMPED = """
import json, sys

job = json.loads(sys.stdin.readline())
print("this line is not a call")
sys.stderr.write("the child said something on the other stream\\n")
answers = []
for index, verb in enumerate(job["ask"], start=1):
    sys.stdout.write(json.dumps({"rk2_call": {"verb": verb}, "id": index}) + "\\n")
    sys.stdout.flush()
    answers.append(json.loads(sys.stdin.readline()))
print(json.dumps({"answers": answers}))
"""

#: A child that says more on its other stream than a pipe holds, and says it
#: after asking for something and before reading the answer.
NOISY = """
import json, sys

job = json.loads(sys.stdin.readline())
sys.stdout.write(json.dumps({"rk2_call": {"verb": "one"}, "id": 1}) + "\\n")
sys.stdout.flush()
sys.stderr.write("n" * (256 * 1024))
sys.stderr.flush()
answer = json.loads(sys.stdin.readline())
print(json.dumps({"answers": [answer]}))
"""


class PumpTest(unittest.TestCase):
    """PH2-87: the launch pipe used both ways, without a container.

    `_pumped` is handed a whole argv and starts it, so a plain interpreter
    stands in for the engine here.  What is under test is not what Docker does
    with the arguments -- the tests above cover that -- but the one thing this
    ticket added: a child that asks for something mid-run gets an answer, and
    the caller still reads the result document out of what is left.
    """

    def pumped(self, job, answer, *, script=PUMPED, timeout=30.0):
        return isolation._pumped(
            [sys.executable, "-c", script],
            host_environment={"PATH": os.environ.get("PATH", "")},
            stdin=json.dumps(job) + "\n",
            timeout=timeout,
            answer=answer,
            engine="docker",
            name="rk2-agent-that-is-never-started",
        )

    def test_a_call_is_answered_and_never_reaches_the_caller(self):
        asked = []

        def answer(call):
            asked.append(dict(call))
            return {"served": True, "for": call["verb"]}

        child = self.pumped({"ask": ["one", "two"]}, answer)

        self.assertEqual(0, child.returncode)
        self.assertEqual([{"verb": "one"}, {"verb": "two"}], asked)
        # The frames are gone from the output and the ordinary lines are not.
        self.assertNotIn(isolation.CALL, child.stdout)
        self.assertIn("this line is not a call", child.stdout)
        self.assertIn("the child said something", child.stderr)
        # And the result document is still the last one, which is what the
        # supervisor reads a run's answer out of.
        result = json.loads(child.stdout.strip().splitlines()[-1])
        self.assertEqual(
            [{"served": True, "for": "one"}, {"served": True, "for": "two"}],
            [one[isolation.ANSWER] for one in result["answers"]],
        )
        self.assertEqual([1, 2], [one["id"] for one in result["answers"]])

    def test_a_handler_that_fails_answers_that_it_failed(self):
        # The child is owed a line whatever happens on this side. Without one
        # it waits on the pipe until the run's deadline, and what the operator
        # would read is a timeout rather than the failure that caused it.
        def answer(call):
            raise RuntimeError("the supervisor could not do that")

        child = self.pumped({"ask": ["one"]}, answer)

        result = json.loads(child.stdout.strip().splitlines()[-1])
        served = result["answers"][0][isolation.ANSWER]
        self.assertFalse(served["served"])
        self.assertEqual(isolation.UNANSWERED, served["reason"])
        self.assertIn("could not do that", served["detail"])

    def test_an_answer_larger_than_a_pipe_does_not_stop_the_run(self):
        # A pipe holds about sixty-four kilobytes and an answer carrying an
        # excerpt is routinely larger. Written inline it would block the loop
        # that is holding the run to its deadline.
        body = "x" * (512 * 1024)

        child = self.pumped({"ask": ["one"]}, lambda call: {"body": body})

        result = json.loads(child.stdout.strip().splitlines()[-1])
        self.assertEqual(body, result["answers"][0][isolation.ANSWER]["body"])

    def test_a_child_is_still_read_while_the_call_it_made_is_being_served(self):
        # A pipe holds about sixty-four kilobytes. Served on the loop that reads
        # the child, a call would stop that loop for as long as the tool behind
        # it takes -- and a child that keeps talking meanwhile fills its pipe
        # and stops, waiting on a supervisor that is waiting on the tool.
        def answer(call):
            time.sleep(0.5)
            return {"served": True}

        child = self.pumped({}, answer, script=NOISY)

        self.assertEqual(0, child.returncode)
        self.assertEqual(256 * 1024, len(child.stderr))
        result = json.loads(child.stdout.strip().splitlines()[-1])
        self.assertEqual({"served": True}, result["answers"][0][isolation.ANSWER])

    def test_the_deadline_still_falls_while_a_call_is_being_served(self):
        # The same loop is what holds the run to its deadline, so a call served
        # on it would let the container run for the whole of that tool's own
        # ceiling past the ceiling this run was started under.
        taken = []

        def answer(call):
            time.sleep(3.0)
            return {}

        with mock.patch.object(
            isolation, "remove", side_effect=lambda *given: taken.append(time.monotonic())
        ):
            started = time.monotonic()
            with self.assertRaises(isolation.Unavailable):
                self.pumped({"ask": ["one"]}, answer, timeout=0.5)

        # Taken away when its time was up, not when the call came back.
        self.assertLess(taken[0] - started, 2.0)

    def test_a_child_that_never_answers_is_taken_away_at_its_deadline(self):
        removed = []
        waiting = "import time\ntime.sleep(300)\n"

        with mock.patch.object(
            isolation, "remove", side_effect=lambda *given: removed.append(given[1])
        ):
            with self.assertRaises(isolation.Unavailable) as refused:
                self.pumped({"ask": []}, lambda call: {}, script=waiting, timeout=0.5)

        self.assertIn("exceeded its 0.5s runtime", str(refused.exception))
        self.assertEqual(["rk2-agent-that-is-never-started"], removed)


class ToolPlanTest(unittest.TestCase):
    """PH2-30: what a tool plan may say, decided before an engine is asked.

    Everything here is refused by reading the plan, so none of it needs a
    container: an argv that is not an argv, a ceiling that bounds nothing, a
    network that is not one of the two, and -- the one that matters -- a path
    that names somewhere other than the two directories the runtime mounts.
    The argument kinds already refuse a separator, so a plan that names a place
    is a plan something built rather than one the database produced, and it is
    refused twice for that reason.
    """

    def ceilings(self, **overrides) -> isolation.Ceilings:
        values = {
            "timeout_seconds": 20.0,
            "memory_mb": 256,
            "cpu_quota": 1.0,
            "pids_limit": 32,
            "max_output_bytes": 1024,
        }
        values.update(overrides)
        return isolation.Ceilings(**values)

    def staging(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="rk2-staging-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_an_argv_that_is_not_one_is_refused_before_an_engine_is_asked(self):
        container = isolation.ToolContainer(image="rk2-tool-image-that-is-never-started")

        for argv, expect in (
            ("/bin/true", "not one string"),
            ((), "non-empty argv"),
            (("/bin/true", ""), "non-empty argv"),
            (("/bin/true", "a\0b"), "non-empty argv"),
            (("/bin/true", 7), "non-empty argv"),
        ):
            with self.subTest(argv=argv):
                with self.assertRaisesRegex(isolation.Unavailable, expect):
                    isolation.run_tool(container, argv, ceilings=self.ceilings())

    def test_a_ceiling_that_bounds_nothing_and_a_network_that_is_not_one_are_refused(self):
        container = isolation.ToolContainer(image="rk2-tool-image-that-is-never-started")

        for ceilings in (self.ceilings(timeout_seconds=0), self.ceilings(max_output_bytes=0)):
            with self.subTest(ceilings=ceilings):
                with self.assertRaisesRegex(isolation.Unavailable, "positive timeout"):
                    isolation.run_tool(container, ("/bin/true",), ceilings=ceilings)

        with self.assertRaisesRegex(isolation.Unavailable, "no network or the proxy"):
            isolation.run_tool(
                container, ("/bin/true",), ceilings=self.ceilings(), network="host"
            )

    def test_an_input_path_that_names_a_place_is_refused(self):
        for path in ("/etc/passwd", "/input/../etc/passwd", "/input/sub/AF1", "/input"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(
                    isolation.Unavailable, f"not under {isolation.TOOL_INPUTS}"
                ):
                    isolation._staged(self.staging(), {path: b"x"}, ())

    def test_a_declared_output_that_is_not_a_bare_filename_is_refused(self):
        for name in ("../../etc/passwd", "/etc/passwd", "sub/report.json", ".."):
            with self.subTest(name=name):
                with self.assertRaisesRegex(isolation.Unavailable, "bare filename"):
                    isolation._staged(self.staging(), {}, (name,))

    def test_what_crosses_is_readable_and_only_the_workspace_is_writable(self):
        staging = self.staging()

        workspace = isolation._staged(
            staging, {f"{isolation.TOOL_INPUTS}/AF1": b"kept"}, ("report.json",)
        )

        inputs = staging / "input"
        self.assertEqual(b"kept", (inputs / "AF1").read_bytes())
        self.assertEqual(0o555, inputs.stat().st_mode & 0o777)
        self.assertEqual(0o444, (inputs / "AF1").stat().st_mode & 0o777)
        # The container's user is nameless and owns nothing, so the one place it
        # may write has to be writable by everyone. What makes that safe is the
        # parent: `run_tool` puts both under a directory only this process can
        # traverse, which is what `mkdtemp` means.
        self.assertEqual(0o777, workspace.stat().st_mode & 0o777)
        self.assertEqual(0o700, staging.stat().st_mode & 0o777)

    def test_a_tool_that_declares_no_output_is_given_no_workspace(self):
        # Not an empty directory: a tool with nothing to write has nothing
        # writable at all, and the difference is one mount that does not exist.
        self.assertIsNone(isolation._staged(self.staging(), {}, ()))

    def test_a_stream_says_whether_it_is_a_prefix_of_something_longer(self):
        self.assertFalse(isolation.Captured(b"kept", 4).truncated)
        self.assertTrue(isolation.Captured(b"kept", 4096).truncated)

        bounded = isolation.Captured(b"", 0)
        self.assertTrue(isolation.ToolProcess(0, bounded, bounded).succeeded)
        for answer in (
            isolation.ToolProcess(1, bounded, bounded),
            isolation.ToolProcess(None, bounded, bounded, timed_out=True),
            isolation.ToolProcess(0, bounded, bounded, overflowed=True),
        ):
            with self.subTest(answer=answer):
                self.assertFalse(answer.succeeded)


@unittest.skipUnless(LIVE, REASON)
class ToolIsolationTest(unittest.TestCase):
    """PH2-30 criteria 2 and 4: a tool has no wire, and its output is bounded.

    Every claim `run_tool`'s docstring makes about the container it starts is
    asked of a real one here, because each of them is a flag that is either on
    the command line or is not: no interface, a read-only root filesystem, the
    nameless user, an input mount nothing can write, and the two bounds that
    have to end a run rather than describe it afterwards.

    The image is the Agent test image, which is a stand-in for the tool image an
    installation builds. What is measured is the boundary, and the boundary does
    not depend on which executables are inside it.
    """

    @classmethod
    def setUpClass(cls):
        if shutil.which("docker") is None:
            raise unittest.SkipTest("docker is not on PATH")
        if docker("image", "inspect", fixtures.AGENT_IMAGE, check=False).returncode:
            raise unittest.SkipTest(f"the local Agent test image is absent: {fixtures.AGENT_IMAGE}")
        cls.container = isolation.ToolContainer(image=fixtures.AGENT_IMAGE)

    def ceilings(self, **overrides) -> isolation.Ceilings:
        values = {
            "timeout_seconds": 30.0,
            "memory_mb": 256,
            "cpu_quota": 1.0,
            "pids_limit": 32,
            "max_output_bytes": 1024,
        }
        values.update(overrides)
        return isolation.Ceilings(**values)

    def test_one_input_crosses_and_comes_back_on_stdout(self):
        answer = isolation.run_tool(
            self.container,
            ("/bin/cat", f"{isolation.TOOL_INPUTS}/AF1"),
            ceilings=self.ceilings(),
            inputs={f"{isolation.TOOL_INPUTS}/AF1": b'{"host": "example.test"}'},
        )

        self.assertTrue(answer.succeeded, answer.stderr.data)
        self.assertEqual(b'{"host": "example.test"}', answer.stdout.data)
        self.assertEqual(24, answer.stdout.produced)
        self.assertFalse(answer.stdout.truncated)
        self.assertEqual(b"", answer.stderr.data)

    def test_the_tool_has_no_route_out_and_cannot_write_what_it_was_given(self):
        probe = fixtures.PROBE + """
print(json.dumps({
    'internet_tcp': reaches('1.1.1.1', 443),
    'rootfs': writable('/rk2-root-write'),
    'input': writable('/input/AF1'),
    'scratch': writable(os.environ['TMPDIR'] + '/scratch'),
    'tmp': writable('/tmp/scratch'),
    'uid': os.getuid(),
}))
"""
        answer = isolation.run_tool(
            self.container,
            ("python3", "-c", probe),
            ceilings=self.ceilings(),
            inputs={f"{isolation.TOOL_INPUTS}/AF1": b"x"},
        )

        self.assertTrue(answer.succeeded, answer.stderr.data)
        facts = json.loads(answer.stdout.data)
        self.assertFalse(facts["internet_tcp"])
        self.assertFalse(facts["rootfs"])
        self.assertFalse(facts["input"])
        # One writable place, and it is the one the runtime mounted and named in
        # the environment. `/tmp` is part of a read-only root here, so a tool
        # that writes where a tool usually writes fails rather than escaping.
        self.assertTrue(facts["scratch"])
        self.assertFalse(facts["tmp"])
        self.assertEqual(isolation.UID, facts["uid"])

    def test_every_ceiling_the_registry_set_is_one_the_kernel_is_holding(self):
        # Read from inside rather than off the command line: a flag the engine
        # accepted and did not apply looks identical in an argv and is the whole
        # difference between a bounded run and an unbounded one.
        probe = """
import json

def read(path):
    with open(path) as handle:
        return handle.read().strip()

print(json.dumps({
    'memory': read('/sys/fs/cgroup/memory.max'),
    'swap': read('/sys/fs/cgroup/memory.swap.max'),
    'cpu': read('/sys/fs/cgroup/cpu.max'),
    'pids': read('/sys/fs/cgroup/pids.max'),
}))
"""
        ceilings = self.ceilings(memory_mb=64, cpu_quota=0.5, pids_limit=16)

        answer = isolation.run_tool(self.container, ("python3", "-c", probe), ceilings=ceilings)

        self.assertTrue(answer.succeeded, answer.stderr.data)
        facts = json.loads(answer.stdout.data)
        self.assertEqual(str(64 * 1024 * 1024), facts["memory"])
        # Nothing to page into: a memory ceiling a container may swap past is a
        # ceiling on how fast it uses the machine rather than on how much.
        self.assertEqual("0", facts["swap"])
        quota, period = facts["cpu"].split()
        self.assertEqual(0.5, int(quota) / int(period))
        self.assertEqual("16", facts["pids"])

    def test_output_past_the_bound_ends_the_run_and_says_how_much_there_was(self):
        started = time.monotonic()

        answer = isolation.run_tool(
            self.container,
            ("python3", "-c", "import sys\nwhile True: sys.stdout.write('x' * 4096)\n"),
            ceilings=self.ceilings(max_output_bytes=1024, timeout_seconds=30),
        )

        self.assertTrue(answer.overflowed)
        self.assertFalse(answer.succeeded)
        self.assertEqual(1024, len(answer.stdout.data))
        self.assertGreater(answer.stdout.produced, 1024)
        self.assertTrue(answer.stdout.truncated)
        # The bound is what ended it, so the run is over long before the timeout
        # it was also given. A bound applied to output already read would leave
        # this loop running for the whole thirty seconds.
        self.assertLess(time.monotonic() - started, 25)

    def test_time_past_the_deadline_ends_the_run(self):
        started = time.monotonic()

        answer = isolation.run_tool(
            self.container, ("sleep", "60"), ceilings=self.ceilings(timeout_seconds=3)
        )

        self.assertTrue(answer.timed_out)
        self.assertFalse(answer.succeeded)
        self.assertLess(time.monotonic() - started, 20)

    def test_a_declared_output_is_read_back_and_a_link_is_not(self):
        answer = isolation.run_tool(
            self.container,
            (
                "python3",
                "-c",
                "import os\n"
                "open('report.json', 'w').write('{\"kept\": true}')\n"
                "os.symlink('/etc/hostname', 'sneaky.txt')\n",
            ),
            ceilings=self.ceilings(),
            outputs=("report.json", "sneaky.txt", "never.txt"),
        )

        self.assertTrue(answer.succeeded, answer.stderr.data)
        self.assertEqual(b'{"kept": true}', answer.outputs["report.json"].data)
        # The workspace is owned by the container's own user, so a declared
        # output written as a link is a name the tool chose and the supervisor
        # would resolve on the host. It is skipped rather than followed.
        self.assertNotIn("sneaky.txt", answer.outputs)
        self.assertNotIn("never.txt", answer.outputs)

    def test_a_tool_that_wants_the_proxy_and_has_no_door_is_refused(self):
        with self.assertRaisesRegex(isolation.Unavailable, "no egress door"):
            isolation.run_tool(
                self.container, ("/bin/true",), ceilings=self.ceilings(), network="proxy"
            )


@unittest.skipUnless(LIVE, REASON)
class AgentContainerIsolationTest(unittest.TestCase):
    """A child has one peer even when it knows every forbidden address."""

    @classmethod
    def setUpClass(cls):
        if shutil.which("docker") is None:
            raise unittest.SkipTest("docker is not on PATH")
        if docker("image", "inspect", fixtures.AGENT_IMAGE, check=False).returncode:
            raise unittest.SkipTest(f"the local Agent test image is absent: {fixtures.AGENT_IMAGE}")

        suffix = uuid.uuid4().hex[:12]
        cls.agent_network = f"rk2-agent-{suffix}"
        cls.target_network = f"rk2-target-{suffix}"
        cls.control_network = f"rk2-control-{suffix}"
        cls.open_network = f"rk2-open-{suffix}"
        cls.proxy = f"rk2-proxy-{suffix}"
        cls.target = f"rk2-target-{suffix}"
        cls.control = f"rk2-control-{suffix}"
        cls.root = Path(tempfile.mkdtemp(prefix="rk2-isolation-"))
        cls.authority = tls.authority(cls.root / "authority")

        try:
            for network in (cls.agent_network, cls.target_network, cls.control_network):
                docker("network", "create", "--internal", network)
            docker("network", "create", cls.open_network)
            fixtures.listener(cls.proxy, cls.agent_network, 18080)
            fixtures.listener(cls.target, cls.target_network, 18081)
            fixtures.listener(cls.control, cls.control_network, 5432)
            docker("network", "connect", cls.target_network, cls.proxy)
            docker("network", "connect", cls.control_network, cls.proxy)
            cls.target_ip = fixtures.address(cls.target, cls.target_network)
            cls.control_ip = fixtures.address(cls.control, cls.control_network)
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        for container in (
            getattr(cls, "proxy", ""),
            getattr(cls, "target", ""),
            getattr(cls, "control", ""),
        ):
            if container:
                docker("rm", "--force", container, check=False)
        for network in (
            getattr(cls, "agent_network", ""),
            getattr(cls, "target_network", ""),
            getattr(cls, "control_network", ""),
            getattr(cls, "open_network", ""),
        ):
            if network:
                docker("network", "rm", network, check=False)
        root = getattr(cls, "root", None)
        if root is not None:
            shutil.rmtree(root, ignore_errors=True)

    def boundary(self, *, network: str | None = None, **supplied) -> isolation.AgentContainer:
        """The described boundary, with the names of things that exist."""
        return fixtures.boundary(
            network=network or self.agent_network,
            proxy_container=self.proxy,
            proxy_url=f"http://{self.proxy}:18080",
            certificate=self.authority.certificate,
            **supplied,
        )

    def test_only_the_proxy_is_reachable_and_only_the_run_root_is_installed(self):
        probe = fixtures.PROBE + """
written = True
try:
    open('/rk2-root-write', 'w').close()
except OSError:
    written = False

print(json.dumps({
    'proxy': reaches(os.environ['HTTP_PROXY'].split('//', 1)[1].split(':')[0], 18080),
    'internet_tcp': reaches('1.1.1.1', 443),
    'external_dns': resolves('example.com'),
    'target_name': resolves('rk2-target-does-not-share-the-agent-network'),
    'target_ip': reaches(os.environ['RK_TEST_TARGET_IP'], 18081),
    'control_ip': reaches(os.environ['RK_TEST_CONTROL_IP'], 5432),
    'proxy_variables': {key: os.environ.get(key) for key in (
        'HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy')},
    'bypass': {key: os.environ.get(key) for key in ('NO_PROXY', 'no_proxy')},
    'trust': {key: os.environ.get(key) for key in (
        'SSL_CERT_FILE', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE',
        'NODE_EXTRA_CA_CERTS')},
    'store': os.environ.get('SSL_CERT_DIR'),
    'ca_readable': os.path.isfile('/run/redkraken-ca.pem'),
    'key_visible': os.path.exists('/run/ca-key.pem')
        or os.path.exists('/run/redkraken-ca-key.pem'),
    'rootfs_writable': written,
    'uid': os.getuid(),
    'watched': sorted(key for key in os.environ if key in %s),
}))
""" % repr(set(_startup.WATCHED_ENV_VECTORS))
        # These two names are test-only coordinates for negative probes. They
        # are deliberately outside the runtime allowlist, so pass them as argv
        # additions rather than asking production to inherit host state.
        probe = probe.replace(
            "os.environ['RK_TEST_TARGET_IP']", repr(self.target_ip)
        ).replace("os.environ['RK_TEST_CONTROL_IP']", repr(self.control_ip))

        result = isolation.run(
            self.boundary(),
            ("python3", "-c", probe),
            source_environment={
                "LANG": "C.UTF-8",
                "ANTHROPIC_API_KEY": "must-not-enter-the-Agent",
                "CLAUDE_CODE_USE_BEDROCK": "must-not-enter-the-Agent",
            },
            timeout=15,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        facts = json.loads(result.stdout)
        proxy_url = f"http://{self.proxy}:18080"
        self.assertTrue(facts["proxy"])
        self.assertFalse(facts["internet_tcp"])
        self.assertFalse(facts["external_dns"])
        self.assertFalse(facts["target_name"])
        self.assertFalse(facts["target_ip"])
        self.assertFalse(facts["control_ip"])
        self.assertEqual({proxy_url}, set(facts["proxy_variables"].values()))
        self.assertEqual({""}, set(facts["bypass"].values()))
        self.assertEqual({isolation.CA_FILE}, set(facts["trust"].values()))
        self.assertEqual("", facts["store"])
        self.assertTrue(facts["ca_readable"])
        self.assertFalse(facts["key_visible"])
        self.assertFalse(facts["rootfs_writable"])
        self.assertEqual(65534, facts["uid"])
        self.assertEqual([], facts["watched"])

    def test_a_non_internal_network_is_refused_before_launch(self):
        with self.assertRaisesRegex(isolation.Unavailable, "not internal"):
            isolation.run(self.boundary(network=self.open_network), ("true",))

    def test_a_second_agent_network_peer_is_refused_before_launch(self):
        docker("network", "connect", self.agent_network, self.target)
        try:
            with self.assertRaisesRegex(isolation.Unavailable, "peers other than the proxy"):
                isolation.run(self.boundary(), ("true",))
        finally:
            docker("network", "disconnect", self.agent_network, self.target, check=False)

    def test_a_second_launch_inside_the_first_s_window_is_refused(self):
        """PH2-85 criteria 1 and 2: the window between the check and the launch.

        The refusal above is what containment between two children rested on:
        every launch reads the network first and stops if anything but the door
        is on it, so a second child cannot come up beside a first. That held for
        two launches that were ordered, and nothing ordered them -- it is a
        check-then-act, the engine holds nothing between the read and the `run`,
        and one network name serves a whole installation, so two launches inside
        each other's window both read a clear network and both attached.

        `isolation.held` is what orders them now, and this is the overlap it is
        claimed against: the second launch is made from inside the first's
        window, at the exact moment the engine is about to be asked to start the
        first child, which is where the old gap was demonstrated. What comes
        back is a typed refusal naming the network rather than a second peer,
        and the first child then runs to completion -- a claim that refused the
        launch holding it would be a boundary that never launches anything.

        What is ordered is this installation's launches. A peer attached to the
        Agent network by something that is not a launch -- an operator's own
        `docker network connect` -- is not this claim's subject and never was:
        it is what `one_peer` reads, and the next launch is refused for it.
        """
        started = threading.Event()
        release = threading.Event()
        launch = isolation.subprocess.run

        def waiting(command, **keywords):
            if len(command) > 1 and command[1] == "run":
                started.set()
                if not release.wait(60):
                    raise AssertionError("the first launch was never released")
            return launch(command, **keywords)

        with mock.patch.object(isolation.subprocess, "run", waiting):
            with futures.ThreadPoolExecutor(max_workers=1) as pool:
                first = pool.submit(isolation.run, self.boundary(), ("true",), timeout=60)
                try:
                    self.assertTrue(started.wait(60))
                    with self.assertRaisesRegex(
                        isolation.Unavailable, "holds the Agent network"
                    ):
                        isolation.run(self.boundary(), ("true",), timeout=60)
                finally:
                    release.set()
                self.assertEqual(0, first.result(timeout=120).returncode)

    def test_a_child_gets_the_seeded_home_and_not_the_last_child_s(self):
        """PH2-86 criteria 1, 2 and 4: the home a child gets is its own.

        `RK_AGENT_HOME` was one directory per installation, mounted writable
        because the CLI resolves a credential from a home and keeps its state
        beside it. So what one child wrote the next child read, and could not
        tell from its own -- ticket 80's planted code, at no privilege.

        Two children, one after the other, because ticket 85's claim is what
        decides that now: two of one installation are never on the Agent network
        at once. The first is handed the template the operator seeded and writes
        its session state; the second is handed the template again. What the
        first wrote is not there, the credential the operator put there is, and
        the template on the host is what it was before either ran -- the run's
        writes went to a copy that no longer exists.
        """
        home = Path(tempfile.mkdtemp(prefix="rk2-home-", dir=self.root))
        # The mode the runtime demands of a home: the child is a user this
        # machine has no name for, so a directory only the operator can write is
        # refused before anything starts.
        home.chmod(0o777)
        seeded = home / "credential.json"
        seeded.write_text('{"the operator": "seeded this"}', encoding="utf-8")
        seeded.chmod(0o666)

        probe = fixtures.PROBE + """
import sys

mine = sys.argv[1]
home = os.environ['HOME']
found = sorted(os.listdir(home))
read = {}
for name in found:
    with open(os.path.join(home, name)) as handle:
        read[name] = handle.read()

with open(os.path.join(home, mine), 'w') as handle:
    handle.write('the session state of ' + mine)

print(json.dumps({'home': home, 'found': found, 'read': read}))
"""

        def child(mine: str) -> dict:
            result = isolation.run(
                self.boundary(home=home),
                ("python3", "-c", probe, mine),
                timeout=60,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            return json.loads(result.stdout)

        first = child("first")
        second = child("second")

        self.assertEqual([isolation.HOME_DIR] * 2, [first["home"], second["home"]])
        # Each was handed the same seeded home, and neither was handed the
        # other's session state.
        self.assertEqual(["credential.json"], first["found"])
        self.assertEqual(["credential.json"], second["found"])
        self.assertEqual(
            {"credential.json": '{"the operator": "seeded this"}'},
            second["read"],
        )
        # And the template is what the operator left, whatever the children did
        # inside their copies of it.
        self.assertEqual(["credential.json"], sorted(item.name for item in home.iterdir()))

    def test_the_operator_s_own_credential_never_reaches_a_child_at_all(self):
        """Ticket 146: the file the operator authenticated with stops crossing.

        It used to be mounted in place so that the CLI's own refresh landed
        where the operator would read it next. That refresh is a rename, which
        breaks the link, and the file it leaves is owned by the operator and
        unwritable by uid 65534 -- so the arrangement ends the installation it
        was built for, on a schedule nobody controls.

        What a child sees now is a home with no credential in it. The operator's
        file is untouched on the host, and what a run authenticates with is the
        setup token the supervisor hands it on stdin.
        """
        home = Path(tempfile.mkdtemp(prefix="rk2-home-", dir=self.root))
        home.chmod(0o777)
        (home / ".claude").mkdir()
        (home / ".claude").chmod(0o777)
        credential = home / ".claude" / ".credentials.json"
        seeded = '{"accessToken": "RK-SYNTHETIC-SETUP-TOKEN-2f7c"}'
        credential.write_text(seeded, encoding="utf-8")
        credential.chmod(0o600)

        probe = fixtures.PROBE + """
holder = os.path.join(os.environ['HOME'], '.claude')
print(json.dumps({
    'holder': os.path.isdir(holder),
    'found': sorted(os.listdir(holder)) if os.path.isdir(holder) else [],
}))
"""

        result = isolation.run(
            self.boundary(home=home), ("python3", "-c", probe), timeout=60
        )
        self.assertEqual(0, result.returncode, result.stderr)
        inside = json.loads(result.stdout)

        # The directory the CLI keeps its state in is there; the credential is
        # not, and no sentinel of it crossed on any stream.
        self.assertTrue(inside["holder"])
        self.assertEqual([], inside["found"])
        self.assertNotIn("RK-SYNTHETIC-SETUP-TOKEN-2f7c", result.stdout + result.stderr)
        # And the operator's own file is exactly what it was.
        self.assertEqual(seeded, credential.read_text(encoding="utf-8"))

    def test_a_tool_on_the_proxy_adapter_gets_its_own_network_and_gives_it_back(self):
        # PH2-30 criterion 2, the half that is not a refusal. A tool that
        # declares the adapter is put on a network of its own with the proxy as
        # its only peer, rather than onto the Agent's -- which already has one
        # peer and would refuse a second, and which the tool has no business
        # sharing. The network exists for the run and is gone afterwards.
        #
        # PH2-31 criterion 2 asks for the same of a browser, which is a tool on
        # this adapter and nothing else. So the name half is probed here too,
        # rather than only on the Agent boundary: a name that resolved would be
        # a second egress the door never sees.
        probe = fixtures.PROBE + """
print(json.dumps({
    'proxy': reaches(os.environ['HTTP_PROXY'].split('//', 1)[1].split(':')[0], 18080),
    'target_ip': reaches(%r, 18081),
    'internet_tcp': reaches('1.1.1.1', 443),
    'external_dns': resolves('example.com'),
    'target_name': resolves(%r),
}))
""" % (self.target_ip, self.target)
        before = docker("network", "ls", "--format", "{{.Name}}").stdout.split()

        answer = isolation.run_tool(
            isolation.ToolContainer(image=fixtures.AGENT_IMAGE, door=self.boundary()),
            ("python3", "-c", probe),
            ceilings=isolation.Ceilings(
                timeout_seconds=30.0,
                memory_mb=256,
                cpu_quota=1.0,
                pids_limit=32,
                max_output_bytes=4096,
            ),
            network="proxy",
        )

        self.assertTrue(answer.succeeded, answer.stderr.data)
        facts = json.loads(answer.stdout.data)
        self.assertTrue(facts["proxy"])
        self.assertFalse(facts["target_ip"])
        self.assertFalse(facts["internet_tcp"])
        self.assertFalse(facts["external_dns"])
        self.assertFalse(facts["target_name"])
        self.assertEqual(
            before, docker("network", "ls", "--format", "{{.Name}}").stdout.split()
        )

    # -- PH2-78: where this machine is, seen from inside the door ---------------

    def engine(self) -> str:
        return isolation.engine_for(isolation.ENGINE)

    def routable(self) -> str:
        """Attach the door to the one routable network, for this test only.

        Given back on the way out, because every other case in this class is
        about a door whose attachments are all internal: a network left
        connected here would be a route off the Agent network that the
        containment proofs above would then be measuring.
        """
        docker("network", "connect", self.open_network, self.proxy)
        self.addCleanup(
            docker, "network", "disconnect", self.open_network, self.proxy, check=False
        )
        return docker(
            "network", "inspect", "--format",
            "{{(index .IPAM.Config 0).Gateway}}", self.open_network,
        ).stdout.strip()

    def test_a_door_with_no_route_off_the_agent_network_answers_with_no_address(self):
        # The arrangement this class holds for every other case: three internal
        # networks and nothing else. There is no address this machine could be
        # reached at from in there, so an evaluation that asked is refused rather
        # than told a number that does not answer.
        with self.assertRaises(isolation.Unavailable) as refused:
            isolation.host_route(self.engine(), self.proxy)

        self.assertIn("no network with a route off it", str(refused.exception))

    def test_the_address_is_the_gateway_of_the_one_routable_attachment(self):
        # And it is this machine: a socket bound there is reached from inside the
        # door. That is the whole property the fixture route rests on -- the
        # evaluator serves its fixture at this address, and the door dials it.
        gateway = self.routable()

        answered = isolation.host_route(self.engine(), self.proxy)

        self.assertEqual(gateway, answered)
        listening = socket.create_server((answered, 0))
        self.addCleanup(listening.close)
        reached = docker(
            "exec", self.proxy, "python3", "-c", fixtures.REACHED,
            answered, str(listening.getsockname()[1]),
            check=False,
        )
        self.assertEqual(0, reached.returncode, reached.stderr)

    def test_a_child_cannot_reach_the_address_the_door_answers_this_machine_at(self):
        # The other half, and the reason a fixture may be served there at all:
        # the routable attachment is the door's alone, so the address that makes
        # the fixture reachable does not also make it reachable from the child
        # being graded against it.
        self.routable()
        answered = isolation.host_route(self.engine(), self.proxy)
        listening = socket.create_server((answered, 0))
        self.addCleanup(listening.close)
        port = listening.getsockname()[1]
        probe = fixtures.PROBE + """
print(json.dumps({'host': reaches(%r, %d)}))
""" % (answered, port)

        result = isolation.run(self.boundary(), ("python3", "-c", probe), timeout=20)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(json.loads(result.stdout)["host"])

    def test_a_door_on_two_routable_networks_has_no_one_address(self):
        # Two answers to "where is this machine" is no answer: a fixture bound at
        # one of them would be reachable at an address the Receipt does not name,
        # and a run that guessed wrong would grade a Playbook against nothing.
        second = f"{self.open_network}-second"
        docker("network", "create", second)
        self.addCleanup(docker, "network", "rm", second, check=False)
        self.routable()
        docker("network", "connect", second, self.proxy)
        self.addCleanup(docker, "network", "disconnect", second, self.proxy, check=False)

        with self.assertRaises(isolation.Unavailable) as refused:
            isolation.host_route(self.engine(), self.proxy)

        self.assertIn("more than one routable network", str(refused.exception))


@unittest.skipUnless(LIVE, REASON)
class BrowserContainerIsolationTest(unittest.TestCase):
    """PH2-62 criterion 3: the browser's boundary, probed from the browser image.

    The case above proves the proxy adapter contains a tool, using the Agent
    image as a stand-in. That is the right stand-in for a tool, and it is the
    wrong one for the browser: the browser image is built by an installation
    out of a headless Chrome distribution, it is the largest and least
    controlled thing this harness starts, and it is the one image whose
    contents an operator did not write. An image can carry its own resolver
    configuration, its own certificate store and its own proxy defaults, and
    none of that is visible in the flags `run_tool` passes. So the question is
    asked again, of the image that actually runs.

    Four destinations, which are the four ways out a browser could have:

    * raw TCP to an address on the internet,
    * a name resolved outside the run's own network,
    * the control and provisioning ports of the machine the harness runs on,
    * and HTTP or HTTPS straight to the target, on the ports a browser speaks.

    Each of them answers from somewhere -- that is what the second case here is
    for. A containment proof against ports nothing is listening on is a proof
    that the test environment is empty, and the two cases together are what
    make the first one a statement about the boundary.

    The probe is python3 rather than Chrome because what is being measured is
    the container's routing, and a browser that could not reach an address
    would be indistinguishable from a browser that chose not to. Chrome runs in
    this image over the same interfaces, under the same environment, on the
    same network `run_tool` builds; `BrowserCommandTest` in the live suite is
    where a real one walks a real plan through the real door.
    """

    #: What the door listens on inside its own container, as everywhere else in
    #: this suite: the tool is told about the door as a URL, and a port the
    #: engine chose would have to be read back before that URL could be written.
    DOOR = 18080

    #: What the target answers on. The two a browser speaks unprompted, and the
    #: one the rest of this suite uses, so a route that opened would be caught
    #: whichever port it opened to.
    TARGET_PORTS = (80, 443, 18081)

    #: What the machine running the harness answers on: the database, and the
    #: port a provisioning run publishes. A browser that reached either would be
    #: inside the control plane rather than inside an engagement.
    CONTROL_PORTS = (5432, 55433)

    @classmethod
    def setUpClass(cls):
        if shutil.which("docker") is None:
            raise unittest.SkipTest("docker is not on PATH")
        for image, reason in (
            (fixtures.AGENT_IMAGE, f"the local Agent test image is absent: {fixtures.AGENT_IMAGE}"),
            (fixtures.BROWSER_IMAGE, f"{fixtures.BROWSER_REASON}; {fixtures.BROWSER_IMAGE} is absent"),
        ):
            if docker("image", "inspect", image, check=False).returncode:
                raise unittest.SkipTest(reason)

        suffix = uuid.uuid4().hex[:12]
        cls.door_network = f"rk2-browser-door-{suffix}"
        cls.target_network = f"rk2-browser-target-{suffix}"
        cls.control_network = f"rk2-browser-control-{suffix}"
        cls.proxy = f"rk2-browser-proxy-{suffix}"
        cls.target = f"rk2-browser-web-{suffix}"
        cls.control = f"rk2-browser-control-{suffix}"
        cls.root = Path(tempfile.mkdtemp(prefix="rk2-browser-isolation-"))
        cls.authority = tls.authority(cls.root / "authority")

        try:
            for network in (cls.door_network, cls.target_network, cls.control_network):
                docker("network", "create", "--internal", network)
            fixtures.listener(cls.proxy, cls.door_network, cls.DOOR)
            fixtures.listener(cls.target, cls.target_network, *cls.TARGET_PORTS)
            fixtures.listener(cls.control, cls.control_network, *cls.CONTROL_PORTS)
            # The proxy joins both, so every address the browser is denied is an
            # address something else on this engine reaches.
            docker("network", "connect", cls.target_network, cls.proxy)
            docker("network", "connect", cls.control_network, cls.proxy)
            cls.target_ip = fixtures.address(cls.target, cls.target_network)
            cls.control_ip = fixtures.address(cls.control, cls.control_network)
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        for container in (
            getattr(cls, "proxy", ""),
            getattr(cls, "target", ""),
            getattr(cls, "control", ""),
        ):
            if container:
                docker("rm", "--force", container, check=False)
        for network in (
            getattr(cls, "door_network", ""),
            getattr(cls, "target_network", ""),
            getattr(cls, "control_network", ""),
        ):
            if network:
                docker("network", "rm", network, check=False)
        root = getattr(cls, "root", None)
        if root is not None:
            shutil.rmtree(root, ignore_errors=True)

    def door(self) -> isolation.AgentContainer:
        """The boundary the browser's door is described by, with real names."""
        return fixtures.boundary(
            image=fixtures.BROWSER_IMAGE,
            network=self.door_network,
            proxy_container=self.proxy,
            proxy_url=f"http://{self.proxy}:{self.DOOR}",
            certificate=self.authority.certificate,
        )

    def probe(self, source: str) -> dict:
        """Run one probe inside the browser image, on the proxy adapter."""
        answer = isolation.run_tool(
            isolation.ToolContainer(image=fixtures.BROWSER_IMAGE, door=self.door()),
            ("python3", "-c", fixtures.PROBE + source),
            ceilings=isolation.Ceilings(
                timeout_seconds=120.0,
                # The ceilings the browser really runs under, so a probe that
                # could not start under them would be telling us something.
                memory_mb=1024,
                cpu_quota=2.0,
                pids_limit=256,
                max_output_bytes=8192,
            ),
            network="proxy",
        )

        self.assertTrue(answer.succeeded, answer.stderr.data)
        return json.loads(answer.stdout.data)

    def test_the_browser_reaches_the_door_and_no_other_route_out(self):
        facts = self.probe("""
print(json.dumps({
    'door': reaches(os.environ['HTTP_PROXY'].split('//', 1)[1].split(':')[0], %r),
    'internet_tcp': reaches('1.1.1.1', 443),
    'external_dns': resolves('example.com'),
    'target_name': resolves(%r),
    'target_http': reaches(%r, 80),
    'target_https': reaches(%r, 443),
    'target_other': reaches(%r, 18081),
    'control_postgres': reaches(%r, 5432),
    'control_provisioning': reaches(%r, 55433),
    'rootfs_writable': writable('/rk2-root-write'),
    'uid': os.getuid(),
}))
""" % (
            self.DOOR,
            self.target,
            self.target_ip,
            self.target_ip,
            self.target_ip,
            self.control_ip,
            self.control_ip,
        ))

        self.assertTrue(facts["door"])
        self.assertFalse(facts["internet_tcp"])
        self.assertFalse(facts["external_dns"])
        self.assertFalse(facts["target_name"])
        self.assertFalse(facts["target_http"])
        self.assertFalse(facts["target_https"])
        self.assertFalse(facts["target_other"])
        self.assertFalse(facts["control_postgres"])
        self.assertFalse(facts["control_provisioning"])
        self.assertFalse(facts["rootfs_writable"])
        self.assertEqual(isolation.UID, facts["uid"])

    def test_every_denied_address_is_one_that_answers_from_outside(self):
        # The other half of the case above, and the reason it means anything.
        # The proxy sits on all three networks, so it is the vantage point that
        # is allowed to reach what the browser is not.
        for host, ports in (
            (self.target_ip, self.TARGET_PORTS),
            (self.control_ip, self.CONTROL_PORTS),
        ):
            for port in ports:
                with self.subTest(host=host, port=port):
                    reached = docker(
                        "exec", self.proxy, "python3", "-c", fixtures.REACHED,
                        host, str(port), check=False,
                    )
                    self.assertEqual(0, reached.returncode, reached.stderr)

    def test_the_browser_is_told_about_the_door_and_about_no_way_around_it(self):
        facts = self.probe("""
print(json.dumps({
    'proxy_variables': {key: os.environ.get(key) for key in (
        'HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy')},
    'bypass': {key: os.environ.get(key) for key in ('NO_PROXY', 'no_proxy')},
    'trust': {key: os.environ.get(key) for key in (
        'SSL_CERT_FILE', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE',
        'NODE_EXTRA_CA_CERTS')},
    'store': os.environ.get('SSL_CERT_DIR'),
    'ca_readable': os.path.isfile(%r),
    'key_visible': os.path.exists('/run/ca-key.pem')
        or os.path.exists('/run/redkraken-ca-key.pem'),
    'watched': sorted(key for key in os.environ if key in %s),
}))
""" % (isolation.CA_FILE, repr(set(_startup.WATCHED_ENV_VECTORS))))

        proxy_url = f"http://{self.proxy}:{self.DOOR}"
        self.assertEqual({proxy_url}, set(facts["proxy_variables"].values()))
        # An empty bypass list rather than an absent one: a variable that is not
        # set is one an image's own default can fill in.
        self.assertEqual({""}, set(facts["bypass"].values()))
        self.assertEqual({isolation.CA_FILE}, set(facts["trust"].values()))
        self.assertEqual("", facts["store"])
        self.assertTrue(facts["ca_readable"])
        self.assertFalse(facts["key_visible"])
        self.assertEqual([], facts["watched"])


class BrowserEgressFlagTest(unittest.TestCase):
    """PH2-31 story 121: the page's one way out, including to this container.

    The driver runs inside the boundary and the boundary is a network with one
    peer, so what is left to decide is what chromium exempts from the proxy of
    its own accord. It exempts loopback, and this container has two loopback
    ports: the shim the door is behind and chromium's own debugger. A page that
    could reach either would be a request with no Receipt and no scope decision
    -- a second network path, which is the one thing the story names.
    """

    def argv(self) -> list[str]:
        plan = {"viewport_width": 1280, "viewport_height": 800, "certificate_pin": "pin"}
        with mock.patch.object(browser_driver.subprocess, "Popen") as started:
            browser_driver.start_browser(plan, None)
        return list(started.call_args.args[0])

    def test_loopback_is_not_exempt_from_the_proxy_the_door_is_behind(self):
        self.assertIn("--proxy-bypass-list=<-loopback>", self.argv())

    def test_the_bypass_is_stated_wherever_the_proxy_is(self):
        # One flag without the other is the hole: a proxy chromium is pointed at
        # and a destination it decides to reach around it.
        argv = self.argv()
        self.assertTrue(
            any(item.startswith("--proxy-server=") for item in argv)
            and any(item.startswith("--proxy-bypass-list=") for item in argv),
            argv,
        )


if __name__ == "__main__":
    unittest.main()


class SetupTokenTest(unittest.TestCase):
    """Ticket 146: the one credential a child is given, and what refuses it.

    Every case here is about a file this process reads and hands on. The token
    itself is a sentinel, and no assertion prints it: what a refusal may carry
    is the path, the property that failed and the remedy, because a refusal an
    operator pastes into a ticket has to be safe to paste.
    """

    SENTINEL = "RK-SYNTHETIC-SETUP-TOKEN-2f7c"

    def installed(self, value: str = SENTINEL, *, mode: int = 0o600) -> Path:
        """A token file as `tools/setup-agent-oauth.sh` leaves one."""
        directory = Path(tempfile.mkdtemp(prefix="rk2-token-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        directory.chmod(0o700)
        path = directory / "claude-oauth-token"
        path.write_text(value, encoding="utf-8")
        path.chmod(mode)
        return path

    def named(self, path: Path) -> dict:
        return {isolation.OAUTH_TOKEN_VARIABLE: str(path)}

    def test_the_default_path_is_the_one_the_wizard_writes(self):
        self.assertEqual(
            Path("~/.config/redkraken/claude-oauth-token").expanduser(),
            isolation.oauth_token_file({}),
        )

    def test_an_operator_may_name_another_absolute_file(self):
        path = self.installed()

        self.assertEqual(path, isolation.oauth_token_file(self.named(path)))
        self.assertEqual(self.SENTINEL, isolation.oauth_token(self.named(path)))

    def test_a_relative_override_is_refused_rather_than_resolved(self):
        with self.assertRaisesRegex(isolation.Unavailable, "absolute"):
            isolation.oauth_token_file({isolation.OAUTH_TOKEN_VARIABLE: "token"})

    def test_a_machine_holding_no_token_holds_none_rather_than_failing(self):
        directory = Path(tempfile.mkdtemp(prefix="rk2-token-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        directory.chmod(0o700)

        self.assertIsNone(isolation.oauth_token(self.named(directory / "absent")))

    def test_a_token_a_second_account_could_read_is_refused(self):
        for mode, description in ((0o640, "group"), (0o604, "world")):
            with self.subTest(description):
                path = self.installed(mode=mode)
                with self.assertRaisesRegex(isolation.Unavailable, "group or world"):
                    isolation.oauth_token(self.named(path))

    def test_the_token_file_has_exactly_the_installed_mode(self):
        """Read-only or owner-executable is drift, not the wizard's 0600 file."""
        for mode in (0o400, 0o700):
            with self.subTest(mode=oct(mode)):
                path = self.installed(mode=mode)
                with self.assertRaisesRegex(isolation.Unavailable, "0600"):
                    isolation.oauth_token(self.named(path))

    def test_a_token_directory_a_second_account_could_reach_is_refused(self):
        path = self.installed()
        path.parent.chmod(0o755)

        with self.assertRaisesRegex(isolation.Unavailable, "token directory"):
            isolation.oauth_token(self.named(path))

    def test_the_token_directory_has_exactly_the_installed_mode(self):
        path = self.installed()
        path.parent.chmod(0o500)

        with self.assertRaisesRegex(isolation.Unavailable, "0700"):
            isolation.oauth_token(self.named(path))

    def test_a_symlink_is_a_way_of_naming_a_file_the_operator_did_not_hand_over(self):
        path = self.installed()
        link = path.parent / "link"
        link.symlink_to(path)

        with self.assertRaisesRegex(isolation.Unavailable, "symlink"):
            isolation.oauth_token(self.named(link))

    def test_a_file_carrying_more_than_one_value_is_not_the_file_this_expects(self):
        path = self.installed(f"{self.SENTINEL}\nand something else\n")

        with self.assertRaisesRegex(isolation.Unavailable, "carries 2 lines"):
            isolation.oauth_token(self.named(path))

    def test_a_blank_second_line_is_still_a_second_line(self):
        path = self.installed(f"{self.SENTINEL}\n\n")

        with self.assertRaisesRegex(isolation.Unavailable, "carries 2 lines"):
            isolation.oauth_token(self.named(path))

    def test_an_empty_token_is_refused_rather_than_handed_on_as_a_value(self):
        for value, description in (("", "nothing at all"), ("   \n", "whitespace")):
            with self.subTest(description):
                path = self.installed(value)
                with self.assertRaisesRegex(isolation.Unavailable, "is empty"):
                    isolation.oauth_token(self.named(path))

    def test_a_trailing_newline_is_a_file_an_editor_wrote_and_not_a_second_line(self):
        path = self.installed(f"{self.SENTINEL}\n")

        self.assertEqual(self.SENTINEL, isolation.oauth_token(self.named(path)))

    def test_no_refusal_ever_carries_the_token_it_refused(self):
        path = self.installed(f"{self.SENTINEL}\nsecond", mode=0o666)

        with self.assertRaises(isolation.Unavailable) as raised:
            isolation.oauth_token(self.named(path))

        self.assertNotIn(self.SENTINEL, str(raised.exception))

    def test_the_age_is_read_off_the_file_and_not_out_of_the_token(self):
        path = self.installed()
        os.utime(path, (time.time() - 331 * 86400,) * 2)

        self.assertEqual(331, isolation.oauth_token_days(self.named(path)))
        self.assertGreater(
            isolation.oauth_token_days(self.named(path)), isolation.OAUTH_TOKEN_DAYS
        )

    def test_a_machine_with_no_token_has_no_age_to_report(self):
        self.assertIsNone(isolation.oauth_token_days(self.named(Path("/nonexistent/token"))))


class SetupWizardTest(unittest.TestCase):
    """`tools/setup-agent-oauth.sh`, driven end to end against stubs.

    `claude setup-token` is a browser flow only a human completes, so what is
    exercised here is everything around it: that the script runs exactly that
    command, that it reads the token once and never prints it, and that what it
    leaves on disk is a file `isolation.oauth_token` will accept. The real mint
    is the operator's, and this is the whole of what can be checked without
    them.
    """

    SENTINEL = "RK-SYNTHETIC-SETUP-TOKEN-2f7c"
    WIZARD = SOURCE.parent / "tools" / "setup-agent-oauth.sh"

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rk2-wizard-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.record = self.root / "claude.argv"

    def stub(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        path.chmod(0o755)

    def run_wizard(
        self, token: str = SENTINEL, environment_overrides: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        """One whole run, with the two commands it shells out to stood in for."""
        self.stub("claude", f'printf "%s\\n" "$@" >> {self.record}\nexit 0')
        # The doctor's own report, in the shape the script reads back. Stubbed
        # rather than run, because a real diagnosis inspects containers this
        # machine does not have and the assertion under test is the file.
        self.stub(
            "rk",
            'printf \'{"assertions":[{"name":"agent_credential","ok":true,'
            '"detail":"a setup token this operator alone can read"}],'
            '"violations":[]}\\n\'',
        )
        environment = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.home),
            "TERM": "dumb",
        }
        environment.update(environment_overrides or {})
        # Enter past the banner, `y` to mint, Enter past the mint, the token.
        return subprocess.run(
            ["bash", str(self.WIZARD)],
            input=f"\ny\n\n{token}\n",
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )

    def installed(self) -> Path:
        return self.home / ".config" / "redkraken" / "claude-oauth-token"

    def test_the_wizard_runs_exactly_claude_setup_token(self):
        answer = self.run_wizard()

        self.assertEqual(0, answer.returncode, answer.stdout + answer.stderr)
        # `--version` in stage one, then the mint, and nothing else: the script
        # asks the CLI which it is and then asks it for a token.
        self.assertEqual(
            ["--version", "setup-token"],
            self.record.read_text(encoding="utf-8").split(),
        )

    def test_a_relative_override_is_refused_before_the_cli_is_run(self):
        answer = self.run_wizard(
            environment_overrides={"RK_AGENT_OAUTH_TOKEN_FILE": "relative/token"}
        )

        self.assertNotEqual(0, answer.returncode)
        self.assertIn("absolute", answer.stdout + answer.stderr)
        self.assertFalse(self.record.exists())

    def test_the_installed_token_is_one_this_operator_alone_can_read(self):
        self.run_wizard()
        path = self.installed()

        self.assertTrue(path.is_file())
        self.assertFalse(path.is_symlink())
        self.assertEqual(0o600, path.stat().st_mode & 0o777)
        self.assertEqual(0o700, path.parent.stat().st_mode & 0o777)
        self.assertEqual(os.getuid(), path.stat().st_uid)
        self.assertEqual(f"{self.SENTINEL}\n", path.read_text(encoding="utf-8"))

    def test_what_it_installs_is_what_the_runtime_reads_back(self):
        self.run_wizard()

        self.assertEqual(
            self.SENTINEL,
            isolation.oauth_token({isolation.OAUTH_TOKEN_VARIABLE: str(self.installed())}),
        )

    def test_the_token_reaches_no_stream_and_no_file_but_its_own(self):
        answer = self.run_wizard()

        self.assertNotIn(self.SENTINEL, answer.stdout)
        self.assertNotIn(self.SENTINEL, answer.stderr)
        elsewhere = [
            path
            for path in self.root.rglob("*")
            if path.is_file()
            and path != self.installed()
            and self.SENTINEL in path.read_text(encoding="utf-8", errors="replace")
        ]
        self.assertEqual([], elsewhere)

    def test_a_replaced_token_is_renamed_over_and_never_half_written(self):
        self.run_wizard()
        first = self.installed().stat().st_ino

        self.run_wizard("RK-SYNTHETIC-SETUP-TOKEN-9b41")

        # A different inode, which is what a rename over leaves: the old file
        # was replaced whole rather than truncated and rewritten in place.
        self.assertNotEqual(first, self.installed().stat().st_ino)
        self.assertEqual(
            "RK-SYNTHETIC-SETUP-TOKEN-9b41\n", self.installed().read_text(encoding="utf-8")
        )

    def test_a_value_that_is_not_one_word_is_refused_before_anything_is_written(self):
        answer = self.run_wizard("two words")

        self.assertNotEqual(0, answer.returncode)
        self.assertIn("one word", answer.stdout + answer.stderr)
        self.assertFalse(self.installed().exists())

    def test_nothing_pasted_installs_nothing(self):
        answer = self.run_wizard("")

        self.assertNotEqual(0, answer.returncode)
        self.assertFalse(self.installed().exists())

    def test_the_canary_is_skipped_rather_than_faked_where_no_boundary_is_described(self):
        answer = self.run_wizard()

        self.assertIn("no Agent boundary is exported", answer.stdout)
