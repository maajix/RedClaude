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
    "identity",
    "program",
    "required_header",
    "rules_of_engagement",
    "schema_version",
    "scope",
)
PROGRAM_KEYS = ("name", "platform")

#: The Rules of Engagement, as typed controls. An absent control is a denial.
RULES_OF_ENGAGEMENT = (
    "availability_impact",
    "credential_use",
    "mutation",
    "pivoting",
    "sensitive_data_access",
)
BUDGET_LIMITS = ("concurrency", "requests", "tokens", "window_seconds")
SCOPE_KEYS = ("exclude", "include")
RULE_KEYS = ("host", "paths", "ports", "protocols")
IDENTITY_KEYS = ("name", "slot_ref")
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
_LABEL = r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
_HOSTNAME = re.compile(rf"{_LABEL}(\.{_LABEL})*")

#: A wildcard must name at least two labels of its own, so an inclusion cannot
#: reach a whole public suffix by writing `*.com`.
_WILDCARD = re.compile(rf"\*\.{_LABEL}(\.{_LABEL})+")
_HOST_SHAPE = "must be a hostname, a wildcard such as *.example.com, or an address"

_HEADER_NAME = re.compile(r"[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}")

#: A reference names a runtime-owned slot and nothing else. Any other scheme
#: would let a configuration carry its own credential material — a URL with
#: userinfo, for one — which is the leak the reference exists to prevent.
_REFERENCE = re.compile(r"slot://[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)+")
_REFERENCE_SHAPE = "a runtime-owned reference such as slot://identity/name"


@dataclass(frozen=True)
class Configuration:
    """A validated Program configuration and the hashes that identify it."""

    path: str
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
            "path": self.path,
            "schema_version": self.schema_version,
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "program_name": self.document["program"]["name"],
            "program_platform": self.document["program"]["platform"],
            "rules_of_engagement": dict(self.document["rules_of_engagement"]),
            "budgets": dict(self.document["budgets"]),
            "scope": {"include": len(scope["include"]), "exclude": len(scope["exclude"])},
            "identities": [entry["name"] for entry in self.document["identity"]],
            "required_headers": [entry["name"] for entry in self.document["required_header"]],
            "callbacks": [entry["name"] for entry in self.document["callback"]],
        }


def load(path: Path) -> tuple[Configuration | None, tuple[Violation, ...]]:
    """Read, validate and hash the configuration at `path`."""
    file = Path(path)
    try:
        data = file.read_bytes()
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
            path=str(file.resolve()),
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
        "rules_of_engagement": _rules_of_engagement(reader, root),
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
        if _HOSTNAME.fullmatch(value) or _WILDCARD.fullmatch(value):
            return value
        try:
            ipaddress.ip_address(value)
        except ValueError:
            self.fail(source, _HOST_SHAPE)
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


def _rules_of_engagement(reader: _Reader, root: dict) -> dict:
    """Typed controls only; an absent control is a denial rather than a default."""
    controls = dict.fromkeys(RULES_OF_ENGAGEMENT, False)
    source = "rules_of_engagement"
    table = reader.table(root.get(source, {}), source, RULES_OF_ENGAGEMENT)
    if table is None:
        return controls
    for control in RULES_OF_ENGAGEMENT:
        if control in table:
            controls[control] = bool(reader.boolean(table[control], f"{source}.{control}"))
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
        "paths": _members(reader, table, source, "paths", _is_path, "must begin with a forward slash"),
        "ports": _members(reader, table, source, "ports", _is_port, "must be between 1 and 65535"),
        "protocols": _members(
            reader, table, source, "protocols", _is_protocol, "must be one of: " + ", ".join(PROTOCOLS)
        ),
    }


def _members(reader: _Reader, table: dict, source: str, key: str, accept, shape: str) -> list:
    """The accepted members of one required array, deduplicated and ordered."""
    raw = reader.required(table, source, key)
    if raw is None:
        return []
    accepted = []
    for index, member in enumerate(reader.array(raw, f"{source}.{key}") or []):
        if accept(member):
            accepted.append(member)
        else:
            reader.fail(f"{source}.{key}[{index}]", shape)
    return sorted(set(accepted))


def _is_port(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and 1 <= value <= 65535


def _is_protocol(value: object) -> bool:
    return value in PROTOCOLS


def _is_path(value: object) -> bool:
    return isinstance(value, str) and value.startswith("/")


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
    if "slot_ref" in table:
        reference = reader.text(
            table["slot_ref"], f"{source}.slot_ref", _REFERENCE, _REFERENCE_SHAPE
        )
    return {"name": name, "slot_ref": reference}


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
