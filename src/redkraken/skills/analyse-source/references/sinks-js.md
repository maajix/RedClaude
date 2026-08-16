# JavaScript and TypeScript sinks

Read `code-review.md` first: a match here is a reason to ask a question, never
an answer.

An Artifact of this kind is usually a minified browser bundle, its source map,
or a Node service's tree. Minification mangles identifiers and leaves string
literals alone, so route strings, header names, feature flags and sink
arguments survive a build even when the function that used them does not. Where
a `sourceMappingURL` resolves, `jq` over `.sources` and `.sourcesContent` gives
original paths and original names, and that extraction is repeatable, which is
what step 2 of `SKILL.md` asks for.

Sources -- where attacker text enters -- are `location`, `location.hash`,
`location.search`, `document.referrer`, `document.cookie`, `name`, a
`message` event's `data`, `localStorage`, and on the server `req.query`,
`req.params`, `req.body`, `req.headers` and a route parameter.

## injection.markup

* `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`,
  `document.writeln`, jQuery `.html()`, `.append()` and `$(input)`.
* React `dangerouslySetInnerHTML`, Vue `v-html`, Angular
  `bypassSecurityTrustHtml` and `bypassSecurityTrustUrl`, Svelte `{@html}`.
* `setAttribute` on `href`, `src`, `action` or `formaction`, which admits a
  `javascript:` value that `textContent` never would.

Safe form: `textContent`, `createTextNode`, a framework's default interpolation
(`{}` in React, `{{ }}` in Vue, `[textContent]` in Angular). Angular's
`[innerHTML]` binding is sanitised unless a `bypassSecurityTrust*` call is in
the path, so the binding alone is not the sink -- the bypass is.

## injection.template

* `eval`, `new Function`, `setTimeout` and `setInterval` given a string rather
  than a function, `document.location = 'javascript:...'`.
* `vm.runInNewContext`, `vm.runInThisContext` and `vm.Script`, none of which is
  a sandbox against hostile input.
* Server templating from a user string: `pug.compile`, `ejs.render` with
  `options.client`, `handlebars.compile`, `lodash.template`.
* A dynamic `import()` whose specifier is built from input.

Safe form: a template compiled from a file the build owns, with input passed as
data.

## injection.command

* `child_process.exec` and `execSync`, which run through a shell.
* `spawn` or `execFile` with `shell: true`.

Safe form: `execFile`/`spawn` with an argument array and no `shell` option. An
argument array is not automatically safe when the program itself takes a
command (`sh -c`, `ssh`, `find -exec`).

## injection.query_language

* A template literal or `+` inside `pool.query`, `connection.query`,
  `sequelize.query`, `knex.raw`, `db.$queryRawUnsafe` (Prisma) or a TypeORM
  `where` string.
* MongoDB `$where`, `mapReduce`, and an operator reaching a filter: a JSON body
  parsed straight into `find({ user: req.body.user })` admits
  `{"$ne": null}` unless the value is cast.

Safe form: placeholders (`?`, `$1`), a query builder given values, Prisma's
`$queryRaw` tagged template, an explicit cast to string before a filter.

## injection.path

* `fs.readFile`, `fs.createReadStream`, `res.sendFile` or `res.download` over
  `path.join(root, userValue)`. `path.join` does not confine: `..` segments are
  resolved and an absolute second argument does not replace the first, but a
  `..` chain leaves the root.
* Archive extraction that trusts an entry name (`unzipper`, `tar` without
  `strip`/filter), which is the zip-slip shape.
* `express.static` or `serve-static` mounted over a directory that also holds
  configuration.

Safe form: `res.sendFile(name, { root })`, or `path.resolve` followed by an
explicit `startsWith(root + path.sep)` check.

## injection.request_forgery

* `fetch`, `axios`, `got`, `node-fetch`, `http.request` or `https.request` with
  a URL from input; a webhook, an avatar fetcher, a link preview, a PDF
  renderer and an import-by-URL are all this shape.
* `new URL(input, base)` used as validation: a value that parses is not a value
  that stays on the allowed host, and a redirect that is followed lands
  somewhere the check never saw.

Safe form: an allow-list matched after resolution, with redirects disabled.

## injection.document_parser

* `JSON.parse` output merged into an object by `Object.assign`, `lodash.merge`,
  `lodash.defaultsDeep` or a hand-written deep merge, which is the prototype
  pollution shape: a `__proto__` or `constructor.prototype` key reaches
  `Object.prototype` and changes code that never read the request.
* `js-yaml` `load` under v3 defaults, and `unsafeLoad` at any version.
* `node-serialize`'s `unserialize`, and any `funcster`-style revival of a
  function from JSON.
* `libxmljs` parsed with `noent: true`, which expands external entities.

Safe form: a schema-validated parse, `Object.create(null)` for a map built from
input, `js-yaml`'s default `load` at v4.

## information_disclosure.artifact_exposure

* A `sourceMappingURL` that resolves in production: the map hands over original
  sources, which is a larger disclosure than the bundle.
* Build-time inlining of environment values. Anything under `NEXT_PUBLIC_`,
  `VITE_`, `REACT_APP_` or `process.env` referenced in client code is in the
  bundle by definition, so a key with that prefix is published, not leaked.
* Committed `.map`, `.env`, `.git` or backup files served by the static mount.

## transport.tls_configuration

* `rejectUnauthorized: false` on an agent or request.
* `NODE_TLS_REJECT_UNAUTHORIZED=0` anywhere in start scripts, a Dockerfile or a
  CI file, which disables verification for the whole process.

## session_handling.cookie_scope

* `res.cookie` with `httpOnly: false`, `secure: false`, `sameSite: 'none'`
  without `secure`, or a `domain` widened to a parent domain that other
  services also answer on.
* A session library configured with a static, committed secret.

## What a match is not

A bundle is the client. A sink in client code that runs on values the client
already had is not a boundary crossing, and a route string in a bundle is not a
route that answers. Both are Surface for somebody with an exchange to make.
