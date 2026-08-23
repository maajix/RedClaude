# 159 — Recon writes no Host and no edge between a name and what serves it

**What to build:** The two facts a recon lap already holds and never records: the
address a name answered with, and the Application that address serves. Both have
a seat in the vocabulary and no writer.

**Blocked by:** nothing.

**Status:** resolved

- [x] **A Host Entity exists for an address this Program actually reached.**
      `hosts` is empty in every database this tree has produced. The address is
      not unknown — `receipts.pinned_ips` carries it, written by
      `src/redkraken/proxy.py:pinned_ips` on every egress, because the door has
      to pin what it dialled. Nothing reads it back into surface. Promotion is
      not the gap: `rk2_promote_entities` has had a `host` arm and a `host`
      scope selector since
      `20260814T070000Z__a_proposal_becomes_a_canonical_hypothesis.sql:1211`.
- [x] **`domain -resolves_to-> host` is written.** The direction is seeded and
      legal (`relationship_directions`, from
      `20260813T090000Z__a_recon_run_becomes_typed_surface.sql:207`). A Receipt
      names the Domain it requested and the address it pinned, so the edge is a
      join over rows the runtime wrote itself, not a claim a child has to make.
- [x] **`host -serves-> application` is written.** Also seeded, also legal, also
      derivable: `applications.base_url` parses to a host name through
      `rk2_parse_base_url`, and that name is the Domain the address answered
      for. Without this edge an Application and the address serving it are two
      islands, which is what the engagement graph draws today.
- [x] **Decide whether a subdomain edge is vocabulary or display.**
      `domains.apex` already carries the fact, but `relationship_directions` has
      no `domain -> domain` type other than `same_as`, and `same_as` means the
      two rows are one subject, which a subdomain and its apex are not. Either
      the vocabulary gains one type, or the relation stays derived and only the
      display draws it. Do not write it as `same_as`.
- [x] **The writer is the runtime, not a proposal.** Every fact above is already
      in a row this harness wrote. A child asked to propose it would be a child
      asked to repeat the Receipt, and `incompatible_provenance` (145) is
      already the cost of that pattern.
- [x] **Checked by something that would go red.** A `tests/test_database.py`
      class that walks one Receipt with a pinned address and asserts the Host,
      the `resolves_to` edge and the `serves` edge exist afterwards, exactly
      once, and that a second Receipt for the same name adds no duplicates.

## Why

`rk2hunt16` on 22 August, the first end-to-end run in this tree:

```
hosts          0
relationships  DOM1 -same_as-> DOM2 ;  APP2 -runs-> TEC1..TEC4
```

`195.201.160.13` is in that database, in `receipts.pinned_ips`, and nowhere
else. So the surface says this Program knows two names and four technologies,
and cannot say that either name is served anywhere.

Ticket 158 leans on this. `hunt.no_address` was deliberately left off
`rk2_terminal_predicate`'s list because a subject with no address today can gain
one when recon promotes an Application on its name. That reasoning holds and is
also an admission: today the only way a Domain gets an address is 157's
`rk2_application_on`, which reads `applications` and stops there. When this
ticket is paid, the address of a name is a fact the Receipt already proved.

## Notes

Not blocking ticket 65. A campaign reaches a Finding without any of this — 156
and 157 are what it needed. This is missing surface, and missing surface costs
targets rather than Findings.

The engagement graph at `~/engagements/*/graph.py` draws the two edges as
*derived*, labelled `served at` and `subdomain of`, joining on
`rk2_parse_base_url(a.base_url).host = d.fqdn` and `d.apex = d2.fqdn`. That is
the display answer and it is allowed to be derived as long as the sheet says
where it came from. This ticket is the harness answer, where the edge is a row.

## What was built, 2026-08-23

`20261030T000000Z__a_pinned_address_becomes_a_host_and_two_edges.sql`, one
function and one caller. No schema change: `hosts`, the `host` promotion arm and
both relationship directions were already there, and what was missing was the
pass that reads a Receipt back.

**`record_receipt_topology(p_receipt uuid DEFAULT NULL)`** (`:67`). It walks
`receipts` where `decision = 'allowed'`, `host IS NOT NULL` and `pinned_ips` is
non-empty (`:83-91`), normalises the name through `scope_normalize_host`, and
for each pinned address writes the Host Entity (`:115-121`), the
`domain -resolves_to-> host` edge when the Program has promoted that name
(`:144`) and the `host -serves-> application` edge when
`rk2_parse_base_url(a.base_url)` parses to it (`:168-175`). Every row carries
`origin = 'observed'`, and `refresh_scope_projection` runs once at the end if
any Host was written (`:198-199`), so a new address is classified like every
other Entity rather than arriving unscoped.

**Criterion 5 as a grant.** It is the runtime's verb: `REVOKE ALL ... FROM
PUBLIC`, `GRANT EXECUTE ... TO rk2_runtime` (`:210-211`), and filed in
`runtime_verb_surface` (`:214-216`) as "the runtime's, because a child proposing
it would be a child repeating the Receipt".

**The caller.** `src/redkraken/execution.py:3252`, over `TOPOLOGY` (`:496`),
inside promotion's transaction and not beside it: both ends of both edges are
rows the promotion has just written, so a pass before it would find nothing to
attach to. The docstring at `:3193-3197` says that.

**Criterion 4, answered and then enforced.** The subdomain relation stays
derived and is display, not vocabulary (`:39-46`): `domains.apex` already
carries the fact, `same_as` would be a lie about two subjects being one, and a
new type would be a second copy of `apex` in a table that can disagree with it.
The answer is not left as prose -- `check_receipt_topology()`'s fourth arm
(`:252-261`) reports `subdomain_written_as_same_as` for any `same_as` edge
between a name and its own apex, so the decision fails loudly if a later writer
forgets it.

**Idempotence, which criterion 6 asks for by name.** Every insert is
`ON CONFLICT ... DO UPDATE SET last_seen_at = now()` on the key that already
exists (`:121`, `:146`, `:177`), so a second Receipt for the same name adds no
Entity and no edge. `entity_provenance` is the one place a second Receipt
legitimately adds a row, and it is guarded by `NOT EXISTS` rather than by
`ON CONFLICT`, because that unique key includes two nullable columns and NULLs
do not conflict (`:61-65`, `:132-135`).

**Checked.** `ReceiptTopologyTest` (`tests/test_database.py:51117`), 6 cases:
the Host, both edges, exactly once, no duplicates on a second Receipt, and the
standing check green. `check_receipt_topology()` (`:222`) is filed as
`receipt_topology` (`:276`) -- the second of the two new rows that took
`standing_checks` to 66. `rk db verify` answers 96 assertions, 0 violations.
`VerticalRunTest` (`tests/test_vertical.py`) walks the same pass on a real recon
lap and reads the Surface before and after it.

## Correction to the Notes, 2026-08-23

**"Not blocking ticket 65" was true of the plan and is false of the result, and
ticket 65 now names this ticket in its `Blocked by:` line.** The Notes above
are left as written: they were sequencing advice for an open ticket, and they
were right that a campaign reaches a Finding without this and that 156 and 157
are what it needed.

What changed is where the work landed. `record_receipt_topology` is not a pass
an operator may skip -- it runs inside promotion's transaction
(`src/redkraken/execution.py:3252`), so every scoped recon lap ticket 65's
second criterion asks for now writes the Host and the two edges, and
`receipt_topology` is one of the 66 standing checks `rk db verify` answers on
the release run. Ticket 158 is already a blocker of 65 and its fourth criterion
leaves `hunt.no_address` off `rk2_terminal_predicate` on the reasoning that a
name carrying no address today can carry one next pass, calling the permanent
case "159's problem"; until this ticket there was no writer behind that
reasoning. The release rests on this the way it rests on any code its own
demonstration executes and its own verify would go red on.
