"""The live surface of one Program, as a canvas in a browser: `rk graph serve`.

A panel is a table, and what a campaign has learned is not a table. `rk ui`
answers "how far along is this Program" in twelve bounded reads; this answers
"what does it know, and how is any of it attached to the rest" in one picture
that redraws while the hunt runs.

Its own server rather than a page on the console, and that is the whole reason
this module sits beside `ui` instead of inside it. The console holds
`rk2_human`, the one role that may lift a Halt or file a Finding, and it is
reachable by any page the operator's browser happens to be on -- so it declares
a content policy that permits no script at all, and `tests/test_ui.py` holds it
to that. A graph is drawn by a script and cannot be drawn without one. It earns
the script by holding none of what the console holds: one connection, as the
runtime, in a transaction that cannot write, answering GET and nothing else.
No verb, no form, no token, and no second role to confuse with the first.

Scoped to one Program, like every other operator surface. The configuration
names it, the slug resolves once per request, and every statement below carries
the `program_id` that came back. That filter is not decoration: the runtime's
row-level policy is `true` -- it is the *agent* role that `rk2_program()`
fences -- so a subselect that forgot its `program_id` would quietly draw this
campaign's graph with another campaign's rows in it. Which is why it is on
every subselect and not on a view that something could join past.

This began as engagement tooling for the Yekta hunt, shelling out to `psql` in
a container as the superuser against whichever database that hunt had made. The
three things that made it tooling rather than a feature are the three things
that are gone: the subprocess, the superuser, and the assumption that a
database holds exactly one campaign.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import socketserver
import uuid
from dataclasses import dataclass
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from redkraken import config, migrate, pg, program, store, ui
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, report


COMMAND = "graph serve"

#: Loopback, and the port the tooling this grew out of already used. The
#: console's own default is one below it, so an operator can hold both open.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8788

#: How many of the newest Observations are drawn. A hunt records them faster
#: than anyone reads them, and a graph of every one is a grey disc. The number
#: the read did not draw comes back beside the ones it did, so a bounded
#: picture says it is bounded rather than implying the campaign is small.
OBSERVATIONS = 400

#: A response body can be a megabyte of minified JavaScript. Proof is the first
#: screenful of it, not all of it.
ARTIFACT_CAP = 96 * 1024

#: What the browser may do with a page from here: render it, run the one script
#: that draws the canvas, and ask this same origin for the JSON it draws from.
#: Nothing else -- no image, no font, no frame, and no connection anywhere but
#: back here. `script-src` is what the console refuses and this surface needs;
#: everything the console refuses *for a reason that also applies here* is
#: refused here too, which is every outbound direction. A graph that could
#: fetch could exfiltrate what it is showing, and what it is showing is a
#: campaign against somebody else's systems.
#:
#: `style-src` keeps `'unsafe-inline'` and `script-src` does not, which is the
#: asymmetry worth stating: the legend and the feed write their colours as
#: `style` attributes, and an attribute is not something a nonce or a hash can
#: cover. The rung below it is real -- with no outbound direction left open,
#: there is nowhere for a stylesheet to send what it could read.
#:
#: `img-src data:` is the node icons and only the node icons. They are Lucide
#: path data built into a data URL in the page itself, so this permits a shape
#: this file already contains and still permits no request: `data:` is not an
#: origin and cannot be fetched from. Without the directive `default-src 'none'`
#: applies and every icon is blocked, which is the state this surface shipped
#: in for exactly as long as it took somebody to look at it.
POLICY = (
    "default-src 'none'; script-src 'self'; img-src data:; "
    "style-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'"
)

#: `nosniff` is load-bearing on one route rather than tidy on all of them.
#: `/artifact` serves the bytes a target actually sent, and a captured HTML or
#: JavaScript response that a browser were allowed to sniff would run as script
#: in this surface's own origin -- which is the one origin allowed to ask this
#: surface for the rest of the campaign.
HEADERS = (
    ("Content-Security-Policy", POLICY),
    ("X-Frame-Options", "DENY"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cache-Control", "no-store"),
)

JSON = "application/json; charset=utf-8"
TEXT = "text/plain; charset=utf-8"
CODE = "text/javascript; charset=utf-8"


# ---------------------------------------------------------------------------
# The statements
# ---------------------------------------------------------------------------

#: One shot of the whole graph: the counts, the nodes and the edges between
#: them, composed in the database as one jsonb document because the page
#: redraws from one document. `$1` is the Program and `$2` is the Observation
#: bound above.
#:
#: Four of the edge kinds are not Relationships and are not mistakes. Recon
#: asserts what it learned; the detail tables already know structurally that an
#: Endpoint is under an Application, that a Parameter is under an Endpoint, and
#: that a subdomain sits under its apex. Without those the picture is a cloud of
#: correct rows with nothing holding them together.
SURFACE = """
SELECT jsonb_build_object(
  'stats', jsonb_build_object(
      'entities',     (SELECT count(*) FROM entities        WHERE program_id = $1),
      'relationships',(SELECT count(*) FROM relationships   WHERE program_id = $1),
      'observations', (SELECT count(*) FROM observations    WHERE program_id = $1),
      'hypotheses',   (SELECT count(*) FROM hypotheses      WHERE program_id = $1),
      'evidence',     (SELECT count(*) FROM hypothesis_evidence WHERE program_id = $1),
      'tests',        (SELECT count(*) FROM test_runs       WHERE program_id = $1),
      'findings',     (SELECT count(*) FROM findings        WHERE program_id = $1),
      'receipts',     (SELECT count(*) FROM receipts        WHERE program_id = $1),
      'tool_runs',    (SELECT count(*) FROM tool_runs       WHERE program_id = $1),
      'agent_runs',   (SELECT count(*) FROM agent_runs      WHERE program_id = $1),
      'tasks',        (SELECT count(*) FROM tasks           WHERE program_id = $1)),
  -- What the picture left out, so a bounded graph says so. The other kinds are
  -- drawn whole; Observations are the one unbounded stream, so it is the one
  -- number that can be greater than zero.
  'omitted', greatest(
      (SELECT count(*) FROM observations WHERE program_id = $1) - $2, 0),
  'nodes',
      (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'id', e.id::text, 'kind', 'entity', 'sub', e.type,
          'label', coalesce(
              d.fqdn,
              a.base_url,
              ep.method || ' ' || ep.path_template,
              nullif(h.hostname, ''), host(h.address),
              p.name || ' (' || p.location || ')',
              t.name || coalesce(' ' || t.version, ''),
              s.protocol || '/' || s.port::text,
              i.slot_name,
              e.label),
          'ref', e.label, 'ok', e.scope_class <> 'denied',
          'at', e.first_seen_at,
          'scope', CASE e.scope_class
              WHEN 'target'         THEN 'in scope'
              WHEN 'egress_support' THEN 'in scope, support'
              WHEN 'not_addressable' THEN 'no address of its own'
              ELSE 'out of scope' END,
          'note', e.type || ' · ' || CASE e.scope_class
              WHEN 'target'         THEN 'in scope'
              WHEN 'egress_support' THEN 'in scope, reached on the way'
              WHEN 'not_addressable'
                THEN 'a fact about a target, not a place to send a request'
              ELSE 'out of scope' END)), '[]'::jsonb)
        FROM entities e
        LEFT JOIN domains d      ON d.entity_id = e.id
        LEFT JOIN applications a ON a.entity_id = e.id
        LEFT JOIN endpoints ep   ON ep.entity_id = e.id
        LEFT JOIN hosts h        ON h.entity_id = e.id
        LEFT JOIN parameters p   ON p.entity_id = e.id
        LEFT JOIN technologies t ON t.entity_id = e.id
        LEFT JOIN services s     ON s.entity_id = e.id
        LEFT JOIN identities i   ON i.entity_id = e.id
       WHERE e.program_id = $1)
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'id', o.id::text, 'kind', 'observation', 'sub', o.kind,
          'label', left(coalesce(nullif(o.summary, ''), o.kind), 60),
          'ref', o.label, 'ok', true,
          'at', o.observed_at,
          'note', o.kind || ' — '
                || left(coalesce(nullif(o.summary, ''), o.kind), 200))), '[]'::jsonb)
        FROM (SELECT * FROM observations WHERE program_id = $1
               ORDER BY observed_at DESC LIMIT $2) o)
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'id', h.id::text, 'kind', 'hypothesis', 'sub', h.status,
          'label', h.property_class,
          'ref', h.label, 'ok', h.status IN ('supported','testable','testing'),
          'at', h.created_at,
          'note', h.status || ' — ' || left(h.statement, 220))), '[]'::jsonb)
        FROM hypotheses h WHERE h.program_id = $1)
   -- Not an Entity. `hosts` is empty when recon proposed no host, and this
   -- surface does not write Surface. What it does have is the address the door
   -- pinned before it connected, which is a measurement on every Receipt.
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'id', 'ip:' || x.ip, 'kind', 'address', 'sub', 'pinned',
          'label', x.ip, 'ok', true, 'at', x.first_at,
          'note', 'the door connected here on ' || x.n || ' exchange(s) for '
               || x.hosts)), '[]'::jsonb)
        FROM (SELECT r.pinned_ips AS ip, count(*) AS n,
                     min(r.ts_arrival) AS first_at,
                     string_agg(DISTINCT r.host, ', ') AS hosts
                FROM receipts r
               WHERE r.program_id = $1 AND nullif(r.pinned_ips, '') IS NOT NULL
               GROUP BY 1) x)
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'id', f.id::text, 'kind', 'finding', 'sub', f.severity,
          'label', left(coalesce(f.title, f.label), 70),
          'ref', f.label, 'ok', true,
          'at', f.created_at,
          'note', coalesce(f.severity, 'finding') || ' — '
                || coalesce(f.property_class, '') || ' — ' || f.status)), '[]'::jsonb)
        FROM findings f WHERE f.program_id = $1),
  'links',
      (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'a', r.src_entity_id::text, 'b', r.dst_entity_id::text,
          'kind', 'relationship', 'label', r.type)), '[]'::jsonb)
        FROM relationships r WHERE r.program_id = $1)
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'a', o.id::text, 'b', o.subject_entity_id::text,
          'kind', 'observed', 'label', 'observed on')), '[]'::jsonb)
        FROM (SELECT * FROM observations WHERE program_id = $1
               ORDER BY observed_at DESC LIMIT $2) o
       WHERE o.subject_entity_id IS NOT NULL)
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'a', h.id::text, 'b', h.subject_entity_id::text,
          'kind', 'about', 'label', 'claim about')), '[]'::jsonb)
        FROM hypotheses h
       WHERE h.program_id = $1 AND h.subject_entity_id IS NOT NULL)
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'a', v.hypothesis_id::text, 'b', v.observation_id::text,
          'kind', v.polarity,
          'label', v.polarity || ' as ' || v.role)), '[]'::jsonb)
        FROM hypothesis_evidence v WHERE v.program_id = $1)
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'a', f.id::text, 'b', f.subject_entity_id::text,
          'kind', 'finding_on', 'label', 'finding on')), '[]'::jsonb)
        FROM findings f
       WHERE f.program_id = $1 AND f.subject_entity_id IS NOT NULL)
   -- The address hangs off the name that resolved to it, which is what makes
   -- two Programs sharing one machine visible at a glance.
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'a', d.entity_id::text, 'b', 'ip:' || rr.ip,
          'kind', 'resolves', 'label', 'resolves to')), '[]'::jsonb)
        FROM (SELECT DISTINCT r.host, r.pinned_ips AS ip
                FROM receipts r
               WHERE r.program_id = $1 AND nullif(r.pinned_ips, '') IS NOT NULL) rr
        JOIN domains d ON d.program_id = $1 AND d.fqdn = rr.host)
   -- The typed parentage. `relationships` carries what recon asserted about two
   -- Entities; this is what the detail tables already know structurally, and
   -- without it an Endpoint floats beside the Application it was found on.
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'a', ep.entity_id::text, 'b', ep.application_id::text,
          'kind', 'under', 'label', 'endpoint of')), '[]'::jsonb)
        FROM endpoints ep
       WHERE ep.program_id = $1 AND ep.application_id IS NOT NULL)
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'a', p.entity_id::text, 'b', p.endpoint_id::text,
          'kind', 'under', 'label', 'parameter of')), '[]'::jsonb)
        FROM parameters p
       WHERE p.program_id = $1 AND p.endpoint_id IS NOT NULL)
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'a', sv.entity_id::text, 'b', sv.host_id::text,
          'kind', 'under', 'label', 'service on')), '[]'::jsonb)
        FROM services sv
       WHERE sv.program_id = $1 AND sv.host_id IS NOT NULL)
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'a', i.entity_id::text, 'b', i.tenant_entity_id::text,
          'kind', 'under', 'label', 'identity of')), '[]'::jsonb)
        FROM identities i
       WHERE i.program_id = $1 AND i.tenant_entity_id IS NOT NULL)
   -- Where an Application is served. Nobody asserts it, because neither row
   -- points at the other: the Application carries a base URL and the Domain
   -- carries a name, and the edge is the host inside the one being the other.
   -- Without it every Application floats away from the name it answers on.
   -- The parse is LATERAL because it returns a row, and a function that
   -- returns rows may not stand in a join condition.
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'a', a.entity_id::text, 'b', d.entity_id::text,
          'kind', 'served_at', 'label', 'served at')), '[]'::jsonb)
        FROM applications a
        CROSS JOIN LATERAL rk2_parse_base_url(a.base_url) u
        JOIN domains d ON d.program_id = a.program_id AND d.fqdn = u.host
       WHERE a.program_id = $1)
   -- The name under the name. `domains.apex` already holds the apex of every
   -- subdomain, so the tree is sitting in the column and only wants joining
   -- back to the row that carries that apex as its own fqdn -- which is a
   -- shape recon never states as a Relationship because it never has to.
   || (SELECT coalesce(jsonb_agg(jsonb_build_object(
          'a', d.entity_id::text, 'b', d2.entity_id::text,
          'kind', 'subdomain_of', 'label', 'subdomain of')), '[]'::jsonb)
        FROM domains d
        JOIN domains d2 ON d2.program_id = d.program_id
                       AND d2.fqdn = d.apex AND d2.fqdn <> d.fqdn
       WHERE d.program_id = $1)
)
"""

#: Everything this Program holds about one node, by its id. `$1` is the Program
#: and `$2` is the node. Both are parameters and neither is formatted in: the
#: id arrives on a query string, and a query string is not a place to take a
#: fragment of a statement from however local the listener is.
NODE = """
SELECT jsonb_strip_nulls(jsonb_build_object(
  'entity',      (SELECT to_jsonb(e) FROM entities e
                   WHERE e.program_id = $1 AND e.id = $2),
  'application', (SELECT to_jsonb(a) FROM applications a
                   WHERE a.program_id = $1 AND a.entity_id = $2),
  'domain',      (SELECT to_jsonb(d) FROM domains d
                   WHERE d.program_id = $1 AND d.entity_id = $2),
  'endpoint',    (SELECT to_jsonb(p) FROM endpoints p
                   WHERE p.program_id = $1 AND p.entity_id = $2),
  'host',        (SELECT to_jsonb(h) FROM hosts h
                   WHERE h.program_id = $1 AND h.entity_id = $2),
  'parameter',   (SELECT to_jsonb(p) FROM parameters p
                   WHERE p.program_id = $1 AND p.entity_id = $2),
  'technology',  (SELECT to_jsonb(t) FROM technologies t
                   WHERE t.program_id = $1 AND t.entity_id = $2),
  'service',     (SELECT to_jsonb(s) FROM services s
                   WHERE s.program_id = $1 AND s.entity_id = $2),
  'identity',    (SELECT to_jsonb(i) FROM identities i
                   WHERE i.program_id = $1 AND i.entity_id = $2),
  'observation', (SELECT to_jsonb(o) FROM observations o
                   WHERE o.program_id = $1 AND o.id = $2),
  'hypothesis',  (SELECT to_jsonb(h) FROM hypotheses h
                   WHERE h.program_id = $1 AND h.id = $2),
  'finding',     (SELECT to_jsonb(f) FROM findings f
                   WHERE f.program_id = $1 AND f.id = $2),
  'seen_by',     (SELECT jsonb_agg(jsonb_build_object(
                     'label', o.label, 'kind', o.kind,
                     'summary', left(coalesce(o.summary, ''), 180),
                     'at', o.observed_at) ORDER BY o.observed_at DESC)
                    FROM observations o
                   WHERE o.program_id = $1 AND o.subject_entity_id = $2),
  'claims',      (SELECT jsonb_agg(jsonb_build_object(
                     'label', h.label, 'status', h.status,
                     'property_class', h.property_class,
                     'statement', left(h.statement, 200)) ORDER BY h.created_at)
                    FROM hypotheses h
                   WHERE h.program_id = $1 AND h.subject_entity_id = $2),
  'evidence',    (SELECT jsonb_agg(jsonb_build_object(
                     'polarity', v.polarity, 'role', v.role,
                     'observation', o.label, 'kind', o.kind,
                     'summary', left(coalesce(o.summary, ''), 180)) ORDER BY v.added_at)
                    FROM hypothesis_evidence v
                    JOIN observations o ON o.id = v.observation_id
                   WHERE v.program_id = $1 AND v.hypothesis_id = $2),
  'receipt',     (SELECT jsonb_build_object(
                     'label', r.label, 'method', r.method,
                     'url', r.scheme || '://' || r.host || r.path,
                     'status', r.status_code, 'lane', r.lane,
                     'pinned_ip', r.pinned_ips,
                     'decision', r.decision, 'waited_ms', r.waited_ms)
                    FROM observations o JOIN receipts r ON r.id = o.receipt_id
                   WHERE o.program_id = $1 AND o.id = $2),
  'run',         (SELECT jsonb_build_object(
                     'label', ar.label, 'role', ar.role, 'model', ar.model)
                    FROM observations o JOIN agent_runs ar ON ar.id = o.agent_run_id
                   WHERE o.program_id = $1 AND o.id = $2),
  'proof',       (SELECT jsonb_agg(p.entry ORDER BY p.at) FROM (
                    SELECT o.observed_at AS at, jsonb_build_object(
                        'observation',  o.label,
                        'kind',         o.kind,
                        'at',           o.observed_at,
                        'provenance',   o.provenance_kind,
                        'statement',    coalesce(nullif(o.summary, ''), words.statement),
                        'proposal',     o.metadata ->> 'proposal',
                        'tool',         coalesce(nullif(tr.offline_tool, ''), tr.tool),
                        'tool_version', tr.tool_version,
                        'tool_status',  tr.status,
                        'tool_args',    tr.args,
                        'run',          ar.label,
                        'model',        ar.model,
                        'exchange',     r.method || ' ' || r.scheme || '://'
                                        || r.host || r.path,
                        'status',       coalesce(r.status_code::text, r.decision),
                        'pinned_ip',    r.pinned_ips,
                        'lane',         r.lane,
                        -- The wire pair is what the door sent and got; the
                        -- agent pair is what the child was shown. They differ
                        -- only where the door rewrote something.
                        --
                        -- The agent digest first, and not the wire one. A wire
                        -- artifact is sealed -- `artifact_seal` files it under
                        -- its `ciphertext_sha256` -- so the plaintext digest a
                        -- Receipt names is not a path in the store, and this
                        -- pane answered `this installation does not hold that
                        -- artifact` for every sealed exchange it had. Measured
                        -- on `rk2here`: all 1369 request and 133 response wire
                        -- digests absent from disk, all 1502 present in
                        -- `artifact_seal`, and every agent digest present.
                        --
                        -- Serving the redaction is also the only thing this
                        -- surface may serve. A sealed wire body is
                        -- `credential_bearing` and this listener has no
                        -- authentication, so unsealing it here would put the
                        -- operator's own bearer tokens on the LAN. The agent
                        -- digest is the same exchange with the secrets already
                        -- taken out -- what the child was shown, which is what
                        -- a proof pane is for.
                        --
                        -- No Receipt on `rk2here` carries a wire digest and no
                        -- agent one (0 of 1727), so the fallback is for an
                        -- installation that seals nothing rather than for a
                        -- gap in this one.
                        'request_sha',  coalesce(r.request_agent_sha, r.request_wire_sha),
                        'response_sha', coalesce(r.response_agent_sha, r.response_wire_sha))
                        AS entry
                      FROM observations o
                      LEFT JOIN agent_runs ar ON ar.id = o.agent_run_id
                      LEFT JOIN receipts   r  ON r.id  = o.receipt_id
                      -- An Observation names the run that read it, and the
                      -- Receipt names the tool run that fetched it. Which tool
                      -- went and looked is the Receipt's answer for anything
                      -- the door carried, and the Observation's for a tool that
                      -- never left the machine.
                      LEFT JOIN tool_runs  tr ON tr.id = coalesce(o.tool_run_id,
                                                                  r.tool_run_id)
                      -- What the child actually wrote. `observations.summary` is
                      -- empty on every row this tree has produced; the sentence
                      -- lives in the proposal it was promoted from, and the
                      -- observation's own metadata says which element of it.
                      LEFT JOIN LATERAL (
                        SELECT said.value ->> 'statement' AS statement
                          FROM proposals pr,
                               LATERAL jsonb_array_elements(pr.payload -> 'observations')
                                   WITH ORDINALITY AS said(value, n)
                         WHERE pr.program_id = o.program_id
                           AND pr.label = o.metadata ->> 'proposal'
                           AND said.n = 1 + coalesce(nullif(split_part(replace(
                                 o.metadata ->> 'element', 'observations[', ''),
                                 ']', 1), '')::int, -1)
                      ) words ON true
                     WHERE o.program_id = $1
                       AND (o.subject_entity_id = $2
                        OR o.id = $2
                        OR o.id IN (SELECT v.observation_id FROM hypothesis_evidence v
                                     WHERE v.program_id = $1 AND v.hypothesis_id = $2)
                        OR o.id IN (SELECT v.observation_id
                                      FROM finding_hypotheses fh
                                      JOIN hypothesis_evidence v
                                        ON v.hypothesis_id = fh.hypothesis_id
                                     WHERE fh.program_id = $1 AND fh.finding_id = $2))
                     ORDER BY o.observed_at DESC
                     LIMIT 40) p)
))
"""

#: One address the door pinned, which is not an Entity and so has no id. `$2`
#: is the address as text, checked before it gets here and parameterised anyway.
ADDRESS = """
SELECT jsonb_build_object(
  'address', jsonb_build_object(
      -- Cast at every use, not just the first. `jsonb_build_object` takes
      -- anything, so a bare parameter there is a parameter Postgres has no
      -- column to infer a type from -- and it refuses the whole statement with
      -- `could not determine data type of parameter $2` rather than guessing.
      'address', $2::text,
      'exchanges', (SELECT count(*) FROM receipts r
                     WHERE r.program_id = $1 AND r.pinned_ips = $2::text),
      'names', (SELECT string_agg(DISTINCT r.host, ', ') FROM receipts r
                 WHERE r.program_id = $1 AND r.pinned_ips = $2::text),
      'source', 'pinned by the door before it connected; no host Entity exists'),
  'exchanges', (SELECT jsonb_agg(jsonb_build_object(
      'label', r.label, 'kind', r.method || ' ' || r.host || r.path,
      'status', coalesce(r.status_code::text, r.decision),
      'summary', r.scheme || '://' || r.host || r.path) ORDER BY r.ts_arrival DESC)
    FROM (SELECT * FROM receipts
           WHERE program_id = $1 AND pinned_ips = $2::text
           ORDER BY ts_arrival DESC LIMIT 60) r)
)
"""

#: What may stand in an address and nothing else. It arrives on a query string
#: and is a parameter by the time it reaches a statement, so this is not what
#: makes it safe -- it is what makes a typo an answer rather than an empty one.
ADDRESS_CHARACTERS = frozenset("0123456789abcdefABCDEF.:")

#: What a digest is made of. Lowercase only, because that is what the store
#: writes: a mixed-case spelling of the same digest is a path that is not there,
#: and answering "not held" is a truer answer than normalising it into one.
HEX = frozenset("0123456789abcdef")

#: The prefix the page gives an address, because an address has no id to send.
PINNED = "ip:"


# ---------------------------------------------------------------------------
# The reads
# ---------------------------------------------------------------------------


def ask(
    runtime: pg.Settings, slug: str, statement: str, parameters: tuple[object, ...]
) -> tuple[bytes, str]:
    """One statement about one Program, and what it answered.

    Every read opens its own connection and resolves the slug again, which is
    what `panels.read` does and for the same reason: a database that goes away
    is then one request that says so rather than a server that has to be
    restarted. The transaction cannot write. That is the whole of this
    surface's authority -- it is asserted here, once, rather than trusted to
    every statement above being a SELECT.
    """
    ledger = Ledger()
    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return _refusal(ledger), JSON
    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return _refusal(ledger), JSON
        program_id = program.resolve(ledger, connection, slug)
        if program_id is None:
            return _refusal(ledger), JSON
        try:
            with connection.transaction():
                connection.execute("SET TRANSACTION READ ONLY")
                answered = connection.execute(
                    statement, (program_id, *parameters)
                ).scalar()
        except (pg.DatabaseError, pg.ConnectionError_) as error:
            return json.dumps({"error": str(error)[:400]}).encode(), JSON
    if isinstance(answered, str):
        return answered.encode(), JSON
    return json.dumps(answered, default=str).encode(), JSON


def _refusal(ledger: Ledger) -> bytes:
    """A Ledger's violations as the page's own error shape.

    The page has one way of showing that a read did not happen, and it is the
    `error` key. A refusal rendered as anything else would be a second shape
    for the same thing, which the page would draw as an empty campaign.
    """
    detail = "; ".join(
        violation.detail or violation.code for violation in ledger.violations
    )
    return json.dumps({"error": detail or "this read was refused"}).encode()


def surface(runtime: pg.Settings, slug: str) -> tuple[bytes, str]:
    """The whole graph, once, as the document the page redraws from."""
    return ask(runtime, slug, SURFACE, (OBSERVATIONS,))


def node(runtime: pg.Settings, slug: str, identifier: str) -> tuple[bytes, str]:
    """One node in full, or a refusal that never reached a statement."""
    if identifier.startswith(PINNED):
        address = identifier[len(PINNED):]
        if not address or len(address) > 45 or set(address) - ADDRESS_CHARACTERS:
            return json.dumps({"error": "not an address"}).encode(), JSON
        return ask(runtime, slug, ADDRESS, (address,))
    if not _is_uuid(identifier):
        return json.dumps({"error": "not an id"}).encode(), JSON
    return ask(runtime, slug, NODE, (identifier,))


def _is_uuid(value: str) -> bool:
    """Whether this is a node id, decided before anything is asked with it."""
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def artifact(root: Path | None, sha256: str) -> tuple[bytes, str]:
    """The bytes the door filed under one digest, capped and made printable.

    `message/http` is what the door stores: the wire, headers and body, exactly
    as it went past. That is the proof behind a claim, so it is served as text
    rather than summarised -- and as `text/plain` with `nosniff`, because those
    bytes are a target's and a browser allowed to sniff them would run somebody
    else's response as script in this surface's origin.

    The digest is checked before it is joined to a path. `store.path_for` takes
    the first two characters as a directory, so a value with a separator in it
    would be a path this surface was never given.
    """
    if len(sha256) != 64 or set(sha256) - HEX:
        return b"not a digest", TEXT
    if root is None:
        return b"this installation was not told where the artifacts are", TEXT
    path = store.path_for(root, sha256)
    if not path.is_file():
        return b"this installation does not hold that artifact", TEXT
    raw = path.read_bytes()
    body = raw[:ARTIFACT_CAP].decode("utf-8", "replace")
    if len(raw) > ARTIFACT_CAP:
        body += f"\n\n... {len(raw) - ARTIFACT_CAP} more byte(s) not shown"
    return body.encode(), TEXT


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<!-- Without this a phone lays the page out at 980px and scales the result
     down, which is why the type came out unreadable and the rails came out
     overlapping. `viewport-fit=cover` is what makes the safe-area insets the
     rails already ask for resolve to anything. Scaling is left enabled: the
     canvas refuses the browser's gesture through `touch-action`, so nothing is
     taken away from the chrome around it. -->
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>redKraken — live surface</title>
<style>
  /* Severity is the only saturated thing on this page. Every other colour is
     pulled back towards the background on purpose: a graph where the terrain
     shouts as loudly as the Finding is a graph an operator has to search. */
  :root{--bg:#0b0f14;--fg:#e6edf3;--dim:#7d8590;--line:#1c2430;--dot:#1b2531;
    --warn:#f0b429;
    --critical:#ff2d55;--high:#ff5a5f;--medium:#ff9f1c;--low:#3fb950;--info:#4cc9f0}
  *{box-sizing:border-box}
  /* The same dot field the canvas draws, standing still behind it. The canvas
     one moves with the view and is the one anybody looks at; this is what is
     under it before the first frame and wherever the canvas is not, so the
     page never flashes as a flat rectangle on the way in. */
  html,body{margin:0;height:100%;color:var(--fg);
    background:radial-gradient(var(--dot) 1.1px, transparent 1.1px) 0 0/30px 30px,
               var(--bg);
    font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;overflow:hidden}
  /* `touch-action:none` is what lets a finger pan and pinch the graph at all:
     without it the browser claims the gesture as a page scroll and the first
     `pointermove` never arrives. */
  canvas{display:block;cursor:grab;touch-action:none}
  canvas.drag{cursor:grabbing}
  /* Two rails and a drawer. Every piece of chrome on this page is one line
     tall and scrolls sideways rather than wrapping, because a legend that
     wraps grows upward into the graph and the operator loses the thing they
     came to look at. Below 900px the drawer leaves the canvas entirely. */
  .rail{position:fixed;left:0;right:0;z-index:4;display:flex;align-items:center;
    gap:14px;padding:9px calc(14px + env(safe-area-inset-right)) 9px
    calc(14px + env(safe-area-inset-left));overflow-x:auto;overflow-y:hidden;
    scrollbar-width:none;-webkit-overflow-scrolling:touch}
  .rail::-webkit-scrollbar{display:none}
  #hud{top:0;background:linear-gradient(#0b0f14f2,#0b0f14cc 60%,#0b0f1400)}
  #legend{bottom:0;padding-bottom:calc(9px + env(safe-area-inset-bottom));
    background:linear-gradient(#0b0f1400,#0b0f14cc 40%,#0b0f14f2)}

  /* The Program name, set at the top of the type scale. It is the one thing on
     the page that is not a measurement, so it is the one thing with room. */
  #program{font-size:15px;letter-spacing:.06em;color:#fff;white-space:nowrap;flex:none}
  #counts{display:flex;gap:14px;align-items:baseline;white-space:nowrap}
  #counts span{color:var(--dim);font-size:11px;letter-spacing:.04em}
  #counts b{font-weight:600;color:var(--fg);font-variant-numeric:tabular-nums}
  #counts .omitted b{color:var(--warn)}
  #drawer{margin-left:auto;flex:none;position:sticky;right:0;
    background:linear-gradient(90deg,#0b0f1400,#0b0f14 22%)}

  .chip{flex:none;color:var(--dim);cursor:pointer;user-select:none;
    padding:4px 10px;border:1px solid var(--line);border-radius:999px;
    background:#0f151ce6;white-space:nowrap;font-size:11px;letter-spacing:.04em}
  .chip:hover{color:var(--fg);border-color:#33404f}
  .chip:focus-visible{outline:2px solid #4aa3ff;outline-offset:2px}
  .chip.off{opacity:.42;border-style:dashed}
  .chip.off i{opacity:.35}
  .chip i{display:inline-block;width:8px;height:8px;border-radius:50%;
    margin-right:7px;vertical-align:middle}

  /* The severity gauge: the five levels a Finding can carry, in order, each lit
     only where this campaign actually holds one. It is the legend for the
     Finding colour and the readout of the hunt at the same time, which is why
     it is the one saturated thing on the page. */
  #gauge{flex:none;display:flex;align-items:stretch;border:1px solid var(--line);
    border-radius:8px;overflow:hidden;background:#0f151ce6}
  #gauge .lvl{display:flex;flex-direction:column;gap:1px;padding:3px 10px 4px;
    border-right:1px solid var(--line);min-width:58px}
  #gauge .lvl:last-child{border-right:0}
  #gauge .lvl .n{font-size:14px;font-weight:600;font-variant-numeric:tabular-nums;
    color:#2b3440;line-height:1.1}
  #gauge .lvl .w{font-size:9px;letter-spacing:.16em;text-transform:uppercase;
    color:#3d4855}
  #gauge .lvl.lit .n{color:var(--tone)}
  #gauge .lvl.lit .w{color:var(--tone);opacity:.85}
  #gauge .lvl.lit{background:linear-gradient(#0000,color-mix(in srgb,var(--tone) 14%,#0000))}
  .rail .sep{flex:none;width:1px;align-self:stretch;background:var(--line);margin:2px 0}

  /* The drawer. Off-canvas on every width, so "closed" means the same thing on
     a phone and on a desk, and nothing on this page ever half-covers the graph. */
  #side{position:fixed;top:52px;right:14px;width:300px;z-index:6;
    display:flex;flex-direction:column;max-height:calc(100vh - 120px);
    background:#0f151cf2;border:1px solid var(--line);border-radius:12px;
    padding:10px 12px;backdrop-filter:blur(10px);box-shadow:0 18px 48px #0009;
    transform:translateX(calc(100% + 20px));opacity:0;pointer-events:none;
    transition:transform .22s cubic-bezier(.2,.8,.2,1),opacity .18s}
  #side.on{transform:none;opacity:1;pointer-events:auto}
  #side header{display:flex;align-items:baseline;gap:10px;flex:none}
  #side h2{margin:0;font-size:10px;letter-spacing:.18em;color:var(--dim);
    text-transform:uppercase;font-weight:600;white-space:nowrap}
  #side h2 span{color:var(--fg);font-variant-numeric:tabular-nums}
  #side button{margin-left:auto;background:transparent;border:0;color:var(--dim);
    cursor:pointer;font:inherit;font-size:16px;line-height:1;padding:2px 4px}
  #side button:hover{color:var(--fg)}
  #side button:focus-visible{outline:2px solid #4aa3ff;outline-offset:2px}
  .feed{margin:8px 0 0;padding:0 6px 0 0;list-style:none;
    overflow-y:auto;overscroll-behavior:contain;flex:1 1 auto;min-height:0}
  .feed::-webkit-scrollbar{width:8px}
  .feed::-webkit-scrollbar-thumb{background:#24303d;border-radius:4px}
  .feed li{padding:6px 0;border-bottom:1px solid var(--line);color:var(--dim);
    font-size:11px;display:flex;gap:8px;align-items:baseline}
  .feed li:last-child{border:0}
  .feed li i{flex:none;width:7px;height:7px;border-radius:50%;margin-top:1px}
  .feed .t{color:var(--fg);font-size:12px;word-break:break-all}
  .feed .s{color:var(--dim);white-space:nowrap}
  .feed .empty{color:#4b5563;padding:14px 0;display:block;border:0}

  @media (max-width:900px){
    /* The drawer stops floating and becomes the bottom half of the screen: at
       this width a 300px panel beside the graph leaves neither of them usable. */
    #side{top:auto;left:8px;right:8px;bottom:0;width:auto;max-height:52vh;
      border-radius:14px 14px 0 0;border-bottom:0;
      padding-bottom:calc(10px + env(safe-area-inset-bottom));
      transform:translateY(calc(100% + 20px))}
    #counts span:nth-child(n+5){display:none}
    #gauge .lvl{min-width:0;padding:3px 8px 4px}
    #gauge .lvl .w{font-size:8px;letter-spacing:.1em}
  }
  @media (max-width:560px){
    #program{font-size:13px}
    #counts span:nth-child(n+3){display:none}
    .chip{padding:4px 9px}
  }
  @media (prefers-reduced-motion:reduce){
    #side{transition:none}
  }
  #tip{position:fixed;padding:7px 10px;background:#111a24f2;border:1px solid #26313f;
    border-radius:8px;max-width:360px;pointer-events:none;opacity:0;transition:opacity .1s;
    box-shadow:0 8px 24px #0008;z-index:5}
  #tip b{display:block;color:#fff;margin-bottom:2px}
  #tip u{color:#8b98a5}
  #tip .hint{display:block;margin-top:4px;color:#5f6b7a}
  #sheet{position:fixed;inset:0;background:#04070aa8;backdrop-filter:blur(3px);
    display:none;z-index:10;align-items:center;justify-content:center;padding:40px}
  #sheet.on{display:flex}
  #card{width:min(1240px,100%);max-height:100%;overflow:auto;background:#0d131a;
    border:1px solid #24303d;border-radius:14px;box-shadow:0 24px 60px #000a}
  #card header{position:sticky;top:0;background:#0d131aee;padding:16px 20px 12px;
    border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:flex-start}
  #card h1{margin:0;font-size:16px;font-weight:600;color:#fff;word-break:break-all}
  #card .meta{color:var(--dim);font-size:12px;margin-top:3px}
  #card .x{margin-left:auto;background:transparent;border:1px solid var(--line);
    color:var(--dim);border-radius:8px;padding:3px 10px;cursor:pointer;font:inherit}
  #card .x:hover{color:#fff;border-color:#33404f}
  #card section{padding:12px 20px}
  #card h3{margin:0 0 8px;font-size:10px;letter-spacing:.14em;text-transform:uppercase;
    color:var(--dim);font-weight:600}
  #card table{width:100%;border-collapse:collapse}
  #card td{padding:3px 0;vertical-align:top;border-bottom:1px solid #141c25}
  #card td.k{color:var(--dim);width:180px;padding-right:14px;white-space:nowrap}
  #card td.v{color:var(--fg);word-break:break-word}
  #card ul{margin:0;padding:0;list-style:none}
  #card li{padding:7px 0;border-bottom:1px solid #141c25;color:var(--fg)}
  #card li:last-child{border:0}
  #card li .tag{display:inline-block;padding:0 7px;border-radius:999px;font-size:11px;
    margin-right:7px;border:1px solid #24303d;color:var(--dim)}
  #card li .sup{color:#3fb950;border-color:#1e4a2b}
  #card li .ref{color:#3fb950;border-color:#1e4a2b}
  #card li .refute{color:#ff4d6d;border-color:#5a2130}
  #card li small{display:block;color:var(--dim);margin-top:2px}
  #hud #program{background:#0f151c;color:#fff;border:1px solid var(--line);
    border-radius:6px;padding:2px 8px;letter-spacing:.04em}
  #hud #counts{display:contents}
  #hud .omitted b{color:var(--warn,#f0b429)}
  #card .poc{border:1px solid #1c2430;border-radius:10px;padding:10px 12px;
    margin-bottom:10px;background:#0a1017}
  #card .poc-h{color:#fff;overflow:hidden}
  #card .poc-at{float:right;color:var(--dim);font-size:11px;margin-left:10px}
  #card .poc-s{margin:6px 0;color:var(--fg)}
  #card .poc-m{color:var(--dim);margin:4px 0 2px;word-break:break-all}
  #card .poc-m em{font-style:normal;color:#7cc7ff}
  #card pre.code{margin:6px 0 0;padding:10px;background:#070b10;border:1px solid #16202b;
    border-radius:8px;overflow:auto;max-height:340px;white-space:pre-wrap;
    word-break:break-word;font:12px/1.5 ui-monospace,Menlo,monospace;color:#c9d5e1}
  #card pre.code .st{color:#f0b429;font-weight:600}
  #card pre.code .k{color:#7cc7ff}
  #card pre.code .s{color:#a5d6a7}
  #card pre.code .n{color:#f0b429}
  #card pre.code .b{color:#c792ea}
  #card pre.code .t{color:#ff8fa3}
  #card pre.code mark{background:#4a3400;color:#ffd479;padding:0 2px;border-radius:3px}
  #card pre.code .hit{background:#3b3006;border-radius:2px;
    box-shadow:-3px 0 0 #f0b429,3px 0 0 #3b3006}
  #card .wires{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:8px}
  /* Both panes the height of the taller one. A request is four lines and a
     response is a page, and two boxes of different heights read as one box
     with something missing beside it. */
  #card .wires .pane{min-width:0;display:flex;flex-direction:column}
  #card .wires .pane pre.code{flex:1 1 auto;min-height:0}
  #card .wires h4{margin:0 0 4px;font-size:10px;letter-spacing:.14em;font-weight:600;
    text-transform:uppercase;color:var(--dim)}
  @media (max-width:1000px){#card .wires{grid-template-columns:1fr}}
</style></head>
<body data-program="__PROGRAM__">
<canvas id="c"></canvas>
<div id="hud" class="rail">
  <span id="program"></span>
  <span id="counts"></span>
  <button id="drawer" class="chip" type="button" aria-expanded="false"
          aria-controls="side">arriving</button>
</div>
<aside id="side" aria-label="nodes as they arrive">
  <header><h2>arriving <span id="count">0</span></h2>
  <button id="fold" type="button" aria-label="close">&times;</button></header>
  <ul class="feed" id="feed"></ul>
</aside>
<div id="legend" class="rail"></div>
<div id="tip"></div>
<div id="sheet"><div id="card"></div></div>
<script src="/app.js"></script></body></html>
"""

# The page and the script it runs are two files so the policy can name the
# script by its origin instead of permitting inline script at large. The
# Program name rides in an attribute for the same reason: it keeps this script
# a constant that the server never rewrites, and an attribute cannot end the
# element it sits in the way a quote can end a string.
SCRIPT = r"""// Which Program is on screen, and the page does not get to choose. The server
// was opened against one configuration and every route it answers is about
// that Program, so this is a caption rather than a control -- the tooling this
// grew out of picked a database per request, which is the same authority
// spelled as a convenience.
const PROGRAM = document.body.dataset.program;
const COLOR = {
  entity:      "#5b8db8",
  observation: "#7d8590",
  hypothesis:  "#a78bfa",
  finding:     "#ff5a5f",
  address:     "#38d6c4",
};
// The five levels `findings.severity` is constrained to, and the only place on
// this page a saturated colour is spent. Hypotheses moved off amber to violet
// when this arrived: a guess and a medium-severity Finding are not the same
// news, and they were the same yellow.
const SEVERITY = {
  critical: "#ff2d55",
  high:     "#ff5a5f",
  medium:   "#ff9f1c",
  low:      "#3fb950",
  info:     "#4cc9f0",
};
const LEVELS = ["critical", "high", "medium", "low", "info"];

// What colour a node is drawn in. A Finding answers with its severity, because
// on this surface how bad it is *is* what it is; everything else answers with
// its kind. A Finding whose severity is not one of the five falls back to the
// kind colour rather than to nothing, so an unexpected value is visible as a
// Finding instead of invisible.
function tone(n){
  if(n.kind === "finding") return SEVERITY[n.sub] || COLOR.finding;
  return COLOR[n.kind];
}
// What is drawn when the page opens. Observations arrive by the hundred and
// are the detail behind a claim, not the shape of the surface, so they start
// folded away and the legend turns them back on.
const SHOW = {entity:true, address:true, hypothesis:true, finding:true,
              observation:false};
const ORDER = {finding:0, hypothesis:1, entity:2, address:2, observation:3};

// The Findings and the ground they were found on, and nothing else. Off, so the
// whole surface is still what this command opens on: a picture that quietly
// held back nineteen nodes in twenty would be answering a different question
// than the one the operator opened it to ask, and the HUD says how many it set
// aside for as long as this is on.
//
// Two hops rather than one or three, measured on the here engagement's 1484
// visible nodes: one hop is 17 nodes -- each Finding and the single Entity it
// was filed against, which is a list and not a picture -- and three is 166 and
// climbing back towards the cloud. Two is 81 nodes and 93 edges: the Finding,
// what it is about, and what that thing is attached to.
let TRAIL = false;
const TRAIL_HOPS = 2;
const RING = {
  application:"#4aa3ff", endpoint:"#38d6c4", host:"#6f7dff", domain:"#6f7dff",
  parameter:"#38d6c4", identity:"#c792ea", technology:"#5f6b7a", service:"#6f7dff",
  supported:"#3fb950", testable:"#f0b429", testing:"#f0b429",
  refuted:"#ff4d6d", inconclusive:"#7d8590", proposed:"#7d8590",
};
const LINK = {
  supports:"#3fb950", refutes:"#ff4d6d", relationship:"#4aa3ff",
  observed:"#8b98a5", about:"#f0b429", finding_on:"#ff4d6d", under:"#4aa3ff",
  resolves:"#38d6c4", served_at:"#4aa3ff", subdomain_of:"#6f7dff",
};
const FADE = {
  supports:"88", refutes:"88", relationship:"55",
  observed:"33", about:"66", finding_on:"99", under:"55", resolves:"66",
  served_at:"55", subdomain_of:"55",
};

// ---------------------------------------------------------------------------
// Glyphs
// ---------------------------------------------------------------------------
// Twelve icons from Lucide (ISC), copied in as their path data rather than
// fetched: this page has no dependency and an engagement laptop is not always
// on a network that reaches a CDN. Each is a 24x24 stroke drawing, rasterised
// once through an SVG data URL and then blitted, which is cheaper per frame
// than replaying the paths.
const ICON = {
  domain:[["circle",{"cx":"12","cy":"12","r":"10"}],["path",{"d":"M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"}],["path",{"d":"M2 12h20"}]],
  host:[["rect",{"width":"20","height":"8","x":"2","y":"2","rx":"2","ry":"2"}],["rect",{"width":"20","height":"8","x":"2","y":"14","rx":"2","ry":"2"}],["line",{"x1":"6","x2":"6.01","y1":"6","y2":"6"}],["line",{"x1":"6","x2":"6.01","y1":"18","y2":"18"}]],
  application:[["rect",{"x":"2","y":"4","width":"20","height":"16","rx":"2"}],["path",{"d":"M10 4v4"}],["path",{"d":"M2 8h20"}],["path",{"d":"M6 4v4"}]],
  endpoint:[["circle",{"cx":"6","cy":"19","r":"3"}],["path",{"d":"M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"}],["circle",{"cx":"18","cy":"5","r":"3"}]],
  parameter:[["path",{"d":"M10 5H3"}],["path",{"d":"M12 19H3"}],["path",{"d":"M14 3v4"}],["path",{"d":"M16 17v4"}],["path",{"d":"M21 12h-9"}],["path",{"d":"M21 19h-5"}],["path",{"d":"M21 5h-7"}],["path",{"d":"M8 10v4"}],["path",{"d":"M8 12H3"}]],
  technology:[["path",{"d":"M12 20v2"}],["path",{"d":"M12 2v2"}],["path",{"d":"M17 20v2"}],["path",{"d":"M17 2v2"}],["path",{"d":"M2 12h2"}],["path",{"d":"M2 17h2"}],["path",{"d":"M2 7h2"}],["path",{"d":"M20 12h2"}],["path",{"d":"M20 17h2"}],["path",{"d":"M20 7h2"}],["path",{"d":"M7 20v2"}],["path",{"d":"M7 2v2"}],["rect",{"x":"4","y":"4","width":"16","height":"16","rx":"2"}],["rect",{"x":"8","y":"8","width":"8","height":"8","rx":"1"}]],
  service:[["path",{"d":"M2.97 12.92A2 2 0 0 0 2 14.63v3.24a2 2 0 0 0 .97 1.71l3 1.8a2 2 0 0 0 2.06 0L12 19v-5.5l-5-3-4.03 2.42Z"}],["path",{"d":"m7 16.5-4.74-2.85"}],["path",{"d":"m7 16.5 5-3"}],["path",{"d":"M7 16.5v5.17"}],["path",{"d":"M12 13.5V19l3.97 2.38a2 2 0 0 0 2.06 0l3-1.8a2 2 0 0 0 .97-1.71v-3.24a2 2 0 0 0-.97-1.71L17 10.5l-5 3Z"}],["path",{"d":"m17 16.5-5-3"}],["path",{"d":"m17 16.5 4.74-2.85"}],["path",{"d":"M17 16.5v5.17"}],["path",{"d":"M7.97 4.42A2 2 0 0 0 7 6.13v4.37l5 3 5-3V6.13a2 2 0 0 0-.97-1.71l-3-1.8a2 2 0 0 0-2.06 0l-3 1.8Z"}],["path",{"d":"M12 8 7.26 5.15"}],["path",{"d":"m12 8 4.74-2.85"}],["path",{"d":"M12 13.5V8"}]],
  identity:[["circle",{"cx":"12","cy":"8","r":"5"}],["path",{"d":"M20 21a8 8 0 0 0-16 0"}]],
  observation:[["path",{"d":"M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"}],["circle",{"cx":"12","cy":"12","r":"3"}]],
  hypothesis:[["path",{"d":"M14 2v6a2 2 0 0 0 .245.96l5.51 10.08A2 2 0 0 1 18 22H6a2 2 0 0 1-1.755-2.96l5.51-10.08A2 2 0 0 0 10 8V2"}],["path",{"d":"M6.453 15h11.094"}],["path",{"d":"M8.5 2h7"}]],
  finding:[["path",{"d":"M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"}],["path",{"d":"M12 8v4"}],["path",{"d":"M12 16h.01"}]],
  address:[["rect",{"x":"16","y":"16","width":"6","height":"6","rx":"1"}],["rect",{"x":"2","y":"16","width":"6","height":"6","rx":"1"}],["rect",{"x":"9","y":"2","width":"6","height":"6","rx":"1"}],["path",{"d":"M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"}],["path",{"d":"M12 12V8"}]]
};
let ICONS = localStorage.getItem("rk2icons") !== "off";
const glyphs = new Map();
function glyph(name){
  if(glyphs.has(name)) return glyphs.get(name);
  const parts = ICON[name];
  if(!parts){ glyphs.set(name, null); return null; }
  const body = parts.map(([tag, at]) => "<" + tag + " "
    + Object.entries(at).map(([k, v]) => k + '="' + v + '"').join(" ") + "/>").join("");
  const img = new Image();
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    + 'stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" '
    + 'stroke-linejoin="round">' + body + "</svg>");
  glyphs.set(name, img);
  return img;
}

const c = document.getElementById("c"), g = c.getContext("2d");
const tip = document.getElementById("tip");
let W=0,H=0, DPR=Math.min(2,devicePixelRatio||1);
function size(){ W=innerWidth;H=innerHeight;c.width=W*DPR;c.height=H*DPR;
  c.style.width=W+"px";c.style.height=H+"px";g.setTransform(DPR,0,0,DPR,0,0); }
addEventListener("resize",size); size();

let nodes=new Map(), allLinks=[], live=[], vlinks=[], degree=new Map(), named=[];
// Opens a little pulled back, because the layout above spreads roughly twice
// as wide as it used to and a graph that starts off the edge reads as broken.
let stats={}, omitted=0, view={x:0,y:0,k:0.7}, hover=null, dragging=null, panning=null;

function merge(data){
  const now = performance.now(), fresh=[], alive=new Set();
  for(const raw of data.nodes){
    alive.add(raw.id);
    let n = nodes.get(raw.id);
    if(!n){
      const a=Math.random()*Math.PI*2, r=40+Math.random()*140;
      n={x:Math.cos(a)*r, y:Math.sin(a)*r, vx:0, vy:0, born:now};
      nodes.set(raw.id, n); fresh.push(raw);
    }
    Object.assign(n, raw);
  }
  for(const id of [...nodes.keys()]) if(!alive.has(id)) nodes.delete(id);
  allLinks = data.links.filter(l => nodes.has(l.a) && nodes.has(l.b));
  stats = data.stats || {};
  omitted = data.omitted || 0;
  filter();
  if(fresh.length) feed(fresh);
  hud();
  // The gauge is a reading of the campaign, so it is redrawn when the campaign
  // is. A Finding that arrived mid-hunt and did not light its level would be a
  // gauge that has to be reloaded to be believed.
  legend();
}

function filter(){
  const shown = trail([...nodes.values()].filter(n => SHOW[n.kind]));
  const on = new Set(shown.map(n => n.id));
  degree = new Map();
  for(const l of allLinks) if(on.has(l.a) && on.has(l.b)){
    degree.set(l.a, (degree.get(l.a)||0)+1);
    degree.set(l.b, (degree.get(l.b)||0)+1);
  }
  lod = detail(view.k);
  live = lod === 0 ? shown : shown.filter(
    n => KEEP[n.kind] || n === hover || (degree.get(n.id)||0) > lod);
  const kept = new Set(live.map(n => n.id));
  vlinks = allLinks.filter(l => kept.has(l.a) && kept.has(l.b));
  // Both of these are functions of `live`, `vlinks` and `degree` and of nothing
  // a frame changes, so they are computed where those are. `radius` was called
  // twice per node pair -- n^2 times a frame -- and this order was a full sort
  // of every node, every frame, for a list that only moves when a filter does.
  for(const n of live) n.r = radius(n);
  // And then the Findings are lifted over whatever the terrain reached. Size on
  // this page means edge count, a Finding has exactly one edge -- the Entity it
  // was filed against -- and the terrain has hubs, so the same rule drew the
  // thing the campaign is for at the size of a leaf. Measured on the here
  // engagement: 429 of the 1484 nodes on screen came out at least as large as
  // the largest of the nine Findings, and the nine were 0.4% of the ink. That
  // is the search the operator was doing.
  //
  // Against the tallest node actually drawn rather than against a number, so
  // this holds on a campaign whose busiest Domain is twice this one's. A
  // Finding still grows with its own edges; it just never falls below the top.
  const tallest = live.reduce(
    (high, n) => n.kind === "finding" ? high : Math.max(high, n.r), 0);
  for(const n of live)
    if(n.kind === "finding") n.r = Math.max(n.r, tallest * FINDING_LEAD);
  islands();
  named = live.filter(n => n.label).sort((a,b) =>
    (ORDER[a.kind]-ORDER[b.kind]) || ((degree.get(b.id)||0)-(degree.get(a.id)||0)));
}

// What is left when the picture is cut back to its Findings: the Findings
// themselves and everything within TRAIL_HOPS edges of one. The whole list back
// unchanged when the trail is off, so this is one call in `filter` rather than
// a branch around it.
//
// Breadth-first over the edges of the kinds that are already showing, so
// turning Observations on widens the trail rather than being ignored by it. A
// Finding with no subject Entity survives on its own -- it is still a Finding,
// and dropping it here would be this rail hiding the thing it exists to find.
function trail(shown){
  if(!TRAIL) return shown;
  const on = new Set(shown.map(n => n.id));
  const near = new Map();
  const join = (a, b) => {
    let list = near.get(a);
    if(!list) near.set(a, list = []);
    list.push(b);
  };
  for(const l of allLinks) if(on.has(l.a) && on.has(l.b)){ join(l.a, l.b); join(l.b, l.a); }
  const reached = new Set(shown.filter(n => n.kind === "finding").map(n => n.id));
  let edge = [...reached];
  for(let hop = 0; hop < TRAIL_HOPS && edge.length; hop++){
    const next = [];
    for(const id of edge) for(const other of near.get(id) || [])
      if(!reached.has(other)){ reached.add(other); next.push(other); }
    edge = next;
  }
  return shown.filter(n => reached.has(n.id));
}

// Which island each node is on: the connected component of the visible graph,
// found by union-find over the visible edges. Computed here and not per frame
// because it is a function of `live` and `vlinks` like the two above it, and
// changes only when a filter does.
//
// This is what `step` needs to tell a neighbour from a stranger. Everything the
// campaign found that has no path to everything else is a separate thing, and a
// field that pushed every pair alike packed the lot into one cloud with the
// group boundaries somewhere inside it.
function islands(){
  const up = new Map();
  const root = id => { let r=id; while(up.get(r)!==r) r=up.get(r);
                       while(up.get(id)!==r){ const nx=up.get(id); up.set(id,r); id=nx; }
                       return r; };
  for(const n of live) up.set(n.id, n.id);
  for(const l of vlinks){
    const a=root(l.a), b=root(l.b);
    if(a!==b) up.set(a, b);
  }
  for(const n of live) n.isle = root(n.id);
}

function feed(fresh){
  const ul = document.getElementById("feed");
  const blank = ul.querySelector(".empty");
  if(fresh.length && blank) blank.remove();
  for(const n of fresh.slice(-24).reverse()){
    const li = document.createElement("li");
    li.innerHTML = '<i style="background:'+tone(n)+'"></i>'
      + '<span class="t">'+esc(n.label||n.ref||n.id.slice(0,8))+'</span>'
      + '<span class="s">'+esc(n.sub||n.kind)+'</span>';
    ul.prepend(li);
  }
  while(ul.children.length > 200) ul.lastChild.remove();
  if(!ul.children.length) ul.innerHTML = '<li class="empty">nothing has arrived yet</li>';
  document.getElementById("count").textContent =
    ul.querySelector(".empty") ? 0 : ul.children.length;
}
function esc(s){ return String(s==null?"":s).replace(/[<>&]/g, ch =>
  ({"<":"&lt;",">":"&gt;","&":"&amp;"}[ch])); }

// The panel is off-canvas rather than shrunk, so "closed" means the same thing
// on a phone as on a desk and nothing here ever half-covers the graph.
const side = document.getElementById("side"),
      drawer = document.getElementById("drawer"),
      fold = document.getElementById("fold");
function panel(open){
  side.classList.toggle("on", open);
  drawer.classList.toggle("off", !open);
  drawer.setAttribute("aria-expanded", open ? "true" : "false");
}
drawer.onclick = () => panel(!side.classList.contains("on"));
fold.onclick = () => panel(false);
addEventListener("keydown", ev => {
  if(ev.key === "Escape" && side.classList.contains("on")) panel(false);
});
// Opens beside the graph where there is room for both, and closed where there
// is not. A panel that covers the picture on arrival is a panel that has to be
// dismissed before the page can be read.
panel(innerWidth > 900);
side.addEventListener("wheel", ev => ev.stopPropagation());

// How many nodes the legend would show that something is holding back. The zoom
// band was the only thing that did, and the finding trail holds back far more of
// them at any zoom -- so the `lod` guard is gone and this is the difference
// between what the kind chips say is on and what is actually drawn, whichever
// of the two took it out.
function hidden(){
  let n = 0;
  for(const x of nodes.values()) if(SHOW[x.kind]) n++;
  return Math.max(n - live.length, 0);
}

function hud(){
  const order = ["entities","relationships","observations","hypotheses","evidence",
                 "tests","findings","receipts","tool_runs","agent_runs","tasks"];
  // The bound is stated where the counts are, because a picture that drew 400
  // of 3000 Observations and said only "observations 3000" is a picture that
  // reads as the whole campaign.
  document.getElementById("counts").innerHTML =
    order.map(k => '<span>'+k.replace("_"," ")+' <b>'+(stats[k]??0)+'</b></span>').join("")
    + (omitted ? '<span class="omitted">not drawn <b>'+omitted+'</b></span>' : "")
    + (hidden() ? '<span class="omitted">held back <b>'+hidden()+'</b></span>' : "");
}

// Written once, outside `hud()`, because it never changes: the Program this
// surface is about was settled when the server opened the configuration.
function caption(){
  document.getElementById("program").textContent = PROGRAM;
}
// How many Findings this campaign holds at each level. Counted off the nodes
// the server sent rather than off `stats`, which carries one total and cannot
// say what it is a total of.
function severities(){
  const tally = {};
  for(const n of nodes.values()) if(n.kind === "finding"){
    tally[n.sub] = (tally[n.sub] || 0) + 1;
  }
  return tally;
}

function gauge(){
  const tally = severities();
  return '<span id="gauge">' + LEVELS.map(level => {
    const held = tally[level] || 0;
    return '<span class="lvl'+(held ? " lit" : "")+'" style="--tone:'+SEVERITY[level]+'">'
      + '<span class="n">'+held+'</span><span class="w">'+level+'</span></span>';
  }).join("") + '</span>';
}

function legend(){
  const box = document.getElementById("legend");
  box.innerHTML = gauge()
    + '<span class="sep"></span>'
    + Object.entries(COLOR).map(([k,v]) =>
        '<button type="button" class="chip'+(SHOW[k]?'':' off')+'" data-kind="'+k+'"'
        + ' aria-pressed="'+(SHOW[k]?"true":"false")+'">'
        + '<i style="background:'+v+'"></i>'+k+'</button>').join("")
    + '<span class="sep"></span>'
    + '<button type="button" class="chip'+(TRAIL?'':' off')+'" id="trail"'
    + ' aria-pressed="'+(TRAIL?"true":"false")+'">finding trail</button>'
    + '<button type="button" class="chip'+(ICONS?'':' off')+'" id="glyphs"'
    + ' aria-pressed="'+(ICONS?"true":"false")+'">icons</button>'
    + '<button type="button" class="chip" id="fitall">fit</button>';
  for(const el of box.querySelectorAll(".chip[data-kind]")) el.onclick = () => {
    SHOW[el.dataset.kind] = !SHOW[el.dataset.kind];
    hover = null; tip.style.opacity = 0;
    filter(); legend();
  };
  // The trail frames what it left as well as cutting to it. Turning it on and
  // leaving the view where it was is the same search over a smaller graph,
  // which is the complaint rather than the answer to it.
  box.querySelector("#trail").onclick = () => {
    TRAIL = !TRAIL;
    hover = null; tip.style.opacity = 0;
    filter(); legend(); hud(); fit();
  };
  box.querySelector("#glyphs").onclick = () => {
    ICONS = !ICONS;
    localStorage.setItem("rk2icons", ICONS ? "on" : "off");
    legend();
  };
  box.querySelector("#fitall").onclick = fit;
}
legend();

// How big a node grows for being connected, as a multiple of its own base.
// Ten. Five was set against a spread of 3 to 22 edges and read as flat on the
// real picture: at 2.2 a busy node came out 3.1x a lone one, which is a
// difference the eye loses among a thousand dots. The ceiling is still what
// keeps it a picture -- unbounded growth turns one busy apex into a disc with
// the rest of the graph behind it -- it is just set where the hubs are.
const MAX_GROWTH = 10;

// How many nodes may glow before the glow costs more than it says. Four
// hundred, because that is where a shadowed fill per node stops fitting in a
// frame on the machines this is opened on.
const GLOW_BUDGET = 400;

// The square root, because what the eye compares is area rather than radius.
// 0.85 rather than 1.2: at 1.2 a median entity of 3 edges came out 2.4x a leaf
// and still read as one more dot in a hairball of sixteen hundred. Against the
// 0.6 floor a median 3 edges now reads 3.1x, the 95th percentile of 9 reads
// 5.6x and the busiest 22 reads 8.9x. The ceiling lands at 75 edges, which a
// long campaign reaches and a short one does not.
const GROWTH_SPREAD = 0.85;

// The floor, and the point the curve passes through 1. A node of one edge is
// its kind's base size, and a node of none is smaller than that -- so the size
// says something about every node rather than only about the hubs. Without the
// floor the curve goes negative at degree 0.
const MIN_SHRINK = 0.6;
const PIVOT = 1;

// How far a Finding stands over the tallest thing beside it, applied in
// `filter` once the terrain has been measured. 1.15 rather than 1.0: level with
// the busiest Domain is level, and a Finding that ties for largest is still a
// Finding somebody has to compare sizes to find.
const FINDING_LEAD = 1.15;

// The zoom bands and the edge count a node needs to survive each. Read
// low-to-high and the last match wins, so 0.30 is stricter than 0.55.
const LOD = [[0.55, 1], [0.30, 3]];
const KEEP = {finding:true, hypothesis:true};

function detail(k){
  let floor = 0;
  for(const [below, need] of LOD) if(k < below) floor = need;
  return floor;
}
let lod = 0;

function radius(n){
  const base = n.kind==="finding" ? 22 : n.kind==="hypothesis" ? 16
             : n.kind==="entity" ? 14 : n.kind==="address" ? 15 : 7;
  // A multiple rather than an addition, so the kinds keep their order however
  // busy any of them gets: the old rule added the same nine pixels to every
  // kind, which made a busy Observation larger than a lone Finding.
  const grow = 1 + (Math.sqrt(degree.get(n.id) || 0) - PIVOT) / GROWTH_SPREAD;
  return base * Math.min(MAX_GROWTH, Math.max(MIN_SHRINK, grow));
}

// The repulsion cut-off, and the grid cell that makes it cheap. Every pair
// further apart than this contributes nothing -- the old loop still measured
// all of them, which is n^2 distance tests a frame and what made a campaign of
// a thousand nodes drop frames. Two nodes more than one cell apart are more
// than REPEL apart on one axis alone, so the five offsets below are every pair
// the cut-off can admit, counted once each.
const REPEL = 1400, REPEL2 = REPEL*REPEL;

// How much harder a node pushes something it has no path to. 3.4 rather than
// more: past about five the small islands are flung to the edge of the world
// and an operator has to zoom out past reading size to see any of them.
const SEPARATE = 3.4;

// The two halves of gravity. COMPACT holds a node to its own island and is what
// keeps a group a group; DRIFT holds the island to the middle and is the only
// thing stopping the whole picture wandering off. DRIFT is deliberately a
// twentieth of COMPACT: the middle has to be a suggestion rather than a squeeze,
// or the gaps close again.
const COMPACT = 0.0018, DRIFT = 0.00009;
const centres = new Map();
const NEIGHBOURS = [[0,0],[1,0],[-1,1],[0,1],[1,1]];
const cells = new Map();

function step(){
  cells.clear();
  for(const n of live){
    const key = ((n.x/REPEL)|0)*100003 + ((n.y/REPEL)|0);
    let bucket = cells.get(key);
    if(!bucket) cells.set(key, bucket=[]);
    bucket.push(n);
  }
  for(const bucket of cells.values()){
    const cx = (bucket[0].x/REPEL)|0, cy = (bucket[0].y/REPEL)|0;
    for(const [ox, oy] of NEIGHBOURS){
      const other = (ox|oy) === 0 ? bucket : cells.get((cx+ox)*100003 + (cy+oy));
      if(!other) continue;
      for(let i=0;i<bucket.length;i++){
        const a=bucket[i];
        for(let j=(other===bucket ? i+1 : 0); j<other.length; j++){
          const b=other[j];
          let dx=a.x-b.x, dy=a.y-b.y, d2=dx*dx+dy*dy;
          if(d2>REPEL2) continue;
          if(d2<1){ dx=Math.random()-.5; dy=Math.random()-.5; d2=1; }
          // Bigger nodes push harder, so a hub keeps room for its own label. The
          // numbers here are what decides whether an operator can see which edge
          // goes where: a graph that fits is not the goal, a graph that reads is.
          // Strangers push harder than neighbours. Two nodes on one island are
          // held together by the springs below whatever this does, so the extra
          // push lands almost entirely between islands -- which is where the
          // space has to go for the groups to be tellable apart.
          const apart = a.isle !== b.isle;
          const push = (7000 + (a.r+b.r)*220) * (apart ? SEPARATE : 1);
          const f = Math.min(push/d2, apart ? 9.0 : 3.0), d=Math.sqrt(d2);
          a.vx+=dx/d*f; a.vy+=dy/d*f; b.vx-=dx/d*f; b.vy-=dy/d*f;
        }
      }
    }
  }
  // Gravity in two parts rather than one. A single pull on every node towards
  // the middle is also a pull of every island into every other island, and it
  // is the reason a campaign of this size draws as one cloud: the islands are
  // there, and the centre squeezes the gaps out of them. So each node is held
  // to its own island and each island, far more weakly, to the middle -- the
  // graph still centres and stops drifting, and what has to open up can.
  centres.clear();
  for(const n of live){
    let h = centres.get(n.isle);
    if(!h) centres.set(n.isle, h={x:0, y:0, n:0});
    h.x+=n.x; h.y+=n.y; h.n++;
  }
  for(const h of centres.values()){ h.x/=h.n; h.y/=h.n; }
  for(const a of live){
    const h = centres.get(a.isle);
    a.vx -= (a.x-h.x)*COMPACT + h.x*DRIFT;
    a.vy -= (a.y-h.y)*COMPACT + h.y*DRIFT;
  }
  for(const l of vlinks){
    const a=nodes.get(l.a), b=nodes.get(l.b);
    const dx=b.x-a.x, dy=b.y-a.y, d=Math.hypot(dx,dy)||1;
    const rest = (l.kind==="observed" ? 320 : l.kind==="under" ? 430
              : l.kind==="served_at" ? 400 : l.kind==="subdomain_of" ? 470
              : l.kind==="resolves" ? 400 : 550)
               + a.r + b.r;
    const f = (d-rest)*0.0075;
    a.vx+=dx/d*f; a.vy+=dy/d*f; b.vx-=dx/d*f; b.vy-=dy/d*f;
  }
  for(const n of live){
    if(n===dragging){ n.vx=n.vy=0; continue; }
    n.vx*=0.86; n.vy*=0.86;
    n.x+=Math.max(-8,Math.min(8,n.vx)); n.y+=Math.max(-8,Math.min(8,n.vy));
  }
}

const sx = n => n.x*view.k + W/2 + view.x;
const sy = n => n.y*view.k + H/2 + view.y;

// Labels are drawn in screen space, at one size, and only where nothing has
// been written yet. Scaled text turns to soup at any zoom that fits a hunt on
// one page, and overlapping text is worse than no text.
let taken = [];
function room(x, y, w, h){
  for(const r of taken)
    if(x < r.x+r.w && x+w > r.x && y < r.y+r.h && y+h > r.y) return false;
  taken.push({x,y,w,h});
  return true;
}
function chip(x, y, text, fg, bg, must){
  g.font = "11px ui-monospace,monospace";
  const w = g.measureText(text).width + 10, h = 16;
  if(!must && !room(x-2, y-h/2, w+4, h+3)) return;
  if(must) taken.push({x:x-2, y:y-h/2, w:w+4, h:h+3});
  g.beginPath(); g.roundRect(x, y-h/2, w, h, 5);
  g.fillStyle = bg; g.fill();
  g.fillStyle = fg; g.fillText(text, x+5, y+4);
}

function arrow(a, b, r){
  const dx=b.x-a.x, dy=b.y-a.y, d=Math.hypot(dx,dy)||1;
  const tx=b.x-dx/d*r, ty=b.y-dy/d*r, s=6/view.k, ang=Math.atan2(dy,dx);
  g.beginPath();
  g.moveTo(tx, ty);
  g.lineTo(tx-s*Math.cos(ang-0.4), ty-s*Math.sin(ang-0.4));
  g.lineTo(tx-s*Math.cos(ang+0.4), ty-s*Math.sin(ang+0.4));
  g.closePath(); g.fill();
}

// The field the graph sits on: a dot grid, drawn in screen space but offset by
// the view, so panning has something to move against. Without it a canvas with
// nothing moving on it reads as a frozen page rather than a still campaign.
//
// One tile, repeated by the pattern, and one `fillRect` a frame. The obvious
// version -- an `arc` per dot -- is a few thousand paths every frame for a
// picture that never changes between zooms, and the tile is only rebuilt when
// the spacing does.
//
// The spacing follows the zoom but is folded back into a band rather than
// tracking it: past about 56px the field reads as scattered specks, and under
// about 14px it stops being dots and becomes a grey wash, so it doubles or
// halves until it is legible again at whatever scale the operator is at.
let dots = null, dotGap = 0;
function field(){
  let gap = 30 * view.k;
  while(gap < 14) gap *= 2;
  while(gap > 56) gap /= 2;
  gap = Math.round(gap);
  if(gap !== dotGap || !dots){
    dotGap = gap;
    const tile = document.createElement("canvas");
    tile.width = tile.height = gap;
    const t = tile.getContext("2d");
    t.fillStyle = "#1b2531";
    t.beginPath(); t.arc(gap/2, gap/2, 1.1, 0, 7); t.fill();
    dots = g.createPattern(tile, "repeat");
  }
  // The pattern's origin is the canvas origin, so the field is moved under it
  // by translating before the fill and undoing that in the rectangle. Modulo
  // twice, because a negative pan would otherwise leave a seam at the edge.
  const ox = ((W/2 + view.x) % gap + gap) % gap;
  const oy = ((H/2 + view.y) % gap + gap) % gap;
  g.save();
  g.translate(ox, oy);
  g.fillStyle = dots;
  g.fillRect(-ox, -oy, W, H);
  g.restore();
}

function draw(){
  // Painted opaque rather than cleared to transparent. The page carries a
  // still dot field of its own for the moment before the first frame, and a
  // transparent canvas would let that one show through the gaps in this one --
  // two grids at two offsets, which is a moire pattern and not a texture.
  g.fillStyle = "#0b0f14";
  g.fillRect(0,0,W,H);
  field();
  const near = hover ? new Set([hover.id]) : null;
  if(near) for(const l of vlinks){
    if(l.a===hover.id) near.add(l.b);
    if(l.b===hover.id) near.add(l.a);
  }
  g.save();
  g.translate(W/2+view.x, H/2+view.y); g.scale(view.k, view.k);
  g.lineWidth = 1.2/view.k;
  for(const l of vlinks){
    const a=nodes.get(l.a), b=nodes.get(l.b);
    const lit = !near || (near.has(l.a) && near.has(l.b));
    g.globalAlpha = lit ? 0.5 : 0.05;
    g.strokeStyle = LINK[l.kind] + (FADE[l.kind]||"55");
    g.beginPath(); g.moveTo(a.x,a.y); g.lineTo(b.x,b.y); g.stroke();
    g.fillStyle = LINK[l.kind] + (FADE[l.kind]||"55");
    arrow(a, b, b.r+1.5/view.k);
  }
  g.globalAlpha = 1;
  const now = performance.now();
  // A shadowed fill is the most expensive thing this frame does -- one blurred
  // composite per node -- and at a thousand nodes it is most of the frame. The
  // glow is what makes a Finding read as a Finding, so it is kept for the two
  // kinds a campaign is about and for the node under the cursor, and dropped
  // for the surface once the surface is large enough to cost anything.
  const glowing = live.length <= GLOW_BUDGET;
  for(const n of live){
    const r = n.r, age = now-n.born;
    g.globalAlpha = (!near || near.has(n.id)) ? 1 : 0.15;
    if(age < 6000){
      const t=age/6000, pr=r+(1-t)*26;
      g.beginPath(); g.arc(n.x,n.y,pr,0,7);
      g.strokeStyle = tone(n)+Math.round((1-t)*200).toString(16).padStart(2,"0");
      g.lineWidth = 2/view.k; g.stroke(); g.lineWidth = 1.2/view.k;
    }
    g.beginPath(); g.arc(n.x,n.y,r,0,7);
    g.fillStyle = n.ok===false ? "#2b3440" : tone(n);
    if(glowing || n===hover || n.kind==="finding" || n.kind==="hypothesis"){
      g.shadowColor = tone(n)+"66"; g.shadowBlur = 12;
      g.fill(); g.shadowBlur = 0;
    } else g.fill();
    const ring = RING[n.sub];
    if(ring){ g.strokeStyle=ring; g.lineWidth=2.5/view.k; g.stroke(); g.lineWidth=1.2/view.k; }
    if(n===hover){ g.strokeStyle="#fff"; g.lineWidth=2.5/view.k; g.stroke(); g.lineWidth=1.2/view.k; }
    if(ICONS){
      // `sub` is the entity type for an entity and a status for a claim, so a
      // claim falls back to its kind. Drawn in white: the discs are mid-tone
      // and a dark glyph on them disappears at the zoom that fits a hunt.
      const mark = glyph(ICON[n.sub] ? n.sub : n.kind);
      if(mark && mark.complete && mark.naturalWidth){
        const s = r*1.2;
        g.drawImage(mark, n.x-s/2, n.y-s/2, s, s);
      }
    }
  }
  g.globalAlpha = 1;
  g.restore();

  taken = [{x:0,y:0,w:W,h:46}, {x:0,y:H-46,w:W,h:46}];
  const box = side.getBoundingClientRect();
  taken.push({x:box.left-8, y:box.top-8, w:box.width+16, h:box.height+16});
  // Only what the pointer is on, and what one edge from it. A chip on every
  // named node is sixteen hundred chips: a wall of text with a graph behind it,
  // and the node sizes underneath it invisible. `near` already holds the hover
  // and its neighbours, so the names follow the hand.
  //
  // The Findings are the exception, and they are nine chips rather than sixteen
  // hundred. Every name here followed the hand, which means a picture nobody is
  // touching carries no text at all -- measured on the here engagement, the
  // opening frame drew 570 discs and zero words -- so the only way to tell
  // which disc was a Finding was to hover discs until one said so. They are
  // drawn in their own severity and with the `ref` the report cites them by, so
  // the badge is the label, the level and the F-number in one, and `must`
  // because nine badges that take turns hiding each other are nine badges that
  // flicker.
  //
  // What bounds this is the viewport cull below rather than a count: a campaign
  // that files fifty Findings draws fifty badges, and the ones off the edge cost
  // nothing. If a screenful of them ever reads as a wall the answer is the
  // finding trail, which is the control that already exists for it.
  for(const n of named){
    const marked = n.kind === "finding";
    if(!marked && (!near || !near.has(n.id))) continue;
    const x = sx(n), y = sy(n), r = n.r*view.k;
    if(x < -200 || x > W+200 || y < -60 || y > H+60) continue;
    if(marked) chip(x + r + 6, y, (n.ref ? n.ref + "  " : "") + n.label,
                    "#0b0f14", tone(n), true);
    else chip(x + r + 6, y, n.label, "#e6edf3", "#111a24e6", n===hover);
  }
  if(view.k > 1.0) for(const l of vlinks){
    if(!l.label) continue;
    if(!near || !(near.has(l.a) && near.has(l.b))) continue;
    const a=nodes.get(l.a), b=nodes.get(l.b);
    chip((sx(a)+sx(b))/2 - 20, (sy(a)+sy(b))/2, l.label, "#8b98a5", "#0b0f14d9");
  }
}

function loop(){ step(); draw(); requestAnimationFrame(loop); }

function at(ev){
  const x=(ev.clientX-W/2-view.x)/view.k, y=(ev.clientY-H/2-view.y)/view.k;
  let best=null, bd=1e9;
  // `n.r` and not `radius(n)`: a Finding is drawn over the terrain rather than
  // at what the size rule alone returns, and a hit box that disagreed with the
  // disc would be a badge you can read and cannot click.
  for(const n of live){
    const d=Math.hypot(n.x-x, n.y-y);
    if(d < n.r+6 && d < bd){ bd=d; best=n; }
  }
  return best;
}
// Zoom about a point rather than about the origin. The world point under
// (px,py) is the one that has to stay under it, so the view moves by whatever
// the scale change opens up beneath it. Without this the picture slides away
// from whatever was being looked at every time the zoom changes, which on a
// pinch is the whole gesture fighting the hand making it.
function anchor(k, px, py){
  const wx = (px - W/2 - view.x)/view.k, wy = (py - H/2 - view.y)/view.k;
  view.k = Math.max(0.15, Math.min(4, k));
  view.x = px - W/2 - wx*view.k;
  view.y = py - H/2 - wy*view.k;
  // Only when the band changes. `filter` sorts and re-measures every node, so
  // running it on every wheel notch would cost more than the detail it saves.
  if(detail(view.k) !== lod){ filter(); hud(); }
}

// Frame everything the filters left on. The layout keeps moving and new nodes
// arrive off the edge, so this is the answer to "where did the rest of it go"
// -- the one question a campaign this size raises on a screen this small.
function fit(){
  if(!live.length) return;
  let x0=1e9, y0=1e9, x1=-1e9, y1=-1e9;
  for(const n of live){
    // The drawn radius, for the reason `at` uses it: a Finding stands over the
    // terrain, and a frame measured on the size rule alone would cut the
    // biggest thing on the picture off at the edge.
    const r = n.r+24;
    x0=Math.min(x0,n.x-r); y0=Math.min(y0,n.y-r);
    x1=Math.max(x1,n.x+r); y1=Math.max(y1,n.y+r);
  }
  const pad = 56;
  view.k = Math.max(0.15, Math.min(4,
    Math.min((W-pad*2)/Math.max(x1-x0,1), (H-pad*2)/Math.max(y1-y0,1))));
  view.x = -((x0+x1)/2)*view.k;
  view.y = -((y0+y1)/2)*view.k;
  if(detail(view.k) !== lod){ filter(); hud(); }
}

// Pointer events and not mouse events: one set of handlers covers a mouse, a
// finger and a pen, and the phone this gets read on has no mouse at all. Under
// the mouse-only version a phone got a still picture -- no pan, no zoom, no way
// to open a node -- and whatever the layout had put off the edge was gone.
const touching = new Map();
let pinch = null, pressed = null, tapped = 0;

c.addEventListener("pointerdown", ev => {
  c.setPointerCapture(ev.pointerId);
  touching.set(ev.pointerId, {x:ev.clientX, y:ev.clientY});
  if(touching.size === 2){
    // A second finger ends whatever the first was doing. Dragging a node with
    // one finger while the other scales the view is two answers to one gesture.
    dragging = null; panning = null; pressed = null;
    const [a,b] = [...touching.values()];
    pinch = {d: Math.hypot(a.x-b.x, a.y-b.y) || 1, k: view.k};
    return;
  }
  const n = at(ev);
  pressed = {x:ev.clientX, y:ev.clientY, node:n};
  hover = n;
  if(n) dragging=n; else panning={x:ev.clientX-view.x, y:ev.clientY-view.y};
  c.classList.add("drag");
});

c.addEventListener("pointermove", ev => {
  const held = touching.get(ev.pointerId);
  if(held){ held.x=ev.clientX; held.y=ev.clientY; }
  if(pinch && touching.size === 2){
    const [a,b] = [...touching.values()];
    anchor(pinch.k * Math.hypot(a.x-b.x, a.y-b.y)/pinch.d, (a.x+b.x)/2, (a.y+b.y)/2);
    return;
  }
  if(dragging){
    dragging.x=(ev.clientX-W/2-view.x)/view.k;
    dragging.y=(ev.clientY-H/2-view.y)/view.k;
    return;
  }
  if(panning){ view.x=ev.clientX-panning.x; view.y=ev.clientY-panning.y; return; }
  // `hover` is still tracked: it is what dims everything the node is not
  // joined to, and that is the useful half. The box that followed the cursor
  // was the other half, and it covered the neighbours it was describing.
  hover = at(ev);
});

function lifted(ev){
  touching.delete(ev.pointerId);
  if(touching.size < 2) pinch = null;
  // A tap is a press that did not travel. Dragging a node into place must not
  // open a sheet over the graph the drag was arranging. Eight pixels rather
  // than five: a finger is not a mouse and never lands twice on one point.
  const still = pressed
    && Math.hypot(ev.clientX-pressed.x, ev.clientY-pressed.y) < 8;
  if(still && pressed.node) open(pressed.node);
  else if(still){
    // Two taps on empty ground frame the whole campaign. A phone has no second
    // button and no keyboard to reach for, so the gesture is the control.
    if(performance.now() - tapped < 320) fit();
    tapped = performance.now();
  }
  pressed=null; dragging=null; panning=null; c.classList.remove("drag");
  // A finger that lifts leaves no cursor behind. Without this the dimming it
  // caused stays on with nothing hovering to justify it.
  if(ev.pointerType !== "mouse") hover = null;
}
c.addEventListener("pointerup", lifted);
c.addEventListener("pointercancel", lifted);

const sheet = document.getElementById("sheet"), card = document.getElementById("card");
sheet.onclick = ev => { if(ev.target === sheet) shut(); };
addEventListener("keydown", ev => { if(ev.key === "Escape") shut(); });
function shut(){ sheet.classList.remove("on"); }

const HIDE = new Set(["id","program_id","entity_id","entity_type","dedup_key",
  "scope_version_at","scope_selector_kind","scope_path_raw","superseded_by",
  "agent_run_id","receipt_id","tool_run_id","subject_entity_id","class_id",
  "application_id","endpoint_id","host_id","tenant_entity_id","secret_ref",
  "callback_interaction_id","observed_fingerprint","identity_a_entity_id",
  "identity_b_entity_id","validated_by_test_run_id","duplicate_of_finding_id",
  "opened_by_test_run_id",
  // An Observation's `metadata` is `{"element":"observations[0]","proposal":"PR2"}`
  // and never anything else: it is the pointer back into the proposal the row
  // was promoted from, which is the one thing the proof section above has
  // already followed. Shown raw it reads as a fact about nothing.
  "metadata"]);
const TITLE = {seen_by:"observed here", claims:"claims about this",
  evidence:"evidence on this claim", receipt:"the exchange behind it",
  exchanges:"exchanges over this address", address:"the address",
  run:"the run that saw it", proof:"why we say this"};

// ---------------------------------------------------------------------------
// Proof
// ---------------------------------------------------------------------------
// A claim on this page used to be a sentence with nothing under it. "Plesk runs
// here" is worth reading only beside the bytes that say so, so every claim
// carries three things now: which tool went and looked, what the child wrote
// when it came back, and the exchange itself, headers and body, as it went past
// the door. The bytes are fetched only when asked for: a body can be a megabyte.

function rx(s){ return s.replace(/[.*+?^{}()|[\]\\$]/g, "\\$&"); }

//: JSON with its keys, strings and numbers apart. The text arriving here is
//: already HTML-escaped, so the patterns match &quot; rather than a quote.
function jsonHi(t){
  return t
    .replace(/(&quot;[^&]*?&quot;)(\s*:)/g, '<span class="k">$1</span>$2')
    .replace(/:(\s*)(&quot;[^&]*?&quot;)/g, ':$1<span class="s">$2</span>')
    .replace(/\b(-?\d+(?:\.\d+)?)\b/g, '<span class="n">$1</span>')
    .replace(/\b(true|false|null)\b/g, '<span class="b">$1</span>');
}

//: Tags one colour, attribute names another, quoted values a third.
function htmlHi(t){
  return t
    .replace(/(&lt;\/?[A-Za-z][\w:-]*)/g, '<span class="t">$1</span>')
    .replace(/([\w:-]+)=(&quot;[^&]*?&quot;)/g,
             '<span class="k">$1</span>=<span class="s">$2</span>');
}

// ---------------------------------------------------------------------------
// What the claim was reading
// ---------------------------------------------------------------------------
// A child writes a sentence and the sentence quotes the thing it read: a header
// name, or a phrase it found in the body. Those quotations are the address of
// the proof inside 40 KB of wire, so they are pulled back out of the sentence
// and the lines carrying them are lit. Nothing is guessed: if the sentence
// quotes nothing, nothing is lit.
function hits(statement){
  if(!statement) return [];
  const out = [];
  //: Anything the child put in quotes, straight or curly.
  for(const m of statement.matchAll(
      /['"‘’“”]([^'"‘’“”]{3,140})['"‘’“”]/g))
    out.push(m[1]);
  //: A header the sentence names with its colon: "Server: Apache".
  for(const m of statement.matchAll(/\b([A-Z][a-z0-9]+(?:-[A-Za-z0-9]+)*)\s*:/g))
    out.push(m[1] + ":");
  //: A header the sentence names without one: "Content-Type text/html".
  for(const m of statement.matchAll(
      /\b(Strict-Transport-Security|Content-Security-Policy|Content-Type|Set-Cookie|Location|Server|Referrer-Policy|Permissions-Policy|WWW-Authenticate|X-[A-Za-z-]+|Access-Control-[A-Za-z-]+)\b/g))
    out.push(m[1] + ":");
  //: A whole URL the sentence names.
  for(const m of statement.matchAll(/https?:\/\/[^\s"'<>)\]]+/g)) out.push(m[0]);
  //: A path. This is the one that matters in a body: a recon sentence reads
  //: "further application paths: /kontakt, /sites/default/files/logo_0.png"
  //: and every one of those is a line in the HTML that nothing else finds. The
  //: leading character is captured so `and/or` in prose is not a path.
  for(const m of statement.matchAll(
      /(^|[\s"'(<[])(\/[A-Za-z0-9._~%-]+(?:\/[A-Za-z0-9._~%-]*)*)/g))
    out.push(m[2]);
  //: A sentence ends and a list separates, and neither belongs to the thing.
  return [...new Set(out.map(s => s.trim().replace(/[.,;:]+$/, "")))]
    .filter(s => s.length >= 3);
}

//: Whether one raw line carries one of them. Asked of the line before it is
//: coloured, because colouring puts tags through the middle of the words.
function struck(raw, html, marks){
  const flat = raw.toLowerCase();
  for(const m of (marks || []))
    if(flat.includes(m.toLowerCase()))
      return '<span class="hit">' + html + "</span>";
  return html;
}

//: What the door stores is `message/http`: a start line, headers, a blank line,
//: then the body. Every line is escaped, coloured for what it is, and then
//: judged against the marks -- in that order, so the judging sees words rather
//: than markup.
function httpHi(text, marks){
  const cut = text.search(/\r?\n\r?\n/);
  const head = cut < 0 ? text : text.slice(0, cut);
  const body = cut < 0 ? "" : text.slice(cut);
  const lines = head.split(/\r?\n/).map((line, i) => {
    const safe = esc(line);
    let html;
    if(i === 0){ html = '<span class="st">' + safe + "</span>"; }
    else {
      const at = safe.indexOf(":");
      html = at < 1 ? safe
        : '<span class="k">' + safe.slice(0, at) + "</span>:"
          + '<span class="s">' + safe.slice(at + 1) + "</span>";
    }
    return struck(line, html, marks);
  });
  const trimmed = body.trim();
  const paint = !trimmed ? (t => esc(t))
    : (trimmed[0] === "{" || trimmed[0] === "[") ? (t => jsonHi(esc(t)))
    : trimmed[0] === "<" ? (t => htmlHi(esc(t))) : (t => esc(t));
  const rest = body.split("\n")
    .map(line => struck(line, paint(line), marks)).join("\n");
  return lines.join("\n") + rest;
}

//: `needles` are the words this node is named by, marked inline wherever they
//: appear. `marks` are what the claim quoted, and light a whole line.
function hi(text, lang, needles, marks){
  let out = lang === "json" ? jsonHi(esc(text)) : httpHi(text, marks);
  // What the claim quoted is marked inline as well as lit as a line: a lit
  // line says which line, and the mark says which words in it were the reason.
  for(const needle of [...(needles || []), ...(marks || [])]){
    out = out.replace(new RegExp("(?![^<]*>)" + rx(esc(needle)), "gi"),
                      m => "<mark>" + m + "</mark>");
  }
  return out;
}

//: The words worth marking in the wire, taken from what this node actually is.
function terms(d){
  const out = [];
  const add = v => { if(typeof v === "string" && v.trim().length >= 3) out.push(v.trim()); };
  if(d.technology){ add(d.technology.name); add(d.technology.version); }
  if(d.domain)      add(d.domain.fqdn);
  if(d.endpoint)    add(d.endpoint.path_template);
  if(d.parameter)   add(d.parameter.name);
  if(d.service)     add(d.service.banner);
  if(d.identity)    add(d.identity.slot_name);
  if(d.application && d.application.base_url){
    try{ add(new URL(d.application.base_url).host); }catch(e){}
  }
  return [...new Set(out)];
}

function proof(rows, needles){
  if(!rows || !rows.length) return "";
  // The box is keyed by where it sits in this list, not by the digest it shows.
  // Several Observations are read out of one exchange, so the same digest is
  // the proof of all of them, and a digest used as an id makes every button on
  // the card open the first box.
  return rows.map((r, seat) => {
    const source = r.tool
      ? 'found by <em>' + esc(r.tool) + '</em>'
        + (r.tool_version ? " " + esc(r.tool_version) : "")
        + (r.tool_status ? " (" + esc(r.tool_status) + ")" : "")
      : "";
    const wire = [r.exchange && esc(r.exchange),
                  r.status && "&rarr; " + esc(r.status),
                  r.pinned_ip && "at " + esc(r.pinned_ip),
                  r.lane && "lane " + esc(r.lane)].filter(Boolean).join(" ");
    // The line under the sentence: who went and looked, what came back, who
    // read it, and where the row came from. `metadata` used to be the only
    // answer to the last of those and it answered in pointers.
    const meta = [source, wire,
      r.run && "read by " + esc(r.run) + (r.model ? " on " + esc(r.model) : ""),
      r.proposal && "proposed as " + esc(r.proposal),
      r.provenance && "provenance " + esc(r.provenance)].filter(Boolean);
    // Both halves of the exchange, always open and side by side. They were
    // behind buttons and the buttons were the wrong shape: on nearly every
    // Observation here the wire IS the finding, and a thing you have to ask
    // for twice is a thing you stop asking for.
    const panes = [["request", r.request_sha], ["response", r.response_sha]]
      .filter(pair => pair[1]);
    const shown = panes.length
      ? '<div class="wires">' + panes.map(([what, sha]) =>
          '<div class="pane"><h4>' + what + "</h4>"
          + '<pre class="code" id="w-' + seat + "-" + what + '">reading</pre></div>'
        ).join("") + "</div>"
      : "";
    return '<div class="poc">'
      + '<div class="poc-h">'
      + (r.at ? '<span class="poc-at">' + esc(pretty(r.at)) + "</span>" : "")
      + '<span class="tag">' + esc(r.kind || "") + "</span>"
      + esc(r.observation || "") + "</div>"
      + (r.statement ? '<p class="poc-s">' + esc(r.statement) + "</p>" : "")
      + (meta.length ? '<div class="poc-m">' + meta.join(" &middot; ") + "</div>" : "")
      + shown + "</div>";
  }).join("");
}

//: One read per digest for the life of the page. Several Observations come out
//: of one exchange, and the digest is what the bytes are, so the same digest is
//: the same bytes whichever hunt is on screen.
const fetched = new Map();
function bytes(sha){
  if(!fetched.has(sha)){
    fetched.set(sha, fetch("/artifact?sha=" + sha)
      .then(r => r.text()).catch(e => String(e)));
  }
  return fetched.get(sha);
}

//: Fill every pane the card just drew. The card is already on screen while
//: this runs, so a slow read shows as one pane still saying "reading" rather
//: than as a blank sheet.
async function wires(rows, needles){
  await Promise.all((rows || []).map(async (r, seat) => {
    const marks = hits(r.statement);
    for(const [what, sha] of [["request", r.request_sha],
                              ["response", r.response_sha]]){
      if(!sha) continue;
      const box = card.querySelector("#w-" + seat + "-" + what);
      if(!box) continue;
      box.innerHTML = hi(await bytes(sha), "http", needles, marks);
    }
  }));
}

function pretty(v){
  if(v === null || v === undefined) return "";
  if(typeof v === "object") return JSON.stringify(v);
  const s = String(v);
  return /^\d{4}-\d\d-\d\dT/.test(s) ? s.slice(0,19).replace("T"," ") : s;
}
function table(obj){
  const rows = Object.entries(obj)
    .filter(([k,v]) => !HIDE.has(k) && v !== null && v !== "" && !k.endsWith("_sha256"))
    .map(([k,v]) => '<tr><td class="k">'+esc(k.replace(/_/g," "))+'</td>'
                  + '<td class="v">'+esc(pretty(v))+'</td></tr>').join("");
  return rows ? "<table>"+rows+"</table>" : "";
}
function list(rows){
  return "<ul>"+rows.map(r => {
    const tag = r.polarity || r.status || r.kind || "";
    const cls = r.polarity==="supports" ? "ref" : r.polarity==="refutes" ? "refute" : "";
    const head = esc(r.label || r.observation || r.statement || r.summary || "");
    const sub = [r.role, r.property_class, r.statement, r.summary, r.url]
      .filter(x => x && x !== head).map(esc).join(" — ");
    return "<li>" + (tag ? '<span class="tag '+cls+'">'+esc(tag)+"</span>" : "")
      + head + (sub ? "<small>"+sub+"</small>" : "") + "</li>";
  }).join("")+"</ul>";
}

async function open(n){
  card.innerHTML = '<header><div><h1>'+esc(n.label||"")+'</h1>'
    + '<div class="meta">'+esc(n.kind)+(n.sub?" · "+esc(n.sub):"")
    + (n.ref?" · "+esc(n.ref):"")+'</div></div>'
    + '<button class="x">close</button></header>'
    + '<section><h3>reading</h3></section>';
  sheet.classList.add("on");
  card.querySelector(".x").onclick = shut;
  let d;
  try{ d = await (await fetch("/node?id="+encodeURIComponent(n.id))).json(); }
  catch(e){ d = {error:String(e)}; }
  const near = allLinks
    .filter(l => l.a===n.id || l.b===n.id)
    .map(l => { const o = nodes.get(l.a===n.id ? l.b : l.a);
                return o && {label:o.label, kind:o.kind, summary:l.label}; })
    .filter(Boolean);
  const needles = terms(d);
  let html = "", pocs = "";
  for(const [key, val] of Object.entries(d)){
    if(key === "error"){ html += "<section><h3>refused</h3><p>"+esc(val)+"</p></section>"; continue; }
    // Proof goes above everything else: it is the answer to the first question
    // anyone opening a node asks, which is "says who".
    if(key === "proof"){
      const body = proof(val, needles);
      if(body) pocs = "<section><h3>"+esc(TITLE.proof)+"</h3>"+body+"</section>";
      continue;
    }
    const title = TITLE[key] || key.replace(/_/g," ");
    const body = Array.isArray(val) ? list(val) : table(val);
    if(body) html += "<section><h3>"+esc(title)+"</h3>"+body+"</section>";
  }
  if(near.length) html += "<section><h3>connected to</h3>"+list(near)+"</section>";
  card.innerHTML = '<header><div><h1>'+esc(n.label||"")+'</h1>'
    + '<div class="meta">'+esc(n.kind)+(n.sub?" · "+esc(n.sub):"")
    + (n.ref?" · "+esc(n.ref):"")+'</div></div>'
    + '<button class="x">close</button></header>' + pocs + html;
  card.querySelector(".x").onclick = shut;
  wires(d.proof, needles);
}
c.addEventListener("wheel", ev => {
  ev.preventDefault();
  anchor(view.k * (ev.deltaY<0 ? 1.12 : 1/1.12), ev.clientX, ev.clientY);
}, {passive:false});

let beat = null, held = null;
async function pull(){
  clearTimeout(beat);
  try{
    // Conditional, because the whole campaign is in this body and most polls
    // ask for a picture the page is already drawing. A 304 costs no transfer
    // and no parse, and `merge` -- which rebuilds every Map, every filter and
    // the label order -- does not run at all.
    const r = await fetch("/data.json",
      {cache:"no-store", headers: held ? {"If-None-Match": held} : {}});
    if(r.status !== 304){
      const d = await r.json();
      // A refused read is drawn as nothing rather than as an empty campaign:
      // the server says `error` when it could not reach the database or the
      // Program, and merging that would be reporting silence as an answer. Its
      // tag is not held either, or one failed read would be cached as the
      // campaign until the body changed.
      if(!d.error){ merge(d); held = r.headers.get("ETag"); }
    }
  }catch(e){}
  beat = setTimeout(pull, 3000);
}
caption(); pull(); loop();
"""


# ---------------------------------------------------------------------------
# The surface, opened
# ---------------------------------------------------------------------------


@dataclass
class Graph:
    """Everything a request needs, and one Program it is all about.

    There is no Program argument on any route below. This is opened against one
    configuration, resolves that Program's slug once, and every read uses it --
    so cross-Program isolation here is not a check that could be forgotten, it
    is that there is nothing to pass. The tooling this grew out of had a picker
    that chose a database per request, which is the same authority spelled as a
    convenience.
    """

    runtime: pg.Settings
    configuration_path: Path
    slug: str
    origin: str
    artifacts: Path | None = None


def build(
    ledger: Ledger,
    runtime: pg.Settings,
    configuration_path: Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    artifacts: Path | None = None,
) -> Graph | None:
    """Open this surface against one configuration, or refuse and say why.

    The configuration is read here rather than on the first request, for the
    reason `ui.build` reads it here: a file that will not load is a surface that
    can answer nothing, and finding that out as a failed `fetch` in a browser
    console is finding it out where the reason is hardest to read.
    """
    configuration, refusals = config.load(Path(configuration_path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return None
    slug = configuration.document["program"]["name"]
    ledger.hold("configuration", f"{slug}, schema {configuration.schema_version}")
    return Graph(
        runtime=runtime,
        configuration_path=Path(configuration_path),
        slug=slug,
        origin=f"http://{host}:{port}",
        artifacts=artifacts,
    )


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

DATA = "/data.json"
NODE_ROUTE = "/node"
ARTIFACT_ROUTE = "/artifact"
SCRIPT_ROUTE = "/app.js"


def respond(graph: Graph, method: str, path: str, *, none_match: str = "") -> ui.Response:
    """One request, as a function of this surface and what was asked.

    The seam every test drives, and the reason there is no socket in any of
    them. GET and nothing else: this surface has no verb, so a POST is not a
    form it refuses, it is a method it does not have.

    `none_match` is the browser saying which body it already holds. The page
    polls `/data.json` every three seconds and the whole campaign is in it --
    roughly a megabyte on a campaign of any size -- so between two laps that
    changed nothing, an unconditional read is a megabyte transferred and a
    megabyte parsed to redraw the same picture. The read still costs the
    database what it costs; what a `304` saves is the wire and the browser.
    """
    if method != "GET":
        return ui.Response(405, "this surface only answers GET", TEXT)
    parts = urlsplit(path)
    query = parse_qs(parts.query)
    if parts.path == DATA:
        body, kind = surface(graph.runtime, graph.slug)
        # Of the bytes that would be sent, so a tag can only match a body this
        # surface would have answered with. Weak-tagged: two equal bodies are
        # equivalent for what the page does with them, which is all a browser
        # is being told here.
        tag = 'W/"' + hashlib.sha256(body).hexdigest()[:32] + '"'
        if none_match and none_match == tag:
            return ui.Response(304, "", kind, tag)
        return ui.Response(200, body.decode("utf-8", "replace"), kind, tag)
    elif parts.path == NODE_ROUTE:
        body, kind = node(graph.runtime, graph.slug, (query.get("id") or [""])[0])
    elif parts.path == ARTIFACT_ROUTE:
        body, kind = artifact(graph.artifacts, (query.get("sha") or [""])[0])
    elif parts.path == SCRIPT_ROUTE:
        return ui.Response(200, SCRIPT, CODE)
    elif parts.path == "/":
        return ui.Response(200, PAGE.replace("__PROGRAM__", escape(graph.slug, quote=True)))
    else:
        return ui.Response(404, "no such route on this surface", TEXT)
    return ui.Response(200, body.decode("utf-8", "replace"), kind)


# ---------------------------------------------------------------------------
# The socket
# ---------------------------------------------------------------------------


class Handler(http.server.BaseHTTPRequestHandler):
    """The socket, and the one question that is about the socket."""

    protocol_version = "HTTP/1.1"
    server_version = "rk-graph"
    sys_version = ""

    @property
    def graph(self) -> Graph:
        return self.server.graph

    def do_GET(self) -> None:  # noqa: N802 - the name `http.server` asks for
        self._answer("GET")

    def do_POST(self) -> None:  # noqa: N802 - the name `http.server` asks for
        # Not drained, so the connection cannot be reused: under HTTP/1.1 the
        # unread bytes would be parsed as the next request line.
        self.close_connection = True
        self._answer("POST")

    def log_message(self, format: str, *args: object) -> None:
        """Nothing, on purpose.

        A request line carries a node id, and a node is somebody's system. This
        surface's log would be a second copy of the campaign in a file nobody
        is redacting. `ui.Handler` is silent for the same reason.
        """

    def _answer(self, method: str) -> None:
        graph = self.graph
        host = self.headers.get("Host", "")
        none_match = self.headers.get("If-None-Match", "")
        if host != graph.origin.removeprefix("http://"):
            # DNS rebinding: a page on another origin can make the browser
            # resolve a name it controls to 127.0.0.1 and send this surface a
            # request that carries the operator's own loopback address. What it
            # cannot do is change the Host header, so a request naming anything
            # but the address this was bound to is not a request from anybody
            # who knows where it is.
            self._send(ui.Response(421, "this surface is not reachable under that name", TEXT))
            return
        self._send(respond(graph, method, self.path, none_match=none_match))

    def _send(self, response: ui.Response) -> None:
        body = response.encoded()
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(body)))
        if response.etag:
            self.send_header("ETag", response.etag)
        for name, value in HEADERS:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """One surface on one socket, answering a connection at a time.

    Threaded, unlike the console, and the difference is `protocol_version`
    rather than load. This speaks HTTP/1.1, so a browser keeps its connection
    open between polls -- and a serial server sitting on that open connection is
    not waiting for a request, it is waiting for the browser to go away. One
    tab would lock out every other tab, every other device, and every `curl`.

    Each thread opens its own database connection and closes it, which is what
    `ask` already did; nothing here is shared across a request but the settings
    it was opened with.
    """

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], graph: Graph) -> None:
        super().__init__(address, Handler)
        self.graph = graph


def server(graph: Graph, *, host: str, port: int) -> Server:
    return Server((host, port), graph)


def serve(
    runtime: pg.Settings,
    configuration_path: Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    artifacts: Path | None = None,
) -> Report:
    """Open this surface and answer requests until the operator stops it.

    Reports in the shape every other command reports in, because the two things
    that can go wrong before anything is ever drawn -- a configuration that will
    not load and an address already in use -- are the two an operator has to be
    told about in a terminal rather than in a browser.
    """
    ledger = Ledger()
    facts: dict[str, object] = {"program_slug": None, "address": None, "artifacts": None}
    graph = build(
        ledger, runtime, configuration_path, host=host, port=port, artifacts=artifacts
    )
    if graph is None:
        return report(COMMAND, ledger, **facts)
    facts["program_slug"] = graph.slug
    facts["artifacts"] = None if graph.artifacts is None else str(graph.artifacts)

    try:
        listening = server(graph, host=host, port=port)
    except OSError as error:
        ledger.fail(
            "address",
            f"this surface cannot listen on {host}:{port}: {error}",
            code=INVALID_CONFIGURATION,
            source="argument:--port",
        )
        return report(COMMAND, ledger, **facts)

    # The port the socket got, under the name the operator gave. `--port 0` is
    # a port the kernel picks, so the origin the Host header is checked against
    # cannot be settled before the bind.
    graph.origin = f"http://{host}:{listening.server_address[1]}"
    facts["address"] = graph.origin
    ledger.hold("address", f"the graph of {graph.slug} is at {graph.origin}")
    ledger.hold("authority", "read only, as the runtime; this surface has no verb")
    if graph.artifacts is None:
        ledger.hold("artifacts", "no artifact root: the proof pane will say so")
    with listening:
        try:
            listening.serve_forever()
        except KeyboardInterrupt:
            ledger.hold("stopped", "the operator stopped this surface")
    return report(COMMAND, ledger, **facts)
