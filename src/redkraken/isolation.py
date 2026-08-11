"""The Agent container's one-peer network boundary.

Proxy variables make cooperative clients use the egress door; they do not stop
model-controlled code from opening its own socket.  This module owns the other
half: an Agent process is attached to one internal container network whose only
existing peer is the proxy, with external DNS deliberately blackholed.  The
proxy may have target, control and egress networks of its own; none is joined to
the Agent process.

The caller supplies no Docker arguments.  It supplies an image, the already
running proxy peer and an argv.  The runtime verifies the topology, constructs
the complete child environment, mounts only the run certificate (never its
directory or signing key), and applies the process restrictions itself.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from redkraken import _startup, tls


ENGINE = "docker"
CA_FILE = "/run/redkraken-ca.pem"
DNS_BLACKHOLE = "127.0.0.1"

# Values the supervisor may deliberately carry into an Agent container.  They
# are copied by name rather than inherited wholesale.  HOME and TMPDIR are
# runtime-owned below; the remaining values are usability, not authority.
INHERITED = ("LANG", "LC_ALL", "TZ")


class Unavailable(RuntimeError):
    """The configured engine, image or topology cannot provide isolation."""


@dataclass(frozen=True)
class AgentContainer:
    """Everything needed to start one process in the verified Agent boundary."""

    image: str
    network: str
    proxy_container: str
    proxy_url: str
    certificate: Path
    engine: str = ENGINE


def run(
    container: AgentContainer,
    argv: Sequence[str],
    *,
    source_environment: Mapping[str, str] | None = None,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    """Run ``argv`` in a verified one-peer Agent container.

    No shell is involved and the image is never pulled implicitly.  A timeout
    removes the exact named child before it is reported, so a failed launch
    cannot leave a process attached to the run network.
    """
    if isinstance(argv, (str, bytes)):
        raise Unavailable("an Agent container argv must be a sequence, not one string")
    engine = _engine(container.engine)
    command = tuple(argv)
    if not command or any(not isinstance(item, str) or not item or "\0" in item for item in command):
        raise Unavailable("an Agent container needs a non-empty argv of plain strings")
    if timeout <= 0:
        raise Unavailable("an Agent container timeout must be positive")

    certificate = Path(container.certificate).resolve()
    if not certificate.is_file():
        raise Unavailable(f"the run trust root is not a readable file: {certificate}")

    proxy_host = _proxy_host(container.proxy_url)
    image_environment = _image_environment(engine, container.image)
    watched = sorted(set(image_environment) & set(_startup.WATCHED_ENV_VECTORS))
    if watched:
        raise Unavailable(
            "the Agent image declares watched credential vectors: " + ", ".join(watched)
        )
    _one_peer(engine, container.network, container.proxy_container, proxy_host)

    inherited = os.environ if source_environment is None else source_environment
    base = {name: inherited[name] for name in INHERITED if inherited.get(name)}
    base.update({"HOME": "/run/redkraken-home", "TMPDIR": "/run"})
    environment = tls.agent_environment(
        base,
        proxy_url=container.proxy_url,
        certificate=CA_FILE,
    )

    name = f"rk2-agent-{uuid.uuid4().hex}"
    docker = [
        engine,
        "run",
        "--rm",
        "--pull",
        "never",
        "--name",
        name,
        "--network",
        container.network,
        "--dns",
        DNS_BLACKHOLE,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--read-only",
        "--tmpfs",
        "/run:rw,nosuid,nodev,noexec,size=64m,mode=1777",
        "--pids-limit",
        "256",
        "--user",
        "65534:65534",
        "--entrypoint",
        "",
        "--mount",
        f"type=bind,src={certificate},dst={CA_FILE},readonly",
    ]
    for key, value in sorted(environment.items()):
        docker.extend(("--env", f"{key}={value}"))
    docker.extend((container.image, *command))

    host_environment = {"PATH": os.environ.get("PATH", "")}
    try:
        return subprocess.run(
            docker,
            env=host_environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        subprocess.run(
            [engine, "rm", "--force", name],
            env=host_environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        raise Unavailable(f"the Agent container exceeded its {timeout:g}s runtime") from error


def _engine(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise Unavailable(f"the configured container engine is not on PATH: {name}")
    return found


def _inspect(engine: str, kind: str, subject: str) -> dict:
    answer = subprocess.run(
        [engine, kind, "inspect", subject],
        env={"PATH": os.environ.get("PATH", "")},
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    if answer.returncode:
        detail = (answer.stderr or answer.stdout).strip().splitlines()
        raise Unavailable(
            f"the Agent {kind} cannot be inspected: {detail[-1] if detail else subject}"
        )
    try:
        records = json.loads(answer.stdout)
    except (json.JSONDecodeError, TypeError) as error:
        raise Unavailable(f"the Agent {kind} inspection was not JSON") from error
    if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
        raise Unavailable(f"the Agent {kind} inspection named other than one object")
    return records[0]


def _image_environment(engine: str, image: str) -> set[str]:
    record = _inspect(engine, "image", image)
    configured = (record.get("Config") or {}).get("Env") or []
    if not isinstance(configured, list):
        raise Unavailable("the Agent image environment cannot be read")
    return {str(item).partition("=")[0] for item in configured}


def _proxy_host(url: str) -> str:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise Unavailable(f"the Agent proxy URL cannot be read: {error}") from error
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise Unavailable("the Agent proxy URL must be an uncredentialed http://host:port")
    return parsed.hostname


def _one_peer(engine: str, network: str, proxy_container: str, proxy_host: str) -> None:
    topology = _inspect(engine, "network", network)
    if topology.get("Internal") is not True:
        raise Unavailable(f"the Agent network is not internal: {network}")
    peers = topology.get("Containers") or {}
    if not isinstance(peers, dict):
        raise Unavailable(f"the Agent network peer set cannot be read: {network}")

    proxy = _inspect(engine, "container", proxy_container)
    proxy_id = str(proxy.get("Id") or "")
    attached = (proxy.get("NetworkSettings") or {}).get("Networks") or {}
    endpoint = attached.get(network) if isinstance(attached, dict) else None
    if proxy_id not in peers or not isinstance(endpoint, dict):
        raise Unavailable(f"the configured proxy is not attached to the Agent network: {network}")
    aliases = {str(item) for item in (endpoint.get("Aliases") or [])}
    aliases.update(
        {
            proxy_id,
            proxy_id[:12],
            str(proxy.get("Name") or "").lstrip("/"),
        }
    )
    if proxy_host not in aliases:
        raise Unavailable(f"the Agent proxy URL does not name the network's proxy peer: {proxy_host}")

    others = sorted(
        str(peer.get("Name") or identity)
        for identity, peer in peers.items()
        if identity != proxy_id
    )
    if others:
        raise Unavailable(
            "the Agent network has peers other than the proxy: " + ", ".join(others)
        )
