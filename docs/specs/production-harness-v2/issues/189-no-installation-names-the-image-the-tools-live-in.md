# 189 — No installation names the image the tools live in

**What to build:** A tool image that exists, and an engagement that names it.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** Database `rk2here`, 2026-08-25,
      after ticket 186 put 35 `source` Artifact references where there had been
      none. The recon child called `run_tool` and the campaign held nothing to
      show for it:

      ```
      -- SELECT offline_tool, status, count(*) FROM tool_runs
      --  WHERE offline_tool IS NOT NULL GROUP BY 1,2;
      (0 rows)
      ```

      Every `tool_runs` row in the database was `mcp__rk2__net_request` or
      `rk2.transport_measurement`. Not one offline tool has ever run against
      this Program, so the three analysers ticket 186 granted to `recon` were
      granted to a role that could not reach them.

      The chain, which is the one ticket 151 wrote down and did not close:

      ```
      RK_TOOL_IMAGE unset
        -> tool.image_from_environment() is None
        -> cli: Slice.tools = None
        -> execution: agent.Tooling(container=None)
        -> _Tools answers `no_tool_image` for run_tool and run_skill_script
      ```

      151 fixed the coupling that took the *other* three verbs down with it, and
      recorded that `RK_TOOL_IMAGE` "appears in no engagement `env.sh`, in no
      shipped documentation and in no default". That sentence stayed true. The
      refusal is now correct and still refuses everything.

- [x] **The image exists and is a file, not a memory.**
      `tools/tool-image.Dockerfile`. `offline_tools.executable` names exactly
      two absolute paths and the image makes both of them true:
      `/usr/local/bin/python3` for the five analysers this harness ships, and
      `/usr/bin/jq` for the one registered tool that is not one of ours.
      Nothing else is in it. The analyser is mounted read-only at run time
      under the hash on the row, so an image carrying a copy would only be a
      second answer to a question the row already settles.

      ```
      docker build -f tools/tool-image.Dockerfile -t rk2tools:latest .
      ```

- [x] **The engagement names it.** `here-env.sh` exports
      `RK_TOOL_IMAGE="rk2tools:latest"` beside `RK_AGENT_IMAGE`, with the
      comment saying why it is a second variable and what is unreachable
      without it.

- [x] **Both halves answer in the built image.** The version probe is the
      honest check, because it runs in the container the call will use:

      ```
      js_routes reports itself as rk2-jsscan 3, from /input/jsscan.py at 77b67c3c...
      jq reports itself as jq-1.7
      ```

## Why

Ticket 186 made a `source` Artifact reachable and ticket 188's Skill rewrite
told the recon child to run `js_routes` over every script it stored. Both were
correct and both were pointed at a door that answered `no_tool_image`. The
measurement that found it is the one that would have found it at any point in
this tree's life: `tool_runs` has never held an `offline_tool`.

The registry, the arguments, the roles, the analyser, the version pattern and
the refusal were all built and all tested. What was missing was an image, which
is the one part of the chain that is not code and therefore the one part no
test could notice.
