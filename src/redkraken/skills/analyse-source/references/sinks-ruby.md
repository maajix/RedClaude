# Ruby sinks

Read `code-review.md` first: a match here is a reason to ask a question, never
an answer.

An Artifact of this kind is usually a Rails tree, a Sinatra service, or a gem.
In Rails `config/routes.rb` is the route table and it is worth reading first:
`resources` generates seven routes per line, and a `match` or a route with
`:action` in the path is a much wider surface than the file's length suggests.
`Gemfile.lock` gives exact versions, which decides whether several of the sinks
below are still sinks.

Sources are `params`, `request.headers`, `request.env`, `cookies`,
`session`, and a JSON body parsed into `params` -- which in Rails is the same
object as the query string, so a value that looks like a form field may have
arrived anywhere.

## injection.command

* Backticks, `%x{}`, `system`, `exec`, `spawn`, `Open3.capture*` and
  `IO.popen` given one string, which is a shell string.
* `Kernel#open` and `IO.read`/`IO.foreach` with a value beginning `|`, which
  runs the rest as a command. This is the sink that does not look like one:
  `open(params[:file])` reads as a file operation.

Safe form: a multi-argument form (`system("convert", src, dst)`), and
`File.read` rather than `open` when a file is what is meant.

## injection.template

* `eval`, `instance_eval`, `class_eval` and `module_eval` over input.
* `send` and `public_send` with a method name from input, which reaches every
  method the object has, and `__send__` on a receiver chosen by input.
* `constantize`, `safe_constantize` and `const_get` over input, which is how a
  parameter becomes a class.
* `ERB.new(user).result(binding)`, and a Slim, Haml or Liquid template compiled
  from input.
* `render inline: params[:x]`, which compiles ERB.

Safe form: a hash mapping an input token to a fixed symbol or class.

## injection.query_language

* A string interpolation inside `where`, `find_by_sql`, `exists?`, `joins`,
  `having`, `group`, `lock` or `select`: `where("name = '#{params[:n]}'")` is
  the whole shape.
* `order(params[:sort])` and `pluck(params[:col])`, which take SQL fragments
  rather than values.
* `sanitize_sql` applied to an already-built string.

Safe form: `where("name = ?", value)` or `where(name: value)`, and an
allow-list for a sort column.

## injection.document_parser

Deserialisation lives here: a parser that turns bytes into objects is the
document parser class even when the bytes are not a document.

* `Marshal.load` over anything from a request, a cookie or a cache.
* `YAML.load` on Psych below 4, and `YAML.unsafe_load` at any version;
  `YAML.load_file` over an uploaded file is the same call.
* `JSON.load`, which is not `JSON.parse`: it revives objects through
  `create_additions`.
* Nokogiri parsed with `Nokogiri::XML(doc) { |c| c.noent }`, which turns
  entity expansion back on.

Safe form: `JSON.parse`, `YAML.safe_load` with an explicit permitted-class
list, Nokogiri at its defaults.

## injection.path

* `File.read`, `File.open`, `send_file` and `IO.read` over `params`.
* `render file: params[:x]`, and `render template:` with input, which reaches
  any template the application can see.
* Rails `send_file` with `disposition: 'inline'` and a type from input, which
  makes the response's rendering the attacker's choice.

Safe form: `File.expand_path` then a prefix check against the canonical root,
with `File.basename` where only a name is wanted.

## injection.markup

* `raw`, `html_safe`, `<%== %>`, and `sanitize` configured with extra tags or
  attributes.
* `link_to` with a `href` from input, which admits `javascript:`.
* A value interpolated into a `<script>` block, where `html_safe` is the wrong
  question entirely.

Safe form: `<%= %>`, which escapes, and `json_escape`/`to_json` for a value
that must land in script.

## authorization.state_transition

* `params.permit!` and `params.require(:x).permit!`, which admit every
  attribute including `admin`, `role_id` and `user_id`. This is the
  mass-assignment shape, and in Rails it is a one-word diff.
* `update(params[:user])` on a model with an ownership column.
* `find(params[:id])` with no ownership scope, against
  `current_user.orders.find(params[:id])`.

## Anchors, which decide whether the classes above are reachable

A validation regular expression anchored with `^` and `$` matches a *line* in
Ruby, not the string, so `"good\nevil"` passes a `^\w+$` check. `\A` and `\z`
are the string anchors.

This is not a class of its own. It is the reason a sink above is reachable when
the tree looks like it validates, so it is recorded as the path to whichever
class the sink carries -- and it is here rather than in the other packs because
the anchor characters mean something different in Ruby than they do in most of
them.

## session_handling.csrf

* `skip_before_action :verify_authenticity_token`, and
  `protect_from_forgery with: :null_session`, which does not reject a forged
  request -- it empties the session and continues, so a token-authenticated
  API still acts.

## information_disclosure.artifact_exposure

* `config/master.key`, `config/credentials.yml.enc` beside its key, or a
  `secret_key_base` literal. In Rails that key signs cookies, so disclosure is
  a session forgery primitive.
* `config.consider_all_requests_local = true` outside development, which
  returns the full error page.

## What a match is not

Rails does a great deal by convention, so an absent line is often the finding
and a present line is often the framework's default doing its job. Say which
version `Gemfile.lock` names before treating a historical sink as a live one.
