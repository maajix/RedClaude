"""The Agent container's one-peer network boundary.

Proxy variables make cooperative clients use the egress door; they do not stop
model-controlled code from opening its own socket.  This module owns the other
half: an Agent process is attached to one internal container network whose only
existing peer is the proxy, with external DNS deliberately blackholed.  The
proxy may have target, control and egress networks of its own; none is joined to
the Agent process.

The caller supplies no Docker arguments.  It supplies an image, the already
running proxy peer, an argv and the host directories an Agent needs to exist
at all -- the application, the SDK it is measured against, the home its
credential is resolved from.  The runtime verifies the topology, constructs the
complete child environment, decides where each of those is mounted and which of
them may be written, adds the run certificate (never its directory or signing
key), and applies the process restrictions itself.
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
# are copied by name rather than inherited wholesale.  HOME, TMPDIR and the
# import path are runtime-owned below; the remaining values are usability, not
# authority.
INHERITED = ("LANG", "LC_ALL", "TZ")

# Where the runtime puts what a child needs, and the two places a child may
# write.  Fixed paths rather than configured ones: which application and which
# SDK a child resolves is exactly what the startup assertion measures, so it is
# a constant of this runtime rather than a value a caller supplies.
APPLICATION = "/opt/rk2-app"
RUNTIME = "/opt/rk2-runtime"
HOME_DIR = "/run/redkraken-home"
WORKSPACE = "/run/rk2"
TMPDIR = "/run"

# How the child is told where the application is.  Set here and never
# inherited: an inherited import path is a way to choose which SDK the
# assertion measures.
IMPORT_PATH = "PYTHONPATH"


class Unavailable(RuntimeError):
    """The configured engine, image or topology cannot provide isolation."""


@dataclass(frozen=True)
class AgentContainer:
    """Everything needed to start one process in the verified Agent boundary.

    The three host directories are what the runtime mounts inside it: the
    application the child runs, the SDK it runs the child with, and the home
    the child's credential is resolved from.  Each is absent by default,
    because absent is the contained value -- a container with no home mounted
    has no credential at all rather than somebody else's, and one with no SDK
    mounted refuses at the startup assertion rather than starting a session.
    """

    image: str
    network: str
    proxy_container: str
    proxy_url: str
    certificate: Path
    application: Path | None = None
    runtime: Path | None = None
    home: Path | None = None
    engine: str = ENGINE


def container_environment(
    container: AgentContainer, source: Mapping[str, str]
) -> dict[str, str]:
    """The whole environment a child gets: a copied list, plus the door.

    Built from a positive list rather than filtered out of the operator's own,
    so a variable that is absent here cannot reach a child by being forgotten,
    only by being added on purpose.  The three the runtime supplies are the
    three that decide what a child resolves -- a credential, a scratch
    directory and an SDK -- which is why none of them is inherited.

    Split out of `run` because it is the half of the boundary that does not
    need a container to be true: the list can be asserted on a machine with no
    engine, and the machine that has to prove nothing crosses is not always the
    machine that can start something for it not to cross into.
    """
    child = {name: source[name] for name in INHERITED if source.get(name)}
    child.update({"HOME": HOME_DIR, "TMPDIR": TMPDIR})
    mounted = [
        destination
        for destination, host in (
            (APPLICATION, container.application),
            (RUNTIME, container.runtime),
        )
        if host is not None
    ]
    if mounted:
        # The container's separator, not this machine's: the value is read by
        # the interpreter inside the image.
        child[IMPORT_PATH] = ":".join(mounted)
    return tls.agent_environment(child, proxy_url=container.proxy_url, certificate=CA_FILE)


def run(
    container: AgentContainer,
    argv: Sequence[str],
    *,
    source_environment: Mapping[str, str] | None = None,
    stdin: str | None = None,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    """Run ``argv`` in a verified one-peer Agent container.

    No shell is involved and the image is never pulled implicitly.  A timeout
    removes the exact named child before it is reported, so a failed launch
    cannot leave a process attached to the run network.

    ``stdin`` is written to the child rather than passed as arguments.  What a
    child is told to do is not a thing to put where every process on the
    machine can read it, and not a thing to size against ``ARG_MAX``.
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
    environment = container_environment(container, inherited)
    mounts = _mounts(container, certificate)

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
        *mounts,
    ]
    if stdin is not None:
        docker.append("--interactive")
    for key, value in sorted(environment.items()):
        docker.extend(("--env", f"{key}={value}"))
    docker.extend((container.image, *command))

    host_environment = {"PATH": os.environ.get("PATH", "")}
    try:
        return subprocess.run(
            docker,
            env=host_environment,
            input=stdin,
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


def _mounts(container: AgentContainer, certificate: Path) -> list[str]:
    """Everything the runtime puts inside the boundary, and nothing else.

    The trust root crosses as a file rather than as the directory holding it,
    because the signing key is what lies beside it: the difference between an
    Agent that can be intercepted and an Agent that can intercept is exactly
    one file.  The application and the SDK cross read-only, because a child
    that could write to them could choose what the next child is measured as.
    The home is the one writable mount -- the CLI keeps session state in it --
    and it has to be a directory the container's own user can write.
    """
    arguments = ["--mount", f"type=bind,src={certificate},dst={CA_FILE},readonly"]
    for destination, host, readonly in (
        (APPLICATION, container.application, True),
        (RUNTIME, container.runtime, True),
        (HOME_DIR, container.home, False),
    ):
        if host is None:
            continue
        source = Path(host).resolve()
        if not source.is_dir():
            raise Unavailable(f"an Agent container mount is not a directory: {source}")
        mount = f"type=bind,src={source},dst={destination}"
        arguments.extend(("--mount", f"{mount},readonly" if readonly else mount))
    return arguments


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
