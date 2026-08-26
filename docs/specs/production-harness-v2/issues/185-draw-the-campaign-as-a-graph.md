# 185 — Draw the campaign as a graph

**What to build:** `rk graph serve --config <program.toml>`, a second local
surface that draws one Program's Entities, Observations, Hypotheses and Findings
as a graph, and shows the bytes behind any of them. It comes out of the Yekta
test hunt, where an operator wrote it in the engagement directory and used it to
read a real campaign.

**Blocked by:** nothing.

**Status:** resolved

## Why it is not a panel

`rk ui` was the obvious home and cannot be it, for two reasons the suite already
holds:

- A panel is a table. `panels.Read` yields `columns` and `rows` and `ui` renders
  a `<table>` from them. A graph is not a table.
- The console runs no script. `ui.POLICY` names no `script-src` at all and
  `tests/test_ui.py` asserts both the absent directive and the absent `<script`.
  The reason is in `ui.py`'s own docstring: the console holds `rk2_human`, the
  one role that can lift a Halt and report a Finding.

The graph holds no such connection. It runs as `rk2_runtime`, answers GET only,
opens a read-only transaction for every statement, and has no verb, no form and
no token. It does not carry the risk the console is script-free because of, so
it is a separate command on a separate port with a policy of its own.

## What it does

- One Program per server. There is no Program argument on any route: the command
  is opened against one configuration, resolves that slug, and every statement
  carries `program_id = $1`. Cross-Program isolation here is not a filter that
  could be forgotten, it is that there is nothing to pass.
- `/data.json` is the whole graph, bounded at `OBSERVATIONS` and carrying the
  number it left out, the same honesty `panels.Panel.omitted` has.
- `/node?id=` is one node in full. A value that is not a UUID, and an `ip:`
  address that is not one, are refused before they reach a statement.
- `/artifact?sha=` is the bytes the door filed, capped, as `text/plain` with
  `nosniff` -- those bytes are a target's, and a browser allowed to sniff them
  would run somebody else's response as script in this surface's origin.
- The `Host` header must name the address that was bound, which is the console's
  own defence against a name in a browser resolving here.

## Its policy

    default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline';
    connect-src 'self'; base-uri 'none'; form-action 'none'

The page carries no inline script: the canvas is served from `/app.js` and takes
the Program name off a body attribute, so `script-src 'self'` is a statement
about origin rather than a permission for whatever ends up written into the
page. `style-src` keeps `'unsafe-inline'` because the legend and the feed write
their colours as `style` attributes, which no nonce or hash covers -- and with
every outbound direction closed there is nowhere for a stylesheet to send what
it could read.

## Deviations from the plan

- **The audit map is not extended.** The plan called for `tests.test_graph` in
  `AREAS["operator"]` in `tools/check_audit.py`. An anchor there is only
  satisfied by a requirement row in `baseline/spec-verification.tsv`, and those
  rows are digests of `spec.md` requirements for the ticket-63 audit. This
  command is not one of them. Adding the anchor would have meant adding a
  requirement to a frozen release audit, which would say that audit verified
  something it never saw.
- **`baseline/status.json` gains one adapter.** `graph.py` imports
  `http.server`, and `check_baseline` refuses any module that reaches a socket
  and is not named in `network_adapters`. It is registered with the same reason
  `ui.py` carries: it listens on loopback and dials nothing.

- [x] **It runs against the live schema.**
      `OperatorConsoleTest.test_every_read_the_graph_draws_from_runs_against_the_live_schema`
      and its two neighbours ask all three statements over the fixture's own
      campaign, which is the thing `tests/test_graph.py` cannot ask: twenty-one
      tables across a dozen migrations, and a canvas that would draw an empty
      graph for a statement that failed exactly as convincingly as for a Program
      with nothing in it.
- [x] **It reads one Program.** `test_the_graph_reads_nothing_of_the_program_it_was_not_opened_over`
      opens the same server over the neighbour slug and gets no nodes. The
      runtime RLS policy is `USING (true)`, so the `program_id = $1` on every
      subselect is load-bearing and not decoration.
- [x] **A node says how connected it is.** The size rule was `base + min(9,
      sqrt(degree) * 2)`, which added the same nine pixels to every kind and so
      made a busy Observation larger than a lone Finding, and capped an Entity
      at twice its base. It is now a multiple -- `base * min(MAX_GROWTH, 1 +
      sqrt(degree) / GROWTH_SPREAD)` with `MAX_GROWTH = 5` -- so the kinds keep
      their order however busy any of them gets, and a hub is visibly a hub.

      `GROWTH_SPREAD` is 2.2, set against what this engagement actually holds:
      a median Entity has 3 edges, the 95th percentile has 9 and the busiest has
      22, so the ceiling is reached at 77 -- a number a long campaign reaches
      and a short one does not. A ceiling nothing reaches is decoration, and no
      ceiling at all turns one apex into a disc with the graph behind it.
      `test_a_node_grows_with_its_edges_and_stops_at_five` reads both constants
      out of the shipped script rather than repeating them.
- [x] **Covered without a database.** `tests/test_graph.py`, 32 tests: the
      policy, every route, the refusals that never reach a statement, the digest
      that never reaches a path, the `Host` check, and that a POST is a method
      this surface does not have rather than a form it refuses.
- [x] **Proved against a real campaign.** Opened over the Yekta hunt's
      `rk2hunt21`: 35 nodes, 43 links, nothing omitted, and the Finding's proof
      pane showing the request and response digests the door filed.
