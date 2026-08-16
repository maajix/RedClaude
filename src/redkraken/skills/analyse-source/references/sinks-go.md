# Go sinks

Read `code-review.md` first: a match here is a reason to ask a question, never
an answer.

An Artifact of this kind is usually a module tree, or the strings recovered
from a compiled binary. A Go binary keeps package paths, struct field names and
format strings, so even without source the route strings, the module list and
often the framework are readable, and `jq` over a `go.mod` or a build-info dump
is a repeatable extraction.

Sources are `r.URL.Query()`, `r.FormValue`, `r.PostForm`, `r.Header`,
`r.Cookie`, `r.Body`, `mux.Vars(r)`, and a framework's own binder
(`c.Param`, `c.Query`, `c.ShouldBind`).

## injection.command

* `exec.Command("sh", "-c", input)` and `exec.CommandContext` with the same
  shape.
* A `fmt.Sprintf` result passed as a single argument to a program that parses
  its own command line.

Safe form: `exec.Command(program, arg1, arg2)`, which does not use a shell.

## injection.query_language

* `db.Query`, `db.Exec` or `QueryRow` given a `fmt.Sprintf` or a `+`
  concatenation.
* GORM `Raw`, `Exec`, and `Where` with a string built from input; `Order` and
  `Select` given a column name from input.
* `sqlx.In` misused, or a placeholder count assembled by hand.

Safe form: `?` or `$1` placeholders with arguments after the query string, and
an allow-list for column and direction names.

## injection.path

* `filepath.Join(root, r.URL.Path)`, which cleans `..` but does not confine: a
  path that climbs out of the root resolves outside it.
* `os.Open`, `os.ReadFile`, `http.ServeFile` and `http.ServeContent` over
  input. `http.ServeFile` refuses a request path containing `..`, and does not
  refuse one built from a query parameter.
* `archive/zip` and `archive/tar` extraction that trusts an entry's name.

Safe form: `os.Root` (Go 1.24) or `os.DirFS` plus `fs.ValidPath`, or
`filepath.Clean` followed by an explicit `strings.HasPrefix(path, root +
string(os.PathSeparator))` check.

## injection.request_forgery

* `http.Get`, `http.Post` and `http.NewRequest` with a URL from input. The
  default client follows up to ten redirects, so a check that ran on the first
  URL did not run on the last.
* A `net.Dialer` with no control function, which is where an allow-list has to
  live if it is to survive DNS rebinding.

Safe form: `CheckRedirect` returning `http.ErrUseLastResponse`, an allow-list
enforced in `DialContext` against the resolved address.

## injection.markup

* A conversion out of `html/template`'s type system: `template.HTML(x)`,
  `template.JS(x)`, `template.URL(x)` and `template.CSS(x)` all mean "this is
  already safe", and each is a sink when `x` came from input.
* `text/template` used to build HTML, which does no contextual escaping at all.
* `w.Write([]byte(input))` with an HTML content type.

Safe form: `html/template` with the value passed as data and no conversion.

## injection.document_parser

* `encoding/gob` over untrusted bytes, and `gopkg.in/yaml` decoding into
  `interface{}` or a type with a custom unmarshaller.
* `text/template` or `html/template` parsing a template from input, which is
  the template class reached through a parser call.
* `encoding/xml` does *not* expand external entities and has no DTD support, so
  a Go XML decoder is not an XXE sink. That is worth stating, because the
  equivalent line in every other pack here is.

## authentication.credential_verification

* `jwt.Parse` with a key function that returns a key without checking
  `token.Method`, which admits an algorithm the verifier did not intend.
* `==` on a token or MAC, against `hmac.Equal` or `subtle.ConstantTimeCompare`.

## information_disclosure.identifier_oracle

* `math/rand` for a token, session identifier or reset code. It is a
  deterministic generator, and in Go below 1.20 an unseeded one, so the value
  is predictable rather than secret.

Safe form: `crypto/rand`.

## information_disclosure.error_detail

* `http.Error(w, err.Error(), 500)`, which returns the wrapped error chain --
  often a full query, a path or a host.
* `fmt.Fprintf(w, "%+v", err)` and a `panic` reaching a handler that prints the
  stack.

## session_handling.cookie_scope

* `http.Cookie` with `HttpOnly` unset (the zero value is false), `Secure`
  unset, `SameSite: http.SameSiteNoneMode`, or a `Domain` widened to a parent
  the target shares with other services.

## transport.tls_configuration

* `tls.Config{InsecureSkipVerify: true}`, and a `VerifyPeerCertificate` that
  returns nil unconditionally.
* `MinVersion` unset on a server config in an old module.

## What a match is not

Strings recovered from a binary have no call graph. A sink name in the string
table proves the symbol was linked in, which every transitive dependency
contributes to, and says nothing about a handler reaching it.
