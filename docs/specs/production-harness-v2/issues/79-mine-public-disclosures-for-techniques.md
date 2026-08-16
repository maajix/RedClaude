# 79 — Mine public disclosures for techniques the corpus does not have

**What to build:** A bounded intake that turns publicly disclosed bug bounty work -- reports, advisories, research posts -- into knowledge this repo can grade: one technique per row, each carrying where it came from, which Property class it belongs to and the fixture case that proves it is real, without giving the runtime a new way to reach the internet and without copying anybody's report.

**Blocked by:** 46 — Evaluate and promote one Playbook; 57 — Close the 223-row v1 disposition ledger.

**Status:** ready-for-agent

- [ ] Every source read is one row in an intake ledger under `baseline/`: source URL, publication date, retrieval date, a digest of what was read, the Property class it maps to, what it produced and a rationale. A checker refuses a row whose class is not in the shipped vocabulary, a row whose named output does not exist on disk, and duplicate coverage of an output another row already claims -- the both-directions rule `check_dispositions` already uses.
- [ ] Producing nothing is a legitimate outcome with a reason -- already covered, target-specific, unreproducible, dead technique -- and is refused only when the reason is absent. An intake that never rejects anything is an intake that is not reading.
- [ ] Nothing under `src/redkraken/` gains a way to fetch a writeup. Retrieval is a maintainer act whose result is files in this repo; at run time the harness reads only what shipped. No retrieval crosses the door, earns a Receipt, or is attributed to an engagement Program.
- [ ] Sources are material published to be read. Nothing behind an account this harness holds a credential for, no platform API called with the operator's identity, and no host, target name or engagement detail out of somebody else's report ever reaches a Scope Policy, a fixture's declared host or a stored Artifact.
- [ ] A technique is restated rather than copied: the row carries provenance plus a fresh statement of the shape, the way the v1 sink packs were written to the scope of their ledger row instead of transcribed. Report prose, screenshots and payload dumps stay out of the corpus.
- [ ] An accepted technique lands as a Playbook step, a Skill reference or a fixture case, and carries a review date because the Playbook format already expires. A technique that cannot be written as a fixture case is filed as ungradeable with the reason rather than added as knowledge nobody can grade.
- [ ] A technique that fits none of the shipped Property classes proposes a vocabulary addition as a migration, and is not filed under the nearest-looking class. An event kind is not a Property class.
- [ ] One run emits a deterministic report -- sources read, rows accepted, rows refused by reason -- reviewable the way the disposition report is, and `baseline/` is byte-identical afterwards unless a row was added on purpose.

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
