# 149 — A tool run that errors records no reason

**What to build:** The part of the Tool run close that writes why a run reached
`status = 'error'`, and the preflight that refuses a run whose door serves a
different database than the runtime does.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** `rk2hunt8`, 2026-08-22. Three Tool
      runs against `https://www.yekta-it.de`, every one of them:

      ```
      label|status|decision|started|finished
      TR1  |error |allow   |t      |t
      TR2  |error |allow   |t      |t
      TR3  |error |allow   |t      |t
      ```

      and every one of them with nothing said about it:

      ```
      label|exit_code|detail|hook|url
      TR1  |         |      |    |https://www.yekta-it.de
      TR2  |         |      |    |https://www.yekta-it.de
      TR3  |         |      |    |https://www.yekta-it.de
      ```

      `exit_code`, `exit_detail` and `hook_error` are all NULL. The run JSON
      reported `"tool_run": {"decision": "allow"}` and `"receipt": null`, and
      the recon child, having nothing to read, filed nothing: `promotion:
      rejected`, zero Observations, zero refusals, 864 output tokens. Task `T1`
      stayed `pending` and burned an attempt per lap.

      The cause was not in the database at all. It was in the door's log:

      ```
      no blocked receipt for 01a02a32-94eb-73ba-8a3a-02959d790184: 23503:
      insert or update on table "label_counters" violates foreign key constraint
      "label_counters_program_id_fkey" | Key (program_id)=(01a02a32-...) is not
      present in table "programs".
      ```

      The door was still the container started for the previous engagement
      database. `RK_PROXY_DATABASE_URL` is read once, when the container starts,
      and the door outlives the command that started it by design -- ticket 82's
      whole point. A run against a second database therefore reaches a door that
      cannot see its Program, and the door cannot even file the blocked Receipt
      that would say so, because the label counter it needs is keyed on a
      Program row that is not there.

- [x] **The error carries its reason.** Whatever closed TR1 knew something went
      wrong, since it wrote `error`. That knowledge must reach `exit_detail`.
      A status with no reason costs the next reader the whole investigation.

- [x] **The preflight asks the door which database it serves.** `rk doctor` and
      the run's own boundary checks already ask the door seven questions; this
      is the eighth, and it is the one that would have turned three wasted
      attempts into one refusal naming the mismatch.

- [x] **Checked by something that would go red.** A test that a Tool run closed
      as `error` has a non-NULL `exit_detail`, and a doctor test that a door
      serving another database is refused.

## Why

Two defects, one incident, and they compound: the first made the failure silent
and the second made it invisible. Found only by reading `docker logs` on the
door, which is not a step any operator procedure names.

The door binding one database for its lifetime is correct and is ticket 82's
design. What is missing is anything that notices when the runtime has moved on.

## Resolution, 2026-08-23

The Door now announces the exact PostgreSQL database identity (database name,
OID and postmaster start), and both Doctor and the run preflight compare it with
the Runtime before orchestration and again before a worker starts. A mismatch is
a configuration refusal before an attempt is spent. Online Tool runs closed as
`error` receive a bounded non-empty `exit_detail`; child/SDK failures receive a
redacted `error_detail` of at most 2048 characters, with database constraints
preventing an alternate writer from persisting a silent failure.

The focused Door, Doctor, execution and database regressions pass. Hunt 21's
initial and final Doctor calls both reported zero violations against its fresh
Program and database, and the fresh database passed all 93 integrity checks.
