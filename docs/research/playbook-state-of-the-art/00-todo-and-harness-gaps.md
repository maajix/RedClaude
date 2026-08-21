# 00 - What the research files do not say, and what has to happen first

The eight files beside this one are the technique research. This file is the
part that came from reading our own tree, and it is written down separately
because none of it is derivable from those files.

Everything here was verified in this repository at the commit this file was
added. Where a research file said something slightly different, the reading in
this file is the one that was checked against the source.

## A. The blocker: our agent cannot send a request body

`src/redkraken/roster.py:738` declares `mcp__rk2__http_request` with exactly
three arguments: `method`, `url`, `headers`. The comment beneath them states
that a body and an identity were both declared once and removed, because "the
child has no store, so it cannot name a body the door could send", and because
the runtime opens the Tool run with the identity already chosen.

Consequences, all checked:

* **A GraphQL reading cannot be performed.** `playbooks/graphql/playbook.md:42`
  says "Send the selection as label A through `mcp__rk2__http_request` with
  `identity_slot` set". There is no argument that carries a selection and no
  argument named `identity_slot`.
* **29 of the 50 playbooks name `identity_slot`.** The capability behind it
  exists -- a Tool run is opened under a leased Identity -- but the field the
  playbooks tell the agent to set does not.
* Everything whose reading is a POST with a document -- GraphQL, gRPC, most of
  the injection corpus, webhook delivery -- is prose today, not a procedure.

This is why the order is harness first. Adding state-of-the-art techniques to
steps that cannot be executed would multiply the unrunnable part of the
catalogue.

## B. What constrains a playbook edit

Measured from `src/redkraken/playbook.py` and the migrations, so an edit is
legal by construction rather than by test failure:

| Thing | Rule | Source |
| --- | --- | --- |
| bb: fields | 12 required, 2 optional (`bb:triggers_any`, `bb:references`), 7 forbidden | `playbook.py:123-149` |
| `bb:outputs` | must be `family.leaf` from the 57 shipped property classes, and the family must match `bb:category` | `playbook.py:427-435`, `0018_vocabularies.sql:72-170` plus nine later migrations |
| `bb:triggers_all` / `bb:triggers_any` | must be surface facts, 55 of them; the two lists may not overlap | `playbook.py:444-449`, `0032_playbooks.sql:38-81` plus eight later migrations |
| `bb:evidence` | kinds from the 16 observation kinds (11 of them evidential); sorted, no duplicates, must contain a `supported` row; every playbook needs both a `control` and a `variant` role | `playbook.py:349-396`, `tests/test_playbook.py:438-444` |
| `bb:skills` | one of the 6 shipped Skills | `skill.py:83-100` |
| `bb:risk` / `bb:effects` | closed sets, and risk may not sit below what the effects imply | `playbook.py:95-112` |
| `bb:status` | every shipped playbook must be `draft` until a fixture has graded it | `tests/test_playbook.py:468-471` |
| `bb:references` | every declared file must exist under the playbook's own `references/`, no symlinks, and no undeclared file may sit there | `playbook.py:459-482` |

Unknown values do not degrade quietly: the catalogue is loaded by migration into
`playbooks` plus five child tables with foreign keys, so an unknown class,
trigger, kind or skill fails at INSERT.

**A new property class needs a vocabulary migration.** Several research findings
ask for one (`authentication.recovery_flow` is named by our own authentication
playbook and emitted by nobody; there is no class for tenant isolation over
HTTP, for object-property write, for cache deception, or for takeability of a
dangling resource).

**Adding or removing a playbook breaks a hard-coded list.**
`tests/test_playbook.py:491-545` enumerates all 50 names; a second test maps the
37 playbooks that carry references. Both have to be edited with the change.

## C0. The vocabulary is bigger than the first reading said

An earlier reading of this repository counted the vocabulary from
`0018_vocabularies.sql` and `0032_playbooks.sql` alone and reported 47 property
classes, 14 observation kinds and 33 surface facts. Nine later migrations add
to all three. The counts in the table above were read back out of a database
with every migration applied and all fifty playbooks loaded:

    property_classes 57 | observation_kinds 16 (11 evidential)
    surface_facts    55 | playbooks          50

Read them from a migrated database rather than from the first migration that
declares them, because every playbook batch since has extended the vocabulary
it needed.

## C. Corrections to the research files

* The LDAP gap is real but is written in the wrong place in `05`. The promise is
  made by `playbooks/command-directory-injection/playbook.md:124`, which says
  LDAP filter injection "lands there" in `sql-injection`. It is `sql-injection`
  that has no LDAP step -- the string does not appear in it at all.
* `05` says `structured-injection` refuses DOCTYPE. Confirmed verbatim at
  `playbooks/structured-injection/playbook.md:142-144`: "no doctype and no
  entity declaration of any kind".
* `03` says no playbook emits `authentication.recovery_flow`. Confirmed: the
  string appears in the authentication playbook's prose and in two of its
  reference pages, and in no `bb:outputs` anywhere.
* `07` says no playbook can answer whether a dangling origin is takeable.
  Confirmed from the output classes: `supply-chain` emits only
  `information_disclosure.dependency_manifest`, `external-resources` only
  `injection.foreign_resource`, `kubernetes` only
  `information_disclosure.workload_metadata` behind a `tech_orchestrator`
  trigger.

## D. Test-suite state at the time of this research

`python -m unittest discover -s tests -t .` ran 3479 tests in 1546 s and
finished with 5 failures and 1 error. Two of them are named:
`ProxyEgressTest.test_an_identity_client_certificate_hash_is_persisted_in_its_receipt`
and `ExchangeTest.test_an_identity_client_certificate_reaches_only_the_https_connector`.
Both are about the leased client certificate, and the second one was re-run
against an unmodified checkout of `HEAD` and fails there too, so it is not from
ticket 93. The refusal is `identity slot refused`, raised when installing the
leased client certificate throws `identity.Invalid` (`proxy.py:2530`).

A first run of the same suite appeared to pass with exit code 0. It did not:
the command was piped into `tail`, so the exit code was `tail`'s.

TODO: identify the remaining four, and decide whether the client-certificate
failure is an environment artefact or a real regression on `main`.

## E. Ordered TODO

Harness first, by the operator's decision. This list is now tickets 94 through
101 in `docs/specs/production-harness-v2/issues/`, in dependency order:

* **95** — A bounded string argument must say maxLength. The prerequisite bug
  found while designing the request contract.
* **94** — Hand the response headers to the caller. Capability B, 18 techniques,
  and the cheapest of them.
* **96** — Carry a request body. Capability A, 61 of 131 techniques, blocked by
  95.
* **97** — Settle what an Identity slot is. The 29 playbooks that name a field
  that does not exist, and the runtime that hardcodes it empty.
* **98** — Let a playbook step reach the out-of-band channel. Capability F, 14
  techniques; tickets 14 and 69 shipped the recording half.
* **99** — Let a playbook step drive the browser. Capabilities D and E, 22 plus
  19 techniques.
* **100** — Extend the vocabulary the corpus is missing. Capability L, 8
  techniques, and it lands after the capability work rather than before it.
* **101** — Rewrite the playbook corpus on the capabilities that now exist.
  Blocked by all seven above, and the ticket they exist for. Ticket 65 is
  blocked by it, so every one of them is on a path to the release candidate.

Section C0 above and `09-capability-matrix.md` carry the corrected counts those
tickets are written against; where this file and the matrix disagreed, the
tickets record the reading that was checked against the source.
