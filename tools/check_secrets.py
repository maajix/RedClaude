"""Whether anything this repository would publish carries a credential.

The tree is publishable: it is a checkout an operator clones, and everything
tracked or unignored in it travels. So does everything a run leaves behind --
container build contexts, generated fixtures, logs, rendered reports and
exported evidence bundles -- because those are the files an operator hands to a
triager. A credential in any of them is the same defect wearing a different
extension, so the same rules read all of them and the roots are arguments.

**What a finding is.** Each rule matches the *shape* of a credential a provider
issues: a prefix nobody else uses, a length nobody types by hand, a structure a
parser would accept. Shape is what a scan can know. Whether a shaped string is
live is a question only the issuer can answer, and a scan that guessed would
either pass a real key or fail forever on a fixture.

**What a finding says, and what it does not.** A finding names the rule, the
file, the line and how long the match was. It does not print the match. A gate
that quoted the secret would copy it into every log the gate's own output
reaches, which is the failure this exists to prevent, one indirection along.
The operator has the file and the line; the value is one look away, and looking
is the friction that belongs in front of writing an allowance for it.

**What an allowance is.** A rule that matches a synthetic value is a rule
working correctly on a fixture, and the tree carries many: an SDK probe's fake
keys, a test's sentinel database password, a redaction rule's own probe string.
Each is declared below as the *literal itself*, with a reason, because the
literal is the thing that is or is not a secret -- a path is not. Declaring the
literal has one more property that a path-shaped exception would not: the same
value appearing in a file nobody expected is still allowed, and a *different*
value in an expected file is still a finding.

**An allowance that no longer matches anything fails.** A tolerance outliving
its cause can only forgive a real one. When the fixture that needed a literal
is deleted, the literal goes with it, and this says so rather than waiting.

Run it as a module -- `python3 -m tools.check_secrets` for the checkout alone,
or with directories after it for the artifacts a run produced:

    python3 -m tools.check_secrets /tmp/reports /tmp/bundle
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple


CHECKOUT = Path(__file__).resolve().parents[1]

#: The largest file this scan reads. A run's logs have no natural size, and a
#: scan that quietly skipped the one file too big to hold would report a clean
#: tree it had not read. Anything over this is a problem rather than a skip, so
#: the hole is in the report instead of in the claim.
CEILING = 64 * 1024 * 1024


class SecretsError(Exception):
    """The scan found something, or could not honestly say it had not."""


class Rule(NamedTuple):
    """One credential shape, with the two strings that keep it honest.

    `probe` is a string the rule must match and `counter_probe` one it must
    not. The pair is what a rule is worth: a pattern edited until the tree came
    back clean is a pattern that may no longer match anything at all, and the
    probe fails the moment that happens. The convention is the schema's --
    `redaction_rules` carries the same pair for the same reason.
    """

    name: str
    what: str
    pattern: re.Pattern[str]
    probe: str
    counter_probe: str

    def identifying(self, match: re.Match[str]) -> str:
        """The part of a match that is or is not a secret.

        A pattern with a group captures it: what matters in a database URL is
        the password, not the role or the host that surround it, and keying the
        allowance on the whole match would make one declared sentinel need a
        row per host it appears against.
        """
        return match.group(1) if self.pattern.groups else match.group(0)

    def probed(self) -> str:
        """What this rule finds in its own probe.

        Raises if the probe does not match, which is the probe doing its job at
        the earliest moment there is: every caller of this module reaches
        `declared()` before it scans anything, so a rule edited until it matched
        nothing fails here rather than by reporting a clean tree.
        """
        found = self.pattern.search(self.probe)
        if found is None:
            raise SecretsError(f"{self.name}: the rule no longer matches its own probe")
        if self.pattern.search(self.counter_probe) is not None:
            raise SecretsError(f"{self.name}: the rule now matches its counter probe")
        return self.identifying(found)


RULES: tuple[Rule, ...] = (
    Rule(
        "anthropic",
        "an Anthropic API key, OAuth access token or refresh token",
        re.compile(r"sk-ant-[a-z0-9]+-[A-Za-z0-9_\-]{8,}"),
        "sk-ant-api03-PROBEcheckSecretsRuleProbe",
        "sk-ant-",
    ),
    Rule(
        "onepassword",
        "a 1Password service-account token",
        re.compile(r"\bops_[A-Za-z0-9_\-]{43,}"),
        "ops_" + "b" * 43,
        # The tree's prose is full of `stops_being_...` and `stops_itself_...`,
        # which carry `ops_` and enough following word characters. The word
        # boundary is what declines them, and this is the string that proves it.
        "the claim stops_being_current_once_however_often_it_is_asked_again",
    ),
    Rule(
        "private_key",
        "a PEM private key with a body",
        re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----[\sA-Za-z0-9+/=]{100,}?-----END"),
        "-----BEGIN PRIVATE KEY-----\n" + "MIIB" * 30 + "\n-----END PRIVATE KEY-----",
        # A header with a word between it and the footer is how this tree writes
        # a key that is not one, and it is not key material by any reading.
        "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----",
    ),
    Rule(
        "url_password",
        "a password written inline in a URL",
        # The scheme is bounded rather than starred. Unbounded, the run before
        # `://` is retried from every offset inside it, and a generated fixture
        # of a million filler characters -- which a run leaves behind and this
        # scan is pointed at -- takes quadratic time to report nothing. Thirty
        # two is past every scheme IANA has registered.
        re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]{0,31}://[^\s:/@\"']+:([^\s/@\"']+)@"),
        "postgresql://rk2_runtime:PROBEcheckSecretsUrlPassword@127.0.0.1:5432/rk2",
        "postgresql://rk2_runtime@127.0.0.1:5432/rk2",
    ),
    Rule(
        "aws",
        "an AWS access key identifier",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "AKIA" + "Q" * 16,
        "AKIA-not-sixteen",
    ),
    Rule(
        "github",
        "a GitHub personal, OAuth, app or refresh token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{22,}"),
        "ghp_" + "z" * 36,
        "ghp_short",
    ),
    Rule(
        "slack",
        "a Slack bot, user, app or refresh token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),
        "xoxb-0123456789-PROBEcheckSecrets",
        "xoxb-short",
    ),
    Rule(
        "google",
        "a Google API key",
        re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
        "AIza" + "K" * 35,
        "AIza-not-thirty-five",
    ),
    Rule(
        "jwt",
        "a JSON Web Token carrying a header and a payload",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]*"),
        "eyJhbGciOiJQUk9CRSJ9.eyJzdWIiOiJjaGVja1NlY3JldHMifQ.cHJvYmU",
        # Two base64 segments that are not a header and a payload: the second
        # must start `eyJ` too, which is what makes this a token rather than any
        # two dotted words.
        "eyJhbGciOiJQUk9CRSJ9.bm90LWEtcGF5bG9hZA.cHJvYmU",
    ),
    Rule(
        "bearer",
        "a bearer token in an Authorization header",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/\-]{20,}={0,2}"),
        "Bearer PROBEcheckSecretsBearerToken",
        "Bearer short",
    ),
    Rule(
        "assigned_secret",
        "a long opaque value assigned to a credential-shaped name",
        re.compile(
            r"(?i)\b(?:password|passwd|secret|token|api[_\-]?key|access[_\-]?key"
            r"|private[_\-]?key)\b[^\S\n]*[:=][^\S\n]*[\"']([A-Za-z0-9+/=_\-]{32,})[\"']"
        ),
        'api_key = "PROBEcheckSecretsAssignedValue00"',
        # The tree assigns readable placeholders constantly. What this rule is
        # about is length and alphabet together, and a hyphenated sentence has
        # neither.
        'password = "fixture-password"',
    ),
)


class Allowance(NamedTuple):
    """Literals a rule matches that are not credentials, and why."""

    rule: str
    reason: str
    literals: tuple[str, ...]


ALLOWED: tuple[Allowance, ...] = (
    Allowance(
        "anthropic",
        "the SDK auth probe's fake keys. The probe exists to find out which "
        "credential the runtime picks up from where, so it has to plant one of "
        "each; every value carries PROBE and none was ever issued. The three "
        "padded to full length are the same values written where a shorter one "
        "would have been rejected before the measurement started.",
        (
            "sk-ant-api03-PROBEenvkey",
            "sk-ant-api03-PROBEfdkey",
            "sk-ant-api03-PROBEhelperkey",
            "sk-ant-api03-PROBEhelperkey"
            "00000000000000000000000000000000000000000000000000000000000000000000000AA",
            "sk-ant-api03-PROBEprojhelper",
            "sk-ant-api03-PROBEprojhelper"
            "0000000000000000000000000000000000000000000000000000000000000000000000AA",
            "sk-ant-api03-PROBEsettingsenv",
            "sk-ant-api03-PROBEsettingsenv"
            "000000000000000000000000000000000000000000000000000000000000000000000AA",
            "sk-ant-oat01-PROBEauthtoken",
        ),
    ),
    Allowance(
        "anthropic",
        "the subscription fixture's token pair. `tests/fixtures.py` writes a "
        "credentials file shaped like the one a logged-in operator has, because "
        "the startup assertion reads that shape; both values say what they are.",
        ("sk-ant-oat01-synthetic-test-value", "sk-ant-ort01-synthetic-test-value"),
    ),
    Allowance(
        "url_password",
        "the sentinel passwords the suite builds connection strings out of. Each "
        "is a literal chosen to be recognisable in a failure message, and the "
        "point of most of the tests holding one is that it never reaches a log.",
        (
            "hunter2",
            "p%40ss%2Fword",
            "pw",
            "rk",
            "s3cr3t-agent",
            "s3cr3t-runtime",
            "s3cr3t-sentinel",
            "secret",
            "unused",
        ),
    ),
    Allowance(
        "url_password",
        "placeholders in documentation and in the console, where the password is "
        "the part deliberately not written: the README elides it and the operator "
        "UI renders the substitution it will make.",
        ("...", "{SECRET}"),
    ),
    Allowance(
        "jwt",
        "the `jwt` redaction rule's own probe, in the migration that registers "
        "it. A rule stored with a string it must match is the reason that rule "
        "can be trusted, and the string has to be a token to serve.",
        ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.c2lnbmF0dXJlX2hlcmU",),
    ),
    Allowance(
        "bearer",
        "synthetic Authorization values planted so a stripping, sealing or "
        "redaction step can be watched removing something. A marker that was not "
        "credential-shaped would be removed by nothing and prove nothing.",
        (
            "Bearer RK-SYNTHETIC-CREDENTIAL-3f9a",
            "Bearer aaaaaaaaaaaaaaaaaaaaaaaa",
            "Bearer bbbbbbbbbbbbbbbbbbbbbbbb",
            "Bearer rk2SyntheticCanary0123456789",
            "Bearer sk-live-not-in-a-log",
            "Bearer synthetic-subscription-fixture",
        ),
    ),
)


class Finding(NamedTuple):
    """A shaped credential, said without saying it."""

    rule: str
    path: str
    line: int
    length: int

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}, {self.length} characters"


def rules() -> dict[str, Rule]:
    return {rule.name: rule for rule in RULES}


def declared() -> dict[str, set[str]]:
    """Per rule, every literal that is not a finding.

    What a rule finds in its own probe is one of them, and has to be: this file
    is in the tree the scan reads, so a rule that could not clear the string it
    is written against would report its own source as a leak.
    """
    allowed: dict[str, set[str]] = {rule.name: {rule.probed()} for rule in RULES}
    for allowance in ALLOWED:
        allowed.setdefault(allowance.rule, set()).update(allowance.literals)
    return allowed


def scan_text(text: str, path: str, seen: dict[str, set[str]] | None = None) -> list[Finding]:
    """Every shaped credential in one file's text that nothing declares.

    `seen` collects the literals that were allowed, so the caller can tell an
    allowance still doing work from one that outlived its fixture.
    """
    allowed = declared()
    findings = []
    for rule in RULES:
        for match in rule.pattern.finditer(text):
            literal = rule.identifying(match)
            if literal in allowed[rule.name]:
                if seen is not None:
                    seen.setdefault(rule.name, set()).add(literal)
                continue
            findings.append(
                Finding(rule.name, path, text.count("\n", 0, match.start()) + 1, len(literal))
            )
    return findings


def scan_file(path: Path, root: Path, seen: dict[str, set[str]] | None = None) -> list[Finding]:
    """One file, read as bytes and matched as latin-1.

    Every byte sequence decodes under latin-1, so a scan that decoded as UTF-8
    would refuse exactly the files whose encoding somebody had reason to hide
    something in. The rules are ASCII shapes, which is what makes reading an
    image this way harmless rather than clever.
    """
    named = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    try:
        size = path.stat().st_size
    except OSError as error:
        raise SecretsError(f"{named}: {error}") from error
    if size > CEILING:
        raise SecretsError(f"{named}: {size} bytes is past the {CEILING} this scan reads")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise SecretsError(f"{named}: {error}") from error
    return scan_text(data.decode("latin-1"), named, seen)


def publishable(root: Path = CHECKOUT) -> list[Path]:
    """Every file in a checkout that a clone would carry.

    Tracked *and* untracked-but-unignored: a file nobody has committed yet is a
    file the next `git add` takes, and the moment to find a credential in one is
    before that rather than after.
    """
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if listed.returncode:
        raise SecretsError(f"{root} is not a checkout this can list: {listed.stderr.strip()}")
    return [root / name for name in listed.stdout.split("\0") if name]


def walk(root: Path) -> list[Path]:
    """Every file under a directory a run produced, or the file itself."""
    if root.is_file():
        return [root]
    if not root.is_dir():
        raise SecretsError(f"{root} is neither a file nor a directory")
    return sorted(item for item in root.rglob("*") if item.is_file())


def check(roots: tuple[Path, ...] = (), checkout: Path = CHECKOUT) -> str:
    """The gate. Returns the report, or raises with every reason it failed."""
    seen: dict[str, set[str]] = {}
    findings: list[Finding] = []
    counted = 0

    for path in publishable(checkout):
        # A tracked file can be a deleted one still in the index. It is not in
        # the clone the next person makes either, so it is nothing to report.
        if path.is_file():
            counted += 1
            findings.extend(scan_file(path, checkout, seen))
    for root in roots:
        for path in walk(root):
            counted += 1
            findings.extend(scan_file(path, root if root.is_dir() else root.parent, seen))

    problems = [str(finding) for finding in findings]
    for allowance in ALLOWED:
        for literal in allowance.literals:
            if literal not in seen.get(allowance.rule, ()):
                problems.append(
                    f"{allowance.rule}: the declared literal of {len(literal)} characters "
                    f"beginning {literal[:8]!r} is in nothing this scanned, so the "
                    f"allowance forgives nothing and is now the only thing that could"
                )
    if problems:
        raise SecretsError("\n".join(problems))
    return (
        f"secrets ok: files={counted} rules={len(RULES)} "
        f"allowances={sum(len(item.literals) for item in ALLOWED)}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        help="directories a run produced -- build contexts, generated fixtures, "
        "logs, reports, evidence bundles. The checkout is always scanned.",
    )
    arguments = parser.parse_args(argv)
    try:
        print(check(tuple(arguments.roots)))
    except (SecretsError, OSError) as error:
        print(f"secrets failed:\n{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
