# 159 — Recon writes no Host and no edge between a name and what serves it

**What to build:** The two facts a recon lap already holds and never records: the
address a name answered with, and the Application that address serves. Both have
a seat in the vocabulary and no writer.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] **A Host Entity exists for an address this Program actually reached.**
      `hosts` is empty in every database this tree has produced. The address is
      not unknown — `receipts.pinned_ips` carries it, written by
      `src/redkraken/proxy.py:pinned_ips` on every egress, because the door has
      to pin what it dialled. Nothing reads it back into surface. Promotion is
      not the gap: `rk2_promote_entities` has had a `host` arm and a `host`
      scope selector since
      `20260814T070000Z__a_proposal_becomes_a_canonical_hypothesis.sql:1211`.
- [ ] **`domain -resolves_to-> host` is written.** The direction is seeded and
      legal (`relationship_directions`, from
      `20260813T090000Z__a_recon_run_becomes_typed_surface.sql:207`). A Receipt
      names the Domain it requested and the address it pinned, so the edge is a
      join over rows the runtime wrote itself, not a claim a child has to make.
- [ ] **`host -serves-> application` is written.** Also seeded, also legal, also
      derivable: `applications.base_url` parses to a host name through
      `rk2_parse_base_url`, and that name is the Domain the address answered
      for. Without this edge an Application and the address serving it are two
      islands, which is what the engagement graph draws today.
- [ ] **Decide whether a subdomain edge is vocabulary or display.**
      `domains.apex` already carries the fact, but `relationship_directions` has
      no `domain -> domain` type other than `same_as`, and `same_as` means the
      two rows are one subject, which a subdomain and its apex are not. Either
      the vocabulary gains one type, or the relation stays derived and only the
      display draws it. Do not write it as `same_as`.
- [ ] **The writer is the runtime, not a proposal.** Every fact above is already
      in a row this harness wrote. A child asked to propose it would be a child
      asked to repeat the Receipt, and `incompatible_provenance` (145) is
      already the cost of that pattern.
- [ ] **Checked by something that would go red.** A `tests/test_database.py`
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
