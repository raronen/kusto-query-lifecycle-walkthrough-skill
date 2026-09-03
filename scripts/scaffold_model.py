from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from model_contract import (
    ModelError,
    RUNNER_TYPES,
    STAGES,
    is_authorized_source_remote,
    query_slug,
    validate_cluster_uri,
)


def resolve_head(workspace: str | None, project: str) -> str:
    if not workspace:
        raise ValueError("--source-workspace is required")
    path = Path(workspace).expanduser().resolve()
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    head = result.stdout.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("Source workspace HEAD is not a full commit.")
    remote = subprocess.run(
        ["git", "-C", str(path), "remote", "get-url", "origin"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not is_authorized_source_remote(remote, project):
        raise ValueError("Source workspace origin is not msazure/Azure-Kusto-Service.")
    return head


def _table(stage_id: str) -> dict[str, Any]:
    return {
        "id": f"{stage_id}-context",
        "title": "Pending query-specific context",
        "columns": ["Property", "Query-specific value"],
        "rows": [["Evidence", "Pending"]],
        "source_links": [],
    }


def _action(action_id: str, title: str) -> dict[str, Any]:
    return {
        "id": action_id,
        "title": title,
        "evidence_kind": "PENDING",
        "what": "Pending query-specific evidence.",
        "why": "Pending source-grounded explanation.",
        "result": "Pending result.",
        "stack_effect": "Pending stack effect.",
        "heap_effect": "Pending heap or lifetime effect.",
        "before": "Pending input.",
        "after": "Pending output.",
        "source_links": [],
    }


def _snapshots(stage_id: str) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{stage_id}-enter",
            "label": "Enter",
            "progress": 0,
            "current": "input",
            "movement": "input-to-owner",
            "return_value": "owner-to-input",
            "next": "owner",
            "visible_state": "Pending runner entry state.",
            "source_links": [],
        },
        {
            "id": f"{stage_id}-leave",
            "label": "Leave",
            "progress": 100,
            "current": "owner",
            "movement": "owner-to-output",
            "return_value": "output-to-owner",
            "next": "output",
            "visible_state": "Pending runner result state.",
            "source_links": [],
        },
    ]


def _common_runner(stage_id: str, title: str) -> dict[str, Any]:
    runner_type = RUNNER_TYPES[stage_id]
    runner = {
        "type": runner_type,
        "title": f"Run the {title.lower()} {runner_type} yourself",
        "actions": [_action(f"{stage_id}-runner-action", "Inspect the pending action")],
        "snapshots": _snapshots(stage_id),
        "experiments": [
            {
                "id": f"{stage_id}-experiment",
                "title": "Pending query-specific experiment",
                "control": "select",
                "options": [
                    {
                        "id": f"{stage_id}-baseline",
                        "label": "Inspect the baseline",
                    },
                    {
                        "id": f"{stage_id}-alternative",
                        "label": "Inspect the alternate gate",
                    },
                ],
                "results": [
                    {
                        "option_id": f"{stage_id}-baseline",
                        "result": "Pending baseline result.",
                    },
                    {
                        "option_id": f"{stage_id}-alternative",
                        "result": "Pending alternate result.",
                    },
                ],
                "source_links": [],
            }
        ],
        "no_op": {
            "enabled": False,
            "gates": [],
            "reasons": [],
        },
        "source_links": [],
    }
    if runner_type == "pass":
        runner["actions"][0].update(
            {
                "traversal": "Pending traversal.",
                "predicate": "Pending predicate.",
                "applicability": "Pending query-specific applicability.",
                "optimization": "Pending optimization target.",
            }
        )
    return runner


def _compiler_runner(stage_id: str) -> dict[str, Any]:
    compiler: dict[str, Any] = {
        "mode": {
            "syntax": "syntax",
            "semantic": "semantic",
            "relop": "csl-to-relop",
        }[stage_id],
        "before_actions": [
            _action(f"{stage_id}-before-action", "Inspect compiler input")
        ],
        "after_actions": [
            _action(f"{stage_id}-after-action", "Inspect compiler output")
        ],
        "mapping": [],
    }
    mapping_kind = {
        "semantic": "semantic",
        "relop": "csl-to-relop",
    }.get(stage_id)
    if mapping_kind:
        compiler["mapping"] = [
            {
                "from": "Pending input construct.",
                "to": "Pending output construct.",
                "reason": f"Pending exact {mapping_kind} source evidence.",
                "source_links": [],
            }
        ]
    return compiler


def _pass_runner(stage_id: str) -> dict[str, Any]:
    return {
        "applicable_passes": [
            {
                "id": f"{stage_id}-applicable-pass",
                "title": "Pending applicable pass",
                "traversal": "Pending traversal.",
                "predicate": "Pending predicate.",
                "applicability": "Pending query-specific applicability.",
                "optimization": "Pending optimized property.",
                "before": "Pending cumulative input.",
                "after": "Pending cumulative output.",
                "outcome": "ESTIMATED",
                "source_links": [],
            }
        ],
        "cumulative_before": "Pending cumulative input.",
        "cumulative_after": "Pending cumulative output.",
        "additional_context_tables": [_table(stage_id)],
    }


def _physical_runner(stage_id: str) -> dict[str, Any]:
    return {
        "input_contract": {
            "title": "Pending physical-plan input contract",
            "collapsible": True,
            "fields": [
                {
                    "name": "pending",
                    "type": "unknown",
                    "nullable": True,
                    "description": "Replace with an evidenced input field.",
                }
            ],
            "source_links": [],
        },
        "full_plan": {
            "complete": False,
            "operator_count": 0,
            "roots": [],
        },
        "logical_to_physical": [],
    }


def _boundary_item(
    item_id: str, fields: dict[str, str]
) -> dict[str, Any]:
    return {"id": item_id, **fields, "source_links": []}


def _boundary_runner(stage_id: str) -> dict[str, Any]:
    lanes = []
    for lane_id in ("managed", "json", "utf-8", "native"):
        lanes.append(
            {
                "id": lane_id,
                "boundary_id": f"{stage_id}-{lane_id}",
                "title": f"Pending {lane_id} lane",
                "input": "Pending input.",
                "output": "Pending output.",
                "source_links": [],
            }
        )
    return {
        "lanes": lanes,
        "representations": {
            name: {
                "label": f"Pending {name} representation",
                "content": "Pending.",
                "source_links": [],
            }
            for name in ("object", "json", "bytes")
        },
        "node_byte_ranges": [
            {
                "node_id": "pending-node",
                "start": 0,
                "end": 1,
                "description": "Replace with an evidenced half-open byte range.",
                "source_links": [],
            }
        ],
        "selectable_views": [
            _boundary_item(
                f"{stage_id}-view",
                {"title": "Pending view", "content": "Pending representation."},
            )
        ],
        "context_toggle_comparisons": [
            _boundary_item(
                f"{stage_id}-context-toggle",
                {
                    "title": "Pending context comparison",
                    "without_context": "Pending.",
                    "with_context": "Pending.",
                },
            )
        ],
        "failure_injections": [
            _boundary_item(
                f"{stage_id}-failure",
                {
                    "title": "Pending failure injection",
                    "injection": "Pending.",
                    "expected_failure": "Pending.",
                },
            )
        ],
        "debugger_map": [
            _boundary_item(
                f"{stage_id}-debugger",
                {
                    "boundary_id": f"{stage_id}-managed",
                    "managed_location": "Pending managed breakpoint.",
                    "native_location": "Pending native breakpoint.",
                },
            )
        ],
    }


def _execute_runner(stage_id: str) -> dict[str, Any]:
    return {
        "action_timeline": [
            {
                "id": f"{stage_id}-timeline-action",
                "title": "Pending execution action",
                "what": "Pending.",
                "why": "Pending.",
                "stack_effect": "Pending.",
                "heap_effect": "Pending.",
                "source_links": [],
            }
        ],
        "language_lanes": [
            {
                "language": "Managed",
                "role": "Pending evidenced role.",
                "applicability": "Pending query-specific applicability.",
                "source_links": [],
            }
        ],
        "call_stack": [
            {
                "position": 0,
                "language": "Managed",
                "frame": "Pending conceptual frame.",
                "what": "Pending.",
                "why": "Pending.",
                "source_links": [],
            }
        ],
        "heap_zones": [
            {
                "id": f"{stage_id}-heap",
                "language": "Managed",
                "state": "live",
                "what": "Pending applicable heap or lifetime zone.",
                "why": "Pending.",
                "owner": "Pending.",
                "source_links": [],
            }
        ],
        "components": [
            {
                "id": f"{stage_id}-component",
                "name": "Pending runtime component",
                "evidence_ref": "pending-physical-or-boundary-id",
                "state": "not-created",
                "role": "Pending.",
                "pull_direction": "Pending.",
                "data_direction": "Pending.",
                "ownership": "Pending.",
                "breakpoint": "Pending.",
                "source_links": [],
            }
        ],
        "scenarios": [
            {
                "type": scenario_type,
                "trigger": "Pending.",
                "behavior": "Pending.",
                "ownership_effect": "Pending.",
                "source_links": [],
            }
            for scenario_type in ("failure", "cancellation", "memory", "lifetime")
        ],
    }


def _runner(stage_id: str, title: str) -> dict[str, Any]:
    runner = _common_runner(stage_id, title)
    runner_type = runner["type"]
    runner[runner_type] = {
        "compiler": _compiler_runner,
        "pass": _pass_runner,
        "physical": _physical_runner,
        "boundary": _boundary_runner,
        "execute": _execute_runner,
    }[runner_type](stage_id)
    return runner


def _stage(
    stage_id: str,
    title: str,
    kind: str,
    order: int,
    query_hint: str,
) -> dict[str, Any]:
    node_input = f"{stage_id}-input"
    node_owner = f"{stage_id}-owner"
    node_output = f"{stage_id}-output"
    stage: dict[str, Any] = {
        "id": stage_id,
        "order": order,
        "title": title,
        "kind": kind,
        "evidence_kind": "PENDING",
        "no_op_explanation": "",
        "source_links": [],
        "overview": {
            "input": f"Pending input for query shape: {query_hint}.",
            "output": "Pending query-specific output.",
            "owner": "Pending owning component.",
            "not_responsible": "Pending responsibility boundary.",
            "handoff": "Pending handoff.",
        },
        "substeps": [
            {
                "id": f"{stage_id}-query-path",
                "title": f"Trace {title.lower()} for the supplied query",
                "behavior": "Pending query-specific behavior.",
                "change_badge": "PENDING",
                "summary": f"Draft substep derived from query shape: {query_hint}.",
                "what_happens": "Pending evidence collection.",
                "why": "Pending source-grounded rationale.",
                "debug": "Pending exact breakpoint and inspection guidance.",
                "next": "Pending lifecycle handoff.",
                "method_path": ["Pending exact method path."],
                "source_links": [],
                "traversal": {
                    "nodes": [
                        {
                            "id": node_input,
                            "label": "Input",
                            "state": "Query-specific stage input.",
                            "source_links": [],
                        },
                        {
                            "id": node_owner,
                            "label": "Owner",
                            "state": "Pending owning method.",
                            "source_links": [],
                        },
                        {
                            "id": node_output,
                            "label": "Output",
                            "state": "Query-specific stage output.",
                            "source_links": [],
                        },
                    ],
                    "snapshots": [
                        {
                            "id": f"{stage_id}-traversal-enter",
                            "current": node_input,
                            "movement": node_owner,
                            "return_value": node_input,
                            "next": node_owner,
                        },
                        {
                            "id": f"{stage_id}-traversal-exit",
                            "current": node_owner,
                            "movement": node_output,
                            "return_value": node_owner,
                            "next": node_output,
                        },
                    ],
                },
                "artifact": {
                    "title": "Pending before/after artifact",
                    "collapsed_by_default": False,
                    "before": "Pending input representation.",
                    "after": "Pending output representation.",
                    "operators": [
                        {
                            "id": node_input,
                            "label": "Input operator",
                            "state": "before",
                            "source_links": [],
                        },
                        {
                            "id": node_output,
                            "label": "Output operator",
                            "state": "after",
                            "source_links": [],
                        },
                    ],
                },
                "runner": _runner(stage_id, title),
            }
        ],
    }
    if kind == "optimizer":
        stage["additional_context"] = {
            "summary": "Pending cumulative optimizer context.",
            "tables": [_table(stage_id)],
        }
    return stage


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a non-executing draft model for a Kusto lifecycle walkthrough."
    )
    parser.add_argument("--query-file", required=True)
    parser.add_argument("--cluster-uri", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-workspace", required=True)
    parser.add_argument("--project", default="One")
    args = parser.parse_args()

    query_path = Path(args.query_file).expanduser().resolve()
    query = query_path.read_text(encoding="utf-8")
    if not query.strip():
        parser.error("--query-file must contain non-empty query text")
    try:
        validate_cluster_uri(args.cluster_uri, "--cluster-uri")
    except ModelError as exc:
        parser.error(str(exc))
    database = args.database.strip()
    if not database:
        parser.error("--database must not be empty")

    slug = query_slug(query, args.cluster_uri, database)
    query_terms = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query)[:5]
    query_hint = " ".join(query_terms) if query_terms else "supplied query"
    head = resolve_head(args.source_workspace, args.project)
    model = {
        "schema_version": "2.0",
        "model_state": "DRAFT",
        "evidence_mode": "ESTIMATED",
        "estimate_reason": "Plan evidence has not been collected.",
        "query": {
            "text": query,
            "cluster_uri": args.cluster_uri,
            "database": database,
            "title": "Kusto query lifecycle walkthrough",
            "slug": slug,
        },
        "source": {
            "organization": "msazure",
            "project": args.project,
            "repository": "Azure-Kusto-Service",
            "workspace_head": head,
        },
        "plan": {
            "tool": "pending non-executing query-plan collection",
            "collected_at_utc": "",
            "non_executing": True,
            "digest_sha256": "",
            "operator_count": 0,
        },
        "network_beacon": {
            "state": "ENABLED",
            "route": (
                f"https://dev.azure.com/msazure/{args.project}/"
                "_git/Azure-Kusto-Service"
            ),
            "purpose": "Outbound source navigation to exact commit-pinned implementation lines.",
        },
        "stages": [
            _stage(stage_id, title, kind, index, query_hint)
            for index, (stage_id, title, kind) in enumerate(STAGES, start=1)
        ],
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(model, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"model": str(output), "slug": slug, "state": "DRAFT"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
