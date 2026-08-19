# 53 — Migrate injection Playbooks

**What to build:** Deliver production-ready Playbooks and fixtures for seven v1 injection topics with explicit controls that distinguish parser behavior from generic errors, reflection and latency noise.

**Blocked by:** 46 — Evaluate and promote one Playbook; 48 — Rework v1 Agents, Skills, references and sink packs.

**Status:** resolved

**Deviation on criterion 6, inherited from 49, 50, 51 and 52:** the positive and adversarial
arrangement exists and is total; the evaluation that would grade it has not run, and cannot run
from this ticket. All seven ship `draft`. `stable` is reachable only through
`playbook_test_verdict` returning `pass` for the exact text, and an evaluation run is an Agent
run against a fixture listening on loopback, which `scope.compile_policy` and
`authorize_identity_egress_address` both refuse. Ticket 78 decided that route; ticket 84 grades
the corpus over it. What moved is the measurement: the corpus is thirty-five Playbooks and
thirty-six fixtures, `playbook_fixture_binding` is still total over the fixture table, and each
of the seven new fixtures is an out-of-class negative for the thirty-four Playbooks that do not
output its class. The half of the criterion that is about selection is checked and holds:
`PlaybookCorpusSelectionTest` is diagonal across all thirty-five subjects, every one of the
seven is loadable by exactly one production role, and
`test_no_reference_text_reaches_a_shipped_projection` reads every line over forty characters
out of all fifty-one attached references and asserts it is absent from the projection the model
receives.

- [x] Command/Directory Injection, NoSQL Injection, ORM, Spreadsheet Injection, SQL Injection, SSTI and Structured Injection each exist as authored v2 Playbooks.
- [x] Output Property classes distinguish query language, command execution, template evaluation, structured-header/document parsing and formula interpretation.
- [x] Detection defaults to the least mutating action and requires explicit risk/grant metadata before any write or execution effect.
- [x] Timing, boolean, error and content differentials each include a neutralized control and configured repeat policy.
- [x] Fixtures include secure twins, noisy endpoints and decoy reflections so a Playbook that always fires fails precision evaluation.
- [ ] All seven exact hashes are role-loadable, selected only on matching facts and pass grounded positive/adversarial promotion gates. **Partial:** loadability and selection hold at the shipped text; the promotion gates wait on the route above. Ticket 78 built that route; ticket 84 grades the corpus over it.

## Comments

Implemented on 2026-08-17.

### Twenty-seven v1 pages, seven readings

This is the largest collapse in the migration and the one where v1's organising principle is
most clearly not a reading. v1 filed this material by dialect and by payoff: eleven pages of
SQL alone, one per database and one per thing to do once you are in. A reading is neither. What
separates one reading here from the next is which interpreter the caller's bytes reach, which
is the cut 018 made when it named the injection family, so the seven Playbooks are seven
interpreters.

`sql-injection` absorbs all eleven sqli pages. `command-directory-injection` absorbs the five
of v1's command pack, two of which -- `ldap-injections.md` and `xxe.md` -- describe classes it
does not grade; they are attached where v1's pack put them, each note says where its subject is
actually read, and step 6 names the right document for both. `structured-injection` absorbs
xpath-injections and smtp-header-injection, because an XPath predicate and a mail header are
the same question about the same kind of parser. One limit of that is worth stating rather
than discovering later: the Playbook triggers on `xml_request`, so a line-oriented header sink
on a JSON or form route is written into the document -- step 1 names it, step 2's control is
built for it -- and is not selected for. Making it selectable needs a fact about where a value
lands rather than about what the body is, which is a vocabulary question 018's successor owns,
not something to bolt onto a trigger set that has to stay diagonal across thirty-five rows. `ssti` takes its one page. `nosql-injection`,
`orm` and `spreadsheet-injection` are rewritten with nothing attached: the first was a payload
list, the second was organised by mapper, and every payload the third named executes on a
reader's machine, so a reference would be material arguing with the document holding it.

### Three new leaves, and why the interpreter cut needed them

Four of the seven land on leaves 018 already named -- `injection.query_language`,
`injection.command`, `injection.template`, `injection.document_parser` -- and this is the
ticket that finally claims them, because every Playbook before it was about a browser, an
identity or an authorisation decision. The other three are interpreters 018 did not name, and
each is a separate leaf for 018's own stated reason: the test is different in each.

`injection.query_operator` is the caller's bytes becoming part of the query's grammar without
ever being a string. There is no quote to escape and no syntax error to provoke, so the whole
of the `query_language` reading -- send a quote, watch it break -- is inapplicable, and what
goes in is a structure.

`injection.query_field` is the caller naming a stored field. The generated query is always
syntactically valid, so nothing ever errors, and the signal is a change in which rows or
columns came back rather than in whether the route worked. That is why its fixture's two halves
differ only in an ordering.

`injection.formula` is the one where the interpreter is not on the target at all. It is the
spreadsheet application on the machine of whoever opens the exported file, which is why its
evidence lives in an Artifact rather than in a response, and why its three evidence rows are
`content_match`.

### What tells the seven apart on the Surface

Five new facts. Four are technology families -- `tech_sql`, `tech_document_store`, `tech_orm`,
`tech_template` -- each mapping a set of fingerprints onto one fact for the reason `tech_cdn`
does: a reading that asks whether a value reached a query language does not care whether MySQL
or Oracle answered, and one that did care would be a reading about a dialect. The fifth is
`xml_request`, the body shape 003's `json_request`, `form_request` and `multipart_request` left
out.

They are what keeps `PlaybookCorpusSelectionTest` diagonal across a table that grew from
twenty-eight rows to thirty-five, and nothing else would have done it. `sql-injection` and
`orm` want the same authenticated read with a query parameter, and `jwt-jose` already had that
shape; `nosql-injection` wants the same typed JSON write `race-conditions` has. What is behind
the route is the question these three ask, so what is behind the route is what triggers them,
and `nosql-injection` states its auth as unknown so that the caller's standing separates it
from `race-conditions` rather than the store alone. The remaining three are separated by the
body instead, because their interpreters are reached through it rather than named by a
fingerprint: a file in a multipart body, an XML body, and a form post whose value comes back.

### The fixtures, and the two controls every one of them carries

Every pair holds one class and enforces everything else identically on both halves, and each
ground truth names the neighbouring class it keeps out. What is new in this ticket is criterion
5's second and third asks, which no earlier fixture had: beside the secure twin, every pair
carries a **noisy endpoint** whose body changes on every request and a **decoy** that reflects
the payload and interprets nothing. Seven of these readings are differencing two responses, and
those are exactly the two ways differencing goes wrong -- a reading that never established what
"the same response" looks like, and a reading that treats a reflection as an interpreter. A
Playbook that always fires hits both.

The design cost of the decoy was that three subject routes had to stop echoing. `/reports`,
`/documents/convert` and `/services/orders` each returned the submitted value in their first
draft, and because the two variants differ by one byte the echo made their responses differ on
the **secure** half too, which destroys the refutation -- and in `command-pair` put a probe
token in the answer on both halves. Reflection now lives only on the decoy routes.

`query-field-pair` is the pair with no errors on either half at all: `sort=risk_score` reorders
the rows against the vulnerable variant and does nothing against the secure one, and neither
half ever returns the hidden column. That is the honest shape of `injection.query_field` and it
is why its Playbook reads an ordering rather than a body.

`command-pair` is the one whose interpreter is real, for the smallest value of real that is
honest: a dozen lines that split on `;`, honour `echo` and a capped `sleep`, and convert
everything else. The cap is in the fixture rather than in the reading, because a fixture that
could be made to hold a connection for an arbitrary time would grade a reading's restraint by
punishing the suite. Its command line puts the filename last, as every converter that takes its
output as an option does, so that what follows a separator in the name is a whole command
rather than a command with a stray argument -- without that, the `; sleep 2` the ground truth
documents parses as `sleep 2 out.pdf`, never sleeps, and the timing channel the Playbook rests
on is unreachable at the one target that is supposed to prove it.

`document-parser-pair` recognises no doctype and no entity anywhere, on either half, so there
is no XXE in it. The class it grades is the predicate: an unbalanced quote in a reference moves
the parser's reported offset on the vulnerable variant and is escaped away on the secure one.

`formula-pair` stores two contacts rather than one. A writer that prefixed every cell would
look, from a single row, exactly like a writer that neutralised a formula, and only the
ordinary row tells them apart.

### Five evidence shapes, and one refutation that is not a `response_invariant`

Six of the seven refute with a `response_invariant` on the variant leg, and that is this
ticket's shape: the payload went in, the route answered exactly as it answers without it, and
nothing parsed anything. It is the strongest answer available here and it is why every one of
these documents sends an inert twin rather than a payload alone.

The supported kinds are four. `response_differential` for `sql-injection`, `nosql-injection`
and `orm`, all answered by which rows came back. `reflected_input` three ways for `ssti`,
because the claim is that a value was evaluated rather than copied. `timing_differential` for
`command-directory-injection`, because duration is the channel a converter leaves open.
`error_detail` for `structured-injection`, because a parser that reports where it stopped is
the finding: the offset moved with the payload, which says the bytes were parsed as document
rather than held as text.

`spreadsheet-injection` is the exception on both counts. All three of its rows are
`content_match`, whose only allowed provenance is a tool run, and that is the honest source: the
evidence is a cell inside a downloaded export, so what says the cell is there is a run over the
Artifact rather than a response body. There is nothing in a response to be invariant about.

That is also where criterion 4 is answered, and it is answered per reading rather than in the
abstract. `command-directory-injection` interleaves its timing pair -- variant, control,
variant, control -- rather than sending two blocks, because backend latency drifts and a block
comparison measures the drift; it reports the separation between two sampled sets with the
counts and the spread stated, never one request that took five seconds. The three boolean
readings send a TRUE arm and a FALSE arm against a baseline pair that was itself invariant, and
the verdict rests on the arm-vs-arm difference: at a real defect the TRUE arm matches the
baseline and the FALSE arm moves, which is the attribution the first draft of three of these
documents had backwards.

The criterion's other half is the repeat policy, and each document now states one as a count
rather than as an adverb, because "several rounds" is not a policy an evaluation can hold a
reading to. `command-directory-injection` samples five interleaved rounds and may run five
more, once, if the sets overlap; the three boolean readings repeat the arm pair three times and
call a differential that does not reproduce in all three inconclusive; `structured-injection`
sends its three requests twice; `ssti` sends its pair twice with a different arithmetic result
in the second round, which is a check that the number in the response is this reading's number
rather than a retry. `spreadsheet-injection` is the one whose repeat is on the read alone: two
exports, two Artifacts, one written record, because the record is somebody else's row to clean
up and the export costs nothing. The machine-readable side of this is 046's
`playbook_test_policy.required_repeats`, which is an evaluation-wide setting this ticket does
not change.

### Risk, effects, and the one that is not read-only

Five are `constrained` and `read_only`. `command-directory-injection` is `approval_required`
for a reason narrow enough to state exactly: every observation it makes runs a process on
somebody else's host, and nothing it sends writes or persists. Whether a Program's rules of
engagement admit that is the operator's judgement, and step 1 does not begin without it.

`spreadsheet-injection` is the only Playbook in this ticket that is not `read_only`. It has to
store a contact, an order line, a display name -- the record must exist before it can be
exported -- so it is `mutates_object`, which 032's `RISK_FLOOR` puts no lower than
`constrained`, and its own step 1 asks for the grant anyway.

All seven carry `compare-responses` and `use-identity`, the first ticket where one Skill set
covers the whole set, because every one of these readings sends two requests differing in one
thing under a leased Identity. `structured-injection` and `spreadsheet-injection` add
`handle-untrusted-content`, both because the material being read is the target's own output --
a parser's error text and a file the target produced -- rather than the reading's.

Every document's last step is its refusal list, and across the seven it is the same discipline:
no union or extraction, no stacked queries, no sandbox escape, no `xp_cmdshell`, no
`COPY FROM PROGRAM`, no NetNTLM capture, no out-of-band DNS, no reverse shells or webshells, no
sending mail, no entity resolution, no live spreadsheet formula. Filter bypass gets exactly one
probe and only as a diagnostic, because getting past a filter is not itself a result. And no
reading escalates its delay until a signal appears: if the arms do not separate the answer is
more samples, not a longer sleep, which is how a reading becomes an outage without anybody
deciding to cause one.

### What the two-axis review moved

Four of its findings were defects rather than notes.

`sql-injection` could not report a true positive. Step 6 required the filter probe to match
the baseline, and step 5's probe is by construction not valid SQL where it lands, so against a
route that really concatenates it returns a syntax error or an empty result -- never the
baseline. The test is that the probe did not *reproduce the true arm*, which is what the step
was for: a route grading request text answers hostile-looking bytes the same way twice, and an
engine does not.

`structured-injection` shipped a `control`/`response_invariant` row with nothing for the
control to be invariant against: `bb:baseline: none` means the document never asked for an
ordinary request, and steps 1-4 sent only the two arms. Step 2 sends three requests now, the
ordinary one first, and step 5 differences the control against it. Its encoding ladder is one
probe rather than three, which is what the ticket's own discipline says, and the doctype whose
entity resolved to a literal string is gone: a declaration that looks inert to the reading
sending it is still a declaration handed to a parser nobody has measured.

`command-pair` and `formula-pair` served their subjects to anybody. Both Playbooks are
`stable_session` and carry `use-identity`, and every other `stable_session` Playbook in the
corpus is graded by a fixture that holds a session, so these two graded a claim they could not
exercise. Both routes are behind a cookie now -- which is the honest shape in each case: the
timing reading calls a separation a property of one caller's conversions, and the formula
reading writes a record and then fetches the export that has to contain it.

`document-parser-pair` carried its parser offset in `ValueError.args[0]`, in a file that also
raises `ValueError` with a sentence in it. The offset has its own exception now, and the
vulnerable variant's ordering key comes from a stated column list rather than from whatever
keys the first stored record happens to have.

### What moved in the ledger

Twenty-seven rows crossed from promised to built: seven `playbook:<name>` and twenty
`reference:playbooks/<topic>/references/<file>.md`, now citing `tests/test_playbook.py`
instead of `ticket:53`. The report's last line reads `built 133 promised 38 retired 52`.

Resolving this ticket came due on 48's rule for the fifth time, and moved the same example test
49, 50, 51 and 52 moved. `test_a_row_that_names_an_open_migration_ticket_is_promised` had been
using `playbook:command-directory-injection` and `ticket:53`, which stopped being a promise
here; it uses `playbook:deserialization` and `ticket:54` now.
