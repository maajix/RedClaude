"""The real Agent-container routing boundary for PH2-10/11."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

from redkraken import _startup, isolation, tls


LIVE = os.environ.get("RK_TEST_CONTAINERS") == "1"
IMAGE = os.environ.get("RK_TEST_AGENT_IMAGE", "python:3.13-alpine")
REASON = "set RK_TEST_CONTAINERS=1 to run the disposable Docker isolation proof"


def docker(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["docker", *arguments],
        env={"PATH": os.environ.get("PATH", "")},
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if check and result.returncode:
        raise AssertionError((result.stderr or result.stdout).strip())
    return result


@unittest.skipUnless(LIVE, REASON)
class AgentContainerIsolationTest(unittest.TestCase):
    """A child has one peer even when it knows every forbidden address."""

    @classmethod
    def setUpClass(cls):
        if shutil.which("docker") is None:
            raise unittest.SkipTest("docker is not on PATH")
        if docker("image", "inspect", IMAGE, check=False).returncode:
            raise unittest.SkipTest(f"the local Agent test image is absent: {IMAGE}")

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
            IMAGE,
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
        return isolation.AgentContainer(
            image=IMAGE,
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
