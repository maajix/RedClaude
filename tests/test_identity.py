import json
import unittest
from pathlib import Path
from unittest import mock

from redkraken import identity, migrate, vault
from redkraken.outcome import INVALID_CONFIGURATION
from tests.fixtures import VALID, write


class SessionTest(unittest.TestCase):
    def session(self) -> identity.Session:
        return identity.Session.from_material(
            {
                "schema_version": 1,
                "origins": [
                    {
                        "url": "https://app.example.com/",
                        "headers": [
                            {"name": "Authorization", "value": "Bearer control-owned"}
                        ],
                        "cookies": ["initial=one; Path=/; Secure; HttpOnly"],
                    }
                ],
            }
        )

    def test_the_identity_owns_credential_headers_only_on_its_exact_origin(self):
        session = self.session()

        injected = session.inject(
            "https://app.example.com/notes",
            [("Authorization", "Bearer agent-authored"), ("Cookie", "agent=one")],
        )
        elsewhere = session.inject(
            "https://other.example.com/notes", [("Accept", "application/json")]
        )

        self.assertEqual(
            ["Bearer control-owned"],
            [value for name, value in injected if name.lower() == "authorization"],
        )
        self.assertEqual(
            ["initial=one"],
            [value for name, value in injected if name.lower() == "cookie"],
        )
        self.assertEqual([("Accept", "application/json")], elsewhere)

    def test_target_cookies_survive_an_encrypted_slot_round_trip(self):
        session = self.session()

        changed = session.capture(
            "https://app.example.com/notes",
            [("Set-Cookie", "session=two; Path=/; Secure; HttpOnly")],
        )
        reopened = identity.Session.decode(session.encode())
        injected = reopened.inject("https://app.example.com/next", [])

        self.assertTrue(changed)
        self.assertEqual(
            ["initial=one; session=two"],
            [value for name, value in injected if name.lower() == "cookie"],
        )

    def test_proxy_owned_headers_cannot_be_provisioned(self):
        for name in ("Cookie", "Host", "Proxy-Authorization", "X-RedKraken-Program"):
            with self.subTest(name=name), self.assertRaises(identity.Invalid):
                identity.Session.from_material(
                    {
                        "schema_version": 1,
                        "origins": [
                            {
                                "url": "https://app.example.com/",
                                "headers": [{"name": name, "value": "not accepted"}],
                                "cookies": [],
                            }
                        ],
                    }
                )

    def test_a_client_certificate_round_trips_only_inside_the_identity(self):
        certificate = "-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----\n"
        private_key = "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----\n"
        session = identity.Session.from_material(
            {
                "schema_version": 1,
                "origins": [
                    {
                        "url": "https://app.example.com/",
                        "headers": [],
                        "cookies": [],
                        "client_certificate": {
                            "certificate_pem": certificate,
                            "private_key_pem": private_key,
                            "password": "fixture-password",
                        },
                    }
                ],
            }
        )

        reopened = identity.Session.decode(session.encode())
        credential = reopened.client_certificate("https://app.example.com/orders")

        self.assertIsNotNone(credential)
        self.assertEqual(certificate, credential.certificate_pem)
        self.assertEqual(private_key, credential.private_key_pem)
        self.assertEqual("fixture-password", credential.password)
        self.assertIsNone(reopened.client_certificate("https://other.example.com/"))

    def test_a_client_key_exists_as_a_private_temporary_only_while_tls_loads_it(self):
        credential = identity.ClientCertificate(
            "-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----\n",
            "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----\n",
            "fixture-password",
        )

        class Context:
            path: Path | None = None
            material: str | None = None
            password: str | None = None

            def load_cert_chain(self, path: str, *, password: str | None = None) -> None:
                self.path = Path(path)
                self.material = self.path.read_text(encoding="utf-8")
                self.password = password

        context = Context()
        credential.install(context)

        self.assertIn("BEGIN CERTIFICATE", context.material)
        self.assertIn("BEGIN PRIVATE KEY", context.material)
        self.assertEqual("fixture-password", context.password)
        self.assertFalse(context.path.exists())

    def test_a_client_certificate_is_https_only_and_closed_schema(self):
        base = {
            "schema_version": 1,
            "origins": [
                {
                    "url": "http://app.example.com/",
                    "headers": [],
                    "cookies": [],
                    "client_certificate": {
                        "certificate_pem": "-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----\n",
                        "private_key_pem": "-----BEGIN PRIVATE KEY-----\ny\n-----END PRIVATE KEY-----\n",
                    },
                }
            ],
        }
        with self.assertRaises(identity.Invalid):
            identity.Session.from_material(base)

        base["origins"][0]["url"] = "https://app.example.com/"
        base["origins"][0]["client_certificate"]["unknown"] = "no"
        with self.assertRaises(identity.Invalid):
            identity.Session.from_material(base)

    def test_normalized_cookie_state_is_bounded_before_provisioning(self):
        material = {
            "schema_version": 1,
            "origins": [
                {
                    "url": "https://app.example.com/",
                    "headers": [],
                    "cookies": [f"cookie{index}=x" for index in range(6_000)],
                }
            ],
        }

        with self.assertRaisesRegex(identity.Invalid, "slot plaintext exceeds"):
            identity.Session.from_material(material)


#: One authorised reference, standing where a credential would have been.
REFERENCE = "op://4exeximtkfyxd2eywo3m7jpfwu/engagement/password"

#: What the vault gives back for it: the whole header value and not the token
#: alone, because a string is a reference or it is not and nothing is
#: substituted inside one.
CREDENTIAL = "Bearer RK-SYNTHETIC-CREDENTIAL-3f9a"

#: The reference as `vault.read` really returns it, taken apart. A `Secret`
#: holds a `Reference` and not the string one was spelled with, and a fixture
#: that handed it the string would be documenting a contract nothing has.
PARSED = vault.Reference.parse(REFERENCE)


class ProvisionedMaterialTest(unittest.TestCase):
    """Where a credential enters the harness, which is the one place it may.

    `rk identity provision` is the only caller of the vault, and the window is
    between parsing the operator's material and validating it. What is asserted
    here is that window's two properties: a reference becomes a value before the
    document is read as a document, and nothing the command reports afterwards
    holds the value it resolved.
    """

    def material(self, value: str) -> Path:
        document = {
            "schema_version": 1,
            "origins": [
                {
                    "url": "https://app.example.com/",
                    "headers": [{"name": "Authorization", "value": value}],
                    "cookies": [],
                }
            ],
        }
        return write(json.dumps(document), name="identity.json")

    def provision(self, path: Path):
        # Stopped at the database, which is everything after the window this
        # tests. `provision` reports the refused connection and returns.
        return identity.provision(None, write(VALID), "member", path)

    def test_a_reference_is_a_value_before_the_document_is_validated(self):
        # Before, so that every refusal below it names a position rather than a
        # value -- `origins[0].headers[0].value` and never what is in it.
        with mock.patch.object(vault, "read", return_value=vault.Secret(CREDENTIAL, PARSED)):
            with mock.patch.object(identity.Session, "from_material") as parsed:
                with mock.patch.object(migrate, "open_connection", return_value=None):
                    self.provision(self.material(REFERENCE))

        headers = parsed.call_args.args[0]["origins"][0]["headers"]
        self.assertEqual(CREDENTIAL, headers[0]["value"])

    def test_nothing_the_command_reports_carries_what_it_resolved(self):
        with mock.patch.object(vault, "read", return_value=vault.Secret(CREDENTIAL, PARSED)):
            with mock.patch.object(migrate, "open_connection", return_value=None):
                report = self.provision(self.material(REFERENCE))

        self.assertNotIn(CREDENTIAL, json.dumps(report.as_dict()))

    def test_a_vault_that_refuses_stops_the_command_before_the_database(self):
        refusal = vault.Refused(
            f"{REFERENCE} names no item in that vault",
            code=INVALID_CONFIGURATION,
            source="vault:no_such_item",
        )
        with mock.patch.object(vault, "read", side_effect=refusal):
            with mock.patch.object(migrate, "open_connection", side_effect=AssertionError("connected")):
                report = self.provision(self.material(REFERENCE))

        self.assertEqual(["vault:no_such_item"], [item.source for item in report.violations])

    def test_material_with_no_reference_in_it_never_asks_the_vault(self):
        # An operator who keeps their material on disk is not made to have a
        # 1Password account.
        with mock.patch.object(vault, "read", side_effect=AssertionError("read")):
            with mock.patch.object(migrate, "open_connection", return_value=None):
                report = self.provision(self.material("Bearer plain-token"))

        self.assertNotIn("vault", [item.source for item in report.violations])


if __name__ == "__main__":
    unittest.main()
