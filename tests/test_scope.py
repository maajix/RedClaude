"""What the compiled Scope Policy decides, and what it refuses to be asked.

Six questions, one per criterion of the ticket:

1. Does one configuration compile to one policy, whatever order it was written
   in, and is every dimension of the grammar represented in the result?
2. Is every address, port and path canonicalised before it is matched, and is an
   ambiguous spelling refused rather than resolved?
3. Can a required header's name be read without its value coming with it?
4. Is an absent permission a denial?
5. Is discovery unauthorised for every policy that can be written?
6. Do the request matrix and the entity matrix decide the same way through the
   evaluator as they do through the CLI and SQL? The matrix itself lives in
   `tests.fixtures`, which is what makes that question answerable at all.
"""

from __future__ import annotations

import json
import unittest

from redkraken import config, scope
from redkraken.outcome import INVALID_CONFIGURATION
from tests.fixtures import (
    SCOPE_ENTITIES,
    SCOPE_REFUSALS,
    SCOPE_REQUESTS,
    SCOPED,
    VALID,
    write,
)


def compiled(text: str = SCOPED) -> scope.Policy:
    configuration, violations = config.load(write(text))
    assert configuration is not None, violations
    policy, refusals = scope.compile_policy(configuration)
    assert policy is not None, refusals
    return policy


def refused(text: str) -> tuple[str, ...]:
    """The refusals compiling one configuration produces, as source strings."""
    configuration, violations = config.load(write(text))
    assert configuration is not None, violations
    policy, refusals = scope.compile_policy(configuration)
    assert policy is None, "the configuration compiled"
    for refusal in refusals:
        assert refusal.code == INVALID_CONFIGURATION, refusal
    return tuple(refusal.source for refusal in refusals)


class CompilationTest(unittest.TestCase):
    """Criterion 1: one canonical decision, covering every dimension."""

    def test_every_dimension_of_the_policy_is_represented(self):
        policy = compiled()

        self.assertEqual({"http", "https"}, {rule.protocol for rule in policy.rules})
        self.assertEqual({80, 443, 8080} & {rule.port for rule in policy.rules}, {80, 443})
        self.assertEqual({"/", "/v1/", "/internal/"}, {rule.path_prefix for rule in policy.rules})
        self.assertEqual(
            {scope.TARGET, scope.EXCLUDE, scope.EGRESS_SUPPORT},
            {rule.effect for rule in policy.rules},
        )
        self.assertEqual(["oob-dns", "oob-http"], [channel.name for channel in policy.channels])
        self.assertEqual(
            list(config.RULES_OF_ENGAGEMENT), [control for control, _ in policy.controls]
        )
        self.assertEqual(["X-Bounty-Id"], [header.name for header in policy.headers])
        self.assertEqual(60, policy.window_seconds)
        self.assertEqual(scope.GRAMMAR_VERSION, policy.grammar_version)

    def test_a_rule_naming_several_ports_and_protocols_compiles_to_one_rule_each(self):
        # The database matches by equality on indexed columns, so the sets in the
        # configuration are expanded here rather than interpreted there.
        policy = compiled()
        wildcards = [
            rule
            for rule in policy.rules
            if rule.effect == scope.TARGET and rule.pattern.text == "*.example.com"
        ]

        self.assertEqual(4, len(wildcards))
        self.assertEqual(
            {("http", 80), ("http", 443), ("https", 80), ("https", 443)},
            {(rule.protocol, rule.port) for rule in wildcards},
        )

    def test_document_order_is_not_a_semantic(self):
        # The same four rules, written in the opposite order. If either the
        # ordinals or the digest moved, precedence would depend on the file.
        blocks = SCOPED.split("[[scope.include]]")
        reversed_scope = blocks[0] + "[[scope.include]]".join(
            [""] + list(reversed(blocks[1:]))
        )

        self.assertEqual(compiled().policy_sha256(), compiled(reversed_scope).policy_sha256())

    def test_ordinals_are_dense_and_ordered_by_effect(self):
        policy = compiled()

        self.assertEqual(
            list(range(1, len(policy.rules) + 1)), [rule.ord for rule in policy.rules]
        )
        ranks = [rule.effect_rank for rule in policy.rules]
        self.assertEqual(sorted(ranks), ranks)

    def test_the_same_rule_written_twice_is_one_rule(self):
        policy = compiled()
        keys = [
            (rule.effect, rule.pattern.text, rule.protocol, rule.port, rule.path_prefix)
            for rule in policy.rules
        ]

        self.assertEqual(len(set(keys)), len(keys))

    def test_an_http_callback_is_reachable_and_a_dns_callback_is_not(self):
        policy = compiled()
        egress = {rule.pattern.text for rule in policy.rules if rule.effect == scope.EGRESS_SUPPORT}

        self.assertEqual({"callback.example.org"}, egress)

    def test_a_configuration_that_names_no_callback_compiles(self):
        policy = compiled(VALID)

        self.assertEqual([], [rule for rule in policy.rules if rule.effect == scope.EGRESS_SUPPORT])
        self.assertEqual(["oob-dns"], [channel.name for channel in policy.channels])

    def test_an_inclusion_may_not_name_an_address_the_proxy_will_refuse(self):
        for address in ("10.0.0.1", "224.0.0.1", "ff02::1"):
            with self.subTest(address=address):
                text = SCOPED.replace('host = "api.example.net"', f'host = "{address}"')

                # Index 1 because the loader has already sorted the rules by
                # content: the source names where the rule ended up, which is
                # the same place the compiled ordinals come from.
                self.assertEqual(("scope:scope.include[1].host",), refused(text))

    def test_an_exclusion_may_name_a_private_address(self):
        # Breadth withdraws authority here, so the asymmetry runs the other way.
        text = SCOPED.replace('host = "admin.example.com"', 'host = "10.0.0.1"')
        policy = compiled(text)

        self.assertIn("10.0.0.1", {rule.pattern.text for rule in policy.rules})

    def test_a_callback_may_not_be_a_wildcard(self):
        text = SCOPED.replace('host = "callback.example.org"', 'host = "*.callback.example.org"')

        self.assertEqual(("scope:callback[0].host",), refused(text))

    def test_two_channels_at_one_endpoint_are_refused_rather_than_ranked(self):
        # `decide_callback` answers with one channel name and the projection
        # keys on the host, so two names for one endpoint would make "which
        # channel admitted this arrival" a question about declaration order --
        # and would leave the compiler reporting two channels where the database
        # kept one row. Index 2 for the same reason the inclusion above is index
        # 1: the loader sorted the entries, and this is the second of the two to
        # arrive at that host.
        text = SCOPED + (
            '\n[[callback]]\nname = "oob-twin"\nkind = "dns"\nhost = "dns.example.org"\n'
        )

        self.assertEqual(("scope:callback[2].host",), refused(text))

    def test_a_pattern_is_a_suffix_test_and_never_a_glob(self):
        for pattern in ("ap*.example.com", "*.*.example.com", "app.*"):
            with self.subTest(pattern):
                with self.assertRaises(scope.PolicyError) as refusal:
                    scope.parse_pattern(pattern)
                self.assertEqual("malformed_host", refusal.exception.reason)

    def test_a_wildcard_may_not_name_a_single_label_or_an_address(self):
        for pattern in ("*.com", "*.93.184.216.34"):
            with self.subTest(pattern):
                with self.assertRaises(scope.PolicyError):
                    scope.parse_pattern(pattern)

    def test_the_policy_digest_covers_the_rules(self):
        policy = compiled()
        moved = scope.Policy(
            program=policy.program,
            configuration_sha256=policy.configuration_sha256,
            rules=policy.rules[:-1],
            channels=policy.channels,
            controls=policy.controls,
            headers=policy.headers,
            budgets=policy.budgets,
        )

        self.assertNotEqual(policy.policy_sha256(), moved.policy_sha256())


class CanonicalFormTest(unittest.TestCase):
    """Criterion 2: one spelling per thing, and a refusal for the ambiguous ones."""

    def test_one_machine_has_one_spelling(self):
        for given, expected in (
            ("APP.example.com.", "app.example.com"),
            ("  app.example.com  ", "app.example.com"),
            ("[::ffff:93.184.216.34]", "93.184.216.34"),
            ("::ffff:93.184.216.34", "93.184.216.34"),
            ("[2001:db8::1]", "2001:db8::1"),
            ("2001:0db8:0000::1", "2001:db8::1"),
        ):
            with self.subTest(given):
                self.assertEqual(expected, scope.normalize_host(given))

    def test_a_host_that_cannot_be_canonicalised_is_refused(self):
        for given, reason in (
            ("", "no_host"),
            ("   ", "no_host"),
            ("[]", "no_host"),
            ("exämple.com", "malformed_host"),
            ("app..example.com", "malformed_host"),
            (".example.com", "malformed_host"),
            ("-app.example.com", "malformed_host"),
            ("a" * 250 + ".example.com", "malformed_host"),
            (b"app.example.com", "malformed_host"),
        ):
            with self.subTest(given):
                with self.assertRaises(scope.PolicyError) as refusal:
                    scope.normalize_host(given)
                self.assertEqual(reason, refusal.exception.reason)

    def test_a_dotted_number_that_is_not_an_address_is_not_widened_into_one(self):
        # `inet` reads '1.2.3' as 1.2.0.3. Neither implementation reaches the
        # cast: the address shapes are matched first, '1.2.3' is not one of them,
        # and what is left is a name whose labels happen to be digits. It matches
        # nothing, which is the point -- what must not happen is one side reading
        # it as an address and the other as a name.
        self.assertEqual("1.2.3", scope.normalize_host("1.2.3"))
        self.assertEqual("1.2.0.3", scope.normalize_host("1.2.0.3"))
        self.assertNotEqual(scope.normalize_host("1.2.3"), scope.normalize_host("1.2.0.3"))

    def test_a_port_is_defaulted_from_the_protocol_and_never_guessed(self):
        self.assertEqual(80, scope.normalize_port(None, "http"))
        self.assertEqual(443, scope.normalize_port("", "https"))
        self.assertEqual(8443, scope.normalize_port("8443", "https"))
        self.assertEqual(8443, scope.normalize_port(8443, "https"))

    def test_an_ambiguous_or_out_of_range_port_is_refused(self):
        for given in ("0443", "443 ", "-1", "0x1bb", 0, 65536, True, 4.43):
            with self.subTest(given):
                with self.assertRaises(scope.PolicyError) as refusal:
                    scope.normalize_port(given, "https")
                self.assertEqual("malformed_port", refusal.exception.reason)

    def test_a_path_is_matched_in_both_the_spelling_asked_for_and_the_one_it_lands_on(self):
        for given, raw, normed in (
            ("/api/x", "/api/x", "/api/x"),
            ("api/x", "/api/x", "/api/x"),
            ("", "/", "/"),
            ("/api/%2e%2e/other", "/api/%2e%2e/other", "/other"),
            ("/api/../other", "/api/../other", "/other"),
            ("/api/./x", "/api/./x", "/api/x"),
            ("/api//x", "/api//x", "/api/x"),
            ("/api/", "/api/", "/api/"),
            ("/api\\..\\x", "/api\\..\\x", "/x"),
        ):
            with self.subTest(given):
                self.assertEqual((raw, normed), scope.path_variants(given))

    def test_a_path_that_does_not_print_is_refused(self):
        for given in ("/api/\x00", "/api/%00", "/api/​", b"/api/"):
            with self.subTest(given):
                with self.assertRaises(scope.PolicyError) as refusal:
                    scope.path_variants(given)
                self.assertEqual("malformed_path", refusal.exception.reason)

    def test_a_traversal_encoded_twice_over_is_decoded_before_it_is_normalised(self):
        # One decoding pass turns `%252e%252e` into `%2e%2e`, which holds no dot
        # segment for `normpath` to collapse. A target that decodes twice -- a
        # proxy in front of an application is the ordinary case -- would then
        # serve the excluded path while the receipt cited the inclusion.
        self.assertEqual(
            ("/x/%252e%252e/internal/secrets", "/internal/secrets"),
            scope.path_variants("/x/%252e%252e/internal/secrets"),
        )

    def test_a_path_encoded_further_than_that_is_refused_rather_than_unwrapped(self):
        # Four layers is the limit, and one more is a refusal rather than a fifth
        # pass: nothing legitimate wraps a dot segment that deeply, and a loop
        # with no bound is a loop an input decides the length of.
        self.assertEqual("/y", scope.path_variants("/x/%" + "25" * 3 + "2e%" + "25" * 3 + "2e/y")[1])
        with self.assertRaises(scope.PolicyError) as refusal:
            scope.path_variants("/x/%" + "25" * 5 + "2e/y")
        self.assertEqual("malformed_path", refusal.exception.reason)

    def test_a_doubled_leading_slash_is_one_slash(self):
        # POSIX reserves exactly two leading slashes and `normpath` preserves
        # them, so `//internal/x` would not be under a `/internal/` exclusion.
        # Web servers serve it as `/internal/x`.
        self.assertEqual(("//internal/x", "/internal/x"), scope.path_variants("//internal/x"))
        self.assertEqual(("///internal", "/internal"), scope.path_variants("///internal"))

    def test_a_prefix_covers_its_own_subtree_and_never_a_sibling(self):
        for path, prefix, under in (
            ("/v1", "/v1", True),
            ("/v1/x", "/v1", True),
            ("/v1/x", "/v1/", True),
            ("/v1-internal/dump", "/v1", False),
            ("/v10/x", "/v1", False),
            ("/v1x", "/v1/", False),
            ("/anything", "/", True),
        ):
            with self.subTest(f"{path} under {prefix}"):
                self.assertEqual(under, scope.path_under(path, prefix))

    def test_a_host_padded_with_what_postgresql_does_not_trim_is_refused(self):
        # `btrim` trims spaces; `str.strip()` also trims U+00A0. Trimming more
        # than SQL trims would make this host a name here and malformed there.
        with self.assertRaises(scope.PolicyError) as refusal:
            scope.normalize_host(" app.example.com")
        self.assertEqual("malformed_host", refusal.exception.reason)

    def test_an_address_the_two_worlds_spell_differently_is_refused(self):
        # Left accepted, each of these would carry a match key that depends on
        # which implementation canonicalised it: `host()` renders the
        # IPv4-compatible range as `::1.2.3.4` and Python as `::102:304`, and
        # `inet` reads a leading-zero octet as decimal where Python refuses it.
        for given in ("::102:304", "::1.2.3.4", "093.184.216.34", "::0.0.1.2"):
            with self.subTest(given):
                with self.assertRaises(scope.PolicyError) as refusal:
                    scope.normalize_host(given)
                self.assertEqual("malformed_host", refusal.exception.reason)

    def test_a_single_label_name_out_of_the_hex_alphabet_is_a_name(self):
        # `db`, `cafe` and `ec2` are spelled out of `[0-9a-f]`, and a pre-filter
        # with no colon in it read them as addresses that then failed to parse:
        # an ordinary name reported as a malformed address.
        for given in ("db", "cafe", "ec2", "beef"):
            with self.subTest(given):
                self.assertEqual(given, scope.normalize_host(given))

    def test_a_port_whose_digits_are_not_the_ones_int_reads_is_refused(self):
        # `str.isdigit()` is true of both: `int` reads the first as 443 and
        # raises a bare ValueError on the second, which no caller here handles.
        for given in ("٤٤٣", "²"):
            with self.subTest(given):
                with self.assertRaises(scope.PolicyError) as refusal:
                    scope.normalize_port(given, "https")
                self.assertEqual("malformed_port", refusal.exception.reason)

    def test_a_url_carrying_a_credential_is_refused(self):
        for url in (
            "https://user:secret@app.example.com/",
            "https://user@app.example.com/",
        ):
            with self.subTest(url):
                with self.assertRaises(scope.PolicyError) as refusal:
                    scope.canonical_request(url)
                self.assertEqual("malformed_url", refusal.exception.reason)
                self.assertNotIn("secret", refusal.exception.detail)

    def test_the_apex_is_not_covered_by_a_wildcard_over_it(self):
        self.assertEqual(
            ("a.b.example.com", "*.b.example.com", "*.example.com", "*.com"),
            scope.host_candidates("a.b.example.com"),
        )
        self.assertNotIn("*.example.com", scope.host_candidates("example.com"))

    def test_a_subtree_is_covered_by_itself_and_by_every_wildcard_above_it(self):
        self.assertEqual(
            ("*.b.example.com", "*.example.com", "*.com"),
            scope.wildcard_candidates("b.example.com"),
        )
        self.assertNotIn("b.example.com", scope.wildcard_candidates("b.example.com"))


class RequiredHeaderTest(unittest.TestCase):
    """Criterion 3: the name travels, the value stays where the runtime owns it."""

    def test_the_policy_document_carries_names_and_no_references(self):
        policy = compiled()
        document = policy.document()

        self.assertEqual(["X-Bounty-Id"], document["required_headers"])
        self.assertNotIn(
            "slot://header/bounty-id", config.canonical_bytes(document).decode("utf-8")
        )

    def test_the_diagnostic_summary_carries_names_and_no_references(self):
        rendered = json.dumps(compiled().summary())

        self.assertIn("X-Bounty-Id", rendered)
        self.assertNotIn("slot://", rendered)

    def test_the_reference_is_still_reachable_where_the_runtime_needs_it(self):
        # Redaction is not deletion: the proxy resolves the slot, and the policy
        # is where it learns which slot. What must not happen is the reference
        # travelling in the document every other reader sees.
        self.assertEqual(
            [("X-Bounty-Id", "slot://header/bounty-id")],
            [(header.name, header.value_ref) for header in compiled().headers],
        )
        self.assertEqual({"name": "X-Bounty-Id"}, compiled().headers[0].summary())


class PermissionTest(unittest.TestCase):
    """Criterion 4: absent is denied, for all five, with no permissive default."""

    def test_a_permission_the_configuration_does_not_grant_is_withheld(self):
        policy = compiled()

        self.assertTrue(scope.decide_action(policy, "mutation").allowed)
        for control in (
            "availability_impact",
            "credential_use",
            "pivoting",
            "sensitive_data_access",
        ):
            with self.subTest(control):
                permission = scope.decide_action(policy, control)
                self.assertFalse(permission.allowed)
                self.assertEqual("withheld", permission.reason)

    def test_a_configuration_that_states_no_permissions_grants_none(self):
        text = SCOPED.replace("mutation = true", "")
        policy = compiled(text)

        for control in config.RULES_OF_ENGAGEMENT:
            with self.subTest(control):
                self.assertFalse(scope.decide_action(policy, control).allowed)

    def test_an_unknown_permission_raises_rather_than_denying(self):
        # A denial would read as a policy decision, and the typo behind it would
        # never be found.
        for control in ("mutations", "", None, "MUTATION"):
            with self.subTest(control):
                with self.assertRaises(scope.PolicyError):
                    scope.decide_action(compiled(), control)


class DiscoveryTest(unittest.TestCase):
    """Criterion 5: not in the grammar, so no configuration turns it on."""

    def test_no_discovery_technique_is_authorised(self):
        policy = compiled()

        for technique in scope.DISCOVERY_TECHNIQUES:
            with self.subTest(technique):
                permission = scope.decide_discovery(policy, technique)
                self.assertFalse(permission.allowed)
                self.assertEqual("discovery_not_authorized", permission.reason)

    def test_the_five_named_techniques_are_the_spec_s_five(self):
        self.assertEqual(
            (
                "adjacent_host",
                "certificate_transparency",
                "dns_enumeration",
                "reverse_ip",
                "virtual_host",
            ),
            scope.DISCOVERY_TECHNIQUES,
        )

    def test_no_configuration_key_enables_discovery(self):
        # The refusal is structural: the loader's schema is closed, so a key that
        # asked for discovery would be refused before this module saw it.
        text = SCOPED.replace("[rules_of_engagement]", "[rules_of_engagement]\ndns_enumeration = true")
        configuration, violations = config.load(write(text))

        self.assertIsNone(configuration)
        self.assertTrue(violations)

    def test_a_wildcard_inclusion_does_not_authorise_finding_what_is_under_it(self):
        policy = compiled()

        # The requests the wildcard authorises are authorised; finding out which
        # hosts exist under it is a separate permission nobody granted.
        self.assertTrue(scope.decide(policy, "https://app.example.com/").allowed)
        self.assertFalse(scope.decide_discovery(policy, "dns_enumeration").allowed)
        self.assertFalse(scope.decide_discovery(policy, "adjacent_host").allowed)

    def test_the_diagnostic_summary_says_so_for_every_technique(self):
        self.assertEqual(
            {technique: False for technique in scope.DISCOVERY_TECHNIQUES},
            compiled().summary()["discovery"],
        )

    def test_an_unknown_technique_raises(self):
        with self.assertRaises(scope.PolicyError):
            scope.decide_discovery(compiled(), "port_scan")


class VerdictTest(unittest.TestCase):
    """Criterion 6, the Python half: the matrix, decided here."""

    @classmethod
    def setUpClass(cls):
        cls.policy = compiled()

    def test_every_request_in_the_matrix_is_decided_as_the_matrix_says(self):
        for url, scope_class, reason in SCOPE_REQUESTS:
            with self.subTest(url):
                verdict = scope.decide(self.policy, url)
                self.assertEqual(scope_class, verdict.scope_class, verdict.detail)
                self.assertEqual(reason, verdict.reason)
                self.assertEqual(scope_class in ("target", "egress_support"), verdict.allowed)

    def test_every_refused_url_in_the_matrix_is_denied_for_the_stated_reason(self):
        for url, reason in SCOPE_REFUSALS:
            with self.subTest(url):
                verdict = scope.decide(self.policy, url)
                self.assertEqual(scope.DENIED, verdict.scope_class)
                self.assertEqual(reason, verdict.reason)

    def test_an_inclusion_path_authorises_its_subtree_and_not_its_siblings(self):
        # The fixture writes `/v1/`, and the trailing slash hides the whole
        # class: an operator who writes `/v1` means the v1 API and would also
        # have authorised `/v1-internal/dump` under a bare prefix test.
        policy = compiled(SCOPED.replace('paths = ["/v1/"]', 'paths = ["/v1"]'))

        for url, scope_class in (
            ("https://api.example.net/v1", "target"),
            ("https://api.example.net/v1/users", "target"),
            ("https://api.example.net/v1-internal/dump", scope.DENIED),
            ("https://api.example.net/v10/users", scope.DENIED),
        ):
            with self.subTest(url):
                self.assertEqual(scope_class, scope.decide(policy, url).scope_class)

    def test_an_exclusion_written_in_a_spelling_nobody_types_still_fires(self):
        # The prefix is canonicalised at compile time for the same reason a
        # request's path is: stored verbatim, `/%69nternal/` withdraws nothing an
        # operator can ask for, and the withdrawal reads as if it were in force.
        policy = compiled(SCOPED.replace('paths = ["/internal/"]', 'paths = ["/%69nternal/"]'))

        verdict = scope.decide(policy, "https://app.example.com/internal/secrets")

        self.assertEqual(scope.DENIED, verdict.scope_class)
        self.assertEqual("excluded", verdict.reason)

    def test_a_question_this_grammar_has_no_word_for_is_refused(self):
        # The two coverage polarities are the wide readings, so a caller that
        # mistyped `request` must not be answered under one of them.
        with self.assertRaises(scope.PolicyError) as refusal:
            scope.Request(
                protocol="https",
                host="api.example.net",
                port=443,
                path_raw="/",
                path_norm="/",
                question="requst",
            )
        self.assertEqual("not_addressable", refusal.exception.reason)

    def test_every_entity_in_the_matrix_is_projected_as_the_matrix_says(self):
        for kind, selector, port, path, scope_class, reason in SCOPE_ENTITIES:
            with self.subTest(f"{kind}:{selector}:{port}:{path}"):
                verdict = scope.decide_entity(
                    self.policy, kind, selector, port=port, path=path
                )
                self.assertEqual(scope_class, verdict.scope_class, verdict.detail)
                self.assertEqual(reason, verdict.reason)

    def test_every_reason_the_matrix_produces_is_in_the_closed_vocabulary(self):
        produced = {reason for _, _, reason in SCOPE_REQUESTS}
        produced |= {reason for _, reason in SCOPE_REFUSALS}
        produced |= {case[5] for case in SCOPE_ENTITIES}

        self.assertLessEqual(produced, set(scope.REASONS))

    def test_an_exclusion_wins_over_every_inclusion_that_also_matches(self):
        verdict = scope.decide(self.policy, "https://admin.example.com/")
        cited = self.policy.rules[verdict.rule_ord - 1]

        self.assertEqual(scope.EXCLUDE, cited.effect)
        self.assertEqual("admin.example.com", cited.pattern.text)

    def test_specificity_decides_which_rule_is_cited_and_not_the_verdict(self):
        # Two rules authorise this request: the wildcard and nothing else, so the
        # citation is the wildcard. Adding an exact rule for the same host must
        # move the citation and leave the verdict alone.
        text = SCOPED.replace(
            "[[scope.exclude]]",
            '[[scope.include]]\nhost = "app.example.com"\nports = [443]\n'
            'protocols = ["https"]\npaths = ["/"]\n\n[[scope.exclude]]',
            1,
        )
        policy = compiled(text)
        verdict = scope.decide(policy, "https://app.example.com/")

        self.assertEqual(scope.TARGET, verdict.scope_class)
        self.assertEqual("app.example.com", policy.rules[verdict.rule_ord - 1].pattern.text)

    def test_an_entity_with_no_address_is_not_a_scope_question(self):
        for kind, selector in ((None, None), (None, "app.example.com"), ("host", None)):
            with self.subTest(f"{kind}:{selector}"):
                verdict = scope.decide_entity(self.policy, kind, selector)
                self.assertEqual(scope.NOT_ADDRESSABLE, verdict.scope_class)
                self.assertEqual("not_addressable", verdict.reason)
                self.assertFalse(verdict.allowed)

    def test_an_unknown_selector_kind_raises(self):
        with self.assertRaises(scope.PolicyError):
            scope.decide_entity(self.policy, "url", "https://app.example.com/")

    def test_an_entity_whose_selector_cannot_be_canonicalised_is_denied(self):
        verdict = scope.decide_entity(self.policy, "host", "app..example.com")

        self.assertEqual(scope.DENIED, verdict.scope_class)
        self.assertEqual("malformed_host", verdict.reason)

    def test_an_interaction_at_a_declared_channel_is_support_and_never_evidence(self):
        for host in ("dns.example.org", "abc123.dns.example.org", "callback.example.org"):
            with self.subTest(host):
                verdict = scope.decide_callback(self.policy, host)
                self.assertEqual(scope.EGRESS_SUPPORT, verdict.scope_class)
                self.assertEqual("matched_callback", verdict.reason)
                self.assertFalse(verdict.is_target)

    def test_an_interaction_nowhere_near_a_channel_is_denied(self):
        for host in ("example.org", "dns.example.org.evil.test", "app.example.com"):
            with self.subTest(host):
                verdict = scope.decide_callback(self.policy, host)
                self.assertEqual(scope.DENIED, verdict.scope_class)

    def test_the_channel_an_interaction_arrived_on_is_the_most_specific_one(self):
        # Two channels, one beneath the other, and both admit the arrival. The
        # child is the answer, the way the more specific rule is everywhere
        # else: beneath it the extra label is a canary, while beneath the parent
        # the same name reads as a canary one label longer.
        policy = compiled(
            SCOPED.replace(
                '[[callback]]\nname = "oob-dns"',
                '[[callback]]\nname = "oob-near"\nkind = "dns"\n'
                'host = "a.dns.example.org"\n\n[[callback]]\nname = "oob-dns"',
            )
        )

        verdict = scope.decide_callback(policy, "abc123.a.dns.example.org")

        self.assertEqual(scope.EGRESS_SUPPORT, verdict.scope_class)
        self.assertEqual("oob-near", verdict.channel)

    def test_a_host_that_is_both_a_channel_and_a_target_is_support(self):
        # The lower effect rank wins, so a callback endpoint the Program happens
        # to own is still not a finding.
        text = SCOPED.replace('host = "callback.example.org"', 'host = "app.example.com"')
        policy = compiled(text)
        verdict = scope.decide(policy, "https://app.example.com/")

        self.assertEqual(scope.EGRESS_SUPPORT, verdict.scope_class)
        self.assertFalse(verdict.is_target)

    def test_a_policy_with_no_matching_rule_denies_without_being_asked_twice(self):
        verdict = scope.decide(self.policy, "https://elsewhere.test/")

        self.assertEqual(scope.DENIED, verdict.scope_class)
        self.assertEqual("unlisted", verdict.reason)
        self.assertIsNone(verdict.rule_ord)


if __name__ == "__main__":
    unittest.main()
