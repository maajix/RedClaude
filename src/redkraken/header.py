"""The value behind a Program's required-header declaration, on its way in.

`[[required_header]]` states a name the agent may read and a `slot://` reference
that resolves to a value the agent may not. This module is the one place that
turns an operator's file into the authenticated ciphertext the door opens: it
holds the plaintext for the length of one command, seals it under a key derived
from the installation root, and returns nothing that could reconstruct it.

The value arrives as a file rather than an argument on purpose. An argument is in
the process table for every other user on the machine, and a bounty identifier
that leaks is one an unrelated program can wear.
"""

from __future__ import annotations

import hmac
import json
from pathlib import Path

from redkraken import config, migrate, pg, program, seal
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, report
from redkraken.store import digest


COMMAND = "header provision"

#: Long enough for a signed token, short enough that a file handed to this
#: command by mistake is refused rather than sealed.
MAX_VALUE_BYTES = 4096

KEYING = (
    "SELECT name, revision, generation, salt_hex, root_check_hex, audit_id"
    "  FROM header_slot_keying($1::uuid, $2, $3::bytea, $4::bytea)"
)
CONFIRM_ROOTCHECK = "SELECT confirm_header_root_check($1::uuid, $2, $3::uuid, $4)"
PROVISION = "SELECT provision_header_slot($1::uuid, $2, $3::bigint, $4::jsonb)"


def provision(
    runtime: pg.Settings | None,
    configuration_path: Path,
    name: str,
    value_path: Path,
    *,
    root_secret: seal.Root | None = None,
    key_path: Path | None = None,
) -> Report:
    """Seal one operator-provided header value into this Program's slot.

    The same shape as `identity.provision`, because it is the same job on the
    same material: a control-side command that holds a plaintext for as long as
    it takes to encrypt it, and reports a revision and a byte count.
    """
    ledger = Ledger()
    facts: dict[str, object] = {"header": None, "program_id": None}

    configuration, refusals = config.load(Path(configuration_path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return report(COMMAND, ledger, **facts)
    slug = str(configuration.document["program"]["name"])
    declared = [
        str(entry["name"]) for entry in configuration.document.get("required_header", ())
    ]
    if not any(spelling.lower() == name.lower() for spelling in declared):
        ledger.fail(
            "header",
            f"{slug} does not require a header named {name}; it requires "
            + (", ".join(declared) if declared else "none"),
            code=INVALID_CONFIGURATION,
            source="argument:--header",
        )
        return report(COMMAND, ledger, **facts)

    value = _value(ledger, Path(value_path))
    if value is None:
        return report(COMMAND, ledger, **facts)

    root = root_secret
    if root is None:
        location = seal.key_from_environment(key_path)
        if location is None:
            ledger.fail(
                "header_key",
                f"no key was provided; pass --key or set {seal.KEY_VARIABLE}",
                code=INVALID_CONFIGURATION,
                source=f"environment:{seal.KEY_VARIABLE}",
            )
            return report(COMMAND, ledger, **facts)
        try:
            root = seal.load_root(location)
        except (OSError, seal.Unusable) as error:
            ledger.fail(
                "header_key",
                f"the key cannot be used: {error}",
                code=INVALID_CONFIGURATION,
                source="argument:--key",
            )
            return report(COMMAND, ledger, **facts)

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return report(COMMAND, ledger, **facts)
    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return report(COMMAND, ledger, **facts)
        program_id = program.resolve(ledger, connection, slug)
        if program_id is None:
            return report(COMMAND, ledger, **facts)
        facts["program_id"] = program_id
        connection.execute("SELECT set_config('rk2.program_id', $1, false)", (program_id,))

        proposed = seal.new_salt()
        try:
            rows = connection.execute(
                KEYING,
                (program_id, name, proposed, root.check(proposed, generation=1)),
            ).rows
        except pg.DatabaseError as error:
            ledger.fail(
                "header",
                f"the configured header did not resolve to a compiled declaration: {error}",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return report(COMMAND, ledger, **facts)
        if not rows:
            ledger.fail(
                "header",
                "the configured header did not resolve to a compiled declaration",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return report(COMMAND, ledger, **facts)
        found, current, generation, salt_hex, root_check_hex, audit_id = rows[0]

        salt = bytes.fromhex(str(salt_hex))
        number = int(generation)
        matched = hmac.compare_digest(
            root.check(salt, generation=number), bytes.fromhex(str(root_check_hex))
        )
        connection.execute(
            CONFIRM_ROOTCHECK,
            (program_id, str(found), str(audit_id), "ok" if matched else "denied"),
        )
        if not matched:
            ledger.fail(
                "header_key",
                "the key does not match this installation",
                code=INVALID_CONFIGURATION,
                source="program_header_slots",
            )
            return report(COMMAND, ledger, **facts)

        revision = int(current) + 1
        sealed = seal.seal(
            root.header_key(
                salt, generation=number, program_id=program_id, name=str(found)
            ),
            value,
            aad=seal.header_associated_data(
                program_id=program_id,
                name=str(found),
                generation=number,
                revision=revision,
            ),
        )
        envelope = sealed.encode()
        state = {
            "alg": sealed.alg,
            "nonce_hex": sealed.nonce.hex(),
            "kek_gen": number,
            "envelope_hex": envelope.hex(),
            "ciphertext_sha256": digest(envelope),
            "byte_size": len(value),
            "value_fpr_hex": root.fingerprint(value).hex(),
            "revision": revision,
        }
        try:
            written = int(
                connection.execute(
                    PROVISION,
                    (
                        program_id,
                        str(found),
                        int(current),
                        json.dumps(state, separators=(",", ":")),
                    ),
                ).scalar()
            )
        except pg.DatabaseError as error:
            ledger.fail(
                "header",
                f"the header value was refused: {error}",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return report(COMMAND, ledger, **facts)

    facts["header"] = {"name": str(found), "revision": written, "byte_size": len(value)}
    ledger.hold(
        "header",
        f"{found} revision {written}: {len(value)} byte(s) sealed under key generation {number}",
    )
    return report(COMMAND, ledger, **facts)


def _value(ledger: Ledger, source: Path) -> bytes | None:
    """The header value the operator's file holds, or a refusal naming why not.

    One trailing newline is removed, because every editor writes one and a
    Program whose identifier ends in `\\n` would send a header the target reads
    as two. Any other control character is a refusal rather than a strip: a value
    that has to be repaired is a value nobody checked, and the door is not the
    place to find that out.
    """
    try:
        raw = source.read_bytes()
    except OSError as error:
        ledger.fail(
            "header_value",
            f"the value cannot be read: {error}",
            code=INVALID_CONFIGURATION,
            source="argument:--from",
        )
        return None
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if raw.endswith(b"\r"):
        raw = raw[:-1]
    if not raw:
        ledger.fail(
            "header_value",
            "the value is empty; a header a Program requires cannot be nothing",
            code=INVALID_CONFIGURATION,
            source="argument:--from",
        )
        return None
    if len(raw) > MAX_VALUE_BYTES:
        ledger.fail(
            "header_value",
            f"the value is {len(raw)} bytes; a header value stops at {MAX_VALUE_BYTES}",
            code=INVALID_CONFIGURATION,
            source="argument:--from",
        )
        return None
    if any(byte < 0x20 or byte == 0x7F for byte in raw):
        ledger.fail(
            "header_value",
            "the value carries a control character; it is not one HTTP header value",
            code=INVALID_CONFIGURATION,
            source="argument:--from",
        )
        return None
    return raw
