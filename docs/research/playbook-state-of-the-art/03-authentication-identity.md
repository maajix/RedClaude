# 03 - Authentication and identity

Scope: the eight playbooks `authentication`, `oauth`, `jwt-jose`, `webauthn`,
`identity-lifecycle`, `identity-parsing`, `workload-identities`, `secrets`,
read at commit `1e39069` on 2026-08-21. All external research below was fetched
between 2026-08-21 and is cited with full URLs and publication dates where the
page stated one. Three pages could not be fetched and are marked as such in
"Sources consulted"; nothing in this document rests on them alone.

Framing: every technique described here is for an authorized engagement against
a Program that has granted permission for the surface in question. Where a
technique cannot be performed without touching a third party or an account the
engagement does not own, the safe substitute is named in "Safety limits worth
keeping".

## What we already cover well

* **A control on every claim.** All eight playbooks establish that the endpoint
  reaches an authentication decision at all before reading a variant. The
  wrong-secret / broken-signature / no-credential control is the single strongest
  thing in this cluster and it is what separates these texts from a checklist.
  `jwt-jose` step 2, `identity-parsing` step 3 and `secrets` step 3 are the best
  examples.
* **Credential presence and type juggling** (`authentication`): omitted, empty,
  wrong-JSON-type and empty-signature variants, one at a time, with an explicit
  refusal to iterate values. This is the correct shape and it still lands.
* **Callback-to-browser binding** (`oauth`): completing a flow in one profile and
  delivering the callback to a clean profile is exactly the right reading for
  `state`/verifier binding, and the account-linking variant in step 4 is a real
  bug class that many methodologies miss.
* **Genuine-token-out-of-scope** (`jwt-jose`): the `aud` / `scope` / `iss` / `exp`
  / lower-privilege-principal matrix is a strong, safe, high-yield family, and
  reading which end of the scale each variant matches is better than status
  matching.
* **Step-up factor enforcement** (`webauthn`): omit, empty, reorder, client-named
  factor, replayed assertion, plus the insistence that the *state change* is the
  evidence rather than the status code. The "client names which factor ran" case
  is genuinely under-tested in the wild.
* **Server-side session survival** (`identity-lifecycle`): three endings, one at a
  time, with the re-lease check in step 4 and the propagation-delay caveat. The
  re-lease check is a subtlety most testers get wrong.
* **Classic XSW with a signature control** (`identity-parsing`): three wrapping
  shapes and a refusal to name subjects the Program does not own.
* **Tenant selection versus tenant proof** (`workload-identities`): the
  duplicated-header and omitted-header variants are good, and requiring
  verification from the second tenant's own side before calling it a differential
  is the right bar.
* **Credential candidates proven by use** (`secrets`): validating each candidate
  against the route the document itself names, reporting the negatives as the
  control, redacting, and reporting live keys early for rotation. This is better
  than every "regex the bundle" methodology in circulation.
* **Cross-cutting discipline**: leased credentials never printed, no enumeration
  of user identifiers, no third-party key exercise, evidence bundles redacted on
  export, and explicit handoffs to neighbouring classes instead of claim
  inflation.

## Missing techniques (ranked by expected yield on a real bounty program)

### 1. Password reset and email-change flow attacks

`authentication` step 6 hands enrolment and recovery to
`authentication.recovery_flow`, and a grep over `bb:outputs` across all 48
playbooks shows **no playbook emits that class**. The single highest-yield
account-takeover family on a real program is therefore unreachable by the
harness. The family is: reset token not invalidated on use or on password
change, reset token still valid after email change, token leaked to a third
party via `Referer` on the reset landing page, token predictable or short,
reset link host taken from the `Host` / `X-Forwarded-Host` header, email change
that does not re-verify the new address or does not require the current
password, and reset that does not clear other sessions or MFA enrolment. Host
header poisoning is an old technique (the PortSwigger Academy material and the
2017 HackerOne report below) that keeps landing in 2024-2025 CMS and framework
advisories.
Belongs in: **new playbook: `account-recovery`** (emits
`authentication.recovery_flow`).
Would have to observe: two mailboxes the engagement owns, the reset link as
generated (not as delivered), the token's validity across a second use and
across a credential change, the `Host`-family headers the app echoes into the
link, and the outbound `Referer` from the reset landing page. The existing
`callback_interaction` evidence kind is the right carrier for a poisoned host
that resolves to our own collaborator.
Sources: https://portswigger.net/web-security/host-header/exploiting/password-reset-poisoning (undated, living Academy topic); https://hackerone.com/reports/226659 (disclosed 2017, technique still landing); https://github.com/joomla/joomla-cms/issues/43873 (Joomla password reset poisoning, reported 2024-07-29); https://github.com/kanboard/kanboard/security/advisories/GHSA-2ch5-gqjm-8p92 (Kanboard, undated advisory); https://github.com/advisories/GHSA-fqh6-6h6c-366m (@perfood/couch-auth host header injection leaking the reset token).

### 2. Mutable-claim identity binding (the nOAuth class)

A relying party that identifies the user by the `email` claim rather than by
`iss` + `sub` can be logged in as anyone whose email an attacker can set in a
tenant or IdP the attacker controls. Entra ID permits unverified `mail`
attributes to support guest scenarios, so the attacker never has to control the
victim's mailbox. Disclosed in 2023 and *still* returning results: Semperis
tested 104 self-signup OIDC apps from the Entra App Gallery in 2025 and found 9
vulnerable. Grafana shipped the same defect against Azure AD multi-tenant apps.
Doyensec calls the general form the "mutable claims attack". This is a two-line
test with an enormous payoff and our cluster cannot express it: `identity-parsing`
is the only playbook that emits `authentication.federation_trust` and its
`bb:triggers_all` requires `tech_saml`.
Belongs in: **`oauth`** as a second output class, or extend
**`identity-parsing`** to fire on OIDC as well as SAML.
Would have to observe: two identities in two tenants/IdPs the engagement owns,
the claim set of the `id_token` the target consumes, and which account the
target's own identity route reports after the flow completes.
Sources: https://www.descope.com/blog/post/noauth (Omer Cohen, Descope, 2023-06-20); https://www.semperis.com/blog/noauth-abuse-alert-full-account-takeover/ (Eric Woodruff, Semperis, 2025-06-26); https://blog.doyensec.com/2025/01/30/oauth-common-vulnerabilities.html (Doyensec, 2025-01-30); https://github.com/grafana/bugbounty/security/advisories/GHSA-gxh2-6vvc-rrgp (Grafana Azure AD OAuth account takeover advisory).

### 3. redirect_uri validation flaws and code/token exfiltration

Our `oauth` playbook explicitly declines this: step 5 says "`redirect_uri`
handling is a neighbouring question this Playbook does not answer". It is the
most productive question in OAuth. The concrete variants are path append, path
traversal (`/oauth/callback/../../x`), case shifting, added query or fragment,
duplicated `redirect_uri` parameter (parameter pollution), userinfo/authority
tricks such as `https://legit.com&@evil.net#@x.evil.net`, wildcard subdomain
plus a dangling-DNS subdomain takeover, and `localhost.evil.net` where
`localhost` is allowed. RFC 9700 now *requires* exact string matching, which
makes any deviation a citable finding rather than an argument.
Belongs in: **`oauth`** (new output class alongside `session_handling.fixation`).
Would have to observe: the registered callback set (from a successful flow), the
authorization endpoint's response to each mutated `redirect_uri`, and whether a
code or token actually arrives at the mutated destination rather than only that
an error page changed.
Sources: https://portswigger.net/web-security/oauth (Academy, living); https://www.rfc-editor.org/info/rfc9700/ (RFC 9700, BCP, published January 2025); https://blog.doyensec.com/2025/01/30/oauth-common-vulnerabilities.html (Doyensec, 2025-01-30); https://dl.acm.org/doi/fullHtml/10.1145/3627106.3627140 ("OAuth 2.0 Redirect URI Validation Falls Short, Literally", ACSAC 2023; page returned 403, findings taken from the search index: 6 IdPs vulnerable to path confusion, 10 to parameter pollution).

### 4. Non-happy-path token retention and third-party gadget leakage ("dirty dancing")

Frans Rosén's technique: force the flow onto an error or intermediate page that
still holds the code or token in its URL, then read that URL through a gadget on
the page that is not an XSS. The gadgets are `postMessage` listeners with weak
origin checks that echo `location.href`, chat/analytics widgets that ship the
page URL to a vendor API, and `Referer` leakage from a third-party asset. The
entry points are `response_type` / `response_mode` switching (asking for
`code,id_token` so the value lands in the fragment), deliberately invalid
`state` so the client aborts *after* the value is in the URL, and the
redirect_uri quirks above. It won PortSwigger's Top 10 for 2022 and the class is
still the standard way to turn "no XSS" into a one-click takeover.
Belongs in: **`oauth`**, with a cross-reference to `browser-messaging`.
Would have to observe: the browser's final URL on every non-success path of the
flow, the set of third-party origins loaded on those pages, and the messages
those listeners return. `browser-evidence` is already a declared skill on this
playbook, so the runtime support exists.
Sources: https://labs.detectify.com/writeups/account-hijacking-using-dirty-dancing-in-sign-in-oauth-flows/ (Frans Rosén, Detectify Labs, 2022-07-06; older but still the reference technique); https://portswigger.net/research/top-10-web-hacking-techniques (index of the annual lists).

### 5. Scope upgrade and client confusion at the token and userinfo endpoints

Two adjacent defects our `jwt-jose` playbook nearly reaches but does not send.
(a) Scope upgrade: add or widen `scope` on the *token request* (RFC says the
authorization server must ignore or reject it there) and see whether the issued
access token carries privileges the user never consented to. (b) Client
confusion / "pass the token": present an access token minted for client A to
client B's backend, or to a `/userinfo`-style endpoint, and see whether the
consumer checks the token's `client_id` / `aud` before trusting it. Salt Labs
found the second form across Grammarly, Vidio and Bukalapak and estimated
thousands of sites. Our playbook tests a *genuine* token at a second audience,
which is the same shape, but only within one application's own routes and never
at the token endpoint.
Belongs in: **`jwt-jose`** (extend step 3) and **`oauth`**.
Would have to observe: the scope actually granted on the returned token as
opposed to the scope requested, and a second client_id in the Program's scope.
Sources: https://blog.doyensec.com/2025/01/30/oauth-common-vulnerabilities.html (Doyensec, 2025-01-30, "Scope Upgrade Attack" and "Client Confusion Attack"); https://salt.security/blog/oh-auth-abusing-oauth-to-take-over-millions-of-accounts (Salt Labs, 2023); https://portswigger.net/web-security/oauth (Academy, flawed scope validation).

### 6. SAML parser differentials, attribute pollution and void canonicalization

Our `identity-parsing` playbook implements 2012-era XSW: add a second assertion,
wrap the signed one, duplicate the subject. 2025 produced a whole new generation
that defeats libraries hardened against exactly those three shapes:
- **Parser differentials** (ruby-saml used REXML and Nokogiri in sequence; a
  `Signature` hidden in `StatusDetail` is seen by one parser and not the other),
  CVE-2025-25291 / CVE-2025-25292, and the incomplete fix CVE-2025-66567.
- **Attribute pollution**: `ID="1"` beside `samlp:ID="2"` resolved differently by
  namespace-agnostic getters.
- **Namespace confusion**: REXML treating `xml:xmlns` as an ordinary attribute so
  the real signature becomes invisible to one XPath and visible to another.
- **Void canonicalization** (novel): an unresolvable relative URI in a namespace
  declaration makes canonicalization return an empty string, so the digest is
  computed over nothing, and a valid signature over the empty string is obtained
  from publicly served signed IdP metadata or an error response.
The tell is what Fedotkin calls "impossible XSW": a `DigestValue` that should
mathematically fail and does not. samlify (CVE-2025-47949) shows the plain
unsigned-second-assertion form is still shipping too.
Belongs in: **`identity-parsing`** (rewrite step 4).
Would have to observe: which XML library the relying party uses (from error
text, headers or the stack), a second signed artefact from the same IdP
(metadata, an error response) to source a valid-signature-over-something block,
and the identity route's answer after each variant.
Sources: https://portswigger.net/research/the-fragile-lock (Zakhar Fedotkin, PortSwigger Research, 2025-12-10); https://github.blog/security/sign-in-as-anyone-bypassing-saml-sso-authentication-with-parser-differentials/ (Peter Stöckli, GitHub Security Lab, 2025-03-12); https://github.com/advisories/GHSA-754f-8gm6-c4r2 (CVE-2025-25292); https://advisories.gitlab.com/gem/ruby-saml/CVE-2025-66567/ (CVE-2025-66567, incomplete fix); https://socradar.io/blog/cve-2025-47949-samlify-authentication-bypass-flaw/ (samlify CVE-2025-47949, CVSS 9.9).

### 7. JWT key-sourcing forgery: jku, x5u, embedded jwk, kid injection

Our `jwt-jose` playbook allows `alg=none`, HMAC-over-published-public-key and
`kid` repointing, but only "where the target's own material provides the key",
and step 6 forbids anything else. That rule excludes the entire modern forgery
family, which does not need any of the target's key material: point `jku` or
`x5u` at a JWKS we host, embed a `jwk` we generated in the header, or abuse
`kid` as a path (`../../dev/null` with an empty-key HMAC) or as a SQL/LDAP
injection sink. These are safe: the only third party involved is our own
collaborator. The detection signal is an outbound fetch, which is precisely what
the existing `callback_interaction` evidence kind records.
Belongs in: **`jwt-jose`** (new step, and a loosening of the step 6 ceiling for
keys we host ourselves).
Would have to observe: an outbound HTTP fetch from the target to our collaborator
carrying the `jku`/`x5u` path, and whether the token signed with our key is then
honoured.
Sources: https://portswigger.net/web-security/jwt (Academy, living; covers jwk/jku/kid); https://www.rfc-editor.org/info/rfc9700/ (RFC 9700, January 2025, on key-source constraints); https://portswigger.net/web-security/oauth/openid (Academy: arbitrary `jwks_uri` on a dynamically registered client).

### 8. OTP and MFA enforcement beyond an assertion-shaped factor

`webauthn` covers the assertion-shaped second factor well but the commodity
bounty findings are on the OTP path: response manipulation (flip `"success":
false` to `true`, or 4xx to 200, and see whether the *next* request is
authorized), OTP not bound to the identity that requested it (accept the code
issued for account A on account B), OTP reusable across attempts or after
expiry, OTP verification racing an email/phone change so the code sent to the
old address validates the new one, 2FA disabled by a password reset or an email
change, and backup/recovery codes that skip the factor entirely. Separately,
Proofpoint documented a *server-side* downgrade against Entra ID where a proxy
spoofs an unsupported browser so the IdP stops offering passkeys, which
generalises to: enumerate every alternative factor the login page will offer
when the strong one is declined.
Belongs in: **`webauthn`** (rename the reading to factor enforcement generally)
or **new playbook: `otp-enforcement`**.
Would have to observe: the response body the client branches on, a second owned
identity to cross-present codes, and the list of alternative factors the server
offers when the primary one is refused.
Sources: https://noorhomaid.medium.com/bug-bounty-writeup-2f-otp-bypass-on-registeration-via-response-manipulation-2e53573ffa4c (OTP bypass via response manipulation); https://github.com/tuhin1729/Bug-Bounty-Methodology/blob/main/2FA.md (2FA bypass technique catalogue); https://thehackernews.com/2025/10/how-attackers-bypass-synced-passkeys.html (Proofpoint downgrade against Entra ID, October 2025).

### 9. Cross-IdP impersonation and unverified second SSO method

Push Security's technique: the target's primary IdP is hardened, so the attacker
registers the victim's *corporate email* at a different IdP (Apple, Google,
Facebook) and uses "Sign in with X" on a downstream SaaS app that keys accounts
on the email. Push found 60% of tested apps do not require re-verification when
a new SSO method is added to an existing account. The 2024 Zendesk case chained
email spoofing plus JIT provisioning into hundreds of organisations' Slack
tenants, and a Google Workspace domain-verification bug let new accounts sign in
to downstream apps before the domain was verified. This is the "linking" half
of technique 2 and our `oauth` playbook mentions account linking only in the
fixation context.
Belongs in: **`oauth`** or the new federation playbook.
Would have to observe: which IdPs the login page offers, whether adding a second
IdP to an existing owned account requires the current password or a mail
confirmation, and whether the account after linking is the same account object.
Sources: https://pushsecurity.com/blog/cross-idp-impersonation/ (Dan Green, Push Security, 2024-11-19); https://www.securing.pl/en/the-year-in-review-the-most-interesting-single-sign-on-vulnerabilities-of-2024/ (2024 SSO round-up: Zendesk JIT chain, Google Workspace verification bypass); https://www.microsoft.com/en-us/msrc/blog/2022/05/pre-hijacking-attacks and https://arxiv.org/pdf/2205.10174 (account pre-hijacking, May 2022: classic-federated merge and non-verifying-IdP variants; older but the root cause is the same unverified identifier).

### 10. SCIM and just-in-time provisioning abuse

Doyensec's 2025 study is the only systematic public work here and every class it
names is a bounty-grade finding: SCIM endpoints reachable unauthenticated (a
Casdoor case allowed an unauthenticated POST to create an admin whose domain
matched an internal one), SCIM secrets that survive a base-URL change so the
integration can be pointed at an attacker's server, re-provisioning fallbacks
that revive a deprovisioned or banned user when an innocuous field is patched,
excessive attribute mapping that lets a SCIM Group ID become an internal role
name (superadmin), and SCIM email changes that bypass the verification flow
required everywhere else. Nothing in our cluster looks at provisioning at all.
Belongs in: **new playbook: `provisioning-scim`**.
Would have to observe: a `/scim/v2/` surface, an owned tenant with SCIM enabled,
the internal user object before and after a PATCH, and whether a deprovisioned
identity answers again.
Sources: https://blog.doyensec.com/2025/05/08/scim-hunting.html (Francesco Lacerenza, Doyensec, 2025-05-08).

### 11. PKCE enforcement, code single-use and authorization code injection

RFC 9700 makes PKCE (or an OIDC `nonce`) mandatory against code injection, and
downgrade is the practical attack: strip `code_challenge` and
`code_challenge_method` from the authorization request and see whether the
server still issues a code that the token endpoint will exchange without a
`code_verifier`; or send a wrong/absent verifier at exchange time.
CVE-2024-23647 is exactly this in authentik. The neighbouring checks are code
single-use (replay the same `code` twice and see whether a second token comes
back) and code lifetime. Our `oauth` playbook records whether `code_challenge`
is *present* in step 1 and never tests whether it is *enforced*.
Belongs in: **`oauth`** (extend step 3).
Would have to observe: the token endpoint's answer to an exchange without a
verifier, and to a second exchange of an already-redeemed code.
Sources: https://github.com/goauthentik/authentik/security/advisories/GHSA-mrx3-gxjx-hjqj (CVE-2024-23647, PKCE downgrade in authentik); https://www.rfc-editor.org/info/rfc9700/ (RFC 9700, January 2025); https://blog.doyensec.com/2026/03/05/mcp-nightmare.html (Doyensec, 2026-03-05, referencing CVE-2025-4144 PKCE bypass and CVE-2025-4143 redirect_uri validation in workers-oauth-provider).

### 12. OIDC dynamic client registration and request-by-reference SSRF

If `/register` accepts an unauthenticated POST, the attacker controls
`redirect_uri` (defeating technique 3 entirely), plus a set of URLs the
authorization server will fetch itself: `logo_uri`, `jwks_uri`,
`sector_identifier_uri`, `request_uri`. Those are second-order SSRF into the
identity provider, which usually sits deeper in the network than the app.
`request_uri` additionally lets authorization parameters be passed by reference,
bypassing whatever validation runs on the query string. This has moved from a
lab curiosity to a live surface because MCP/agent deployments turned DCR on by
default, and the November 2025 MCP spec revision introduced CIMD partly in
response.
Belongs in: **`oauth`** (new step), cross-referenced from `ssrf-url-routing`.
Would have to observe: the presence of a registration endpoint in the OIDC
discovery document, the HTTP status of an unauthenticated registration, and an
outbound fetch to our collaborator (`callback_interaction` again).
Sources: https://portswigger.net/web-security/oauth/openid (Academy: unprotected dynamic client registration, request_uri by reference); https://portswigger.net/web-security/oauth/openid/lab-oauth-ssrf-via-openid-dynamic-client-registration (Academy lab); https://www.descope.com/blog/post/dcr-hardening-mcp (DCR hardening for MCP servers); https://nhimg.org/articles/cimd-vs-dcr-for-mcp-client-registration-in-2025/ (CIMD vs DCR, 2025 spec change).

### 13. Device code grant and cross-device flows

The IETF published a whole BCP for this in 2026 (RFC 10027 / BCP 247) because
the channel between the initiating device and the authorizing device is
unauthenticated, so the attacker can start a flow and social-engineer a victim
into approving *their* device. Proofpoint tracked a surge from September 2025
onward against Microsoft 365 with QR-code lures and tooling (SquarePhish2,
Graphish). For an authorized web engagement the testable server-side questions
are: does the target expose a `device_authorization_endpoint` at all, how long
is the user code and how long does it live, is it single-use, is it bound to any
proximity or session signal, is the consent screen specific about which client
is asking, and is there a deny-list on repeated code reuse.
Belongs in: **`oauth`** (a read-only recon step is enough and needs no approval),
or **new playbook: `cross-device-auth`**.
Would have to observe: the OIDC discovery document, one device-authorization
response (code, `expires_in`, `interval`), and whether polling the token endpoint
after the code is consumed once succeeds again.
Sources: https://www.rfc-editor.org/info/rfc10027/ (RFC 10027, BCP 247, "Best Current Practice for Security of Cross-Device Flows", 2026); https://datatracker.ietf.org/doc/draft-ietf-oauth-cross-device-security/13/ (working-group draft history); https://www.proofpoint.com/us/blog/threat-insight/access-granted-phishing-device-code-authorization-account-takeover (Proofpoint Threat Research, 2025-12-18, campaign timeline September to December 2025).

### 14. WebAuthn relying-party ceremony validation

Our `webauthn` playbook tests whether the factor is *required*. It does not test
whether the assertion is *validated*. The RP-side checks that get skipped in
practice: the `origin` and `rpId` inside `clientDataJSON` are not compared
against the RP's own origin, the `challenge` is not one the server issued or is
not consumed, `type` is not checked (`webauthn.create` accepted where
`webauthn.get` is expected), the signature counter is ignored, user verification
(`UV` flag) is not required when the policy says it is, and the credential is not
bound to the user handle so credential A can authenticate user B. Registration
is a separate ceremony we do not touch at all: can an additional passkey be
enrolled on an owned account without a step-up, which is the persistence half of
every passkey takeover. The 2025-2026 passkey research (SquareX at DEF CON,
SpecterOps "pass-the-passkey") is mostly endpoint-side and out of scope for a web
bounty, but it points at the same RP-side gaps.
Belongs in: **`webauthn`** (new step).
Would have to observe: the raw assertion fields the client posts, a second owned
account with its own credential, and a server-issued challenge to replay.
Sources: https://www.securityweek.com/passkey-login-bypassed-via-webauthn-process-manipulation/ (SquareX at DEF CON, 2025-08-14 weekend; WebAuthn API hijack, forged registration and login); https://thehackernews.com/2026/08/new-passkey-attacks-can-recover-synced.html (SpecterOps pass-the-passkey, August 2026, not fetched directly, see Sources consulted); https://thehackernews.com/2025/10/how-attackers-bypass-synced-passkeys.html (synced-passkey bypass overview, October 2025).

### 15. CI-to-cloud OIDC federation trust policies

Our `workload-identities` playbook tests one thing: a tenant header on a route.
The live workload-identity bug in 2024-2026 is the trust policy on the cloud
side: an AWS IAM role whose OIDC condition checks only `aud`
(`sts.amazonaws.com`) and not `sub`, so *any* GitHub Actions workflow anywhere
can assume it; or a `sub` condition with an organisation wildcard
(`repo:acme/*:*`) so any repo or any feature branch in the org gets production
credentials, bypassing branch protection and required reviewers entirely. Tinder
Security Labs released a black-box scanner for the AWS form. The same shape
exists in GCP Workload Identity Pool provider conditions and Azure federated
credentials, and in Kubernetes when a projected service-account token is not
audience-bound.
Belongs in: **`workload-identities`** (new step and a second output class), where
the Program names the cloud accounts.
Would have to observe: a role ARN or workload-identity-pool provider the Program
discloses, and an OIDC token this run can legitimately mint from a repository the
engagement owns.
Sources: https://www.lifeattinder.com/blog/identifying-vulnerabilities-in-github-actions-aws-oidc-configurations (Tinder Security Labs: Rojan Rijal, Johnny Nipper, Tanner Emek; page carried no date); https://github.com/TinderSec/oidc-scanner-aws (the released scanner); https://medium.com/@sadi.zane/exploiting-organisation-wildcards-in-oidc-trust-policies-a98eda04fb46 and https://medium.com/@sadi.zane/exploiting-branch-wildcards-in-oidc-trust-policies-51bd4e9a1e37 (Sadi Zane, wildcard exploitation walk-throughs); https://www.systemshardening.com/articles/kubernetes/service-account-tokens/ (projected token audience binding).

### 16. Refresh tokens, revocation propagation and sender-constrained tokens

`identity-lifecycle` measures session survival. It does not measure the two
things RFC 9700 actually mandates: refresh token rotation with reuse detection
(replay a rotated refresh token and see whether the family is revoked or whether
a fresh access token comes back), and sender-constrained access tokens (DPoP or
mTLS) so a stolen bearer is useless off the client. Add: does revoking an OAuth
grant or an application password kill the tokens already issued under it, and
does an admin-side session revocation propagate to the API gateway as well as to
the web app.
Belongs in: **`identity-lifecycle`** (extend step 3's list of endings).
Would have to observe: a refresh token this run obtained itself from an issuance
route, and a grant-revocation control the target exposes.
Sources: https://www.rfc-editor.org/info/rfc9700/ (RFC 9700, January 2025: refresh token rotation, reuse detection, sender-constrained tokens); https://workos.com/blog/oauth-best-practices (readable summary of the RFC's requirements).

### 17. Legacy or parallel identity API divergence

The Entra ID Actor-token issue (CVE-2025-55241, CVSS 10.0, reported 2025-07-14,
fixed 2025-07-23) is the archetype: a *legacy* API (Azure AD Graph) accepted a
token shape that the modern API validated properly, and failed to check the
originating tenant claim, so a token minted in the attacker's tenant
authenticated as a Global Administrator in anyone else's. Generalised into a
technique we can run: for every identity-bearing token, find the target's older
API version, its mobile API host, its GraphQL twin and its admin API, and
present the same token there. Our `workload-identities` playbook already has the
right instinct (one credential, two selectors) but only varies the tenant header
on one route.
Belongs in: **`workload-identities`** or **`jwt-jose`** (extend the "second
endpoint" variant to second *API surface*, not second scope).
Would have to observe: more than one API host or version for the same identity,
and a differential in what each accepts.
Sources: https://dirkjanm.io/obtaining-global-admin-in-every-entra-id-tenant-with-actor-tokens/ (Dirk-jan Mollema; page not fetched directly, see Sources consulted); https://thehackernews.com/2025/09/microsoft-patches-critical-entra-id.html (September 2025 write-up of CVE-2025-55241 with the disclosure timeline); https://www.securityweek.com/all-microsoft-entra-tenants-were-exposed-to-silent-compromise-via-invisible-actor-tokens-researcher/ (same, independent).

### 18. Long-input truncation and cache-key collisions in credential handling

Okta's own advisory: the DelAuth cache key was `bcrypt(userId + username +
password)`, bcrypt truncates at 72 bytes, so a username of 52 characters or more
pushed the password out of the hashed region and a previously cached
authentication could be replayed with any password. This is a cheap variant to
add to the existing `authentication` step 3 list, it costs one request, and it
generalises: over-long usernames, over-long passwords, unicode-normalising
identifiers, and null bytes in the identifier.
Belongs in: **`authentication`** (extend the step 3 variant list).
Would have to observe: nothing new; it is one more malformation of the same
request, and the existing three-way scale reads it correctly.
Sources: https://trust.okta.com/security-advisories/okta-ad-ldap-delegated-authentication-username/ (Okta, 2024-11-01, with the six exact preconditions).

### 19. Secret exposure beyond the served SPA bundle

`secrets` is triggered on `embedded_document` + `spa_surface` and reads one
served document. The volume findings live elsewhere: source maps (`.map` files
that restore pre-minified constants), an exposed `.git` directory or a stale
`.env`, CI artefacts (the ArtiPACKED race: GitHub Actions artefacts downloadable
while the run is still in progress, carrying `GITHUB_TOKEN` written into
`.git/config` by `actions/checkout`, and `ACTIONS_RUNTIME_TOKEN` with roughly six
hours of validity), and non-repository channels. GitGuardian's 2026 report puts
28.65 million new hardcoded secrets in public GitHub in 2025 (up 34%), 64% of
2022-leaked secrets still valid, and 28% of incidents now originating outside
code repositories.
Belongs in: **`secrets`** (widen the triggers and the "take the document as it
was served" step to a small set of document *kinds*), with the reachability half
staying in `attack-surface`.
Would have to observe: a source map alongside a bundle, a `.git/config` or `.env`
response that is not a 404, and (only where the Program's scope includes the
repository) workflow artefacts.
Sources: https://unit42.paloaltonetworks.com/github-repo-artifacts-leak-tokens/ (Yaron Avital, Unit 42, 2024-08-13, ArtiPACKED); https://blog.gitguardian.com/the-state-of-secrets-sprawl-2025/ (GitGuardian, March 2025: 23.8M secrets in 2024, 70% of 2022 secrets still valid); https://blog.gitguardian.com/the-state-of-secrets-sprawl-2026-pr/ (GitGuardian, 2026: 28.65M in 2025, +81% AI-service credentials, 28% of incidents outside repositories).

### 20. Agent and MCP OAuth proxies

New surface, growing fast, and our `agentic-ai` playbook is elsewhere in the
tree. The specific OAuth defects: an MCP server acting as an OAuth proxy uses one
static `client_id` against the upstream SaaS, so the upstream's consent cache
suppresses the consent screen and an attacker who completes a flow themselves can
hand the resulting URL to a victim for a one-click grant; no consent layer at the
MCP tier; state not bound to the session; raw upstream SaaS tokens passed through
as MCP tokens; DCR with no `redirect_uri` restriction; session cookies without a
`__Host-` prefix so a subdomain can inject them. Doyensec adds scope-namespace
collision across MCP servers and no defined access-invalidation mechanism.
Belongs in: **`oauth`** (the proxy shape) with a cross-reference from
`agentic-ai`.
Would have to observe: an MCP or agent-gateway authorization surface, its
`client_id` reuse across users, and whether the consent screen appears on a
second, different user's first authorization.
Sources: https://www.obsidiansecurity.com/blog/when-mcp-meets-oauth-common-pitfalls-leading-to-one-click-account-takeover (Obsidian Security, 2026-01-29, updated 2026-02-02); https://blog.doyensec.com/2026/03/05/mcp-nightmare.html (Francesco Lacerenza, Doyensec, 2026-03-05).

## What in our playbooks looks stale or weak

* **`oauth` reduces an entire protocol family to one leaf.** Its only output is
  `session_handling.fixation`, and step 5 explicitly declines `redirect_uri`.
  Techniques 3, 4, 5, 11, 12, 13 and 20 above all have no home. For a real
  engagement against an OAuth-bearing target this is the largest single gap in
  the cluster.
* **`jwt-jose`'s key ceiling is self-defeating.** Step 6 requires keys to come
  from "the target's own published material". `jku`, `x5u` and embedded `jwk`
  forgery use a key *we* generate and a JWKS *we* host on our own collaborator.
  Nothing about that touches a third party. The rule as written was aimed at not
  using somebody else's credential and it is currently blocking a safe,
  high-yield family.
* **`identity-parsing` is a 2012 playbook.** Its three variants are the shapes
  every hardened SAML library already rejects. The 2025 generation (parser
  differentials, attribute pollution, namespace confusion, void canonicalization)
  is what actually lands, and none of it is expressible. It is also keyed to
  `tech_saml` only, so OIDC `id_token` trust has no reading anywhere.
* **`authentication` hands recovery to a class no playbook emits.** The
  `authentication.recovery_flow` reference in step 6 is a dead end. Verified by
  grepping `bb:outputs` across all 48 playbooks.
* **`webauthn` assumes a step-up context and never validates the ceremony.** It
  reads whether the factor was required, never whether the assertion was checked,
  and never touches registration. It is also `mutates_account` +
  `approval_required` for its whole body, so an unattended run gets nothing.
* **`identity-lifecycle` only knows sessions.** No refresh tokens, no OAuth grant
  revocation, no token-family reuse detection, no sender-constrained tokens.
* **`workload-identities` is one header substitution.** It reads which tenant a
  workload token can *name*, not which trust policy will *mint* one for us, and
  not whether a legacy API surface accepts what the current one rejects.
* **`secrets` is narrowly triggered.** `embedded_document` + `read_method` +
  `spa_surface` means source maps, `.git`, `.env` and CI artefacts fall outside.
* **No `callback_interaction` evidence anywhere in this cluster.** The kind exists
  in the vocabulary and several of the strongest missing techniques (jku/x5u,
  `request_uri`, `logo_uri`, host-header reset poisoning) are naturally
  out-of-band. This is free capability we are not using.
* **Trigger vocabulary has no identity-specific hooks.** There is `tech_oauth`,
  `tech_saml`, `tech_jwt`, `tech_webauthn`, but nothing for OIDC discovery, a
  device-authorization endpoint, a SCIM surface or a recovery route. Several
  proposals below need a new trigger or an existing one stretched.
* **`bb:stale_after: 2027-03-15` across the cluster.** Not wrong, but the SAML
  and OAuth texts are already behind published 2025 research, so the date is
  giving false confidence.

## Concrete change proposals per playbook

* **`src/redkraken/playbooks/authentication/playbook.md`** - extend the step 3
  variant list with over-length identifiers and credentials (52+ character
  username, 72+ byte combined input, unicode-normalising identifier, null byte in
  the identifier), citing the bcrypt-truncation shape. Costs one request per
  variant and reads correctly against the existing three-way scale. Also fix the
  dangling reference in step 6 once `account-recovery` exists.
* **`src/redkraken/playbooks/oauth/playbook.md`** - this file needs to become
  three or four readings, not one. Minimum: (a) rewrite step 5 to stop declining
  `redirect_uri` and add a step that sends the eight canonical mutations and
  measures whether a code or token *arrives* at the mutated destination; (b) add
  a step for PKCE enforcement and code single-use (strip `code_challenge`;
  exchange without `code_verifier`; redeem the same code twice); (c) add a
  read-only recon step over the OIDC discovery document recording
  `registration_endpoint`, `device_authorization_endpoint`, `request_uri`
  support, and whether an unauthenticated POST to `/register` is accepted, which
  needs no approval and gives the operator the map; (d) add the mutable-claim
  reading (log in from a second owned tenant whose `email` claim matches the
  first identity, read which account answers) as a second output class.
* **`src/redkraken/playbooks/jwt-jose/playbook.md`** - rewrite the step 6 ceiling
  to permit key material *we* generate and host on our own collaborator, then add
  a step: `jku`/`x5u` pointed at our JWKS, an embedded `jwk` header, and `kid` as
  a path and as an injection sink. Declare `callback_interaction` in
  `bb:evidence` so the outbound fetch is the supporting evidence. Separately,
  extend the "second endpoint" variant in step 3 to a second *API surface*
  (older version, mobile host, GraphQL twin, admin API) for the legacy-divergence
  technique.
* **`src/redkraken/playbooks/webauthn/playbook.md`** - add a step between the
  current 2 and 3 that validates the ceremony rather than its presence: mutate
  `origin` and `rpId` in `clientDataJSON`, replay a stale or never-issued
  `challenge`, flip `type` between `webauthn.create` and `webauthn.get`, present
  a credential enrolled on a second owned account, and clear the UV flag. Add a
  registration-ceremony variant (enrol an extra authenticator on an owned account
  and record whether a step-up was demanded). Split the read-only half out so it
  runs without `approval_required`.
* **`src/redkraken/playbooks/identity-lifecycle/playbook.md`** - add refresh
  tokens and grants to step 3's list of endings: replay a rotated refresh token
  and record whether the token family is revoked; revoke an OAuth grant and
  replay the access token issued under it; and record whether the access token is
  sender-constrained (DPoP/mTLS) or a plain bearer. Keep the one-ending-per-
  reading rule.
* **`src/redkraken/playbooks/identity-parsing/playbook.md`** - rewrite step 4.
  Keep the three classic wrapping shapes as the first tier, then add the 2025
  tier: duplicate `ID` under different namespace prefixes (attribute pollution),
  redefine a reserved namespace declaration so the real signature is invisible to
  one XPath (namespace confusion), and an unresolvable relative URI in a
  namespace declaration to force canonicalization over an empty string (void
  canonicalization), sourcing a valid-signature-over-something block from the
  IdP's own published metadata. Add a step 2b recording which XML library the
  relying party appears to use. Widen `bb:triggers_all` so an OIDC `id_token`
  consumer can also be read for `authentication.federation_trust`.
* **`src/redkraken/playbooks/workload-identities/playbook.md`** - add a second
  reading for federation trust policies: where the Program names a role ARN or
  workload-identity pool, mint an OIDC token from a repository or workload the
  engagement owns and record whether the trust policy accepts it (missing `sub`
  condition, organisation wildcard, branch wildcard, `aud`-only). Keep the
  never-harvest rule for tokens; this reading mints its own.
* **`src/redkraken/playbooks/secrets/playbook.md`** - widen step 1 from "the
  embedded document" to a small enumerated set of document kinds: the bundle, its
  `.map` sibling, `.env`, `.git/config`, and any workflow artefact the Program's
  scope covers. Everything from step 2 onward already works unchanged, and the
  negatives-as-control discipline in step 4 is exactly what a wider net needs.
* **New playbook: `account-recovery`** (emits `authentication.recovery_flow`) -
  two owned mailboxes; the reset link as generated; token reuse after use, after
  a password change, after an email change; `Host` / `X-Forwarded-Host` /
  `X-Forwarded-Server` in the reset request with a collaborator hostname, read as
  a `callback_interaction`; outbound `Referer` from the reset landing page; and
  the email-change half (does it require the current credential, does it verify
  the new address before switching, does it invalidate sessions and MFA).
* **New playbook: `provisioning-scim`** - unauthenticated SCIM endpoint, attribute
  overreach into internal roles, re-provisioning of a deprovisioned identity via a
  benign PATCH, and an email change through SCIM that skips the verification the
  UI enforces.
* **New playbook or `oauth` step: `cross-device-auth`** - read-only measurement of
  a device-authorization endpoint: user-code entropy and lifetime, single-use,
  what the consent screen names, and whether polling succeeds twice.

## Safety limits worth keeping

* **Recovery flows must use two mailboxes the engagement owns.** Never trigger a
  reset for an address that belongs to a real user, even to observe rate
  limiting: the victim receives the mail. Safe substitute: two owned accounts,
  and where only one is provisioned, read the reset link's *construction* (host
  echo, token entropy, `Referer`) rather than its *delivery*.
* **Host-header reset poisoning must assert on our own collaborator.** The
  evidence is a DNS or HTTP hit on a hostname we control, or the link as rendered
  in our own inbox. Never poison a reset for somebody else's address, which mails
  an attacker link to a real person.
* **Never send an assertion, `id_token` or SCIM record naming a subject the
  Program does not own.** `identity-parsing` step 4 already states this and it
  must survive the rewrite: a successful wrapping variant *creates a session*, and
  creating one as a real user is an unauthorised login against a person. The
  mutable-claim reading (technique 2) has the same rule: the "victim" email must
  be a second identity we hold.
* **Device code and QR flows must never be presented to a human.** The entire
  published attack is social engineering against a real person. Safe substitute:
  measure the code's properties and the consent screen's specificity, and where a
  human step is unavoidable, the only human is the operator approving their own
  run.
* **`jku` / `x5u` / `request_uri` / `logo_uri` must point only at our own
  collaborator.** Pointing them at a third party turns the target into an
  attacker's proxy against a stranger. Never at an internal address the Program
  has not put in scope, and never at a cloud metadata endpoint outside scope.
* **Third-party keys are reported, never exercised.** `secrets` step 6 has this
  exactly right and it must be inherited by any widened version: a live vendor key
  found in a source map or a CI artefact is reported early for rotation and is
  never presented to the vendor's API.
* **CI-to-cloud federation testing only against roles the Program names.** Minting
  an OIDC token from a repository we own is safe; assuming a role in an account
  the engagement does not cover is unauthorised access to somebody's cloud.
  Safe substitute where the Program will not name accounts: read the trust policy
  if the target discloses it, and report the wildcard as a configuration finding
  without assuming the role.
* **SCIM is a write into a directory.** Any `provisioning-scim` playbook is
  `mutates_account` and `approval_required`, must record every attribute before it
  changes it, must restore it, and must never re-provision or deprovision an
  identity that is not ours.
* **Dynamic client registration must be cleaned up and must not be repeated.** One
  registration, deleted after the reading. Registering many is a denial-of-service
  against the authorization server's storage, which is the documented abuse.
* **Browser-side passkey attacks are out of scope for a web engagement.** The
  SquareX and SpecterOps techniques need a malicious extension, an XSS, or code
  execution on the user's endpoint. Safe substitute: test the relying party's
  server-side ceremony validation (technique 14), which finds the same class of
  trust failure without touching anyone's browser.
* **Identity-vendor platform bugs are not the Program's bug.** If a reading points
  at Entra ID, Okta or the IdP itself rather than at the target's use of it, it
  goes to the vendor's own disclosure channel and to the operator, not into the
  Program's report as a target finding.
* **Stop on lockout, captcha or 429.** `authentication` step 5 already says this.
  It applies with more force to recovery and OTP readings, where the defence
  being tripped can lock a real user's account.
* **No credential guessing anywhere.** Every technique above is a structural
  question about whether a check happens, not a search over a value space. The
  moment a reading iterates over candidate secrets, codes or identifiers it has
  become `rate_limiting` and the Program's rules of engagement decide it.

## Sources consulted

* https://portswigger.net/research/top-10-web-hacking-techniques-of-2025 - the 2025 annual list; confirmed that no authentication or identity technique made the top ten, and that SAML exploitation was the notable near-miss. Establishes where the community's attention actually is.
* https://portswigger.net/research/top-10-web-hacking-techniques - index of all annual lists; context for the 2022 "dirty dancing" win.
* https://portswigger.net/research/the-fragile-lock - Zakhar Fedotkin, 2025-12-10. The source for attribute pollution, namespace confusion and void canonicalization, and for the "impossible XSW" detection signal.
* https://github.blog/security/sign-in-as-anyone-bypassing-saml-sso-authentication-with-parser-differentials/ - Peter Stöckli, GitHub Security Lab, 2025-03-12. The REXML/Nokogiri parser differential and the attacker precondition (one valid signature from the same key).
* https://github.com/advisories/GHSA-754f-8gm6-c4r2 - CVE-2025-25292 advisory record.
* https://advisories.gitlab.com/gem/ruby-saml/CVE-2025-66567/ - the incomplete-fix follow-up CVE; no publication date was fetched from this page.
* https://socradar.io/blog/cve-2025-47949-samlify-authentication-bypass-flaw/ - samlify CVE-2025-47949, CVSS 9.9; evidence that plain unsigned-second-assertion injection still ships.
* https://www.descope.com/blog/post/noauth - Omer Cohen, Descope, 2023-06-20. Original nOAuth disclosure.
* https://www.semperis.com/blog/noauth-abuse-alert-full-account-takeover/ - Eric Woodruff, Semperis, 2025-06-26. The 2025 re-measurement: 104 Entra App Gallery apps tested, 9 vulnerable, and the exact tester-side detection method.
* https://github.com/grafana/bugbounty/security/advisories/GHSA-gxh2-6vvc-rrgp - a disclosed bug-bounty advisory of the same mutable-claim defect in a product our operators will recognise.
* https://blog.doyensec.com/2025/01/30/oauth-common-vulnerabilities.html - Jose Catalan and Szymon Drosdzol, Doyensec, 2025-01-30. The cleanest current taxonomy: CSRF/state, redirect URI, mutable claims, client confusion, scope upgrade, redirect scheme hijacking.
* https://blog.doyensec.com/2025/05/08/scim-hunting.html - Francesco Lacerenza, Doyensec, 2025-05-08. The only systematic public SCIM attack-surface work; source for technique 10 in full.
* https://blog.doyensec.com/2026/03/05/mcp-nightmare.html - Francesco Lacerenza, Doyensec, 2026-03-05. MCP authn/authz classes, scope namespace collision, and the CVE-2025-4143 / CVE-2025-4144 references.
* https://www.obsidiansecurity.com/blog/when-mcp-meets-oauth-common-pitfalls-leading-to-one-click-account-takeover - Obsidian Security, 2026-01-29 (updated 2026-02-02). The shared-`client_id` consent-cache bypass chain in full.
* https://labs.detectify.com/writeups/account-hijacking-using-dirty-dancing-in-sign-in-oauth-flows/ - Frans Rosén, Detectify Labs, 2022-07-06. Response-type switching, redirect_uri quirks, invalid-state token retention, and the postMessage/third-party gadget leakage catalogue.
* https://www.rfc-editor.org/info/rfc9700/ - RFC 9700, Best Current Practice for OAuth 2.0 Security, published January 2025. The citable authority for exact redirect_uri matching, mandatory PKCE or nonce, the `iss` response parameter against mix-up, refresh token rotation with reuse detection, and sender-constrained tokens.
* https://www.rfc-editor.org/info/rfc10027/ - RFC 10027 / BCP 247, Best Current Practice for Security of Cross-Device Flows, 2026. Threat model and mitigations (proximity, short-lived and single-use codes, code-reuse deny lists) for technique 13.
* https://datatracker.ietf.org/doc/draft-ietf-oauth-cross-device-security/13/ - the working-group draft behind RFC 10027, useful for the illicit-consent-grant framing.
* https://www.proofpoint.com/us/blog/threat-insight/access-granted-phishing-device-code-authorization-account-takeover - Proofpoint Threat Research, 2025-12-18. Campaign timeline September to December 2025 and the endpoints abused; the reason device-code deserves a playbook now rather than later.
* https://thehackernews.com/2025/10/how-attackers-bypass-synced-passkeys.html - October 2025. Proofpoint's server-side passkey downgrade against Entra ID (spoofed unsupported browser causing the IdP to stop offering passkeys), which is the testable half of the passkey research.
* https://www.securityweek.com/passkey-login-bypassed-via-webauthn-process-manipulation/ - SquareX at DEF CON, weekend of 2025-08-14. WebAuthn API hijack; classified above as out of scope for a web engagement, with the RP-side substitute named.
* https://thehackernews.com/2026/08/new-passkey-attacks-can-recover-synced.html - August 2026, SpecterOps "pass-the-passkey". Listed for completeness; not fetched directly, and nothing above depends on it.
* https://portswigger.net/web-security/oauth - Web Security Academy, living. The concrete redirect_uri bypass payloads, flawed state, flawed scope validation, unverified user registration, and the Referer/open-redirect exfiltration routes.
* https://portswigger.net/web-security/oauth/openid - Web Security Academy, living. Unprotected dynamic client registration and authorization requests by reference (`request_uri`).
* https://portswigger.net/web-security/oauth/openid/lab-oauth-ssrf-via-openid-dynamic-client-registration - the Academy lab that makes the DCR SSRF concrete.
* https://portswigger.net/web-security/jwt - Web Security Academy, living. The `jwk`, `jku`, `kid` and algorithm-confusion family that our jwt-jose ceiling currently excludes.
* https://portswigger.net/web-security/host-header/exploiting/password-reset-poisoning - Web Security Academy, living. The canonical reset-poisoning method.
* https://hackerone.com/reports/226659 - disclosed report, password reset link hijacking via Host header poisoning. Older (2017) and still the shape that lands in 2024-2025 advisories.
* https://github.com/joomla/joomla-cms/issues/43873 - Joomla password reset poisoning, reported 2024-07-29. Evidence the class is current.
* https://github.com/kanboard/kanboard/security/advisories/GHSA-2ch5-gqjm-8p92 and https://github.com/advisories/GHSA-fqh6-6h6c-366m - two more recent reset-poisoning advisories in maintained projects.
* https://github.com/goauthentik/authentik/security/advisories/GHSA-mrx3-gxjx-hjqj - CVE-2024-23647, PKCE downgrade in an identity provider. The concrete precedent for technique 11.
* https://pushsecurity.com/blog/cross-idp-impersonation/ - Dan Green, Push Security, 2024-11-19. Cross-IdP impersonation and the 60%-of-apps-do-not-re-verify figure.
* https://www.securing.pl/en/the-year-in-review-the-most-interesting-single-sign-on-vulnerabilities-of-2024/ - 2024 SSO round-up: UnOAuthorized, Okta FastPass bypass, Silver SAML, Azure tenant takeover via unregistered redirect URIs, DoubleClickjacking on consent prompts, Zendesk JIT chain, Google Workspace verification bypass, and the 2024 SAML CVE run in GitLab, GitHub Enterprise, Keycloak and Ivanti.
* https://www.microsoft.com/en-us/msrc/blog/2022/05/pre-hijacking-attacks and https://arxiv.org/pdf/2205.10174 - account pre-hijacking, May 2022. Classic-federated merge and non-verifying-IdP variants; older, but it is the same unverified-identifier root cause that nOAuth and cross-IdP impersonation exploit today.
* https://trust.okta.com/security-advisories/okta-ad-ldap-delegated-authentication-username/ - Okta, 2024-11-01. The bcrypt 72-byte truncation cache-key bypass with the six exact preconditions; source for technique 18.
* https://dirkjanm.io/obtaining-global-admin-in-every-entra-id-tenant-with-actor-tokens/ - Dirk-jan Mollema's Actor-token research (CVE-2025-55241). Not fetched directly; the technical detail above comes from the two independent write-ups below.
* https://thehackernews.com/2025/09/microsoft-patches-critical-entra-id.html - September 2025 report of CVE-2025-55241 with the disclosure timeline (reported 2025-07-14, fixed 2025-07-23).
* https://www.securityweek.com/all-microsoft-entra-tenants-were-exposed-to-silent-compromise-via-invisible-actor-tokens-researcher/ - independent corroboration of the Actor-token issue and the legacy-API root cause.
* https://unit42.paloaltonetworks.com/github-repo-artifacts-leak-tokens/ - Yaron Avital, Unit 42, 2024-08-13. ArtiPACKED: the artefact race window, `GITHUB_TOKEN` via `actions/checkout` credential persistence, and `ACTIONS_RUNTIME_TOKEN` validity.
* https://www.lifeattinder.com/blog/identifying-vulnerabilities-in-github-actions-aws-oidc-configurations - Tinder Security Labs (Rojan Rijal, Johnny Nipper, Tanner Emek); the page carried no publication date. Missing `sub` condition in IAM trust policies and the CloudTrail detection signal.
* https://github.com/TinderSec/oidc-scanner-aws - the black-box scanner released with that research.
* https://medium.com/@sadi.zane/exploiting-organisation-wildcards-in-oidc-trust-policies-a98eda04fb46 and https://medium.com/@sadi.zane/exploiting-branch-wildcards-in-oidc-trust-policies-51bd4e9a1e37 - Sadi Zane; step-by-step exploitation of organisation and branch wildcards in OIDC trust policies.
* https://www.systemshardening.com/articles/kubernetes/service-account-tokens/ - projected service-account tokens, audience binding, and the EKS/GKE identity-to-IAM escalation surface.
* https://blog.gitguardian.com/the-state-of-secrets-sprawl-2025/ - GitGuardian, March 2025. 23.8M secrets leaked on public GitHub in 2024 (+25% YoY), 70% of 2022 secrets still valid.
* https://blog.gitguardian.com/the-state-of-secrets-sprawl-2026-pr/ - GitGuardian, 2026. 28.65M new secrets in 2025 (+34%), AI-service credential leaks +81%, 64% of 2022 secrets still valid, 28% of incidents outside code repositories.
* https://salt.security/blog/oh-auth-abusing-oauth-to-take-over-millions-of-accounts - Salt Labs. The "pass the token" / token-verification-missing family across Grammarly, Vidio and Bukalapak.
* https://www.descope.com/blog/post/dcr-hardening-mcp and https://nhimg.org/articles/cimd-vs-dcr-for-mcp-client-registration-in-2025/ - why dynamic client registration became a live surface again, and the November 2025 CIMD spec change.
* https://workos.com/blog/oauth-best-practices - a readable restatement of RFC 9700's requirements, used only to cross-check the RFC summary.

**Could not fetch** (noted so nothing here rests on them): https://dl.acm.org/doi/fullHtml/10.1145/3627106.3627140 returned HTTP 403, so the ACSAC 2023 redirect_uri paper's numbers (6 IdPs vulnerable to path confusion, 10 to parameter pollution) come from the search index rather than the paper; https://labs.sqrx.com/passkeys-pwned-turning-webauth-against-itself-0dbddb7ade1a returned HTTP 403, so the SquareX detail comes from the SecurityWeek write-up; https://www.cyberark.com/resources/threat-research-blog/how-secure-is-your-oauth-insights-from-100-websites now 301-redirects to a Palo Alto Networks landing page and its "100 websites" statistics are therefore not cited above.
