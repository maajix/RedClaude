"""One probe run: drive claude_agent_sdk.query() once and dump everything.

PROTOTYPE - throwaway. Ticket 21.

Reads a JSON job on argv[1], prints one JSON object on stdout. The driver
(probe.py) owns the environment: this process is spawned with an already
scrubbed env plus whatever credential vector is under test, so the SDK's
os.environ inheritance starts from a known state.

Never handles a working API key. Every credential value it may set is a
deliberately invalid probe string.
"""

import json
import os
import sys
import time
from dataclasses import asdict, is_dataclass

import anyio

from claude_agent_sdk import ClaudeAgentOptions, query


def jsonable(obj):
    if is_dataclass(obj) and not isinstance(obj, type):
        return jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


async def run(job):
    stderr_lines = []
    opts_kwargs = dict(
        model=job.get("model"),
        max_turns=1,
        tools=[],  # no built-in tools: the run is one model call, nothing else
        # Isolation by default: the operator's own settings stay out. A vector
        # that is *about* filesystem settings passes its own sources.
        setting_sources=job.get("setting_sources", []),
        stderr=stderr_lines.append,
        cwd=job["cwd"],
    )
    if job.get("settings_path"):
        opts_kwargs["settings"] = job["settings_path"]
    options = ClaudeAgentOptions(**{k: v for k, v in opts_kwargs.items() if v is not None})

    messages = []
    started = time.monotonic()
    error = None
    try:
        with anyio.fail_after(job.get("timeout_s", 90)):
            async for message in query(prompt=job["prompt"], options=options):
                messages.append({"class": type(message).__name__, "value": jsonable(message)})
    except BaseException as exc:  # noqa: BLE001 - the failure mode IS the finding
        error = {"class": type(exc).__name__, "message": str(exc)[:4000]}

    return {
        "elapsed_s": round(time.monotonic() - started, 2),
        "messages": messages,
        "stderr": stderr_lines[-40:],
        "error": error,
    }


def main():
    job = json.loads(sys.argv[1])

    # CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR vector: open the fd in this process
    # first, mark it inheritable, then hand its number to the CLI through the
    # env var. Whether the SDK's spawn actually passes it on is the question.
    if job.get("fd_secret"):
        read_fd, write_fd = os.pipe()
        os.write(write_fd, job["fd_secret"].encode())
        os.close(write_fd)
        os.set_inheritable(read_fd, True)
        os.environ["CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR"] = str(read_fd)
        job["fd_number"] = read_fd

    result = anyio.run(run, job)
    result["fd_number"] = job.get("fd_number")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
