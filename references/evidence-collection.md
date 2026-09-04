# Evidence collection

## Priority

1. A real plan obtained through a documented non-executing `.show queryplan` or equivalent
   query-plan operation.
2. Exact source evidence from the authorized local Azure-Kusto-Service workspace.
3. A source-based estimate only when plan evidence is unavailable.

Never execute the supplied query. Reject tooling that cannot prove its request is plan-only.
Do not use `take`, `count`, result truncation, or cancellation as substitutes for
non-execution.

Cluster transport must use HTTPS except for the explicit local-development exception: HTTP is
allowed only for exact `localhost`, IPv4 `127.0.0.0/8`, or IPv6 `::1`. Userinfo, hostname
suffix tricks, non-loopback HTTP, and non-HTTP(S) schemes are invalid.

## Plan record

Record only:

- tool name and version;
- UTC collection time;
- cluster URI and database supplied by the user;
- whether the operation is guaranteed non-executing;
- a SHA-256 digest of the raw plan;
- sanitized structural facts needed by the walkthrough.

Keep raw proprietary plans outside this repository. A local model/page may include an authorized
raw-plan section only when the evidence policy permits it and the canonical physical deep dive
requires it; redact confidential payloads, literals, tenant data, request identifiers, and
credentials first. Repository fixtures remain synthetic and contain no proprietary plan.

## Evidence modes

### Complete physical QueryPlan gate

After automatic plan collection, inspect the result for a complete physical `QueryPlan`
operator tree. Logical Relop, hints, statistics, an absent `QueryPlan` cell, a malformed cell,
or a tree marked incomplete/truncated does not satisfy the gate.

A complete serialized physical plan has a `RootOperator` with a non-negative `NodeId`, a
nonempty `Operators` array, and recursively valid physical nodes identified by the source-backed
`Kusto.DataNode.DataEngineQueryPlan.<Type>, DataNode` `$type` shape plus non-negative `NodeId`.
Accept either a named `QueryPlan` cell, the Kusto
`ResultType = QueryPlan` / `Content` row shape, or the decoded plan object. Reject `Relop`,
`replotree`, arbitrary `Kind`/`Operator` objects, missing child node types, non-boolean
completeness flags, and incomplete/truncated flags at any envelope depth.

When the gate fails, build only:

```kusto
.show queryplan <|
<the exact supplied query, byte-for-byte>
```

This is the supported plan-only wrapper used by Microsoft Kusto tooling. Do not append
`| project QueryPlan` to the supplied query because that changes the query being planned. The
user copies the `QueryPlan` result cell/JSON from the command result.

Attempt `kusto-kusto_deeplink_from_query` with the exact command, cluster URI, and database.
Then use the interactive ask-user tool to present the evidence deficiency, clickable deeplink
when available, exact copyable command, and paste/attachment/file-path instructions. The
command remains available when deeplink generation fails.

Validate user-supplied output before use. It must be non-empty JSON with a complete physical
operator root and recursively valid children, and must not be truncated. Retain only an
allowlisted structural projection (`RootOperator`, `Operators`, child-lane names, `$type`, and
`NodeId`), dropping every literal, arbitrary property bag, credential, token, identifier,
connection string, path, and other non-structural value. Hash both the exact original bytes and
the canonical sanitized projection, then mark provenance
`user_supplied non-executing plan evidence`.

Pass the original payload bytes or text to the inspector. Parsed dictionaries are rejected
because reserialization cannot prove the digest of the exact user-supplied bytes.

Persist the allowlisted structural projection in `plan.sanitized_queryplan`. Every EVIDENCE
physical `full_plan` must use the corresponding `node-<NodeId>`, normalized `$type` name, and
parent-child topology exactly; an operator count alone never binds evidence to the rendered tree.

The recovery prompt record must contain the exact command, automatic-evidence summary,
deficiency, deeplink result, UTC prompt timestamp, and SHA-256 of the deterministic prompt text.
Accepted user evidence and explicit estimation consume that unresolved record. A standalone
`prompted: true` assertion is insufficient.

Never transition silently to `ESTIMATED`. Fallback requires automatic failure, a recorded
recovery prompt, and an explicit user decline, inability to provide the plan, or choice after
an invalid/incomplete response. Record the exact outcome and missing `QueryPlan` in
`estimate_reason`.

`EVIDENCE` requires real plan evidence. `ESTIMATED` is allowed only when plan collection
failed or was unavailable, and requires a non-empty `estimate_reason`. Estimated pages must
use query syntax plus exact source evidence to explain likely behavior and must avoid claiming
that a pass ran, an operator exists, or a boundary was crossed unless supported.

Use `OBSERVED` for plan-backed facts, `TRANSFORMED` only when before/after evidence proves a
change, `SCHEDULED_NO_OP` when scheduling is observed but the tree is unchanged, and `NO_OP`
for a query-specific phase with no work.

## Sensitive-data hygiene

Before writing the model:

- remove query literals from plan annotations unless essential and user-approved;
- exclude raw logs, request IDs, tenant IDs, tokens, machine paths, and memory addresses;
- summarize source behavior; link to source instead of copying source text;
- store the exact query only in the generated local page/model, never in this repository.

## Publication isolation

Evidence collection, model completion, validation, and HTML rendering never depend on bookmark
companion availability. Do not run a companion preflight or ask the user about publication.
Only after the valid HTML exists may the publisher be attempted best-effort. Preserve the model
and HTML and report a bookmark warning when publication is skipped or fails.

Rendering is complete only after `scripts/spec_compliance.py` validates the model and generated
HTML against every item in `spec-compliance-manifest.json`. The four canonical runner omissions
are structural requirements, not missing evidence. Query-specific source paths and line ranges
replace canonical example values while retaining exact-line current-HEAD pinning.
