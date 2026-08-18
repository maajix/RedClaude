# Carbonyl is not adopted: what it renders is unreachable from what drives it

Carbonyl is a Chromium build that paints a page into a terminal as ANSI escape
codes. Ticket 77 asked whether an Agent can navigate and extract through it, and
whether that buys this harness anything the browser slice it already has does
not. It can navigate, it can extract, and it buys nothing. Declined.

Two of the ticket's three questions resolved in carbonyl's favour, and the
working assumption behind them turned out to be wrong in carbonyl's favour too:
the image is not a pty puppet. `fathyb/carbonyl:latest`, digest
`sha256:77b3686f46a16375004985b522cef8f66e27fabc4a7d80209609bbb20fdfb362`,
reports `Carbonyl 0.0.3` over `Google Chrome/111.0.5511.1`, and its `--help`
says it takes most Chromium options. It does: started with
`--remote-debugging-port=9222 --remote-debugging-address=0.0.0.0` and no
terminal attached at all, it serves an ordinary CDP handshake. One run over that
socket reached a three-page fixture, clicked a real anchor rather than
navigating to its href, filled and submitted a form, and read the result back
off the live DOM. Text, links and a form's fields came back as the same JSON
shapes the existing browser action already files as an Artifact. Chromium
prints `Failed to setup terminal: Inappropriate ioctl for device` to stderr
without a pty and keeps running.

Egress is fenceable by the mechanism this repository already built. On a
`--internal` network whose only other peer was a proxy holding a self-signed
leaf, carbonyl honoured `--proxy-server` and `--ignore-certificate-errors-spki-list`
exactly as `chromedp/headless-shell` does, and the page loaded -- which on a
network with no other route is proof that every byte crossed the one peer. The
proxy's log shows a bare `CONNECT` with no `Proxy-Authorization`, which is the
same gap ticket 31 closed with a loopback shim, unchanged and reusable. No
Receipt was earned in this evaluation and none could be: a Receipt is filed by
the door against a Program, and an evaluation that runs outside an engagement
has neither. What was measured is the boundary behaviour the door depends on,
not the door.

The third question is the one that decides it, and it fails twice over. Through
CDP, `Page.captureScreenshot` returns a fixed 161x93 pixel, roughly 330-byte
blank PNG whatever `--window-size` says, so the one capture path this repository
uses for canvas, WebGL and video evidence comes back empty. Through this
installation's own containment it is worse: run under `isolation.run_tool` with
`--headless --dump-dom` against a mounted `file://` page, carbonyl ignored both
flags, wrote roughly 33 KB of escape codes and cursor moves to stdout, and never
exited -- the run ended at its 90-second ceiling with exit code -9, and what the
bounded stream captured was a picture of the words rather than the words. The
same container answered `--version` with exit code 0, so the refusal is
carbonyl's rendering model and not the containment.

That is the whole finding. The channel carrying carbonyl's actual output is a
terminal frame on stdout that CDP cannot see and a one-shot tool run cannot
parse, and the channel an Agent can drive is a Chromium roughly forty major
versions behind the one already shipping here, with a broken screenshot. There
is no job left for it: adopting it even for a single named task would mean
building a pty-capture pipeline to reach evidence the existing slice already
gets from a working screenshot call.

## Consequences

- **The browser slice stands as it is.** Ticket 31's proxied `headless-shell`
  remains the only browser this harness drives, and no second browser path
  enters the tree.
- **The proxy finding is reusable and outlives the decline.** Any future
  Chromium-derived browser will need the loopback shim for the same reason:
  Chromium does not send `Proxy-Authorization` on its own, whatever build it is.
- **A terminal browser is not the way to reach a page a DOM does not describe.**
  If that requirement returns, the answer is a capture path off the rendering
  the browser already produces, not a browser that renders somewhere else.
- **Nothing was added to the tree, so nothing new can fail.** This decision is
  recorded here rather than in code, which is the honest form for a result that
  is "we looked, and no".
