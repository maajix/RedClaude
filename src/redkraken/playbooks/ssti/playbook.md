---
description: Ask whether a reflected parameter becomes part of a template's source rather than a value passed into it, by sending an arithmetic expression whose result cannot be confused with its input beside a one-character-shorter twin the engine cannot evaluate, and, where the sink renders nothing at all, by gating an exception on the answer, reading the computed value out of an error message, and submitting a stylesheet whose only effect is a fetch at a minted correlator.
bb:category: injection
bb:outputs: ["injection.template"]
bb:triggers_all: ["authenticated_endpoint", "reflected_parameter", "tech_template"]
bb:skills: ["compare-responses", "handle-untrusted-content", "use-identity"]
bb:risk: constrained
bb:effects: read_only
bb:baseline: none
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 53 as the v2 replacement for v1's ssti page against the template leaf of the ticket 18 vocabulary; the v1 text is attached as a maintainer reference and every sandbox escape and context read in it is refused by the closing section. Rewritten for ticket 101 against the merged ledger, which carries seven readings and one refusal for this slug; the shipped arithmetic pair is one of the seven and the other six are new, four of them for sinks that render nothing at all. One key moved -- handle-untrusted-content is added, because section 6 submits a document and reads what a processor sends back. bb:evidence is unchanged, and all three rows already ask for reflected_input -- one kind for the variant role whichever way the reading goes, written by promote_proposal from the same Receipt the Test closes on. Two corrections came from source rather than from the earlier draft -- bb:effects does not decide whether a request may carry a body, and body_equals reads the response body digest alone.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "reflected_input", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "reflected_input", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "reflected_input", "polarity": "supports", "min_count": 1}]
bb:references: ["ssti.md"]
---

# Ask whether the value became the template

A template engine takes source and takes values. A route that passes the caller's value
in as a value is doing what it was built to do; a route that pastes it into the source,
because the greeting is built with string formatting, has handed the caller the template
language. The subject is an authenticated endpoint whose parameter a pass saw reflected.

Every reading runs twice over and the order is not optional. First in the agent lane
through mcp__rk2__http_request, where mcp__rk2__run_skill_script differences the two
stored Artifacts with compare-responses and the mechanism edge is filed as a
reflected_input Observation WITH the proposal through mcp__rk2__submit_mission_result,
which promote_proposal writes: this Playbook asks a reflected_input of the variant role
and one of the control role, and an edge cannot be added once a claim is past proposed.
Then as a Test proposed with mcp__rk2__propose_test and closed by close_test_replay, the
only writer of the transition a Finding needs.

Every specification carries the same five actions, never re-ordered, because the ordinal
binds an action to its Receipt. Actions 1 and 2 are the role baseline, the ordinary value
twice unchanged, asserted body_equals, which reads the response body digest alone. Action
3 is the role control, the reading's own twin. Action 4 is the role variant, the probe,
asserted body_differs or status_differs against action 3, which makes both a
response_differential, and action 5 is the variant again with one constant changed. Fewer
than three actions, or a missing role, is refused at propose_test and never runs.

Since ticket 211 an action states its own headers and its own body, and the door opens a
replay run body-bearing because a Playbook was selected rather than because one admitted
to changing something, so a payload rides the query string or the body as the sink
requires; a setup or cleanup step carries a method and a url and nothing else. A
specification url is refused outright for a `.` or `..` path segment or `%2e` anywhere,
so a dot inside a payload is fine while one the agent encodes refuses the whole plan. No
step plans a Cookie or an Authorization value, and every send goes as whichever Identity
the Task was opened under, which is what keeps a pair comparable.

## 1. Name the parameter, the reflection and the engine

This step is a lead and nothing grades its outcome. It reads the recorded surface with
mcp__rk2__get_attack_surface and writes no Observation, because naming a sink is a
selection and not a reading. Read which parameter is reflected and where it lands: the
sink that matters is the one rendered by the server, not an attribute or a script block. Name the engine the
surface fact came from, because delimiters are not shared, `{{ }}` for Jinja and Twig,
`${ }` for Freemarker and JSP expression language, `<%= %>` for ERB, `#{ }` for others
again, and a probe in the wrong delimiter is a probe for a string. Where no fact named an
engine, section 4 runs in place of section 2, and only where the Task was selected for
another reason, since tech_template is in this Playbook's own trigger set. Every section
below reads the bytes the server sent and not what a browser renders.

## 2. Ask whether the value became the source

The probe is an arithmetic expression in the engine's delimiters whose result is a
different string from the expression itself, `{{7*7}}`. The result must appear nowhere in
the request: a probe whose output looks like its input is equally well explained by
reflection, which is what this surface already does. The control is the twin, the same
bytes with the closing delimiter one character short, `{{7*7}`, so the engine has nothing
to evaluate while a filter or a length check sees the same length and the same code path;
a control that omits the payload compares two response sizes through two code paths and
is not a control. Action 5 asks `{{8*8}}`, because a template that evaluated `7*7`
answers 64 when asked for 8*8 while a page holding 49 will hold it again. body_differs
names the probe against the twin.

Once that has supported, one more pair names the engine, which changes what everything
downstream is worth. `{{7*7}}` cannot separate two engines that both answer 49;
`{{7*'7'}}` can, because Twig renders 49 and Jinja2 renders 7777777. Action 3 is the
arithmetic arm and action 4 the coercion arm with body_differs between them, and action 5
carries `{{7*"7"}}` so an engine that errors on the quote style is not read as one that
refuses to coerce. What is evidential is the difference; the engine name that falls out of
it is a non-evidential technology_identified Observation filed through
mcp__rk2__submit_mission_result and settles nothing on its own. One pair, then stop.

## 3. Ask whether the value sits inside an expression rather than beside one

A value concatenated into template source and one placed inside an existing expression
are two defects, and the second renders nothing until the injected text closes the
expression. This reading has the state the shipped text used to read as refuted: the
plaintext probe came back verbatim. The baseline carries `data.username<tag>`, and where
`<tag>` appears in the body this is ordinary markup reflection, the class is
`injection.markup`, and the reading stops. The probe carries `data.username}}<tag>`,
closing the surrounding expression so the tag appears BESIDE the rendered value rather
than instead of it, with `%>` and `}` as the other spellings. The control is the
arithmetic probe in plaintext position, which must render 49 there and nothing here, and
body_differs names the closing arm against it.

## 4. Ask whether anything compiles it at all, when no fact named the engine

One value, `${{<%[%'"}}%\`, which every engine family chokes on, read by its STATUS
rather than its body. The control is a value of the SAME LENGTH made of harmless
punctuation, which must stay 200, so that a 500 is the syntax and not the length and not
a content filter. status_differs names the metacharacter arm against the control. What
this closes is only that the value reaches a parser, which makes it the step before
section 2 rather than a weaker version of it; the engine's error text rides as an
error_detail Observation beside the reflected_input. One string only: it raises inside the
rendering process, so a second send is a second exception in a process serving others.

## 5. Ask a sink that renders nothing, by the status and by the error

Two readings for a sink whose output is discarded, both needing evaluation established by
section 2 or section 4 first. Gate an exception on the answer. The baseline is `1/(0)`, the
condition that is certainly false, twice, answering 500; the probe is `1/(<condition>)`
where the condition is true, answering 200, spelled `1/((X)?1:0)+""` in SpEL and
`[""][0+!(X)]["length"]` in Node. The control is the polyglot pair `(3*4/2)` beside
`3*)2(/4`, of which the second must error and the first must not, proving the field
reaches a parser rather than being echoed. Both arms are the same length and shape, so a
filter cannot be what changed the answer, and status_differs names the true-condition arm
against the control. Declare the bit budget before starting and stop there.

Read the value out of the message. The baseline sends the expression quoted,
`getattr("", "7*7")`, so the error body carries the literal 7*7; the probe sends
`getattr("", 7*7)`, where the missing attribute name is the evaluated string and the
handler prints 49; PHP spells it `call_user_func(X)` and SpEL
`T(java.lang.Integer).valueOf(X)`, whose dots travel literally because an encoded one
refuses the specification. The control sends the constant, `getattr("", "49")`, whose
error body ALSO contains 49, which is why the proving pair is the quoted form against the
unquoted one: the error path reflects whatever it is handed. body_differs names the
unquoted arm, and the message rides as an error_detail Observation.

## 6. Ask whether a submitted document reaches a stylesheet processor

This step is a lead and nothing grades its outcome, and the reason is this Playbook's own
bar rather than the harness. Its product is an arrival, written by
record_callback_interaction and filed as a callback_interaction edge with the proposal,
while the bar asks a reflected_input of the variant and control roles, which a sink that
reflects nothing cannot produce. The edge is real and the claim it supports stays proposed.

Where the surface records submitted XML or an assertion consumer, the sink can be a
stylesheet processor with no output channel at all. Mint a correlator with
mcp__rk2__mint_callback, naming the channel the Program declared in `channel` and this
reading in `subject_label`; arrival_kind is dns or http and an XSLT document() call is
an http fetch, so the lane fits. The payload is
`<xsl:copy-of select="document('http://<correlator>/')"/>` as the whole submitted document
through mcp__rk2__http_request and then, as a separate attempt, the same select inside a
valid signed document's ds:Transform node, since the transform may only run when what
surrounds it is valid. Three controls: document() replaced by a literal string, which must
not arrive and which separates a processor that EVALUATED the transform from a consumer
that dereferences any URL it is handed; two identical sends of the ordinary document; and
a correlator minted and never sent anywhere, read for freshness and writing no Observation
at all, because a correlator that is about nothing has no subject to file against. No
arrival inside the window is the absence of a proof rather than a refutation. document()
reaches the correlator and nothing else, never a local scheme, never a file path.

## 7. State the claim, and state what would refute it

The Hypothesis is `injection.template` on the endpoint, carried to a Finding with
mcp__rk2__propose_finding once a Test has settled it. This section proposes no Test of
its own and grades nothing. It is supported when the probe's evaluated result is in what
the server sent, the control came back as it was sent, the two baseline reads were
invariant, and the fifth action tracked the constant it was asked for. It is refuted
when both arms come back verbatim and alike: the value reached the sink and was passed
as a value. An engine that rejected the probe is its own outcome and not the supported
verdict, since the control is the malformed arm by design; so is an engine that errored
on BOTH arms, and that halt goes into this Task's own record, because no question code
in the served set says a reading ran out of probes. Two neighbours are close. Where the
value came back verbatim into markup and a browser acted on it, the class is
`injection.markup`, and verbatim reflection is this Playbook's refutation and that one's
precondition. Where an Angular or Vue application evaluated the expression client-side,
the class is `injection.client_channel` and the Playbook is browser-messaging. Cite both
Artifacts, the compare-responses result, and action 5.

## 8. One multiplication, and nothing that escapes the sandbox

This section performs and grades nothing. This Playbook is read_only and it evaluates
arithmetic. It does not walk an object graph to reach a runtime, call a class loader, read
the template context, print the application's configuration or its secret key, read a file
through a template loader, or run a command. Named so they are not re-proposed as cheap:
Jinja through `__class__` and `__subclasses__` to a process call, Freemarker's Execute,
Velocity's class tool, Twig's registered filters, ERB backticks, `{{config}}`, and bare
enumeration of the context's identifiers. The refusal is a decision rather than a capability
gap, because name resolution in a template IS a body differential and an escape's side effect
WOULD be filable now that an arrival carries a bar. The chains are long, version-specific and
they half-work, leaving a template context nobody can describe in a process serving other
people, while a multiplication evaluates and leaves nothing behind. Where an escape is asked
for anyway, ask for this Task to be parked with mcp__rk2__park_for_human under this Task's
`task_label` and a `question_code` of destructive_action rather than sending it, since a
half-applied escape changes state at the target. Impact belongs in the report.

4 of 8 steps cannot be graded.
