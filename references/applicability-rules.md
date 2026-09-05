# Applicability rules

## Optimizer labs

Include an optimizer action only when the supplied query and evidence establish applicability.
Put each applicable action in the relevant query-specific substep runner. Each action requires:

- before and after representations;
- traversal order or visited nodes;
- the predicate evaluated by the pass;
- why that predicate applies to this query;
- the specific cost/shape/property optimized;
- exact source evidence;
- evidence kind.

Use `TRANSFORMED` only when runtime per-pass before/after snapshots differ, their digests match,
and evidence ties those snapshots to that pass. Use `SCHEDULED_NO_OP` only when the same runtime
trace captures identical before/after snapshots. Never infer either result by comparing the
final RelopTree with the final physical QueryPlan.

When pinned source control flow proves execution but runtime per-pass snapshots are absent, use
`EXECUTED_OUTCOME_NOT_CAPTURED`; both panes must explicitly say `OUTCOME NOT CAPTURED`. When
neither runtime snapshots nor execution evidence exists, use `NOT_TRACED`. Do not create a
generic catalog of passes or a pass runner for irrelevant optimizations.

Do not choose either fallback until active optimizer trace acquisition has been attempted.
When an isolated local-development workspace is explicitly authorized, missing trace support
requires request-scoped instrumentation around `pass.Execute`, a supported local build/restart,
one non-executing plan request, capture, and cleanup. Bind every captured pass through
`runtime_evidence.trace_pass_id`.

Instrumentation additionally requires a loopback `query.cluster_uri`, a free explicit port, a
disposable sibling worktree, and the packaged driver's cleanup receipt. The trace must bind
sequence, optimizer phase, canonical and concrete pass identity, request scope, canonical Relop
snapshots, verified change, continuity, and the terminal final-Relop digest.

Every optimizer phase still has at least one query-specific substep. If the phase schedules no
applicable transformation, its pass runner must show the evaluated evidence gates, the
unchanged before/after artifact, and the precise reason each gate prevents a rewrite.

## No-op phases

All ten phases remain visible. A no-op explanation must identify the relevant query shape and
the missing trigger, work item, or boundary. Avoid vague text such as "nothing happened" or
"not applicable." Every no-op substep retains traversal, artifact, experiment, and runner
controls so the user can inspect why the phase does not transform or execute work.

## Physical plan

When evidence mode is `EVIDENCE`, render the complete physical tree from the plan, preserving
all operators and relationships. Set `complete` only after comparing the model operator count
with the sanitized plan operator count. Every node must have an exact source link.

In `ESTIMATED` mode, call the section "Estimated physical plan" and identify every inferred
node. Never present a simplified cartoon as the complete plan.

Every logical-to-physical mapping must name the exact lowering `Visit*` method, link its pinned
source lines, use a logical ID derived from `plan.final_relop.content`, and cover physical IDs in
the evidenced tree. The rendered page must show the actual final RelopTree above these mappings.
Mappings must cover every final logical ID. Every mapped pair must also appear in the target
physical operator's `logical_operator_ids`; duplicate logical mappings, duplicate pairs, and
contradictory pairs are invalid.

## Serialization and execution

Include only boundaries/operators present in the supplied evidence. Each execution event must
provide:

- user-driven event and timeline position;
- mixed-language conceptual call stack, limited to evidenced languages;
- managed/C++/Rust heap or query-lifetime zones only where applicable;
- borrowed/owned/released state and evidence basis;
- runtime components after the stack and heap regions;
- pull direction and data direction;
- current ownership and next breakpoint;
- failure, cancellation, and lifetime scenarios;
- exact source links.

Use conceptual frames. Do not claim concrete stack locations, addresses, allocators, or sizes
without direct evidence.
