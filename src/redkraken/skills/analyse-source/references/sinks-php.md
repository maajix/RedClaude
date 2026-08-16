# PHP sinks

Read `code-review.md` first: a match here is a reason to ask a question, never
an answer.

An Artifact of this kind is usually a Laravel or Symfony tree, a WordPress
plugin or theme, or loose `.php` files from an exposed directory. PHP's routing
is sometimes a table and sometimes the filesystem, so in a tree with no router
the file layout is the route table, and a file that is reachable is a file that
executes.

Sources are `$_GET`, `$_POST`, `$_REQUEST`, `$_COOKIE`, `$_FILES`,
`$_SERVER` (including `HTTP_*` headers, `PHP_SELF` and `REQUEST_URI`),
`php://input`, and in Laravel `request()`, `$request->input()` and a route
parameter.

## injection.command

* `system`, `exec`, `shell_exec`, `passthru`, `popen`, `proc_open`, and the
  backtick operator, which is `shell_exec` in punctuation.
* `mail()`'s fifth argument, which is passed to sendmail.

Safe form: `escapeshellarg` per argument, not `escapeshellcmd` over a whole
command line. A fixed argument vector is better than either.

## injection.template

* `eval`, `assert` with a string on PHP below 8, `create_function`,
  `preg_replace` with the `/e` modifier on legacy trees.
* A variable function call `$f()`, `call_user_func` or `call_user_func_array`
  with a callable from input, and `array_map`/`usort` given the same.
* Twig `createTemplate` or Smarty `display`/`fetch` over a user string; Blade
  `@php` blocks or `Blade::render` with input.

Safe form: a dispatch table mapping an input token to a fixed callable.

## injection.path

* `include`, `include_once`, `require`, `require_once` with a variable, which is
  code execution and not only disclosure.
* `file_get_contents`, `fopen`, `readfile`, `file`, `unlink`, `copy`,
  `move_uploaded_file`, `glob` and `scandir` over input.
* Stream wrappers, which make a "file name" much wider than a path:
  `php://filter` (source disclosure, and with a chain, execution),
  `data://`, `zip://`, `phar://` and, where `allow_url_include` is on,
  `http://`.
* A `..` chain, and a trailing null byte on very old builds.

Safe form: `basename` plus an allow-list plus `realpath` with a prefix check.
`basename` alone still admits any file in the directory.

## injection.document_parser

* `unserialize` on input, which is the POP-chain shape: a magic method
  (`__wakeup`, `__destruct`, `__toString`) on any loaded class becomes the
  payload's first instruction.
* `phar://` reaching almost any filesystem function on PHP below 8, which
  deserialises the archive's metadata without an `unserialize` call in the
  source at all.
* `simplexml_load_string`, `DOMDocument::loadXML` or `XMLReader` with
  `LIBXML_NOENT`.

Safe form: `json_decode` for data, and `unserialize($x, ['allowed_classes' =>
false])` where the format cannot be changed.

## injection.query_language

* `mysqli_query`, `mysql_query`, `$pdo->query` or `$pdo->exec` with a string
  built by interpolation; `"... WHERE id = $id"` is the whole shape.
* Laravel `DB::raw`, `whereRaw`, `orderByRaw`, `selectRaw`, and `havingRaw`.
* `addslashes` used as an escape, which is not one for the connection's
  charset.

Safe form: `prepare` with bound parameters and emulation off
(`PDO::ATTR_EMULATE_PREPARES => false`), or the query builder given values.

## injection.markup

* `echo`, `print`, `printf` and `<?= ?>` over input.
* Blade's `{!! !!}`, Twig's `|raw`, and `htmlspecialchars` called without
  `ENT_QUOTES`, which leaves single quotes intact inside an attribute.

Safe form: `{{ }}` in Blade or Twig, or `htmlspecialchars($x, ENT_QUOTES,
'UTF-8')`.

## injection.request_forgery

* `curl_exec` with a URL from input and `CURLOPT_FOLLOWLOCATION` on, which
  follows a redirect past whatever check ran first.
* `file_get_contents('http://...')`, `fsockopen`, and any image or PDF library
  handed a remote URL.

## authentication.credential_verification

* `==` between a stored hash and a computed one, which is a loose comparison:
  two strings that both look like scientific notation compare equal, and a
  hash beginning `0e` compares equal to another such hash.
* `strcmp` given an array, which returns null on old versions rather than a
  difference.
* `md5` or `sha1` as a password hash, and a token compared without
  `hash_equals`.

Safe form: `password_verify`, and `hash_equals` for anything else.

## information_disclosure.error_detail

* `display_errors = On`, `error_reporting(E_ALL)` reaching the response,
  `APP_DEBUG=true` in a Laravel `.env`, which renders a stack trace with
  environment values in it.
* `phpinfo()` left in the tree.

## information_disclosure.artifact_exposure

* `.env`, `config.php.bak`, `composer.lock`, `.git` or an editor swap file
  under the document root.
* A Laravel `APP_KEY` in the tree, which signs cookies and encrypts session
  payloads, so disclosure is a forgery primitive.

## What a match is not

WordPress and Laravel trees carry vendor directories with sinks in code the
application never calls. A sink inside a dependency is a fact about the
dependency until something in the application's own path reaches it.
