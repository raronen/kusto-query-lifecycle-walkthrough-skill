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

Use `TRANSFORMED` only when the before and after representations differ and evidence ties the
change to that pass. Use `SCHEDULED_NO_OP` when scheduling is evidenced but before and after
are identical. Do not create a generic catalog of passes or a pass runner for irrelevant
optimizations.

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
