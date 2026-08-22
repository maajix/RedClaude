# 155 — An evidence edge written inside its claim is never read

**What to build:** Read the evidence edge wherever the child put it, so a claim
is graded on whether it cited support rather than on where it wrote the citation.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** `rk2hunt14`, 2026-08-22. Two recon
      runs, three claims proposed, all three dropped:

      ```
      hypotheses[0] | no_support | no evidence edge in this result supports it
      hypotheses[0] | no_support | no evidence edge in this result supports it
      hypotheses[1] | no_support | no evidence edge in this result supports it
      ```

      The claims were not unsupported. Every one of them carried its edge
      inside itself:

      ```json
      {
        "ref": "h_hdr",
        "evidence": [
          {"observation_ref": "o_hdr", "polarity": "supports", "role": "baseline"}
        ],
        "rationale": {"mechanism": "...", "expectation": "...", "falsifier": "..."},
        "statement": "The application serves HTTPS responses without Strict-Transport-Security ...",
        "subject_label": "APP2",
        "property_class": "transport.header_policy"
      }
      ```

      `rk2_promote_hypotheses` reads `payload -> 'evidence'` and nothing else,
      so pass 2 walked an empty list and pass 3 refused every survivor.

      The divergence against the run that worked is placement and nothing else:

      ```
      run          | claims | edges at the top | edges inside a claim | survived
      rk2hunt13    | 5      | 2, 4, 4, 3       | 0                    | 2
      rk2hunt14    | 3      | 0                | one per claim        | 0
      ```

      No code changed between the two runs. The failure is a coin flip that has
      been in this contract since it was written.

- [x] **An edge inside a claim counts as an edge naming that claim.** The
      element carries no `hypothesis_ref` because the claim it belongs to is
      the one it is written in. Lifting it is reading what the child meant.

- [x] **An explicit reference still wins.** An edge that names a
      `hypothesis_ref` or a `hypothesis_label` of its own is left alone, even
      nested: the child said which claim, and this must not overwrite it.

- [x] **A lifted edge is refused under its own name.** `element_path` is what a
      drop is reported and de-duplicated by, so a lifted edge reports as
      `hypotheses[i].evidence[j]` rather than borrowing a top-level ordinal
      that belongs to a different element.

- [x] **The contract says where the edge goes.** Both the mission text and the
      tool description say "give each one at least one evidence edge naming
      it", and neither says at which level. That sentence is why a model
      reasonably nests it.

**Why not the other fix.** Closing the hypothesis element so a stray `evidence`
key is refused at the schema would tell the child at once -- and would cost the
whole call, which is the failure `roster.py`'s contract comment is written to
avoid: a run that cannot get its result accepted files nothing at all. One
badly placed key would throw away every Observation of that run.

## How it was paid

`src/redkraken/migrations/20261017T000000Z__an_evidence_edge_is_read_where_the_child_wrote_it.sql`
rewrites `rk2_promote_hypotheses`. Pass 2 now walks the top-level `evidence`
array and the `evidence` array of every claim as one ordered stream. A nested
edge is given the `hypothesis_ref` of the claim it was written in, unless it
already carries a `hypothesis_ref` or a `hypothesis_label`, and it is reported
under `hypotheses[i].evidence[j]`.

The contract text said the opposite of what the schema does -- "a claim carrying
an evidence field of its own is refused as you send it", which nothing refuses,
because `roster._ELEMENTS["hypotheses"]` does not close the element. Both places
that said it now say both placements are read:
`src/redkraken/_launch.py` (the `submit_mission_result` description) and
`execution.Claimed.objective`.

Measured by `tests.test_database.HypothesisPromotionTest`, which promotes a
fifth result into a third Program: two claims whose only edges are nested, one
of them naming the other claim explicitly, and one nested edge citing an
Observation the result does not carry.

```
Ran 46 tests in 32.698s
OK
```
