# redKrakenV2 und Yekta-Live-Engagement: aktueller Stand

Stand: 2026-08-23 09:39 UTC. Recherche read-only gegen `majix.server`.
Keine Produktivänderung, kein Datenbanktest, kein weiterer Hunt gestartet.

## Kurzfazit

redKrakenV2 hat wesentliche Produktionspfade und maschinenlesbare Gates. Es ist
nicht releasebereit: 33 von 164 Production-Harness-Tickets sind offen, Ticket 65
ist unbewiesen, und die grünen Wiring-Gates erlauben ausdrücklich inventarisierte
Schulden. Das Yekta-Engagement hat über die Datenbanken `rk2hunt` bis
`rk2hunt20` kein Finding erzeugt.

Der jüngste fachliche Fehler bleibt: Nach Ticket 164 ließen Recon-Kinder jedes
Subject an Observations und Folgeelementen weg. H18 und H19 verloren dadurch die
gesamte epistemische Ausgabe. Ein uncommitteter WIP-Fix liegt wieder im
Arbeitsbaum. H20 prüfte ihn nicht: drei Versuche, einschließlich sauberem
`HEAD` als Kontrolle, starben vorher am separaten Agent-/SDK-Fehler
`Exception: Claude Code returned an error result: success`.

## Quellen und Snapshot-Grenze

Primärquellen:

- Repo: `/home/majix/redKrakenV2`
- Production-Spec: `docs/specs/production-harness-v2/spec.md`
- Tickets: `docs/specs/production-harness-v2/issues/*.md`
- Tracker-Konvention: `docs/agents/issue-tracker.md`
- Testkonvention: `docs/agents/testing.md`
- Auditdaten: `baseline/spec-verification.tsv`, `baseline/status.json`,
  `tools/check_audit.py`, `tools/check_wiring.py`, `tools/check_baseline.py`,
  `tools/check_coverage.py`
- Engagement: `/home/majix/engagements/yekta-first-hunt-2026-08-22`
- Engagement-Handoff: `HANDOFF-2026-08-23.md`
- Frühe Run-Analyse: `notes/2026-08-22-run-analysis.md`
- Laufberichte: `out/rk2hunt17-*.json`, `out/h18-*.json`, `out/h19-*.json`,
  `out/h20-01.json`, `out/h20-retry.json`, `out/h20-ctl.json`
- Kanonischer Engagement-Zustand: PostgreSQL-Datenbanken `rk2hunt17` bis
  `rk2hunt20`, ausschließlich in read-only Transaktionen abgefragt

Zeitgleiche Claude-Remote-Control-Arbeit änderte den Server während der
Recherche. Dieser Bericht nennt deshalb Commit, Stash und UTC-Zeit. Spätere
Änderungen sind nicht eingeschlossen.

## Repo-Zustand

- `main`/`HEAD`: `143b41276cd6498678abc259f6da2f7bf8380203`
- Commit: `FEAT: a subject that is an application has facts, and a near miss is readable`
- Commitzeit: 2026-08-23 00:32:45 UTC
- `main` liegt 64 Commits vor `origin/main`; `origin/main` ist `1e39069`.
- Arbeitsbaum beim finalen Snapshot: geändert in `src/redkraken/_launch.py` und
  `src/redkraken/roster.py`.
- Stash-Liste beim finalen Snapshot: leer. Der WIP wurde für den Kontrolllauf
  temporär als `t164-fix-wip` gestasht und danach wiederhergestellt.
- Laufender Dienst: `rk2hunt-door`; kein aktiver `h20`-Hunt-Prozess beim
  finalen Snapshot.

Während der Recherche enthielt der temporär gestashte WIP Änderungen an
`src/redkraken/_launch.py` und `src/redkraken/roster.py`. `_launch.py` benannte
Subject-, Summary- und Relationship-Felder ausdrücklich. `roster.py` machte
dieselben Namen zu echten `_ELEMENTS`-Schemaargumenten, einschließlich Bounds.
Der H20-Kontrolllauf lief auf sauberem `HEAD` und scheiterte gleich; dieser
SDK-Fehler ist daher nicht durch den WIP-Diff erklärt.

## Spec und Tickets

Die Primär-Spec umfasst laut aktuellem Audit:

- 230 User Stories
- 19 Implementation Decisions
- 24 Testing Decisions
- 9 Out-of-Scope Constraints
- 6 Release Conditions
- 7 registrierte Prototype Regressions

Das sind 295 auditierte Requirements. Der Tracker hat inzwischen 164
Production-Harness-Tickets:

| Status | Anzahl |
| --- | ---: |
| `resolved` | 131 |
| `ready-for-agent` | 25 |
| `ready-for-human` | 2 |
| `needs-triage` | 6 |
| offen gesamt | 33 |

Zentrale offene Tickets:

- 65: erster Hunt-Release-Candidate; `ready-for-agent`
- 84: Playbook-Corpus-Grading; `ready-for-human`; Ticket kalkuliert 16.500
  Agent Runs für Vollgrading und empfiehlt einen autorisierten Slice
- 99 bis 101: Browser-Capability, fehlendes Vokabular, Corpus-Rewrite
- 103: Downstream-Verben nach Finding ohne Caller
- 131 bis 137: Identity/Egress/Migration/Scope/pgvector, teils Triage
- 142: Suggested Task wird von nichts gelesen; `ready-for-human`
- 159 bis 163: Lücken aus dem ersten echten Kampagnenpfad

`docs/specs/production-harness-v2/ticket-coverage.md` ist kein aktueller
Tracker-Snapshot: es nennt noch 93 Tickets und nur 65/84 als offen.
`.scratch/TODO.md` ist vom 2026-08-21. Für Statuszahlen gelten die 164
Ticketheader und `check_audit.py`.

## Gates gegen tatsächliche Implementierung

Folgende Repo-Gates liefen auf `143b412` read-only und endeten jeweils mit rc 0:

```text
check_audit:    tickets 164, resolved 131, verification 216,
                tests 211, gates 5, owed 1
check_wiring:   register 64 rows/findings, 11 Tickets
check_baseline: classifications 10, regressions 7, adapters 10,
                artifacts 223 frozen
check_coverage: in-scope Playbooks 49, loadable 49, frozen 49,
                catalogue 50, skills 6, references 84
```

`check_wiring` ist grün, weil offene Verdrahtung einer registrierten Schuld und
einem offenen Ticket zugeordnet ist. Es meldet weiterhin:

```text
W1 contracts served       3 owed
W3 verbs called          18 owed
W4 read surface          27 owed
W5 results resolvable     1 owed
W6 producers              3 owed
W7 guards satisfiable     1 owed
W8 write targets          1 owed
W9 vocabulary             9 owed
W10 corpus instructions   1 owed
```

Grün bedeutet hier konsistent inventarisiert, nicht vollständig umgesetzt oder
releasefähig.

Substanzielle aktuelle Pfade sind vorhanden:

- `src/redkraken/program.py:178`: create/resume und Ausführung über einen
  Program-Seam
- `src/redkraken/execution.py:1740`: Task-Ausführung, Playbook-Auswahl, Packet,
  Child, Promotion
- `src/redkraken/execution.py:2158`: Playbook-Auswahl
- `src/redkraken/execution.py:2425`: Egress-Autorisierung; Identity-Slot bleibt
  leer
- `src/redkraken/execution.py:2726`: Proposal-Promotion
- `src/redkraken/agent.py:660`: isolierter Agent-Launch
- `src/redkraken/agent.py:1280`: Supervisor-Dispatch unter anderem für Finding-
  und Test-Proposals
- `src/redkraken/replay.py:101`: Replay-Pfad

Relevante Commits:

- `6d70106`: Claim wird Test; Test wird ausgeführt; Suggested Task wird gelesen
- `72c7681`: Supported Claim öffnet Finding-Arbeit; unmögliche Tasks enden
- `143b412`: Application-Facts und Playbook-Near-Misses, Ticket 164

CodeGraph erkundete diese Pfade. Remote-Index war aktuell: 224 Dateien, 9.702
Nodes, 29.165 Edges. Der separate Engagement-CodeGraph-Index enthielt 0 Dateien
und war für Engagement-Zustand ungeeignet; dort galten Dateien und DB als
Primärquellen.

## Yekta-Engagement: Autorität und Grenzen

`README.md` und `program-yekta-it.toml` halten die Autorisierung fest: alle
Tests außer Denial of Service und Login-Bruteforce. Der Live-Program-Scope
enthält `yekta-it.de` und `www.yekta-it.de`, HTTPS Port 443. Budget:

- 1.200 Campaign Requests
- 40 Requests pro Run
- 60 Requests pro 60 Sekunden
- Concurrency 2
- `availability_impact = false`
- `credential_use = false`

Keine Secrets wurden gelesen oder in diesen Bericht kopiert. Keine
Datenbanktests liefen: `docs/agents/testing.md` und Engagement-`README.md`
warnen, dass `tests/test_database.py` clusterweite Rollenpasswörter rotiert und
einen Live-Hunt brechen kann.

## Engagement-Ergebnis bis H17

Frühe sechs `rk run`-Aufrufe erreichten laut
`notes/2026-08-22-run-analysis.md` dreimal den Zielpfad, alle innerhalb Scope:
zwei HTTP-Exchanges plus Transportmessung. Ein erstes Tokenlimit von 40.000
schnitt Orchestrator und Recon ab; 250.000 ließ den erfolgreichen Pair-Run
durchlaufen.

Kanonischer DB-Snapshot von `rk2hunt17`:

| Objekt | Anzahl |
| --- | ---: |
| Tasks | 9 |
| Agent Runs | 29 |
| Tool Runs | 16 |
| Receipts | 18 |
| Entities | 14 |
| Relationships | 6, davon 5 `runs`-Edges |
| Observations | 29 |
| Hypotheses | 2, beide `supported` |
| Tests | 3 |
| Findings | 0 |
| Playbook Selections | 0 |
| Proposal Drops | 39 |

Damit existieren Claim-, Test- und Task-Pfade im Live-Lauf. Finding-,
Validation-, Report- und Chain-Ende wurden nicht erreicht. Zwei Conclude-Tasks
endeten `abandoned`; Ticket 163 dokumentiert unter anderem, dass der Child eine
37-Wörter-Vulnerability-Class-Vocabulary erraten musste und seine drei
Refusals auf Synonyme verbrauchte.

## Regression H18/H19 nach Ticket 164

`HANDOFF-2026-08-23.md`, Proposal-Payloads und DB stimmen überein:

| DB | Agent Runs | Observations | Relationships | Hypotheses | Findings | Selections | Drops |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `rk2hunt17` | 29 | 29 | 6 | 2 | 0 | 0 | 39 |
| `rk2hunt18` | 4 | 0 | 0 | 0 | 0 | 0 | 26 |
| `rk2hunt19` | 4 | 0 | 0 | 0 | 0 | 0 | 25 |

H17 trug an jeder Observation `subject_label` oder `subject_ref`; H18/H19 an
keiner. H19-Drops:

```text
observations/no_subject       11
evidence/no_subject            2
evidence/no_such_label         3
hypotheses/no_subject          1
hypotheses/no_support          2
relationships/invalid_direction 1
suggested_tasks/no_subject     2
suggested_tasks/no_address     2
suggested_tasks/unopenable_kind 1
```

Beide Recon-Tasks wurden trotzdem `done`; danach meldete der Lauf
`nothing_to_execute`. H19 hatte zwei Applications, zwei Endpoints und fünf
Technologies, aber keine Observation, Relationship, Hypothesis, Finding oder
Playbook Selection.

Der Handoff plante als nächsten Schritt, H19-Child-Transcripts zu lesen. Die
durablen Primärquellen enthalten sie nicht: `agent_runs.result` ist in H19 für
alle vier Runs NULL, und `agent-home` enthält nur die Credentials-Datei. Die
Proposal-Payloads bewahren den abgegebenen Mission Result, nicht den Dialog oder
frühere Tool-Versuche. Aus dem erhaltenen Zustand lässt sich deshalb belegen,
dass der Child ohne Subjects abgab; nicht, ob er vorher einen Subject-Versuch
unternahm und lokal abgewiesen wurde.

## H20: separater Launch-/SDK-Fehler

H20 lief dreimal gegen dieselbe frische Datenbank:

- `out/h20-01.json`: WIP aktiv
- `out/h20-retry.json`: WIP aktiv
- `out/h20-ctl.json`: sauberer `HEAD` nach `git stash push t164-fix-wip`

Alle drei endeten `ok=false`, Exit 9, `stop_reason=refused`. Je Versuch
aborted ein Orchestrator und ein Recon-Run. Entscheidende Exception:

```text
Exception: Claude Code returned an error result: success
```

Finaler `rk2hunt20`-DB-Snapshot:

- 2 Tasks: 1 `abandoned`, 1 `pending`
- 6 Agent Runs: 3 Orchestrator, 3 Recon, alle `aborted`
- 0 Receipts
- 0 Proposals
- 0 Observations
- 0 Findings
- 0 Playbook Selections

H20 erreichte das Ziel nicht und sagt nichts über Wirksamkeit des Subject-WIP-
Fixes. Dass die saubere Kontrolle identisch stirbt, trennt den Fehler vom
gestashten Diff.

## Testlage und nächste belastbare Frage

Der Engagement-Handoff nennt vier grüne Gates sowie einzeln grüne Module
`test_agent`, `test_roster`, `test_execution`, `test_playbook`. Ein gemeinsamer
Prozess dieser drei ersten Module erzeugte 13 order-dependent Fehler auch ohne
Ticket-164-Diff; nicht untersucht und als bestehende Testverschmutzung
behandelt.

Aktueller Erkenntnisrand:

1. Agent-/SDK-Refusal von H20 klären, bevor der Subject-Fix live messbar ist.
2. Danach frische DB mit gestashtem strukturiertem Schema-WIP gegen sauberen
   HEAD vergleichen.
3. Erfolgskriterium: Observations/Relationships behalten Subjects und
   Relationship-Enden; Promotion erzeugt epistemische Rows und Folge-Tasks.
4. Erst danach Ticket 163/Finding-Vocabulary und Playbook-Auswahl weiter
   verfolgen.

Keine dieser Aktionen wurde in dieser Recherche ausgeführt. Ponytail blieb
unbenutzt, weil keine Implementierung autorisiert war. Caveman wurde für
kompakte, dauerhaft gespeicherte Ausgabe verwendet.
