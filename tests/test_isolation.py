"""The real Agent-container routing boundary for PH2-10/11."""

from __future__ import annotations

import ipaddress
import json
import os
import shutil
import socket
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

from redkraken import _startup, isolation, tls
from tests import fixtures
from tests.fixtures import docker


LIVE = os.environ.get("RK_TEST_CONTAINERS") == "1"
REASON = "set RK_TEST_CONTAINERS=1 to run the disposable Docker isolation proof"


class ContainerEnvironmentTest(unittest.TestCase):
    """What a child is told about the world, and what it is not told.

    No engine required. The environment is the half of the boundary that is
    decidable without one, and the machine that has to prove nothing crosses is
    not always the machine that can start something for it not to cross into.
    """

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

    def boundary(self, *, network: str | None = None) -> isolation.AgentContainer:
        """The described boundary, with the names of things that exist."""
        return fixtures.boundary(
            network=network or self.agent_network,
            proxy_container=self.proxy,
            proxy_url=f"http://{self.proxy}:18080",
            certificate=self.authority.certificate,
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

    def test_a_peer_that_arrives_after_the_check_is_reachable_by_the_child(self):
        """Ticket 80, criterion 5: the window between the check and the launch.

        The refusal above is what containment between two children rests on:
        every launch reads the network first and stops if anything other than
        the door is on it, so a second child cannot come up beside a first.
        That holds for two launches that are ordered. It is a check-then-act,
        the engine holds nothing between the two, and one network name serves a
        whole installation -- so two launches that overlap can both read a clear
        network and both attach to it.

        Demonstrated rather than argued, and deterministically rather than by
        racing: the peer is attached inside the launch call itself, after
        `one_peer` has returned and before the engine is asked to start
        anything. The engine command is the one that begins `run`; everything
        before it in this call is the check reading the engine's records.

        What comes back is the gap: the child starts, and reaches a machine the
        boundary check said was not there. Nothing here is a defect in the
        refusal, which does what it says -- the gap is that ordering the launches
        is what makes it hold, and nothing does. Ticket 85 is where that is
        answered.
        """
        subnet = docker(
            "network", "inspect", "--format", "{{(index .IPAM.Config 0).Subnet}}",
            self.agent_network,
        ).stdout.strip()
        # A fixed address, so the child can be told where to look before the
        # peer that answers there exists. High in the range, because the engine
        # assigns from the bottom of it and an address it had already handed out
        # would fail the attach rather than demonstrate anything.
        arriving = str(ipaddress.ip_network(subnet).network_address + 250)
        probe = fixtures.PROBE + """
print(json.dumps({'arrived': reaches(%r, 18081)}))
""" % arriving

        attached = []
        launch = isolation.subprocess.run

        def racing(command, **keywords):
            if not attached and len(command) > 1 and command[1] == "run":
                attached.append(arriving)
                docker("network", "connect", "--ip", arriving,
                       self.agent_network, self.target)
            return launch(command, **keywords)

        try:
            with mock.patch.object(isolation.subprocess, "run", racing):
                result = isolation.run(
                    self.boundary(), ("python3", "-c", probe), timeout=20
                )
        finally:
            docker("network", "disconnect", self.agent_network, self.target, check=False)

        self.assertEqual([arriving], attached)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)["arrived"])

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


if __name__ == "__main__":
    unittest.main()
