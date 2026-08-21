# 128 — Three Python capabilities with no caller

**What to build:** A caller or a removal for each of `Store.holds`,
`skill.check` and `skill.check_all`, and a corrected docstring where one of them
claims a caller it does not have.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] `Store.holds` (`src/redkraken/store.py:162-171`) is removed, or its
      docstring stops naming a caller it does not have. The docstring
      (`:163-170`) ends "which is what the proxy asks before deciding whether
      withholding a wire view would withhold anything at all". The proxy asks
      the database instead -- `READS = "SELECT program_reads_artifact($1, $2)"`
      at `src/redkraken/proxy.py:1061` -- and the only references to `holds` in
      the tree are four in `tests/test_database.py`. Superseded and never
      removed.
- [ ] The Skill corpus is checked by something other than the test suite, or the
      checking is deliberately test-only and says so. `skill.check_all`
      (`src/redkraken/skill.py:477-485`) runs every declared synthetic case in
      the corpus and its docstring says "so a caller can count"; there is no
      caller outside `tests/test_skill.py`. `skill.check`
      (`skill.py:430`) is called only from inside `check_all` (`skill.py:483`),
      so the whole subtree is production-dead.
- [ ] `doctor.diagnose` is the candidate caller and the ticket decides for or
      against it explicitly. `doctor.CORPORA` (`src/redkraken/doctor.py:102-106`)
      compiles all three corpora -- playbooks, skills, fixtures -- and compiling
      a Skill is not running its cases, so a shipped Skill script whose declared
      answer no longer holds is never caught on an installation. Either the
      diagnosis runs the cases, or a comment says why running attacker tooling
      during a health check is the wrong trade.
- [ ] Nothing is removed on the strength of a cross-reference alone. The
      counter-example is in the same file tree: `jsscan.py`'s entire public
      surface looks orphaned to a Python cross-reference and is not -- it is
      mounted into a tool container and run as a subprocess
      (`src/redkraken/tool.py:118`, `:653`, `:666`). Each of the three above was
      checked for that shape and has none.
- [ ] Where a function is kept deliberately uncalled, it is documented the way
      the repo already documents one:
      `src/redkraken/skills/analyse-source/scripts/extract_paths.py:151-157`
      says it is "Not called by `extract`, and here on purpose", names the other
      half of the pair and names the test that holds the two answers equal.

## Why

`docs/research/wiring/21-agent-surface-wiring.md` section 2.8. Three functions,
none with a comment explaining the absence, and one of them asserting in prose
that a caller exists.

The `skill.check` pair is the one with a cost beyond tidiness. A Skill script is
a program the harness ships and hands to a model; its declared cases are the
only statement of what it does. Running them only in the repo's own test suite
means an installation whose Python, whose container image or whose corpus has
drifted finds out when a hunt uses the Skill.

`ready-for-agent` because each of the three is a small, bounded decision with
the evidence already gathered, and because the removal option is safe: the tests
that reference them are the only callers, so a removal is visible immediately.
