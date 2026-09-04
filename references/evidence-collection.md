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

Keep raw proprietary plans outside this repository and out of the generated HTML. The model
must describe operators without embedding confidential payloads, literals, tenant data, or
internal identifiers.

## Evidence modes

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
