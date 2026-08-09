"""Scope enforcement that sits BELOW the agent.

Three things v1 did not do, and each is a real hole rather than a nicety:

1. v1 matched hostnames only. An in-scope name that resolves to 127.0.0.1 or
   169.254.169.254 passed. Here every resolved address is checked.
2. v1 never pinned the address it validated, so the name could be re-resolved
   between the check and the connect (DNS rebinding). `resolve_and_validate`
   returns the addresses it approved and the addon pins them.
3. v1 accepted any pattern string. `yekta-it.de*` would have matched
   `yekta-it.de.evil.com`. Patterns are parsed strictly and a malformed one is
   a hard failure, never a silent widening.
"""

from __future__ import annotations

import fnmatch
import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urlsplit


class PolicyError(Exception):
    """Malformed policy. Always fails closed at the call site."""


@dataclass
class Decision:
    allowed: bool
    reason: str
    host: str
    port: int
    path: str
    target_id: str = ""
    # Addresses validated for THIS decision. The addon pins the connection to
    # them so a second resolution cannot land somewhere else.
    pinned: list[str] = field(default_factory=list)


def normalize_pattern(pattern: str) -> str:
    """Accept a bare host, an IP literal, or a single leading `*.` wildcard.

    Anything else raises. A trailing wildcard (`example.com*`) is the dangerous
    case: it matches `example.com.evil.test`, so it is rejected rather than
    normalised into something that looks safe.
    """
    if not isinstance(pattern, str) or not pattern.strip():
        raise PolicyError(f"empty host pattern: {pattern!r}")
    value = pattern.strip().lower().rstrip(".")
    body = value[2:] if value.startswith("*.") else value
    if "*" in body:
        raise PolicyError(
            f"host pattern {pattern!r}: `*` is only allowed as a leading `*.` label"
        )
    if not body:
        raise PolicyError(f"host pattern {pattern!r} has no host part")
    try:
        return ipaddress.ip_address(body).compressed
    except ValueError:
        pass
    if any(c in body for c in "/:@ "):
        raise PolicyError(f"host pattern {pattern!r} is not a hostname")
    return value


def host_matches(host: str, pattern: str) -> bool:
    value = normalize_pattern(pattern)
    host = (host or "").strip().lower().rstrip(".")
    if value.startswith("*."):
        # fnmatch's `*` spans dots, which is what a subdomain wildcard wants.
        # The literal dot in the pattern is what stops `evilexample.com`.
        return fnmatch.fnmatchcase(host, value)
    return host == value


def public_enough(addr: str) -> tuple[bool, str]:
    ip = ipaddress.ip_address(addr)
    for flag in ("is_loopback", "is_private", "is_link_local", "is_reserved",
                 "is_multicast", "is_unspecified"):
        if getattr(ip, flag, False):
            return False, flag
    return True, ""


def resolve(host: str, port: int) -> list[str]:
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise PolicyError(f"cannot resolve {host}: {exc}") from exc
    seen: list[str] = []
    for info in infos:
        addr = info[4][0]
        if addr not in seen:
            seen.append(addr)
    if not seen:
        raise PolicyError(f"{host} resolved to nothing")
    return seen


def decide(url: str, targets: list[dict]) -> Decision:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    port = parts.port or (443 if parts.scheme == "https" else 80)
    path = parts.path or "/"
    base = Decision(False, "", host, port, path)

    if not host:
        base.reason = "no host in request"
        return base

    # Parse EVERY pattern before deciding anything. A malformed deny entry must
    # not be skipped past into an allow.
    try:
        for target in targets:
            for pattern in list(target.get("deny") or []) + list(target.get("hosts") or []):
                normalize_pattern(pattern)
    except PolicyError as exc:
        base.reason = f"policy malformed, failing closed: {exc}"
        return base

    for target in targets:
        for pattern in target.get("deny") or []:
            if host_matches(host, pattern):
                base.target_id = target["id"]
                base.reason = f"explicit deny: {pattern}"
                return base

    match = None
    for target in targets:
        for pattern in target.get("hosts") or []:
            if host_matches(host, pattern):
                match = target
                break
        if match:
            break

    if match is None:
        base.reason = "host not in any target"
        return base

    base.target_id = match["id"]

    for excluded in match.get("excluded_paths") or []:
        if fnmatch.fnmatchcase(path, excluded):
            base.reason = f"excluded path: {excluded}"
            return base

    try:
        addrs = resolve(host, port)
    except PolicyError as exc:
        base.reason = str(exc)
        return base

    if not match.get("allow_private_ips"):
        for addr in addrs:
            ok, why = public_enough(addr)
            if not ok:
                base.reason = (
                    f"{host} resolved to {addr} ({why}); possible DNS rebinding"
                )
                return base

    base.allowed = True
    base.pinned = addrs
    base.reason = f"matched target {match['id']}"
    return base
