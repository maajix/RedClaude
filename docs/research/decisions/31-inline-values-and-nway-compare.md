# 31 — Two decisions settled by measurement

Both tickets ask a question that reading cannot answer, so both were run. The
work is at `/tmp/rk2-proto`. Four of the six subjects for ticket 107 are the
ones ADR 0006 fetched for its own measurement and are reused here rather than
invented; the HTTP responses and the JSON documents were fetched live on
2026-08-22. Token counts are `cl100k_base`. The database experiment in ticket
109 ran against a private migrated database named `rk2_proto_a`, which was
dropped afterwards.

## Ticket 107 — inline the value or refresh the packet

### What was measured

The first question the ticket poses is how big the thing B would inline is, so
every registered offline tool was run on a real input and its standard output
weighed. The six registered programs are `jq`, `js_parse`, `js_routes`,
`js_map`, `compare_responses` and `extract_paths`
(`src/redkraken/migrations/20260814T030000Z__an_offline_tool_becomes_evidence.sql:159`,
`20260814T050000Z__source_becomes_a_grounded_conclusion.sql:436-448`,
`20260922T030000Z__a_skill_script_is_a_program_the_harness_ships.sql:443-455`).
The commands were `python3 src/redkraken/jsscan.py <question> <file>` for the
three `jsscan` rows, `/usr/bin/jq <filter> <file>` for `jq`, and the script
itself over a `skill.envelope` document on standard input for the two Skill
scripts, which is exactly how `tool._perform` feeds them
(`src/redkraken/tool.py:748-770`).

| Program | Real input | Input bytes | stdout bytes | stdout tokens |
| --- | --- | ---: | ---: | ---: |
| `js_parse` | `@octokit/plugin-rest-endpoint-methods` 10.4.1 `dist-web/index.js` | 87,967 | **158,222** | **49,237** |
| `js_parse` | `swagger-ui-dist` 5.11.0 `swagger-ui-bundle.js` | 1,400,489 | 16,124 | 5,495 |
| `js_parse` | monaco `editor.main.js` | 3,469,378 | 8,819 | 2,944 |
| `js_parse` | `react-dom` 18.2.0 production min | 131,882 | 2,269 | 794 |
| `js_parse` | `vue` 3.4.21 | 147,534 | 1,045 | 374 |
| `js_parse` | `moment` 2.30.1 with locales | 375,055 | 340 | 133 |
| `js_routes` | all six of the above | 87,967 to 3,469,378 | 182 to 184 | 78 to 84 |
| `js_map` index | `swagger-ui-bundle.js.map`, 1,722 sources | 1,905,485 | **260,942** | **80,938** |
| `js_map` index | `axios` 1.6.8 `axios.min.js.map`, 43 sources | 142,627 | 4,134 | 1,373 |
| `js_map` select 5 | the same axios map | 142,627 | 4,300 plus a 1,559-byte declared output | 1,449 |
| `extract_paths` | the octokit bundle | 87,967 | **72,102** | **19,917** |
| `extract_paths` | the swagger bundle | 1,400,489 | 677 | 215 |
| `jq '.'` | `registry.npmjs.org/vue` | 2,090,619 | **2,775,503** | **966,253** |
| `jq '.'` | `petstore3.swagger.io/api/v3/openapi.json` | 17,106 | 32,787 | 6,878 |
| `jq '.versions\|keys'` | `registry.npmjs.org/vue` | 2,090,619 | 8,408 | 5,455 |
| `compare_responses` | two `api.github.com/user` transcripts | 1,244 and 1,085 | 520 | 209 |

The second question is what an `http_request` response Artifact weighs. Ten
targets were fetched and the received transcript assembled the way `proxy.py`
assembles it, a start line and the headers and the body
(`src/redkraken/proxy.py:850-882`, called at `:2966`). "Seen today" is the
document `_spend` returns, with the header list bounded at `HEADERS_EXCERPT`
and the body at `packet.DEFAULT_EXCERPT`, both 4,096
(`src/redkraken/_launch.py:111`, `:899-911`; `src/redkraken/packet.py:60`).

| Target | Status | Body bytes | Transcript bytes | Seen today, bytes | Seen today, tokens | Whole transcript, tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `github.com/login` | 200 | 46,991 | 52,051 | 5,068 | 1,384 | 15,762 |
| `api.github.com/` | 200 | 2,262 | 3,559 | 3,954 | 1,132 | 1,035 |
| `petstore3.swagger.io/api/v3/openapi.json` | 200 | 17,106 | 17,480 | 5,083 | 1,194 | 3,911 |
| `accounts.google.com/.well-known/openid-configuration` | 200 | 1,399 | 2,253 | 2,665 | 798 | 655 |
| `en.wikipedia.org/wiki/HTTP` | 200 | 619,368 | **625,735** | 4,746 | 1,151 | **195,582** |
| `reddit.com/robots.txt` | 200 | 538 | 1,699 | 1,977 | 607 | 532 |
| `httpbin.org/status/404` | 404 | 0 | 238 | 375 | 119 | 74 |
| `news.ycombinator.com/` | 200 | 34,430 | 35,142 | 5,241 | 1,637 | 11,951 |
| `developer.mozilla.org/en-US/` | 200 | 121,525 | 124,578 | 7,707 | 2,323 | 30,551 |
| `pypi.org/simple/requests/` | 200 | 82,826 | 84,486 | 6,089 | 2,543 | 39,573 |

What the child loses to the excerpt was measured on the same ten bodies by
counting the same patterns inside the first 4,096 bytes and in the whole body.

| Target | Excerpt covers | Inside the excerpt, of the whole body |
| --- | ---: | --- |
| `github.com/login` | 8.7% | 0 of 1 `<form`, 0 of 16 named inputs, 0 of 9 `<script src`, 0 of 4 CSRF-shaped tokens |
| `en.wikipedia.org/wiki/HTTP` | 0.7% | 0 of 2 forms, 0 of 12 named inputs, 0 of 155 rooted `href` paths |
| `news.ycombinator.com/` | 11.9% | 0 of 1 form, 0 of 1 named input, 0 of 1 `<script src` |
| `developer.mozilla.org/en-US/` | 3.4% | 4 of 4 `<script src`, 22 of 158 rooted `href` paths |
| `pypi.org/simple/requests/` | 4.9% | nothing of that shape present |

The third question is how many labels one realistic Task mints. The
`authentication` Playbook is a fair case because it is one of the eleven ticket
109 names. Its step 2 instructs two exchanges (`playbook.md:43` and `:47`), its
step 3 instructs eight, one per bullet with the JSON-type bullet naming four
values and the signature bullet naming two, "and each is sent once"
(`:59-67`), and its step 4 asks for the variant against each of two baselines
(`:74`), which is sixteen calls with a two-argument script. Every exchange
mints one Receipt and, once ticket 106 lands, two agent-view Artifacts. Every
tool run mints one `tool_runs` row and exactly two Artifacts, because
`tool._streams` keeps standard output and standard error whether empty or not
(`src/redkraken/tool.py:790-804`), plus one per declared output. So one run of
this one Playbook mints 10 x 3 + 16 x 3 = **78 labels**. The shipped per-run
request ceiling is `run_requests = 50` (`README.md:205`), so the configured
worst case is 150 labels from exchanges alone.

Those rows were then weighed in the packet's own encoder, `packet.encode`
(`packet.py:101-108`), against the projections the views already carry: the
Receipt projection at
`20260814T080000Z__a_refutation_is_kept_and_made_due.sql:1263-1286`, the
Artifact projection at `packet.py:567-580`, and the `tool_run` projection at
`20260814T080000Z...:1290-1308`.

| Row | Encoded bytes | Tokens |
| --- | ---: | ---: |
| one Receipt | 663 | 202 |
| one Artifact | 352 | 113 |
| one `tool_run` | 565 | 185 |
| one exchange after ticket 106, being one Receipt and two Artifacts | 1,367 | 428 |
| one tool run, being one `tool_run` row and two Artifacts | 1,269 | 411 |

The ceilings those numbers are against are three. The packet's whole document
ceiling is `min(byte_limit, token_limit * 4)`, which with the shipped defaults
of 65,536 and 8,192 is **32,768 bytes** (`packet.py:58-59`, `:133-134`). A
single Artifact head is staged at 4,096 bytes and never more (`packet.py:60`,
`_excerpts` at `:717-758`). The run's whole token budget in the shipped example
configuration is `run_tokens = 40000` (`README.md:204`).

The fourth question is what A would actually cost, and the answer is that the
channel A needs already exists and already carries a call from the child to the
supervisor and back. `Channel.call` writes one JSON line under `rk2_call` on
the child's standard output and blocks on one line back under `rk2_answer`,
matched by an integer `id` (`src/redkraken/_launch.py:399-467`;
`isolation.CALL` and `isolation.ANSWER` at `src/redkraken/isolation.py:152-153`,
framed and answered by `isolation._framed` and `isolation._served` at
`:547-580`). The supervisor's side is one closed dispatch on `verb` that already
answers `unknown_call` for anything else, and it already opens a database
connection lazily for the calls it does serve
(`src/redkraken/agent.py:1193-1240`). Three further facts make A cheaper still.
`v_records` already projects a `tool_run` kind with fourteen fields, so a
`tool_runs` section needs no new SQL; `packet.RECORD_KINDS` maps only three of
the kinds that view offers (`packet.py:49`). `Reader.packet` is a plain
attribute holding a `replace`-able dataclass (`packet.py:825-830`), so merging
new rows into what the child reads is an assignment. And
`packet.compile` needs an `rk2_state` connection rather than the runtime one
`_Tools` holds, which is the one genuinely new thing A costs: a second
`pg.Settings` on `agent.Tooling` and the same four calls `execution._packet`
already makes (`src/redkraken/execution.py:1823-1859`).

### What it decides

**A, the refresh path.** The number that decides it is **32,768**, the packet's
whole byte ceiling, set against **158,222**, the bytes one `js_parse` run
produced on a real 88 KB bundle. One act-tool result under B would be 4.8 times
the entire read surface the run is held to, and at 49,237 tokens it is 1.23
times the run's whole 40,000-token budget. The response side is worse by
another order: the `en.wikipedia.org/wiki/HTTP` transcript is 625,735 bytes and
195,582 tokens, which is 4.9 times that budget for one exchange, and a run may
make fifty.

B is also not a new design. It is the design that already shipped for the case
where the value is small: `run_tool` already returns a 4,096-byte head of
standard output (`tool.py:520-535`), and ticket 94 already put the response
headers and a 4,096-byte body excerpt in `_spend`'s answer
(`_launch.py:899-911`). The `compare_responses` output measured above is 520
bytes, which is already entirely inside that head. The labels exist precisely
for the cases those excerpts do not cover, so "carry the value instead" either
changes nothing, for the small case, or is the arithmetic above, for the large
one.

A's cost is small and was established rather than assumed. There is no new
transport to build: the child reaches the supervisor today on the two file
descriptors the launch already has, and the supervisor already holds a live
connection when it answers. The added surface is one verb on a dispatch that is
already keyed on verb, one `Contract` in `roster.CONTRACTS`, one connection
setting on `agent.Tooling`, and a reuse of `packet.compile`.

Two things must be said with the verdict, because the measurement says them.

The first is that a full refresh cannot honour the ticket's fourth criterion by
handing back everything. The rows one `authentication` run mints are 10 x 1,367
+ 16 x 1,269 = **33,974 bytes**, which is already over the 32,768-byte ceiling
before any Artifact head is staged. So the refresh has to be bounded and has to
report its own bound the way `_page` already does with `packet_bound`
(`packet.py:966`). The honest shape is a refresh scoped to the labels the child
names, which is what `Reader.receipts` and `Reader.artifact` already take.

The second is that neither A nor B fixes the read that the excerpt measurement
above is actually about, and this is the finding that makes both options
partly wrong. `_window` reads the *staged head* and nothing else: a `range`
past `staged_bytes` returns `range_beyond_excerpt` and no content
(`packet.py:981-1009`). So even a perfect refresh gives a child at most 4,096
bytes of any one Artifact, and on `github.com/login` that is 8.7% of the body
containing none of the sixteen input names. The route that reads a whole
Artifact already exists and is the right one: `run_skill_script` hands the
program the entire Artifact with nothing truncated on the way in
(`tool.py:741-748`, `skill.envelope` at `skill.py:170-193`) and answers a
bounded summary. What is missing is not a value and not a refresh but the
label that makes that route addressable from an exchange, which is ticket 106.
107 should therefore refresh the *rows*, not the values, and should say
explicitly that the way to read past byte 4,096 of any Artifact is a tool run.

### What would change the answer

One measurement flips this: if the largest stdout any registered program can
produce on a realistic input fell below the packet's ceiling, B would be right
and A would be unnecessary work. The registry already bounds it, at
`max_output_bytes` of 4,194,304 for the three `jsscan` rows, 2,097,152 for the
two Skill scripts and 1,048,576 for `jq`, and lowering those to something under
32,768 is a one-line registry change. The reason not to is in the table: the
octokit `js_parse` answer is 158,222 bytes because that bundle holds 591
distinct API paths, and a program that answered a bundle's whole surface in
32,768 bytes would be answering a different question. Re-run the first table
against a corpus of real target bundles rather than library bundles; if the
95th percentile of `js_parse` output on it is under 32,768 bytes, reopen this.

The second flip is on the label count. Ticket 106 is what turns one exchange
from one label into three. If 106 lands handing back one Artifact label per
exchange rather than two, one `authentication` run mints 10 x 2 + 16 x 3 = 68
labels and 10 x 1,015 + 16 x 1,269 = 30,454 bytes of rows, which is under the
32,768 ceiling, and an unscoped refresh becomes expressible. That is a
different design than the scoped one recommended above and it is worth
re-measuring when 106 is written.

## Ticket 109 — N-way compare or fan-out

### What was measured

The script was run rather than read. Four real arms were fetched from
`api.github.com/user`, which is the shape `authentication` asks for: the
credential structurally absent, wrong, empty, and of the wrong JSON type. The
received transcripts are 1,244, 1,085, 1,083 and 1,085 bytes. Each call was
`python3 envelope.py <arms> | python3 src/redkraken/skills/compare-responses/scripts/compare.py`,
where `envelope.py` builds exactly what `skill.envelope` builds
(`src/redkraken/skill.py:170-193`).

| Call | Exit | Output |
| --- | ---: | --- |
| two artifacts | 0 | 520 bytes of JSON: `identical false`, `lengths [1244, 1085]`, `line_counts [29, 23]`, 8 lines in `only_in_first`, 2 in `only_in_second`, `shared_lines 21` |
| three artifacts | 2 | nothing on stdout; `compare takes exactly two artifacts` on stderr |
| one artifact | 2 | nothing on stdout; `compare takes exactly two artifacts` on stderr |

What `only_in_first` and `only_in_second` become for N was then written as a
program and run, because the shape is the decision. A line's membership across
N inputs is a subset of the N arms, so the two fields generalise to one class
per non-empty membership mask, of which there are 2^N - 1. The measured shape
over the same real arms is this, where the key is the mask and `1` in position
k means the line is present in arm k:

```
{"identical": false,
 "lengths": [1244, 1085, 1083],
 "line_counts": [29, 23, 23],
 "classes": {"001": [...1 line], "010": [...1], "011": [...1],
             "100": [...8], "111": [...21]},
 "shared_lines": 21}
```

`only_in_first` is the class `100`, `only_in_second` is `010`, and for N = 2
that is the whole lattice, which is why the current two fields are complete
there and nowhere else.

| N | Masks possible | Masks non-empty on the real arms | Partition answer, bytes | Fan-out: calls / bytes | All pairs: calls / bytes |
| ---: | ---: | ---: | ---: | --- | --- |
| 2 | 3 | 3 | 1,543 | 1 / 500 | 1 / 500 |
| 3 | 7 | 5 | 1,633 | 2 / 998 | 3 / 1,247 |
| 4 | 15 | 6 | 1,719 | 3 / 1,498 | 6 / 2,247 |

The partition is compact, because each line is written once whatever its mask.
It is also not the answer any of the eleven Playbooks is reading. Every one of
them reads a *pair verdict* out of the result, and the field carrying that
verdict is `identical`, which is a property of a pair. Its N-way generalisation
is not one boolean but the N(N-1)/2 booleans of a pairwise matrix, which is the
fan-out written a second way.

The eleven bodies were then read and classified. The question is whether each
wants all arms compared to each other or each arm compared to one baseline.

| Playbook and line | What the body says | Which it is |
| --- | --- | --- |
| `agentic-ai:75` | "over the baseline set and the variant set"; supported when "the marker appearing in the variant answers and in none of the baseline or control answers" | set against set, two groups |
| `authentication:74` | "over the variant and the two stored answers"; "matches the wrong-secret answer / matches the correct-secret answer / matches neither" | fan-out, 2 calls per variant |
| `browser-storage:64` | "over this answer, the step 1 answer and an anonymous answer" | fan-out, 2 calls |
| `browser-realtime:55` | "Three handshakes, one difference each"; the readings are the owner against the other Identity and against the anonymous one | fan-out on the owner handshake |
| `identity-lifecycle:63` | "over this answer, the answer from step 1 and the control from step 2"; "matches step 1 / matches step 2 / neither" | fan-out, 2 calls |
| `routing:77` | "over that answer, the completed-flow answer from step 1 and the pristine answer from step 2"; same three-way reading | fan-out, 2 calls |
| `web-cache:71` | "over this answer, the step 3 authenticated answer and the step 1 anonymous answer"; same three-way reading | fan-out, 2 calls |
| `workload-identities:68` | "over each variant and the two ends" | fan-out, explicit loop |
| `jwt-jose:82` | "over each variant and the two stored answers" | fan-out, explicit loop |
| `request-integrity:73` | "over the baseline and each arm" | fan-out, spelled in those words |
| `webauthn:60` | "over each variant against the two ends of the scale" | fan-out, spelled in those words |

Ten of eleven are fan-out. The eleventh is two groups rather than N arms.
**Zero of eleven ask for all arms compared to each other**, which is the only
thing an N-way answer would say that a fan-out does not.

Whether an N-argument script can be registered under the rule at
`20260922T030000Z__a_skill_script_is_a_program_the_harness_ships.sql:457-467`
was settled by running it against a migrated database rather than by reading
the constraint. A `third` argument of kind `artifact` at position 2, not
required, inserts cleanly and both standing checks stay empty:

```
INSERT INTO offline_tool_arguments (tool,name,position,value_kind,required,description)
VALUES ('compare_responses','third',2,'artifact',false,'a third artifact');
SELECT * FROM check_skill_scripts();   -- 0 rows
SELECT * FROM check_offline_tools();   -- 0 rows
```

An `integer` argument that would have carried an arity is refused by the
registry's own check, which is the answer to whether N could be a parameter
rather than a set of rows:

```
INSERT INTO offline_tool_arguments (tool,name,position,value_kind,required,description)
VALUES ('compare_responses','arity',3,'integer',false,'how many');
SELECT * FROM check_skill_scripts();
-- ('envelope_tool_takes_a_literal', 'compare_responses.arity')
```

So N is registrable, as a fixed maximum of fixed names with everything past
`second` optional, and it is not parameterisable. Calls against the widened row
set through `open_offline_tool_run` behaved as follows:

```
first+second                       -> [('first','X1'), ('second','X2')]
first+second+third                 -> [('first','X1'), ('second','X2'), ('third','X3')]
first+third  (second still required) -> REFUSED 22023: compare_responses requires the argument second
fourth (undeclared name)           -> REFUSED 22023: compare_responses takes no argument named fourth
```

With `second` also made optional and a `fourth` added, the hole case runs, and
it is where the rule as written stops holding:

```
all four                    inputs=[('first','X1'),('second','X2'),('third','X3'),('fourth','X4')]
                            envelope entries = ['cdb2708d','85316b1d','93926848','8dbd7393']
first+third (hole at 1)     inputs=[('first','X1'),('third','X3')]
                            envelope entries = ['cdb2708d','93926848']
first+second (the old call) inputs=[('first','X1'),('second','X2')]
                            envelope entries = ['cdb2708d','85316b1d']
```

The loop is `ORDER BY position` with `CONTINUE` on a missing optional
(`:289-299`), so a skipped middle argument compacts out. `skill.envelope`
carries only `sha256` and `text` per entry and no argument name
(`skill.py:189-193`), so the last two calls produce envelopes of identical
shape. The script reading `artifacts[1]` cannot tell the second artifact from
the third, and would print `only_in_second` about the argument the caller
named `third`. The registry's stated reason at `:457-460` is that "the order is
part of the call and not a convenience"; the measurement says that promise is
made by the registry and is not carried across to the program.

### What it decides

**B, rewrite the eleven Playbook bodies as one call per arm against a
baseline.** The number that decides it is **10 of 11**: ten of the eleven
bodies already describe a baseline and a set of arms, and two of them
(`request-integrity:73` and `webauthn:60`) already spell the fan-out in those
words, so for those two the rewrite is not a change of meaning at all. Zero of
eleven ask for all arms compared to each other. Widening the script would
produce an answer with 2^N - 1 classes that no body reads, and every body would
still have to recover the pair verdict `identical` from it by hand.

The cost side agrees. For the N = 3 case the eleven mostly ask for, fan-out is
two calls and 998 bytes against a partition answer of 1,633 bytes, and the
partition is the one the model then has to reinterpret. The arithmetic only
turns against fan-out at N-squared growth that none of the eleven reaches:
`request-integrity:73` names "four requests in total ... and no more", and the
largest arm count anywhere in the eleven is the four-value JSON-type bullet in
`authentication:63-64`.

The registry finding closes it rather than opening it. N registers, so "the
rule as written forbids it" would be the wrong reason to decline; the right
reason is that the envelope cannot carry which argument each entry was, so a
widened script would be shipping a positional promise it cannot keep. Fixing
that means changing `skill.envelope` to carry the argument name, which changes
the input document of every Skill script and invalidates every declared case
in CI, to serve an answer shape no Playbook asked for.

Ticket 109's own fourth criterion is also right that this is downstream of 106
and 107. The rewrite the corpus half needs belongs to ticket 101, and it is
eleven paragraphs, each replacing "over X, Y and Z" with "against Y, then
against Z". None of the eleven changes its claim, its evidence profile or its
refutation condition, because the verdicts they already enumerate are pair
verdicts.

### What would change the answer

One measurement flips this: a body that reads a property of the arm *set*
rather than a pair verdict. `agentic-ai:75` is the closest thing to one in the
corpus, and it is not one either, because its reading is a marker present in
one group and absent from another, which the two-argument script answers over
two concatenated groups given a way to name a group. If ticket 101's rewrite
produces a body whose reading cannot be stated as a pair verdict or a
two-group difference, count how many such bodies exist; at three or more,
widening the script and paying for the envelope change becomes the cheaper
side.

The second flip is arity growth. Fan-out costs N-1 tool runs and therefore
3(N-1) labels, against 3 for one N-way call. At the arm counts the eleven
actually name, between two and four, that is 3 to 9 labels and it is not the
binding cost; at twenty arms it would be 57, which against the 78-label run
measured in the ticket 107 section above would matter. If a Playbook is written
that instructs more than ten arms in one reading, re-measure the label cost
before rewriting it as fan-out.
