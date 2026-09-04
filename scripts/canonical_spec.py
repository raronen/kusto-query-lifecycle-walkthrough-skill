from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalSubstep:
    key: str
    title: str
    runner_type: str | None
    item_count: int
    focus: int
    runner_mode: str = ""
    scenario_count: int = 0


CANONICAL_SUBSTEPS = (
    (
        CanonicalSubstep("0-0", "Accept and validate text", "compiler", 3, 0, "syntax"),
        CanonicalSubstep("0-1", "Apply syntax-affecting flags", "compiler", 3, 0, "syntax"),
        CanonicalSubstep("0-2", "Build the syntax tree", "compiler", 4, 5, "syntax"),
        CanonicalSubstep("0-3", "Gate on diagnostics", "compiler", 4, 10, "syntax"),
    ),
    (
        CanonicalSubstep("1-0", "Create semantic context", "compiler", 4, 0, "semantic"),
        CanonicalSubstep("1-1", "Resolve local entities", "compiler", 4, 6, "semantic"),
        CanonicalSubstep("1-2", "Resolve remote scope and schema", "compiler", 4, 10, "semantic"),
        CanonicalSubstep("1-3", "Bind operators and join", "compiler", 5, 15, "semantic"),
        CanonicalSubstep("1-4", "Gate semantic errors", "compiler", 4, 18, "semantic"),
    ),
    (
        CanonicalSubstep("2-0", "Validate result shape", "compiler", 4, 0, "relop"),
        CanonicalSubstep("2-1", "Translate pipe operators", "compiler", 5, 3, "relop"),
        CanonicalSubstep("2-2", "Create remote leaf", "compiler", 4, 12, "relop"),
        CanonicalSubstep("2-3", "Return RelopQuery", "compiler", 4, 19, "relop"),
    ),
    (
        CanonicalSubstep("3-0", "Create preparation PassManager", None, 0, 0),
        CanonicalSubstep("3-1", "Assign execution semantics", "pass", 4, 5),
        CanonicalSubstep("3-2", "Prepare catalog work", "pass", 3, 12),
        CanonicalSubstep("3-3", "Return prepared Relop", None, 0, 19),
    ),
    (
        CanonicalSubstep("4-0", "Run GenericOptimizationPhase", "pass", 22, 0),
        CanonicalSubstep("4-1", "Establish initial remote placement", "pass", 1, 9),
        CanonicalSubstep("4-2", "Run pre-distribution remoting #2", "pass", 1, 9),
        CanonicalSubstep("4-3", "Expose work, then remoting #3", "pass", 3, 16),
        CanonicalSubstep("4-4", "Finalize initial optimization", "pass", 3, 20),
    ),
    (
        CanonicalSubstep("5-0", "Collect partial-query operators", None, 0, 0),
        CanonicalSubstep("5-1", "Take the no-op path for this query", None, 0, 13),
        CanonicalSubstep("5-2", "Understand the optional evaluation path", "pass", 29, 5),
        CanonicalSubstep("5-3", "Substitute and re-optimize", "pass", 6, 10),
    ),
    (
        CanonicalSubstep("6-0", "Run post-substitution rewrites", "pass", 23, 0),
        CanonicalSubstep("6-1", "Retry remoting after substitution", "pass", 3, 10),
        CanonicalSubstep("6-2", "Prepare graph operators", "pass", 1, 0),
        CanonicalSubstep("6-3", "Freeze placement and distribute", "pass", 11, 14),
        CanonicalSubstep("6-4", "Finish final phases", "pass", 15, 17),
    ),
    (
        CanonicalSubstep("7-0", "Create builder context", "physical", 5, 0, "CONTEXT ASSEMBLY"),
        CanonicalSubstep("7-1", "Walk and lower the tree", "physical", 8, 2, "VISITOR + UNWIND"),
        CanonicalSubstep("7-2", "Create the physical hash join", "physical", 7, 8, "JOIN ASSEMBLY"),
        CanonicalSubstep("7-3", "Generate the remote query node", "physical", 7, 12, "REMOTE KQL COMPILATION"),
        CanonicalSubstep("7-4", "Finalize and package QueryPlan", "pass", 17, 16),
    ),
    (
        CanonicalSubstep("8-0", "Serialize the physical tree", "boundary", 6, 0),
        CanonicalSubstep("8-1", "Serialize query context", "boundary", 5, 5),
        CanonicalSubstep("8-2", "Submit through managed processor", "boundary", 7, 9),
    ),
    (
        CanonicalSubstep("9-0", "Deserialize native operators", "execute", 7, 0, scenario_count=3),
        CanonicalSubstep("9-1", "Construct the Rust-backed join", "execute", 7, 2, scenario_count=3),
        CanonicalSubstep("9-2", "Enter Rust", "execute", 7, 3, scenario_count=3),
        CanonicalSubstep("9-3", "Pull C++ children through callbacks", "execute", 8, 6, scenario_count=4),
        CanonicalSubstep("9-4", "Execute the remote right child", "execute", 8, 8, scenario_count=4),
        CanonicalSubstep("9-5", "Stream results and complete", "execute", 7, 14, scenario_count=4),
    ),
)

CANONICAL_SUBSTEP_COUNT = sum(len(stage) for stage in CANONICAL_SUBSTEPS)
RUNNERLESS_KEYS = frozenset(
    substep.key
    for stage in CANONICAL_SUBSTEPS
    for substep in stage
    if substep.runner_type is None
)
RUNNER_BY_KEY = {
    substep.key: substep.runner_type
    for stage in CANONICAL_SUBSTEPS
    for substep in stage
}
CANONICAL_BY_KEY = {
    substep.key: substep for stage in CANONICAL_SUBSTEPS for substep in stage
}

BOUNDARY_LANES_BY_KEY = {
    "8-0": ("C#",) * 6,
    "8-1": ("C#",) * 5,
    "8-2": ("C#", "C#", "C#", "C#", "Interop", "C++", "C++"),
}

NETWORK_OVERRIDES = {
    "1-0": ("possible", "May fetch"),
    "1-2": ("possible", "May fetch"),
    "5-2": ("possible", "Conditional"),
    "7-3": ("none", "No HTTP"),
    "8-2": ("none", "No external HTTP"),
    "9-3": ("imminent", "HTTP imminent"),
    "9-4": ("active", "HTTP active"),
    "9-5": ("none", "HTTP response consumed"),
}
