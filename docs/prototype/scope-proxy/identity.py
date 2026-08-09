"""Identity injection. The agent sends a name; the proxy attaches the material.

Architectural note the prototype deliberately embodies: the proxy is an
INJECTOR, not an authenticator. Logging in is the runtime's job (it is the thing
that holds 1Password and the KEK), and it hands the proxy a jar. Making the
proxy log in on demand would put credentials on the request path and give the
addon a reason to open sockets outside its own receipt trail.

`http.cookiejar` is used rather than a dict-of-dicts on purpose. Domain
matching, path matching, Secure, and the `__Host-`/`__Secure-` prefixes are the
difference between a cookie jar and a cookie leak, and stdlib already gets them
right.
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}

# No proxy handler: the addon's own fetches must not be routed back through the
# proxy the addon is running inside.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class _Req:
    """Minimal urllib.request.Request lookalike for http.cookiejar."""

    def __init__(self, url: str, host: str):
        self._url = url
        self._host = host
        self.unverifiable = False
        self.origin_req_host = host
        self._headers: dict[str, str] = {}

    def get_full_url(self) -> str:
        return self._url

    def get_host(self) -> str:
        return self._host

    @property
    def host(self) -> str:
        return self._host

    @property
    def type(self) -> str:
        return self._url.split(":", 1)[0]

    def has_header(self, name: str) -> bool:
        return name in self._headers

    def get_header(self, name: str, default=None):
        return self._headers.get(name, default)

    def add_unredirected_header(self, name: str, value: str) -> None:
        self._headers[name] = value

    def header_items(self):
        return list(self._headers.items())


class _Resp:
    """Minimal response lookalike for http.cookiejar."""

    def __init__(self, set_cookie_values: list[str]):
        self._msg = Message()
        for value in set_cookie_values:
            self._msg["Set-Cookie"] = value

    def info(self):
        return self._msg


def _cookie_value(cookie_header: str, name: str) -> str:
    for part in (cookie_header or "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return ""


def _input_value(body: str, name: str) -> str:
    """Pull `value` out of the `<input name="...">` carrying this name.

    Attribute order is not fixed in real HTML, so the tag is located first and
    the value is read out of that tag rather than assuming `name` precedes
    `value`.
    """
    for tag in re.findall(r"<input\b[^>]*>", body, re.IGNORECASE):
        found = re.search(r'\bname\s*=\s*["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if not found or found.group(1) != name:
            continue
        value = re.search(r'\bvalue\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
        if value:
            return value.group(1)
    return ""


class IdentityStore:
    def __init__(self, identities: dict, jar_path: Path):
        self.identities = identities
        self.jar_path = Path(jar_path)
        self.jars: dict[str, http.cookiejar.CookieJar] = {}
        self.csrf: dict[str, dict[str, str]] = {}
        # identity -> host -> the Cookie header that was in force when the token
        # was captured. A CSRF token is bound to a session, so when the session
        # changes the token is dead even though it is still syntactically fine.
        # Storing the binding is what lets the proxy know that, instead of
        # cheerfully injecting a token the server will reject.
        self.bound: dict[str, dict[str, str]] = {}
        self.load()

    # -- persistence -----------------------------------------------------
    def load(self) -> None:
        for name in self.identities:
            jar = http.cookiejar.MozillaCookieJar()
            self.jars[name] = jar
            self.csrf.setdefault(name, {})
            self.bound.setdefault(name, {})
        if not self.jar_path.exists():
            return
        raw = json.loads(self.jar_path.read_text())
        for name, blob in raw.items():
            if name not in self.jars:
                continue
            self.csrf[name] = dict(blob.get("csrf") or {})
            self.bound[name] = dict(blob.get("csrf_bound") or {})
            for c in blob.get("cookies") or []:
                self.jars[name].set_cookie(http.cookiejar.Cookie(
                    version=0, name=c["name"], value=c["value"], port=None,
                    port_specified=False, domain=c["domain"], domain_specified=True,
                    domain_initial_dot=c["domain"].startswith("."), path=c["path"],
                    path_specified=True, secure=c["secure"], expires=None,
                    discard=False, comment=None, comment_url=None, rest={},
                ))

    def save(self) -> None:
        out = {}
        for name, jar in self.jars.items():
            out[name] = {
                "csrf": self.csrf.get(name, {}),
                "csrf_bound": self.bound.get(name, {}),
                "cookies": [
                    {"name": c.name, "value": c.value, "domain": c.domain,
                     "path": c.path, "secure": bool(c.secure)}
                    for c in jar
                ],
            }
        self.jar_path.write_text(json.dumps(out, indent=2))

    # -- session binding -------------------------------------------------
    def cookie_header(self, identity: str, url: str, host: str) -> str:
        req = _Req(url, host)
        self.jars[identity].add_cookie_header(req)
        return req.get_header("Cookie") or ""

    def token_for(self, identity: str, host: str, cookie: str) -> str:
        """The stored token, but only if it still belongs to this session."""
        if self.bound.get(identity, {}).get(host, "") != cookie:
            return ""
        return self.csrf.get(identity, {}).get(host, "")

    def needs_csrf(self, identity: str, url: str, host: str, method: str,
                   target: dict | None, csrf_raw: bool) -> bool:
        """True when this request needs a token the proxy does not have."""
        conf = ((target or {}).get("csrf") or {})
        send, extract = conf.get("send"), conf.get("extract")
        if csrf_raw or not send or not extract or not extract.get("source"):
            return False
        if method.upper() not in STATE_CHANGING or identity not in self.jars:
            return False
        return not self.token_for(identity, host,
                                  self.cookie_header(identity, url, host))

    def refresh_csrf(self, identity: str, base: str, host: str,
                     target: dict) -> dict:
        """Fetch a token page with this identity's jar and bind what comes back.

        Blocking on purpose -- it is called via `asyncio.to_thread` so the
        mitmproxy event loop keeps serving other flows. The interesting part is
        not the fetch, it is that the fetch is EGRESS: the addon is now a client
        of the target in its own right, so the caller runs it through the same
        scope decision, the same target budget, and the same receipt trail as a
        request the agent made. A proxy that quietly makes its own unmetered
        requests has broken the one-egress-path constraint it exists to enforce.
        """
        extract = target["csrf"]["extract"]
        url = base.rstrip("/") + "/" + str(extract["source"]).lstrip("/")
        req = urllib.request.Request(url, method="GET")
        cookie = self.cookie_header(identity, url, host)
        if cookie:
            req.add_header("Cookie", cookie)
        conf = self.identities.get(identity) or {}
        for name, value in (conf.get("static_headers") or {}).items():
            req.add_header(name, value)
        try:
            with _OPENER.open(req, timeout=10) as resp:
                status, body = resp.status, resp.read()
                values = resp.headers.get_all("set-cookie") or []
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read()
            values = exc.headers.get_all("set-cookie") or []
        except Exception as exc:  # noqa: BLE001
            return {"url": url, "error": f"{type(exc).__name__}: {exc}",
                    "body": b"", "status": 0, "token": False}

        if values:
            self.jars[identity].extract_cookies(_Resp(list(values)), _Req(url, host))
        token = _input_value(body.decode("utf-8", "replace"), extract["name"])
        if token:
            self._store_token(identity, url, host, token)
        return {"url": url, "status": status, "token": bool(token), "body": body}

    def _store_token(self, identity: str, url: str, host: str, token: str) -> None:
        self.csrf.setdefault(identity, {})[host] = token
        # Bind AFTER any Set-Cookie from the same response has landed, so the
        # binding describes the session the token was actually issued for.
        self.bound.setdefault(identity, {})[host] = self.cookie_header(
            identity, url, host)

    # -- the two operations that matter ----------------------------------
    def inject(self, identity: str, url: str, host: str, method: str,
               headers, get_body, set_body, target: dict | None,
               csrf_raw: bool) -> dict:
        """Attach this identity's material. Returns notes for the receipt."""
        notes: dict = {"identity": identity, "cookies_attached": [],
                       "agent_sent_cookie": False, "csrf": "none"}

        # An agent that sets its own Cookie header is either confused or trying
        # to smuggle one. Either way it never reaches the wire, and the attempt
        # is evidence rather than a silent strip.
        if "cookie" in headers:
            notes["agent_sent_cookie"] = True
            del headers["cookie"]

        conf = self.identities.get(identity)
        if conf is None:
            notes["error"] = f"unknown identity {identity!r}"
            return notes

        for name, value in (conf.get("static_headers") or {}).items():
            headers[name] = value

        cookie = self.cookie_header(identity, url, host)
        if cookie:
            headers["cookie"] = cookie
            notes["cookies_attached"] = [
                part.split("=", 1)[0].strip() for part in cookie.split(";")
            ]

        double = ((target or {}).get("csrf") or {}).get("double_submit")
        if double and method.upper() in STATE_CHANGING:
            if csrf_raw:
                notes["double_submit"] = "raw (agent opted out)"
            else:
                value = _cookie_value(cookie, double["cookie"])
                if value:
                    headers[double["header"]] = value
                    notes["double_submit"] = (
                        f"{double['header']} set from jar cookie {double['cookie']}")
                else:
                    notes["double_submit"] = f"{double['cookie']} not in jar"

        send = ((target or {}).get("csrf") or {}).get("send")
        token = self.token_for(identity, host, cookie)
        if send and method.upper() in STATE_CHANGING and not token:
            notes["csrf"] = "no token bound to this session"
        if send and token and method.upper() in STATE_CHANGING:
            if csrf_raw:
                # Deliberate CSRF testing: leave whatever the agent wrote alone,
                # but say so, because a silent rewrite would make every CSRF
                # finding untrustworthy.
                notes["csrf"] = "raw (agent opted out)"
            elif send.get("kind") == "form_field":
                body = get_body().decode("utf-8", "replace")
                fields = parse_qsl(body, keep_blank_values=True)
                if any(k == send["name"] for k, _ in fields):
                    fields = [(k, token if k == send["name"] else v) for k, v in fields]
                    set_body(urlencode(fields).encode())
                    notes["csrf"] = f"injected into form field {send['name']}"
                else:
                    notes["csrf"] = f"field {send['name']} absent, nothing injected"
        return notes

    def capture(self, identity: str, url: str, host: str, headers,
                body: bytes, target: dict | None, strip: bool = True) -> dict:
        """Take Set-Cookie and CSRF into the jar, then strip Set-Cookie.

        `strip` is False only on the provisioning lane, where the client is the
        runtime rather than an agent and needs to see that its login worked.
        """
        notes: dict = {"cookies_stored": [], "csrf_captured": ""}
        if identity not in self.jars:
            return notes

        values = headers.get_all("set-cookie") if hasattr(headers, "get_all") else []
        values = list(values or [])
        if values:
            self.jars[identity].extract_cookies(_Resp(values), _Req(url, host))
            notes["cookies_stored"] = [v.split("=", 1)[0].strip() for v in values]
            if strip:
                # The agent must not see credential material in either direction.
                del headers["set-cookie"]

        extract = ((target or {}).get("csrf") or {}).get("extract")
        if extract and extract.get("kind") == "html_input" and body:
            token = _input_value(body.decode("utf-8", "replace"), extract["name"])
            if token:
                self._store_token(identity, url, host, token)
                notes["csrf_captured"] = extract["name"]
        return notes
