"""The browser half that can be proved without a container or a database."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from redkraken import browser_driver


class Debugger:
    """The narrow CDP answers one Mission action needs."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []
        self.events = []

    def call(self, method, parameters=None, session=None):
        self.calls.append((method, parameters or {}, session))
        answer = self.answers[method]
        return answer(parameters or {}) if callable(answer) else answer

    def drain(self, seconds):
        return None


def mission(debugger):
    return browser_driver.Mission(
        {"step_timeout_ms": 1000, "max_artifact_bytes": 65536, "steps": []},
        debugger,
        "session",
    )


class BrowserDriverTest(unittest.TestCase):
    def test_a_probe_returns_every_outcome_key_it_declares(self):
        body = {
            "verdict": "reflected",
            "node_count": 1,
            "marker_in_text": False,
        }
        debugger = Debugger(
            {
                "Runtime.evaluate": {
                    "result": {"value": json.dumps(body, separators=(",", ":"))}
                }
            }
        )
        step = {
            "ordinal": 4,
            "arguments": {"probe": "markup_injection"},
            "javascript": "registry-owned",
            "verdicts": ["reflected", "escaped", "absent"],
            "outcome_keys": ["verdict", "node_count", "marker_in_text"],
            "artifact": "probe-4.json",
        }

        with tempfile.TemporaryDirectory() as root, mock.patch.object(
            browser_driver, "WORKSPACE", root
        ):
            answer = mission(debugger).probe(step)

        self.assertEqual(body, answer)

    def test_a_probe_refuses_a_field_its_registry_did_not_declare(self):
        debugger = Debugger(
            {
                "Runtime.evaluate": {
                    "result": {
                        "value": json.dumps(
                            {"verdict": "reflected", "timestamp": "now"}
                        )
                    }
                }
            }
        )
        step = {
            "ordinal": 1,
            "arguments": {"probe": "bounded"},
            "javascript": "registry-owned",
            "verdicts": ["reflected", "absent"],
            "outcome_keys": ["verdict"],
            "artifact": "probe-1.json",
        }

        with tempfile.TemporaryDirectory() as root, mock.patch.object(
            browser_driver, "WORKSPACE", root
        ):
            with self.assertRaisesRegex(browser_driver.Refused, "undeclared timestamp"):
                mission(debugger).probe(step)

    def test_a_cookie_inventory_never_keeps_a_value(self):
        secret = "rk-cookie-secret"

        def runtime(parameters):
            if parameters.get("expression") == "window":
                return {"result": {"objectId": "window-1"}}
            return {"result": {"value": "https://app.example.com"}}

        debugger = Debugger(
            {
                "Runtime.evaluate": runtime,
                "Runtime.callFunctionOn": {
                    "result": {"value": "https://app.example.com"}
                },
                "Storage.getCookies": {
                    "cookies": [
                        {
                            "name": "__Host-session",
                            "value": secret,
                            "domain": "app.example.com",
                            "path": "/",
                            "httpOnly": True,
                            "secure": True,
                            "sameSite": "Lax",
                        }
                    ]
                },
            }
        )
        step = {
            "ordinal": 3,
            "arguments": {"kind": "cookies"},
            "artifact": "client-state-3.json",
        }

        with tempfile.TemporaryDirectory() as root, mock.patch.object(
            browser_driver, "WORKSPACE", root
        ):
            run = mission(debugger)
            answer = run.read_client_state(step)
            kept = Path(root, step["artifact"]).read_text()

        self.assertEqual({"entries": 1}, answer)
        self.assertNotIn(secret, kept)
        self.assertNotIn('"value"', kept)
        self.assertEqual("__Host-", json.loads(kept)["entries"][0]["prefix"])
        self.assertEqual("cookies", run.artifacts[0]["output_name"])

    def test_message_listener_inventory_is_closed_to_message_events(self):
        debugger = Debugger(
            {
                "Runtime.evaluate": {"result": {"objectId": "window-1"}},
                "Runtime.callFunctionOn": {
                    "result": {"value": "https://app.example.com"}
                },
                "DOMDebugger.getEventListeners": {
                    "listeners": [
                        {"type": "click", "scriptId": "1"},
                        {"type": "message", "scriptId": "2", "lineNumber": 7},
                    ]
                },
            }
        )

        self.assertEqual(
            [{"type": "message", "useCapture": False, "passive": False,
              "once": False, "scriptId": "2", "lineNumber": 7,
              "columnNumber": None}],
            mission(debugger)._client_state("message_listeners"),
        )

    def test_send_message_posts_only_the_registry_body_to_the_current_origin(self):
        body = {"redkraken": "listener_inventory_probe"}

        def called(parameters):
            self.assertEqual([{"value": body}], parameters["arguments"])
            self.assertIn("window.location.origin", parameters["functionDeclaration"])
            return {"result": {"value": True}}

        debugger = Debugger(
            {
                "Runtime.evaluate": {"result": {"objectId": "window-1"}},
                "Runtime.callFunctionOn": called,
            }
        )

        run = mission(debugger)
        run.results.append(
            {"action": "read_client_state", "outcome": {"entries": 1}}
        )
        self.assertEqual({"matched": True}, run.send_message({"message_body": body}))

    def test_send_message_refuses_an_empty_listener_inventory(self):
        debugger = Debugger({})
        run = mission(debugger)
        run.results.append(
            {"action": "read_client_state", "outcome": {"entries": 0}}
        )

        with self.assertRaisesRegex(browser_driver.Refused, "non-empty"):
            run.send_message({"message_body": {"redkraken": "probe"}})

        self.assertEqual([], debugger.calls)

    def test_attach_enables_every_read_domain(self):
        debugger = Debugger(
            {
                "Target.createTarget": {"targetId": "target"},
                "Target.attachToTarget": {"sessionId": "session"},
                **{
                    f"{domain}.enable": {}
                    for domain in (
                        "Page", "Runtime", "Network", "Log", "DOMStorage",
                        "IndexedDB", "ServiceWorker",
                    )
                },
            }
        )

        self.assertEqual("session", browser_driver.attach(debugger))
        self.assertEqual(
            {
                "Page.enable", "Runtime.enable", "Network.enable", "Log.enable",
                "DOMStorage.enable", "IndexedDB.enable", "ServiceWorker.enable",
            },
            {method for method, _, _ in debugger.calls if method.endswith(".enable")},
        )


if __name__ == "__main__":
    unittest.main()
