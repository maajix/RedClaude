# 164 — Fifty Playbooks, and not one has ever been selected

**What to build:** The facts a Playbook triggers on, actually written down. The
corpus holds 50 Playbooks that trigger on 49 distinct facts. `subject_facts`
produced 7 of them in `rk2hunt17`, every Playbook needs 2 or 3 at once, and
`playbook_selections` holds zero rows — kept *or* dropped — for the whole
campaign. The strategy corpus has never run.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The three columns that carry most of the vocabulary are never filled.**
      `applications.kind` is NULL on both Applications, so `web_surface`,
      `api_surface`, `spa_surface`, `graphql_surface` and `websocket_surface`
      cannot fire — five trigger words dead on one NULL.
      `endpoints.auth_required` is NULL on all four Endpoints, so every subject
      reads `unknown_auth_endpoint` and neither `authenticated_endpoint` nor
      `unauthenticated_endpoint` ever exists. `parameters` holds zero rows, so
      the twelve `*_parameter` and `*_valued_parameter` facts are dead as a
      block. That is roughly half the trigger vocabulary, absent because three
      things were not written rather than because they were not true.
- [x] **Two of the three are fields the child is not told about.**
      `rk2_promote_entities` reads `auth_required` off the proposal element and
      has since `20260813T090000Z`. The `submit_mission_result` description
      lists "endpoint method and path_template" and stops, so a field the
      promotion is waiting for is one no child knows exists. `kind` is the
      opposite case and worth separating: it *is* in the description and *is* an
      enum in `_ELEMENTS["new_entities"]`, and both recon runs still left it
      NULL. One is a missing field, the other is a field nothing asks for.
- [x] **Facts exist for Endpoints and every Task subject is an Application.**
      `subject_facts` in `rk2hunt17` covers EP1 through EP4 and nothing else.
      All nine Tasks carry APP1 or APP2. So even with the vocabulary filled, the
      selection asks about a row that has no facts and gets the honest answer.
      Settle which subject a `hunt` Task is about: the Application it was
      derived from, or the Endpoint the claim is actually about.
- [x] **A Playbook that misses by one fact is reported as missing by one.**
      Against EP1, eight Playbooks are exactly one fact short —
      `playbooks/cms/playbook.md` needs `tech_cms`, `read_method` and
      `authenticated_endpoint`, and holds the first two. Today the near miss and
      the total mismatch are the same output: no row at all.
      `playbook_candidates` filters on `playbooks_by_trigger` before it can
      report anything, so an operator asking "why did the CMS Playbook not run
      against a Drupal site" has nothing to read. A near-miss is the single most
      useful thing this machinery could say.
- [x] **All fifty are `draft` and nothing says whether that matters.**
      `playbooks.status` is `draft` on every row. `playbook_candidates` drops
      only `deprecated`, and sorts `stable` first — so `draft` is selectable and
      merely ranks last. That is either correct and should be stated, or the
      corpus was never promoted and the promotion step is missing. It is named
      here because an operator reading "0 selections, 50 drafts" will reach for
      it first, and it is not the cause.
- [x] **Checked by something that would go red.** A test that stands one
      Application with `kind = 'web'`, one Endpoint under it with
      `auth_required = false`, and asserts `subject_facts` yields
      `web_surface` and `unauthenticated_endpoint`, and that
      `playbook_candidates` returns a non-empty set for that subject. Today
      every one of those assertions fails on real data and no test notices.

## Why

`rk2hunt17` found Drupal 10, PHP 8.4.24, Apache and Plesk, and found
`GET /user/login`. An operator looking at that says "Drupal login page, check
username enumeration" and reaches for the CMS strategy. The harness holds that
strategy, in `playbooks/cms/playbook.md`, and never opened it:

```
T8 runs under no Playbook: nothing in the corpus is about this subject
T9 runs under no Playbook: nothing in the corpus is about this subject
```

Every lap said that. `playbook_selections` is empty in every database this tree
has produced. Fifty Playbooks were compiled, gated by `check_wiring`, seeded
into every Program, and handed to nobody.

The subject was an Application with a NULL `kind` and no Parameters, so the
questions the corpus knows how to ask could not be matched to it. The Playbooks
are not wrong and the trigger logic is not wrong. The surface is thinner than
either of them assumes, and nothing measures the gap.

## Notes

The seven facts `rk2hunt17` produced, for scale against the 49 the corpus wants:

```
anonymous_identity_available  flow_step  read_method  redirect_target
tech_cms  tech_edge_proxy  unknown_auth_endpoint
```

`tech_cms` fired. The Drupal detection worked. The Playbook that consumes it
needs one more word.

Related to 162 and distinct from it: 162 is about facts inside a body that
nothing extracts, this is about facts the schema already has columns for that
nothing fills. 162 would add Parameters as a side effect and is not a substitute
for asking for them.

Not related to 163. 163 is why a Finding could not be named; this is why there
was nothing better to name.

## What was built

`20261023T000000Z__fifty_playbooks_and_not_one_has_ever_been_selected.sql`, one
sentence in `_launch.py`, and one caller in `execution.py`.

**The subject.** Settled as "the one the Hypothesis names, whichever type that
is", and the view learns to answer for both rather than the Task's subject being
rewritten. There is no rule that could pick the Endpoint: a claim about an
Application ("this deployment runs Drupal and exposes a login") is about the
Application and about no route in particular. `subject_facts` is rebuilt on
three CTEs where it had one -- `endpoint` keeps the Endpoint's own id so the
parameter and relationship branches still reach it, `ep` is one row per
(subject, Endpoint under it), and `subj` is every subject with the Application
behind it, including an Application with no Endpoint at all. The branches about
the Application's shape, its technologies and the Program's identities read
`subj`, so a site recon found before it found a route now reads `web_surface`
rather than nothing. `SELECT DISTINCT` on the outside, because an Application
collects the same fact from each of its Endpoints and 032's per-branch DISTINCT
stops being right the moment one subject has two.

**The three columns.** Not a schema change: `applications.kind`,
`endpoints.auth_required` and the `parameters` table are empty because the child
was never asked. `submit_mission_result`'s typed-field list was a subset of what
`rk2_promote_entities` reads -- `banner`, `auth_required`,
`request_content_type` and `reflected` were all read and none of them named --
so the list is now the whole of it, and a paragraph says what leaving one out
costs: about half the trigger vocabulary, and the hunt that follows runs under
no Playbook. `kind` needed the paragraph rather than the field name, which is
the distinction the ticket drew.

**The near miss.** `playbook_near_misses(program, subject, max_missing)` counts
the way `playbooks_by_trigger` decides -- every unheld `all` fact, plus one for
an unsatisfied `any` group, so a Playbook six ways short of one `any` is one
fact short and not six. `execution._playbooks` asks it only when the selection
kept nothing, and appends the answer to the sentence that used to end at
"nothing in the corpus is about this subject". On `rk2hunt17`'s surface that
sentence now names eight Playbooks and the one fact each of them wanted.

**Draft.** Stated and not changed, as the ticket says. The rule now sits on
`playbooks.status` as a column comment, where an operator reading "0 selections,
50 drafts" at three in the morning meets it.

### What this does not do

It does not promote anything, and it does not touch the metadata stage. On the
Drupal surface the one Playbook whose triggers now match outright,
`playbooks/attack-surface/playbook.md`, comes back dropped for
`role_lacks_skill`: `web_hunter` does not hold its Skills. That is a reason an
operator can already read, which is exactly what the trigger stage did not have
and now does. Whether the roster should give that Playbook to the hunter is a
different question and not this one.

### Repairs this ticket had to make first

`PlaybookCorpusSelectionTest` is the only case that asks the whole catalogue
what each of the fifty Playbooks matches, and it is what proves this rebuild
did not move any Endpoint subject. It could not run: two earlier tickets closed
a vocabulary at the column and did not carry this class with them. Ticket 112
retired `identities.class = 'service'` (used here for a tenant, now
`privileged`), and ticket 111 closed `parameters.value_class` to nine values
without `text` (used here for an unclassified parameter, now NULL). Neither
value is a `subject_facts` branch, so what the catalogue matches is unchanged;
both were `setUpClass` errors from the day the constraint landed.
