"""Two control runs against the real api.anthropic.com. Ticket 21.

PROTOTYPE - throwaway.

The matrix in probe.py answers "which credential does the CLI choose" behind a
fake upstream. These two runs check that the fake upstream did not change the
answer, on the only question that can be asked of the real service without
spending anything meaningful:

  live_baseline - no credential vector set. Does query() actually complete on
                  the subscription, and what does apiKeySource say?
  live_api_key  - ANTHROPIC_API_KEY set to an unusable probe value. Does the
                  call fail with an error attributable to that key (the key was
                  chosen over OAuth), or succeed (OAuth won)?

The second run cannot bill: the key is invalid, so the request is rejected.
The first run is one Haiku turn on the subscription.

    .venv/bin/python live_control.py
"""

import json
import os
import pathlib
import subprocess

from probe import FAKE, OUT, VENV_PY, HERE, PROMPT, summarize

MODEL = "claude-haiku-4-5-20251001"


def live_env(extra: dict) -> dict:
    keep = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "TMPDIR", "XDG_RUNTIME_DIR")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["TERM"] = "dumb"
    env["CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"] = "1"
    env.update(extra)
    return env


def run(name: str, extra: dict, timeout_s: int = 120) -> dict:
    job = {"prompt": PROMPT, "cwd": str(HERE), "model": MODEL, "timeout_s": timeout_s}
    proc = subprocess.run(
        [str(VENV_PY), str(HERE / "runner.py"), json.dumps(job)],
        cwd=HERE,
        env=live_env(extra),
        capture_output=True,
        text=True,
        timeout=240,
    )
    try:
        raw = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        raw = {"error": {"class": "RunnerCrash", "message": proc.stderr[-2000:]}, "messages": []}
    return {"id": name, "result": summarize(raw), "raw": raw}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    # The invalid key is retried 10 times before the CLI gives up, so it needs
    # a longer leash than the one-shot subscription run.
    results = [
        run("live_baseline", {}),
        run("live_api_key", {"ANTHROPIC_API_KEY": FAKE["env_api_key"]}, timeout_s=420),
    ]
    for entry in results:
        print(f"--- {entry['id']}")
        print(json.dumps(entry["result"])[:900])
    pathlib.Path(OUT / "live-results.json").write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT / 'live-results.json'}")


if __name__ == "__main__":
    main()
