---
name: kusto-query-lifecycle-walkthrough
description: Generate an evidence-grounded, interactive Kusto query lifecycle walkthrough from query text, a cluster URI, and a database without executing the query. Uses non-executing query-plan evidence and an authorized local Azure-Kusto-Service workspace, labels source-only fallbacks ESTIMATED, renders all ten lifecycle phases, and publishes the self-contained page through the existing bookmark companion.
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

4. Attempt to collect real non-executing plan evidence. Record the tool, timestamp, and
   sanitized plan digest, not proprietary raw output.
5. Populate the model according to
   [references/evidence-model.schema.json](references/evidence-model.schema.json). Preserve
   exactly these phases in order: Syntax, Semantic, Relop, Preparation, Initial optimize,
   Partial queries, Final optimize, Physical plan, Serialize/native boundary, Execute.
6. Follow [references/feature-parity-contract.md](references/feature-parity-contract.md).
   Every phase needs query-specific substeps, and every substep needs a phase-appropriate
   interactive `Run the ... yourself` runner. Missing runners are invalid. No-op substeps keep
   their runner and expose the evidence gates and reasons that prevent work.
7. Follow [references/applicability-rules.md](references/applicability-rules.md). Keep no-op
   phases with a precise query-specific explanation. Include optimizer labs only for
   applicable passes. Distinguish `TRANSFORMED` from `SCHEDULED_NO_OP`.
8. If real plan evidence is unavailable, set top-level `evidence_mode` to `ESTIMATED`, state
   the reason, and keep every unsupported claim visibly estimated. Never blend estimated
   claims into observed evidence.
9. Validate and render against the same workspace:

   ```powershell
   python scripts\render_walkthrough.py `
     --model "<model.json>" `
     --source-workspace "<Azure-Kusto-Service-workspace>"
   ```

10. Inspect the generated page against
   [references/artifact-quality.md](references/artifact-quality.md).
11. Publish only through:

    ```powershell
    .\scripts\Publish-Walkthrough.ps1 `
      -ModelPath "<model.json>" `
      -SourceWorkspace "<Azure-Kusto-Service-workspace>"
    ```

    Success requires `CompanionResult.ok` to be exactly boolean `true`. If rendering or
    publication fails, preserve the model/page and report the exact failed step.

## Completion gate

Do not claim success unless all are true:

- the renderer accepted the complete model;
- the page exists under `Documents\Bookmarks\<query-derived-slug>\<slug>.html`;
- the page visibly says `EVIDENCE` or `ESTIMATED`;
- every operator/action link is absolute, line-specific, and pinned to current workspace HEAD;
- every one of the ten phases has query-specific substeps and every substep has a validated
  interactive runner;
- the bookmark publisher ran for that page;
- `CompanionResult.ok` is exactly `true`.

Final output must include evidence mode, HTML path, bookmark destination, and any limitations.
