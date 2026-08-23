# TASKS — RedKrakenV2 Hunt-Readiness

> Zielpfad: `/home/majix/redKrakenV2/docs/specs/production-harness-v2/TASKS.md`. Diese Datei koordiniert die Arbeit; maßgeblich bleiben die einzelnen Issue-Dateien und Postgres.

## Ziel und Ausgangslage

Ziel ist ein autonom einsetzbarer Web-Harness. Frühere kommerzielle Zwischenstufen werden bewusst genutzt:

1. beaufsichtigter, anonymer Read-only-Pilot;
2. kommerziell brauchbarer beaufsichtigter Hunt mit Finding und Report;
3. autonomer Hunt mit Identity-, Browser-, Impact- und Kill-chain-Unterstützung.

Baseline ist `main@402b8bd`:

- [x] `dec1e52`: Subject-Felder stehen im Schema und in der Beschreibung.
- [x] `afe8a58`: `_NAME` akzeptiert `0..2000`, damit ein einzelnes schlechtes Element durch Promotion verworfen wird und nicht die gesamte Abgabe am SDK-Schema scheitert.
- [x] `402b8bd`: Ticket 165 dokumentiert den kumulierten Prefix als falsche Agent-run-Grenze.
- [x] `tests.test_roster + tests.test_agent`: 279 grün, 8 übersprungen.
- [x] Hunt 20 beweist Promotion, Playbook-Auswahl, Test-Ausführung, Replay und eine `supported` Hypothesis: 16 Observations, keine leeren Summaries und drei `runs` Relationships.
- [x] Hunt 21 bestätigt `_NAME` live: PR3 akzeptierte vier Observations und
  verwarf zwei leere Namen einzeln, ohne die gesamte Proposal abzulehnen.
- [x] Hunt 21 führte Conclude bis zu einem candidate Finding; dabei gab es keine
  Denials für `get_validation_packet` oder `get_slate`.
- [x] Der Setup-Token-Pfad aus Ticket 146 und der terminale
  `ResultMessage`-/`success`-Fix sind implementiert, getestet und live belegt.

Aktuelle Bewertung: **Freigabe A und Freigabe B sind am 23.08.2026 erreicht.**
Begrenzte, beaufsichtigte, anonyme Read-only-Hunts sind vertretbar, und mit dem
Abschluss von Arbeitsblock 1 auch ein beaufsichtigter Hunt mit reproduzierbarem
Finding und Report. Die beiden Vorbehalte stehen bei Freigabe B.

## Arbeitsblock 0 — Stabiler Abschluss und früher Pilot

Dauer mit drei parallelen Implementierungssträngen plus Lead: **4–6 Arbeitstage**.

### Strang A — Agent boundary

Exklusiver Owner für `_launch.py`, `roster.py` und die Child-Seite des Agent-run-Vertrags:

- [x] Ticket 165: Provider-Nutzung getrennt erfassen:
  - `uncached_input_tokens`
  - `cache_creation_input_tokens`
  - `cache_read_input_tokens`
  - `output_tokens`
  - `answer_count`
  - `budget_tokens`
- [x] Budgetpolitik `cache-credit-v1` implementieren:

  ```text
  raw_input_tokens =
      uncached_input_tokens
      + cache_creation_input_tokens
      + cache_read_input_tokens

  budget_tokens =
      uncached_input_tokens
      + cache_creation_input_tokens
      + ceil(cache_read_input_tokens / 10)
      + output_tokens
  ```

  Die Formel ist eine feste Harness-Budgetpolitik, keine exakte Dollarabrechnung. Sie bildet ab, dass Cache Reads gegenüber normalem Input deutlich vergünstigt sind. [Anthropic Pricing](https://docs.anthropic.com/en/docs/about-claude/pricing)

- [x] Die Agent-run-Grenze inkrementell gegen `budget_tokens` prüfen; `max_turns` bleibt eine getrennte harte Grenze.
- [x] Das abschließende `ResultMessage` ersetzt vorhandene Rohsummen nur, wenn es eigene Usage-Daten trägt.
- [x] MCP-Server pro Role aus dem Roster bauen. Ein `web_hunter` darf `get_validation_packet` und `get_slate` weder sehen noch aufrufen. Der Pre-tool gate bleibt als zweite Verteidigung bestehen; Authority wird nicht erweitert.
- [x] `success`-Error test-first beheben:
  - erstes terminales `ResultMessage` beendet den Stream;
  - terminaler Erfolg bleibt Erfolg, selbst wenn der Fake-Stream danach eine SDK-Exception liefern würde;
  - `is_error=true` bleibt immer `error`, auch bei widersprüchlichem Subtype `success`;
  - Fehler erhalten ein redigiertes `error_detail` von höchstens 2048 Zeichen.
- [x] Den über den privaten Child-Envelope gelieferten Setup Token erst nach der Ambient- und Konfigurationsprüfung in die Umgebung des kurzlebigen Child-Prozesses einsetzen; `ClaudeAgentOptions.env` bleibt leer.
- [x] Die bestehende Auth-Korroboration muss weiterhin `apiKeySource=none` messen.

### Strang B — Supervisor und Runtime

Exklusiver Owner für Credential-Bereitstellung, Doctor und Task-Wiederholungen:

- [x] Ticket 146 durch eine Setup-Token-Datei ersetzen:
  - Standardpfad `~/.config/redkraken/claude-oauth-token`;
  - optionaler absoluter Override `RK_AGENT_OAUTH_TOKEN_FILE`;
  - Elternverzeichnis `0700`, reguläre Datei `0600`, Supervisor als Eigentümer;
  - Symlinks, mehrere Zeilen, leere Werte sowie Gruppen-/Weltzugriff verweigern.
- [x] Ein interaktives `tools/setup-agent-oauth.sh` bereitstellen:
  - exaktes `claude setup-token` ausführen;
  - Token einmal verdeckt einlesen;
  - atomar über eine temporäre `0600`-Datei installieren;
  - Doctor und einen minimalen Canary mit dem gebündelten SDK/CLI-Paar ausführen.
- [x] Ab Dateialter 330 Tage warnen und den Wizard erneut anbieten. Setup Tokens gelten laut aktueller Dokumentation ungefähr ein Jahr und werden über `CLAUDE_CODE_OAUTH_TOKEN` verwendet. [Authentication](https://code.claude.com/docs/en/authentication), [Environment variables](https://code.claude.com/docs/en/env-vars)
- [x] Keine `.credentials.json` mehr kopieren, hardlinken oder bind-mounten. Bestehende Dateien werden nach erfolgreicher Umstellung ignoriert, aber nicht automatisch gelöscht.
- [x] Das Token nur in einem privaten stdin-Envelope an den Child-Prozess übergeben; niemals in Docker-Argumenten, Logs, Datenbank, Mission packet oder Program-Verzeichnis.
- [x] Ticket 165: `attempt_profile_sha256` aus Task, Mission-packet-Digest, Role, Model, Agent-run-Grenze, Budgetpolitik und Build/SDK/CLI bilden. Der Recovery-Hinweis selbst gehört nicht in diesen Digest.
- [x] Nach dem ersten Budget-Ende mit unverändertem Profil die zweite Dispatch-Anweisung auf Abschluss reduzieren: vorhandenes Mission packet verwenden, keine erneute Exploration, nur notwendige Submission-Verben.
- [x] Nach dem zweiten Budget-Ende mit demselben Profil die Task als `abandoned` mit `budget_exhausted_twice` schließen. Ändern sich Packet, Build oder Budgetpolitik, ist wieder eine erste Wiederholung erlaubt.
- [x] Ticket 161: Budget-, Turn-, SDK- und Child-Fehler dürfen nie als `nothing_to_execute` erscheinen. Dieser Grund bleibt einer tatsächlich leeren Slate vorbehalten.
- [x] Ticket 163: Conclude erhält die kanonischen Vulnerability-Klassen und gültigen Alternativen direkt im Objective.

### Strang C — alleiniger Datenbank-Owner

Alle Migrationen und `tests/test_database.py` liegen ausschließlich hier:

- [x] `agent_runs` um Cache-Kategorien, `answer_count`, `budget_tokens`, `budget_policy`, `attempt_profile_sha256` und `error_detail` ergänzen.
- [x] Historische Zeilen mit `budget_policy=legacy-raw-v1` und `budget_tokens=input_tokens+output_tokens` rückfüllen.
- [x] Program-, Lane- und Reservation-Abrechnung für neue Agent runs ausschließlich auf `budget_tokens` umstellen; rohe Provider-Tokens bleiben als Telemetrie erhalten.
- [x] `finish_task_attempt` erweitert die Werte in derselben Transaktion, in der Agent run, Task und Reservation geschlossen werden. Event- und Actor-Invarianten aus ADR 0001/0002 bleiben erhalten.
- [x] Die Regel für zwei gleiche Budget-Enden in der Datenbank erzwingen, damit kein alternativer Python-Pfad eine dritte unveränderte Dispatch erzeugen kann.
- [x] Ticket 142 positiv beweisen: ein gültiger vorgeschlagener Task wird geöffnet; ein ungültiger wird als einzelnes Drop-Ergebnis erklärt.
- [x] Tickets 148/163: Finding-Refusals nennen die wirkliche Ursache und gültige Vocabulary-Werte.
- [x] Nur wenn diese positiven Tests rot sind, den kleinsten dafür nötigen Writer-/Constraint-Fix implementieren.

### Naht zwischen den Strängen

Vom Lead vor der Parallelisierung festgelegt, weil drei Stränge ohne festes
Wortlaut-Format an der Integration auseinanderlaufen. Die Schreibweise ist
verbindlich; A, B und C bauen gegen genau diese Namen.

**Datei-Ownership.** A: `_launch.py`, `roster.py`, `tests/test_agent.py`,
`tests/test_roster.py`. B: `agent.py`, `isolation.py`, `doctor.py`,
`execution.py`, `program.py`, `tools/setup-agent-oauth.sh`,
`tests/test_isolation.py`, `tests/test_doctor.py`, `tests/test_execution.py`,
`tests/test_program.py`. C: `src/redkraken/migrations/*.sql` und
`tests/test_database.py`, exklusiv. Lead: `docs/**`, `tests/fixtures.py`, Ledger.
`agent.py` war in der ursprünglichen Fassung keinem Strang zugewiesen und liegt
bei B, weil dort die Job-Zeile gebaut und das Kindergebnis eingelesen wird.

**Child-Job-Envelope.** B legt den Setup Token in die eine JSON-Zeile, die das
Kind auf stdin liest (`agent.py:692` schreibt, `_launch.py:2159` liest), unter
dem Schlüssel `oauth_token`. A nimmt ihn sofort aus der Mapping heraus, bevor
irgendetwas die Job-Zeile liest, speichert, ausgibt oder protokolliert, und
setzt `CLAUDE_CODE_OAUTH_TOKEN` erst nach der Ambient- und
Konfigurationsprüfung. `ClaudeAgentOptions.env` bleibt leer.

**Child-Run-Report.** A ergänzt das zurückgegebene Dict um genau diese
Schlüssel; B trägt sie durch `AgentRunResult` und `execution.py`; C speichert
sie:

```text
uncached_input_tokens        int
cache_creation_input_tokens  int
cache_read_input_tokens      int
answer_count                 int
budget_tokens                int
budget_policy                str   = "cache-credit-v1"
error_detail                 str | None   (redigiert, höchstens 2048 Zeichen)
```

`input_tokens` (rohe Providersumme, Telemetrie) und `output_tokens` behalten
ihre heutige Bedeutung und bleiben erhalten.

**Datenbankseite.** `agent_runs` erhält `uncached_input_tokens`,
`cache_creation_input_tokens`, `cache_read_input_tokens`, `answer_count`,
`budget_tokens`, `budget_policy`, `attempt_profile_sha256` und `error_detail`.
`finish_task_attempt` erhält passende `p_<name>`-Parameter, alle `DEFAULT NULL`
und als `coalesce(p_x, x)` angewandt. `DEFAULT NULL` ist der Grund, warum C
allein vor A und B integriert werden kann: ein unveränderter Aufrufer läuft
weiter.

**Basen und Diffs.** Implementierungs- und Review-Diff ist `801c491..HEAD`.
Der Release-Diff für die Provenienz ist
`hunt-readiness-baseline-402b8bd..HEAD`. `main` bleibt bis zum abschließenden
Fast-forward auf `801c491` eingefroren. Kein Remote-Push.

**Gates an der Baseline `801c491`**, vom Lead vor der Parallelisierung gemessen,
alle vier grün: `check_audit` rc=0; `check_wiring` rc=0 (64 Register-Zeilen);
`check_baseline` rc=0 (classifications=10, regressions=7, adapters=10,
artifacts=223); `check_coverage` rc=0 (census 223 reconciled).

**CodeGraph.** Das MCP-Tool steht in dieser Sitzung nicht zur Verfügung. Die
CLI ist der Weg: `codegraph explore "<Symbole>" -p <eigener Worktree>`. Jeder
der vier Worktrees hat seit dem 23.08.2026 einen eigenen Index, weil die
Branches während der Implementierung auseinanderlaufen. `.codegraph/` steht in
`.gitignore` und wird nie committet.

### Lead — Integration und Live-Abnahme

- [x] Wegen `main...origin/main [ahead 67]` vor Parallelisierung einen lokalen Tag und ein Git-Bundle von `402b8bd` außerhalb des Repos anlegen. Kein Remote-Push ohne gesonderte Freigabe.
- [x] Drei Worktrees von derselben Baseline eröffnen; keine parallelen direkten Änderungen auf `main`.
- [x] Ticket 149: Doctor prüft vor jedem Agent run, dass Runtime und Door dasselbe Program und dieselbe Datenbank sehen; Tool-run- und Child-Fehler müssen ein nichtleeres Detail tragen.
- [x] Strang C zuerst in den Integrationszweig übernehmen, danach A und B; Konflikte werden nur durch den Lead aufgelöst.
- [x] Einen frischen `rk2hunt21`-Canary anlegen. `rk2hunt17` bis `rk2hunt20` bleiben unverändert als Evidenz erhalten.
- [x] `_NAME` live bestätigen: eine lange oder leere Einzelangabe darf nicht die gesamte Abgabe verweigern; fehlerhafte Elemente werden einzeln verworfen und erklärt.
- [x] Einen Conclude-Agent-run bis zu einem Finding führen, ohne Denials für `get_validation_packet` oder `get_slate`.
- [x] Zehn aufeinanderfolgende Agent-Starts über mindestens einen Supervisor-Neustart durchführen, ohne Credential-Kopie und ohne Secret-Leak.

**Freigabe A — erreicht am 23.08.2026:** Begrenzte, beaufsichtigte, anonyme
Read-only-Hunts sind vertretbar. Reports werden noch durch einen Menschen
fertiggestellt. Abnahmebasis ist `rk2hunt21` auf dem zusammengeführten lokalen
`main`; es erfolgte kein Remote-Push.

## Arbeitsblock 1 — Finding, Impact und Report

Dauer: weitere **4–6 Arbeitstage**.

- [x] Ticket 104: `park_for_human` implementieren. Eine Task wird `parked`, verbraucht keinen Versuch, gibt Leases frei und wird nur durch einen Operator wieder freigegeben oder superseded.
- [x] Ticket 103 vollständig, nicht als verkürzten Report-Slice implementieren:
  - angebotene Contracts: `open_impact_task`, `state_severity`, `compose_finding_report`;
  - Runtime-Verben: `apply_computed_cvss`, `issue_pivot_stamp`, `build_kill_chain`;
  - Operator-Read: `read_kill_chain`;
  - `compose_finding_report` darf nicht mehr über eine zu breite `PUBLIC`-Berechtigung erreichbar sein.
- [x] Ticket 159: Host-Entities sowie `resolves_to`- und `serves`-Relationships aus Runtime-Evidenz ableiten.
- [x] Einen synthetischen vertikalen Lauf beweisen:

  ```text
  Recon
  → Hunt/Playbook
  → Test
  → Replay
  → supported Hypothesis
  → candidate/validated Finding
  → Impact demonstration
  → Severity basis/CVSS
  → Pivot stamp
  → Kill chain
  → Report
  ```

- [x] Alle state-changing oder genehmigungspflichtigen Pfade ohne Standing grant müssen parken; verbotene Pfade dürfen nicht angeboten werden.

**Freigabe B — erreicht am 23.08.2026:** Ein kommerziell brauchbarer
beaufsichtigter Web-Hunt mit reproduzierbarem Finding und Report ist vertretbar.
Abnahmebasis ist `77bcfecd` auf dem lokalen Integrationszweig; es erfolgte kein
Remote-Push. Der Termin **02.09.–08.09.2026** war die Schätzung bei Start am
24.08. und ist damit gegenstandslos.

Gemessen am Tag der Freigabe:

- `tests.test_database`: 1462 Tests, 1 Fehler, 69 übersprungen.
- `tests.test_vertical`: 3 Tests, OK. Das ist der synthetische vertikale Lauf.
- `tests.test_roster` 115 OK; `tests.test_execution` 192 OK; `tests.test_wiring`
  20 OK; `tests.test_agent` 190 OK bei 37 übersprungenen; `tests.test_cli`
  zusammen mit `tests.test_reporting` 194 OK.
- Die vier Repository-Gates enden alle mit rc=0: `tools/check_audit.py`,
  `tools/check_wiring.py`, `tools/check_baseline.py`, `tools/check_coverage.py`.
- `rk db verify`: **96 Assertions, 0 Verletzungen**. `standing_checks` hält
  **66** Zeilen, zwei davon neu: `agent_asks` aus Ticket 104 und
  `receipt_topology` aus Ticket 159.

Zwei Vorbehalte, ausdrücklich und nicht stillschweigend:

- **(a) Der vertikale Lauf hat genau eine arrangierte Zeile.**
  `tests/test_vertical.py` schreibt in `the_control_the_playbook_asks_for()`
  die eine `credential_effect`-Observation samt `control`-Evidenzkante, die
  `playbooks/object-ownership/playbook.md` für `supported` verlangt, als Owner
  und nicht über ein Verb. Sie ist im echten Receipt der Recon-Runde verankert,
  aber sie ist nicht verdient: `close_test_replay` kann ausschließlich
  `response_invariant` und `response_differential` schreiben, und der
  Proposal-Pfad verweigert eine Evidenzkante, sobald der Claim über `proposed`
  hinaus ist. Alles unterhalb dieser Zeile -- Test, Replay, `supported`
  Hypothesis, Finding, Impact, Severity, Pivot stamp, Kill chain, Report -- ist
  verdient. Ticket 166 besitzt die Lücke und misst sie: 33 der 50 Playbooks
  verlangen eine Observation-Art, die kein Runtime-Writer erzeugen kann.
- **(b) Der eine rote Test ist lastabhängig.**
  `SurfaceBenchmarkTest.test_slate_computation_is_within_budget` ist der
  dokumentierte Last-Flake aus `docs/agents/testing.md`, Abschnitt "Known
  failures that are not yours". Er ist nicht durch diesen Arbeitsblock
  verursacht und wird hier nicht als grün ausgegeben.

## Arbeitsblock 2 — Identity und authentifizierte Hunts

Dauer: weitere **4–6 Arbeitstage**.

- [ ] Ticket 131 zuerst:
  - jede Task erhält genau eine `selected_identity_entity_id` innerhalb desselben Program;
  - auch Anonymous wird ausdrücklich gewählt;
  - A/B-Prüfungen werden als zwei Tasks über dieselbe Hypothesis abgebildet;
  - die Task-Identity-Projektion enthält genau die gewählte Identity.
- [ ] Ticket 133 danach: `multiple_test_identities` bedeutet zwei verschiedene nicht-anonyme Identities; fehlende Voraussetzungen müssen als typisierte Gründe sichtbar bleiben.
- [ ] Ticket 136 nach dem Kern von 131: jede Door-Antwort nennt die Scope-Klasse und die tatsächlich verwendete Identity.
- [ ] Ticket 119: den vom SDK gemeldeten Session-Identifier nach Init über den vorhandenen Supervisor-Channel an den Agent run binden.
- [ ] Ticket 120 bleibt außerhalb dieses Meilensteins; Hook-Receipts sind für den ersten authentifizierten Produktionslauf nicht erforderlich.

## Arbeitsblock 3 — Browser und fünf High-Yield-Playbooks

Code-Dauer: **5–8 Arbeitstage**, anschließend **2–6 Kalendertage** Grading.

- [ ] Ticket 99: die bestehende proxied `headless-shell` Browser mission über einen geschlossenen Contract anbieten.
- [ ] Ausschließlich die vorhandenen registrierten Aktionen nutzen:

  ```text
  navigate, wait_for, fill, inject, click,
  assert_text, assert_absent, probe, capture_dom, screenshot
  ```

- [ ] Kein Carbonyl, kein agent-browser, kein persistenter Browser-Daemon und kein beliebiges JavaScript; ADR 0004/0005 bleiben unverändert.
- [ ] Ticket 101 nur für die fünf benötigten Capability-Zeilen implementieren.
- [ ] Ticket 109 auf paarweise Vergleiche festlegen.
- [ ] Ticket 84 nur für diese fünf High-Yield-Paare durchführen:
  1. `attack-surface` ↔ `artifact-exposure-pair`
  2. `object-ownership` ↔ `object-ownership-pair`
  3. `browser-script` ↔ `markup-pair`
  4. `cookies` ↔ `cookie-scope-pair`
  5. `payment-workflows` ↔ `quantity-or-price-pair`
- [ ] Vor dem Grading Code-, Runtime-, SDK/CLI-, Corpus- und Fixture-Digests einfrieren.
- [ ] Zuerst 30 Canary-Agent-runs ausführen: fünf Playbooks × zwei Fixture-Hälften × drei Wiederholungen.
- [ ] Nur wenn alle Canaries grün sind, dieselbe Grading-Datenbank für die verbleibenden 1620 Agent runs weiterverwenden; maximal drei parallele Grading-Lanes.
- [ ] Bei einem roten Canary die Messung als ungültig markieren, korrigieren und in einer neuen Datenbank neu beginnen. Keine Datenbank automatisch löschen.
- [ ] Das vollständige Grading umfasst 1650 Agent runs und reserviert beim heutigen 200k-Envelope rund 330 Millionen Budgeteinheiten.

**Freigabe C:** Autonomer Web-Harness nach vollständigem Grading. Code-complete voraussichtlich **15.09.–28.09.2026**, finales Live-/Grading-Gate etwa **17.09.–04.10.2026**.

## Test- und Integrationsregeln

- [x] Ponytail für jede Code-Implementierung verwenden: kleinster Root-cause-Diff, bestehende Contracts wiederverwenden, keine unnötige Abstraktion oder Dependency.
- [x] CodeGraph vor jeder Änderung mit `explore`/`callers` für Ownership und Blast radius verwenden. `affected` ist nur Hinweis und wird wegen beobachteter False Negatives mit `git grep`, Ticket-Citations und Tests gegengeprüft. CodeGraph bleibt reine Code-Intelligenz gemäß ADR 0006.
- [x] Den `diagnosing-bugs`-Ablauf für Ticket 146, 165 und den Success-Error verwenden: reproduzierbarer roter Test, kleinster Fix, grüner Test, anschließend Live-Beweis.
- [x] Den Engineering-Wizard ausschließlich für den menschlichen Einmalschritt `claude setup-token` verwenden.
- [x] Während der Arbeit nur die berührten Testmodule ausführen.
- [x] Vor Rückgabe jedes Tickets die vier Repository-Gates ausführen:
  - `check_audit.py`
  - `check_wiring.py`
  - `check_baseline.py`
  - `check_coverage.py`
- [x] Jede Datenbankausführung enthält `CleanCreationTest`, läuft unter `flock -w 3600 /tmp/rk2-db.lock` und niemals parallel zu einem Live-Hunt.
- [x] Die vollständige Suite nur nach breiter Migration, vor Live-Canary und vor Release Candidate ausführen.
- [x] Nach jedem Integrationsblock `git diff --check`, die aktuell 96 Integritätsprüfungen -- die Assertion-Zahl, die `rk db verify` meldet -- und den jeweiligen vertikalen Smoke ausführen.

Besonders erforderliche Regressionen:

- [x] Zehn Turns mit etwa 40k gecachtem Prefix bleiben bei `cache-credit-v1` unter einer 250k-Agent-run-Grenze.
- [x] Gleich große ungecachete Turns überschreiten dieselbe Grenze weiterhin.
- [x] Rohdaten, `answer_count`, Budgeteinheiten und Reservation-Abrechnung stimmen exakt überein.
- [x] Ein `web_hunter` sieht keine fremden MCP-Contracts; ein künstlich injizierter Aufruf wird weiterhin vom Pre-tool gate verweigert.
- [x] Terminaler Erfolg, terminaler Fehler und fehlendes ResultMessage erzeugen drei verschiedene, dauerhafte Ergebnisse.
- [x] Zwei identische Budget-Enden erzeugen keine dritte Dispatch; ein geändertes Attempt-Profil erlaubt wieder einen ersten Versuch.
- [x] Ein Setup-Token-Sentinel erscheint weder in stdout/stderr noch in Program-Daten, Datenbank, Mission packet oder Agent-visible Artifact.
- [x] Yekta-Canary bleibt innerhalb der aktuellen Scope- und Risikoregeln.

## Output-Sicherung und Tracker

- [x] Ergebnisse knapp und technisch vollständig im vorgesehenen Caveman-Format sichern.
- [x] Der Lead führt append-only:

  `/home/majix/engagements/yekta-first-hunt-2026-08-22/out/readiness-ledger.ndjson`

- [x] Eine Zeile pro Merge oder Live-Gate mit:
  - Zeit
  - Arbeitsblock
  - Commit
  - Owner
  - Tests/Gates
  - Live-Beweis
  - Agent-run-/Token-Metriken
  - verbleibende Blocker
- [x] Keine Secrets, rohe Zielantworten oder vollständigen Modelltranskripte in diesem Ledger speichern.
- [x] `TASKS.md` und der Ledger sind abgeleitete Koordinationsansichten. Issue-Status, Program-Zustand und Events bleiben maßgeblich.
- [x] Vor Arbeit an einem Issue dessen `Status:` gemäß lokalem Tracker setzen; erst nach Implementierung, Tests, Review und Commit auf `resolved`.
- [x] Die vorhandene ungetrackte Research-Datei nicht überschreiben oder versehentlich committen.

## Bewusst zurückgestellt

Nicht erforderlich für den ersten autonomen Web-Meilenstein:

- Ticket 105
- Ticket 120
- Tickets 122 und 124
- Rest von Ticket 129
- Tickets 134, 135 und 137
- Tickets 145, 160 und 162
- vollständiges Ticket 101 und vollständiges Ticket 84
- Ticket 65 als gesamter Release-Proof

Ticket 132 bleibt ausdrücklich die letzte Migration nach allen übrigen schemaändernden Arbeiten.

## Annahmen

- Drei Implementierungsstränge und ein Lead stehen durchgehend zur Verfügung.
- Live-Canaries sind nur innerhalb der bestehenden Yekta-Scope- und Risikoregeln autorisiert.
- Aktuell gebündelt sind SDK `0.2.132` und CLI `2.1.224`. Falls dieses Paar den Setup Token nicht mit `apiKeySource=none` bestätigt, wird ausschließlich das erste gemeinsam gepinnte Paar übernommen, das sowohl die bestehende Auth-Messung als auch den Setup-Token-Canary besteht; es gibt keinen Rückfall auf `.credentials.json`.
- Die Zeitangaben gelten ohne neuen externen SDK-, Infrastruktur- oder Scope-Blocker.
