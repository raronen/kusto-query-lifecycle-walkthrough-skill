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
- the actual final logical Relop payload and its independent SHA-256 digest;
- sanitized physical structural facts needed by the walkthrough.

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

### Final logical RelopTree gate

Extract the final logical payload independently from the physical gate. Accept direct
`RelopTree` / `relop_tree` keys and Kusto column or `ResultType` / `Content` envelopes. Preserve
an object/array as JSON content or preserve nonempty serialized text exactly. Compute the digest
over canonical JSON for structured content or the exact UTF-8 text for serialized content.
Derive stable logical IDs from explicit `LogicalId`, `RelopId`, `NodeId`, or `Id` fields. When
the accepted representation has none, derive deterministic JSON-path IDs for structured content
or a content-hash root ID for opaque text. Reject EVIDENCE mode when no final logical payload is
available.

Always retain the exact-content digest for provenance. When structured content or textual
content parses as JSON, also compute `canonical_digest_sha256` over sorted, compact JSON. Bind
the terminal optimizer snapshot to the canonical structural digest, never to formatting or
property order in the exact textual payload.

For textual content, preserve and hash the original text but attempt JSON decoding first for ID
derivation. Merge IDs discovered from parsed generic `Id` fields with explicit `logical-*`
references found in the representation. Use regex/hash fallback only when JSON decoding fails.

The logical payload does not prove physical completeness, and the physical tree does not replace
the logical payload. Recovery may combine a previously captured final RelopTree with a
user-supplied physical QueryPlan, but both remain separately digested and validated.

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

For optimizer passes, final-state artifacts never identify pass history. Use `TRANSFORMED` or
`SCHEDULED_NO_OP` only with runtime per-pass before/after snapshots whose recorded SHA-256
digests match the displayed content. When pinned source control flow proves that a pass was
scheduled/executed but no snapshots exist, use `EXECUTED_OUTCOME_NOT_CAPTURED` and display
identical `OUTCOME NOT CAPTURED` panes. Use `NOT_TRACED` when even execution is unavailable.
Use `NO_OP` only for a query-specific phase proven to have no work; do not relabel an untraced
optimizer pass as a no-op.

### Active optimizer trace acquisition

Missing runtime snapshots trigger evidence acquisition, not immediate fallback. Inspect the
current local source for an existing request-scoped diagnostic path around `PassManager.Execute`
and concrete `pass.Execute` calls. Attempt that path first with the exact non-executing
`.show queryplan <|` wrapper.

If no existing path exposes before/after state, source modification is allowed only after
explicit authorization for an isolated local-development workspace. Then:

1. Require `query.cluster_uri` and the source-verified trace endpoint to be loopback URIs with
   the same explicit, currently unowned port.
2. Use `scripts\local_trace_driver.py` to create a new disposable git worktree outside the
   primary checkout. Resolve `--base-ref` before creation, require it equals the primary/source
   HEAD, and verify the created worktree is detached at that same commit. Never instrument in
   the primary checkout. Require the primary checkout to be completely clean (tracked, staged,
   and untracked), create an invocation-owned root with an exclusive marker, and recursively
   delete only when that marker still matches. If ownership is unexpected, remove only confirmed
   Git registration, leave the path, and fail cleanup.
3. Add minimal instrumentation immediately before and after `pass.Execute`.
4. Gate every emission on a unique request-scope token for this one plan request.
5. Serialize only the logical tree needed for structural comparison; do not emit credentials,
   tenant data, unrelated requests, or query results.
6. Use repository-documented build and test commands under a finite timeout, then start a new
   isolated local service. Place both build and service process trees in Windows Job Objects.
   Launch suspended, assign the Job Object, then resume; wrap `.cmd`/`.bat` explicitly through
   `%ComSpec%` without `shell=True`. Never stop, replace, or reuse an existing Engine process.
7. Issue only the unchanged plan command; never submit the supplied query for execution.
8. Capture the per-pass payload and validate it with `scripts\optimizer_trace.py`.
9. In `finally`, terminate the Job Objects, treat any process-stop error as a failure, verify
   every owned build/service PID exited, verify the port was released, and remove both the
   disposable worktree path and registration even after partial worktree creation. Verify the
   primary HEAD and status digest are unchanged.

A COMPLETE model records this attempt in `optimizer_trace.acquisition`; `attempted: false` is
invalid. Request-scoped instrumentation requires `explicit_local` authorization plus successful
build/restart and completed cleanup. Without that authorization, attempt only existing
read-only diagnostics and record `read_only_only`. Source-schedule or unavailable outcomes are
permitted only after the runtime capture attempt fails and the failure is recorded.

The driver's raw receipt contains local paths, PIDs, and the request-scope value and must remain
outside the model and generated page. `optimizer_trace.py` validates its digest, source/worktree
HEADs, port/process ownership, Job Object termination, primary-checkout preservation, and
worktree cleanup, then retains only the receipt digest, request-scope digest, trace-output
digest, and nonsensitive booleans/enums.

Each captured pass contains exact before/after content and digests. Its ID is referenced exactly
once by `runtime_evidence.trace_pass_id`. This binding, rather than a hand-authored digest pair,
authorizes `TRANSFORMED` or `SCHEDULED_NO_OP`.

Trace events are ordered, not a bag. Require sequence `1..N`, the optimizer phase, canonical
model pass ID, concrete source pass identity, request scope on every event, `executed: true`,
and an explicit `changed` boolean. Before/after values must already be canonical JSON strings
that parse to nonempty Relop objects/arrays. Verify `changed` from the digests, require each
event's before digest to equal the previous event's after digest, bind phase/identity/sequence
to model order, and require the terminal after digest to equal
`plan.final_relop.canonical_digest_sha256`. Reject opaque snapshots and relabeled IDs.

For physical lowering, inspect the current implementation (for example the applicable
`InitialQueryPlanBuilder.Visit*` methods). Each mapping must connect a logical ID derived from
the recorded final RelopTree to physical operator IDs in the sanitized QueryPlan and include
exact current-HEAD source links.

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
