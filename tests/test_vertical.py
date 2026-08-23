"""One synthetic vertical run, from a recon Receipt to a composed report.

`tests/test_database.py` proves each verb against the arrangement that verb is
about, and every case there starts from a fixture that has already walked the
half before it. What that shape cannot answer is whether the halves are one
path: a stage that stopped connecting to the next one would go on passing in
both of its own cases.

This module is the connection, and it is Arbeitsblock 1's last item read
literally. One Program walks recon, the Playbook its hunt ran under, the Test
that would settle its claim, the replay that performed it, the claim reaching
`supported`, the Finding that earned, the impact demonstrated under an
operator's grant, the severity stated on that demonstration, the pivot stamped
from the run that showed it, the chain those stamps compose, and the report
composed out of what the Finding cites -- in that order, with every stage
asserted off the rows the one before it wrote.

The two security requirements are asserted where they happen rather than in a
Program of their own: an approval-required impact class with no live grant
parks the Task instead of reaching the target, and a forbidden impact class is
refused before there is a Test, a Task, or a question a person might feel able
to answer.

Everything commits and the Program is purged at the end, for `ReplayFixture`'s
reason: what survives the transaction is the subject. The fixtures come from
`tests.test_database` rather than being rebuilt here, and `setUpModule` and
`tearDownModule` come with them because the harness they build is the database
this module runs against and unittest looks for both in the module it runs.
"""

from __future__ import annotations

import json
import secrets

from redkraken import program
from tests.fixtures import write
from tests.test_database import (
    ChainFixture,
    DatabaseCase,
    committed,
    setUpModule,  # noqa: F401 -- unittest reads both off this module's namespace
    specification,
    tearDownModule,  # noqa: F401
)


#: The Program this run is walked in. Its own, for `ReplayFixture`'s reason: the
#: teardown purges by it.
VERTICAL_SLUG = "selftest-vertical"


class VerticalRunTest(ChainFixture, DatabaseCase):
    """Arbeitsblock 1: eleven stages in one Program, each read off the last one's rows.

    The arrangement is the walk itself. `setUpClass` performs it once, in the
    order the evidence accrues, and keeps what cannot be read back afterwards --
    the state a Task was in while it was parked, the settlement that a
    reproduction later supersedes, the Surface before and after the topology
    walk. Everything else is read at assertion time out of the tables.

    Three places in the order are load-bearing. The forbidden classes are asked
    before the impact Task that opens, because 012 allows a Finding one live
    Task and afterwards each of them would be refused for that instead. The
    severity is stated after the first impact replay, because
    `demonstrated_impact` is refused until there is a demonstration. And the
    report is composed last, because `apply_computed_cvss` reads the effects the
    composition wrote and `report_blockers` is only true about the Finding as it
    stands after both.

    Everything commits, for 38's reason: the grant is asked in one transaction
    and answered by an operator on a connection of its own in another.
    """

    slug = VERTICAL_SLUG

    TOPOLOGY = "SELECT record_receipt_topology($1::uuid)"
    SELECTION = "SELECT record_playbook_selection($1::uuid, $2::uuid)"
    PROPOSE_TEST = "SELECT propose_test($1, $2::jsonb, $3::uuid)"
    PROPOSE_FINDING = "SELECT propose_finding($1, $2, $3, $4::uuid)"
    IMPACT_TASK = "SELECT propose_impact_task($1, $2::jsonb, $3::uuid)"
    SEVERITY = "SELECT propose_severity($1, $2, $3, $4)"
    REPORT = "SELECT propose_finding_report($1, $2::jsonb)"

    #: The address this Program's door dialled, and the name it dialled it for.
    #: TEST-NET-3, because the exchange is synthetic and says so.
    ADDRESS = "203.0.113.10"
    NAME = "app.example.com"
    APEX = "example.com"

    #: The second Identity slot. Declared and never provisioned: what it is for
    #: is `multiple_test_identities`, which counts declared user Identities, and
    #: that is one of the two facts the Playbook the hunt runs under triggers on.
    THERE = "neighbour"

    #: The one route the recon lap reached, the Endpoint under it and the
    #: parameter that makes it an ownership question at all.
    PATH = "/api/orders/2"
    TEMPLATE = "/api/orders/{id}"

    #: The claim, and the two routes the pivots walk. Each pivot has its own,
    #: for 39's reason: a transition on the route the member was validated on is
    #: refused as the member's own request.
    CLAIM = "the orders API lets a stranger write on a neighbour's order"
    ROUTES = ("165/note", "165/token")

    #: 034's vocabulary, and the band 38's basis admits.
    EFFECTS = ("cross_account_read", "cross_account_write")
    BAND = "high"
    RATIONALE = "a stranger read and wrote a neighbour's order and the write stayed written"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.declared = cls.configured((cls.HERE, cls.THERE))
        moved = program.run(cls.harness.runtime, write(cls.declared), accept_change=True)
        assert moved.ok, moved.violations
        cls.identity = cls.provisioned_identity(cls.HERE, cls.declared)

        cls.the_recon_lap()
        cls.the_hunt()
        cls.the_authored_test()
        cls.the_replay()
        cls.the_finding()
        cls.the_forbidden_impacts()
        cls.reach = cls.pivot("reach", cls.ROUTES[0], "other_account_data",
                              ["authenticated_session"])
        cls.the_severity()
        cls.token = cls.pivot("token", cls.ROUTES[1], "credential_material",
                              ["other_account_data"])
        cls.the_chain()
        cls.the_report()

    # -- stage 1: recon ---------------------------------------------------------

    @classmethod
    def the_recon_lap(cls):
        """One allowed exchange, and the two facts a lap already held and never wrote.

        The Application is the one `rk run` promoted out of the scope document
        rather than a second one, so the `serves` edge the walk draws has the
        subject every later stage is about at the other end of it.
        """
        cls.application = str(
            cls.connection.execute(
                "SELECT a.entity_id FROM applications a JOIN entities e ON e.id = a.entity_id"
                " CROSS JOIN LATERAL rk2_parse_base_url(a.base_url) u"
                " WHERE e.program_id = $1::uuid AND u.host = $2",
                (cls.program_id, cls.NAME),
            ).scalar()
        )
        cls.domain = cls.promoted(cls.NAME, cls.APEX)
        cls.reached = cls.receipt_of_the_lap(cls.PATH)
        cls.receipt = cls.label_of("receipts", cls.reached)

        cls.before = cls.topology()
        cls.recorded = cls.called(cls.TOPOLOGY, (cls.reached,))
        cls.after = cls.topology()
        cls.edges = [
            (str(source), str(kind), str(destination))
            for source, kind, destination in cls.rows_of(
                "SELECT s.type, r.type, d.type FROM relationships r"
                "  JOIN entities s ON s.id = r.src_entity_id"
                "  JOIN entities d ON d.id = r.dst_entity_id"
                " WHERE r.program_id = $1::uuid AND r.origin = 'observed'"
                " ORDER BY r.type",
                (cls.program_id,),
            )
        ]

    @classmethod
    def promoted(cls, fqdn: str, apex: str) -> str:
        """One Domain of this Program, through the verb that projects scope.

        `add_entity` rather than an INSERT because the walk reads the Domain to
        draw the edge and `refresh_scope_projection` is what decides whether the
        name is a target at all.
        """
        entity = committed(
            cls.owner_as_runtime(),
            "SELECT add_entity($1::uuid, 'domain', '', 'host', $2, 443, $3)::text",
            (cls.program_id, fqdn, f"domain:{fqdn}"),
        )
        cls.as_owner(
            "INSERT INTO domains (entity_id, fqdn, apex) VALUES ($1::uuid, $2, $3)",
            (entity, fqdn, apex),
        )
        return entity

    @classmethod
    def receipt_of_the_lap(cls, path: str) -> str:
        """One allowed exchange on the agent Lane, carrying the address it dialled.

        The Tool run holds a live capability and no Task, which is one of the two
        shapes `enforce_allowed_receipt_capability` admits and the shorter one.
        Written by the owner, like every Receipt in this tree's cases, because
        the proxy writes them and nothing here is running one.

        This is also the Receipt the report cites at the other end of the walk:
        034 admits the agent Lane and no other, and every other exchange this
        Program makes is a replay.
        """
        run = committed(
            cls.connection,
            "INSERT INTO agent_runs (program_id, role, runs_as, model, effort, mission_packet)"
            " VALUES ($1::uuid, 'orchestrator', 'session', 'operator', 'low', '{}'::jsonb)"
            " RETURNING id",
            (cls.program_id,),
        )
        tool_run = committed(
            cls.owner_as_runtime(),
            "INSERT INTO tool_runs (program_id, agent_run_id, tool, args, status, transport,"
            "                       decision, egress_token_sha256, egress_token_expires_at)"
            " VALUES ($1::uuid, $2::uuid, 'mcp__rk2__http_request', '{}'::jsonb, 'running',"
            "         'runtime', 'allow', $3, clock_timestamp() + interval '1 hour')"
            " RETURNING id",
            (cls.program_id, run, secrets.token_hex(32)),
        )
        return committed(
            cls.owner_as_runtime(),
            "INSERT INTO receipts (program_id, tool_run_id, lane, decision, reason, method,"
            "                      scheme, host, port, path, status_code, ts_arrival,"
            "                      scope_class, scope_version, pinned_ips)"
            " SELECT $1::uuid, $2::uuid, 'agent', 'allowed',"
            "        'allowed as target under scope version ' || p.scope_version,"
            "        'GET', 'https', $3, 443, $4, 200, now(), 'target', p.scope_version, $5"
            "   FROM programs p WHERE p.id = $1::uuid RETURNING id",
            (cls.program_id, tool_run, cls.NAME, path, cls.ADDRESS),
        )

    @classmethod
    def topology(cls) -> tuple:
        """The Host, the address it is, and the two edges around it."""
        hosts, address, resolves, serves = cls.rows_of(
            "SELECT (SELECT count(*) FROM entities e"
            "         WHERE e.program_id = $1::uuid AND e.type = 'host'"
            "           AND e.origin = 'observed'),"
            "       (SELECT host(h.address) FROM entities e JOIN hosts h ON h.entity_id = e.id"
            "         WHERE e.program_id = $1::uuid AND e.type = 'host' LIMIT 1),"
            "       (SELECT count(*) FROM relationships r"
            "         WHERE r.program_id = $1::uuid AND r.type = 'resolves_to'"
            "           AND r.src_entity_id = $2::uuid),"
            "       (SELECT count(*) FROM relationships r"
            "         WHERE r.program_id = $1::uuid AND r.type = 'serves'"
            "           AND r.dst_entity_id = $3::uuid)",
            (cls.program_id, cls.domain, cls.application),
        )[0]
        return (int(hosts), None if address is None else str(address),
                int(resolves), int(serves))

    # -- stage 2: the hunt, and the Playbook it runs under ----------------------

    @classmethod
    def the_hunt(cls):
        """The claim, the Playbook the catalogue chose for it, and the Task it froze onto.

        The subject is the Application the recon lap just proved is served,
        which is what makes this stage the next one rather than a second
        arrangement: 164 taught `subject_facts` to answer for an Application
        precisely because a hunt Task carries the subject of the claim, and a
        claim a recon child writes is about the Application.
        """
        cls.the_endpoint_under_it()
        cls.hypothesis, cls.subject = cls.claim_waiting(cls.CLAIM, cls.application)
        cls.claim = cls.label_of("hypotheses", cls.hypothesis)
        cls.task = cls.hunt_task()
        cls.kept = int(committed(cls.connection, cls.SELECTION, (cls.task, cls.subject)))
        cls.hunt_run = cls.claimed_by_a_hunter()
        cls.control = cls.the_control_the_playbook_asks_for()

    @classmethod
    def the_control_the_playbook_asks_for(cls) -> str:
        """The one Observation the chosen Playbook demands and no replay can file.

        `close_test_replay` derives the kind of every Observation it writes from
        the assertions that name the action, so the only two it can ever produce
        are `response_invariant` and `response_differential`.
        `object-ownership` asks for one `credential_effect` in the `control`
        role before `enforce_playbook_evidence` will admit `supported` -- the
        row that says the Identity the control ran under was working at the time
        -- and 155 admits a proposed evidence edge only while the claim is still
        `proposed`, which a claim with a Test running is not. So this row is
        arranged here rather than earned, out of the Receipt the lap already
        filed, the way every other case in this tree arranges the evidence it
        did not come to prove. It is the only row in the walk that is.
        """
        observation = committed(
            cls.owner_as_runtime(),
            "INSERT INTO observations (program_id, agent_run_id, subject_entity_id, kind,"
            "                          summary, provenance_kind, receipt_id)"
            " VALUES ($1::uuid, $2::uuid, $3::uuid, 'credential_effect',"
            "         'the exchange the lap made was answered rather than refused',"
            "         'receipt', $4::uuid) RETURNING id",
            (cls.program_id, cls.hunt_run, cls.subject, cls.reached),
        )
        cls.as_owner(
            "INSERT INTO hypothesis_evidence (program_id, hypothesis_id, observation_id,"
            "                                 polarity, role)"
            " VALUES ($1::uuid, $2::uuid, $3::uuid, 'supports', 'control')",
            (cls.program_id, cls.hypothesis, observation),
        )
        return observation

    @classmethod
    def the_endpoint_under_it(cls):
        """One route under the Application, with the parameter that makes it a question.

        A Playbook is chosen against facts and the facts are joins: an Endpoint
        in scope gives the Application `path_parameter`, and a parameter whose
        value class is an identifier gives it `object_identifier`. Without a
        route under it, the Surface says only that this Program holds two
        Identities, and 164's `nothing in the corpus is about this subject` is
        the honest answer to that.
        """
        endpoint = committed(
            cls.owner_as_runtime(),
            "SELECT add_entity($1::uuid, 'endpoint', '', 'host', $2, 443, $3)::text",
            (cls.program_id, cls.NAME, f"endpoint:GET {cls.TEMPLATE}"),
        )
        cls.re_addressed(endpoint, cls.NAME, cls.PATH)
        cls.as_owner(
            "INSERT INTO endpoints (entity_id, application_id, method, path_template,"
            "                       auth_required)"
            " VALUES ($1::uuid, $2::uuid, 'GET', $3, true)",
            (endpoint, cls.application, cls.TEMPLATE),
        )
        parameter = committed(
            cls.owner_as_runtime(),
            "SELECT add_entity($1::uuid, 'parameter', '', 'host', $2, 443, $3)::text",
            (cls.program_id, cls.NAME, f"parameter:{cls.TEMPLATE}:id"),
        )
        cls.as_owner(
            "INSERT INTO parameters (entity_id, endpoint_id, name, location, value_class)"
            " VALUES ($1::uuid, $2::uuid, 'id', 'path', 'integer_id')",
            (parameter, endpoint),
        )

    @classmethod
    def hunt_task(cls) -> str:
        """One `hunt` over the subject the claim is about, as the scheduler files one.

        Written by hand for `claimed_agent_run`'s reason: filing one is the
        scheduler's move and no case here is running a slate. It names no
        Finding, which is what keeps it and the impact Tasks below apart under
        008's live dedup index.
        """
        cls.as_owner(
            "INSERT INTO tasks (program_id, kind, subject_entity_id, hypothesis_id,"
            "                   expected_information_gain, potential_impact)"
            " VALUES ($1::uuid, 'hunt', $2::uuid, $3::uuid, 0.5, 0.5)",
            (cls.program_id, cls.subject, cls.hypothesis),
        )
        return str(
            cls.connection.execute(
                "SELECT id FROM tasks WHERE program_id = $1::uuid"
                "   AND hypothesis_id = $2::uuid AND finding_id IS NULL",
                (cls.program_id, cls.hypothesis),
            ).scalar()
        )

    @classmethod
    def claimed_by_a_hunter(cls) -> str:
        """The Task claimed and the run that holds it, with what a claim takes along.

        The Identity Leases go with it because 072 makes a hunt Task act as its
        Program's anonymous session, so a run arranged without them is a clamped
        run holding no session -- the state `check_identity_clamp()` exists to
        find.
        """
        cls.as_owner(
            "UPDATE tasks SET status = 'claimed', claimed_at = now(),"
            "                 lease_expires_at = now() + interval '30 minutes'"
            " WHERE id = $1::uuid",
            (cls.task,),
        )
        run = committed(
            cls.connection,
            "INSERT INTO agent_runs (program_id, task_id, role, model, effort, mission_packet)"
            " VALUES ($1::uuid, $2::uuid, 'web_hunter', 'operator', 'low', '{}'::jsonb)"
            " RETURNING id",
            (cls.program_id, cls.task),
        )
        cls.as_owner(
            "INSERT INTO identity_leases (program_id, identity_entity_id,"
            "                             holder_agent_run_id, expires_at)"
            " SELECT $1::uuid, ti.identity_entity_id, $2::uuid, t.lease_expires_at"
            "   FROM task_identities ti JOIN tasks t ON t.id = ti.task_id"
            "  WHERE t.id = $3::uuid ON CONFLICT DO NOTHING",
            (cls.program_id, run, cls.task),
        )
        return run

    # -- stages 3 to 6: the Test, the replay, the claim and the Finding ---------

    @classmethod
    def the_authored_test(cls):
        """Stage 3: the hunt files the Test that would settle its claim."""
        cls.proposed = cls.called(
            cls.PROPOSE_TEST, (cls.claim, specification(cls.HELD), cls.hunt_run)
        )
        assert cls.proposed["outcome"] == "created", cls.proposed
        cls.authored = cls.id_of("tests", cls.proposed["test"])

    @classmethod
    def the_replay(cls):
        """Stages 4 and 5: the Test is performed, and the claim it settles moves.

        The settlement is read here rather than at assertion time because the
        reproduction below reopens the claim and settles it a second time: read
        afterwards, this would be the passage that superseded the one stage 5 is
        about.
        """
        cls.first = cls.performed(cls.authored, answers=cls.ANSWERS)
        cls.settlement = tuple(
            str(field) if index < 4 else int(field)
            for index, field in enumerate(cls.rows_of(
                "SELECT h.status, ht.from_status, ht.to_status, ht.actor_kind,"
                "       (SELECT count(*) FROM test_run_receipts trr"
                "         WHERE trr.receipt_id = ht.receipt_id"
                "           AND trr.test_run_id = $2::uuid)"
                "  FROM hypotheses h JOIN hypothesis_transitions ht ON ht.hypothesis_id = h.id"
                " WHERE h.id = $1::uuid AND ht.to_status = 'supported'"
                " ORDER BY ht.at DESC LIMIT 1",
                (cls.hypothesis, cls.first["closed"]["test_run_id"]),
            )[0])
        )

    @classmethod
    def the_finding(cls):
        """Stage 6: the supported claim becomes the Finding it earned, and is judged.

        `propose_finding` and not `open_finding`, because what is under test
        here is the path a caller has: a child reads `H4` and never a uuid, and
        the verb resolves the claim, the run that settled it and the Agent run
        that asked.
        """
        cls.opened = cls.called(
            cls.PROPOSE_FINDING, (cls.claim, cls.klass, cls.TITLE, cls.hunt_run)
        )
        assert cls.opened["outcome"] == "created", cls.opened
        cls.made = cls.reproduced({
            "hypothesis": cls.hypothesis,
            "subject": cls.subject,
            "test": cls.authored,
            "finding": cls.opened["finding_id"],
        })
        cls.made["opened"] = cls.called(
            cls.SESSION, (cls.program_id, cls.made["finding"], cls.made["replay"])
        )
        assert cls.made["opened"]["outcome"] == "opened", cls.made["opened"]
        cls.answer(cls.made, "confirmed")
        assert cls.made["verdict"]["status"] == "validated", cls.made["verdict"]
        cls.finding = cls.made["finding"]
        cls.label = cls.label_of("findings", cls.finding)

    # -- stage 7: the impact, and the two things that may not happen -----------

    @classmethod
    def the_forbidden_impacts(cls):
        """The security half, asked before the impact Task that opens.

        Before it, because 012 allows a Finding one live Task: asked afterwards,
        each of these would come back refused for the Task that is already open
        rather than for the reason it is here.

        Measured rather than read: what has to be true is that no Test row was
        written and that nobody was asked a question -- a `pending_decisions`
        row for a class `risk_classes` denies is a question with no admissible
        answer, and an operator holding one has been invited to authorise what
        the schema exists to refuse.
        """
        before = cls.surface()
        cls.forbidden = {
            klass: cls.called(
                cls.IMPACT_TASK,
                (cls.label,
                 specification(cls.SHOWN, cleanup=cls.UNDO,
                               impact=cls.IMPACT | {"class": klass}),
                 cls.hunt_run),
            )
            for klass in ("degrade_availability", "reach_third_party", "pivot_out_of_scope")
        }
        cls.nothing_was_asked = (before, cls.surface())

    @classmethod
    def surface(cls) -> tuple:
        """What a refused proposal must not have left behind."""
        return tuple(
            int(count)
            for count in cls.rows_of(
                "SELECT (SELECT count(*) FROM tests WHERE program_id = $1::uuid),"
                "       (SELECT count(*) FROM tasks WHERE program_id = $1::uuid),"
                "       (SELECT count(*) FROM pending_decisions WHERE program_id = $1::uuid)",
                (cls.program_id,),
            )[0]
        )

    @classmethod
    def pivot(cls, name: str, route: str, provides: str, requires: list[str]) -> dict:
        """One impact Test opened, parked, granted, replayed and stamped.

        39's arrangement asked through 103's Contract rather than through
        `open_impact_task`, for `propose_finding`'s reason: the verb a caller
        has is the one that takes the label.

        The park between the proposal and the replay is not arrangement either.
        It is the first security requirement read where it happens: an
        approval-required impact class with no live grant behind it stops the
        Task and asks a person, and nothing that could reach the target has been
        written when it does.
        """
        opened = cls.called(
            cls.IMPACT_TASK,
            (cls.label, cls.pivot_spec(route, provides, requires, cls.HERE), cls.hunt_run),
        )
        assert opened["outcome"] == "created", opened
        test = cls.id_of("tests", opened["test"])
        parked = cls.called(cls.OPEN_REPLAY, (cls.run_on(opened["task"]), test, cls.HERE))
        waiting = cls.waiting_on(opened["task"])
        cls.approve(parked["parked"])
        walk = cls.impact_replay(opened["task"], test, cls.ANSWERED, "done", slot=cls.HERE)
        issued = cls.issue(walk)
        assert issued["refusal"] is None, issued
        cls.settled(opened["task"])
        cls.of[name] = {"task": opened["task"], "test": test, "walk": walk,
                        "label": issued["stamp"]}
        cls.stamp[name] = cls.id_of("pivot_stamps", issued["stamp"])
        return {"opened": opened, "test": test, "parked": parked, "waiting": waiting,
                "walk": walk, "issued": issued}

    @classmethod
    def waiting_on(cls, task: str) -> tuple:
        """What a Task with no grant behind it is left holding.

        The last field is the half that matters: a parked impact run has no Tool
        run, so it holds no capability, so the door has nothing to let through.
        """
        status, decision, risk, rule, capability = cls.rows_of(
            "SELECT t.status, d.label, d.risk_class, d.risk_rule,"
            "       (SELECT count(*) FROM tool_runs tr WHERE tr.task_id = t.id)"
            "  FROM tasks t JOIN pending_decisions d ON d.id = t.pending_decision_id"
            " WHERE t.program_id = $1::uuid AND t.label = $2",
            (cls.program_id, task),
        )[0]
        return (str(status), str(decision), str(risk), str(rule), int(capability))

    # -- stages 8 to 11: the band, the chain and the report ---------------------

    @classmethod
    def the_severity(cls):
        """Stage 8: the band, on the demonstration the impact replay just filed."""
        cls.stated = cls.called(
            cls.SEVERITY, (cls.label, cls.BAND, "demonstrated_impact", cls.RATIONALE)
        )
        assert cls.stated["outcome"] == "stated", cls.stated

    @classmethod
    def the_chain(cls):
        """Stage 10: the two stamps compose, and the operator read answers."""
        cls.chain = cls.build(cls.members("reach", "token"),
                              run=cls.of["reach"]["walk"]["run"])
        assert cls.chain["refusal"] is None, cls.chain
        cls.chain_read = cls.read(cls.chain["chain"])

    @classmethod
    def the_report(cls):
        """Stage 11: the impact and reproduction halves, composed out of what is cited."""
        cls.read_what_the_finding_cites()
        cls.reported = cls.called(cls.REPORT, (cls.label, cls.composition()))
        cls.blockers = cls.hard_blockers()

    @classmethod
    def read_what_the_finding_cites(cls):
        """The witnesses and the tokens the composition is built out of.

        Read rather than written down: 034's no-new-facts rule admits only a
        value that is in a row the Finding cites, so a literal path here would
        fail with a message about a new fact rather than about the edit that
        caused it. In labels, because that is what the Contract sends.

        The witnesses are the three the replay filed and not everything the
        Finding carries: the Playbook's `control` row above is evidence of the
        claim and is cited as such, but it stands on the lap's Receipt rather
        than on an action of the run this report reproduces.
        """
        cls.witness = [
            str(row[0])
            for row in cls.rows_of(
                "SELECT o.label FROM finding_evidence fe"
                "  JOIN observations o ON o.id = fe.observation_id"
                "  JOIN test_run_receipts trr ON trr.receipt_id = o.receipt_id"
                " WHERE fe.finding_id = $1::uuid AND trr.test_run_id = $2::uuid"
                " ORDER BY trr.ordinal",
                (cls.finding, cls.first["closed"]["test_run_id"]),
            )
        ]
        cls.cited = [
            (str(path), str(status))
            for path, status in cls.rows_of(
                "SELECT DISTINCT r.path, r.status_code::text"
                "  FROM finding_cited_receipts fcr JOIN receipts r ON r.id = fcr.receipt_id"
                " WHERE fcr.finding_id = $1::uuid ORDER BY 1",
                (cls.finding,),
            )
        ]
        assert len(cls.witness) == 3, cls.witness
        assert len(cls.cited) == 3, cls.cited
        cls.variant, cls.control = cls.cited[1], cls.cited[2]

    @classmethod
    def composition(cls) -> str:
        """What the hunter judged, in the words a child was shown it in.

        The Receipt cited is the recon lap's, which is the only exchange this
        Program made on the agent Lane -- and the Lane 034 admits.
        """
        return json.dumps({
            "effects": [
                {"effect": cls.EFFECTS[0], "witness": cls.witness[0]},
                {"effect": cls.EFFECTS[1], "witness": cls.witness[1]},
            ],
            "steps": [
                {
                    "mechanism": "generic.control",
                    "params": {"control_path": cls.control[0],
                               "control_status": cls.control[1],
                               "path": cls.variant[0]},
                    "citations": [{"observation": cls.witness[0]},
                                  {"receipt": cls.receipt}],
                },
            ],
        })

    @classmethod
    def hard_blockers(cls) -> dict:
        return {
            str(code): str(detail)
            for severity, code, detail in cls.rows_of(
                "SELECT * FROM report_blockers($1::uuid)", (cls.finding,)
            )
            if str(severity) == "hard"
        }

    # -- the two lookups these verbs are asked in ------------------------------

    @classmethod
    def label_of(cls, table: str, identifier: str) -> str:
        """The label behind an id, because these verbs are asked in labels.

        The table name is interpolated and every call site passes a literal, for
        `id_of`'s reason: this is that lookup read the other way round.
        """
        return str(
            cls.connection.execute(
                f"SELECT label FROM {table} WHERE id = $1::uuid", (identifier,)
            ).scalar()
        )

    # -- the run itself ---------------------------------------------------------

    def test_one_program_walks_from_a_recon_receipt_to_a_composed_report(self):
        """The eleven stages, in order, each asserted off the rows it wrote.

        One method rather than eleven, because what is under test is that the
        stages connect: eleven independent cases would prove eleven things and
        nothing about the path between them. Each block below reads a row the
        block before it produced -- the Application the topology walk served is
        the subject the Playbook was chosen for, the Test the hunt filed is the
        Test the replay performed, the Receipt that settled the claim is the
        Receipt the transition cites, and so on to the report.
        """
        # -- 1. Recon: the address the door dialled, as a subject and two edges
        self.assertEqual((0, None, 0, 0), self.before)
        self.assertEqual({"hosts": 1, "resolves_to": 1, "serves": 1}, self.recorded)
        self.assertEqual((1, self.ADDRESS, 1, 1), self.after)
        self.assertEqual(
            [("domain", "resolves_to", "host"), ("host", "serves", "application")],
            self.edges,
        )

        # -- 2. Hunt/Playbook: a claimed hunt over the subject that Application is
        kind, status, subject, path, dropped = self.rows(
            "SELECT t.kind, t.status, s.subject_entity_id::text, p.path, s.dropped_because"
            "  FROM playbook_selections s JOIN tasks t ON t.id = s.task_id"
            "  JOIN playbooks p ON p.id = s.playbook_id"
            " WHERE s.task_id = $1::uuid AND s.dropped_because IS NULL"
            " ORDER BY s.rank LIMIT 1",
            (self.task,),
        )[0]

        self.assertGreaterEqual(self.kept, 1)
        self.assertEqual(("hunt", "claimed", self.application, None),
                         (str(kind), str(status), str(subject), dropped))
        self.assertTrue(str(path).endswith("playbook.md"), path)

        # -- 3. Test: one immutable plan, digested, filed by the run that holds the hunt
        digest, claim, authored_by = self.rows(
            "SELECT t.spec_sha256, h.label, t.created_by_run_id::text FROM tests t"
            "  JOIN hypotheses h ON h.id = t.hypothesis_id WHERE t.id = $1::uuid",
            (self.authored,),
        )[0]

        self.assertEqual(
            (self.proposed["spec_sha256"], self.claim, self.hunt_run),
            (str(digest), str(claim), str(authored_by)),
        )

        # -- 4. Replay: the Test run, and the exchanges it filed
        outcome, lane, receipts = self.rows(
            "SELECT tr.outcome, tr.lane,"
            "       (SELECT count(*) FROM test_run_receipts x WHERE x.test_run_id = tr.id)"
            "  FROM test_runs tr WHERE tr.id = $1::uuid AND tr.test_id = $2::uuid",
            (self.first["closed"]["test_run_id"], self.authored),
        )[0]

        self.assertEqual(("holds", "replay", 3), (str(outcome), str(lane), int(receipts)))

        # -- 5. supported: the transition the runtime made, citing that run's Receipt
        self.assertEqual(("supported", "testing", "supported", "runtime", 1), self.settlement)

        # -- 6. Finding: opened on the claim, and validated on the reproduction
        status, subject, rests_on, validated_by = self.rows(
            "SELECT f.status, f.subject_entity_id::text,"
            "       (SELECT count(*) FROM finding_hypotheses fh"
            "         WHERE fh.finding_id = f.id AND fh.hypothesis_id = $2::uuid),"
            "       f.validated_by_test_run_id::text"
            "  FROM findings f WHERE f.id = $1::uuid",
            (self.finding, self.hypothesis),
        )[0]

        self.assertEqual("created", self.opened["outcome"])
        self.assertEqual(("validated", self.application, 1, self.made["replay"]),
                         (str(status), str(subject), int(rests_on), str(validated_by)))

        # -- 7. Impact: the Test and Task the Contract opened, and what the replay showed
        test, task, demonstrated, undone = self.rows(
            "SELECT (SELECT count(*) FROM tests s"
            "         WHERE s.program_id = $1::uuid AND s.label = $2"
            "           AND s.impact_class = 'write_target_state'),"
            "       (SELECT count(*) FROM tasks t JOIN findings f ON f.id = t.finding_id"
            "         WHERE t.program_id = $1::uuid AND t.label = $3 AND f.id = $4::uuid),"
            "       (SELECT count(*) FROM impact_demonstrations d"
            "         WHERE d.finding_id = $4::uuid AND d.tool_run_id = $5::uuid"
            "           AND d.cleanup = 'done' AND d.run_outcome = 'holds'),"
            "       (SELECT cleanup_receipts FROM impact_demonstrations d"
            "         WHERE d.tool_run_id = $5::uuid)",
            (self.program_id, self.reach["opened"]["test"], self.reach["opened"]["task"],
             self.finding, self.reach["walk"]["plan"]["tool_run_id"]),
        )[0]

        self.assertEqual("created", self.reach["opened"]["outcome"])
        self.assertEqual((1, 1, 1), (int(test), int(task), int(demonstrated)))
        self.assertGreaterEqual(int(undone), 1)

        # -- 8. Severity: the band, its basis, and the demonstration under it
        basis, severity, band, on_demonstration = self.rows(
            "SELECT s.basis, s.severity, f.severity::text, s.impact_demonstration_id IS NOT NULL"
            "  FROM severity_statements s JOIN findings f ON f.id = s.finding_id"
            " WHERE s.finding_id = $1::uuid ORDER BY s.created_at DESC, s.id DESC LIMIT 1",
            (self.finding,),
        )[0]

        self.assertEqual("stated", self.stated["outcome"])
        self.assertEqual(("demonstrated_impact", self.BAND, self.BAND, True),
                         (str(basis), str(severity), str(band), bool(on_demonstration)))

        # -- 9. Pivot stamp: issued on the run that showed it
        stamped, provides, transition = self.rows(
            "SELECT s.tool_run_id::text, s.provides, s.transition FROM pivot_stamps s"
            " WHERE s.program_id = $1::uuid AND s.label = $2",
            (self.program_id, self.reach["issued"]["stamp"]),
        )[0]

        self.assertIs(True, self.reach["issued"]["issued"])
        self.assertEqual(
            (self.reach["walk"]["plan"]["tool_run_id"], "other_account_data",
             self.SHOWN[0]["id"]),
            (str(stamped), str(provides), str(transition)),
        )

        # -- 10. Kill chain: two steps, one edge, and a read that answers sound
        steps, edges, capability = self.rows(
            "SELECT (SELECT count(*) FROM chain_steps s JOIN chains c ON c.id = s.chain_id"
            "         WHERE c.program_id = $1::uuid AND c.label = $2),"
            "       (SELECT count(*) FROM chain_edges e JOIN chains c ON c.id = e.chain_id"
            "         WHERE c.program_id = $1::uuid AND c.label = $2),"
            "       (SELECT string_agg(e.capability, ',') FROM chain_edges e"
            "          JOIN chains c ON c.id = e.chain_id"
            "         WHERE c.program_id = $1::uuid AND c.label = $2)",
            (self.program_id, self.chain["chain"]),
        )[0]

        self.assertEqual((2, 1, "other_account_data"),
                         (int(steps), int(edges), str(capability)))
        self.assertEqual((True, None),
                         (self.chain_read["sound"], self.chain_read["unsound"]))
        self.assertEqual((int(steps), int(edges)),
                         (len(self.chain_read["steps"]), len(self.chain_read["edges"])))

        # -- 11. Report: the two halves composed, the vector written, nothing blocking
        effects, chain_steps, citations, vector = self.rows(
            "SELECT (SELECT count(*) FROM finding_effects fe WHERE fe.finding_id = $1::uuid),"
            "       (SELECT count(*) FROM finding_chain_steps s WHERE s.finding_id = $1::uuid),"
            "       (SELECT count(*) FROM finding_chain_step_citations c"
            "          JOIN finding_chain_steps s ON s.id = c.step_id"
            "         WHERE s.finding_id = $1::uuid),"
            "       (SELECT f.cvss_vector FROM findings f WHERE f.id = $1::uuid)",
            (self.finding,),
        )[0]

        self.assertEqual(("composed", self.label),
                         (self.reported["outcome"], self.reported["finding"]))
        self.assertEqual((2, 1, 2), (int(effects), int(chain_steps), int(citations)))
        self.assertEqual(self.reported["cvss_vector"], None if vector is None else str(vector))
        self.assertIsNotNone(vector)
        self.assertEqual({}, self.blockers)

    # -- the two things this run may not do ------------------------------------

    def test_an_approval_required_impact_parks_the_task_instead_of_running_it(self):
        """Ticket 104's rule, on the path that reaches it: no standing grant, no run.

        Read off the Task and the question rather than off the answer: what has
        to be true is that the work stopped and a person was asked, and that
        nothing which could reach the target existed while they thought about it.
        """
        self.assertEqual(
            ("parked", self.reach["parked"]["parked"], "approval_required",
             "impact_classes:write_target_state", 0),
            self.reach["waiting"],
        )
        self.assertEqual(
            "no live operator grant covers " + self.reach["opened"]["test"],
            self.reach["parked"]["refusal"],
        )

    def test_a_forbidden_impact_class_is_refused_and_becomes_no_question(self):
        """Ticket 38's criterion 5, restated as the thing an operator never sees.

        A `pending_decisions` row for a class `risk_classes` denies is a question
        with no admissible answer, and an operator holding one has been invited
        to authorise what the schema exists to refuse.
        """
        for klass, answered in self.forbidden.items():
            with self.subTest(impact_class=klass):
                self.assertEqual("refused", answered["outcome"])
                self.assertIn(f"impact class {klass} is forbidden", answered["refusal"])

        before, after = self.nothing_was_asked

        self.assertEqual(before, after)
        self.assertEqual(
            0,
            int(self.rows(
                "SELECT count(*) FROM pending_decisions"
                " WHERE program_id = $1::uuid AND risk_class = 'forbidden'",
                (self.program_id,),
            )[0][0]),
        )
