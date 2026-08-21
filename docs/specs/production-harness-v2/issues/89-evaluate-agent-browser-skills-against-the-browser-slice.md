# 89 — Evaluate the agent-browser Skill set against the browser slice

**What to build:** An answer, on record, to whether [agent-browser](https://agent-browser.dev/) and the Skills it publishes at <https://agent-browser.dev/skills> buy this harness anything the browser slice it already has does not — and, if only the instructions are worth having, what a rewritten Skill of our own would say.

**Blocked by:** nothing. Ticket 31 built what this compares against and is resolved; ticket 87 owns the mechanism a rewritten Skill would run under and does not block reading one.

**Status:** ready-for-agent

- [ ] What agent-browser actually is, is written down before it is judged: publisher, licence, version, distribution (npm, brew, or a binary), the protocol it drives, and whether the daemon is separable from the CLI.
- [ ] The comparison against the slice this repo already has is a table of what each can do, not a preference.
- [ ] The fence question is answered with evidence, not assumption: whether it honours `--proxy-server` and an SPKI pin, and whether the capability header the door reads can be put on the hop without a second shim.
- [ ] The daemon question is answered: a process that outlives a command is answered against per-run containment, the Halt gate and the request budget, or the evaluation records that it cannot be and stops there.
- [ ] The Skill text is read on its own merits and the parts worth keeping are quoted, so that "adopt the instructions, not the binary" is a decision with content behind it.
- [ ] A decision is recorded — adopt, adopt the instructions only, adopt for one named job, or decline — with the reason, as an ADR under `docs/adr/` at `0005`. Declining is a result and closes this ticket.
- [ ] No production code path depends on agent-browser unless the decision is adopt. A spike lives under `/tmp` or is deleted.

## Why this is asked

The operator found it and asked. The premise worth testing is Vercel Labs' own
claim: **compact text output that minimises context usage**. This repo drives a
browser by hand over raw CDP and turns what comes back into Artifacts; if a
tool built for exactly this audience gives a model less to read for the same
facts, that is a real gain and not a matter of taste. The second premise is
cheaper and may be the whole of the value: a published Skill corpus is written
instructions for an agent, and instructions can be read, rewritten and kept
without ever installing the thing they describe.

## What is already here, so the comparison is against the real thing

Ticket 31 is resolved and this repo drives a browser today. What it is, in the
shape ticket 77 already set out and which nothing since has changed:

- `src/redkraken/browser_driver.py` speaks the **Chrome DevTools Protocol** over
  a websocket it frames by hand, against `/headless-shell/headless-shell` inside
  a container. There is no Playwright and no Selenium — `pyproject.toml` line 27
  says `dependencies = []` and a startup assertion holds it there.
- The container gets a `--internal` network from `isolation.run_tool(network="proxy")`
  whose only peer is the door, with DNS blackholed. Chromium cannot send
  `Proxy-Authorization: RedKraken <hex>` itself, so the driver runs a loopback
  shim that puts the control headers on the hop the door reads.
- `check_browser_runs` holds the count of requests the driver reported against
  the count of Receipts the door wrote. Fewer Receipts than requests is a fault.
- The actions are a closed set walked from a step list — `navigate`, `wait_for`,
  `screenshot` and the rest — and DOM, screenshot, console and probe output
  become content-addressed Artifacts linked to the Receipts behind them.
- `src/redkraken/skills/browser-evidence/` is the Skill an Agent reads to use
  that slice, and it sits beside five others in the same directory.

So the bar is not "agent-browser can browse". The bar is the one ticket 77 set:
it can browse **under that fence**, and produces evidence **at least as
attributable**.

## What is known before the work starts

From the project's own pages, so that nothing below is guessed:

- Published by **Vercel Labs**. Installed as an npm or brew package; the Skills
  are added with `npx skills add vercel-labs/agent-browser`.
- **100% native Rust**, a **client-daemon architecture**: a CLI talks to a
  daemon that manages Chrome over **CDP**. Headless by default, with headed,
  Safari and iOS WebDriver sessions also offered.
- The daemon **persists between commands**, with an idle timeout defaulting to
  one hour.
- 50+ commands across navigation, forms, screenshots, network, storage, files,
  tabs, frames and debugging. Proxy, network control and storage controls are
  claimed; **custom headers and TLS pinning are not mentioned**, which is the
  first thing to check rather than the first thing to assume.
- The Skills are readable without installing anything that drives a browser:
  `agent-browser skills get <name> --full`, and `core`, `dogfood`,
  `derive-client`, `electron`, `slack`, `vercel-sandbox`, `agentcore` are the
  names published.
- **Licence and version are not stated on the pages read.** They are criterion 1
  and have to come from the repository.

## The four questions, in the order they decide the ticket

1. **Does it clear the fence?** It is Chromium underneath, so `--proxy-server`
   and an SPKI pin are likely to work exactly as they did for carbonyl. The part
   that is not likely is the capability header: the door reads
   `Proxy-Authorization: RedKraken <hex>`, Chromium will not send it, and
   agent-browser sits between us and the flags. If the ticket 31 shim can be
   reused unchanged, say so; if driving it means a second shim or a patched
   daemon, that is a larger ticket than a research one.
2. **Can a daemon live inside this containment?** This is the question carbonyl
   never had to answer. A process that outlives the command, holds a browser for
   an hour and is reachable by whatever else can see its socket is the opposite
   shape from `isolation.run_tool`, from ticket 86's one home per Agent run, and
   from a Halt that has to stop work already in flight. Either the daemon can be
   confined to one run's container and torn down with it, or it cannot, and the
   answer decides the ticket regardless of anything else.
3. **Is the accounting still ours?** `check_browser_runs` compares requests the
   driver reported against Receipts the door wrote, and that check only means
   something if the thing reporting the count is the thing making the requests.
   A CLI that summarises its own network activity is a second bookkeeper. Say
   whether the door's Receipt count can still be reconciled against what
   agent-browser did, or whether adopting it means trusting its report.
4. **Is the context saving real, and is it the binary's or the text's?** Measure
   it rather than repeat it: one page, one extraction, agent-browser's output
   against what `browser_driver` files today, in tokens. Then read the `core`
   and `derive-client` Skills and ask the separable question — is the saving in
   the Rust, or in a better-written instruction that our own
   `skills/browser-evidence/` could carry unchanged? The second answer is worth
   more than the first, because it costs one file and no dependency.

## The optional half, and what it would have to respect

The operator asked whether the instructions alone could be extracted and rebuilt
to fit. They could, and that is the likelier outcome, but the rebuild is not a
copy:

- Their Skills describe **their** 50+ verbs. Ours describe a closed action set
  walked from a step list. A rewritten Skill names our verbs or it is wrong.
- Anything a rewritten Skill tells an Agent to *run* is a Tool call the roster
  has to grant, and a script it runs is ticket 87's mechanism. Nothing here
  invents a second route to a shell.
- Licence first. Criterion 1 covers this deliberately: text is copyrightable and
  a rewritten Skill that is a paraphrase of an incompatibly licensed one is a
  problem no amount of rewording fixes. Establish the licence before quoting at
  length.

## What "no" looks like, and why it is fine

A persistent daemon, a second bookkeeper for egress, and an npm-installed Rust
binary on the path an unattended campaign depends on is a lot of new surface for
a browser this repo already drives. If the answer is that the fence and the
daemon do not fit and the only portable part is prose, then the answer is
decline the binary, keep what the prose taught, and the value of this ticket is
that nobody has to wonder again.

## Note on the number

The tracker numbers are append-only and other files cite them, so this sits at
89 because 88 was the last one taken. Topically it belongs next to 31 and 77.
