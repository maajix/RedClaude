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

An offline tool is the same boundary asked for less.  `run_tool` starts one
registry-described process with no network at all unless its registry row says
it uses the proxy adapter, in which case it is given a one-peer network of its
own to the same proxy -- the Agent's topology rather than the Agent's network,
because a second peer on that one is a route between two children.  What it may
consume is stated per tool rather than per installation, and what it produced is
read back through bounds the supervisor enforces while the process is still
running: a tool that decides to print forever is a tool that decides how much of
the supervisor's memory it gets, unless something is counting.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import selectors
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
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
SDK = "/opt/rk2-sdk"
HOME_DIR = "/run/redkraken-home"
WORKSPACE = "/run/rk2"
TMPDIR = "/run"

# The interpreter a child is started with.  The image's, not the supervisor's:
# `sys.executable` names a file on the machine that decides to launch, and the
# machine that runs is a container that has never seen it.
INTERPRETER = "python3"

# How the child is told where the application is.  Set here and never
# inherited: an inherited import path is a way to choose which SDK the
# assertion measures.
IMPORT_PATH = "PYTHONPATH"

# Who a child is inside its container.  Unprivileged and nameless, which is why
# the one directory a child may write has to be one *this* user can write: the
# supervisor's own access to it answers a question nobody asked.
UID = 65534
GID = 65534

# Where an offline tool's inputs appear and the one directory it may write.  The
# runtime's half of an agreement the database states -- `rk2_offline_input_path`
# and `rk2_offline_workspace` return them, and a plan naming anything else is
# refused here rather than mounted.  Scratch space is `TMPDIR` above, the same
# directory an agent child gets: the conventional one names a tree on the machine
# that launches as well, and a path that means one thing inside the container and
# another outside it is a path someone will eventually read as the wrong one.
TOOL_INPUTS = "/input"
TOOL_WORKSPACE = "/work"

# What an offline tool starts from.  Nothing is inherited: the executable is an
# absolute path from the registry, so there is no search path to poison, and a
# tool whose output depended on the operator's locale would be a tool whose
# Artifact is not reproducible.
#
# One thing is added afterwards and only one.  A tool that declares the proxy
# adapter is handed the door through `tls.agent_environment`, which is the same
# three variables every other container behind the fence gets and is the whole
# of how a process finds it.  Everything else here is the whole environment.
TOOL_ENVIRONMENT = {"HOME": "/", "TMPDIR": TMPDIR, "LC_ALL": "C.UTF-8"}


# Where this machine records that a launch onto an Agent network is in flight.
# Per user rather than per machine: two operators on one host are two
# installations with two networks, and a claim either could take would be one
# operator refusing the other's launches for a reason the other cannot see.
LOCKS = "rk2-agent-networks"


class Unavailable(RuntimeError):
    """The configured engine, image or topology cannot provide isolation."""


def hardened(name: str, *, ephemeral: bool = True) -> list[str]:
    """The restrictions every container this harness starts runs under.

    One list rather than one per caller.  An Agent child and an offline tool
    differ in what they are given -- a network, a scratch size, a memory ceiling
    -- and not at all in what they are denied, so a second copy of the denials
    is a second place for one of them to quietly lose a line.  Public, and about
    this harness rather than this module, for the same reason: `door` starts the
    proxy peer this module then holds every child to, and a door denied less
    than the children around it is the hole.

    The engine is not named here, only the arguments it takes.  A caller that
    runs the command itself puts the engine in front; one that hands it to
    `engine_command` does not, and neither has to know which of those the other
    is doing.

    `ephemeral` is the one thing a caller decides here, and only because the
    door is the one container this harness starts that outlives the command
    starting it.  A one-shot child that is gone is a child whose output has
    already been read; a door that is gone is a door whose reason for going is
    gone with it.
    """
    return [
        "run",
        *(["--rm"] if ephemeral else []),
        # Never pulled implicitly: which build ran is half of what its output
        # means, and a pull here would decide that from the network.
        "--pull",
        "never",
        "--name",
        name,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--read-only",
        "--user",
        f"{UID}:{GID}",
        # The image's entrypoint is not the argv the caller asked for, and a
        # tool run through one is a tool whose argv the registry did not decide.
        "--entrypoint",
        "",
    ]


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
    sdk: Path | None = None
    home: Path | None = None
    engine: str = ENGINE
    #: What the child may consume, and why it is here at all. `run_tool` reads
    #: its ceilings out of the registry because an offline tool declares what it
    #: needs; an Agent container has no registry row and had, until this, no
    #: ceiling either -- a `--pids-limit` and a scratch bound, and nothing
    #: stopping one runaway child from taking the machine's memory with it and
    #: the door, the database and every sibling run along with it.  Defaults
    #: rather than required arguments so every existing caller keeps working,
    #: and the same numbers `browser_ceilings` ships with: the browser is the
    #: heaviest thing this harness starts, so a bound that holds it holds a
    #: session that mostly waits on a model.
    memory_mb: int = 1024
    cpu_quota: float = 2.0


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
        destination for destination, _, _, imported in _supplied(container) if imported
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
    engine = engine_for(container.engine)
    command = tuple(argv)
    if not command or any(not isinstance(item, str) or not item or "\0" in item for item in command):
        raise Unavailable("an Agent container needs a non-empty argv of plain strings")
    if timeout <= 0:
        raise Unavailable("an Agent container timeout must be positive")

    certificate = Path(container.certificate).resolve()
    if not certificate.is_file():
        raise Unavailable(f"the run trust root is not a readable file: {certificate}")

    with held(container.network):
        return _launched(container, command, source_environment, stdin, timeout, engine, certificate)


def _launched(
    container: AgentContainer,
    command: tuple[str, ...],
    source_environment: Mapping[str, str] | None,
    stdin: str | None,
    timeout: float,
    engine: str,
    certificate: Path,
) -> subprocess.CompletedProcess[str]:
    """The checked launch, inside the claim `run` holds on the network.

    Split out for one reason: everything here reads or changes what is attached
    to one Agent network, and a reader has to be able to see that all of it is
    under the same claim rather than trace an indentation to find out.
    """
    proxy_host, _ = proxy_peer(container.proxy_url)
    image_environment = _image_environment(engine, container.image)
    watched = sorted(set(image_environment) & set(_startup.WATCHED_ENV_VECTORS))
    if watched:
        raise Unavailable(
            "the Agent image declares watched credential vectors: " + ", ".join(watched)
        )
    one_peer(engine, container.network, container.proxy_container, proxy_host)

    inherited = os.environ if source_environment is None else source_environment
    environment = container_environment(container, inherited)
    mounts = _mounts(container, certificate)

    name = f"rk2-agent-{uuid.uuid4().hex}"
    docker = [
        engine,
        *hardened(name),
        "--network",
        container.network,
        "--dns",
        DNS_BLACKHOLE,
        "--tmpfs",
        f"{TMPDIR}:rw,nosuid,nodev,noexec,size=64m,mode=1777",
        "--memory",
        f"{container.memory_mb}m",
        # The same number again, for the reason `run_tool` gives: a memory
        # ceiling a container may page past is a ceiling on how fast it uses the
        # machine, not on how much.
        "--memory-swap",
        f"{container.memory_mb}m",
        "--cpus",
        f"{container.cpu_quota:g}",
        "--pids-limit",
        "256",
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
        remove(engine, name, host_environment)
        raise Unavailable(f"the Agent container exceeded its {timeout:g}s runtime") from error


@dataclass(frozen=True)
class ToolContainer:
    """What this installation can offer an offline tool, whatever it asks for.

    The image is the one holding the registered executables.  `door` is the
    Agent boundary a tool that declares the proxy adapter is put on, and it is
    absent by default because absent is the contained value: an installation
    that has not described a door cannot run a tool that wants one, which is a
    refusal rather than a tool quietly running with the wire open.
    """

    image: str
    engine: str = ENGINE
    door: AgentContainer | None = None


@dataclass(frozen=True)
class Ceilings:
    """What one run may consume before it is taken away.

    Five numbers that travel together because the registry decides all five per
    tool, and a run held to four of them is a run that is not held.
    """

    timeout_seconds: float
    memory_mb: int
    cpu_quota: float
    pids_limit: int
    max_output_bytes: int


@dataclass(frozen=True)
class Captured:
    """One stream of a run: the bytes kept, and how many there were.

    The two are different numbers whenever a tool printed more than its bound
    allows, and both are needed downstream -- the bytes become the Artifact, the
    count is what says the Artifact is a prefix of something longer.
    """

    data: bytes
    produced: int

    @property
    def truncated(self) -> bool:
        return self.produced > len(self.data)


@dataclass(frozen=True)
class ToolProcess:
    """What became of one offline tool process."""

    exit_code: int | None
    stdout: Captured
    stderr: Captured
    outputs: dict[str, Captured] = field(default_factory=dict)
    timed_out: bool = False
    overflowed: bool = False

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.overflowed


def run_tool(
    container: ToolContainer,
    argv: Sequence[str],
    *,
    ceilings: Ceilings,
    inputs: Mapping[str, bytes] | None = None,
    outputs: Sequence[str] = (),
    network: str = "none",
    scratch_mb: int = 16,
) -> ToolProcess:
    """Run one registry-described tool, bounded, and read back what it produced.

    The caller passes the plan the database produced and nothing of its own:
    the argv, where each input's bytes are to appear, which filenames the tool
    declares, whether it has a network, and the five ceilings.  Every path is
    checked against this module's constants rather than trusted, because a plan
    is data and the one thing an argument may never do is name a place.

    Inputs cross read-only, so the only writable thing in the container is the
    workspace, and the workspace exists only for a tool that declares outputs.
    Both staging directories live under a private one this process owns, which
    is what makes it safe for the mount itself to be readable by the nameless
    user the child runs as.

    Nothing about the result is decided after the fact.  Bytes past the output
    bound and time past the deadline both end the run where they happen, and
    both are reported, because a truncated stream that read like a complete one
    would be evidence of something that did not happen.
    """
    if isinstance(argv, (str, bytes)):
        raise Unavailable("an offline tool argv must be a sequence, not one string")
    command = tuple(argv)
    if not command or any(
        not isinstance(item, str) or not item or "\0" in item for item in command
    ):
        raise Unavailable("an offline tool needs a non-empty argv of plain strings")
    if ceilings.timeout_seconds <= 0 or ceilings.max_output_bytes <= 0:
        raise Unavailable("an offline tool needs a positive timeout and output bound")
    if network not in ("none", "proxy"):
        raise Unavailable(f"an offline tool has no network or the proxy, not {network}")
    if not 1 <= scratch_mb <= 1024:
        raise Unavailable(f"a tool's scratch tmpfs is between 1MB and 1GB, not {scratch_mb}")

    engine = engine_for(container.engine)
    watched = sorted(
        set(_image_environment(engine, container.image)) & set(_startup.WATCHED_ENV_VECTORS)
    )
    if watched:
        raise Unavailable(
            "the tool image declares watched credential vectors: " + ", ".join(watched)
        )

    environment = dict(TOOL_ENVIRONMENT)
    routing = ["--network", "none"]
    certificate: Path | None = None
    door: AgentContainer | None = None
    if network == "proxy":
        door = container.door
        if door is None:
            raise Unavailable(
                "this tool declares the proxy adapter and no egress door is configured"
            )
        certificate = Path(door.certificate).resolve()
        if not certificate.is_file():
            raise Unavailable(f"the run trust root is not a readable file: {certificate}")
        environment = tls.agent_environment(
            environment, proxy_url=door.proxy_url, certificate=CA_FILE
        )

    staging = Path(tempfile.mkdtemp(prefix="rk2-tool-"))
    name = f"rk2-tool-{uuid.uuid4().hex}"
    host_environment = {"PATH": os.environ.get("PATH", "")}
    adapter: str | None = None
    try:
        if door is not None:
            adapter = f"{name}-door"
            _adapter(engine, door, adapter, host_environment)
            routing = ["--network", adapter, "--dns", DNS_BLACKHOLE]
        workspace = _staged(staging, inputs or {}, outputs)
        mounts = [f"type=bind,src={staging / 'input'},dst={TOOL_INPUTS},readonly"]
        if workspace is not None:
            mounts.append(f"type=bind,src={workspace},dst={TOOL_WORKSPACE}")
        if certificate is not None:
            mounts.append(f"type=bind,src={certificate},dst={CA_FILE},readonly")

        docker = [
            engine,
            *hardened(name),
            *routing,
            # The scratch a tool is given, and the reason it is a parameter: a
            # command-line tool needs somewhere to put a few kilobytes, and a
            # browser needs somewhere to put its shared memory because
            # `--disable-dev-shm-usage` sends it here.  The mount options do not
            # move -- what a tool may do with its scratch is not negotiable, and
            # only how much of it there is.
            "--tmpfs",
            f"{TMPDIR}:rw,nosuid,nodev,noexec,size={scratch_mb}m,mode=1777",
            "--memory",
            f"{ceilings.memory_mb}m",
            # The same number again: a memory ceiling a container may page past
            # is a ceiling on how fast it uses the machine, not on how much.
            "--memory-swap",
            f"{ceilings.memory_mb}m",
            "--cpus",
            f"{ceilings.cpu_quota:g}",
            "--pids-limit",
            str(ceilings.pids_limit),
            "--workdir",
            TOOL_WORKSPACE if workspace is not None else "/",
        ]
        for mount in mounts:
            docker.extend(("--mount", mount))
        for key, value in sorted(environment.items()):
            docker.extend(("--env", f"{key}={value}"))
        docker.extend((container.image, *command))

        process = subprocess.Popen(
            docker,
            env=host_environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        with process:
            answer = _bounded(
                process,
                ceilings,
                stop=lambda: remove(engine, name, host_environment),
            )
        if answer.timed_out or answer.overflowed:
            # The process is gone and whatever it wrote is a fragment, but the
            # fragment is read anyway: what a run printed before it was taken
            # away is the most an operator will ever be told about why.
            return answer
        produced = _produced(workspace, outputs, ceilings.max_output_bytes)
        return ToolProcess(
            exit_code=answer.exit_code,
            stdout=answer.stdout,
            stderr=answer.stderr,
            outputs=produced,
            # A declared output past the bound is the same overrun as a stream
            # past it, and the run has to end the same way. The file is kept as
            # the prefix it is, but a run whose output was cut off is not a run
            # that succeeded, whichever place the bytes were going.
            overflowed=any(item.truncated for item in produced.values()),
        )
    finally:
        if adapter is not None:
            _unadapt(engine, adapter, door.proxy_container, host_environment)
        shutil.rmtree(staging, ignore_errors=True)


def _staged(staging: Path, inputs: Mapping[str, bytes], outputs: Sequence[str]) -> Path | None:
    """Write the inputs where the plan says they appear, and open a workspace if asked.

    The plan names the container paths, so this is where they are held against
    what the runtime actually mounts: an input under anything but `/input`, or a
    declared output that is not a bare filename, is a plan that has been made to
    name a place, and no argument kind admits a separator for exactly that
    reason.

    `staging` is this process's own directory and stays so.  What crosses is
    readable, and the workspace is writable by everyone, because the user inside
    the container is nameless and owns nothing -- reachable only through a
    parent no other user on this machine can traverse.
    """
    root = staging / "input"
    root.mkdir()
    for path, data in inputs.items():
        placed = PurePosixPath(path)
        if placed.parent != PurePosixPath(TOOL_INPUTS) or placed.name in ("", ".", ".."):
            raise Unavailable(f"an offline tool input is not under {TOOL_INPUTS}: {path}")
        target = root / placed.name
        target.write_bytes(data)
        target.chmod(0o444)
    root.chmod(0o555)

    if not outputs:
        return None
    for name in outputs:
        if name != PurePosixPath(name).name or name in ("", ".", ".."):
            raise Unavailable(f"an offline tool output is not a bare filename: {name}")
    workspace = staging / "work"
    workspace.mkdir()
    workspace.chmod(0o777)
    return workspace


def _bounded(
    process: subprocess.Popen[bytes], ceilings: Ceilings, *, stop: Callable[[], None]
) -> ToolProcess:
    """Read both streams while the process runs, holding it to time and to size.

    Neither bound survives being applied afterwards.  Reading to the end and
    then truncating lets a tool decide how much of the supervisor's memory it
    takes; waiting for exit and then noticing the clock lets it decide how long
    the supervisor waits.  So the reads are incremental, everything past the
    bound is counted and dropped, and the first breach of either takes the
    container away rather than waiting to see what the exit code turns out to be.
    """
    selector = selectors.DefaultSelector()
    streams = {"stdout": process.stdout, "stderr": process.stderr}
    kept = {name: bytearray() for name in streams}
    produced = dict.fromkeys(streams, 0)
    for name, handle in streams.items():
        selector.register(handle, selectors.EVENT_READ, name)

    deadline = time.monotonic() + ceilings.timeout_seconds
    timed_out = overflowed = False
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            for key, _ in selector.select(min(remaining, 0.25)):
                chunk = key.fileobj.read1(65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                produced[key.data] += len(chunk)
                room = ceilings.max_output_bytes - len(kept[key.data])
                if room > 0:
                    kept[key.data].extend(chunk[:room])
            if any(count > ceilings.max_output_bytes for count in produced.values()):
                overflowed = True
                break
    finally:
        selector.close()

    if timed_out or overflowed:
        # The client first, then the container.  The daemon streams a container's
        # output through the attached client, and by here that client is blocked
        # writing into a pipe this loop has stopped reading -- so a removal asked
        # for while it still holds the stream waits on a reader that is never
        # coming, and the removal is what times out instead of the run.
        process.kill()
        stop()
    try:
        process.wait(timeout=max(deadline - time.monotonic(), 10.0))
    except subprocess.TimeoutExpired:
        process.kill()
        stop()
        process.wait(timeout=10.0)
        timed_out = True
    return ToolProcess(
        exit_code=process.returncode,
        stdout=Captured(bytes(kept["stdout"]), produced["stdout"]),
        stderr=Captured(bytes(kept["stderr"]), produced["stderr"]),
        timed_out=timed_out,
        overflowed=overflowed,
    )


def _produced(
    workspace: Path | None, outputs: Sequence[str], limit: int
) -> dict[str, Captured]:
    """Read the declared outputs a run actually left behind.

    Opened without following links and refused unless regular, because the
    container's own user owns this directory: a tool that wrote its declared
    output as a symlink would otherwise have the supervisor resolve it here, on
    the host, where the name means something else entirely.  An output the tool
    did not write is simply absent -- whether that is a failure is the caller's
    question, not this one's.
    """
    if workspace is None:
        return {}
    found: dict[str, Captured] = {}
    for name in outputs:
        try:
            handle = os.open(workspace / name, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError:
            continue
        try:
            status = os.fstat(handle)
            if not stat.S_ISREG(status.st_mode):
                continue
            with open(handle, "rb", closefd=False) as opened:
                found[name] = Captured(opened.read(limit), status.st_size)
        finally:
            os.close(handle)
    return found


def _adapter(
    engine: str, door: AgentContainer, network: str, host_environment: Mapping[str, str]
) -> None:
    """One internal network for one tool run, whose only peer is the proxy.

    A network of its own rather than the Agent's.  That network's whole claim is
    that the only peer on it is the proxy: a tool attached to it would be a
    second peer, which is both a route between the tool and whatever agent
    process is running beside it and a topology `one_peer` would refuse for the
    next run either of them made.  So a tool that declares the proxy adapter gets
    the same shape of boundary rather than a share of somebody else's -- created
    here, the proxy joined to it under the hostname the door's URL names, held to
    the same assertion, and taken away when the run ends.

    The caller names the network before this is called, so a step that fails
    part of the way through is still a network the `finally` knows to remove.
    """
    proxy_host, _ = proxy_peer(door.proxy_url)
    engine_command(
        engine, ("network", "create", "--internal", network), host_environment,
        f"the tool egress network cannot be created: {network}",
    )
    join(engine, network, door.proxy_container, proxy_host, host_environment)


def _unadapt(
    engine: str, network: str, proxy_container: str, host_environment: Mapping[str, str]
) -> None:
    """Take one run's egress network away, whatever became of the run.

    Unchecked, and in this order: the proxy is a container this harness does not
    own and must be left as it was found, and a network still holding a peer is
    a network the engine will not remove.  A failure here is not something to
    raise over the run's own answer -- what is left behind is one empty network
    with this run's name on it, which is a thing an operator can see and remove.
    """
    engine_command(
        engine, ("network", "disconnect", "--force", network, proxy_container),
        host_environment, None,
    )
    engine_command(engine, ("network", "rm", network), host_environment, None)


def engine_command(
    engine: str,
    arguments: Sequence[str],
    host_environment: Mapping[str, str],
    refusal: str | None,
) -> None:
    """One engine command that changes something, with `refusal` if it may not fail."""
    answer = subprocess.run(
        [engine, *arguments],
        env=dict(host_environment),
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if answer.returncode and refusal is not None:
        detail = (answer.stderr or answer.stdout).strip().splitlines()
        raise Unavailable(f"{refusal}: {detail[-1] if detail else 'no reason given'}")


def remove(engine: str, name: str, host_environment: Mapping[str, str]) -> None:
    """Take one named container away, now, and never mind whether it was there."""
    subprocess.run(
        [engine, "rm", "--force", name],
        env=dict(host_environment),
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )


def _supplied(container: AgentContainer) -> list[tuple[str, Path, bool, bool]]:
    """Where each host directory this container supplies lands inside it.

    One table, read by everything that needs the answer.  Which application and
    which SDK a child resolves is exactly what the startup assertion measures,
    so two lists that had to agree about where a directory landed would be two
    answers to one question.  Each row is the destination, the host directory,
    whether it crosses read-only, and whether it is on the child's import path.
    """
    rows = (
        (APPLICATION, container.application, True, True),
        (SDK, container.sdk, True, True),
        (HOME_DIR, container.home, False, False),
    )
    return [
        (destination, Path(host), readonly, imported)
        for destination, host, readonly, imported in rows
        if host is not None
    ]


def _mounts(container: AgentContainer, certificate: Path) -> list[str]:
    """Everything the runtime puts inside the boundary, and nothing else.

    The trust root crosses as a file rather than as the directory holding it,
    because the signing key is what lies beside it: the difference between an
    Agent that can be intercepted and an Agent that can intercept is exactly
    one file.  The application and the SDK cross read-only, because a child
    that could write to them could choose what the next child is measured as.
    The home is the one writable mount -- the CLI keeps session state in it.

    A caller names the host directories, so the two properties that make them
    contained are checked here rather than assumed of the caller: no mount may
    carry the operator's own home, and the writable one has to be writable by
    the user the child actually runs as.
    """
    arguments = ["--mount", f"type=bind,src={certificate},dst={CA_FILE},readonly"]
    for destination, host, readonly, _ in _supplied(container):
        source = host.resolve()
        if not source.is_dir():
            raise Unavailable(f"an Agent container mount is not a directory: {source}")
        if _carries_operator_home(source):
            raise Unavailable(f"an Agent container mount carries the operator's home: {source}")
        if not readonly and not writable_by_the_child(source):
            raise Unavailable(f"an Agent container home the child cannot write: {source}")
        mount = f"type=bind,src={source},dst={destination}"
        arguments.extend(("--mount", f"{mount},readonly" if readonly else mount))
    return arguments


def _carries_operator_home(source: Path) -> bool:
    """Whether mounting this directory would put the operator's home inside.

    Asked of every mount and not only the writable one: read-only is enough to
    read a credentials file, and the whole point of mounting a home is that the
    CLI resolves a credential from it.  A directory *under* the operator's home
    is fine and common -- the checkout and the installed SDK usually live there
    -- so what is refused is the home itself and anything containing it.
    """
    home = Path(os.path.expanduser("~")).resolve()
    return source == home or source in home.parents


def writable_by_the_child(source: Path) -> bool:
    """Whether the container's own unprivileged user could write this directory.

    Decided from the directory's ownership and mode rather than from
    `os.access`, which would answer for the supervisor -- a different user, on
    the machine that is not the one running the child.
    """
    status = source.stat()
    if status.st_uid == UID:
        return status.st_mode & 0o300 == 0o300
    if status.st_gid == GID:
        return status.st_mode & 0o030 == 0o030
    return status.st_mode & 0o003 == 0o003


def engine_for(name: str) -> str:
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


def proxy_peer(url: str) -> tuple[str, int]:
    """The name and port the Agent proxy URL claims, or a refusal.

    Both halves out of one parse.  The name is what the topology assertion below
    looks for among the network's aliases; the port is what the door itself has
    to bind, which is why the port is returned at all -- see `door.main` for who
    binds it and what goes wrong when the two disagree.
    """
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
    return parsed.hostname, port


def peers(engine: str, network: str) -> tuple[bool, dict[str, str]]:
    """Whether this network is internal, and the identity and name of each peer.

    One parse for the two questions everything below asks of a network, and the
    only place the engine's spelling of either is read.  The identity is the key
    because that is what a container's own record can be compared against; the
    name is what an operator is told, because an identity in a refusal is a
    refusal nobody can act on.
    """
    topology = _inspect(engine, "network", network)
    attached = topology.get("Containers") or {}
    if not isinstance(attached, dict):
        raise Unavailable(f"the peer set of {network} cannot be read")
    return topology.get("Internal") is True, {
        str(identity): str((peer or {}).get("Name") or identity)
        for identity, peer in attached.items()
    }


def empty_network(engine: str, network: str) -> None:
    """Refuse unless this network is internal and nothing is on it yet.

    The question `one_peer` cannot ask.  That one says the proxy is alone, which
    can only be true once the proxy exists; a peer that was already there is a
    peer that had a route to the door for however long it took to start it.  So
    a door is put on a network that is provably empty first, and held to
    `one_peer` after.
    """
    internal, attached = peers(engine, network)
    if not internal:
        raise Unavailable(f"the Agent network is not internal: {network}")
    if attached:
        raise Unavailable(
            "the Agent network already has peers: " + ", ".join(sorted(attached.values()))
        )


@contextlib.contextmanager
def held(network: str) -> Iterator[None]:
    """Hold this machine's claim on one Agent network, or refuse to launch.

    `one_peer` is a check-then-act. It reads the network and says the door is
    alone on it, and the engine holds nothing at all between that read and the
    `run` that follows -- so two launches inside each other's window both read a
    clear network and both attach, and each child is then a peer of the other.
    The internal network carries no route off itself and every route across it.

    So the window is held here instead, and by the kernel rather than by a
    convention: an exclusive `flock` on a file named after the network, taken
    before the check and let go after the child is gone. Two `rk run` processes
    are two open file descriptions on one inode, which is the case that has to
    be answered -- a flag in this process's memory would be a claim the other
    process cannot see, and the roster's concurrency caps are counted in a
    database that knows nothing about which machine is launching.

    Refused rather than queued. A launch that waited would hold a claimed Task
    open for as long as the child in front of it runs, and would tell its caller
    it had a boundary only afterwards; `one_peer` refuses a second child that is
    already up, and this is the same answer given a moment earlier.

    The file is a name and never a message: nothing is written into it, and the
    claim is the lock rather than the contents, so a stale file from a killed
    process claims nothing.
    """
    directory = _lock_directory()
    # Named by digest rather than by the network itself: the name comes from the
    # environment, and a name is not a filename until something has decided what
    # `..` in it means.
    claim = directory / (hashlib.sha256(network.encode("utf-8")).hexdigest()[:32] + ".lock")
    handle = os.open(claim, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Unavailable(
                f"another launch on this machine holds the Agent network: {network}"
            ) from None
        yield
    finally:
        os.close(handle)


def _lock_directory() -> Path:
    """The directory this user's network claims live in, made if it is absent.

    `XDG_RUNTIME_DIR` when the machine has one, because it is already this
    user's alone and is cleared when the session ends. The temporary directory
    otherwise, under a name carrying the user id, which is where a claim between
    two `rk run` processes of one installation can still be found.

    A directory that is not this user's own is a directory somebody else can put
    a file in, so it is refused rather than used.
    """
    base = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
    directory = base / f"{LOCKS}-{os.getuid()}"
    directory.mkdir(mode=0o700, exist_ok=True)
    status = directory.lstat()
    if not stat.S_ISDIR(status.st_mode) or status.st_uid != os.getuid():
        raise Unavailable(f"the Agent network claims are not this user's own: {directory}")
    if status.st_mode & 0o077:
        directory.chmod(0o700)
    return directory


def one_peer(engine: str, network: str, proxy_container: str, proxy_host: str) -> None:
    internal, attached = peers(engine, network)
    if not internal:
        raise Unavailable(f"the Agent network is not internal: {network}")

    proxy = _inspect(engine, "container", proxy_container)
    proxy_id = str(proxy.get("Id") or "")
    joined = (proxy.get("NetworkSettings") or {}).get("Networks") or {}
    endpoint = joined.get(network) if isinstance(joined, dict) else None
    if proxy_id not in attached or not isinstance(endpoint, dict):
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

    others = sorted(name for identity, name in attached.items() if identity != proxy_id)
    if others:
        raise Unavailable(
            "the Agent network has peers other than the proxy: " + ", ".join(others)
        )


def host_route(engine: str, proxy_container: str) -> str:
    """The address this machine answers on from inside the door.

    The door sits on two kinds of network: the internal one it is the only peer
    of, which is how children reach it and has no route anywhere else, and the
    routable one it reaches targets through.  That second one has a gateway, and
    the gateway is this host -- so a process bound there is reachable from the
    door and from nothing a child can address.  That is the property the fixture
    route in `evaluation.py` is built on, and this is where the address comes
    from: the engine's own record of the attachment, not a guess at what a
    bridge numbers its subnet from.

    Exactly one routable attachment, or nothing.  A door on two of them has two
    answers to "where is this machine", and a fixture bound at one of them would
    be reachable at an address the Receipt does not name.
    """
    record = _inspect(engine, "container", proxy_container)
    attachments = (record.get("NetworkSettings") or {}).get("Networks") or {}
    if not isinstance(attachments, dict):
        raise Unavailable(f"the door's networks cannot be read: {proxy_container}")
    routes = {}
    for network, attachment in attachments.items():
        if not isinstance(attachment, dict):
            # Refused rather than skipped: an attachment this function cannot
            # read is a network it cannot say is internal, and skipping it would
            # let a door on two routable networks answer as if it were on one.
            raise Unavailable(
                f"the door's attachment to {network} cannot be read: {proxy_container}"
            )
        internal, _ = peers(engine, str(network))
        gateway = str(attachment.get("Gateway") or "")
        if not internal and gateway:
            routes[str(network)] = gateway
    if not routes:
        raise Unavailable(
            f"the door is on no network with a route off it: {proxy_container}"
        )
    if len(routes) > 1:
        raise Unavailable(
            "the door is on more than one routable network, so this machine has no "
            "one address from inside it: " + ", ".join(sorted(routes))
        )
    return next(iter(routes.values()))


def join(
    engine: str,
    network: str,
    proxy_container: str,
    proxy_host: str,
    host_environment: Mapping[str, str],
) -> None:
    """Attach the door to one network under the name its peers dial, and hold it there.

    Two things that are one thing.  An attachment whose alias is not the name the
    children's proxy URL resolves is an attachment nothing on the network can
    use, and an attachment that turns out to have brought a second peer with it
    is a network with a route across it.  Both are asked here, so neither the
    tool adapter nor the door's own start can do the first and forget the second.
    """
    engine_command(
        engine,
        ("network", "connect", "--alias", proxy_host, network, proxy_container),
        host_environment,
        f"the door cannot be joined to {network}: {proxy_container}",
    )
    one_peer(engine, network, proxy_container, proxy_host)
