"""mitmproxy addon: capture the credential the CLI chose, answer locally.

PROTOTYPE - throwaway. Ticket 21.

The point of intercepting rather than pointing ANTHROPIC_BASE_URL at a local
server: the CLI's auth resolution has a first-party-endpoint branch, so a
rewritten base URL would be testing a different code path than the harness
runs. Here the CLI still believes it is talking to api.anthropic.com.

Every request is answered from this file. No connection is ever made upstream,
so a probe run costs nothing and cannot bill - including when the credential
under test is invalid.

Credential values are never written out. Each is recorded as
(scheme, length, sha256[:12]), which is enough to say *which* of the probe's
distinct fake secrets - or the operator's real OAuth token - was chosen.
"""

import hashlib
import json
import os
import pathlib

from mitmproxy import http

CAPTURE = pathlib.Path(os.environ.get("PROBE_CAPTURE", "out/capture.jsonl"))
CAPTURE.parent.mkdir(parents=True, exist_ok=True)

CREDENTIAL_HEADERS = {
    "authorization",
    "x-api-key",
    "proxy-authorization",
    "x-goog-api-key",
    "x-amz-security-token",
    "x-api-key-source",
}


def fingerprint(value: str) -> dict:
    """Identify a credential without recording it."""
    scheme, _, rest = value.partition(" ")
    secret = rest if rest else value
    return {
        "scheme": scheme if rest else None,
        "len": len(secret),
        "sha12": hashlib.sha256(secret.encode()).hexdigest()[:12],
    }


def record(event: dict) -> None:
    with CAPTURE.open("a") as fh:
        fh.write(json.dumps(event) + "\n")


SSE = "\n".join(
    f"event: {name}\ndata: {json.dumps(payload)}\n"
    for name, payload in [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_probe",
                    "type": "message",
                    "role": "assistant",
                    "model": "probe-model",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            },
        ),
        (
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        ),
        (
            "content_block_delta",
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "PROBE_OK"}},
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 1},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
)


def request(flow: http.HTTPFlow) -> None:
    creds = {
        name: fingerprint(value)
        for name, value in flow.request.headers.items()
        if name.lower() in CREDENTIAL_HEADERS
    }
    body_head = ""
    if flow.request.content and len(flow.request.content) < 200_000:
        try:
            body = json.loads(flow.request.content)
            body_head = json.dumps({k: body[k] for k in ("model", "max_tokens", "stream") if k in body})
        except Exception:  # noqa: BLE001 - a non-JSON body is not interesting here
            body_head = f"<{len(flow.request.content)} bytes>"

    record(
        {
            "host": flow.request.pretty_host,
            "port": flow.request.port,
            "method": flow.request.method,
            "path": flow.request.path.split("?")[0],
            "credential_headers": creds,
            "header_names": sorted(name.lower() for name in flow.request.headers.keys()),
            "body_head": body_head,
        }
    )

    if flow.request.path.startswith("/v1/messages") and flow.request.method == "POST":
        flow.response = http.Response.make(
            200,
            SSE.encode(),
            {"content-type": "text/event-stream", "anthropic-probe": "fake-upstream"},
        )
    else:
        flow.response = http.Response.make(
            200, json.dumps({"probe": "fake-upstream"}).encode(), {"content-type": "application/json"}
        )
