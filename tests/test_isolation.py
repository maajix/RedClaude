"""The real Agent-container routing boundary for PH2-10/11."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

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
            cls._serve(cls.proxy, cls.agent_network, 18080)
            cls._serve(cls.target, cls.target_network, 18081)
            cls._serve(cls.control, cls.control_network, 5432)
            docker("network", "connect", cls.target_network, cls.proxy)
            docker("network", "connect", cls.control_network, cls.proxy)
            cls.target_ip = cls._address(cls.target, cls.target_network)
            cls.control_ip = cls._address(cls.control, cls.control_network)
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

    @classmethod
    def _serve(cls, name: str, network: str, port: int) -> None:
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
            fixtures.AGENT_IMAGE,
            "python3",
            "-m",
            "http.server",
            str(port),
            "--bind",
            "0.0.0.0",
        )

    @staticmethod
    def _address(container: str, network: str) -> str:
        result = docker(
            "inspect",
            "--format",
            f"{{{{(index .NetworkSettings.Networks {json.dumps(network)}).IPAddress}}}}",
            container,
        )
        return result.stdout.strip()

    def boundary(self, *, network: str | None = None) -> isolation.AgentContainer:
        """The described boundary, with the names of things that exist."""
        return fixtures.boundary(
            network=network or self.agent_network,
            proxy_container=self.proxy,
            proxy_url=f"http://{self.proxy}:18080",
            certificate=self.authority.certificate,
        )

    def test_only_the_proxy_is_reachable_and_only_the_run_root_is_installed(self):
        probe = r"""
import json, os, socket

def reaches(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.6):
            return True
    except OSError:
        return False

def resolves(host):
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return True
    except OSError:
        return False

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


if __name__ == "__main__":
    unittest.main()
