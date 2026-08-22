# 164 — Fifty Playbooks, and not one has ever been selected

**What to build:** The facts a Playbook triggers on, actually written down. The
corpus holds 50 Playbooks that trigger on 49 distinct facts. `subject_facts`
produced 7 of them in `rk2hunt17`, every Playbook needs 2 or 3 at once, and
`playbook_selections` holds zero rows — kept *or* dropped — for the whole
campaign. The strategy corpus has never run.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] **The three columns that carry most of the vocabulary are never filled.**
      `applications.kind` is NULL on both Applications, so `web_surface`,
      `api_surface`, `spa_surface`, `graphql_surface` and `websocket_surface`
      cannot fire — five trigger words dead on one NULL.
      `endpoints.auth_required` is NULL on all four Endpoints, so every subject
      reads `unknown_auth_endpoint` and neither `authenticated_endpoint` nor
      `unauthenticated_endpoint` ever exists. `parameters` holds zero rows, so
      the twelve `*_parameter` and `*_valued_parameter` facts are dead as a
      block. That is roughly half the trigger vocabulary, absent because three
      things were not written rather than because they were not true.
- [ ] **Two of the three are fields the child is not told about.**
      `rk2_promote_entities` reads `auth_required` off the proposal element and
      has since `20260813T090000Z`. The `submit_mission_result` description
      lists "endpoint method and path_template" and stops, so a field the
      promotion is waiting for is one no child knows exists. `kind` is the
      opposite case and worth separating: it *is* in the description and *is* an
      enum in `_ELEMENTS["new_entities"]`, and both recon runs still left it
      NULL. One is a missing field, the other is a field nothing asks for.
- [ ] **Facts exist for Endpoints and every Task subject is an Application.**
      `subject_facts` in `rk2hunt17` covers EP1 through EP4 and nothing else.
      All nine Tasks carry APP1 or APP2. So even with the vocabulary filled, the
      selection asks about a row that has no facts and gets the honest answer.
      Settle which subject a `hunt` Task is about: the Application it was
      derived from, or the Endpoint the claim is actually about.
- [ ] **A Playbook that misses by one fact is reported as missing by one.**
      Against EP1, eight Playbooks are exactly one fact short —
      `playbooks/cms/playbook.md` needs `tech_cms`, `read_method` and
      `authenticated_endpoint`, and holds the first two. Today the near miss and
      the total mismatch are the same output: no row at all.
      `playbook_candidates` filters on `playbooks_by_trigger` before it can
      report anything, so an operator asking "why did the CMS Playbook not run
      against a Drupal site" has nothing to read. A near-miss is the single most
      useful thing this machinery could say.
- [ ] **All fifty are `draft` and nothing says whether that matters.**
      `playbooks.status` is `draft` on every row. `playbook_candidates` drops
      only `deprecated`, and sorts `stable` first — so `draft` is selectable and
      merely ranks last. That is either correct and should be stated, or the
      corpus was never promoted and the promotion step is missing. It is named
      here because an operator reading "0 selections, 50 drafts" will reach for
      it first, and it is not the cause.
- [ ] **Checked by something that would go red.** A test that stands one
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
