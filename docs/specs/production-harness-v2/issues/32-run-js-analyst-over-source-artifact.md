# 32 — Run the JS analyst over a source Artifact

**What to build:** Let the JS analyst inspect a content-addressed JavaScript or source-map Artifact and propose grounded Surface or Hypothesis updates without target egress.

**Blocked by:** 30 — Promote offline Tool output through an Artifact.

**Status:** resolved

- [x] The JS analyst receives only reachable source Artifacts, the bounded Mission packet and its allowed offline analysis capabilities.
- [x] Its runtime has no target network capability, credential material or arbitrary Program read surface.
- [x] Source parsing, endpoint extraction and source-map recovery run through recorded Tool runs with exact tool and input hashes.
- [x] Proposed endpoints, parameters and hypotheses cite the source Artifact and Tool run that produced them.
- [x] Runtime promotion rejects conclusions citing missing, changed, foreign or non-source Artifacts.
- [x] A synthetic bundle with known routes and a secure decoy demonstrates grounded recall without invented endpoints.

## How each is met

1. What the analyst may be pointed at is a column rather than a convention.
   `offline_tool_arguments.artifact_kind` is `source` on all three tools, and
   `open_offline_tool_run` refuses an Artifact this Program holds any other way
   — including an earlier run's own output, which is what stops a tool
   laundering arbitrary bytes into source by printing them. An Artifact another
   Program holds gets the same answer a label nobody holds gets, so the argument
   cannot be used to ask what somebody else has. The capabilities are the three
   registry rows, granted in `offline_tool_roles` to `js_analyst` and to nothing
   else: `recon` keeps `jq` and finds hosts, and a second role holding these
   would be a second place a source conclusion could come from without the
   roster having said so. The packet is 028's, unchanged. Proven in
   `SourceCitationTest` (the two refusals and the argv) and end to end in
   `JsAnalystCommandTest.test_an_artifact_the_runtime_stored_is_not_something_an_analysis_may_read`
   and `test_no_role_but_the_analyst_may_ask_these_questions`.

2. All three tools are `network = 'none'`, so `isolation.run_tool` gives the
   container `--network none` and there is no adapter to reach anything with.
   `check_source_conclusions` re-asks that of the registry rather than of a run
   — `source_tool_has_network` fires on any tool that reads source and has
   acquired a network, because that would be true of every run made after the
   row changed. The read surface is the mount list: only `/input`, read only,
   holding exactly the analyser and the Artifacts the plan resolved, plus the
   `/work` scratch when a tool declares an output. No credential material can
   arrive because nothing but those files is mounted and the argv is built from
   the registry. `JsAnalystCommandTest.test_the_analysis_runs_with_no_network_and_reads_only_what_it_was_given`
   holds the network and the whole argv, which names two paths and no third.

3. The three analyses are `js_parse`, `js_routes` and `js_map`, one harness
   analyser (`src/redkraken/jsscan.py`) asked three questions. The tool name is
   the subcommand, so which analysis this is comes from the registry key rather
   than from an argument. `tool_runs.analyser_sha256` records the hash of the
   analyser bytes the runtime mounted, and `open_offline_tool_run` refuses a run
   where the registry and the runtime disagree about whether there is an
   analyser at all. `tool_run_inputs` records what the run was given — argument,
   label, sha256 and kind — inside the same statement that opens the row and
   before the process starts, so a run that never comes back still says which
   bytes it was going to read. `check_source_conclusions` reports an analyser
   run with no hash and a closed source run that recorded nothing.
   `JsAnalystCommandTest.test_the_run_records_the_analyser_and_the_bytes_it_was_given`
   holds both against a real container. The two hashes are not equally
   checkable and the schema says which is which: an input hash is verified
   against `artifact_references` by `tool_run_input_is_this_runs_input`, and the
   analyser hash is provenance the runtime supplies — the registry never sees
   the file, so it is the same kind of claim `tool_version` is, and the column
   comment says so.

4. `rk2_source_citation` is the one question asked in both directions: an
   element that names a source Artifact must have named one that holds up, and
   an element grounded in a run that read source must name which source. The
   second half asks the registry and the run together — did this run fill an
   argument declared to take source, with source — so a tool with an optional
   source argument is not made to cite one on a run that read none, and `jq`
   handed a file this Program happens to hold as source is not made to cite one
   either. It runs from
   `proposals_ground_source_citations`, an AFTER INSERT trigger on `proposals`,
   over all four element lists — `rk2_proposal_elements` is the one place that
   spells `promote_proposal`'s element paths, and both this trigger and the
   standing check walk it. Hypotheses are the reason it is a trigger: nothing
   promotes a Hypothesis, so a check inside `promote_proposal` would never see
   one, and the criterion names hypotheses beside endpoints and parameters.
   Endpoints and parameters are Entities and arrive in `new_entities`;
   Relationships are walked too, because a list left out is a list an ungrounded
   conclusion promotes through.
   `SourceCitationTest.test_the_endpoint_promoted_is_the_one_that_can_name_its_source`
   proposes an application, an endpoint and a parameter that can name their
   source and a second endpoint that cannot, and holds the canonical
   `endpoints` rows afterwards.

5. The refusal is a `proposal_drops` row, which is what every promotion walk
   already skips, so the element never becomes canonical. Six reasons, six
   different mistakes: `no_such_artifact` (missing or another Program's — one
   answer, deliberately), `artifact_not_source`, `artifact_changed` (the element
   named a hash and the label resolves to other bytes), `artifact_not_read` (the
   citation holds and the cited run never read those bytes),
   `no_source_citation` (grounded in a run that read source and does not say
   which) and `path_not_in_output` (the element proposes a route and the run it
   cites never reported it). The first five are about the citation and the sixth
   is about the answer, which is why it is the one that catches an invented
   route. `check_source_conclusions` re-asks the whole question of everything
   already promoted, which is how a citation that held when it was checked and
   stopped holding afterwards becomes visible.
   `SourceCitationTest.test_each_way_a_citation_fails_is_dropped_by_the_reason_it_failed`
   walks elements alike in everything but their citation, across all four lists,
   and gets one promotion and a refusal per way of failing.
   `test_an_artifact_another_program_holds_is_not_a_citation_either` is the one
   worth stating separately, because it is the only reason where the refusal
   depends on who is asking rather than on what the element says.

6. `SOURCE_BUNDLE` in `tests/test_database.py` holds three routes something
   requests — a template literal through `fetch`, an `axios.post` and a
   `$.ajax` with its method in an options object — and three paths nothing does:
   one in a comment, one assigned and never used, and one inside a regular
   expression. `js_routes` reports the three routes with the call site that
   grounds each, and none of the decoys: a path is a route only when it is
   lexically an argument of a request-shaped call. `js_parse` reports the one
   decoy that is a string literal with `requested: false` rather than dropping
   it, because an analyst has to be able to see the decoy in order to not
   propose it. `js_map` then recovers an original out of a source map, which is
   filed as `source` because its `offline_tool_outputs.reference_kind` says so,
   and `js_routes` over that recovered file finds a route the bundle does not
   contain — which is how "this came out of the map" is told from "this was
   already read".

## Two writers, one table

`proposal_drops` now has two: the trigger, at staging, and `proposal.stage`
afterwards. The ordinal is part of the key, so both ask `rk2_next_drop_ordinal`
where theirs starts and `stage` reports back what the table holds rather than
only what it wrote.
`SourceCitationTest.test_each_way_a_citation_fails_is_dropped_by_the_reason_it_failed`
pins the whole sequence, nine from the trigger and the tenth from the runtime.

## What a citation is not

A citation says which bytes a conclusion came from and which run read them. On
its own it does not say that the run reported that conclusion — an analyst that
reads a bundle through `mcp__rk2__get_artifact`, invents a route and cites the
bundle and a real `js_parse` run over it satisfies every rule about the citation
and is wrong.

`tool_run_paths` is the answer to that, and where it lives is the whole design.
What a run printed is an Artifact in the store, and the store is on the disk
rather than in the database, so a trigger reading a proposal has the hash of the
output and never its contents. The runtime does have the contents, once, while
it is filing them: `tool.run` reads the `paths` key out of the answer it just
stored and files one row per path against the hash it read them out of. What the
trigger then asks is a join. The rows are as checkable as everything else here —
the hash is on the row, so re-deriving the list is reading those bytes again.

Three things keep the table from becoming a way to write the ground truth. The
run has to be an analyser's, so a tool from the image printing a `paths` key
files nothing; the bytes have to be that run's own output; and the run has to
still be open, so the answer cannot be amended after it was reported. What is
left uncovered is what is not a route: an invented parameter, or a Hypothesis
about a file, is still grounded only by its citation, because the analysers
report paths and there is nothing else to hold those against.
