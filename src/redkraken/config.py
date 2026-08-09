"""The versioned, declarative Program configuration.

One operation matters to callers: `load`, which reads a configuration file and
returns either a hashed `Configuration` or every violation that refused it. The
schema is closed, so an unrecognised key is a refusal rather than an ignored
line, and secret material is declared as a reference the runtime resolves
elsewhere. A configuration never carries a secret value.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from redkraken.outcome import INVALID_CONFIGURATION, UNSUPPORTED_VERSION, Violation


SUPPORTED_SCHEMA_VERSIONS = (1,)

TOP_LEVEL = (
    "budgets",
    "callback",
    "engagement",
    "identity",
    "program",
    "required_header",
    "schema_version",
    "scope",
)
PROGRAM_KEYS = ("name", "platform")
ENGAGEMENT_CONTROLS = (
    "availability_impact",
    "credential_use",
    "mutation",
    "pivoting",
    "sensitive_data_access",
)
BUDGET_LIMITS = ("concurrency", "requests", "tokens", "window_seconds")
SCOPE_KEYS = ("exclude", "include")
RULE_KEYS = ("host", "paths", "ports", "protocols")
IDENTITY_KEYS = ("credential_ref", "name")
HEADER_KEYS = ("name", "value_ref")
CALLBACK_KEYS = ("host", "kind", "name")
PROTOCOLS = ("http", "https")
CALLBACK_KINDS = ("dns", "http")

#: Key names that would carry a secret inline. Naming them separately turns a
#: leaked credential into a precise refusal rather than an unknown key.
SECRET_KEYS = (
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
    "value",
)

_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
_HOSTNAME = re.compile(
    r"(\*\.)?[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*"
)
_HEADER_NAME = re.compile(r"[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}")
_REFERENCE = re.compile(r"[a-z][a-z0-9+.-]*://[A-Za-z0-9._~/%:@-]{1,480}")
_REFERENCE_SHAPE = "a secret reference such as slot://identity/name"


@dataclass(frozen=True)
class Configuration:
    """A validated Program configuration and the hashes that identify it."""

    source: str
    schema_version: int
    document: dict
    source_sha256: str
    canonical_sha256: str

    def summary(self) -> dict:
        """The diagnostic projection: names, counts, controls and hashes only.

        Built by positive selection so a later schema addition cannot leak a
        reference or a value into operator-visible output by default.
        """
        scope = self.document["scope"]
        return {
            "source": self.source,
            "schema_version": self.schema_version,
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "program_name": self.document["program"]["name"],
            "program_platform": self.document["program"]["platform"],
            "engagement": dict(self.document["engagement"]),
            "budgets": dict(self.document["budgets"]),
            "scope": {"include": len(scope["include"]), "exclude": len(scope["exclude"])},
            "identities": [entry["name"] for entry in self.document["identity"]],
            "required_headers": [entry["name"] for entry in self.document["required_header"]],
            "callbacks": [entry["name"] for entry in self.document["callback"]],
        }


def load(path: Path) -> tuple[Configuration | None, tuple[Violation, ...]]:
    """Read, validate and hash the configuration at `path`."""
    source = Path(path)
    try:
        data = source.read_bytes()
    except OSError as error:
        return None, (_refusal(f"cannot read configuration: {error.strerror}"),)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, (_refusal("cannot read configuration: not UTF-8 text"),)
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        line = getattr(error, "lineno", None)
        where = f" at line {line}" if isinstance(line, int) else ""
        return None, (_refusal(f"cannot parse configuration{where}"),)

    normalized, violations = validate(document)
    if normalized is None:
        return None, violations
    return (
        Configuration(
            source=str(source.resolve()),
            schema_version=normalized["schema_version"],
            document=normalized,
            source_sha256=hashlib.sha256(data).hexdigest(),
            canonical_sha256=hashlib.sha256(canonical_bytes(normalized)).hexdigest(),
        ),
        (),
    )


def validate(document: object) -> tuple[dict | None, tuple[Violation, ...]]:
    """Check one parsed document, returning its normalised form or violations."""
    reader = _Reader()
    root = reader.table(document, "", TOP_LEVEL)
    if root is None:
        return None, tuple(sorted(reader.violations))

    normalized = {
        "schema_version": _schema_version(reader, root),
        "program": _program(reader, root),
        "engagement": _engagement(reader, root),
        "budgets": _budgets(reader, root),
        "scope": _scope(reader, root),
        "identity": _entries(reader, root, "identity", IDENTITY_KEYS, _identity),
        "required_header": _entries(reader, root, "required_header", HEADER_KEYS, _header),
        "callback": _entries(reader, root, "callback", CALLBACK_KEYS, _callback),
    }
    if reader.violations:
        return None, tuple(sorted(reader.violations))
    return normalized, ()


def canonical_bytes(document: dict) -> bytes:
    """The formatting-independent encoding a configuration hash is taken over."""
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _refusal(detail: str) -> Violation:
    return Violation(code=INVALID_CONFIGURATION, source="config", detail=detail)


def _join(source: str, key: str) -> str:
    return f"{source}.{key}" if source else key


class _Reader:
    """Collects every violation instead of stopping at the first one."""

    def __init__(self) -> None:
        self.violations: list[Violation] = []

    def fail(self, source: str, detail: str, code: str = INVALID_CONFIGURATION) -> None:
        self.violations.append(
            Violation(code=code, source=f"config:{source}" if source else "config", detail=detail)
        )

    def table(self, value: object, source: str, allowed: tuple[str, ...]) -> dict | None:
        if not isinstance(value, dict):
            self.fail(source, "must be a table")
            return None
        for key in sorted(value):
            if key in allowed:
                continue
            if key in SECRET_KEYS:
                self.fail(
                    _join(source, key),
                    "inline secret values are not accepted; declare a reference instead",
                )
            else:
                self.fail(_join(source, key), "unknown key")
        return value

    def required(self, table: dict, source: str, key: str) -> object | None:
        if key not in table:
            self.fail(_join(source, key), "required key is absent")
            return None
        return table[key]

    def array(self, value: object, source: str, minimum: int = 1) -> list | None:
        if not isinstance(value, list):
            self.fail(source, "must be an array")
            return None
        if len(value) < minimum:
            self.fail(source, "must list at least one entry")
            return None
        return value

    def text(self, value: object, source: str, pattern: re.Pattern[str], shape: str) -> str | None:
        if not isinstance(value, str):
            self.fail(source, "must be text")
            return None
        if not pattern.fullmatch(value):
            self.fail(source, f"must match {shape}")
            return None
        return value

    def boolean(self, value: object, source: str) -> bool | None:
        if not isinstance(value, bool):
            self.fail(source, "must be true or false")
            return None
        return value

    def positive_integer(self, value: object, source: str) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            self.fail(source, "must be a positive integer")
            return None
        return value

    def host(self, value: object, source: str) -> str | None:
        if not isinstance(value, str):
            self.fail(source, "must be text")
            return None
        if _HOSTNAME.fullmatch(value):
            return value
        try:
            ipaddress.ip_address(value)
        except ValueError:
            self.fail(source, "must be a hostname or an address")
            return None
        return value


def _schema_version(reader: _Reader, root: dict) -> int | None:
    value = reader.required(root, "", "schema_version")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        reader.fail("schema_version", "must be an integer")
        return None
    if value not in SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(str(version) for version in SUPPORTED_SCHEMA_VERSIONS)
        reader.fail(
            "schema_version",
            f"unsupported schema version {value}; supported: {supported}",
            code=UNSUPPORTED_VERSION,
        )
        return None
    return value


def _program(reader: _Reader, root: dict) -> dict | None:
    value = reader.required(root, "", "program")
    if value is None:
        return None
    table = reader.table(value, "program", PROGRAM_KEYS)
    if table is None:
        return None
    name = None
    raw = reader.required(table, "program", "name")
    if raw is not None:
        name = reader.text(raw, "program.name", _SLUG, _SLUG.pattern)
    platform = None
    if "platform" in table:
        platform = reader.text(table["platform"], "program.platform", _SLUG, _SLUG.pattern)
    return {"name": name, "platform": platform}


def _engagement(reader: _Reader, root: dict) -> dict:
    """Rules of Engagement are typed controls; an absent control is a denial."""
    controls = dict.fromkeys(ENGAGEMENT_CONTROLS, False)
    table = reader.table(root.get("engagement", {}), "engagement", ENGAGEMENT_CONTROLS)
    if table is None:
        return controls
    for control in ENGAGEMENT_CONTROLS:
        if control in table:
            controls[control] = bool(reader.boolean(table[control], f"engagement.{control}"))
    return controls


def _budgets(reader: _Reader, root: dict) -> dict | None:
    value = reader.required(root, "", "budgets")
    if value is None:
        return None
    table = reader.table(value, "budgets", BUDGET_LIMITS)
    if table is None:
        return None
    limits: dict[str, int | None] = {}
    for limit in BUDGET_LIMITS:
        raw = reader.required(table, "budgets", limit)
        limits[limit] = None if raw is None else reader.positive_integer(raw, f"budgets.{limit}")
    return limits


def _scope(reader: _Reader, root: dict) -> dict | None:
    table = reader.table(root.get("scope", {}), "scope", SCOPE_KEYS)
    if table is None:
        return None
    return {
        "include": _rules(reader, table, "include", required=True),
        "exclude": _rules(reader, table, "exclude", required=False),
    }


def _rules(reader: _Reader, scope: dict, key: str, required: bool) -> list[dict]:
    source = f"scope.{key}"
    if key not in scope:
        if required:
            reader.fail(source, "required key is absent")
        return []
    entries = reader.array(scope[key], source, minimum=1 if required else 0)
    if entries is None:
        return []
    rules = [_rule(reader, entry, f"{source}[{index}]") for index, entry in enumerate(entries)]
    return sorted((rule for rule in rules if rule is not None), key=canonical_bytes)


def _rule(reader: _Reader, entry: object, source: str) -> dict | None:
    table = reader.table(entry, source, RULE_KEYS)
    if table is None:
        return None
    host = None
    raw = reader.required(table, source, "host")
    if raw is not None:
        host = reader.host(raw, f"{source}.host")
    return {
        "host": host,
        "paths": _paths(reader, table, source),
        "ports": _ports(reader, table, source),
        "protocols": _protocols(reader, table, source),
    }


def _ports(reader: _Reader, table: dict, source: str) -> list[int]:
    entries = _members(reader, table, source, "ports")
    ports = []
    for index, port in enumerate(entries):
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            reader.fail(f"{source}.ports[{index}]", "must be between 1 and 65535")
            continue
        ports.append(port)
    return sorted(set(ports))


def _protocols(reader: _Reader, table: dict, source: str) -> list[str]:
    entries = _members(reader, table, source, "protocols")
    protocols = []
    for index, protocol in enumerate(entries):
        if protocol not in PROTOCOLS:
            reader.fail(
                f"{source}.protocols[{index}]", "must be one of: " + ", ".join(PROTOCOLS)
            )
            continue
        protocols.append(protocol)
    return sorted(set(protocols))


def _paths(reader: _Reader, table: dict, source: str) -> list[str]:
    entries = _members(reader, table, source, "paths")
    paths = []
    for index, path in enumerate(entries):
        if not isinstance(path, str) or not path.startswith("/"):
            reader.fail(f"{source}.paths[{index}]", "must begin with a forward slash")
            continue
        paths.append(path)
    return sorted(set(paths))


def _members(reader: _Reader, table: dict, source: str, key: str) -> list:
    raw = reader.required(table, source, key)
    if raw is None:
        return []
    return reader.array(raw, f"{source}.{key}") or []


def _entries(reader: _Reader, root: dict, key: str, keys: tuple[str, ...], build) -> list[dict]:
    if key not in root:
        return []
    entries = reader.array(root[key], key, minimum=0)
    if entries is None:
        return []
    built: list[dict] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        source = f"{key}[{index}]"
        table = reader.table(entry, source, keys)
        if table is None:
            continue
        item = build(reader, table, source)
        if item is None:
            continue
        name = item["name"].lower()
        if name in seen:
            reader.fail(f"{source}.name", f"duplicate name: {name}")
            continue
        seen.add(name)
        built.append(item)
    return sorted(built, key=canonical_bytes)


def _identity(reader: _Reader, table: dict, source: str) -> dict | None:
    name = _name(reader, table, source, _SLUG, _SLUG.pattern)
    if name is None:
        return None
    reference = None
    if "credential_ref" in table:
        reference = reader.text(
            table["credential_ref"], f"{source}.credential_ref", _REFERENCE, _REFERENCE_SHAPE
        )
    return {"credential_ref": reference, "name": name}


def _header(reader: _Reader, table: dict, source: str) -> dict | None:
    name = _name(reader, table, source, _HEADER_NAME, "an HTTP field name")
    reference = None
    raw = reader.required(table, source, "value_ref")
    if raw is not None:
        reference = reader.text(raw, f"{source}.value_ref", _REFERENCE, _REFERENCE_SHAPE)
    if name is None or reference is None:
        return None
    return {"name": name, "value_ref": reference}


def _callback(reader: _Reader, table: dict, source: str) -> dict | None:
    name = _name(reader, table, source, _SLUG, _SLUG.pattern)
    kind = None
    raw = reader.required(table, source, "kind")
    if raw is not None and raw not in CALLBACK_KINDS:
        reader.fail(f"{source}.kind", "must be one of: " + ", ".join(CALLBACK_KINDS))
    elif raw is not None:
        kind = raw
    host = None
    raw = reader.required(table, source, "host")
    if raw is not None:
        host = reader.host(raw, f"{source}.host")
    if name is None or kind is None or host is None:
        return None
    return {"host": host, "kind": kind, "name": name}


def _name(reader: _Reader, table: dict, source: str, pattern: re.Pattern[str], shape: str) -> str | None:
    raw = reader.required(table, source, "name")
    if raw is None:
        return None
    return reader.text(raw, f"{source}.name", pattern, shape)
