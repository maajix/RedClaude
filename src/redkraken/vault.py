"""Read one engagement secret out of the operator's 1Password vaults.

An engagement credential belongs to the operator and not to this harness. It is
an account on somebody else's bug bounty program, so the harness should hold it
for as long as it takes to seal it into an Identity slot and no longer. This
module is that hand-off and nothing besides: it shells out to the `op` CLI,
returns the value to its one caller, and puts it nowhere else.

Two vaults may be read and no others. The pair is a constant here rather than a
setting, because it is the operator's authorisation and not a preference -- a
reference naming any other vault is refused before a subprocess starts, so the
refusal belongs to this harness and does not depend on how the 1Password
account's own permissions happen to be set today. Those permissions are a
second boundary underneath this one, and the two disagreeing is exactly what a
`vault:forbidden` refusal reports.

The CLI rather than `onepassword-sdk`, because the SDK is not pure Python -- it
ships a compiled core -- and `pyproject.toml` says `dependencies = []` with a
startup assertion behind it. `op` reaches the same account, honours the same
service account token, and costs no dependency. If that trade ever reverses it
is this module rewritten and no call site touched.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from redkraken import child
from redkraken.outcome import (
    INVALID_CONFIGURATION,
    MISSING_DEPENDENCY,
    VAULT_UNREADABLE,
    Violation,
)


BINARY = "op"
SCHEME = "op://"

#: The vaults this harness may read, by id, beside the name the operator knows
#: each one by. Ids and not names: a name is a label the operator can change, and
#: two vaults can be renamed into each other, while the id is what a grant is
#: actually written against. A reference spelling its vault by name is refused
#: for the same reason -- `op` would happily resolve it, and this module would
#: have had nothing to check it against.
AUTHORISED = {
    #: Per-engagement accounts, one per program.
    "4exeximtkfyxd2eywo3m7jpfwu": "BugBounty Dynamic",
    #: What outlives an engagement: a store account for mobile work, and the key
    #: that saved cookies and confidential evidence are encrypted under.
    "a4g3qhvisxxcyvfzjtfpariwfe": "BugBounty Static",
}

#: Where `op` reads a service account token from. Set by this module rather than
#: by the caller, and never passed as an argument: an argument vector is
#: world-readable in `/proc` for as long as the process lives.
TOKEN_VARIABLE = "OP_SERVICE_ACCOUNT_TOKEN"

#: Where to find that token on disk when it is not already in the environment,
#: and the variable that moves it. A file rather than an exported variable is
#: what makes an unattended campaign possible at all: the token outlives one
#: shell, and nothing has to carry it through the process tree that starts a run.
TOKEN_PATH_VARIABLE = "RK_OP_TOKEN_FILE"
DEFAULT_TOKEN_PATH = Path("~/.config/op/claude-sa-token")

#: What the child inherits. `op` keeps its account configuration under HOME and
#: reaches a running desktop app through the user's runtime directory, so both
#: have to survive, and every `OP_` variable travels because that is the channel
#: an interactive `op signin` session arrives on. Nothing outside those two sets
#: is carried.
#:
#: `OP_` is a whole namespace and not one session variable, so what an operator
#: exports there does reach the read: `OP_ACCOUNT` chooses which account answers
#: it and `OP_DEBUG` makes the child verbose on the stderr `_refusal` may quote.
#: That is inheritance working as intended -- the environment is where a signed-
#: in operator's session lives -- and it is not a way past this module's own
#: check, which is the allowlist at `Reference.__post_init__`: it runs on the
#: reference before any child is started, so no environment reaches a vault
#: this repository has not named.
PASSED_THROUGH = ("PATH", "HOME", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR", "TMPDIR")

#: One read over the network. Long enough for a slow round trip, short enough
#: that an unattended campaign fails rather than hangs on a vault that stopped
#: answering.
DEFAULT_TIMEOUT = 30.0

#: The largest field this module will accept. A password is bytes and a private
#: key is kilobytes; anything at this size is a file somebody attached, and
#: reading it into a credential is a mistake worth refusing.
MAX_SECRET_BYTES = 64 * 1024

#: How much of a failed `op` run's own words to carry into a refusal that this
#: module could not classify. `op` produced no value in that case, so its stderr
#: is diagnosis and not contents -- but it is bounded and reached only by the
#: unclassified path, so the recognised refusals below stay this module's words.
STDERR_LIMIT = 500


class Refused(Exception):
    """A secret was not read, said in the vocabulary every command reports in.

    Carries a `Violation` rather than only a sentence so that a caller records
    the refusal the same way it records its own, and so the class of what went
    wrong survives into the process exit code.
    """

    def __init__(self, detail: str, *, code: str, source: str):
        super().__init__(detail)
        self.violation = Violation(code=code, source=source, detail=detail)


@dataclass(frozen=True)
class Reference:
    """Where one secret lives: an authorised vault, an item, and one field.

    Parsed rather than passed through, because the vault segment is the whole
    authorisation boundary and a string nobody has taken apart cannot be checked
    against it. The check is in `__post_init__` and not in `parse`, so that the
    boundary is a property of the type: there is no way to hand `read` a
    reference into an unauthorised vault, including by constructing one
    directly, and enforcement does not rest on every caller remembering which
    constructor is the safe one.
    """

    vault: str
    item: str
    field: str
    section: str | None = None

    def __post_init__(self) -> None:
        if self.vault not in AUTHORISED:
            # Before `op` is ever invoked, and this is the point of the module.
            # Both the item and its vault are named because an operator has to
            # know which reference to correct; nothing was read, so there are no
            # contents to name.
            raise Refused(
                f"{self.item[:64]!r} is in {self.vault[:64]!r}, which is not a vault this "
                f"harness may read; the authorised vaults are "
                f"{', '.join(sorted(AUTHORISED.values()))}",
                code=INVALID_CONFIGURATION,
                source="vault:unauthorised",
            )
        for name, segment in (("item", self.item), ("field", self.field), ("section", self.section)):
            if segment is None:
                continue
            if not segment.strip():
                raise Refused(
                    f"a secret reference has an empty {name}",
                    code=INVALID_CONFIGURATION,
                    source="vault:reference",
                )
            if segment.startswith("-") or any(character < " " for character in segment):
                # A leading dash would reach `op` as a flag rather than as part
                # of the one positional it takes, and a control character would
                # split what this module renders back into its own violations.
                raise Refused(
                    f"a secret reference has an unusable {name}",
                    code=INVALID_CONFIGURATION,
                    source="vault:reference",
                )

    @classmethod
    def looks_like(cls, value: object) -> bool:
        """Whether this is a reference at all, asked without refusing anything.

        Separate from `parse` so a document can be walked for references without
        every plain string in it becoming a violation.
        """
        return isinstance(value, str) and value.startswith(SCHEME)

    @classmethod
    def parse(cls, text: str) -> Reference:
        """One `op://vault/item[/section]/field`, or a refusal saying why not.

        Splitting only. What makes a reference usable is `__post_init__`'s
        business, so that a reference which never came through here is held to
        the same rules.

        Nothing here echoes the text it was given. A caller that passed a
        plaintext credential by mistake has made one error, and quoting it into
        a violation that is rendered, logged and stored would turn that into a
        second and more permanent one.
        """
        if not text.startswith(SCHEME):
            raise Refused(
                f"a secret reference must begin with {SCHEME}",
                code=INVALID_CONFIGURATION,
                source="vault:reference",
            )
        body = text[len(SCHEME) :]
        if "?" in body:
            raise Refused(
                "a secret reference may not carry a query parameter",
                code=INVALID_CONFIGURATION,
                source="vault:reference",
            )
        parts = body.split("/")
        if len(parts) not in (3, 4):
            raise Refused(
                f"a secret reference is {SCHEME}<vault>/<item>[/<section>]/<field>",
                code=INVALID_CONFIGURATION,
                source="vault:reference",
            )
        vault, item, *rest = parts
        return cls(
            vault=vault,
            item=item,
            field=rest[-1],
            section=rest[0] if len(rest) == 2 else None,
        )

    def __str__(self) -> str:
        middle = f"{self.item}/{self.section}" if self.section is not None else self.item
        return f"{SCHEME}{self.vault}/{middle}/{self.field}"


class Secret:
    """A value out of the vault, wrapped for as far as it travels wrapped.

    Everything about it is a barrier between the value and the places a string
    ends up on its own. It does not render -- `repr`, `str` and `format` all give
    the reference back -- it has no attribute dictionary to walk, it answers no
    state to reflect over, it refuses to be copied or pickled, and `json.dumps`
    cannot serialise it. So a secret
    interpolated into a log line, an event payload or an exception message is a
    reference, and reaching the value at all means writing `reveal()`.

    What this is not is a container the credential lives in. A credential has to
    become a string to be sealed, so both callers reveal it within a line or two
    and it is a plain `str` from there to the seal. The barrier is on the way
    out of this module, where a value crosses code that has no idea it is
    holding one; past `reveal()` the protection is that the window is short and
    that everything in it was read for that.
    """

    __slots__ = ("_value", "reference")

    def __init__(self, value: str, reference: Reference):
        self._value = value
        self.reference = reference

    def reveal(self) -> str:
        """The value. Every call site of this is a place worth reading twice."""
        return self._value

    def __repr__(self) -> str:
        return f"<Secret {self.reference}>"

    __str__ = __repr__

    def __format__(self, specification: str) -> str:
        return repr(self)

    def __getstate__(self):
        # `__slots__` leaves no `__dict__`, but since 3.11 the inherited
        # `object.__getstate__` reads the slots and answers the value anyway.
        # `__reduce__` below already refuses every ordinary serialiser; this
        # closes the one door reflection can still open by hand.
        raise TypeError("a Secret answers no state")

    def __reduce__(self):
        raise TypeError("a Secret is not copied, pickled or serialised")


def read(
    reference: Reference | str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    environ: Mapping[str, str] | None = None,
) -> Secret:
    """Read one field out of one authorised vault.

    The reference travels as the child's single positional argument and the
    credential travels in its environment, which is the same split `rk db dump`
    makes for the same reason: an argument vector is world-readable in `/proc`
    and an environment is not.
    """
    target = reference if isinstance(reference, Reference) else Reference.parse(reference)
    binary = shutil.which(BINARY)
    if binary is None:
        raise Refused(
            f"{BINARY} is not on PATH; install the 1Password CLI to read engagement secrets",
            code=MISSING_DEPENDENCY,
            source=f"runtime:program:{BINARY}",
        )
    completed = child.run(
        binary,
        ["read", "--no-newline", str(target)],
        environment=_environment(dict(os.environ if environ is None else environ)),
        timeout=timeout,
    )
    if isinstance(completed, str):
        # It never ran or never finished, so there is no stderr to classify and
        # nothing about the reference is in question.
        raise Refused(completed, code=VAULT_UNREADABLE, source="vault:op")
    if completed.returncode != 0:
        raise _refusal(completed.stderr, target)
    value = completed.stdout
    if not value:
        raise Refused(
            f"{target} is empty",
            code=INVALID_CONFIGURATION,
            source="vault:empty_field",
        )
    if len(value.encode("utf-8", "surrogatepass")) > MAX_SECRET_BYTES:
        raise Refused(
            f"{target} is larger than {MAX_SECRET_BYTES} bytes; that is a file and not a credential",
            code=INVALID_CONFIGURATION,
            source="vault:oversized_field",
        )
    return Secret(value, target)


def resolve(
    document: object,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    environ: Mapping[str, str] | None = None,
) -> tuple[object, int]:
    """Return one document with every secret reference in it replaced by its value.

    This is how a credential reaches the harness without ever being written
    down: the operator's material file holds references where the values would
    have been, and the values exist only between this call and the seal.

    A string is a reference or it is not; nothing is substituted inside one. So
    a header value is stored in the vault as `Bearer eyJ...` and a cookie as the
    whole `session=...; Path=/; Secure` line, rather than as the token with a
    template around it. The cost is one awkward field per credential and what it
    buys is that there is no parser here deciding where a reference ends inside
    arbitrary header text, and no credential that happens to contain `op://` can
    make this function read anything.

    Keys are left alone and only values are resolved -- a key is structure, and
    a document whose shape depends on a vault is one nobody can read. Repeats
    are read once, because a service account has an hourly budget and one
    material file naming the same field for two origins should spend one of it.
    """
    reads: dict[str, str] = {}
    resolved = 0

    def walk(node: object) -> object:
        nonlocal resolved
        if isinstance(node, dict):
            return {key: walk(value) for key, value in node.items()}
        if isinstance(node, list):
            return [walk(value) for value in node]
        if not Reference.looks_like(node):
            return node
        text = str(node)
        if text not in reads:
            reads[text] = read(text, timeout=timeout, environ=environ).reveal()
        resolved += 1
        return reads[text]

    return walk(document), resolved


def _environment(environ: dict[str, str]) -> dict[str, str]:
    """The child's whole environment, credential included.

    Three authentication paths, in the order an unattended run should prefer
    them: a token already exported, a token on disk, and -- when neither is
    there -- whatever local `op` session or desktop app the operator has. The
    last one is not refused in advance even though it cannot work on a headless
    host, because refusing it here would be this module deciding that a machine
    with a desktop app has no way to authenticate. `op` knows better than that,
    and says so in words `_refusal` turns into `vault:locked`.
    """
    carried = {name: environ[name] for name in PASSED_THROUGH if name in environ}
    carried.update({name: value for name, value in environ.items() if name.startswith("OP_")})
    if carried.get(TOKEN_VARIABLE):
        return carried
    given = environ.get(TOKEN_PATH_VARIABLE)
    path = Path(given).expanduser() if given else DEFAULT_TOKEN_PATH.expanduser()
    token = _token(path, explicit=given is not None)
    if token is not None:
        carried[TOKEN_VARIABLE] = token
    return carried


def _token(path: Path, *, explicit: bool) -> str | None:
    """The service account token on disk, if there is a usable one.

    A path the operator named is required to work: `None` there would silently
    fall through to whichever session the machine happens to have, which is the
    opposite of what naming a file means. The default path is allowed to be
    absent, because a machine with a desktop app has no reason to have one.
    """
    source = f"environment:{TOKEN_PATH_VARIABLE}" if explicit else f"file:{path}"
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        if explicit:
            raise Refused(
                f"{path} does not exist",
                code=INVALID_CONFIGURATION,
                source=source,
            ) from None
        return None
    except OSError as error:
        raise Refused(
            f"{path} cannot be read: {error.strerror or error}",
            code=INVALID_CONFIGURATION,
            source=source,
        ) from None
    if mode & 0o077:
        # Refused rather than repaired. A token that has been group-readable is
        # a token that may already have been read, and quietly narrowing the
        # mode would hide that from the one person who can rotate it.
        raise Refused(
            f"{path} is readable beyond its owner (mode {mode & 0o777:04o}); "
            "rotate the token and store it at 0600",
            code=INVALID_CONFIGURATION,
            source=source,
        )
    try:
        token = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as error:
        raise Refused(
            f"{path} cannot be read: {error}",
            code=INVALID_CONFIGURATION,
            source=source,
        ) from None
    if not token:
        raise Refused(
            f"{path} holds no token",
            code=INVALID_CONFIGURATION,
            source=source,
        )
    return token


class Sign(NamedTuple):
    """One thing `op` says, and what this module reports when it says it."""

    #: A substring of `op`'s stderr, not a pattern. It is matched against one
    #: whitespace-collapsed line, so it must not span what was two lines.
    said: str
    code: str
    source: str
    #: Completes the sentence "<reference> ...", so it reads as a fact about
    #: that reference rather than as a message that happens to mention one.
    detail: str


#: One sentence for both of the ways `op` says nothing authenticated it, because
#: an operator who reads either has exactly the same thing to go and do.
_UNAUTHENTICATED = (
    f"could not be read: nothing authenticated `{BINARY}`. Export {TOKEN_VARIABLE}, "
    f"or put a service account token at {DEFAULT_TOKEN_PATH}"
)

#: What `op` says, and what each of its answers means here. Matched on its own
#: words because it exits `1` for most of them, so the status alone separates
#: nothing; measured against `op` 2.39.0 on this host rather than taken from its
#: documentation, which does not specify any of these strings. An answer none of
#: these match is still refused -- as `vault:op`, carrying `op`'s own words --
#: so a message that changes in a later release costs precision and not safety.
SIGNS = (
    Sign("isn't an item", INVALID_CONFIGURATION, "vault:no_such_item", "names no item in that vault"),
    Sign(
        "does not have a field",
        INVALID_CONFIGURATION,
        "vault:no_such_field",
        "names no field on that item",
    ),
    Sign("not currently signed in", VAULT_UNREADABLE, "vault:locked", _UNAUTHENTICATED),
    Sign("could not find session token", VAULT_UNREADABLE, "vault:locked", _UNAUTHENTICATED),
    Sign(
        "aren't authorized",
        VAULT_UNREADABLE,
        "vault:forbidden",
        "is in a vault this harness is authorised to read and the 1Password account is not; "
        "grant the service account read access to it",
    ),
    Sign(
        "rate limit",
        VAULT_UNREADABLE,
        "vault:rate_limited",
        "could not be read: the service account is over its rate limit",
    ),
)


def _refusal(stderr: str, reference: Reference) -> Refused:
    """Why one `op` run failed, as a violation naming the reference and no value."""
    said = child.collapse(stderr)
    for sign in SIGNS:
        if sign.said in said:
            return Refused(f"{reference} {sign.detail}", code=sign.code, source=sign.source)
    return Refused(
        f"{reference} could not be read: {child.tail(stderr, limit=STDERR_LIMIT)}",
        code=VAULT_UNREADABLE,
        source="vault:op",
    )
