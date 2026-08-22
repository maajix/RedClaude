"""One compiled Scope Policy, and the decision every target-facing operation asks.

A Program configuration says what may be touched in five different vocabularies:
hosts and wildcards under `scope`, ports and protocols and path prefixes inside
each rule, out-of-band channels under `callback`, typed permissions under
`rules_of_engagement`, and a time window under `budgets`. Compiling them into
one policy is what stops those five from being answered five different ways by
the proxy, the browser driver, the callback listener and the report renderer.

Four properties make the compiled answer worth citing, and each is a refusal
rather than a convention:

* Deny by default. A request matches no rule and is denied; a permission is
  absent and is withheld. There is no code path in this module that turns
  silence into authority, which is why `decide` returns a verdict for every
  input including the ones it could not parse.
* Precedence is by effect, never by document order. The verdict is the lowest
  effect rank over *every* matching rule, so an exclusion cannot be outvoted by
  writing it above an inclusion, or below one. Specificity picks only which rule
  is cited in the answer.
* Everything is canonicalised before it is matched. Two spellings of one host,
  one address or one path must not be able to get two verdicts, so `%2e%2e`,
  `::ffff:93.184.216.34`, a trailing dot and an uppercase label are all resolved
  first, and a spelling that cannot be resolved unambiguously is refused.
* Discovery is not in the grammar. Adjacent-host expansion, DNS enumeration,
  certificate-transparency search, reverse-IP lookup and virtual-host probing
  are excluded by the spec, so no configuration key enables them and
  `decide_discovery` denies all five whatever policy it is handed. A wildcard
  inclusion authorises *requests* to hosts beneath it; it never authorises the
  enumeration that would find them.

What this module deliberately does not do is resolve DNS. `decide` is the static
layer: it answers from the policy and the request alone, which is what makes it
the same function in Python and in SQL. The peer-address layer — resolve, then
refuse a name that points somewhere the policy did not authorise — can only ever
narrow this answer, and it belongs to the proxy, which is the only component
that holds a socket.

The SQL half of the same grammar is `scope_class_of` in the corpus. It is not a
second interpretation: this module compiles the patterns into rows and SQL does
set membership and precedence over them, so nothing in the database parses a
host. The fixture matrix in the tests decides the same requests through both.
"""

from __future__ import annotations

import hashlib
import ipaddress
import posixpath
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from redkraken import config
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, Violation, ordered, report


#: What the operator diagnostic is filed under, so a refusal from it is
#: attributable to the same command an operator typed.
COMMAND = "scope"

#: The compiled grammar's own version, recorded in every policy document. A
#: change to how a pattern matches is a change here, so a stored policy always
#: says which rules produced it. 2 is the address range: a third pattern kind,
#: matched by containment rather than by key, and a `net` column on every rule
#: row. Every policy compiled by 1 hashes differently under 2 even when the
#: operator's file has not moved, which is the case
#: `program_scope_versions.configuration_revision` exists to keep separable --
#: the compiler changing while the file does not is a change in what the policy
#: means and therefore a new version.
GRAMMAR_VERSION = 2

#: What a rule does when it matches, and the order in which those answers win.
#: Withdrawal beats support beats authorisation, over every match at once: this
#: is the whole of precedence, and there is nothing else that decides a verdict.
EXCLUDE = "exclude"
EGRESS_SUPPORT = "egress_support"
TARGET = "target"
EFFECT_RANK = {EXCLUDE: 0, EGRESS_SUPPORT: 1, TARGET: 2}

#: What a caller may do with a verdict. `denied` is every refusal, whatever
#: produced it, so no caller has to enumerate the failures to find the allows.
DENIED = "denied"
NOT_ADDRESSABLE = "not_addressable"

#: How specific a pattern is, which decides only which rule is *cited*. The
#: numbers match `program_scope_rules.spec_kind`, and the ordering SQL applies
#: is `spec_kind DESC, spec_len DESC, ord ASC`.
SPEC_CIDR = 0
SPEC_WILDCARD = 1
SPEC_EXACT = 2

#: The protocols a rule may name, taken from the configuration schema rather
#: than restated, so adding one there cannot leave this module behind.
PROTOCOLS = config.PROTOCOLS
DEFAULT_PORTS = {"http": 80, "https": 443}

#: What an HTTP callback channel is reachable on. A callback has no ports or
#: protocols of its own in the schema: it is an endpoint the harness operates,
#: not a target surface an operator negotiates, so the compiler states the two
#: web ports and nothing wider.
CALLBACK_PORTS = (80, 443)

#: The two entity selector kinds the projection can decide. Mirrors
#: `entities.scope_selector_kind`; an entity with neither is not a scope
#: question at all, which `NOT_ADDRESSABLE` says.
SELECTOR_HOST = "host"
SELECTOR_WILDCARD = "wildcard_domain"
SELECTORS = (SELECTOR_HOST, SELECTOR_WILDCARD)

#: What is being asked, which is not always "may this exact request be made".
#: A request is decided strictly. A host entity asks whether it is reachable at
#: all, and a wildcard entity asks the same of a whole subtree; both are
#: coverage questions, and answering them strictly would deny every seed a
#: path-qualified inclusion produces. The names are the argument
#: `scope_class_of` takes, so the two evaluators dispatch on one word.
QUESTION_REQUEST = "request"
QUESTION_COVERAGE = "coverage"
QUESTION_SUBTREE = "subtree"
QUESTIONS = (QUESTION_REQUEST, QUESTION_COVERAGE, QUESTION_SUBTREE)

#: The five techniques the spec puts out of scope. They are named so that a
#: caller asking for one gets a denial it can log, rather than an unknown-verb
#: error that some future caller would be tempted to treat as "not applicable".
DISCOVERY_TECHNIQUES = (
    "adjacent_host",
    "certificate_transparency",
    "dns_enumeration",
    "reverse_ip",
    "virtual_host",
)

#: Every reason a decision can give, as a closed vocabulary. Closed because
#: these strings end up in receipts and in the event log, and a reason invented
#: at a call site is a reason no query can count.
REASONS = (
    "excluded",
    "malformed_host",
    "malformed_path",
    "malformed_port",
    "malformed_url",
    "matched_callback",
    "matched_egress_support",
    "matched_target",
    "no_host",
    "not_addressable",
    "unlisted",
    "unsupported_protocol",
)

#: Mirrors `scope_normalize_host`. The shapes an address may be written in are
#: matched before anything is parsed, so Python and SQL agree on which strings
#: are even considered addresses -- the disagreement that would otherwise let
#: `1.2.3` be a name on one side and the address `1.2.0.3` on the other.
#: The colon is required, or every hostname spelled out of the hex alphabet --
#: `db`, `cafe`, `ec2` -- would be read as an address, fail to parse, and be
#: refused as malformed rather than matched as the name it is.
_IPV4 = re.compile(r"[0-9]{1,3}(\.[0-9]{1,3}){3}")
_IPV6 = re.compile(r"[0-9a-f]*:[0-9a-f:]*")
_MAPPED = re.compile(r"::ffff:[0-9]{1,3}(\.[0-9]{1,3}){3}")

#: The deprecated IPv4-compatible range, `::a.b.c.b`. Refused rather than
#: canonicalised, because Python and PostgreSQL render it differently --
#: `::102:304` here and `::1.2.3.4` there -- and a match key that depends on
#: which side normalised it is a rule that covers a host in one world only.
_V4_COMPATIBLE = ipaddress.ip_network("::/96")

#: One DNS label as the matcher accepts it. Wider than the configuration's own
#: pattern on purpose: this reads hosts off the wire, where an underscore label
#: is common, and a host the matcher refuses to normalise is a host no rule can
#: cover -- which would be a denial arrived at by accident rather than by rule.
_LABEL = re.compile(r"[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?")

_MAXIMUM_HOST = 253

#: How many times a path may be percent-encoded before it is refused.
_DECODE_PASSES = 4


class PolicyError(Exception):
    """An input that cannot be canonicalised, and the reason it is refused.

    Carries a reason from `REASONS` as well as a message, so a caller that turns
    it into a verdict does not have to classify the message text.
    """

    def __init__(self, reason: str, detail: str, key: str = "") -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        #: The one key of the entry that is wrong, when there is one. A caller
        #: turning this into a refusal can point the operator at the line they
        #: have to edit instead of at the table it sits in.
        self.key = key


# ---------------------------------------------------------------------------
# Canonical forms
# ---------------------------------------------------------------------------


def canonical_address(value: str) -> str:
    """One address in one spelling, with the IPv4-mapped form collapsed.

    `::ffff:93.184.216.34` and `93.184.216.34` are one machine. Left apart, a
    rule written for either would silently miss the other, because containment
    across address families answers false rather than raising.
    """
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise PolicyError("malformed_host", f"{value} is not an address") from error
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is None and address.version == 6 and address in _V4_COMPATIBLE:
        # `::` and `::1` are in the same /96 and are not this: they are the
        # unspecified and loopback addresses, refused a step later for being
        # unroutable rather than here for being ambiguously spelled.
        if not (address.is_unspecified or address.is_loopback):
            raise PolicyError(
                "malformed_host",
                f"{value} is in the deprecated IPv4-compatible range; write the address itself",
            )
    return (mapped or address).compressed


def parse_network(value: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    """One address range, in the strict spelling `config` already accepted.

    Strict, so `10.0.0.5/8` raises rather than widening to `10.0.0.0/8`: the
    loader refuses that spelling with the canonical form in the message, and a
    compiler that read it the other way would compile a policy the file does
    not state. There is no mapped or compatible form to collapse here the way
    `canonical_address` collapses one -- a range is written the way it is
    delegated, and `::ffff:0:0/96` is a different assertion from a v4 range,
    which is why containment across families answers false rather than raising.
    """
    try:
        return ipaddress.ip_network(value, strict=True)
    except ValueError as error:
        raise PolicyError("malformed_host", f"{value} is not an address range") from error


def address_refusal(value: str) -> str | None:
    """Why an address may not be dialled, or nothing when the public internet routes it.

    This is shared by policy compilation and the egress door.  An inclusion
    that the compiler accepts must not become an address the proxy refuses only
    after a capability has been spent.  A non-address is a refusal here too;
    callers that also accept hostnames first decide whether the value is an
    address literal before asking this question.
    """
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return f"{value!r} is not an address"
    if parsed.is_unspecified:
        return f"{value} is the unspecified address"
    if parsed.is_loopback:
        return f"{value} is a loopback address"
    if parsed.is_link_local:
        return f"{value} is a link-local address"
    if parsed.is_multicast:
        # `is_global` is true for multicast, although it is not a destination
        # this harness can send an ordinary target exchange to.
        return f"{value} is a multicast address"
    if not parsed.is_global:
        return f"{value} is not a public address"
    return None


def unbracket(host: str) -> str:
    """A host with the brackets a URL puts around an IPv6 address removed.

    The brackets belong to the URL and not to the host: they are what keeps the
    colons inside the address apart from the colon before the port. Every place
    that has to recognise an address takes them off first -- the normalizer
    below, the CONNECT line at the door, the name written into a certificate --
    and three copies of two lines is three chances for one of them to drift.
    """
    if host.startswith("[") and host.endswith("]"):
        return host[1:-1]
    return host


def normalize_host(raw: object) -> str:
    """One host in one spelling, or a refusal naming what is wrong with it.

    The steps are `scope_normalize_host`'s, in the same order, because the two
    have to answer alike or the projection in the database and the decision at
    the proxy stop describing the same policy.
    """
    if not isinstance(raw, str):
        raise PolicyError("malformed_host", "a host must be text")
    # Spaces only, because `btrim` trims spaces only. `str.strip()` also removes
    # U+00A0, so a host padded with one would be a name here and malformed in
    # SQL -- the exact class of disagreement this pairing exists to prevent.
    value = unbracket(raw.strip(" ").lower().rstrip("."))
    if not value:
        raise PolicyError("no_host", "no host was given")
    if not value.isascii():
        raise PolicyError(
            "malformed_host",
            f"{value!r} is not ASCII; an internationalised name is encoded before it is matched",
        )
    if _IPV4.fullmatch(value) or _IPV6.fullmatch(value) or _MAPPED.fullmatch(value):
        return canonical_address(value)
    if len(value) > _MAXIMUM_HOST:
        raise PolicyError("malformed_host", f"a host longer than {_MAXIMUM_HOST} characters")
    for label in value.split("."):
        if not _LABEL.fullmatch(label):
            raise PolicyError("malformed_host", f"{value!r} carries the label {label!r}")
    return value


def normalize_port(value: object, protocol: str) -> int:
    """The port a request is for, defaulted from the protocol when absent.

    An empty port is the protocol's own; anything else must be a plain decimal
    number in range. `0443` is refused rather than read as 443, because a rule
    written for one of those two spellings would not cover the other.
    """
    if value is None or value == "":
        return DEFAULT_PORTS[protocol]
    if isinstance(value, str):
        # `isdigit` alone is true of Arabic-Indic digits, which `int` reads as a
        # port the operator never typed, and of superscripts, which `int` refuses
        # with a bare ValueError no caller of this module handles.
        if not (value.isascii() and value.isdigit()) or (
            len(value) > 1 and value.startswith("0")
        ):
            raise PolicyError("malformed_port", f"{value!r} is not a decimal port number")
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PolicyError("malformed_port", "a port must be a number")
    if not 1 <= value <= 65535:
        raise PolicyError("malformed_port", f"port {value} is outside 1-65535")
    return value


def path_variants(path: object) -> tuple[str, str]:
    """A path in both spellings a prefix rule is matched against.

    The raw form is what was asked for and the normalised form is where it
    lands. Both are kept because the two polarities need different ones: an
    exclusion fires if *either* spelling is under its prefix, so `/admin/../x`
    cannot escape a `/admin/` exclusion, while an inclusion needs *both*, so the
    same trick cannot smuggle a request into an authorised prefix.
    """
    if not isinstance(path, str):
        raise PolicyError("malformed_path", "a path must be text")
    raw = path or "/"
    if not raw.startswith("/"):
        raw = "/" + raw
    if not raw.isprintable():
        raise PolicyError("malformed_path", "the path holds a character that does not print")
    # To a fixpoint, not once. One pass turns `%252e%252e` into `%2e%2e`, which
    # holds no dot segment for `normpath` to collapse, so a doubly-encoded
    # traversal would walk out of an exclusion while the receipt cited the
    # inclusion. A path that is still changing after this many passes is refused
    # rather than decoded further: nothing legitimate encodes that deeply.
    decoded = raw
    for _ in range(_DECODE_PASSES + 1):  # the last pass is the one that confirms
        once = unquote(decoded)
        if once == decoded:
            break
        decoded = once
    else:
        raise PolicyError(
            "malformed_path", f"the path is encoded more than {_DECODE_PASSES} times over"
        )
    if not decoded.isprintable():
        raise PolicyError(
            "malformed_path", "the path decodes to a character that does not print"
        )
    normed = posixpath.normpath(decoded.replace("\\", "/"))
    if decoded.endswith("/") and not normed.endswith("/"):
        normed += "/"
    # `normpath` preserves exactly two leading slashes, POSIX having reserved
    # them, so `//admin` would not be under a `/admin` exclusion while most web
    # servers serve it as one.
    normed = "/" + normed.lstrip("/")
    return raw, normed


def path_under(path: str, prefix: str) -> bool:
    """Whether `path` is at or below `prefix`, ending on a segment boundary.

    A bare `startswith` would make the prefix `/v1` authorise `/v1-internal/dump`
    and `/v10/anything`, which share four characters with it and nothing else. A
    prefix names a subtree, so it covers itself and what is under the separator,
    and never a sibling that merely begins the same way. Mirrors
    `scope_path_under`.
    """
    if not path.startswith(prefix):
        return False
    return prefix.endswith("/") or len(path) == len(prefix) or path[len(prefix)] == "/"


def host_candidates(host: str) -> tuple[str, ...]:
    """Every match key that may cover this host, exact first.

    `a.b.c` is covered by `a.b.c`, `*.b.c` and `*.c`, and *not* by `*.a.b.c`.
    The series starts at the second label, and that is the entire apex rule:
    `*.here.com` never matches `here.com`, so a wildcard inclusion cannot put
    the Program's own apex in scope by implication.
    """
    labels = host.split(".")
    return (host,) + tuple(
        "*." + ".".join(labels[index - 1 :]) for index in range(2, len(labels) + 1)
    )


def wildcard_candidates(suffix: str) -> tuple[str, ...]:
    """Every match key that may cover this whole subtree.

    A different question from `host_candidates`, so a different series: the
    subtree `*.account.here.com` is covered by `*.account.here.com` and by
    `*.here.com`, so this one starts at the first label. No exact rule appears
    here, which is `jaguar.here.com` being a legal target without thereby
    authorising anything about `*.jaguar.here.com`.
    """
    labels = suffix.split(".")
    return tuple("*." + ".".join(labels[index - 1 :]) for index in range(1, len(labels) + 1))


@dataclass(frozen=True)
class Request:
    """One canonicalised request, in the terms the rules are matched against.

    `protocol` and `port` are `None`, and `question` something other than
    `request`, only for the entity projection: it asks whether a host is
    reachable at all rather than whether one exact request is authorised.
    `canonical_request` produces neither, so the wider reading is not reachable
    from anything that came off the wire.
    """

    protocol: str | None
    host: str
    port: int | None
    path_raw: str
    path_norm: str
    question: str = QUESTION_REQUEST

    def __post_init__(self) -> None:
        # An unknown word raises here rather than being matched, because the two
        # coverage polarities are the wide ones: a caller that mistyped
        # `request` would otherwise be answered under the widest reading of the
        # policy and read it as an authorisation.
        if self.question not in QUESTIONS:
            raise PolicyError(
                "not_addressable",
                f"unknown scope question {self.question!r}; known: " + ", ".join(QUESTIONS),
            )

    def summary(self) -> dict:
        return {
            "question": self.question,
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "path": self.path_raw,
            "normalized_path": self.path_norm,
        }


def canonical_request(url: object) -> Request:
    """Read one URL into the five values a decision is made from.

    Userinfo is refused outright. A configuration may not carry a credential and
    neither may a URL handed to the policy: `https://user:pw@host/` would put one
    in whatever log the request is reported to, and the harness resolves
    credentials from runtime-owned slots instead.
    """
    if not isinstance(url, str):
        raise PolicyError("malformed_url", "a URL must be text")
    try:
        parts = urlsplit(url)
    except ValueError as error:
        raise PolicyError("malformed_url", f"the URL cannot be read: {error}") from error
    protocol = parts.scheme.lower()
    if protocol not in PROTOCOLS:
        raise PolicyError(
            "unsupported_protocol",
            f"{protocol or '(none)'} is not one of: " + ", ".join(PROTOCOLS),
        )
    try:
        userinfo = parts.username is not None or parts.password is not None
    except ValueError as error:
        raise PolicyError("malformed_url", f"the URL cannot be read: {error}") from error
    if userinfo:
        raise PolicyError(
            "malformed_url",
            "a URL carrying userinfo is refused; credentials are runtime-owned",
        )
    try:
        given = parts.port
    except ValueError as error:
        raise PolicyError("malformed_port", f"the port cannot be read: {error}") from error
    host = normalize_host(parts.hostname or "")
    raw, normed = path_variants(parts.path or "/")
    return Request(
        protocol=protocol,
        host=host,
        port=normalize_port(given, protocol),
        path_raw=raw,
        path_norm=normed,
    )


def canonical_selector(value: object) -> tuple[str, int | None, str]:
    """One `host[:port][/path]` as an operator writes it, canonicalised.

    The selector an entity carries, in the spelling an operator can type. Read
    through `urlsplit` on a scheme-relative URL rather than by splitting on
    colons and slashes, so a bracketed IPv6 literal, a userinfo prefix and an
    out-of-range port are refused by exactly the code that refuses them inside a
    URL. A missing port stays `None`, which is the entity question — reachable on
    any port the policy authorises — rather than a guess at 443. A query or a
    fragment is refused: neither is matched by any rule, so accepting one would
    answer a narrower question than it appears to ask.
    """
    if not isinstance(value, str):
        raise PolicyError("malformed_host", "a selector must be text")
    try:
        parts = urlsplit("//" + value)
    except ValueError as error:
        raise PolicyError("malformed_host", f"the selector cannot be read: {error}") from error
    if parts.username is not None or parts.password is not None:
        raise PolicyError(
            "malformed_url",
            "a selector carrying userinfo is refused; credentials are runtime-owned",
        )
    if parts.query or parts.fragment:
        raise PolicyError(
            "malformed_host",
            f"{value!r} carries a query or fragment; no rule matches either",
        )
    try:
        given = parts.port
    except ValueError as error:
        raise PolicyError("malformed_port", f"the port cannot be read: {error}") from error
    return normalize_host(parts.hostname or ""), given, parts.path or "/"


# ---------------------------------------------------------------------------
# The compiled policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pattern:
    """One host pattern, already parsed, in the form SQL joins on.

    Three kinds, and the third one matches differently from the other two.
    `exact` and `wildcard` are keys: SQL joins them by equality against the
    candidate series a host expands to. `cidr` is a range, and the only thing
    that decides it is address containment, which is why `match_key` is None
    there and `net` is not -- `program_scope_rules` asserts both directions of
    that pairing (`0021_scope_policy.sql:109-110`), so a pattern that answered
    both would fail the insert.
    """

    kind: str
    text: str

    @property
    def match_key(self) -> str | None:
        return None if self.kind == "cidr" else self.text

    @property
    def net(self) -> str | None:
        return self.text if self.kind == "cidr" else None

    @property
    def spec_kind(self) -> int:
        if self.kind == "cidr":
            return SPEC_CIDR
        return SPEC_EXACT if self.kind == "exact" else SPEC_WILDCARD

    @property
    def spec_len(self) -> int:
        # A prefix length, so a /24 is cited over the /8 that also matched, on
        # the same reading that cites `a.b.c` over `*.c`: the narrower rule is
        # the one that describes the decision. Only compared within a kind,
        # because `spec_kind DESC` is applied first.
        return parse_network(self.text).prefixlen if self.kind == "cidr" else self.text.count(".") + 1

    def covers(self, host: str) -> bool:
        """Whether this pattern covers one host, by key or by containment.

        A range decides addresses and never names, and that is deliberate
        rather than unfinished: the door decides before it resolves -- "So the
        order is decide, then resolve, then dial" (`proxy.resolve`) -- so a
        request naming `www.example.com` cannot be admitted by the range its
        address happens to fall in without the policy depending on what a
        resolver said today. `scope_class_of` guards its containment arm on the
        same test, `nh.h ~ '^([0-9.]+|[0-9a-f:]+)$'`.
        """
        if self.kind == "cidr":
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                return False
            return address in parse_network(self.text)
        return self.match_key in host_candidates(host)

    def covers_subtree(self, suffix: str) -> bool:
        # A range is not a domain and cannot cover one, whatever addresses the
        # names beneath it resolve to. `scope_class_of` says the same thing by
        # guarding the containment arm with `p_question <> 'subtree'`.
        if self.kind == "cidr":
            return False
        return self.match_key in wildcard_candidates(suffix)


def parse_pattern(raw: str, *, broad: bool = False) -> Pattern:
    """One host pattern from the configuration, or a refusal.

    There is no globbing here and there never will be. A leading `*.` is a
    suffix test and nothing else, so `ap*.example.com` and `*.*.example.com` are
    refused rather than quietly matching more or less than they appear to.

    `broad` is the exclusion side, and it lifts exactly one rule: the two-label
    floor under a wildcard. README's scope section grants it -- "An exclusion has
    no floor, because breadth there withdraws authority rather than claiming it"
    -- and `config.load` already implements it through `_BROAD_HOST`, so without
    the flag a configuration that loads is one this function refuses to compile.

    A slash is a range and is read before anything else, because every other
    branch here is about names: `10.0.0.0/8` carries the label `0/8` to the
    hostname reader, which is a refusal that tells an operator nothing about
    what they wrote.
    """
    if not isinstance(raw, str):
        raise PolicyError("malformed_host", "a host pattern must be text")
    text = raw.strip(" ").lower().rstrip(".")
    if "/" in text:
        if "*" in text:
            # A wildcard is a suffix test over names and a range is containment
            # over addresses. Something that claimed both would have to be read
            # as one of them, and neither reading is the one an operator wrote.
            raise PolicyError("malformed_host", f"{raw!r} wildcards an address range")
        return Pattern(kind="cidr", text=str(parse_network(text)))
    if text.startswith("*."):
        suffix = normalize_host(text[2:])
        if "*" in suffix:
            raise PolicyError("malformed_host", f"{raw!r} carries more than one wildcard")
        if _IPV4.fullmatch(suffix) or _IPV6.fullmatch(suffix) or _MAPPED.fullmatch(suffix):
            raise PolicyError("malformed_host", f"{raw!r} wildcards an address")
        if "." not in suffix and not broad:
            raise PolicyError(
                "malformed_host", f"{raw!r} wildcards a single label, which is a whole registry"
            )
        return Pattern(kind="wildcard", text="*." + suffix)
    if "*" in text:
        raise PolicyError(
            "malformed_host", f"{raw!r} is not a pattern; a wildcard is only a leading '*.'"
        )
    return Pattern(kind="exact", text=normalize_host(text))


@dataclass(frozen=True)
class Rule:
    """One compiled rule: one effect, one pattern, one protocol, port and path.

    A configuration rule names sets — several ports, both protocols, a handful
    of prefixes — and is expanded into one of these per combination. Expanding
    rather than storing the sets is what lets the database match by equality on
    indexed columns without knowing anything about the grammar.
    """

    ord: int
    effect: str
    pattern: Pattern
    protocol: str
    port: int
    path_prefix: str
    origin: str

    @property
    def effect_rank(self) -> int:
        return EFFECT_RANK[self.effect]

    def matches(self, request: Request) -> bool:
        """Whether this rule covers one request.

        Three polarities, not one. An exclusion fires if *either* spelling of
        the path is under its prefix, so a traversal cannot walk out of a
        withdrawal, and it is the same test whatever is being asked: a
        withdrawal removes only what it names, so a `/admin/` exclusion does not
        put the host out of reach. An authorising rule answering a request needs
        *both* spellings, so a traversal cannot walk into one. An authorising
        rule answering a coverage question is satisfied by a prefix in either
        direction, because a host whose `/api/` is in scope is a host worth
        queueing even though its `/` is not a request anyone authorised.
        """
        if request.protocol is not None and request.protocol != self.protocol:
            return False
        if request.port is not None and request.port != self.port:
            return False
        covers = (
            self.pattern.covers_subtree(request.host)
            if request.question == QUESTION_SUBTREE
            else self.pattern.covers(request.host)
        )
        if not covers:
            return False
        if self.effect == EXCLUDE:
            return path_under(request.path_raw, self.path_prefix) or path_under(
                request.path_norm, self.path_prefix
            )
        if request.question == QUESTION_REQUEST:
            return path_under(request.path_raw, self.path_prefix) and path_under(
                request.path_norm, self.path_prefix
            )
        return path_under(request.path_raw, self.path_prefix) or path_under(
            self.path_prefix, request.path_raw
        )

    def row(self) -> dict:
        """The rule as `program_scope_rules` holds it, plus where it came from.

        Every key but `origin` is a column of that table. `origin` names the
        configuration entry the rule was expanded from, which is what makes a
        stored policy readable back to the file that produced it; the insert
        selects the columns it needs and leaves it in the document.

        `match_key` and `net` are the pair the table's two CHECKs assert both
        directions of: exactly one of them is set, and which one it is says how
        the rule is matched. Both keys are always present and one of them is
        always null, because the rows are projected through
        `jsonb_to_recordset`, which needs every row to name the same columns.
        """
        return {
            "ord": self.ord,
            "effect": self.effect,
            "effect_rank": self.effect_rank,
            "pattern_kind": self.pattern.kind,
            "pattern_text": self.pattern.text,
            "match_key": self.pattern.match_key,
            "net": self.pattern.net,
            "protocol": self.protocol,
            "port": self.port,
            "path_prefix": self.path_prefix,
            "spec_kind": self.pattern.spec_kind,
            "spec_len": self.pattern.spec_len,
            "origin": self.origin,
        }


def host_admitted(observed: str, endpoint: str | None) -> bool:
    """Whether an observed name is a channel endpoint or a label beneath it.

    The rule written once, because three places ask it: the compiled channel,
    the verb that admits an arrival, and `callback_host_admitted` in SQL, which
    is this function in the one place Python cannot reach. None is not an
    endpoint, so a channel with nothing bound admits nothing.
    """
    if endpoint is None:
        return False
    return observed == endpoint or observed.endswith("." + endpoint)


@dataclass(frozen=True)
class Channel:
    """One out-of-band callback endpoint the harness operates.

    A channel is never a target and never evidence. It is somewhere the harness
    may observe an interaction arriving, which is why it compiles to
    `egress_support` and why a host that is both a channel and an inclusion
    resolves to the channel: the lower effect rank wins, and a callback endpoint
    the Program also happens to own is still not a finding.

    Two things about a channel are not the endpoint. `placement` says where in
    an arrival its correlator sits -- a label beneath the endpoint, or the first
    segment of the request path, which is the difference between a canary that
    can only be pinged and one that can serve a file per correlator.
    `provider` says who decides the endpoint: `static` is the name the operator
    wrote down, and anything else is a name bound at run time, for which `host`
    is None here and the live value lives in `callback_channel_bindings`.
    """

    name: str
    kind: str
    host: str | None = None
    placement: str = "label"
    provider: str = "static"

    def __post_init__(self) -> None:
        """The three ways a channel can be self-contradictory, refused here.

        Written once, in the type, because a channel is built from a
        configuration and read back from a projection, and a rule enforced at
        one of those doors is a rule the other one lets through.
        """
        if self.placement not in config.CALLBACK_PLACEMENTS:
            raise PolicyError(
                "unsupported", f"unknown callback placement {self.placement}", "placement"
            )
        if self.provider not in config.CALLBACK_PROVIDERS:
            raise PolicyError(
                "unsupported", f"unknown callback provider {self.provider}", "provider"
            )
        if (self.provider == "static") != (self.host is not None):
            # An endpoint is either written down or bound at run time. Both is a
            # host that would go stale the moment something bound a name, and
            # neither is a channel nothing can arrive at.
            raise PolicyError(
                "unsupported",
                "a static callback names its endpoint and a bound one does not: "
                f"provider {self.provider} with "
                + ("a host" if self.host is not None else "no host"),
                "host",
            )
        if self.kind != "http" and (self.placement != "label" or self.provider != "static"):
            # A resolver sends a name and nothing else: there is no path to put
            # a correlator in, and no way to publish a file at a bound name over
            # DNS. Both are the HTTP channel's business.
            raise PolicyError(
                "unsupported",
                f"a {self.kind} callback carries its correlator in a label of an "
                "endpoint written down in advance",
            )

    @property
    def dynamic(self) -> bool:
        """Whether this channel's name is bound at run time rather than declared.

        Asked of `host` rather than of `provider` because `__post_init__` has
        already made them the same question, and this is the half every caller
        means: a channel with no name in the configuration is one whose name has
        to be read from somewhere else.
        """
        return self.host is None

    def endpoint(self, bindings: dict[str, str] | None = None) -> str | None:
        """The name this channel is answering at, or nothing when none is.

        A static channel answers at what the operator wrote down, whatever is
        bound; a bound one answers at what `bindings` says and at nothing when
        that says nothing. None is a real answer for the second, and it is the
        answer that makes a channel with nothing bound admit nothing.
        """
        if self.host is not None:
            return self.host
        return (bindings or {}).get(self.name)

    def admits(self, host: str, bindings: dict[str, str] | None = None) -> bool:
        """Whether an interaction at `host` arrived on this channel.

        Labels beneath the endpoint count, because that is how an out-of-band
        canary is addressed: the token is the label. The endpoint itself counts
        too, and nothing above it does.
        """
        return host_admitted(host, self.endpoint(bindings))

    def summary(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "host": self.host,
            "placement": self.placement,
            "provider": self.provider,
        }


@dataclass(frozen=True)
class Header:
    """One header the proxy injects: a name that travels and a slot that does not.

    The value is never here and never in the configuration — `config` refuses an
    inline one — so the pair is a name and a reference the runtime resolves.
    `document` and `summary` carry the name alone, which is the whole of what an
    agent-visible projection may say about a required header.
    """

    name: str
    value_ref: str

    def summary(self) -> dict:
        return {"name": self.name}


@dataclass(frozen=True)
class Permission:
    """One independent risk permission, and whether the policy grants it."""

    subject: str
    allowed: bool
    reason: str
    detail: str = ""

    def summary(self) -> dict:
        return {
            "subject": self.subject,
            "allowed": self.allowed,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Policy:
    """Everything one Program is authorised to do, compiled once.

    Built by `compile_policy` from a validated configuration and never assembled
    by hand: the ordering of `rules` carries the ordinals the database stores,
    so two policies compiled from one configuration have to be identical byte
    for byte, and `policy_sha256` is what says they are.
    """

    program: str
    configuration_sha256: str
    rules: tuple[Rule, ...]
    channels: tuple[Channel, ...]
    controls: tuple[tuple[str, bool], ...]
    headers: tuple[Header, ...]
    budgets: tuple[tuple[str, int], ...]
    grammar_version: int = GRAMMAR_VERSION

    @property
    def window_seconds(self) -> int:
        """The time window the budgets are counted over, in seconds."""
        return dict(self.budgets)["window_seconds"]

    def channel(self, name: str) -> Channel | None:
        """The channel declared under that name, or nothing when none is.

        Beside `channels` rather than in a caller, because both questions the
        callback verbs ask -- whether this Program declares a channel by that
        name, and which channel `decide_callback` named -- are the same lookup,
        and two spellings of one lookup are two answers waiting to disagree.
        """
        for channel in self.channels:
            if channel.name == name:
                return channel
        return None

    def document(self) -> dict:
        """The policy as `program_scope_versions.policy` holds it.

        Names only for the required headers. The slot reference is what the
        proxy resolves a value through, and it lives in one place —
        `program_required_headers` — rather than being copied into a document
        that several things read.
        """
        return {
            "grammar_version": self.grammar_version,
            "program": self.program,
            "configuration_sha256": self.configuration_sha256,
            "rules": [rule.row() for rule in self.rules],
            "channels": [channel.summary() for channel in self.channels],
            "rules_of_engagement": dict(self.controls),
            "required_headers": [header.name for header in self.headers],
            "budgets": dict(self.budgets),
        }

    def policy_sha256(self) -> str:
        return hashlib.sha256(config.canonical_bytes(self.document())).hexdigest()

    def summary(self) -> dict:
        """The diagnostic projection: counts, names, controls and hashes."""
        return {
            "grammar_version": self.grammar_version,
            "program": self.program,
            "configuration_sha256": self.configuration_sha256,
            "policy_sha256": self.policy_sha256(),
            "rules": len(self.rules),
            "targets": sum(1 for rule in self.rules if rule.effect == TARGET),
            "exclusions": sum(1 for rule in self.rules if rule.effect == EXCLUDE),
            "channels": [channel.summary() for channel in self.channels],
            "rules_of_engagement": dict(self.controls),
            "required_headers": [header.name for header in self.headers],
            "budgets": dict(self.budgets),
            "window_seconds": self.window_seconds,
            "discovery": {technique: False for technique in DISCOVERY_TECHNIQUES},
        }


def compile_policy(
    configuration: config.Configuration,
) -> tuple[Policy | None, tuple[Violation, ...]]:
    """Compile one validated configuration into the policy every caller asks.

    Returns violations rather than raising, in the shape `config.load` returns
    them, so a command can refuse a configuration that parses and does not
    compile without a traceback reaching an operator.
    """
    document = configuration.document
    refusals: list[Violation] = []
    compiled: dict[tuple, Rule] = {}

    def add(effect: str, entry: dict, source: str, protocols, ports, paths) -> None:
        try:
            pattern = parse_pattern(entry["host"], broad=effect == EXCLUDE)
        except PolicyError as error:
            refusals.append(_refusal(f"{source}.host", error.detail))
            return
        if effect != EXCLUDE and _unroutable(pattern):
            # Only on the authorising side. An exclusion naming a private range
            # withdraws authority and is the operator's business; an inclusion
            # naming one points the harness at infrastructure the Program's
            # scope statement cannot have meant, most often its own.
            subject = "address range" if pattern.kind == "cidr" else "address"
            refusals.append(
                _refusal(
                    f"{source}.host",
                    f"{pattern.text} is not a globally routable {subject}; "
                    "an inclusion may not name one",
                )
            )
            return
        # The stored prefix is canonicalised the same way a request's path is,
        # because the two are compared. Left verbatim, an exclusion written
        # `/adm%69n/` would fire on nothing an operator can type, and an
        # inclusion written `/a/../v1/` would match neither spelling and quietly
        # authorise nothing at all.
        prefixes: list[str] = []
        for path in paths:
            try:
                prefixes.append(path_variants(path)[1])
            except PolicyError as error:
                refusals.append(_refusal(f"{source}.paths", error.detail))
                return
        for protocol in protocols:
            for port in ports:
                for path in prefixes:
                    key = (effect, pattern.text, protocol, port, path)
                    compiled.setdefault(
                        key,
                        Rule(
                            ord=0,
                            effect=effect,
                            pattern=pattern,
                            protocol=protocol,
                            port=port,
                            path_prefix=path,
                            origin=source,
                        ),
                    )

    scope = document["scope"]
    for index, entry in enumerate(scope["exclude"]):
        add(
            EXCLUDE,
            entry,
            f"scope.exclude[{index}]",
            entry["protocols"],
            entry["ports"],
            entry["paths"],
        )
    for index, entry in enumerate(scope["include"]):
        add(
            TARGET,
            entry,
            f"scope.include[{index}]",
            entry["protocols"],
            entry["ports"],
            entry["paths"],
        )

    channels: list[Channel] = []
    endpoints: dict[str, str] = {}
    for index, entry in enumerate(document["callback"]):
        source = f"callback[{index}]"
        host = entry["host"]
        if host is not None:
            if host.startswith("*."):
                # A channel already admits everything beneath its endpoint, so a
                # wildcard here is a second way to say one thing -- and the two
                # spellings would not agree about the endpoint itself.
                refusals.append(
                    _refusal(
                        f"{source}.host",
                        "a callback names its own endpoint; interactions beneath it are "
                        "admitted by the channel, so a wildcard is refused",
                    )
                )
                continue
            try:
                host = normalize_host(host)
            except PolicyError as error:
                refusals.append(_refusal(f"{source}.host", error.detail))
                continue
            if host in endpoints:
                # One endpoint, one channel, which is what `program_callback_channels`
                # keys on as well. Two names for one host would make "which channel
                # admitted this arrival" a question about declaration order, and the
                # projection would silently keep one row while the compiler reported
                # two channels.
                refusals.append(
                    _refusal(
                        f"{source}.host",
                        f"{host} is already the endpoint of callback {endpoints[host]}; "
                        "one endpoint is one channel",
                    )
                )
                continue
            endpoints[host] = entry["name"]
        # An absent key is the dataclass default, so a configuration written
        # before there was a placement or a provider reads as the one behaviour
        # there was; the contradictions between the four are `Channel`'s to
        # refuse, which is why this only turns them into a refusal.
        declared = {key: entry[key] for key in ("placement", "provider") if key in entry}
        try:
            channel = Channel(name=entry["name"], kind=entry["kind"], host=host, **declared)
        except PolicyError as error:
            # Pointed at the key when the contradiction has one, because
            # `callback[0]` sends an operator to read four keys to find the one
            # they can fix. The kind rule names no single key and stays here.
            refusals.append(
                _refusal(f"{source}.{error.key}" if error.key else source, error.detail)
            )
            continue
        channels.append(channel)
        if channel.kind == "http" and channel.host is not None:
            # A DNS channel is not an HTTP destination, so only this kind
            # becomes a request rule. Both kinds stay channels.
            #
            # A bound channel gets no rule at all: there is no name to write one
            # about until something binds it, and the harness never requests its
            # own endpoint anyway -- the target does. `rk oob` reaches the
            # publisher on the loopback address, which no policy governs.
            add(
                EGRESS_SUPPORT,
                {"host": channel.host},
                source,
                PROTOCOLS,
                CALLBACK_PORTS,
                ("/",),
            )

    if refusals:
        return None, ordered(refusals)

    # Sorted on the rule's own content, never on where it appeared. Document
    # order is not a semantic here, and an ordinal derived from it would make
    # two configurations that say the same thing compile to different bytes.
    rules = tuple(
        Rule(
            ord=index + 1,
            effect=rule.effect,
            pattern=rule.pattern,
            protocol=rule.protocol,
            port=rule.port,
            path_prefix=rule.path_prefix,
            origin=rule.origin,
        )
        for index, rule in enumerate(
            sorted(
                compiled.values(),
                key=lambda item: (
                    item.effect_rank,
                    # The pattern's own text rather than its match key, which is
                    # None on a range and would not order against a host.
                    item.pattern.text,
                    item.pattern.kind,
                    item.protocol,
                    item.port,
                    item.path_prefix,
                ),
            )
        )
    )

    controls = tuple(
        (control, bool(document["rules_of_engagement"][control]))
        for control in config.RULES_OF_ENGAGEMENT
    )
    headers = tuple(
        Header(name=entry["name"], value_ref=entry["value_ref"])
        for entry in document["required_header"]
    )
    budgets = tuple((limit, int(document["budgets"][limit])) for limit in config.BUDGET_LIMITS)

    return (
        Policy(
            program=document["program"]["name"],
            configuration_sha256=configuration.canonical_sha256,
            rules=rules,
            channels=tuple(sorted(channels, key=lambda item: item.name)),
            controls=controls,
            headers=headers,
            budgets=budgets,
        ),
        (),
    )


def _refusal(source: str, detail: str) -> Violation:
    return Violation(code=INVALID_CONFIGURATION, source=f"scope:{source}", detail=detail)


def _unroutable(pattern: Pattern) -> bool:
    """Whether an authorising pattern names address space the door would refuse.

    `address_refusal` is the rule, shared with the egress door, so an inclusion
    the compiler accepts cannot become an address the proxy refuses only after a
    capability has been spent. A range is asked the same question at both ends,
    which is what catches the ones an operator reaches for by accident --
    `10.0.0.0/8`, `192.168.0.0/16`, `0.0.0.0/0`, `::/0`.

    What both ends do not catch is a globally routable block that contains a
    private one, `172.0.0.0/8` being the case: private space is itself carved
    into CIDR blocks, so a wider block can straddle one with global addresses on
    either side. That range compiles, and every private address inside it is
    still refused at the door -- `proxy.unroutable` denies by default and
    `authorize_egress_address` re-decides the literal address the proxy pinned.
    Closing it here would mean restating the door's block list in this module,
    which is the duplication `address_refusal` exists to prevent.
    """
    if pattern.kind == "cidr":
        edges = parse_network(pattern.text)
        return any(
            address_refusal(str(edge)) is not None
            for edge in (edges.network_address, edges.broadcast_address)
        )
    try:
        ipaddress.ip_address(pattern.text)
    except ValueError:
        return False
    return address_refusal(pattern.text) is not None


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Verdict:
    """One decision, and everything a receipt needs to cite it."""

    scope_class: str
    reason: str
    request: Request | None = None
    rule_ord: int | None = None
    channel: str = ""
    detail: str = ""

    @property
    def allowed(self) -> bool:
        return self.scope_class in (TARGET, EGRESS_SUPPORT)

    @property
    def is_target(self) -> bool:
        return self.scope_class == TARGET

    def summary(self) -> dict:
        return {
            "scope_class": self.scope_class,
            "reason": self.reason,
            "allowed": self.allowed,
            "request": self.request.summary() if self.request else None,
            "rule_ord": self.rule_ord,
            "channel": self.channel,
            "detail": self.detail,
        }


def decide(policy: Policy, url: object) -> Verdict:
    """The verdict for one URL. Every input gets one, including a refused one."""
    try:
        request = canonical_request(url)
    except PolicyError as error:
        return Verdict(scope_class=DENIED, reason=error.reason, detail=error.detail)
    return decide_request(policy, request)


def decide_request(policy: Policy, request: Request) -> Verdict:
    """The verdict for one canonicalised request.

    The verdict is the lowest effect rank over every matching rule, computed
    before any question of specificity is asked. Specificity then picks which of
    the winning rules is named in the answer, in the order SQL applies:
    `spec_kind DESC, spec_len DESC, ord ASC`.
    """
    return _cite([rule for rule in policy.rules if rule.matches(request)], request)


def decide_entity(
    policy: Policy,
    kind: str | None,
    selector: str | None,
    *,
    port: int | None = None,
    path: str = "/",
) -> Verdict:
    """The verdict for a stored entity, which is a different question.

    A host entity asks whether it may be reached under *any* protocol, on any
    port the policy authorises, so those two dimensions are dropped rather than
    guessed; an entity that names a port keeps it. A wildcard entity asks about
    a whole subtree and is matched on the wildcard series, so an exact rule
    never authorises the domain above it.

    An unknown selector kind raises. It must not fall through to a denial: a
    caller that mistyped a kind would then read a refusal as a policy decision
    and never find the bug.
    """
    if kind is None or selector is None:
        return Verdict(scope_class=NOT_ADDRESSABLE, reason="not_addressable")
    if kind not in SELECTORS:
        raise PolicyError("not_addressable", f"unknown entity selector kind {kind!r}")
    try:
        host = normalize_host(selector)
        raw, normed = path_variants(path)
        asked = None if port is None else normalize_port(port, "https")
    except PolicyError as error:
        return Verdict(scope_class=DENIED, reason=error.reason, detail=error.detail)

    return decide_request(
        policy,
        Request(
            protocol=None,
            host=host,
            port=asked,
            path_raw=raw,
            path_norm=normed,
            question=(
                QUESTION_COVERAGE if kind == SELECTOR_HOST else QUESTION_SUBTREE
            ),
        ),
    )


def decide_callback(
    policy: Policy, host: object, bindings: dict[str, str] | None = None
) -> Verdict:
    """Whether an observed interaction arrived on a channel this Program declared.

    Never `target`, whatever else the policy says about the host: an interaction
    with the harness's own listener is evidence that something reached out, not
    evidence about a target surface.

    Which channel is named, when a Program declares one beneath another, is the
    most specific declaration -- the same rule `decide_request` applies to rules
    and for the same reason. It also decides where the correlator ends: the
    label beneath `a.oob.example.net` is a label of that channel and not a
    longer canary on its parent.

    `bindings` is what each bound channel is answering at right now, which is
    not in the policy because it is not in the configuration: a channel whose
    provider hands it a name has no endpoint until something binds one, and a
    channel missing from this mapping admits nothing.
    """
    try:
        observed = normalize_host(host)
    except PolicyError as error:
        return Verdict(scope_class=DENIED, reason=error.reason, detail=error.detail)
    admitting = [channel for channel in policy.channels if channel.admits(observed, bindings)]
    if not admitting:
        return Verdict(scope_class=DENIED, reason="unlisted", detail=observed)
    channel = max(admitting, key=lambda entry: len(entry.endpoint(bindings) or ""))
    return Verdict(
        scope_class=EGRESS_SUPPORT,
        reason="matched_callback",
        channel=channel.name,
        detail=observed,
    )


def decide_action(policy: Policy, control: object) -> Permission:
    """Whether one independent risk permission is granted.

    Absence is a denial and there is no permissive default: the configuration
    loader fills every control it was not given with `False`, and this reads that
    table rather than a `get` with a fallback. An unknown control raises for the
    reason an unknown selector kind does — a typo that silently denied would be
    a bug nobody could see from the outside.
    """
    controls = dict(policy.controls)
    if control not in controls:
        raise PolicyError(
            "not_addressable",
            f"unknown rule of engagement {control!r}; known: "
            + ", ".join(config.RULES_OF_ENGAGEMENT),
        )
    allowed = controls[str(control)]
    return Permission(
        subject=str(control),
        allowed=allowed,
        reason="permitted" if allowed else "withheld",
        detail=(
            "" if allowed else "the configuration does not grant this permission, so it is denied"
        ),
    )


def decide_discovery(policy: Policy, technique: object) -> Permission:
    """Whether an infrastructure-discovery technique is authorised. None is.

    The spec puts all five out of scope, so there is no configuration key that
    turns one on and this function does not consult the policy it is handed.
    The argument is there so that callers ask the policy rather than remembering
    the rule, and so a test can assert the answer is the same for every policy
    that can be written.
    """
    if technique not in DISCOVERY_TECHNIQUES:
        raise PolicyError(
            "not_addressable",
            f"unknown discovery technique {technique!r}; known: "
            + ", ".join(DISCOVERY_TECHNIQUES),
        )
    return Permission(
        subject=str(technique),
        allowed=False,
        reason="discovery_not_authorized",
        detail=(
            "infrastructure discovery outside the configured web and API scope is excluded; "
            "an inclusion authorises requests to the hosts it names, never the enumeration "
            "that would find them"
        ),
    )


# ---------------------------------------------------------------------------
# The operator diagnostic
# ---------------------------------------------------------------------------


def diagnose(
    configuration_path: object,
    *,
    urls: tuple[str, ...] = (),
    hosts: tuple[str, ...] = (),
    subtrees: tuple[str, ...] = (),
    callbacks: tuple[str, ...] = (),
    actions: tuple[str, ...] = (),
    techniques: tuple[str, ...] = (),
) -> Report:
    """Compile one configuration and answer whatever was asked of the result.

    This is the diagnostic behind `rk scope`, and it reaches no database: the
    verdict for a request is a function of the policy and the request, so an
    operator can hold a configuration against a URL before any Program exists.
    That is also what makes it worth comparing against the runtime — the tests
    put the same fixture matrix through here, through the evaluator directly and
    through `scope_class_of`, and a disagreement is a bug in one of the three.

    A denial is an answer, not a refusal: every verdict is reported and the exit
    stays `0`. Only a configuration that does not load, does not compile, or
    names something this grammar has no word for refuses.
    """
    ledger = Ledger()
    empty: dict = {
        "policy": None,
        "requests": [],
        "entities": [],
        "callbacks": [],
        "permissions": [],
        "discovery": [],
    }

    configuration, violations = config.load(configuration_path)
    if configuration is None:
        ledger.refuse(
            "configuration",
            f"{configuration_path} is not a Program configuration this harness can compile",
            violations,
        )
        return report(COMMAND, ledger, **empty)
    ledger.hold("configuration", f"{configuration.path} states a Program policy")

    policy, refusals = compile_policy(configuration)
    if policy is None:
        ledger.refuse(
            "policy",
            "the configuration is valid and does not compile to a scope policy",
            refusals,
        )
        return report(COMMAND, ledger, **empty)
    ledger.hold(
        "policy",
        f"{len(policy.rules)} rule(s) over {len(policy.channels)} channel(s), "
        f"policy {policy.policy_sha256()[:12]}",
    )

    facts = dict(empty, policy=policy.summary())
    for url in urls:
        verdict = decide(policy, url)
        facts["requests"].append({"url": url, **verdict.summary()})
    for authority in hosts:
        facts["entities"].append(_entity(policy, SELECTOR_HOST, authority))
    for authority in subtrees:
        facts["entities"].append(_entity(policy, SELECTOR_WILDCARD, authority))
    # This command reaches no database, so a channel whose endpoint is bound at
    # run time has no name here to compare an arrival against, and every answer
    # below is about the declared endpoints only. Said out loud rather than left
    # for a reader to infer from an `unlisted` about a name that is answering
    # right now: `rk oob status` is where the live ones are.
    bound = [entry.name for entry in policy.channels if entry.dynamic]
    if callbacks and bound:
        ledger.hold(
            "callback_bindings",
            f"{', '.join(bound)} bind an endpoint at run time, which is in the "
            "database and not in this configuration; these verdicts read the "
            "declared endpoints only",
        )
    for host in callbacks:
        verdict = decide_callback(policy, host)
        facts["callbacks"].append({"host": host, **verdict.summary()})

    # Asked about nothing in particular is asked about everything: the whole
    # point of the permission half of the policy is that an operator can see all
    # five at once and find the one they did not mean to grant.
    for control in actions or config.RULES_OF_ENGAGEMENT:
        permission = _permission(ledger, lambda: decide_action(policy, control), control)
        facts["permissions"].append(permission)
    for technique in techniques or DISCOVERY_TECHNIQUES:
        permission = _permission(
            ledger, lambda: decide_discovery(policy, technique), technique
        )
        facts["discovery"].append(permission)

    return report(COMMAND, ledger, **facts)


def _entity(policy: Policy, kind: str, selector: str) -> dict:
    """One entity question, from the `host[:port][/path]` an operator wrote."""
    try:
        host, port, path = canonical_selector(selector)
    except PolicyError as error:
        return {
            "selector_kind": kind,
            "selector": selector,
            "port": None,
            "path": None,
            **Verdict(scope_class=DENIED, reason=error.reason, detail=error.detail).summary(),
        }
    verdict = decide_entity(policy, kind, host, port=port, path=path)
    return {
        "selector_kind": kind,
        "selector": host,
        "port": port,
        "path": path,
        **verdict.summary(),
    }


def _permission(ledger: Ledger, ask, subject: object) -> dict:
    """One permission answer, or a refusal naming a word the grammar lacks.

    `decide_action` and `decide_discovery` raise on an unknown subject on
    purpose, and an operator typing one at the command line is exactly the
    caller that must not read the resulting denial as policy.
    """
    try:
        return ask().summary()
    except PolicyError as error:
        ledger.fail(
            "permission",
            error.detail,
            code=INVALID_CONFIGURATION,
            source=f"argument:{subject}",
        )
        return {"subject": str(subject), "allowed": False, "reason": error.reason,
                "detail": error.detail}


def _cite(matched: list[Rule], request: Request) -> Verdict:
    """The verdict a set of matching rules produces, and which one it names."""
    if not matched:
        return Verdict(scope_class=DENIED, reason="unlisted", request=request)
    rank = min(rule.effect_rank for rule in matched)
    cited = min(
        (rule for rule in matched if rule.effect_rank == rank),
        key=lambda rule: (-rule.pattern.spec_kind, -rule.pattern.spec_len, rule.ord),
    )
    scope_class, reason = _outcome(cited.effect)
    return Verdict(scope_class=scope_class, reason=reason, request=request, rule_ord=cited.ord)


def _outcome(effect: str) -> tuple[str, str]:
    """The class and reason one winning effect produces."""
    if effect == EXCLUDE:
        return DENIED, "excluded"
    if effect == EGRESS_SUPPORT:
        return EGRESS_SUPPORT, "matched_egress_support"
    return TARGET, "matched_target"
