# 101 — Rewrite the playbook corpus on the capabilities that now exist

**What to build:** The fifty shipped Playbooks rewritten against the tooling the
seven tickets before this one deliver, and the Playbooks the 131 researched
techniques have no home in. This is the ticket the other seven exist for.

**Blocked by:** 94 — Hand the response headers to the caller; 95 — A bounded string argument must say maxLength; 96 — Carry a request body; 97 — Settle what an Identity slot is; 98 — Let a playbook step reach the out-of-band channel; 99 — Let a playbook step drive the browser; 100 — Extend the vocabulary the corpus is missing; 109 — `compare_responses` differences two Artifacts where eleven Playbooks ask for more.

**Status:** ready-for-agent

- [ ] **The rewrite uses the operator's pentest corpus and current external
      research, with provenance.** The local source is
      `/home/majix/hacking-wiki`: its index currently carries 326 concept pages,
      including 131 Web, 30 Infrastructure/Network and 15 Windows/AD/Lateral
      pages. Each Playbook receives the relevant local references instead of a
      wholesale copy of payload prose. Current web research is checked against
      versioned OWASP WSTG scenarios, ASVS 5.0.0 requirements, the OWASP API
      Security Top 10 2023, PortSwigger Web Security Academy and original
      PortSwigger Research; infrastructure methodology is checked against NIST
      SP 800-115 and the live MITRE ATT&CK Enterprise matrix. A source ledger
      records source version/date, technique, Playbook destination, whether the
      harness can execute it, the permitted payload family and the evidence
      writer. A link list without that mapping does not satisfy this criterion.
- [ ] **All fifty Playbooks, not only the five High-Yield pairs, carry an
      executable testing shape.** Each one states prerequisites, attack
      hypothesis, baseline, variant, control, allowed payload family, branches,
      stop conditions and the evidence bar for both `supported` and `refuted`.
      Tool operation belongs in a referenced Skill; target-specific ordering
      belongs in a Test; active bodies stay registry-owned. Any evidence kind
      with no runtime writer blocks the Playbook through ticket 166 rather than
      being left as unreachable prose.
- [ ] **The knowledge view conforms to Google Open Knowledge Format v0.2.** A
      dedicated bundle declares `okf_version: "0.2"` at its root and exposes
      every shipped Playbook, Skill and maintained reference as a linked
      concept without weakening the closed `bb:` execution schema. Concepts
      carry `type`, `title`, `description`, `sources` with stable IDs and
      per-claim footnote attribution, `generated`, `verified`, `status` and an
      intentional `stale_after`; actor strings follow OKF's
      `<producer>/<version>`, `human:<id>` and `process:<id>` convention.
      Unknown OKF extensions round-trip, indexes support progressive disclosure
      and links form the Playbook → Skill → Reference graph. The bundle is
      validated in tests against the canonical GoogleCloudPlatform
      `open-knowledge-format` v0.2 specification. The existing
      `/home/majix/hacking-wiki` is input, not proof of conformance: its shape is
      OKF-like, but its root currently lacks `okf_version` and many imported
      Notion pages lack `type` and the v0.2 trust/provenance families.
- [ ] **Part of this work needed no new capability and is done first.** The
      research names 11 techniques that are reachable today with `method`, `url`
      and `headers` alone or with the ten already-registered browser actions,
      and that no Playbook uses: double-decoding across a proxy hop (01 #2);
      grounded route inventory from the client bundle, whose `js_routes` is
      already in the `run_tool` enum at `roster.py:784` (01 #3); the RSC and
      hydration payload as a second copy of server state (01 #14); shadow and
      zombie API versions with `.well-known` as a seed (01 #16); encoding and
      Unicode normalization differentials in the path and query (02 #7 = 05 #9);
      the error message as an oracle, whose class and evidential kind both
      already exist (02 #12); ORM operator injection over the query string
      (04 #8 = 05 #2); framework and edge authorization bypass via internal
      headers (04 #14); predictable identifiers as the enabling step (04 #15);
      error and oracle-based SQL injection without sleeping (05 #13); and the
      read half of abandoned storage the application still fetches from
      (07 #5). The preflight half of 02 #10 goes in beside them: `OPTIONS` has
      been in the method enum since the contract was written
      (`roster.py:743-747`) and no Playbook sends one.
- [ ] The 29 Playbooks that name `identity_slot` say what ticket 97 settled
      instead, and the string `identity_slot` appears in no `playbook.md` in the
      corpus afterwards.
- [ ] The Playbooks whose reading is a document -- GraphQL, gRPC, SOAP, SCIM,
      token endpoints, the injection corpus and all ten techniques of file 08 --
      carry a step that sends one, rather than prose describing one.
      `playbooks/graphql/playbook.md:42-43` and
      `playbooks/grpc/playbook.md:50` are the two the research quotes and there
      are more.
- [ ] `authentication.recovery_flow` has an emitter. The class exists
      (`0018_vocabularies.sql:105-106`), the fixture that grades it exists
      (`20260915T000000Z…:92`), our own authentication Playbook names it in
      prose (`playbooks/authentication/playbook.md:101`), and no `bb:outputs`
      anywhere declares it -- so a fixture and a class have been sitting unused
      on either side of a gap no document crosses.
- [ ] **The hard-coded catalogue lists are updated with every added or removed
      Playbook.** `tests/test_playbook.py:491-545` enumerates all fifty names in
      sorted order, and the v1 disposition rows resolve against that same list,
      so a Playbook without a row or a row without a Playbook fails one of the
      two. The second list is
      `test_every_reference_is_attached_to_the_one_playbook_that_absorbed_it`
      (`tests/test_playbook.py:547-619`), which maps every Playbook that carries
      references to its reference filenames.
      `00-todo-and-harness-gaps.md:62-63` calls that second list "the 37
      playbooks that carry references"; that number does not check out --
      counted at this commit the map holds **31** entries and 31 Playbook
      directories have a `references/` directory, over 74 reference files.
- [ ] Every new or rewritten Playbook satisfies the frontmatter rules section B
      of `00-todo-and-harness-gaps.md` records, each of which is a load rule
      rather than a style preference: 12 required `bb:` fields, 2 optional
      (`bb:triggers_any`, `bb:references`) and 7 forbidden
      (`playbook.py:123-149`); `bb:outputs` a `family.leaf` from the shipped
      property classes whose family matches `bb:category`
      (`playbook.py:427-435`); `bb:triggers_all` and `bb:triggers_any` drawn
      from the surface facts and non-overlapping (`playbook.py:444-449`);
      `bb:evidence` sorted, duplicate-free, containing a `supported` row, and
      carrying both a `control` and a `variant` role
      (`playbook.py:349-396`, `tests/test_playbook.py:435-444`); `bb:skills`
      one of the six shipped Skills; `bb:risk` and `bb:effects` closed sets with
      risk never below what the effects imply (`playbook.py:95-112`);
      `bb:status` `draft` until a fixture has graded it
      (`tests/test_playbook.py:461-471`); and `bb:references` naming only files
      that exist under the Playbook's own `references/`, with no symlinks and no
      undeclared file sitting there (`playbook.py:459-482`).
- [ ] Nothing is added that the research says we should not build, and each
      refusal keeps the reason the research gave, because a refusal without its
      reason gets re-proposed: the raw-framing and desync classes, which
      `0025_transport_claims.sql:222-233` records as `unmakeable` and an
      `ENABLE ALWAYS` trigger raises on where the claim is first written
      (research file 09 names that trigger `transport_claim_guard()`, which does
      not check out -- the only occurrence of that spelling is a comment at
      `0025_transport_claims.sql:201`, and the function is
      `transport_hypothesis_guard()` at `:265-278`); the single-packet timing
      attack; CRLF in our own header names or values, which
      `roster.py:753-757` excludes by construction; anything needing a
      machine-in-the-middle position;
      registering or claiming a third-party resource; credential validity checks
      at a vendor; retrieving cloud metadata credentials as opposed to reading
      the response shape; and hosting a second origin, which five techniques
      want and which the browser lane does not do. Techniques whose
      cross-origin half needs a second origin go in with that half described and
      its preconditions checked, not executed.
- [ ] The four techniques the matrix marks unmapped or out of scope stay out:
      07 #2, #4, #7 and the claiming half of #12, each because the subject is a
      source repository, a CI runner or a vendor's own API rather than an
      application the Program's scope covers, and no harness change makes it in
      scope.
- [ ] Every Playbook this ticket touches still ships `draft`, and the corpus
      statements that count the catalogue move together with it -- the
      enumerated corpus in `tests/test_database.py`, the binding totals `rk
      playbook cost` states, and whatever ticket 84's campaign was costed
      against. A Playbook added here restates that campaign, the way a
      fifty-fifth fixture restated it for ticket 88.

## Why

`docs/research/playbook-state-of-the-art/09-capability-matrix.md` is one row per
technique across all eight research files -- 20 + 15 + 20 + 18 + 18 + 16 + 14 +
10 = **131** -- with the capability each needs and whether the harness has it.
Tickets 94 through 100 are that file's ranked capability list. This ticket is
what the list was ranked for: a capability with no Playbook that uses it is a
capability nobody can spend.

The ordering is the operator's decision, recorded in section E of
`00-todo-and-harness-gaps.md`: harness first, because "adding state-of-the-art
techniques to steps that cannot be executed would multiply the unrunnable part
of the catalogue". The first criterion above is the one exception the research
itself carves out -- the section titled "What is already reachable and simply
unused", which says of those eleven techniques that "nothing below needs a
ticket; they need a playbook edit".

## Comments

**2026-08-24 -- Arbeitsblock 3 implemented this ticket for five Playbooks and
five capability rows, and for nothing else.**

The five are the High-Yield pairs ticket 84 grades: `attack-surface`,
`object-ownership`, `browser-script`, `cookies` and `payment-workflows`. The five
capability rows are A to E of
`docs/research/playbook-state-of-the-art/09-capability-matrix.md`: a request
body, response headers on the answer, the settled Identity slot, a browser
mission from a Playbook step, and the wider browser action set.

Row E is the one that was answered by subtraction. Arbeitsblock 3 adds no browser
action, so every ask that needed one was removed rather than served, and `cookies`
carried three of them: a step reporting the browser's own cookie jar, a
navigation "captured with its network log", and a cross-site request from a
second origin this lane does not host. Its fourth repair is row C -- it told the
model to name the Identity slot in the plan, which tickets 97 and 131 settled the
other way. `attack-surface` lost a sentence that said `jq` is the only tool in
`offline_tools`, which stopped being true when the registry reached six programs;
the true sentence is about the grant, since it executes as `recon` and `recon`
holds `jq` alone. `browser-script` gained row D, the tool ticket 99 built.
`payment-workflows` gained row A, the call that carries the edited number.
`object-ownership` needed nothing.

`20261105T000000Z` re-registers the four bodies that moved. No `bb:` field moved
in any of them, so no class, trigger, evidence bar or fixture binding changed and
all five still ship `draft`.

Everything else in this ticket is untouched: the other forty-five Playbooks, the
eleven already-reachable techniques, the `authentication.recovery_flow` emitter,
the nine `owed:101` rows in `check_wiring`'s register, and the thirteen bodies
ticket 109 handed over. The ticket stays `ready-for-agent` for all of it.

**One thing the slice found and did not fix.** All five of these Playbooks gate
`supported` on an Observation kind no runtime verb writes -- `content_match`,
`credential_effect`, `header_policy_observed`, `reflected_input`, `state_change`
-- which is ticket 166, measured there at 33 of 50 Playbooks. Their bodies are
now true about what the harness can do; their `bb:evidence` bars are not
reachable, and no edit inside this slice's scope makes them reachable.
