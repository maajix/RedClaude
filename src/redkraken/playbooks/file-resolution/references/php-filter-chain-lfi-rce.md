# PHP filter chains: turning a read into an execution, and why that is the end

Maintainer notes, not projected. Written fresh for v2; the v1 text is not in
this repository.

## What the v1 page was

The technique that made file inclusion interesting again on PHP. `php://filter`
takes a stream and applies conversion filters to it; chain enough
`convert.iconv.*` and `convert.base64-*` steps together and the output is a
string you chose, built out of the encoder's own error bytes, without needing any
file on the target to contain it. Feed that into an `include` and the target
executes code that was never written anywhere.

The page gave the generator, the chain syntax, and the two prerequisites: an
`include`/`require` reached by a caller-controlled string, and no
`allow_url_include` needed because `php://filter` is not a remote wrapper.

It also listed the neighbours: `php://input` where the body becomes the included
file, `data://text/plain;base64,` where the URL is the file, `zip://` and
`phar://` where an uploaded archive becomes one, and `expect://` where the
"file" is a command.

## Why the Playbook does not run it

**It is remote code execution, produced deliberately.** There is no
proof-of-concept version. The chain's entire output is the code that runs; the
smallest possible demonstration executes something on the host.

**The precondition is the finding.** A filter chain requires a caller-controlled
`include`. If the reading has established that -- and it has, the moment the
parameter resolved outside its directory into a file the route then interpreted
-- the report is already complete. The chain adds severity to the write-up by
adding an exploit to the engagement.

**`phar://` deserialises.** Reaching a phar stream triggers PHP object
instantiation from the archive's metadata, which is the object-graph class with
worse controls and no way to make it inert.

**`expect://` is a shell.** It is on the list only because the page was
enumerating wrappers, and it belongs to `injection.command`, under
`command-directory-injection`'s approval, not to a file-reading Playbook.

**The chains are long and fragile.** A generated chain is hundreds of filter
names in one parameter. A partial application leaves the interpreter having
consumed part of a stream in a state nobody predicted, on a live target, with no
undo.

## What is kept

The distinction the page rests on, because the Playbook's step 7 needs it: there
is a difference between a route that *reads* a resolved path and a route that
*interprets* it. Both are reachable through the same parameter, and the second
one is what makes this class matter -- but the evidence for the first is what a
reading is allowed to collect.

Also kept, as a neighbour pointer: when the caller's name decides how a stored
file is later served or interpreted rather than which file is read, that is
`injection.stored_file` and `file-upload` asks it, with an approval and a cleanup
plan attached.

## The trap in the whole technique

A wrapper that "works" often has not. `php://filter/read=convert.base64-encode/`
returning base64 proves the wrapper is enabled; it does not prove the target
would have executed anything, because `include` and `file_get_contents` reach the
same wrapper and only one of them runs code.

The v1 page conflated those two constantly. A reading that inherits the
conflation reports remote code execution on a route that reads a template into a
string and prints it.
