# Python sinks

Read `code-review.md` first: a match here is a reason to ask a question, never
an answer.

An Artifact of this kind is usually a Django, Flask or FastAPI tree, or a
handful of modules recovered from an exposed repository. Python routing is
explicit -- `urls.py`, a decorator, an `APIRouter` -- so the route table and the
parameter names are readable without running anything, and a view's signature
already says which parameters reach it.

Sources are `request.GET`, `request.POST`, `request.data`, `request.headers`,
`request.COOKIES`, `request.FILES`, a path converter, a Pydantic model field
typed loosely, and `os.environ` where it is filled from a request upstream.

## injection.command

* `os.system`, `os.popen`, `subprocess.run`/`call`/`Popen`/`check_output` with
  `shell=True`, `commands.getoutput` on legacy trees.
* `shlex.quote` applied to a whole command string rather than to one argument.

Safe form: a list argument with `shell=False`, which is the default. A list is
not enough when the program takes a command of its own (`bash -c`, `ssh`,
`git` with `-c`).

## injection.template

* `eval`, `exec`, `compile` over request text.
* `flask.render_template_string`, `jinja2.Template(user).render`,
  `django.template.Template(user)`, Mako `Template(user)`.
* Jinja given a template name from input, which is a path sink as well.

Safe form: a template loaded by name from the application's own loader, with
input passed as context.

## injection.query_language

* `cursor.execute` with `%`, `+`, `.format` or an f-string.
* Django `.extra(where=[...])`, `RawSQL`, `Model.objects.raw`, and `order_by`
  or `values` given a field name from input.
* SQLAlchemy `text()` around an interpolated string, `filter` with a literal
  clause built by concatenation.

Safe form: parameters passed as the second argument to `execute`, SQLAlchemy
bind parameters, an ORM filter given values. Note that `LIMIT`, `ORDER BY` and
identifiers cannot be parameterised, so those need an allow-list rather than a
placeholder.

## injection.path

* `open`, `send_file`, `send_from_directory`, `FileResponse` or `pathlib.Path`
  built from input. `os.path.join(root, user)` returns `user` when `user` is
  absolute, so an absolute value replaces the root entirely.
* `tarfile.extractall` and `zipfile.extractall` without a filter, which trusts
  entry names.
* `django.views.static.serve` mounted in production.

Safe form: `os.path.realpath` followed by a prefix check, `send_from_directory`
with a fixed directory and a name validated against a pattern, or
`tarfile.extractall(filter="data")`.

## injection.request_forgery

* `requests.get`, `httpx`, `urllib.request.urlopen`, `aiohttp` with a URL from
  input. `urlopen` also accepts `file://` and `ftp://`, so the scheme is part of
  the sink.
* A URL validated before a redirect is followed, which validates a host the
  request may never reach.

Safe form: an allow-list checked after resolution, redirects disabled, the
scheme pinned.

## injection.document_parser

Deserialisation lives here: a parser that turns bytes into objects is the
document parser class even when the bytes are not a document.

* `pickle.loads`, `dill`, `shelve`, `marshal.loads`, `jsonpickle.decode`.
* `yaml.load` without `Loader=SafeLoader`, and `yaml.unsafe_load`.
* `xml.etree.ElementTree`, `xml.dom.minidom`, `xml.sax` and `lxml.etree` with
  `resolve_entities=True`, which is lxml's default.
* `xmlrpc.client` against a host from input.

Safe form: `json.loads` into a validated schema, `yaml.safe_load`,
`defusedxml`, or lxml with an `XMLParser(resolve_entities=False,
no_network=True)`.

## injection.markup

* Django `mark_safe`, `|safe`, `{% autoescape off %}`, `format_html` with a
  pre-built string.
* Jinja `|safe`, `Markup(user)`, or an environment created without
  `autoescape=True`, which is the default for a bare `Environment`.

Safe form: default escaping, with `Markup` applied only to text the application
composed.

## information_disclosure.error_detail

* `DEBUG = True` in a settings module, and the Werkzeug debugger, which offers
  an interactive console on an unhandled exception.
* A handler returning `str(exception)` or a traceback in the response body.
* `ALLOWED_HOSTS = ["*"]`, which removes the check that keeps a debug page from
  answering an arbitrary Host.

## information_disclosure.artifact_exposure

* A literal `SECRET_KEY`, database URL or API token in a settings module. In
  Django a known `SECRET_KEY` is a signing key, so it is not only a secret but
  a forgery primitive.
* A committed `.env`, a `settings_local.py` in the tree, or a static mount that
  covers the project root.

## authentication.credential_verification

* A password compared with `==` rather than `hmac.compare_digest`.
* A token derived from `random` rather than `secrets`, which is a predictable
  identifier and not a secret.

## session_handling.csrf

* `@csrf_exempt`, `CsrfViewMiddleware` removed from the middleware list, or a
  DRF view whose authentication is session-based with no CSRF enforcement.

## transport.tls_configuration

* `verify=False` on a `requests` call, `ssl._create_unverified_context`,
  `ssl.CERT_NONE`, or `urllib3.disable_warnings` used to silence the message
  that verification is off.

## What a match is not

Python trees recovered from an exposed repository are often the deployment's
ancestor rather than the deployment. A sink in a file the running service does
not import is a fact about the repository, and saying which one is running
needs an exchange.
