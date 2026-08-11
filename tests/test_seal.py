"""Authenticated encryption for wire artifacts: everything answerable without a server.

The whole of ticket 07's first criterion is decidable here, because the
construction is over bytes and a key and nothing else. Four properties carry it.

`hkdf` is the derivation, and it is held against RFC 5869's own test vectors
rather than against itself -- a derivation tested by re-deriving it agrees with
any implementation, including a broken one.

`seal` and `unseal` are the round trip, and the interesting cases are the ones
where the answer must be nothing at all: a flipped byte anywhere in the
envelope, a different key, a different associated data string. Each of those is
one of ticket 07's failure modes -- tampered ciphertext, wrong key material, a
cross-Program reference -- and each must raise rather than return a shortened or
garbled plaintext. There is no partial answer to give.

`Root` is the key material, and what is tested is what it refuses: a file that
is not there, a file another account can read, a file too short to be a key. The
root check is the one derived value that is safe to store, and it is what makes
"wrong key material" a fact the runtime can establish before it touches a single
byte of ciphertext.

The fourth is an absence: no function here takes a connection, and the secret
never leaves the process in any form a report could print.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import unittest
from pathlib import Path
from unittest import mock

from redkraken import seal
from tests.fixtures import scratch


#: A body long enough to cross several keystream blocks, so an off-by-one in the
#: counter shows up as a wrong answer rather than as a coincidence.
BODY = b"".join(f"wire line {number}\n".encode() for number in range(97))

PROGRAM = "0198b7a0-0000-7000-8000-000000000001"
OTHER = "0198b7a0-0000-7000-8000-000000000002"

#: RFC 5869 A.1, the SHA-256 basic case. Pinned bytes, not a recomputation.
RFC_IKM = bytes.fromhex("0b" * 22)
RFC_SALT = bytes.fromhex("000102030405060708090a0b0c")
RFC_INFO = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9")
RFC_OKM = bytes.fromhex(
    "3cb25f25faacd57a90434f64d0362f2a"
    "2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
    "34007208d5b887185865"
)


def key(seed: int = 1) -> bytes:
    return hashlib.sha256(f"key-{seed}".encode()).digest()


def written(data: bytes, mode: int = 0o600, name: str = "artifact.key") -> Path:
    """One key file, with the permissions the test is about."""
    path = scratch() / name
    path.write_bytes(data)
    path.chmod(mode)
    return path


class DerivationTest(unittest.TestCase):
    """HKDF, against the vectors that define it."""

    def test_rfc_5869_a1(self):
        self.assertEqual(
            seal.hkdf(RFC_IKM, salt=RFC_SALT, info=RFC_INFO, length=42), RFC_OKM
        )

    def test_a_different_info_derives_a_different_key(self):
        first = seal.hkdf(key(), salt=b"", info=b"one", length=32)
        second = seal.hkdf(key(), salt=b"", info=b"two", length=32)
        self.assertNotEqual(first, second)

    def test_a_different_salt_derives_a_different_key(self):
        first = seal.hkdf(key(), salt=b"a", info=b"one", length=32)
        second = seal.hkdf(key(), salt=b"b", info=b"one", length=32)
        self.assertNotEqual(first, second)

    def test_length_is_the_length_asked_for(self):
        for length in (1, 32, 33, 255 * 32):
            with self.subTest(length=length):
                self.assertEqual(len(seal.hkdf(key(), salt=b"", info=b"i", length=length)), length)

    def test_a_length_beyond_what_the_expansion_can_produce_is_refused(self):
        with self.assertRaises(ValueError):
            seal.hkdf(key(), salt=b"", info=b"i", length=255 * 32 + 1)


class RoundTripTest(unittest.TestCase):
    """What comes back is what went in, and only under the same three inputs."""

    def setUp(self):
        self.aad = seal.associated_data(program_id=PROGRAM, sha256=hashlib.sha256(BODY).hexdigest(), generation=1)

    def test_plaintext_survives_the_round_trip(self):
        sealed = seal.seal(key(), BODY, aad=self.aad)
        self.assertEqual(seal.unseal(key(), sealed, aad=self.aad), BODY)

    def test_an_empty_plaintext_survives_the_round_trip(self):
        sealed = seal.seal(key(), b"", aad=self.aad)
        self.assertEqual(seal.unseal(key(), sealed, aad=self.aad), b"")

    def test_the_ciphertext_is_the_length_of_the_plaintext(self):
        self.assertEqual(len(seal.seal(key(), BODY, aad=self.aad).ciphertext), len(BODY))

    def test_the_plaintext_does_not_appear_in_the_envelope(self):
        marker = b"RK-SYNTHETIC-CREDENTIAL-3f9a"
        sealed = seal.seal(key(), b"Authorization: Bearer " + marker, aad=self.aad)
        self.assertNotIn(marker, sealed.encode())

    def test_sealing_the_same_plaintext_twice_produces_different_bytes(self):
        # A fresh nonce per seal. Equal ciphertexts would say the two bodies are
        # equal to anyone holding the store and no key at all.
        first = seal.seal(key(), BODY, aad=self.aad)
        second = seal.seal(key(), BODY, aad=self.aad)
        self.assertNotEqual(first.nonce, second.nonce)
        self.assertNotEqual(first.ciphertext, second.ciphertext)

    def test_the_algorithm_version_travels_with_the_ciphertext(self):
        self.assertEqual(seal.seal(key(), BODY, aad=self.aad).alg, seal.ALG)

    def test_the_envelope_survives_encoding(self):
        sealed = seal.seal(key(), BODY, aad=self.aad)
        self.assertEqual(seal.Sealed.decode(sealed.encode()), sealed)

    def test_an_envelope_answers_whether_a_recorded_description_is_of_itself(self):
        # The question both the gate and `rk artifact open` ask before they trust
        # a row: does this file's own header say what the database says it says.
        sealed = seal.seal(key(), BODY, aad=self.aad)
        other = seal.seal(key(), BODY, aad=self.aad)

        self.assertTrue(sealed.describes(sealed.alg, sealed.nonce.hex()))
        self.assertFalse(sealed.describes(sealed.alg, other.nonce.hex()))
        self.assertFalse(sealed.describes("rk-something-else-v1", sealed.nonce.hex()))

    def test_a_description_is_compared_as_the_database_renders_it(self):
        # The row arrives as whatever the driver made of `text` and
        # `encode(nonce, 'hex')`, so the comparison is over the rendering rather
        # than over a type the caller had to convert first.
        sealed = seal.seal(key(), BODY, aad=self.aad)

        self.assertTrue(sealed.describes(sealed.alg, sealed.nonce.hex()))
        self.assertFalse(sealed.describes(sealed.alg, sealed.nonce))


class FailClosedTest(unittest.TestCase):
    """Ticket 07's three failure modes, each answering with nothing."""

    def setUp(self):
        self.sha256 = hashlib.sha256(BODY).hexdigest()
        self.aad = seal.associated_data(program_id=PROGRAM, sha256=self.sha256, generation=1)
        self.sealed = seal.seal(key(), BODY, aad=self.aad)

    def test_a_flipped_ciphertext_byte_is_refused(self):
        damaged = bytearray(self.sealed.ciphertext)
        damaged[len(damaged) // 2] ^= 0x01
        with self.assertRaises(seal.Tampered):
            seal.unseal(
                key(),
                seal.Sealed(self.sealed.alg, self.sealed.nonce, self.sealed.tag, bytes(damaged)),
                aad=self.aad,
            )

    def test_a_flipped_nonce_byte_is_refused(self):
        damaged = bytearray(self.sealed.nonce)
        damaged[0] ^= 0x01
        with self.assertRaises(seal.Tampered):
            seal.unseal(
                key(),
                seal.Sealed(self.sealed.alg, bytes(damaged), self.sealed.tag, self.sealed.ciphertext),
                aad=self.aad,
            )

    def test_a_flipped_tag_byte_is_refused(self):
        damaged = bytearray(self.sealed.tag)
        damaged[-1] ^= 0x01
        with self.assertRaises(seal.Tampered):
            seal.unseal(
                key(),
                seal.Sealed(self.sealed.alg, self.sealed.nonce, bytes(damaged), self.sealed.ciphertext),
                aad=self.aad,
            )

    def test_every_single_bit_of_the_envelope_is_covered(self):
        # One flip per byte position rather than per bit: the tag is over the
        # whole envelope, so a position nobody covers shows up here as a
        # successful open rather than as a weaker guarantee nobody notices.
        blob = self.sealed.encode()
        for position in range(len(blob)):
            damaged = bytearray(blob)
            damaged[position] ^= 0x80
            with self.subTest(position=position):
                with self.assertRaises(seal.Tampered):
                    seal.unseal(key(), seal.Sealed.decode(bytes(damaged)), aad=self.aad)

    def test_a_truncated_envelope_is_refused(self):
        blob = self.sealed.encode()
        with self.assertRaises(seal.Tampered):
            seal.Sealed.decode(blob[:-1])

    def test_an_envelope_that_is_not_one_is_refused(self):
        with self.assertRaises(seal.Tampered):
            seal.Sealed.decode(b"this is a plaintext body, not an envelope")

    def test_wrong_key_material_is_refused(self):
        with self.assertRaises(seal.Tampered):
            seal.unseal(key(2), self.sealed, aad=self.aad)

    def test_another_programs_associated_data_is_refused(self):
        other = seal.associated_data(program_id=OTHER, sha256=self.sha256, generation=1)
        with self.assertRaises(seal.Tampered):
            seal.unseal(key(), self.sealed, aad=other)

    def test_another_artifacts_associated_data_is_refused(self):
        other = seal.associated_data(
            program_id=PROGRAM, sha256=hashlib.sha256(b"other").hexdigest(), generation=1
        )
        with self.assertRaises(seal.Tampered):
            seal.unseal(key(), self.sealed, aad=other)

    def test_another_generations_associated_data_is_refused(self):
        other = seal.associated_data(program_id=PROGRAM, sha256=self.sha256, generation=2)
        with self.assertRaises(seal.Tampered):
            seal.unseal(key(), self.sealed, aad=other)

    def test_an_unknown_algorithm_is_refused_before_any_decryption(self):
        renamed = seal.Sealed(
            "rk-something-else-v9", self.sealed.nonce, self.sealed.tag, self.sealed.ciphertext
        )
        with self.assertRaises(seal.Tampered):
            seal.unseal(key(), renamed, aad=self.aad)


class RootTest(unittest.TestCase):
    """The key material: where it comes from, and what it refuses."""

    def test_a_root_is_read_from_the_file_the_variable_names(self):
        path = written(b"x" * 64)
        with mock.patch.dict(os.environ, {seal.KEY_VARIABLE: str(path)}):
            self.assertEqual(seal.key_from_environment(), path)

    def test_an_argument_outranks_the_variable(self):
        path = written(b"x" * 64)
        with mock.patch.dict(os.environ, {seal.KEY_VARIABLE: "/nowhere"}):
            self.assertEqual(seal.key_from_environment(path), path)

    def test_no_argument_and_no_variable_is_nothing(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(seal.key_from_environment())

    def test_a_key_file_that_is_not_there_is_refused(self):
        with self.assertRaises(seal.Unusable):
            seal.load_root(scratch() / "absent.key")

    def test_a_key_file_another_account_can_read_is_refused(self):
        with self.assertRaises(seal.Unusable) as refusal:
            seal.load_root(written(b"x" * 64, mode=0o644))
        self.assertIn("readable", str(refusal.exception))

    def test_a_key_file_too_short_to_be_a_key_is_refused(self):
        with self.assertRaises(seal.Unusable) as refusal:
            seal.load_root(written(b"short"))
        self.assertIn("32", str(refusal.exception))

    def test_a_directory_is_refused(self):
        with self.assertRaises(seal.Unusable):
            seal.load_root(scratch())

    def test_a_trailing_newline_is_not_key_material(self):
        # An operator writing a key with `echo` gets a newline they did not
        # intend. Treating it as key material would make the same secret two
        # different keys depending on how it was written down.
        one = seal.load_root(written(b"a" * 64))
        two = seal.load_root(written(b"a" * 64 + b"\n"))
        self.assertEqual(one.check(b"s" * 32, generation=1), two.check(b"s" * 32, generation=1))

    def test_the_root_check_is_the_documented_derivation(self):
        root = seal.load_root(written(b"a" * 64))
        salt = b"s" * 32
        kek = seal.hkdf(b"a" * 64, salt=salt, info=b"rk2/kek/v1|gen=1", length=32)
        self.assertEqual(
            root.check(salt, generation=1),
            hmac.new(kek, b"rk2/rootcheck/v1", hashlib.sha256).digest()[:16],
        )

    def test_the_root_check_is_sixteen_bytes(self):
        root = seal.load_root(written(b"a" * 64))
        self.assertEqual(len(root.check(b"s" * 32, generation=1)), 16)

    def test_a_different_root_produces_a_different_check(self):
        salt = b"s" * 32
        first = seal.load_root(written(b"a" * 64)).check(salt, generation=1)
        second = seal.load_root(written(b"b" * 64)).check(salt, generation=1)
        self.assertNotEqual(first, second)

    def test_a_different_generation_produces_a_different_check(self):
        root = seal.load_root(written(b"a" * 64))
        salt = b"s" * 32
        self.assertNotEqual(root.check(salt, generation=1), root.check(salt, generation=2))

    def test_each_program_gets_a_key_of_its_own(self):
        root = seal.load_root(written(b"a" * 64))
        salt = b"s" * 32
        self.assertNotEqual(
            root.program_key(salt, generation=1, program_id=PROGRAM),
            root.program_key(salt, generation=1, program_id=OTHER),
        )

    def test_a_program_key_is_the_length_of_a_key(self):
        root = seal.load_root(written(b"a" * 64))
        self.assertEqual(
            len(root.program_key(b"s" * 32, generation=1, program_id=PROGRAM)), seal.KEY_BYTES
        )

    def test_each_identity_gets_a_key_of_its_own_inside_one_program(self):
        root = seal.load_root(written(b"a" * 64))
        salt = b"s" * 32

        first = root.identity_key(
            salt,
            generation=1,
            program_id=PROGRAM,
            identity_id="11111111-1111-1111-1111-111111111111",
        )
        second = root.identity_key(
            salt,
            generation=1,
            program_id=PROGRAM,
            identity_id="22222222-2222-2222-2222-222222222222",
        )

        self.assertEqual(seal.KEY_BYTES, len(first))
        self.assertNotEqual(first, second)

    def test_an_identity_slot_is_bound_to_its_identity_and_revision(self):
        root = seal.load_root(written(b"a" * 64))
        identity_id = "11111111-1111-1111-1111-111111111111"
        key = root.identity_key(
            b"s" * 32, generation=1, program_id=PROGRAM, identity_id=identity_id
        )
        aad = seal.identity_associated_data(
            program_id=PROGRAM, identity_id=identity_id, generation=1, revision=4
        )
        encrypted = seal.seal(key, BODY, aad=aad)

        with self.assertRaises(seal.Tampered):
            seal.unseal(
                key,
                encrypted,
                aad=seal.identity_associated_data(
                    program_id=PROGRAM,
                    identity_id=identity_id,
                    generation=1,
                    revision=5,
                ),
            )

    def test_the_audit_fingerprint_is_four_keyed_bytes(self):
        root = seal.load_root(written(b"a" * 64))
        fingerprint = root.fingerprint(BODY)
        self.assertEqual(len(fingerprint), 4)
        self.assertNotEqual(fingerprint, hashlib.sha256(BODY).digest()[:4])

    def test_the_audit_fingerprint_answers_whether_two_values_are_one(self):
        root = seal.load_root(written(b"a" * 64))
        self.assertEqual(root.fingerprint(BODY), root.fingerprint(BODY))
        self.assertNotEqual(root.fingerprint(BODY), root.fingerprint(BODY + b"!"))

    def test_a_salt_is_the_length_the_schema_requires(self):
        self.assertEqual(len(seal.new_salt()), 32)

    def test_two_salts_are_not_one(self):
        self.assertNotEqual(seal.new_salt(), seal.new_salt())

    def test_the_secret_is_not_in_the_repr(self):
        # A Root travels through report-building code. A dataclass repr that
        # carried the secret would put it in the first traceback anything logs.
        root = seal.load_root(written(b"sixty-four bytes of key material" * 2))
        self.assertNotIn("key material", repr(root))


class ContainmentTest(unittest.TestCase):
    """What this module is not allowed to know about."""

    def test_nothing_here_reaches_a_database(self):
        source = Path(seal.__file__).read_text(encoding="utf-8")
        for forbidden in ("import psycopg", "from redkraken import pg", "connection"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":  # pragma: no cover - parity with the other modules
    unittest.main()
