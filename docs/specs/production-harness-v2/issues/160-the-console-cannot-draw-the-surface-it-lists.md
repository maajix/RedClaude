# 160 — The console cannot draw the surface it lists

**What to build:** The knowledge graph as a page of `rk ui serve`, live, so an
operator watches a campaign arrive instead of reading it back afterwards. The
shape is already proved: `~/engagements/*/graph.py` has run against fourteen
hunt databases and is what this ticket is asking to be made permanent.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] **One page, one script, one poll.** A `/graph` route beside the five in
      `ui.NAVIGATION`, a canvas, and a fetch every three seconds. No frontend
      build, no package, no CDN: the prototype draws twelve Lucide icons from
      path data copied into the file and highlights HTTP with about forty lines
      of regex, and both stay that way.
- [ ] **The strict policy survives, per route.** `ui.POLICY` is
      `default-src 'none'` and its comment says why: "A console that could fetch
      could exfiltrate what it is showing, and what it is showing is a campaign
      against somebody else's systems." A canvas needs `script-src 'self'`,
      `connect-src 'self'` and `img-src 'self' data:`. Those three go on the
      graph route and on nothing else, so every page that is script-free today
      is script-free after this. Relaxing `POLICY` itself is the wrong shape and
      is what this criterion exists to refuse.
- [ ] **The reads are `panels.Read`, on the runtime connection.** The prototype
      shells out to `docker exec psql` because it is engagement tooling with no
      driver. The console has one. Every query becomes a named read the same way
      `panels.SLATES` is, takes `program_id` as `$1`, and is bounded the same
      way — a hunt makes Observations faster than anyone reads them.
- [ ] **One Program, not one database.** The prototype draws whatever database
      it was pointed at. `rk ui serve` is opened with `--config` and is about
      exactly one Program, so the graph is that Program's and the database
      picker the prototype grew has no counterpart here.
- [ ] **Artifacts go through `artifact.get`, never through the directory.** The
      proof panel shows the request and the response as bytes. The prototype
      reads `artifacts/<ab>/<sha>` off disk, which walks past `visibility` and
      `encrypted` — `artifact.seal_wire` files two artifacts per exchange and
      the wire one is sealed under a Program key. The console serves the
      agent-visible view or it serves nothing, and asking for a sealed digest is
      a refusal rather than a decryption.
- [ ] **The proof panel is the point, and it is already specified.** For each
      Observation on a node: the tool run that fetched it (`tool_runs.tool`,
      `offline_tool`, `status`), the sentence the child wrote, the exchange with
      its pinned address, and both halves of the wire side by side. The sentence
      is not in `observations.summary` — that column is empty in every database
      this tree has produced — it is in the proposal the row was promoted from,
      reachable through `metadata ->> 'proposal'` and `metadata ->> 'element'`.
- [ ] **A label in a card is a way to the thing it names.** A card says
      `APP2`, `R3`, `AR6`, `PR2`, `TST1` and `H1`, and every one of those is a
      row this installation holds. Hovering a label shows a short tooltip of
      what it is — for an Entity its type and its address, for a Receipt the
      exchange, for a run its role — and clicking it opens that node's card.
      The labels are already unique inside a Program, so the link is a lookup
      and not a new query per word. Back to the card that was open before,
      because a graph is walked and a dead end is a reload.
- [ ] **Checked by something that would go red.** `tests/test_ui.py`: the graph
      route answers with the relaxed policy and every other route still answers
      with `POLICY`; the reads are Program-scoped; a request for a sealed
      artifact digest is refused; a label naming a row resolves to that row's id
      and a label naming nothing is inert rather than a broken link.

## Why

The console lists. `panels.SLATES` says what was offered, `panels.FINDINGS` says
how far each claim got, and an operator reading them holds the campaign in their
head as rows. The thing an operator actually wants during a live hunt is to see
a node appear and see what it joined to.

The prototype answers that and has earned the ticket rather than argued for it:

```
graph of rk2hunt17 on http://0.0.0.0:8788
entities 12  relationships 5  observations 10  hypotheses 2  receipts 5
```

It also answered a question the console cannot: **says who.** Opening a
`technology` node shows the sentence the child wrote, the tool that fetched the
bytes, and the response with `Server: Apache` lit because the sentence named
that header. That is one click from "we claim Apache runs here" to the line that
says so.

## Notes

Written from `~/engagements/yekta-first-hunt-2026-08-22/graph.py`, which is
engagement tooling and stays there: it is read-only, it is outside the harness,
and it is allowed to shell out to `psql` and read a directory because nothing
depends on it. This ticket is the harness answer to the same question and is
held to the harness's rules, which is most of the work.

The force layout, the icon set, the HTTP highlighter and the line-marking rule
(pull the quoted phrases and header names out of the child's own sentence, light
the lines that carry them) are settled by the prototype and should be carried
over rather than redesigned.

Not blocking ticket 65. Nothing about a Finding depends on it.
