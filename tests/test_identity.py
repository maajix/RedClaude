import unittest

from redkraken import identity


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


if __name__ == "__main__":
    unittest.main()
