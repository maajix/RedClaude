"""The half of a browser Mission that runs inside the container.

This file is not imported by anything.  It is staged into `/input` and run by
the container's own interpreter, which is why it imports nothing from this
package and nothing from outside the standard library: the boundary the browser
runs behind has no `redkraken` on its path and no index to install one from.
Everything it needs to know arrives in one JSON document the database wrote and
the host completed -- the steps, the ceilings, and the three facts about the
door -- so that no constant here can drift from the constant it mirrors.

Three things run here, in this order.

The **capability shim** is the reason this file exists at all.  Chromium cannot
be made to send `Proxy-Authorization: RedKraken <hex>`: `--proxy-server` ignores
credentials in the URL, `Fetch.continueWithAuth` speaks only Basic and Digest,
and `Network.setExtraHTTPHeaders` decorates the request to the origin rather
than the hop to the proxy and never touches a CONNECT at all.  So chromium is
pointed at a listener on this container's own loopback, and that listener puts
the control headers on the hop the door reads and relays the bytes onward.  It
decides nothing.  It holds no policy, no scope, no identity and no allowlist:
every byte still crosses the door, is still classified there, and still earns a
Receipt there.  The capability it carries is bound to this one Tool run, expires
in five minutes, and buys a compromised renderer nothing it could not already
have by making the same request through chromium's own proxy connection.

The **debugger** is a Chrome DevTools Protocol client over a websocket this
module frames by hand, because a browser is the one tool that cannot be driven
by an argv.

The **mission** walks the steps.  Every value the plan supplies -- a selector, a
literal to type, a probe's payload -- crosses into the page as a
`Runtime.callFunctionOn` argument rather than as text spliced into an
expression, so a value can never become code.  The single exception is a
registered probe's JavaScript, which is evaluated as the expression it is: that
text comes from `browser_probes`, which only a migration writes.

What this prints on stdout is one JSON document and nothing else.  Evidence goes
to `/work` under names the host derived from the same plan, because a driver
that could name its own output files would be a driver that could name a place.
"""

import base64
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

#: The browser itself, at the path its image installs it.  Named here rather
#: than in the plan for the same reason the plan may not name a path: an argv
#: that could say which binary to start is an argv that could start another.
CHROMIUM = "/headless-shell/headless-shell"

#: Where the host mounts the two staging directories.  Mirrors `isolation`.
PLAN = "/input/plan.json"
WORKSPACE = "/work"
PROFILE = "/work/profile"

#: Loopback coordinates, both inside this container and reachable from nowhere
#: else: the network this container is on has exactly one peer and it is the
#: door.  The debugger port is chromium's; the shim port is ours.
LOOPBACK = "127.0.0.1"
DEBUG_PORT = 9222
SHIM_PORT = 3128

#: How long to wait for chromium to open its debugger, and how often to ask.
READY_SECONDS = 30.0
READY_INTERVAL = 0.2

#: Headers that belong to one hop and must not be copied onto the next, plus
#: the two the shim is here to set.  A client-supplied control header is dropped
#: rather than forwarded: the door refuses a request that names its Program
#: twice, so a page that could inject one could deny this Mission its egress.
HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-connection",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)

#: The actions whose failure makes the rest of the plan meaningless.  A
#: `wait_for` that never matched leaves the next step typing into nothing, so
#: the mission stops and closes as an error.  An assertion or a probe that
#: comes back false is not a failure -- it is the answer -- and the plan runs on.
HALT_ON_FALSE = frozenset({"wait_for", "fill", "inject", "click"})

#: Every CDP name under which a request leaves the page for the door.  Ordinary
#: navigation, XHR, fetch and subresources all arrive as `requestWillBeSent`; a
#: websocket handshake never does, and gets its own event.  Both are HTTP
#: requests the door decides on and writes a Receipt for, so both are counted.
NETWORK_REQUEST_EVENTS = frozenset(
    {"Network.requestWillBeSent", "Network.webSocketWillSendHandshakeRequest"}
)

#: What every artifact of this mission is called is the host's to say, not this
#: driver's: the host has to declare the files it expects out of the container
#: before the container starts, and two places composing the same names is one
#: place too many the day either changes. So a step that produces evidence
#: carries the name to write it under, and the console carries this key.
CONSOLE = "console"

#: The chromium flags this harness has proven, and the reason for each.
FLAGS = (
    # No setuid sandbox of Chromium's own: the Agent boundary is what confines
    # this process, and the two together need a capability set this container
    # drops.
    "--no-sandbox",
    "--disable-gpu",
    # Send shared memory to TMPDIR instead of /dev/shm, which a hardened
    # container does not have enough of.
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-sync",
    # Nothing on this network answers a metrics endpoint, and an attempt would
    # be one more Receipt for something nobody asked for.
    "--disable-breakpad",
    "--metrics-recording-only",
)


class Refused(Exception):
    """Something the mission will not do, said in one sentence."""


# ---------------------------------------------------------------------------
# The capability shim
# ---------------------------------------------------------------------------


def _handler(door, control, timeout):
    """One handler class bound to one door, one capability and one deadline.

    A closure rather than class attributes assigned after the fact, because the
    control headers are a secret for the length of one run and a class that
    still held them afterwards would be a place to find them.
    """

    forbidden = HOP_BY_HOP | {name.lower() for name in control}

    class Shim(BaseHTTPRequestHandler):
        """Add the control headers to one hop and get out of the way.

        Every request opens its own connection to the door and asks the door to
        close it, which is what makes this safe to write in forty lines: a
        connection carrying exactly one request needs no framing, no
        content-length arithmetic and no chunked decoder, and neither side can
        smuggle a second request past the headers this adds.  Chromium opens
        another connection for the next request, which on loopback costs
        nothing.
        """

        protocol_version = "HTTP/1.1"
        server_version = "redkraken-shim"
        sys_version = ""

        def do_CONNECT(self):
            # The capability goes on the CONNECT, because that is the hop the
            # door can read: everything after it is the target's TLS.
            self._relay(f"CONNECT {self.path} HTTP/1.1", {"Host": self.path}, True)

        def _forward(self):
            # `self.path` is already the absolute form a proxy request carries,
            # which is exactly what the door expects to be given.
            self._relay(f"{self.command} {self.path} HTTP/1.1", self.headers, False)

        do_GET = _forward
        do_HEAD = _forward
        do_POST = _forward
        do_PUT = _forward
        do_PATCH = _forward
        do_DELETE = _forward
        do_OPTIONS = _forward

        def _relay(self, line, headers, tunnel):
            self.close_connection = True
            try:
                upstream = socket.create_connection(door, timeout=timeout)
            except OSError as error:
                self.send_error(502, "the door is not reachable", str(error))
                return
            with upstream:
                head = [line]
                for name, value in headers.items():
                    if name.lower() not in forbidden:
                        head.append(f"{name}: {value}")
                if not tunnel:
                    head.append("Connection: close")
                head.extend(f"{name}: {value}" for name, value in control.items())
                try:
                    upstream.sendall(("\r\n".join(head) + "\r\n\r\n").encode("latin-1"))
                except OSError as error:
                    self.send_error(502, "the door closed the connection", str(error))
                    return
                self._both_ways(upstream)

        def _both_ways(self, upstream):
            """Pump until one side ends, then end the other.

            The client side is read through `self.rfile` rather than through the
            socket: the header parser above it is buffered, so a body that
            arrived in the same segment as the headers is already in that buffer
            and reading the socket underneath would lose it.
            """

            def upward():
                try:
                    while True:
                        chunk = self.rfile.read1(65536)
                        if not chunk:
                            break
                        upstream.sendall(chunk)
                except OSError:
                    pass
                finally:
                    try:
                        upstream.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass

            pump = threading.Thread(target=upward, daemon=True)
            pump.start()
            try:
                while True:
                    chunk = upstream.recv(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except OSError:
                pass
            finally:
                try:
                    self.connection.shutdown(socket.SHUT_RD)
                except OSError:
                    pass
                pump.join(timeout=2.0)

        def log_message(self, *arguments):
            # Stdout is the result document and nothing else, and a request log
            # of what a target's page asked for is the door's record to keep.
            pass

    return Shim


def open_shim(plan):
    """Start the loopback shim and return the server, listening."""
    door = plan["door"]
    server = ThreadingHTTPServer(
        (LOOPBACK, SHIM_PORT),
        _handler(
            (door["host"], int(door["port"])),
            dict(door["headers"]),
            float(plan["step_timeout_ms"]) / 1000.0 + 30.0,
        ),
    )
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# ---------------------------------------------------------------------------
# The debugger
# ---------------------------------------------------------------------------


class Socket:
    """One websocket client connection, RFC 6455, text frames only.

    Hand-framed because the standard library has no websocket client and this
    container has no place to get one from.  Only what a debugger connection
    needs is here: masked client frames, the two extended length forms, and
    enough of the control opcodes to ignore a ping and notice a close.
    """

    def __init__(self, url, timeout):
        rest = url.split("://", 1)[1]
        authority, _, path = rest.partition("/")
        host, _, port = authority.partition(":")
        self.socket = socket.create_connection((host, int(port or 80)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.socket.sendall(
            (
                f"GET /{path} HTTP/1.1\r\nHost: {authority}\r\n"
                f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode("latin-1")
        )
        self.buffer = b""
        while b"\r\n\r\n" not in self.buffer:
            chunk = self.socket.recv(4096)
            if not chunk:
                raise Refused("the debugger closed during the handshake")
            self.buffer += chunk
        head, _, self.buffer = self.buffer.partition(b"\r\n\r\n")
        if b"101" not in head.split(b"\r\n")[0]:
            raise Refused(f"the debugger refused the upgrade: {head[:120]!r}")

    def _read(self, count):
        while len(self.buffer) < count:
            chunk = self.socket.recv(65536)
            if not chunk:
                raise Refused("the debugger closed the connection")
            self.buffer += chunk
        taken, self.buffer = self.buffer[:count], self.buffer[count:]
        return taken

    def send(self, message):
        data = json.dumps(message).encode()
        header = bytearray([0x81])
        mask = os.urandom(4)
        size = len(data)
        if size < 126:
            header.append(0x80 | size)
        elif size < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", size))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", size))
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        self.socket.sendall(bytes(header) + masked)

    def receive(self):
        while True:
            first, second = self._read(2)
            opcode = first & 0x0F
            size = second & 0x7F
            if size == 126:
                size = struct.unpack("!H", self._read(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", self._read(8))[0]
            body = self._read(size) if size else b""
            if opcode == 0x9:
                continue
            if opcode == 0x8:
                raise Refused("the debugger closed the socket")
            if opcode in (0x1, 0x2):
                return json.loads(body)

    def close(self):
        try:
            self.socket.close()
        except OSError:
            pass


class Debugger:
    """Calls and events over one debugger socket.

    Events are kept in arrival order and never consumed, because two different
    questions are asked of them -- what happened during step four, and what the
    console said all mission -- and a queue that answered the first would have
    thrown away the second.
    """

    def __init__(self, url, timeout):
        self.socket = Socket(url, timeout)
        self.timeout = timeout
        self.counter = 0
        self.events = []

    def call(self, method, params=None, session=None):
        self.counter += 1
        message = {"id": self.counter, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        self.socket.send(message)
        while True:
            answer = self.socket.receive()
            if answer.get("id") == self.counter:
                if "error" in answer:
                    raise Refused(f"{method}: {answer['error'].get('message')}")
                return answer.get("result", {})
            if "method" in answer:
                self.events.append(answer)

    def drain(self, seconds):
        """Collect whatever arrives for a while, and stop."""
        self.wait(seconds, lambda event: False)

    def wait(self, seconds, matches, since=0):
        """The first event `matches` accepts, or None once `seconds` are gone.

        `since` is an index into the events already collected, so a caller that
        took the length before it acted sees an event that arrived while it was
        acting -- a load that finished before the wait began is not missed.
        """
        for event in self.events[since:]:
            if matches(event):
                return event
        deadline = time.monotonic() + seconds
        self.socket.socket.settimeout(0.2)
        try:
            while time.monotonic() < deadline:
                try:
                    answer = self.socket.receive()
                except (TimeoutError, socket.timeout):
                    continue
                if "method" not in answer:
                    continue
                self.events.append(answer)
                if matches(answer):
                    return answer
        finally:
            self.socket.socket.settimeout(self.timeout)
        return None

    def close(self):
        self.socket.close()


# ---------------------------------------------------------------------------
# The mission
# ---------------------------------------------------------------------------


class Mission:
    """One plan, walked, with what each step is allowed to report."""

    def __init__(self, plan, debugger, session):
        self.plan = plan
        self.debugger = debugger
        self.session = session
        self.step_timeout = float(plan["step_timeout_ms"]) / 1000.0
        self.limit = int(plan["max_artifact_bytes"])
        self.artifacts = []
        # Held on the Mission rather than returned by `walk`, because a step
        # that halts the plan does not un-happen: what ran before the halt is
        # what the host records, and a return value is lost to the raise.
        self.results = []

    # -- what a step is allowed to do to the page ---------------------------

    def _page(self, body, arguments=()):
        """Call one function in the page with the plan's values as arguments.

        Not `Runtime.evaluate`.  A selector or a literal to type is data the
        plan carries, and the way to keep data from becoming code is to hand it
        across as an argument rather than to build an expression out of it.
        """
        window = self.debugger.call(
            "Runtime.evaluate", {"expression": "window"}, self.session
        )["result"]
        answer = self.debugger.call(
            "Runtime.callFunctionOn",
            {
                "objectId": window["objectId"],
                "functionDeclaration": body,
                "arguments": [{"value": value} for value in arguments],
                "returnByValue": True,
                "awaitPromise": True,
            },
            self.session,
        )
        if "exceptionDetails" in answer:
            said = answer["exceptionDetails"].get("text", "the page raised")
            raise Refused(f"the page refused the step: {said}")
        return answer["result"].get("value")

    def _kept(self, name, data, stream, ordinal=None, output_name=None):
        """Write one piece of evidence to the workspace and declare it."""
        truncated = len(data) > self.limit
        with open(os.path.join(WORKSPACE, name), "wb") as handle:
            handle.write(data[: self.limit])
        self.artifacts.append(
            {
                "file": name,
                "stream": stream,
                "ordinal": ordinal,
                "output_name": output_name,
                "produced_bytes": len(data),
                "truncated": truncated,
            }
        )

    # -- the actions --------------------------------------------------------

    def navigate(self, step):
        url = step["arguments"]["url"]
        since = len(self.debugger.events)
        self.debugger.call("Page.navigate", {"url": url}, self.session)
        loaded = self.debugger.wait(
            self.step_timeout,
            lambda event: event["method"] == "Page.loadEventFired",
            since,
        )
        # Zero, not null, when no Document response arrived.  A refused or
        # timed-out navigation is an outcome the mission has to be able to
        # record, and `rk2_browser_outcome_word` admits a boolean, a small
        # integer or a lowercase word -- JSON null is none of the three, so a
        # null here would abort the whole mission rather than write down that
        # the page never answered.  Zero is the same thing browsers report for a
        # request that never reached a status line.
        status = 0
        for event in self.debugger.events[since:]:
            if (
                event["method"] == "Network.responseReceived"
                and event["params"].get("type") == "Document"
            ):
                status = event["params"]["response"].get("status") or 0
        # `scope_class` is not here on purpose.  What class a URL belongs to is
        # the door's answer, read from the Receipt the door wrote, and a
        # container that could report its own would be a container that could
        # call an out-of-scope host in-scope.
        return {"http_status": status, "document_loaded": loaded is not None}

    def wait_for(self, step):
        selector = step["arguments"]["selector"]
        asked = step["arguments"].get("timeout_ms")
        limit = min(float(asked) / 1000.0, self.step_timeout) if asked else self.step_timeout
        deadline = time.monotonic() + limit
        while True:
            if self._page("function (s) { return !!document.querySelector(s); }", (selector,)):
                return {"matched": True}
            if time.monotonic() >= deadline:
                return {"matched": False}
            time.sleep(0.1)

    def _type(self, selector, value):
        """Put one literal in one field and tell the page it happened.

        The two events are what a framework listens for; a value assigned
        without them is a value the application never sees.
        """
        return self._page(
            """function (s, v) {
                var node = document.querySelector(s);
                if (!node) { return false; }
                node.focus();
                node.value = v;
                node.dispatchEvent(new Event('input', { bubbles: true }));
                node.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }""",
            (selector, value),
        )

    def fill(self, step):
        return {"matched": bool(self._type(step["arguments"]["selector"], step["arguments"]["value"]))}

    def inject(self, step):
        # The payload comes from `browser_probes` by way of the plan, not from
        # the caller: what may be typed at a target is a migration's decision.
        return {"matched": bool(self._type(step["arguments"]["selector"], step["payload"]))}

    def click(self, step):
        selector = step["arguments"]["selector"]
        since = len(self.debugger.events)
        clicked = self._page(
            """function (s) {
                var node = document.querySelector(s);
                if (!node) { return false; }
                node.click();
                return true;
            }""",
            (selector,),
        )
        if clicked:
            # A click may submit, navigate or do nothing at all, and there is no
            # event that means "whatever this was, it is over".  Waiting for the
            # load that a submission causes and settling for the timeout when
            # there is none is the honest shape.
            self.debugger.wait(
                self.step_timeout,
                lambda event: event["method"] == "Page.loadEventFired",
                since,
            )
        return {"matched": bool(clicked)}

    def assert_text(self, step):
        return {"matched": bool(self._present(step["arguments"]["text"]))}

    def assert_absent(self, step):
        return {"matched": not self._present(step["arguments"]["text"])}

    def _present(self, text):
        return self._page(
            """function (t) {
                var body = document.body ? document.body.innerText : '';
                return body.indexOf(t) !== -1;
            }""",
            (text,),
        )

    def probe(self, step):
        # The one place a string becomes an expression.  `browser_probes` is
        # written by migration and readable by nobody the Agent can reach, and
        # `check_browser_runs` refuses any entry that touches stored
        # credentials -- so this text is the harness's, never a caller's.
        answer = self.debugger.call(
            "Runtime.evaluate",
            {"expression": step["javascript"], "returnByValue": True},
            self.session,
        )
        if "exceptionDetails" in answer:
            said = answer["exceptionDetails"].get("text", "the probe raised")
            raise Refused(f"the probe {step['arguments']['probe']} did not run: {said}")
        raw = answer["result"].get("value")
        if not isinstance(raw, str):
            raise Refused(
                f"the probe {step['arguments']['probe']} did not return a JSON document"
            )
        try:
            body = json.loads(raw)
        except ValueError as error:
            raise Refused(
                f"the probe {step['arguments']['probe']} returned no readable JSON: {error}"
            ) from error
        verdict = body.get("verdict")
        if verdict not in step["verdicts"]:
            raise Refused(
                f"the probe {step['arguments']['probe']} returned a verdict"
                f" it does not declare: {verdict!r}"
            )
        self._kept(
            step["artifact"],
            raw.encode(),
            "probe",
            step["ordinal"],
            step["arguments"]["probe"],
        )
        return {"verdict": verdict}

    def capture_dom(self, step):
        markup = self._page(
            "function () { return document.documentElement.outerHTML; }"
        )
        self._kept(step["artifact"], (markup or "").encode(), "dom", step["ordinal"])
        return {"captured": bool(markup)}

    def screenshot(self, step):
        answer = self.debugger.call(
            "Page.captureScreenshot", {"format": "png"}, self.session
        )
        image = base64.b64decode(answer.get("data") or "")
        self._kept(step["artifact"], image, "screenshot", step["ordinal"])
        return {"captured": bool(image)}

    # -- the walk -----------------------------------------------------------

    def walk(self):
        """Every step in order, until one of them makes the rest meaningless."""
        for step in self.plan["steps"]:
            action = getattr(self, step["action"], None)
            if action is None:
                raise Refused(f"this driver does not perform {step['action']}")
            since = len(self.debugger.events)
            outcome = action(step)
            # Both spellings, because CDP has two.  A websocket handshake is an
            # HTTP request that goes through the door and earns a Receipt like
            # any other, but it is never announced as `requestWillBeSent`, so
            # counting only that name would leave every socket invisible in
            # exactly the direction `check_browser_receipts` reads -- it faults
            # when the count of requests exceeds the count of Receipts, and an
            # uncounted request can never make it fire.
            requests = sum(
                1
                for event in self.debugger.events[since:]
                if event["method"] in NETWORK_REQUEST_EVENTS
            )
            self.results.append(
                {
                    "ordinal": step["ordinal"],
                    "action": step["action"],
                    "outcome": outcome,
                    "network_requests": requests,
                }
            )
            if step["action"] in HALT_ON_FALSE and not outcome.get("matched"):
                raise Refused(
                    f"step {step['ordinal']} ({step['action']}) matched nothing,"
                    " so the rest of the plan would act on a page that is not there"
                )

    def console(self):
        """Everything the page said, as one line per entry.

        Kept whether or not the mission finished: what a page logged on the way
        to failing is exactly what an operator will want.
        """
        lines = []
        for event in self.debugger.events:
            if event["method"] == "Runtime.consoleAPICalled":
                params = event["params"]
                lines.append(
                    {
                        "source": "console",
                        "level": params.get("type"),
                        "text": " ".join(
                            str(argument.get("value", argument.get("description", "")))
                            for argument in params.get("args", ())
                        ),
                    }
                )
            elif event["method"] == "Log.entryAdded":
                entry = event["params"]["entry"]
                lines.append(
                    {
                        "source": entry.get("source"),
                        "level": entry.get("level"),
                        "text": entry.get("text"),
                    }
                )
        body = "".join(json.dumps(line) + "\n" for line in lines).encode()
        self._kept(self.plan[CONSOLE], body, "console")


# ---------------------------------------------------------------------------
# Starting and stopping the browser
# ---------------------------------------------------------------------------


def start_browser(plan, log):
    """Chromium, pointed at the shim and told which certificate to believe.

    The pin is the leaf key's public key, not the run CA's, because the run
    authority signs every host with one key -- so one pin covers every target
    this mission touches, and covers nothing else.  It is passed instead of
    installing the CA because this image has no certificate store to install
    into, and it is preferred to `--ignore-certificate-errors` for the reason
    that flag exists to warn about: that one trusts everything, and this one
    trusts exactly what the door presents.
    """
    return subprocess.Popen(
        [
            CHROMIUM,
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--remote-debugging-address={LOOPBACK}",
            f"--user-data-dir={PROFILE}",
            f"--window-size={plan['viewport_width']},{plan['viewport_height']}",
            f"--proxy-server=http://{LOOPBACK}:{SHIM_PORT}",
            f"--ignore-certificate-errors-spki-list={plan['certificate_pin']}",
            *FLAGS,
            "about:blank",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=log,
    )


def debugger_url(deadline):
    """Chromium's websocket address, once it has one."""
    # An opener with no proxies: this container's environment points every
    # scheme at the door, and asking the door for the browser's own loopback
    # would be a Receipt for a request nobody made.
    direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        try:
            with direct.open(
                f"http://{LOOPBACK}:{DEBUG_PORT}/json/version", timeout=1.0
            ) as answer:
                return json.loads(answer.read())["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(READY_INTERVAL)
    return None


def tail(log, count=2000):
    """The last of whatever chromium said, for a mission that never started."""
    try:
        log.flush()
        size = os.fstat(log.fileno()).st_size
        log.seek(max(0, size - count))
        return log.read().decode("utf-8", "replace")
    except OSError:
        return ""


def attach(debugger):
    """One page, attached to, with the four domains a mission reads."""
    target = debugger.call("Target.createTarget", {"url": "about:blank"})["targetId"]
    session = debugger.call(
        "Target.attachToTarget", {"targetId": target, "flatten": True}
    )["sessionId"]
    for domain in ("Page", "Runtime", "Network", "Log"):
        debugger.call(f"{domain}.enable", session=session)
    return session


def main(argv):
    path = argv[1] if len(argv) > 1 else PLAN
    with open(path, "rb") as handle:
        plan = json.loads(handle.read())

    os.makedirs(PROFILE, exist_ok=True)
    deadline = time.monotonic() + float(plan["timeout_seconds"])
    mission = None
    status, detail = "error", "the mission did not start"

    open_shim(plan)
    # The scratch the supervisor gave this container, which is the one place a
    # browser's own noise belongs: the workspace beside it is evidence, and a
    # log written there would be a file the mission never declared.  Read
    # without a fallback on purpose -- nothing but `isolation.run_tool` starts
    # this, and a driver started another way should say so here.
    log = open(os.path.join(os.environ["TMPDIR"], "browser.log"), "w+b")
    browser = start_browser(plan, log)
    debugger = None
    try:
        url = debugger_url(min(deadline, time.monotonic() + READY_SECONDS))
        if url is None:
            detail = f"the browser opened no debugger: {tail(log)}"
        else:
            debugger = Debugger(url, timeout=max(1.0, deadline - time.monotonic()))
            session = attach(debugger)
            mission = Mission(plan, debugger, session)
            try:
                mission.walk()
                status, detail = "success", ""
            except Refused as error:
                detail = str(error)
            mission.console()
    except Refused as error:
        detail = str(error)
    except Exception as error:  # the container's last word is still a sentence
        detail = f"{type(error).__name__}: {error}"
    finally:
        if debugger is not None:
            try:
                debugger.call("Browser.close")
            except Exception:
                pass
            debugger.close()
        if browser.poll() is None:
            browser.terminate()
            try:
                browser.wait(timeout=10)
            except subprocess.TimeoutExpired:
                browser.kill()
        log.close()

    json.dump(
        {
            "plan_sha256": plan["plan_sha256"],
            "status": status,
            "detail": detail,
            "steps": mission.results if mission is not None else [],
            "artifacts": mission.artifacts if mission is not None else [],
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
