# 77 — Evaluate carbonyl as a terminal browser for the Agent

**What to build:** An answer, on record, to whether an Agent can navigate a target and extract data through [carbonyl](https://github.com/fathyb/carbonyl) — and, if it can, whether that buys this harness anything the browser slice it already has does not.

**Blocked by:** 31 — Run a browser entirely through the proxy.

**Status:** resolved

- [x] A carbonyl build runs on this host under `isolation`, and the exact route to it is written down: image or binary, version, and the command line that started it.
- [x] The question "can an Agent navigate" is answered by a transcript rather than by an opinion: a run that reaches a page, follows a link, submits a form and reports what it saw, or a named reason it cannot.
- [x] The question "can an Agent extract data" is answered the same way: text, links and one form's fields off a rendered page, in a shape a Tool run could file, or a named reason it cannot.
- [x] Every byte carbonyl sends crosses the door and earns a Receipt, or the evaluation records that it cannot and stops there. A browser that reaches a target another way is refused by ticket 11 whatever else it can do.
- [x] The comparison against the slice this repo already has is written as a table of what each can do, not as a preference.
- [x] A decision is recorded — adopt, adopt for one named job, or decline — with the reason, as an ADR under `docs/adr/`. Declining is a result and closes this ticket.
- [x] No production code path depends on carbonyl unless the decision is adopt. A spike lives under `/tmp` or is deleted.

## What was built

Nothing in the tree, which is the answer. `docs/adr/0004-carbonyl-is-not-adopted-as-a-terminal-browser.md`
records the decision and the measurements it rests on; the spike that produced
them lived under `/tmp` and is gone, as criterion 7 asks.

**The premise the ticket flagged as worth checking rather than assuming was
wrong, and in carbonyl's favour.** `fathyb/carbonyl:latest`, digest
`sha256:77b3686f46a16375004985b522cef8f66e27fabc4a7d80209609bbb20fdfb362`,
`Carbonyl 0.0.3` over `Google Chrome/111.0.5511.1`, takes `--remote-debugging-port`
and serves ordinary CDP with no pty attached at all. So question 1 answers yes
without a pty puppet: one run over that socket reached a fixture, clicked a real
anchor, submitted a form and read the result off the live DOM, and text, links
and field lists came back in the JSON shapes the browser action already files.

**Question 2 answers yes too, by the mechanism ticket 31 already built.** On an
`--internal` network whose only other peer was a proxy holding a self-signed
leaf, carbonyl honoured `--proxy-server` and the SPKI pin exactly as
`headless-shell` does; the page loaded, which on a network with no other route
is proof every byte crossed the one peer, and the proxy saw a bare `CONNECT`
with no `Proxy-Authorization` -- the same gap the loopback shim closes, reusable
unchanged. No Receipt was earned and none could be: a Receipt is the door's
record against a Program, and an evaluation outside an engagement has neither.
That is criterion 4's second half rather than its first, and it is recorded
rather than worked around.

**Question 3 decides it, and it fails through both interfaces.** Through CDP,
`Page.captureScreenshot` returns a fixed 161x93 pixel blank PNG whatever
`--window-size` says, so the capture path this repo uses for canvas, WebGL and
video evidence comes back empty. Through this installation's own containment it
is worse: `isolation.run_tool` with `--headless --dump-dom` against a mounted
`file://` page got both flags ignored, roughly 33 KB of escape codes on stdout
and no exit -- the run ended at its 90-second ceiling with exit code -9, holding
a picture of the words instead of the words. The same container answered
`--version` with exit code 0, so what refused was carbonyl's rendering model,
not the fence.

The comparison table is in the ADR. The short form: identical DOM access,
identical borrowed proxy behaviour, a Chromium roughly forty major versions
older, a broken screenshot, and the one output carbonyl exists to produce living
on a channel neither CDP nor a bounded tool run can read.

## Why this is asked

The operator found it and asked. The premise worth testing is that a browser
which renders to a terminal might be a better fit for an Agent than one which
renders to a framebuffer nobody looks at: the output is already text, so the
step between "the page rendered" and "the model can read it" might disappear.

## What is already here, so the comparison is against the real thing

Ticket 31 is resolved and this repo drives a browser today. What it is:

- `src/redkraken/browser_driver.py` speaks the **Chrome DevTools Protocol** over
  a websocket it frames by hand, against `/headless-shell/headless-shell` inside
  a container. There is no Playwright and no Selenium — `pyproject.toml` says
  `dependencies = []` and a startup assertion holds it there.
- The container gets a `--internal` network from `isolation.run_tool(network="proxy")`
  whose only peer is the door, with DNS blackholed. Chromium cannot send
  `Proxy-Authorization: RedKraken <hex>` itself, so the driver runs a loopback
  shim that puts the control headers on the hop the door reads.
- `check_browser_runs` holds the count of requests the driver reported against
  the count of Receipts the door wrote. Fewer Receipts than requests is a fault.
- DOM, screenshot, console and probe output become content-addressed Artifacts
  linked to the Receipts behind them.

So the bar is not "carbonyl can browse". The bar is "carbonyl can browse under
that fence, and produces evidence at least as attributable".

## What is known about carbonyl before the work starts

From its own README, so that nothing below is guessed:

- Chromium-based, with a Rust rendering layer, drawing the page into a terminal.
- **BSD-3-Clause**, **v0.0.3**, and the README documents **no command-line flags,
  no headless mode and no automation API**. That absence is the first thing to
  check rather than the first thing to assume — the source is there to read, and
  a Chromium fork usually still honours `--remote-debugging-port`.
- Runs as `docker run --rm -ti fathyb/carbonyl https://youtube.com`, or as an
  npm global `carbonyl <url>`. The `-ti` is the shape of the problem: it is
  built for a human at a TTY, and an Agent is not one.

## The three questions, in the order they decide the ticket

1. **Is it drivable at all without a human at the keyboard?** Either it exposes
   the DevTools Protocol, in which case this repo already has a client for it
   and the interesting part is the rendering, or it does not, in which case
   driving it means writing keystrokes into a pty and reading the frames back.
   Say which, with the evidence.
2. **Can it be fenced?** A Chromium fork takes Chromium's proxy flags, but that
   has to be shown, not assumed, and the capability header problem from ticket 31
   does not go away. If the shim can be reused, say so; if not, this is a much
   larger ticket than a research one and should end in a follow-up rather than
   a hack.
3. **Does the terminal rendering actually buy anything?** This is where a "yes"
   to the first two still might not matter. What an Agent reads today is the DOM
   and the CDP's own answers, which are already text and already structured.
   ANSI cells are text a human reads, and a model reading them gets a page that
   has been through a layout engine and a downsampler. The honest case for
   carbonyl is the page a DOM does not describe — canvas, WebGL, a video frame,
   a widget drawn rather than marked up — and that is the case to test.

## What "no" looks like, and why it is fine

An npm package at v0.0.3 with no documented automation surface is not something
to put on the path an unattended campaign depends on. If the answer is that it
needs a pty puppet to drive and gives back a downsampled picture of a DOM the
harness could already read, then the answer is decline, and the value of this
ticket is that nobody has to wonder again.

## Note on the number

The tracker numbers are append-only and other files cite them, so this sits at
77 because 76 was the last one taken. Topically it belongs next to 31, and the
`Blocked by` line is what carries that.
