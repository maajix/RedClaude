# PDF generators: a headless browser somebody forgot was there

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The observation that "export to PDF" is usually a browser. Anywhere a target
renders caller-influenced HTML into a document -- an invoice, a report, a
certificate, a shipping label -- there is wkhtmltopdf, headless Chrome, Puppeteer,
Playwright, PrinceXML or a Java library, running on the target's network, fetching
whatever the HTML references.

So: get HTML into the document. An `<iframe src="file:///etc/passwd">` to read
files. An `<img src="http://169.254.169.254/...">` to reach the metadata service.
An `<script>` that fetches an internal URL and writes the response into the page,
so the PDF itself carries the exfiltrated body. XHR from the renderer, since it
runs with whatever origin the generator gave it. The page also covered the
XSS-to-SSRF pivot: an injected script in a stored field that only fires when
somebody exports.

## Why the Playbook does not run it

**The targets are the same forbidden targets.** `file://`, loopback, the metadata
address, internal ranges. Everything the SSRF reference says applies unchanged;
the renderer is just a different way to ask.

**The output carries the loot.** The technique's payoff is a PDF containing the
fetched content. That means the exfiltrated file, credential or internal page is
now a document in the target's own storage, generated under a real user's
account, sitting in whatever pipeline that document normally goes to -- an email,
an invoice archive, a customer's inbox.

**Stored HTML is a mutation with a delayed fuse.** Putting an `<iframe>` into an
invoice field to see what the exporter does leaves markup in a business record
that renders whenever anyone exports it, including people who are not in the
engagement, days later.

**Renderers are heavy.** A payload that makes headless Chrome fetch a slow
resource holds a worker for the timeout, and a handful of them is a capacity
problem on the target's rendering fleet.

## What is kept

The surface insight, and it is a good one: a URL-valued parameter is not the only
way a server fetches. A generator, a thumbnailer, a link unfurler, an importer, a
webhook and a preview all fetch, and several of them take their URL out of
content rather than out of a parameter.

That matters for `file-upload` too, whose neighbour note points at
`command-directory-injection` for exactly this reason: the uploaded document's
name and content reach a converter.

Where a Program has a renderer and an operator wants it examined, the reachable
question under this corpus's ceilings is narrow: does a reference in the rendered
document to a host the *Program controls* end up fetched? That is the arrival
question, which is `webhooks` and a correlator, and it requires an approval
because it stores content on the target.

## The trap in the whole technique

Everything the renderer does happens out of band, so attribution is guesswork
unless every reference carries a per-request token. Exports get triggered by
background jobs, by other users, by retries, and by the target's own QA. A fetch
that arrives is not necessarily the one this reading caused, and a PDF that comes
back without the content may simply have been generated before the field was
saved.
