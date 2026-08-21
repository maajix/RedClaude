---
description: Difference two stored responses deterministically and cite the difference rather than describe it. Use when a baseline and a variant exchange have both been recorded and the claim depends on what changed between them.
bb:roles: ["web_hunter"]
bb:tool_groups: ["exec.tool_run", "state.propose", "state.read"]
bb:evidence_profile: identity_differential
bb:scripts: [{"name": "compare.py", "description": "Line-level difference between two stored Artifacts, as one JSON object.", "checks": [{"artifacts": ["ok", "ok"], "stdout": {"identical": true, "lengths": [2, 2], "line_counts": [1, 1], "only_in_first": [], "only_in_second": [], "shared_lines": 1}}, {"artifacts": ["HTTP/1.1 200\nrole: member\nid: 7", "HTTP/1.1 200\nrole: admin\nid: 7"], "stdout": {"identical": false, "lengths": [31, 30], "line_counts": [3, 3], "only_in_first": ["role: member"], "only_in_second": ["role: admin"], "shared_lines": 2}}]}]
---

# Compare two responses

A differential is a claim about two exchanges. This turns that claim into a
number somebody else can recompute.

## 1. Hold everything but one variable

The two exchanges differ in exactly one thing: the Identity, one parameter, one
header, one method. If they differ in two, the comparison answers about neither.
Name the variable before running anything, and name the Receipt of each side.

## 2. Difference the stored bytes, not your memory of them

Call `mcp__rk2__run_skill_script` with `skill_name` `compare-responses`, `script`
`compare.py`, and `arguments` set to `{"first": ..., "second": ...}`, where each
value is the Artifact label the packet gave you and `first` is the baseline. The
script takes the two Artifacts and nothing else, and it answers the same way
every time it is run:

```json
{"identical": false, "lengths": [31, 30], "line_counts": [3, 3],
 "only_in_first": ["role: member"], "only_in_second": ["role: admin"],
 "shared_lines": 2}
```

The run is a Tool run and its output is an Artifact. That Artifact is what the
observation cites.

## 3. Say what the difference is evidence of

`identical: true` is a result, not a failure. It is the control that a change of
the variable changed nothing, and a hypothesis with no control is one nobody can
refute.

Where the difference is real, quote the differing lines from the script's answer
rather than paraphrasing them, and cite both Receipts and the Tool run. A
sentence about a difference, without the Artifact hashes it came from, is a
sentence the validator cannot check and the reporter will not carry.

## 4. Stop when the bytes are sealed

Where either side's response body is in the sealed wire view, there is nothing
to difference and the comparison is inconclusive. Report it as inconclusive with
both Receipt labels; do not substitute the status line for the body, and do not
re-run the exchange in the hope of a different visibility.
