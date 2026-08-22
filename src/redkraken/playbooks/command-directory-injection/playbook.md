---
description: Ask whether an uploaded file's name is concatenated into a command line, by sending a name carrying a bounded delay beside a name carrying the same characters inert and reporting the separation between two interleaved sets of samples.
bb:category: injection
bb:outputs: ["injection.command"]
bb:triggers_all: ["file_parameter", "multipart_request", "state_changing_method"]
bb:skills: ["compare-responses", "use-identity"]
bb:risk: approval_required
bb:effects: read_only
bb:baseline: stable_session
bb:status: draft
bb:stale_after: 2027-03-15
bb:provenance: Written for ticket 53 as the v2 replacement for v1's command-directory-injection pack against the command leaf of the ticket 18 vocabulary; the pack's five pages are attached as maintainer references, two of them (ldap-injections, xxe) describe classes graded by sql-injection and structured-injection respectively, and every escalation step in the other three is refused by step 7.
bb:evidence: [{"to_status": "refuted", "role": "variant", "kind": "response_invariant", "polarity": "refutes", "min_count": 1}, {"to_status": "supported", "role": "control", "kind": "response_invariant", "polarity": "supports", "min_count": 1}, {"to_status": "supported", "role": "variant", "kind": "timing_differential", "polarity": "supports", "min_count": 1}]
bb:references: ["command-injection-filter-bypass.md", "ldap-injections.md", "os-command-injection.md", "shells.md", "xxe.md"]
---

# Ask whether a shell read the filename

Routes that accept a file rarely handle it themselves. They shell out: to a
converter, a thumbnailer, an archiver, a virus scanner, a font renderer. The
command line is built by formatting, and the easiest thing to format into it is
the name the caller supplied.

The subject is a state-changing endpoint taking a multipart body with a file
parameter. The question is whether the filename reaches a shell, and the answer
is a difference between two sampled distributions rather than a fact about one
request.

## 1. Name the endpoint and get the approval

This Playbook's risk is `approval_required`, and the reason is narrow enough to
state exactly: every observation it makes runs a process on somebody else's host.
Nothing it sends writes, stores or persists, and it still executes. Whether a
Program's rules of engagement admit that is the operator's judgement, not this
document's, and the reading does not begin without it.

Complete this step with the endpoint, the file parameter, and the grant.

## 2. Establish the baseline, and measure what normal costs

Send the request through `mcp__rk2__http_request`, uploading a small, valid file
with an ordinary name. Send it several times. Every one of them goes out as
whichever Identity the Task was opened under: the step does not choose it and
there is no argument for it.

This measures two things the reading needs. First, that the route works and what
it answers. Second, and more important, how long it takes and how much that
varies -- because a timing claim against an unmeasured distribution is one sample
with an opinion attached.

Note any ceiling. If the route or its gateway cuts requests at a fixed duration,
the delay this reading asks for must be well under it, or both arms return at the
ceiling and a live injection reads as refuted.

## 3. Try the cheap channel first

Before any timing, send one upload whose filename contains a statement separator
followed by a token that would appear in output if a shell ran it, and read the
response.

Output in the response is the cheapest evidence there is: one request, one
comparison, no distribution to reason about. Many converters echo the command
line or its error into the response body, and a route that does answers this
question immediately.

Run `compare-responses` over that response and the baseline. If the token or a
shell-shaped error is there, the reading is done and step 6 reads it. If the
response is identical, continue.

## 4. Send the timing pair, interleaved

Two filenames, differing in one thing:

* the variant: the ordinary name with a separator and a bounded delay appended
* the control: the same name, same length, same separator characters, with the
  delay replaced by a command that does nothing

Both arms carry the separator. That is what makes the control a control: if a
filter is stripping the separator, it strips it from both, and the difference
that remains is about what the shell did rather than what the filter matched.

Send them alternately -- variant, control, variant, control -- rather than as two
blocks. Backend latency drifts, deployments roll, pools refill, and a block
comparison measures the drift.

The repeat policy is five rounds, ten requests, and it is not negotiable
downwards: three samples an arm is the fewest from which a separation and a
spread can both be stated, and five leaves room for one round to land in a
garbage collection pause without deciding the verdict. If the two sets overlap
after five rounds, run five more and stop there. A third five is not a
measurement, it is a route being hammered until it agrees.

Choose at least one separator from each of three families across the rounds: a
statement separator, a substitution, and a newline. A route running `cmd.exe`
ignores a semicolon because a semicolon is an ordinary character there, and a
reading that tried one family and stopped has reported the separator rather than
the route.

## 5. Report the separation, not the duration

Cite the samples. The claim is that the variant's durations separate from the
control's, with the counts and the spread stated. It is not that one request took
five seconds.

The delay stays small -- a signal, not an outage. A route with a connection pool
that is asked to hold connections for ten seconds at a time is a route this
reading has taken down, and no verdict is worth that.

## 6. State the claim, and state what would refute it

The Hypothesis is `injection.command` on the endpoint. It is supported when the
variant's durations separate from the control's across interleaved samples, or
when step 3's token came back, and the control is invariant against the baseline.
It is refuted when the filename comes back byte for byte with every separator
intact and the timing arms do not separate -- something encoded the name at the
sink, which is the strongest possible answer.

Inconclusive covers a ceiling that truncates both arms, overlapping
distributions with too few samples, a route that rejects every upload, and a
route that queues the conversion and answers before it runs.

Two neighbours are close.

* Where the value reaches a query rather than a shell, the class is
  `injection.query_language` and the Playbook is `sql-injection`. LDAP filter
  injection lands there too, which is why the attached `ldap-injections.md` says
  so.
* Where the value reaches a document parser -- an XML body, an SVG, an office
  document -- the class is `injection.document_parser` and the Playbook is
  `structured-injection`. That is where `xxe.md` is graded.

Cite the samples and the difference `compare-responses` returned.

## 7. One delay, and nothing that outlives the request

This Playbook is `read_only` and `approval_required`.

It appends a bounded delay or an echoed token to a filename. It does not open a
listener, write a file, fetch and run anything, start a process that outlives the
request, chain into a second command once the first has answered, enumerate the
host, or read a file off it.

It also does not escalate the delay until a signal appears. If the arms do not
separate, the answer is more samples, not a longer sleep -- the second is how a
reading becomes an outage without anybody deciding to cause one.

Filter bypass gets exactly one probe, and only as a diagnostic: if the direct
separator is refused and one inert substitution behaves like the unfiltered
request, the route filters characters instead of escaping them, and that
difference is the finding. Getting past a filter is not itself a result.
