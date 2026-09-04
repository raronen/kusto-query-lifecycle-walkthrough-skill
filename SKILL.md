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

Forbidden:

- executing the supplied query, even to sample one row;
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

4. Attempt to collect real non-executing plan evidence. Inspect the returned payload and
   explicitly prove that it contains a complete physical `QueryPlan` operator tree. Logical
   Relop, hints, statistics, or a missing/truncated `QueryPlan` cell are not complete evidence.
   Record the tool, timestamp, provenance, and sanitized plan digest. Keep proprietary raw
   output out of this repository; include a redacted raw-plan section in the local model/page
   only when authorized and evidence-safe.
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
8. Follow [references/applicability-rules.md](references/applicability-rules.md). Keep no-op
   phases with a precise query-specific explanation. Include optimizer labs only for
   applicable passes. Distinguish `TRANSFORMED` from `SCHEDULED_NO_OP`.
9. Only after the recovery rule above permits estimation, set top-level `evidence_mode` to
   `ESTIMATED`, state the recovery provenance, and keep every unsupported claim visibly
   estimated. Never blend estimated claims into observed evidence.
10. Validate and render against the same workspace:

   ```powershell
   python scripts\render_walkthrough.py `
     --model "<model.json>" `
     --source-workspace "<Azure-Kusto-Service-workspace>"
   ```

11. Inspect the generated page against
   [references/artifact-quality.md](references/artifact-quality.md).
12. After a valid page is rendered and saved, attempt best-effort publication only through:

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
- the final output identifies automatic, user-supplied, or estimated-after-recovery plan
  provenance;
- every operator/action link is absolute, line-specific, and pinned to current workspace HEAD;
- every one of the ten phases has its exact canonical substeps and runner topology;
- the renderer's authoritative-spec audit reports all 93 requirements automated, zero manual,
  and no failures;

Walkthrough success does not depend on bookmark publication. Final output must include evidence
mode, plan provenance, HTML path, bookmark status (`published`, `skipped`, or `failed`), and any
publication warning or other limitations.
