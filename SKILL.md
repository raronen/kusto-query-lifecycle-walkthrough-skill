---
name: kusto-query-lifecycle-walkthrough
description: Generate an evidence-grounded, interactive Kusto query lifecycle walkthrough from query text, a cluster URI, and a database without executing the query. Uses non-executing query-plan evidence and an authorized local Azure-Kusto-Service workspace, labels source-only fallbacks ESTIMATED, renders all ten lifecycle phases, and optionally attempts best-effort bookmark publication after saving the self-contained page.
---

# Kusto Query Lifecycle Walkthrough

Build a query-specific, source-linked walkthrough without executing the supplied query.

## Required input

Require all three values before doing work:

- exact query text;
- cluster URI;
- database name.

The cluster URI must be absolute HTTPS. For local development only, absolute HTTP is allowed
when the host is exactly `localhost`, an IPv4 address in `127.0.0.0/8`, or IPv6 `::1`.
Reject userinfo, deceptive hostname suffixes, non-loopback HTTP, and all other schemes.

Treat the query as untrusted text. Never run it, rewrite it into an executable command, or
send it to a query endpoint.

## Safety boundary

Allowed:

- non-executing `.show queryplan` or equivalent query-plan tooling;
- read-only inspection of an authorized local Azure-Kusto-Service workspace;
- read-only git commands used to resolve the workspace HEAD;
- local deterministic scripts in this package.
- after explicit authorization for an isolated local-development workspace only: request-scoped
  optimizer instrumentation, the repository-prescribed local build/test, and restart of only
  the local service instance needed to collect non-executing per-pass snapshots.

Forbidden:

- executing the supplied query, even to sample one row;
- modifying, building, restarting, or instrumenting production, shared, remote, or
  non-development services;
- broad/global optimizer logging or instrumentation not correlated to the one plan request;
- copying Azure-Kusto-Service source, internal logs, proprietary plans, credentials, or a
  previous query-specific HTML into this package;
- inventing transformations, runtime operators, stack placement, allocator addresses, or
  byte sizes.

Read [references/evidence-collection.md](references/evidence-collection.md) before collecting
evidence and [references/source-grounding.md](references/source-grounding.md) before creating
links.

Read the complete
[authoritative as-built specification](references/query-lifecycle-two-level-walkthrough.spec.md)
before modeling or rendering. Generated HTML MUST satisfy every applicable normative statement
and every acceptance item pedantically. Do not summarize, omit, simplify, regularize, or replace
specified behavior with generic prose. Defects marked `[C]` are normative; only explicit CAVEAT
remediations are advisory. The
[compliance manifest](references/spec-compliance-manifest.json) tracks all 93 acceptance items.

## Workflow

1. Save the exact query text to a temporary local file outside the repository.
2. Locate the authorized Azure-Kusto-Service workspace and resolve its current HEAD.
3. Create a draft:

   ```powershell
   python scripts\scaffold_model.py `
     --query-file "<query.kql>" `
     --cluster-uri "<cluster-uri>" `
     --database "<database>" `
     --source-workspace "<Azure-Kusto-Service-workspace>" `
     --output "<model.json>"
   ```

4. Attempt to collect real non-executing plan evidence. Preserve the actual final logical
   `RelopTree` returned by the operation (object/array or exact nonempty serialized text), its
   exact-content digest, canonical structural digest when JSON-decodable, and deterministic
   logical IDs. Separately prove that the response contains a
   complete physical `QueryPlan` operator tree. A final Relop, hints, statistics, or a
   missing/truncated `QueryPlan` cell does not satisfy the physical gate. Record the tool,
   timestamp, provenance, and both digests. Keep proprietary raw output out of this repository;
   the query-specific local model/page is the only place where the actual final Relop content
   may be retained.
5. If automatic evidence lacks a complete physical `QueryPlan`, do not render yet:

   - Build the exact plan-only command with `scripts\plan_recovery.py`. Its form is
     `.show queryplan <|` followed by the exact unchanged query. Do not append a projection to
     the supplied query.
   - Invoke `kusto-kusto_deeplink_from_query` with that command, cluster URI, and database when
     the tool is available. Record `generated`, `failed`, or `unavailable`. A deeplink failure
     never suppresses the command or recovery prompt.
   - Use the interactive ask-user tool once with one focused freeform question. State what
     automatic evidence was found, that the complete physical `QueryPlan` is missing, provide
     the clickable deeplink when available, show the exact command, tell the user to copy the
     `QueryPlan` result cell/JSON, and ask them to paste it or attach/save it and provide its
     path if too large.
   - Validate the response with `scripts\plan_recovery.py --payload-file`. Reject empty,
     malformed, logical-only, truncated, or incomplete operator trees with the exact
     deficiency. Require the physical `RootOperator`/`Operators`/`$type` structure emitted by
     the plan command; `ResultType`/`Content` and named `QueryPlan` cell envelopes are accepted.
     Retain only the allowlisted operator topology, compute raw and sanitized digests, and mark
     accepted evidence `user_supplied`. Bind every rendered physical node to the sanitized
     `node-<NodeId>`, normalized type, and parent-child topology; matching counts alone are
     insufficient.
   - Build the prompt state by running `python scripts\plan_recovery.py` with `--query-file`,
     `--record-prompt`, automatic-evidence, deficiency, deeplink-status, and UTC timestamp
     arguments. Submit its `prompt` through the interactive ask-user tool and retain its
     `recovery` record. Accepted user evidence and `ESTIMATED` fallback must consume that
     unresolved record. A boolean `prompted` value without a matching prompt digest is invalid.
   - If evidence remains unusable, ask again or use the ask-user tool to offer an explicit
     choice to continue `ESTIMATED`. Never infer consent from silence or an invalid payload.
     `ESTIMATED` is valid only after the prompt and an explicit decline, inability to provide,
     or choice after rejection; record that outcome and the missing `QueryPlan` in
     `estimate_reason`.
6. Populate the model according to
   [references/evidence-model.schema.json](references/evidence-model.schema.json). Preserve
   exactly these phases in order: Syntax, Semantic, Relop, Preparation, Initial optimize,
   Partial queries, Final optimize, Physical plan, Serialize/native boundary, Execute.
7. Follow [references/feature-parity-contract.md](references/feature-parity-contract.md) under
   the authoritative specification. Emit exactly 45 canonical substeps. Exactly S4.1, S4.4,
   S6.1, and S6.2 omit the runner, runner badge, lab, and placeholder. Every other substep has
   its canonical runner family and interaction count.
8. Follow [references/applicability-rules.md](references/applicability-rules.md). Inspect the
   current source that lowers the recorded final logical nodes into physical nodes (for example,
   the applicable `InitialQueryPlanBuilder.Visit*` methods). Every logical-to-physical mapping
   must name the exact builder method, link its current-HEAD source lines, reference a logical
   ID present in `plan.final_relop.logical_ids`, and reference physical IDs present in the
   evidenced physical tree.
9. Actively acquire optimizer trace evidence; do not stop at graceful degradation:

   - Inspect current source around `PassManager.Execute`, concrete `pass.Execute` calls, tree
     serialization, request context, and existing diagnostics. Discover the repository's own
     build/test/run commands; do not invent them.
   - First attempt an existing request-scoped trace path using only the exact non-executing
     `.show queryplan <|` command. Never send the query to an execution endpoint.
   - If existing diagnostics do not expose per-pass snapshots, and the user explicitly
     authorized an isolated local-development workspace, proceed autonomously: add the smallest
     request-scoped instrumentation around each applicable `pass.Execute`, capture the exact
     logical tree immediately before and after, correlate records to only that plan request,
     build/test with repository-supported commands, restart only that local service, issue the
     same plan-only request, capture the trace, and remove the instrumentation. Do not ask again
     between these local steps once authorization is explicit.
   - Run this lifecycle through `scripts\local_trace_driver.py`. Give it a new disposable
     worktree path outside the primary checkout, a free explicit loopback port, the
     instrumentation patch, repository-supported build/service argv arrays, and output/receipt
     paths outside both checkouts. The driver refuses occupied ports and non-loopback endpoints,
     resolves `--base-ref` to the current source HEAD, verifies the detached worktree HEAD,
     contains timed build/service trees in Windows Job Objects, never stops an existing process,
     sends the exact plan command itself, and removes every owned process plus the worktree path
     and registration in `finally`. It rejects a primary checkout with any tracked, staged, or
     untracked change and refuses build/service argv that reference the primary checkout.

     ```powershell
     python scripts\local_trace_driver.py `
       --primary-checkout "<Azure-Kusto-Service-workspace>" `
       --worktree "<new-sibling-worktree>" --base-ref "<workspace-HEAD>" `
       --instrumentation-patch "<request-scoped.patch>" `
       --build-command-json '["<repo-build-tool>","<validated-args>"]' `
       --service-command-json '["<built-local-engine>","<validated-args>"]' `
       --cluster-uri "http://127.0.0.1:<free-port>" `
       --trace-url "http://127.0.0.1:<free-port>/<source-verified-plan-endpoint>" `
       --database "<database>" --query-file "<query.kql>" `
       --request-scope "<deterministic-unique-scope>" `
       --trace-output "<outside-repos>\trace.json" `
       --receipt-file "<outside-repos>\receipt.json"
     ```

   - Never instrument a production/shared/remote service. If local modification authorization
     is absent, attempt only existing read-only tracing and record that boundary.
   - Validate captured output with `scripts\optimizer_trace.py`; bind each pass model entry to
     its unique `trace_pass_id`. Record authorization, attempt, method, build/restart results,
     request-scope digest, raw trace digest, cleanup, and failure in
     `optimizer_trace.acquisition`.
     For an instrumented local capture, use:

     ```powershell
     python scripts\optimizer_trace.py `
       --payload-file "<request-scoped-trace.json>" `
       --query-file "<query.kql>" `
       --authorization explicit_local `
       --workspace-kind local_development `
       --source-head "<workspace-HEAD>" `
       --cluster-uri "http://127.0.0.1:<free-port>" `
       --method request_scoped_local_instrumentation `
       --instrumentation-changed --build-attempted --build-succeeded `
       --restart-attempted --restart-succeeded --cleanup-status completed `
       --driver-receipt-file "<outside-repos>\receipt.json" `
       --final-relop-canonical-digest-sha256 `
         "<plan.final_relop.canonical_digest_sha256>"
     ```

   - Do not render a COMPLETE model with `attempted: false`. Runtime capture requires a
     request-scoped non-executing record and all captured pass records must be consumed exactly
     once. Instrumented capture also requires a valid driver receipt proving the worktree was
     outside the primary checkout, the chosen loopback port had no preexisting listener, the
     listener belonged to the driver-started PID tree, the primary checkout was unchanged, and
     every build/service process, port, worktree path, and worktree registration were cleaned up
     in `finally`. Keep the raw receipt outside the model/page; `optimizer_trace.py` validates it
     and emits only its digest plus nonsensitive proof booleans/enums.

   Never reconstruct pass history from the final RelopTree and final QueryPlan. `TRANSFORMED`
   and `SCHEDULED_NO_OP` require runtime per-pass before/after snapshots with matching digests.
   Trace events must have strictly increasing sequence, optimizer phase, canonical and concrete
   pass identities, the same request-scope digest, canonical parseable Relop JSON, verified `changed`,
   pass-to-pass continuity, and a terminal digest equal to
   `plan.final_relop.canonical_digest_sha256`.
   Only after active capture fails may source scheduling/control-flow evidence establish
   `EXECUTED_OUTCOME_NOT_CAPTURED`; render identical explicit `OUTCOME NOT CAPTURED` panes.
   With neither runtime snapshots nor source schedule evidence, use `NOT_TRACED`. Never label
   an uncaptured pass as transformed or no-op.
10. Only after the recovery rule above permits estimation, set top-level `evidence_mode` to
   `ESTIMATED`, state the recovery provenance, and keep every unsupported claim visibly
   estimated. Never blend estimated claims into observed evidence.
11. Validate and render against the same workspace:

   ```powershell
   python scripts\render_walkthrough.py `
     --model "<model.json>" `
     --source-workspace "<Azure-Kusto-Service-workspace>"
   ```

12. Inspect the generated page against
   [references/artifact-quality.md](references/artifact-quality.md).
13. After a valid page is rendered and saved, attempt best-effort publication only through:

    ```powershell
    .\scripts\Publish-Walkthrough.ps1 `
      -ModelPath "<model.json>" `
      -SourceWorkspace "<Azure-Kusto-Service-workspace>"
    ```

    Never perform or require a companion preflight, and never block, ask, or prompt the user
    about publication. If the publisher is absent, unsupported, unhealthy, or fails, preserve
    the model/page, continue successfully, and report bookmark status as `skipped` or `failed`
    with the warning. Declare `published` only when `CompanionResult.ok` is exactly boolean
    `true`.

## Completion gate

Do not claim success unless all are true:

- the renderer accepted the complete model;
- the page exists under `Documents\Bookmarks\<query-derived-slug>\<slug>.html`;
- the page visibly says `EVIDENCE` or `ESTIMATED`;
- the page visibly renders the actual final RelopTree, its digest, and optimizer trace status;
- the page visibly reports the optimizer trace acquisition attempt, authorization, safety,
  request-scope digest, instrumentation/build/restart/cleanup status, and any failure;
- physical lowering mappings link each recorded final logical ID to evidenced physical IDs via
  exact source-backed `Visit*` methods;
- the final output identifies automatic, user-supplied, or estimated-after-recovery plan
  provenance;
- every operator/action link is absolute, line-specific, and pinned to current workspace HEAD;
- every one of the ten phases has its exact canonical substeps and runner topology;
- the renderer's authoritative-spec audit reports all 93 requirements automated, zero manual,
  and no failures;

Walkthrough success does not depend on bookmark publication. Final output must include evidence
mode, plan provenance, HTML path, bookmark status (`published`, `skipped`, or `failed`), and any
publication warning or other limitations.
