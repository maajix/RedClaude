# Rust sinks

Read `code-review.md` first: a match here is a reason to ask a question, never
an answer.

An Artifact of this kind is usually a Cargo workspace, or the strings and panic
messages recovered from a compiled binary, which keep crate names, source paths
and format strings. `Cargo.toml` and `Cargo.lock` say which framework and which
versions, and that decides several of the entries below.

Rust removes memory-safety classes and removes none of the injection classes.
A safe language with a `format!` inside a query is the same query.

Sources are an Axum extractor (`Query`, `Path`, `Json`, `Form`, `HeaderMap`),
an Actix `web::Query`/`web::Json`, a Rocket route parameter, and anything the
handler pulls out of `Request` directly.

## injection.query_language

* `sqlx::query(&format!("... {} ...", user))`, which is the plain form: the
  `query!` macro checks against the schema at compile time and cannot take a
  runtime string, so a `format!` is the signal that the macro was abandoned.
* `diesel::sql_query` with an interpolated string, and `sql_literal`.
* SeaORM `Statement::from_string` built by concatenation.

Safe form: `sqlx::query("... $1 ...").bind(value)`, the `query!` macro,
Diesel's DSL.

## injection.command

* `Command::new("sh").arg("-c").arg(user)`, and any single-argument form that
  reaches a shell.
* `Command::new(user)`, where the program itself is chosen by input.

Safe form: a fixed program with `.arg(value)` per argument, which does not use
a shell.

## injection.path

* `Path::join` and `PathBuf::push` with a value from input. Both *replace* the
  whole path when the pushed component is absolute, which is stronger than the
  `..` case and easier to miss.
* `fs::read`, `File::open`, `tokio::fs` and `NamedFile::open` over input.
* `tower_http::services::ServeDir` or `actix_files::Files` mounted with
  `show_files_listing` or over a directory that also holds configuration.
* An archive crate extracting an entry by its stored name.

Safe form: `canonicalize()` then `starts_with(root)` on the canonical root,
with `Component::Normal` filtering where a name is all that is wanted.

## injection.request_forgery

* `reqwest::get(user_url)` and `Client::get(user_url)`. The default redirect
  policy follows up to ten hops, so the host that was checked is not
  necessarily the host that answered.
* `Url::parse` treated as validation, which reports that a string parsed.

Safe form: `redirect::Policy::none()`, an allow-list applied to the resolved
address, and a pinned scheme.

## injection.markup

* Askama's `{{ x|safe }}` and Tera's `{{ x | safe }}`, which turn escaping off
  for that value.
* `maud::PreEscaped`, and Yew's `dangerously_set_inner_html`.
* Writing a response body with `format!` and an HTML content type, which has no
  escaping at all.

Safe form: a template engine at its defaults, with the value passed as context.

## injection.document_parser

* `serde_yaml` and `bincode` over untrusted bytes, and any `Deserialize` into an
  untagged or internally tagged enum that admits more shapes than intended.
* `quick-xml` or `roxmltree` configured to expand entities, which is the XXE
  shape; both refuse external entities by default, so a line enabling them is
  the finding.
* `serde_json::Value` accepted and then indexed by field name, which is
  schema-less parsing wearing a typed API.

Safe form: `#[serde(deny_unknown_fields)]` on a concrete struct.

## authentication.credential_verification

* `jsonwebtoken::decode` with `Validation` whose `algorithms` were widened, and
  `insecure_disable_signature_validation`.
* `==` on a token or MAC, against a constant-time comparison
  (`subtle::ConstantTimeEq`, `ring::constant_time::verify_slices_are_equal`).
* `rand::random` or `thread_rng` for a token, against `rand::rngs::OsRng` or
  `getrandom`.

## transport.tls_configuration

* `reqwest::ClientBuilder::danger_accept_invalid_certs(true)` and
  `danger_accept_invalid_hostnames(true)`.
* A `rustls` `ServerCertVerifier` implementation whose `verify_server_cert`
  returns `Ok` unconditionally, which is the same hole written by hand.

## information_disclosure.error_detail

* `format!("{:?}", err)` or `{:#?}` returned in a response body, which prints
  the whole error chain including a connection string or a path.
* `unwrap`, `expect` and a panic reaching a handler with backtraces enabled
  (`RUST_BACKTRACE=1` in a container image), which returns source paths.

## Memory safety, and where `unsafe` matters

An `unsafe` block is not a finding. It is the only place in a Rust tree where
the classes this harness does not model can exist, so it is worth naming when
it is reachable from a handler:

* `from_utf8_unchecked`, `get_unchecked`, `slice::from_raw_parts` and
  `mem::transmute` over lengths or bytes derived from input.
* An `as` cast that truncates a length, and arithmetic that wraps in release
  where it would panic in debug.

## What a match is not

Rust's type system means most parsing errors become a 400 rather than a
vulnerability, and its defaults are safe more often than the other packs'. A
match here is therefore usually a deliberate opt-out, which makes it worth
reading the surrounding lines for the reason before proposing anything.
