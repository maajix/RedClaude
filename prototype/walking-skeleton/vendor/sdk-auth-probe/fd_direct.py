"""Does CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR work at all? Ticket 21.

PROTOTYPE - throwaway.

The SDK spawns the CLI through anyio/asyncio, which closes every inherited fd
above stderr, so the fd vector may be unreachable *through the SDK* while still
being live in the CLI itself. This spawns the bundled CLI directly with
pass_fds, which is the only way to tell those two apart.

Runs behind the same fake upstream as probe.py, so nothing leaves the machine.

    .venv/bin/python fd_direct.py
"""

import json
import os
import subprocess

from probe import (
    CAPTURE,
    FAKE,
    HERE,
    MITM_CONF,
    OUT,
    PROMPT,
    classify,
    credential_names,
    events_after,
    marker,
    read_capture,
    scrubbed_env,
    start_proxy,
)

BUNDLED_CLI = HERE / ".venv/lib/python3.14/site-packages/claude_agent_sdk/_bundled/claude"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    names = credential_names()
    proxy = start_proxy()
    env = scrubbed_env(str(MITM_CONF / "mitmproxy-ca-cert.pem"))
    env["CLAUDE_CODE_ENTRYPOINT"] = "sdk-py"  # what the SDK sets; keep the same path

    read_fd, write_fd = os.pipe()
    os.write(write_fd, FAKE["fd_key"].encode())
    os.close(write_fd)
    os.set_inheritable(read_fd, True)
    env["CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR"] = str(read_fd)

    marker("fd_direct")
    try:
        proc = subprocess.run(
            [str(BUNDLED_CLI), "-p", PROMPT, "--output-format", "stream-json", "--verbose"],
            cwd=HERE,
            env=env,
            pass_fds=(read_fd,),
            capture_output=True,
            text=True,
            timeout=180,
        )
    finally:
        proxy.terminate()

    observed = classify(events_after(read_capture(), "fd_direct"), names)
    init = next(
        (
            json.loads(line)
            for line in proc.stdout.splitlines()
            if line.startswith("{") and '"subtype":"init"' in line.replace(" ", "")
        ),
        {},
    )
    payload = {
        "fd_number": read_fd,
        "apiKeySource": init.get("apiKeySource"),
        "observed": observed,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
    }
    print(json.dumps(observed))
    print(proc.stdout[:600])
    (OUT / "fd-direct.json").write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {OUT / 'fd-direct.json'}")


if __name__ == "__main__":
    main()
