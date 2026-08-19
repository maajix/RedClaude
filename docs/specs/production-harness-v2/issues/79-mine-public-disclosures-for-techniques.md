# 79 — Mine public disclosures for techniques the corpus does not have

**What to build:** A bounded intake that turns publicly disclosed bug bounty work -- reports, advisories, research posts -- into knowledge this repo can grade: one technique per row, each carrying where it came from, which Property class it belongs to and the fixture case that proves it is real, without giving the runtime a new way to reach the internet and without copying anybody's report.

**Blocked by:** 46 — Evaluate and promote one Playbook; 57 — Close the 223-row v1 disposition ledger.

**Status:** resolved

- [x] Every source read is one row in an intake ledger under `baseline/`: source URL, publication date, retrieval date, a digest of what was read, the Property class it maps to, what it produced and a rationale. A checker refuses a row whose class is not in the shipped vocabulary, a row whose named output does not exist on disk, and duplicate coverage of an output another row already claims -- the both-directions rule `check_dispositions` already uses.
- [x] Producing nothing is a legitimate outcome with a reason -- already covered, target-specific, unreproducible, dead technique -- and is refused only when the reason is absent. An intake that never rejects anything is an intake that is not reading.
- [x] Nothing under `src/redkraken/` gains a way to fetch a writeup. Retrieval is a maintainer act whose result is files in this repo; at run time the harness reads only what shipped. No retrieval crosses the door, earns a Receipt, or is attributed to an engagement Program.
- [x] Sources are material published to be read. Nothing behind an account this harness holds a credential for, no platform API called with the operator's identity, and no host, target name or engagement detail out of somebody else's report ever reaches a Scope Policy, a fixture's declared host or a stored Artifact.
- [x] A technique is restated rather than copied: the row carries provenance plus a fresh statement of the shape, the way the v1 sink packs were written to the scope of their ledger row instead of transcribed. Report prose, screenshots and payload dumps stay out of the corpus.
- [x] An accepted technique lands as a Playbook step, a Skill reference or a fixture case, and carries a review date because the Playbook format already expires. A technique that cannot be written as a fixture case is filed as ungradeable with the reason rather than added as knowledge nobody can grade.
- [x] A technique that fits none of the shipped Property classes proposes a vocabulary addition as a migration, and is not filed under the nearest-looking class. An event kind is not a Property class.
- [x] One run emits a deterministic report -- sources read, rows accepted, rows refused by reason -- reviewable the way the disposition report is, and `baseline/` is byte-identical afterwards unless a row was added on purpose.

## Why this needs a boundary at all

The value is real: disclosed reports are where bypass shapes, parser differentials
and chain patterns are written down years before anybody's methodology catches up,
and this corpus was migrated from one operator's v1 knowledge rather than from the
field. The risk is equally real and is the same one this whole migration is
undoing. Knowledge with no provenance, no class and no grading is ambient authority
wearing a different hat: an Agent that has read a hundred tricks and can prove none
of them files a hundred unverifiable Hypotheses.

So the unit of intake is not "a trick" but a row that resolves -- to a class the
selector can select on, to an output that exists, and to a fixture that says whether
the technique is still true. That is the same contract `baseline/v1-dispositions.tsv`
holds v1 to, applied to knowledge arriving from outside instead of knowledge arriving
from before.

Two failure modes to design against explicitly. The first is volume: a scrape of a
platform's hacktivity feed produces thousands of rows and no judgement, so this
ticket is satisfied by a small number of well-resolved rows and not by coverage.
The second is recency theatre: a 2016 technique that every framework now blocks is
worth a refused row with "dead technique" as the reason, and that refusal is itself
knowledge the next reader does not have to re-derive.

## What was built

Sixteen techniques, read from sixteen public pages on 2026-08-19, as
`baseline/technique-intake.tsv`. Four produced a fixture, five were already
graded by one the corpus ships, three were refused with a reason and four are
filed as ungradeable. That ratio is the ticket working rather than a shortfall:
a reading that produced sixteen files would have been a scrape, and the refusals
are the part the next reader does not have to re-derive.

**The unit of intake is a row that resolves.** Nine columns: the technique's
name, the URL, what the source says its publication date is, when it was
retrieved, the digest of what was read, the Property class it maps to, what it
produced, when that comes up for review, and a restatement of the shape in this
repository's words. `tools/check_intake` refuses a class that is not in the
shipped vocabulary -- naming the migration such a technique would have to
propose -- and refuses an event kind with its own message, because the two
vocabularies look alike from a distance and only one of them is something a
target can be true of. It refuses an output that is not on disk, and it refuses
two rows claiming one output, which is the both-directions rule
`check_dispositions` already uses.

**The other direction of that rule is the one that binds the corpus.** A fixture
whose provenance cites this ticket and which no row produced fails the gate. A
file can no longer arrive in `src/redkraken/fixtures/` from a disclosure without
the row that says which page it came from and what was read.

**Producing nothing is a resolution, not an omission.** `covered_by:` names what
already grades the shape, so "already covered" cannot be asserted without saying
by what; `none:` carries one of three reasons -- `target_specific`,
`unreproducible`, `dead_technique` -- and a row that produced nothing carries no
review date, because there is nothing to review. A ledger in which nothing was
refused fails on its own: an intake that never rejects anything is not reading.

**The four ungradeable rows defer to the schema instead of arguing with it.**
`transport.request_framing` and `transport.datagram_transport` are `unmakeable`
in `transport_makeability` and `transport.tls_configuration` and
`transport.certificate_trust` are `probe_only`, each because the reading would
land on the interception proxy, the authority this harness issued, or a protocol
the door does not forward. The gate enforces the agreement: a row claiming a
fixture for a class the schema records as anything but `agent_ok` is refused,
naming the mode. Those four are the only declared Property classes the corpus
does not grade, and now they are the only ones with a written reason.

**Four fixtures, for the four classes that had a Playbook and no case.**
`recovery-flow-pair` builds a reset link's authority from the request's own
`Host` header on one variant; `identifier-oracle-pair` refuses an unregistered
address and a wrong password differently on one variant; `per-origin-limit-pair`
counts an unauthenticated route per origin on one variant; `resource-cost-pair`
enforces the same per-origin request limit on both variants and bounds the work
inside one request on only one of them. Each declares one class, and each
document argues why its neighbours are not merely absent from the ground truth
but could not be true of what it serves. One migration,
`20260915T000000Z__four_disclosed_techniques_arrive_as_fixtures.sql`, registers
all four at both digests; no Playbook names any of them, because the binding is
total and derived.

**Retrieval is a maintainer act and left no trace in the runtime.** Nothing
under `src/redkraken/` mentions the ledger, nothing fetches a writeup, and the
gate imports no network module -- `tests/test_intake.py` asserts all three. No
retrieval crossed the door, earned a Receipt or was attributed to a Program,
because none of it ran inside the harness at all. Sources are `https`, carry no
credentials and carry no query string, which is how a gated resource is spelled;
no host, target name or engagement detail out of anybody's report reaches a
Scope Policy, a fixture's declared host or an Artifact, and the one row that
read a vendor advisory is refused as `target_specific` for exactly that reason.

**A restatement is bounded rather than trusted.** A rationale is between 120 and
600 characters and carries no URL, so provenance stays in its own column and a
row cannot quietly become a transcript. No checker can tell a restatement from a
quotation; what the bounds hold is that the row is the size of a claim, and
review does the rest -- which is what the review date on each produced row is
for.

### Where it is proven

`tests/test_intake.py`, in four parts: the shipped ledger through its gate,
including the report two runs agree on and `baseline/` unchanged by reading it;
the boundary, that nothing in the package reads the ledger and the gate cannot
fetch; every rule of the gate driven from the real rows with one thing changed;
and the four produced fixtures served from the corpus the catalogue digested and
asked the question their class is about, both halves, including the precision
controls -- the recovery route answers an unregistered address identically on
both variants, the oracle pair still authenticates on both, and the cost pair's
request limit engages at the same request on both.

What is not proven here is that a model reads any of it. These four fixtures
enter the graded corpus every Playbook is measured against, and what that
measurement says is ticket 84's to report.
