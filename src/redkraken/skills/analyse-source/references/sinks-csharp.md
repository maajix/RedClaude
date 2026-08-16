# C# and .NET sinks

Read `code-review.md` first: a match here is a reason to ask a question, never
an answer.

An Artifact of this kind is usually an ASP.NET Core tree, a legacy Web Forms or
MVC application, or a decompiled assembly. Routing is attributes plus
convention: `[Route]`, `[HttpGet]`, `[HttpPost]` and `MapControllers` give the
table, and model binding gives the parameters -- which is itself worth reading,
because binding fills every public settable property on the model whether the
action meant it to or not.

Sources are `Request.Query`, `Request.Form`, `Request.Headers`,
`Request.Cookies`, `Request.Body`, a route value, and a bound model's
properties.

## injection.document_parser

Deserialisation lives here: a parser that turns bytes into objects is the
document parser class even when the bytes are not a document. On .NET this is
the pack's highest-value class.

* `BinaryFormatter`, `SoapFormatter`, `NetDataContractSerializer`,
  `LosFormatter` and `ObjectStateFormatter`, all of which reconstruct arbitrary
  types. `BinaryFormatter` is removed in current .NET and still present in
  long-lived applications.
* `Newtonsoft.Json` with `TypeNameHandling` set to anything but `None`, and
  `JavaScriptSerializer` with a `SimpleTypeResolver`: both let the document
  name the type.
* `XmlSerializer` constructed with a type from input, and `DataContractSerializer`
  with a permissive resolver.
* `XmlDocument`, `XmlTextReader` or `XPathDocument` with a non-null
  `XmlResolver`, which is the XXE shape. Modern defaults are null; a line that
  sets one is the finding.
* ViewState with `enableViewStateMac="false"`, or a `machineKey` committed in
  `web.config`. A known key makes ViewState an attacker-authored object graph.

Safe form: `System.Text.Json` into a concrete type, `TypeNameHandling.None`,
`XmlResolver = null`.

## injection.query_language

* `new SqlCommand("... " + user)`, and string interpolation inside a Dapper
  call: Dapper parameterises anonymous-object arguments and does nothing for
  text already inside the SQL string.
* Entity Framework `FromSqlRaw`, `ExecuteSqlRaw` and `SqlQuery` with
  interpolation. `FromSqlInterpolated` and `ExecuteSqlInterpolated` do
  parameterise an interpolated string, so the two spellings look alike and
  behave differently.
* A sort column or table name from input, which no parameter can carry.

Safe form: `SqlParameter`, Dapper's parameter object, the `*Interpolated`
variants, an allow-list for identifiers.

## injection.command

* `Process.Start(fileName, arguments)` where `arguments` is built from input,
  and `ProcessStartInfo` with `UseShellExecute = true`, which hands the string
  to the shell and admits a URL or a document as a "program".

Safe form: `ProcessStartInfo.ArgumentList`, one element per argument.

## injection.markup

* `Html.Raw`, `HtmlString`, `MvcHtmlString`, `Response.Write`, `<%= %>`, and
  `@Html.Raw(Model.Anything)`.
* `[ValidateInput(false)]` and `requestValidationMode="2.0"` on legacy
  applications, which turn off the platform's own filter.
* A Razor `@` binding placed inside a `<script>` block, where HTML escaping is
  the wrong escaping.

Safe form: `@model.Value` in Razor, which HTML-encodes, and
`JsonSerializer` for a value that must land in script.

## injection.path

* `Path.Combine(root, user)`, which returns `user` when `user` is rooted, so an
  absolute value discards the base entirely.
* `File.ReadAllText`, `File.OpenRead`, `PhysicalFile`, `Server.MapPath` and
  `VirtualPathUtility.Combine` over input.
* `ZipArchiveEntry.FullName` used as a destination, which is zip slip.

Safe form: `Path.GetFullPath` then `StartsWith` the canonical root with a
trailing separator, plus `Path.GetFileName` where only a name is wanted.

## injection.request_forgery

* `HttpClient.GetAsync`, `WebRequest.Create`, `WebClient.DownloadString` with a
  URL from input, and `HttpClientHandler.AllowAutoRedirect`, which is on by
  default.
* `Uri.TryCreate` used as validation, which says a string parses and not that
  the host is allowed.

## injection.template

* `RazorEngine`/`RazorLight` compiling a template from input, which compiles and
  runs C#.
* An expression evaluator (`DataTable.Compute`, `System.Linq.Dynamic`) over
  attacker text.

## authorization.function_access

* An action with no `[Authorize]` where its siblings have one, and
  `[AllowAnonymous]`, which wins over a controller-level `[Authorize]`.
* `app.UseAuthorization()` missing or ordered before `app.UseAuthentication()`
  in the pipeline.
* Over-posting: a bound model that carries `IsAdmin` or `RoleId` with no
  `[Bind]` list and no separate view model, which is the mass-assignment shape.

## session_handling.csrf

* A POST action without `[ValidateAntiForgeryToken]`, and
  `services.AddControllers()` without an antiforgery filter, where the session
  is a cookie.
* `SameSite = SameSiteMode.None` on the auth cookie.

## transport.tls_configuration

* `ServicePointManager.ServerCertificateValidationCallback = (s, c, ch, e) =>
  true`, and `HttpClientHandler.ServerCertificateCustomValidationCallback` set
  to the same.

## information_disclosure.error_detail

* `app.UseDeveloperExceptionPage()` outside a development branch,
  `customErrors mode="Off"`, and a `Trace.axd` handler left mapped.

## What a match is not

Decompiled output loses attributes only sometimes and loses comments always,
so an absent `[Authorize]` in decompiled source is weaker evidence than an
absent one in a repository. Say which the Artifact is.
