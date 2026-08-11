import sys
import unittest
from unittest import mock

from redkraken import config
from redkraken.outcome import INVALID_CONFIGURATION, MISSING_DEPENDENCY, UNSUPPORTED_VERSION
from tests.fixtures import VALID, scratch, write


#: The operator-visible wording of a refused path, written out here so that
#: changing it is a decision rather than a side effect.
PATH_SHAPE = (
    "must be a path prefix beginning with one forward slash, printable and free of .. segments"
)


def violations(text: str) -> list[tuple[str, str, str]]:
    configuration, found = config.load(write(text))
    if found:
        assert configuration is None, "a rejected configuration must not be returned"
    return [(violation.code, violation.source, violation.detail) for violation in found]


def sources(text: str) -> list[str]:
    return [source for _, source, _ in violations(text)]


class ValidConfigurationTest(unittest.TestCase):
    def test_valid_configuration_is_accepted_and_hashed(self):
        configuration, found = config.load(write(VALID))

        self.assertEqual((), found)
        self.assertEqual(1, configuration.schema_version)
        self.assertEqual(64, len(configuration.source_sha256))
        self.assertEqual(64, len(configuration.canonical_sha256))
        self.assertNotEqual(configuration.source_sha256, configuration.canonical_sha256)

    def test_absent_optional_sections_default_to_denial(self):
        configuration, found = config.load(write(
            "schema_version = 1\n"
            '[program]\nname = "acme-web"\n'
            "[budgets]\nrequests = 1\ntokens = 1\nconcurrency = 1\nburst = 1\nwindow_seconds = 1\n"
            '[[scope.include]]\nhost = "app.example.com"\n'
            'ports = [443]\nprotocols = ["https"]\npaths = ["/"]\n'
        ))

        self.assertEqual((), found)
        self.assertEqual(
            {
                "availability_impact": False,
                "credential_use": False,
                "mutation": False,
                "pivoting": False,
                "sensitive_data_access": False,
            },
            configuration.document["rules_of_engagement"],
        )
        self.assertEqual([], configuration.document["identity"])
        self.assertIsNone(configuration.document["program"]["platform"])

    def test_canonical_hash_ignores_formatting_but_not_policy(self):
        original, _ = config.load(write(VALID))
        reformatted, _ = config.load(write(
            "# an operator comment\n\n"
            + VALID.replace('ports = [443]', 'ports = [ 443, ]')
        ))
        widened, _ = config.load(write(VALID.replace('ports = [443]\nprotocols = ["https"]\npaths = ["/api/"]', 'ports = [443, 8443]\nprotocols = ["https"]\npaths = ["/api/"]')))

        self.assertEqual(original.canonical_sha256, reformatted.canonical_sha256)
        self.assertNotEqual(original.source_sha256, reformatted.source_sha256)
        self.assertNotEqual(original.canonical_sha256, widened.canonical_sha256)

    def test_summary_reports_names_and_hashes_without_references(self):
        configuration, _ = config.load(write(VALID))

        summary = configuration.summary()

        self.assertEqual("acme-web", summary["program_name"])
        self.assertEqual({"include": 1, "exclude": 1}, summary["scope"])
        self.assertEqual(["member"], summary["identities"])
        self.assertEqual(["X-Bounty-Id"], summary["required_headers"])
        self.assertEqual(["oob-dns"], summary["callbacks"])
        self.assertNotIn("slot://identity/member", repr(summary))
        self.assertNotIn("slot://header/bounty-id", repr(summary))


class SchemaVersionTest(unittest.TestCase):
    def test_unknown_schema_version_is_an_unsupported_version(self):
        self.assertEqual(
            [(UNSUPPORTED_VERSION, "config:schema_version", "unsupported schema version 2; supported: 1")],
            violations(VALID.replace("schema_version = 1", "schema_version = 2")),
        )

    def test_absent_schema_version_is_invalid_rather_than_unsupported(self):
        self.assertEqual(
            [(INVALID_CONFIGURATION, "config:schema_version", "required key is absent")],
            violations(VALID.replace("schema_version = 1\n", "")),
        )

    def test_non_integer_schema_version_is_invalid(self):
        self.assertEqual(
            [(INVALID_CONFIGURATION, "config:schema_version", "must be an integer")],
            violations(VALID.replace("schema_version = 1", 'schema_version = "1"')),
        )


class ClosedSchemaTest(unittest.TestCase):
    def test_unknown_key_is_rejected(self):
        self.assertEqual(
            [(INVALID_CONFIGURATION, "config:program.owner", "unknown key")],
            violations(VALID.replace('[program]\n', '[program]\nowner = "someone"\n')),
        )

    def test_inline_secret_value_is_rejected_by_name(self):
        self.assertEqual(
            [
                (
                    INVALID_CONFIGURATION,
                    "config:required_header[0].value",
                    "inline secret values are not accepted; declare a reference instead",
                ),
                (INVALID_CONFIGURATION, "config:required_header[0].value_ref", "required key is absent"),
            ],
            violations(VALID.replace(
                'value_ref = "slot://header/bounty-id"',
                'value = "b3adc0de"',
            )),
        )

    def test_unknown_top_level_table_is_rejected(self):
        self.assertEqual(
            [(INVALID_CONFIGURATION, "config:database", "unknown key")],
            violations(VALID + '\n[database]\nurl = "postgres://localhost/rk"\n'),
        )


class ScopeTest(unittest.TestCase):
    def test_scope_requires_at_least_one_inclusion(self):
        self.assertEqual(
            [(INVALID_CONFIGURATION, "config:scope.include", "required key is absent")],
            violations(
                "schema_version = 1\n"
                '[program]\nname = "acme-web"\n'
                "[budgets]\nrequests = 1\ntokens = 1\nconcurrency = 1\nburst = 1\nwindow_seconds = 1\n"
            ),
        )

    def test_empty_inclusion_list_is_refused(self):
        self.assertEqual(
            [(INVALID_CONFIGURATION, "config:scope.include", "must list at least one entry")],
            violations(
                "schema_version = 1\n"
                '[program]\nname = "acme-web"\n'
                "[budgets]\nrequests = 1\ntokens = 1\nconcurrency = 1\nburst = 1\nwindow_seconds = 1\n"
                "[scope]\ninclude = []\n"
            ),
        )

    def test_every_inclusion_names_ports_protocols_and_paths(self):
        self.assertEqual(
            [
                "config:scope.include[0].paths",
                "config:scope.include[0].ports",
                "config:scope.include[0].protocols",
            ],
            sorted(sources(
                "schema_version = 1\n"
                '[program]\nname = "acme-web"\n'
                "[budgets]\nrequests = 1\ntokens = 1\nconcurrency = 1\nburst = 1\nwindow_seconds = 1\n"
                '[[scope.include]]\nhost = "app.example.com"\n'
            )),
        )

    def test_port_range_protocol_and_path_shapes_are_checked(self):
        self.assertEqual(
            [
                (INVALID_CONFIGURATION, "config:scope.include[0].paths[0]", PATH_SHAPE),
                (INVALID_CONFIGURATION, "config:scope.include[0].ports[0]", "must be between 1 and 65535"),
                (INVALID_CONFIGURATION, "config:scope.include[0].protocols[0]", "must be one of: http, https"),
            ],
            sorted(violations(VALID.replace(
                'ports = [443]\nprotocols = ["https"]\npaths = ["/api/"]',
                'ports = [70000]\nprotocols = ["ftp"]\npaths = ["api"]',
                1,
            ))),
        )

    def test_host_must_be_a_hostname_or_address(self):
        self.assertEqual(
            ["config:scope.include[0].host"],
            sources(VALID.replace('host = "app.example.com"', 'host = "https://app.example.com/api"')),
        )

    def test_address_literal_is_accepted_as_a_host(self):
        _, found = config.load(write(VALID.replace('host = "app.example.com"', 'host = "203.0.113.10"')))

        self.assertEqual((), found)

    def test_wildcard_host_is_accepted(self):
        _, found = config.load(write(VALID.replace('host = "app.example.com"', 'host = "*.example.com"')))

        self.assertEqual((), found)

    def test_an_inclusion_host_is_a_name_an_address_or_a_wildcard_over_two_labels(self):
        accepted = ("app.example.com", "*.example.com", "*.co.uk", "203.0.113.10", "2001:db8::1")
        refused = (
            "*.com",  # a whole registry
            "localhost",  # not a name this Program can be reached at
            "999.999.999.999",  # neither an address nor a plausible name
            "010.0.0.1",  # an address with a leading zero is not one here
            "app.example.com:443",  # a port belongs in `ports`
            "app example com",
            "",
        )

        for host in accepted:
            with self.subTest(host=host):
                self.assertEqual([], sources(VALID.replace("app.example.com", host, 1)))
        for host in refused:
            with self.subTest(host=host):
                self.assertEqual(
                    ["config:scope.include[0].host"],
                    sources(VALID.replace("app.example.com", host, 1)),
                )

    def test_a_host_is_normalised_so_two_spellings_are_one_policy(self):
        original, _ = config.load(write(VALID))
        respelled, found = config.load(write(VALID.replace("app.example.com", "APP.Example.Com.", 1)))

        self.assertEqual((), found)
        self.assertEqual(original.canonical_sha256, respelled.canonical_sha256)

    def test_an_exclusion_may_be_as_wide_as_the_operator_likes(self):
        """Breadth withdraws authority here, so the inclusion floor does not apply."""
        for host in ("*.com", "localhost", "*.example.com"):
            with self.subTest(host=host):
                _, found = config.load(write(VALID.replace("admin.example.com", host, 1)))
                self.assertEqual((), found)

    def test_a_path_names_a_prefix_on_its_own_host(self):
        refused = (
            "//elsewhere.example/x",  # a protocol-relative URL, not a path
            "/api/../../etc",
            "/..",
            "/api\tX-Injected: 1",  # a control character TOML happens to allow
            "/api\u202e",  # a right-to-left override hides what follows it
            "api/",
        )

        for path in refused:
            with self.subTest(path=path):
                self.assertEqual(
                    [(INVALID_CONFIGURATION, "config:scope.include[0].paths[0]", PATH_SHAPE)],
                    violations(VALID.replace("/api/", path, 1)),
                )

    def test_a_repeated_rule_is_one_rule(self):
        original, _ = config.load(write(VALID))
        repeated, found = config.load(write(
            VALID + '\n[[scope.include]]\nhost = "app.example.com"\n'
            'ports = [443]\nprotocols = ["https"]\npaths = ["/api/"]\n'
        ))

        self.assertEqual((), found)
        self.assertEqual(1, len(repeated.document["scope"]["include"]))
        self.assertEqual(original.canonical_sha256, repeated.canonical_sha256)


class ReferenceTest(unittest.TestCase):
    def test_a_credential_bearing_url_is_not_a_reference(self):
        found = violations(VALID.replace(
            'slot_ref = "slot://identity/member"',
            'slot_ref = "https://admin:hunter2@app.example.com/login"',
        ))

        self.assertEqual(["config:identity[0].slot_ref"], [source for _, source, _ in found])
        self.assertNotIn("hunter2", found[0][2])

    def test_a_header_reference_must_name_a_slot_too(self):
        self.assertEqual(
            ["config:required_header[0].value_ref"],
            sources(VALID.replace("slot://header/bounty-id", "file:///etc/rk/bounty-id")),
        )

    def test_a_slot_reference_names_a_store_and_a_key_within_it(self):
        self.assertEqual(
            ["config:identity[0].slot_ref"],
            sources(VALID.replace("slot://identity/member", "slot://member")),
        )


class ControlsTest(unittest.TestCase):
    def test_rules_of_engagement_are_closed_and_boolean(self):
        self.assertEqual(
            [
                (INVALID_CONFIGURATION, "config:rules_of_engagement.exfiltration", "unknown key"),
                (
                    INVALID_CONFIGURATION,
                    "config:rules_of_engagement.mutation",
                    "must be true or false",
                ),
            ],
            sorted(violations(VALID.replace(
                "[rules_of_engagement]\nmutation = true",
                '[rules_of_engagement]\nmutation = "yes"\nexfiltration = true',
            ))),
        )

    def test_budgets_must_be_present_and_positive(self):
        self.assertEqual(
            [
                (INVALID_CONFIGURATION, "config:budgets.burst", "required key is absent"),
                (INVALID_CONFIGURATION, "config:budgets.requests", "must be a positive integer"),
                (INVALID_CONFIGURATION, "config:budgets.window_seconds", "required key is absent"),
            ],
            sorted(violations(VALID.replace(
                "requests = 5000\ntokens = 2000000\nconcurrency = 2\nburst = 500\nwindow_seconds = 3600",
                "requests = 0\ntokens = 2000000\nconcurrency = 2",
            ))),
        )

    def test_identity_and_header_names_are_unique(self):
        self.assertEqual(
            [
                (INVALID_CONFIGURATION, "config:identity[1].name", "duplicate name: member"),
                (INVALID_CONFIGURATION, "config:required_header[1].name", "duplicate name: x-bounty-id"),
            ],
            sorted(violations(
                VALID
                + '\n[[identity]]\nname = "member"\n'
                + '\n[[required_header]]\nname = "x-bounty-id"\nvalue_ref = "slot://header/other"\n'
            )),
        )

    def test_required_header_must_carry_a_reference(self):
        self.assertEqual(
            [(INVALID_CONFIGURATION, "config:required_header[0].value_ref", "required key is absent")],
            violations(VALID.replace('value_ref = "slot://header/bounty-id"\n', "")),
        )

    def test_callback_kind_is_closed(self):
        self.assertEqual(
            [(INVALID_CONFIGURATION, "config:callback[0].kind", "must be one of: dns, http")],
            violations(VALID.replace('kind = "dns"', 'kind = "smtp"')),
        )


class SourceTest(unittest.TestCase):
    def refusal(self, path) -> str:
        configuration, found = config.load(path)

        self.assertIsNone(configuration)
        self.assertEqual(1, len(found))
        self.assertEqual(INVALID_CONFIGURATION, found[0].code)
        self.assertEqual("config", found[0].source)
        return found[0].detail

    def test_unreadable_configuration_is_invalid(self):
        self.assertIn("cannot read", self.refusal(scratch() / "absent.toml"))

    def test_a_directory_is_not_a_configuration(self):
        self.assertIn("not a regular file", self.refusal(scratch()))

    def test_a_configuration_larger_than_policy_is_refused_unread(self):
        oversized = scratch() / "program.toml"
        oversized.write_bytes(b"# " + b"a" * config.MAXIMUM_BYTES)

        self.assertIn("larger than", self.refusal(oversized))

    def test_a_path_that_is_not_one_is_refused_rather_than_raised(self):
        self.assertIn("cannot read", self.refusal("program\x00.toml"))

    def test_an_interpreter_without_a_toml_parser_is_a_missing_dependency(self):
        """The parser ships with CPython, but a minimal build may leave it out."""
        source = write(VALID)

        with mock.patch.dict(sys.modules, {"tomllib": None}):
            configuration, found = config.load(source)

        self.assertIsNone(configuration)
        self.assertEqual(
            [(MISSING_DEPENDENCY, "runtime:module:tomllib")],
            [(item.code, item.source) for item in found],
        )

    def test_unparsable_configuration_is_invalid(self):
        self.assertEqual(
            [INVALID_CONFIGURATION],
            [code for code, _, _ in violations("schema_version = ,\n")],
        )

    def test_document_root_must_be_a_table(self):
        self.assertEqual(
            [(INVALID_CONFIGURATION, "config:program", "must be a table")],
            violations(VALID.replace('[program]\nname = "acme-web"\nplatform = "hackerone"', 'program = "acme-web"')),
        )


class AggregationTest(unittest.TestCase):
    def test_every_violation_is_reported_in_a_stable_order(self):
        found = violations(VALID.replace('name = "acme-web"', 'name = "ACME WEB"').replace(
            "requests = 5000", "requests = -1"
        ))

        self.assertEqual(
            [
                (INVALID_CONFIGURATION, "config:budgets.requests", "must be a positive integer"),
                (INVALID_CONFIGURATION, "config:program.name", "must match [a-z0-9][a-z0-9-]{0,62}"),
            ],
            found,
        )

    def test_a_reference_is_still_checked_when_its_entry_is_named_badly(self):
        """A bad name must not hide the field that decides whether a secret is inline."""
        self.assertEqual(
            [
                "config:identity[0].name",
                "config:identity[0].slot_ref",
            ],
            sources(VALID.replace(
                'name = "member"\nslot_ref = "slot://identity/member"',
                'name = "MEMBER ONE"\nslot_ref = "https://admin:hunter2@app.example.com/login"',
            )),
        )

    def test_an_unsupported_version_is_reported_alone(self):
        """The version explains every other refusal, so reporting them would mislead."""
        self.assertEqual(
            [(UNSUPPORTED_VERSION, "config:schema_version", "unsupported schema version 2; supported: 1")],
            violations(
                VALID.replace("schema_version = 1", "schema_version = 2")
                + '\n[telemetry]\nendpoint = "https://collector.example"\n'
            ),
        )


if __name__ == "__main__":
    unittest.main()
