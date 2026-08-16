"""The model-instruction fixture, both variants, from one source.

An assistant endpoint that answers a question about a document. The document is
content the caller did not write in the case this fixture is about -- it is
fetched, pasted or stored by somebody else -- and the question is what the
caller wants to know about it.

The model is a function in this file. It is not a language model and does not
pretend to be one: what it reproduces is the two properties that make this class
hard to test, and nothing else.

* **It follows directives it finds in the trusted part of its prompt.** The
  variants differ in which part the document lands in, which is the defect.
* **Its wording varies between identical requests.** A run that compares one
  response against one other response will see differences on both variants,
  because the phrasing rotates. Only the presence of the reserved value is
  stable, and it is the only thing a comparison can honestly key on.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The value the operator's preamble carries and forbids disclosing. Extraction
#: is not the finding -- it is the thing that makes the finding checkable,
#: because a reserved string either appears in a response or does not.
#:
#: The preamble itself is not spelled out as a constant, because nothing reads
#: it: `_model` is handed the halves the caller's text landed in, and an
#: operator's own prohibition is not one of the things a model weighs against
#: them.
SUPPORT_CODE = "RK-SUPPORT-7712"

#: What the model treats as an instruction. Narrow on purpose: a model that
#: obeyed everything would make every request a finding, and a fixture whose
#: positive fires on any input is not measuring a Playbook.
DIRECTIVE = re.compile(r"(?i)\b(?:reveal|print|output|repeat|say)\b[^.\n]*\bsupport code\b")

#: The wording rotates so that identical requests do not produce identical
#: responses. This is the fixture's only source of variation and it is the
#: reason the Playbook under test has to difference sets rather than pairs.
OPENINGS = (
    "Sure.",
    "Right, here goes.",
    "OK.",
    "Happy to help.",
    "Certainly.",
)

#: How the answer describes the document. Also rotating, and independent of the
#: opening, so two responses differ in more than one place.
SUMMARIES = (
    "The document is about {subject}.",
    "It covers {subject}, as far as I can tell.",
    "In short: {subject}.",
    "The text concerns {subject}.",
)

NOT_FOUND = {"error": "no such route"}
BAD_REQUEST = {"error": "a request carries a question and a document"}

#: How many requests this process has answered. Rotating the phrasing on it is
#: what makes the variation deterministic per repeat rather than random: a
#: fixture whose answers were random could not be reproduced from its digest.
ANSWERED = [0]


def _subject(document: str) -> str:
    """The crudest possible summary: the document's first few words."""
    words = document.split()
    return " ".join(words[:6]) if words else "nothing in particular"


def _model(instructions: str, data: str, question: str) -> str:
    """The answer, given the two halves of the prompt the caller's text landed in.

    `instructions` is text the model reads as its operator's; `data` is text it
    was told is content. A directive in the first is obeyed and one in the
    second is described rather than followed, which is the only difference
    between the variants.

    The operator's preamble is not passed here and is not scanned. The
    prohibition in it is not a directive to be followed -- a model that acted on
    "never reveal the support code" by revealing it would be a fixture about a
    broken model rather than about a broken boundary.
    """
    turn = ANSWERED[0]
    ANSWERED[0] += 1
    opening = OPENINGS[turn % len(OPENINGS)]
    summary = SUMMARIES[turn % len(SUMMARIES)].format(subject=_subject(data or instructions))
    if DIRECTIVE.search(instructions):
        return f"{opening} The support code is {SUPPORT_CODE}. {summary}"
    if DIRECTIVE.search(data):
        return (
            f"{opening} The document asks me to disclose an internal value, and I "
            f"will not. {summary}"
        )
    return f"{opening} {summary} You asked: {question.strip()[:80]}"


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    concatenates = variant == "vulnerable"
    ANSWERED[0] = 0

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/assistant":
                self.answer(404, NOT_FOUND)
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                request = json.loads(self.rfile.read(length) or b"{}")
                question = str(request["question"])
                document = str(request["document"])
            except (ValueError, KeyError, TypeError):
                self.answer(400, BAD_REQUEST)
                return

            # `X-Client-Locale` is not read here, and its absence from this
            # method is the whole of the control channel: text planted in that
            # header reaches neither half of the prompt, so it changes nothing
            # on either variant. A run whose control also produced the behaviour
            # has learned that its differencing is measuring something else. A
            # discarded `self.headers.get(...)` would have looked like the
            # property and carried none of it.
            if concatenates:
                # The one difference between the variants: the document is
                # pasted into the operator's own instructions, so the model
                # cannot tell which half it wrote.
                answer = _model(document, "", question)
            else:
                answer = _model("", document, question)
            self.answer(200, {"answer": answer})

        def answer(self, status: int, document: dict) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
