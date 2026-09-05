from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from model_contract import STAGES, query_slug
from scaffold_model import _stage


HEAD = "a" * 40
QUERY = (Path(__file__).parent / "fixtures" / "synthetic-query.kql").read_text(encoding="utf-8")
CLUSTER = "https://example.kusto.windows.net"
DATABASE = "Synthetic"


def source_link(label: str, line: int = 10) -> dict[str, Any]:
    path = "/synthetic/Component.cs"
    query = urlencode(
        {
            "path": path,
            "version": f"GC{HEAD}",
            "line": line,
            "lineEnd": line + 3,
            "lineStartColumn": 1,
            "lineEndColumn": 1,
            "syntheticAnchor": label,
        }
    )
    return {
        "label": label,
        "url": f"https://dev.azure.com/msazure/One/_git/Azure-Kusto-Service?{query}",
        "path": path,
        "start_line": line,
        "end_line": line + 2,
        "commit": HEAD,
    }


def _fill_links(value: Any, counter: list[int]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "source_links" and isinstance(child, list) and not child:
                counter[0] += 1
                value[key] = [
                    source_link(
                        f"Synthetic source evidence {counter[0]}",
                        10 + counter[0] % 150,
                    )
                ]
            else:
                _fill_links(child, counter)
    elif isinstance(value, list):
        for child in value:
            _fill_links(child, counter)


def _set_evidence(value: Any, kind: str) -> None:
    if isinstance(value, dict):
        if value.get("evidence_kind") == "PENDING":
            value["evidence_kind"] = kind
        for child in value.values():
            _set_evidence(child, kind)
    elif isinstance(value, list):
        for child in value:
            _set_evidence(child, kind)


def _schema_field(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "type": "string",
        "nullable": False,
        "description": f"Synthetic {name} field.",
    }


def _operator(
    operator_id: str,
    node_id: str,
    name: str,
    children: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "operator_id": operator_id,
        "node_id": node_id,
        "name": name,
        "details": f"Synthetic details for {name}.",
        "logical_operator_ids": [f"logical-{operator_id}"],
        "input_schema": [_schema_field("input")],
        "output_schema": [_schema_field("output")],
        "key_indexes": [0],
        "execution_eligibility": "Eligible for the synthetic execution path.",
        "rust_eligibility": "Eligible only where the synthetic native boundary permits it.",
        "target_scope": "Synthetic local scope.",
        "remote_metadata": {
            "applicable": False,
            "cluster": "",
            "database": "",
            "endpoint": "",
            "reason": "The synthetic fixture has no remote query.",
            "source_links": [],
        },
        "source_links": [],
        "children": children,
    }


def rich_model() -> dict[str, Any]:
    stages = [
        _stage(stage_id, title, kind, index, "SyntheticEvents where Severity")
        for index, (stage_id, title, kind) in enumerate(STAGES, start=1)
    ]
    for stage in stages:
        stage_id = stage["id"]
        outcome = (
            "SCHEDULED_NO_OP"
            if stage_id == "partial-queries"
            else "TRANSFORMED"
            if stage_id in {"initial-optimize", "final-optimize"}
            else "OBSERVED"
        )
        stage["evidence_kind"] = outcome
        stage["no_op_explanation"] = (
            "The synthetic query has no partition boundary, so the scheduled pass inspects "
            "its gates and leaves the tree unchanged."
            if outcome == "SCHEDULED_NO_OP"
            else ""
        )
        for substep in stage["substeps"]:
            substep["behavior"] = f"Query-specific {stage['title']} behavior."
            substep["change_badge"] = outcome
            substep["summary"] = f"Synthetic walkthrough for {substep['title']}."
            substep["what_happens"] = f"The {stage['title']} owner processes the synthetic shape."
            substep["why"] = "This state is required before the next lifecycle handoff."
            substep["debug"] = "Break at the linked synthetic method and inspect the current node."
            substep["next"] = "Advance to the next evidenced lifecycle owner."
            substep["method_path"] = [
                {
                    "name": f"Synthetic.{stage_id}.Enter",
                    "source_links": [],
                },
                {
                    "name": f"Synthetic.{stage_id}.Leave",
                    "source_links": [],
                },
            ]
            substep["artifact"]["title"] = f"{substep['title']} synthetic artifact"
            substep["artifact"]["before"] = f"{substep['id']}: before"
            substep["artifact"]["after"] = (
                substep["artifact"]["before"]
                if outcome == "SCHEDULED_NO_OP"
                else f"{substep['id']}: after"
            )
            if "runner" not in substep:
                continue
            runner = substep["runner"]
            runner["title"] = f"Run the {substep['title'].lower()} {runner['type']} yourself"
            runner["no_op"] = {
                "enabled": outcome == "SCHEDULED_NO_OP",
                "gates": ["Synthetic partition gate is absent."] if outcome == "SCHEDULED_NO_OP" else [],
                "reasons": ["The tree remains unchanged."] if outcome == "SCHEDULED_NO_OP" else [],
            }
            runner["experiments"][0]["title"] = f"Compare {substep['title']} evidence gates"
            for action in runner["actions"]:
                action["evidence_kind"] = outcome
                action["what"] = f"Apply the synthetic {stage['title']} action."
                action["why"] = "The linked evidence establishes this action."
                action["result"] = "The synthetic state advances visibly."
                action["stack_effect"] = "Compiler-only until execution; no concrete stack address claimed."
                action["heap_effect"] = "Lifetime ownership is described conceptually without byte-size claims."
                action["before"] = f"{substep['id']}: runner before"
                action["after"] = (
                    action["before"] if outcome == "SCHEDULED_NO_OP" else f"{substep['id']}: runner after"
                )
                if runner["type"] == "pass":
                    action["traversal"] = "Root to synthetic filter to source."
                    action["predicate"] = "The synthetic filter shape matches the pass gate."
                    action["applicability"] = "The supplied synthetic query contains that filter."
                    action["optimization"] = "Reduces synthetic rows before projection."
            if runner["type"] == "compiler":
                for action in runner["compiler"]["before_actions"] + runner["compiler"]["after_actions"]:
                    action["evidence_kind"] = "OBSERVED"
                    action["what"] = "Inspect the synthetic compiler state."
                    action["why"] = "The compiler action is present in the synthetic path."
                    action["result"] = "The compiler representation is visible."
                    action["stack_effect"] = "No runtime stack effect."
                    action["heap_effect"] = "No runtime heap effect."
                    action["before"] = "Synthetic compiler input."
                    action["after"] = "Synthetic compiler output."
            if runner["type"] == "pass":
                for item_index, item in enumerate(runner["pass"]["applicable_passes"]):
                    item_outcome = (
                        "SCHEDULED_NO_OP"
                        if substep["id"] == "4-0" and item_index >= 5
                        else outcome
                    )
                    item["title"] = f"Applicable {stage['title']} synthetic pass"
                    item["concrete_pass"] = (
                        f"Synthetic.{stage_id.replace('-', '_')}."
                        f"Pass{item_index + 1}"
                    )
                    item["outcome"] = item_outcome
                    item["before"] = f"{substep['id']}: cumulative before"
                    item["after"] = (
                        item["before"]
                        if item_outcome == "SCHEDULED_NO_OP"
                        else f"{substep['id']}: cumulative after"
                    )
                    item["runtime_evidence"] = {
                        "captured": False,
                        "trace_pass_id": "",
                        "sequence": 0,
                        "before_digest_sha256": "",
                        "after_digest_sha256": "",
                    }
                runner["pass"]["cumulative_before"] = f"{substep['id']}: cumulative before"
                runner["pass"]["cumulative_after"] = (
                    runner["pass"]["cumulative_before"]
                    if outcome == "SCHEDULED_NO_OP"
                    else f"{substep['id']}: cumulative after"
                )

    child = _operator("op-source", "node-2", "IteratorScan", [])
    root = _operator("op-filter", "node-1", "HashJoin", [child])
    for substep in stages[7]["substeps"][:4]:
        physical = substep["runner"]["physical"]
        physical["full_plan"] = {"complete": True, "operator_count": 2, "roots": [root]}
        physical["logical_to_physical"] = [
            {
                "logical_id": "logical-op-filter",
                "physical_operator_ids": ["op-filter"],
                "builder_method": "InitialQueryPlanBuilder.VisitFilter",
                "reason": "The synthetic logical filter maps to the physical filter.",
                "source_links": [],
            },
            {
                "logical_id": "logical-op-source",
                "physical_operator_ids": ["op-source"],
                "builder_method": "InitialQueryPlanBuilder.VisitTable",
                "reason": "The synthetic logical source maps to the physical source.",
                "source_links": [],
            },
        ]

    for substep in stages[9]["substeps"]:
        execute = substep["runner"]["execute"]
        execute["components"][0]["evidence_ref"] = "op-filter"
        execute["components"][0]["state"] = "active"
        execute["components"][0]["ownership"] = "The synthetic coordinator owns the current batch."
        execute["components"][0]["breakpoint"] = "Before the synthetic predicate callback."
        for event in execute["action_timeline"]:
            event.update(
                {
                    "title": "Pull the next synthetic batch",
                    "what": "The coordinator requests the next batch.",
                    "why": "The pull model drives the evidenced operators.",
                    "stack_effect": "Adds the conceptual operator frame at the top.",
                    "heap_effect": "Keeps the query-lifetime state live.",
                }
            )
        execute["language_lanes"][0].update(
            {
                "role": "Coordinates the synthetic pull.",
                "applicability": "The supplied synthetic plan uses this managed coordinator.",
            }
        )
        execute["call_stack"][0].update(
            {
                "frame": "SyntheticCoordinator.Pull",
                "what": "Requests the next batch.",
                "why": "This is the top conceptual frame for the event.",
            }
        )
        execute["heap_zones"][0].update(
            {
                "what": "Synthetic query-lifetime token.",
                "why": "The request remains active during the pull.",
                "owner": "SyntheticCoordinator",
            }
        )
        for scenario in execute["scenarios"]:
            scenario.update(
                {
                    "trigger": f"Synthetic {scenario['type']} trigger.",
                    "behavior": f"The runtime handles the synthetic {scenario['type']} path.",
                    "ownership_effect": "Ownership is released or retained according to the linked path.",
                }
            )

    _set_evidence(stages, "OBSERVED")
    _fill_links(stages, [0])
    sanitized_queryplan = {
        "RootOperator": {
            "NodeId": 0,
            "Operators": [
                {
                    "$type": "HashJoin",
                    "NodeId": 1,
                    "Build": {"$type": "IteratorScan", "NodeId": 2},
                }
            ],
        }
    }
    sanitized_plan_bytes = json.dumps(
        sanitized_queryplan,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    final_relop = {
        "Kind": "Filter",
        "LogicalId": "logical-op-filter",
        "Input": {
            "Kind": "Table",
            "LogicalId": "logical-op-source",
        },
    }
    final_relop_bytes = json.dumps(
        final_relop,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    optimizer_items = [
        (stage["id"], item)
        for stage in stages
        if stage["kind"] == "optimizer"
        for substep in stage["substeps"]
        if "runner" in substep and substep["runner"]["type"] == "pass"
        for item in substep["runner"]["pass"]["applicable_passes"]
    ]
    current_snapshot = json.dumps(
        {
            "Kind": "Initial",
            "LogicalId": "logical-op-filter",
            "Revision": 0,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    captured_passes: list[dict[str, Any]] = []
    for sequence, (phase, item) in enumerate(optimizer_items, start=1):
        before = current_snapshot
        if sequence == len(optimizer_items):
            after = final_relop_bytes.decode("utf-8")
        elif item["outcome"] == "SCHEDULED_NO_OP":
            after = before
        else:
            after = json.dumps(
                {
                    "Kind": "Intermediate",
                    "LogicalId": "logical-op-filter",
                    "Revision": sequence,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        before_digest = hashlib.sha256(before.encode("utf-8")).hexdigest()
        after_digest = hashlib.sha256(after.encode("utf-8")).hexdigest()
        item["before"] = before
        item["after"] = after
        item["runtime_evidence"] = {
            "captured": True,
            "trace_pass_id": item["id"],
            "sequence": sequence,
            "before_digest_sha256": before_digest,
            "after_digest_sha256": after_digest,
        }
        captured_passes.append(
            {
                "id": item["id"],
                "sequence": sequence,
                "phase": phase,
                "concrete_pass": item["concrete_pass"],
                "request_scope_digest_sha256": hashlib.sha256(
                    b"synthetic-request-scope"
                ).hexdigest(),
                "changed": before_digest != after_digest,
                "before": before,
                "after": after,
                "before_digest_sha256": before_digest,
                "after_digest_sha256": after_digest,
            }
        )
        current_snapshot = after
    return {
        "schema_version": "2.0",
        "model_state": "COMPLETE",
        "evidence_mode": "EVIDENCE",
        "estimate_reason": "",
        "query": {
            "text": QUERY,
            "cluster_uri": CLUSTER,
            "database": DATABASE,
            "title": "Synthetic Kusto lifecycle walkthrough",
            "slug": query_slug(QUERY, CLUSTER, DATABASE),
        },
        "source": {
            "organization": "msazure",
            "project": "One",
            "repository": "Azure-Kusto-Service",
            "workspace_head": HEAD,
        },
        "optimizer_trace": {
            "provenance": "runtime_per_pass",
            "status": "CAPTURED",
            "description": (
                "Synthetic runtime per-pass snapshots capture each optimizer pass input and output."
            ),
            "source_links": [source_link("Synthetic optimizer trace evidence", 8)],
            "acquisition": {
                "authorization": "explicit_local",
                "workspace_kind": "local_development",
                "attempted": True,
                "method": "existing_non_executing_trace",
                "instrumentation_changed": False,
                "build_attempted": False,
                "build_succeeded": False,
                "restart_attempted": False,
                "restart_succeeded": False,
                "command": f".show queryplan <|\n{QUERY}",
                "non_executing": True,
                "supplied_query_executed": False,
                "request_scope_digest_sha256": hashlib.sha256(
                    b"synthetic-request-scope"
                ).hexdigest(),
                "cleanup_status": "not_required",
                "outcome": "captured",
                "failure": "",
                "raw_digest_sha256": hashlib.sha256(
                    b"synthetic-optimizer-trace"
                ).hexdigest(),
                "driver_receipt": {},
            },
            "captured_passes": captured_passes,
        },
        "plan": {
            "tool": "synthetic non-executing plan fixture",
            "collected_at_utc": "2026-01-01T00:00:00Z",
            "non_executing": True,
            "digest_sha256": hashlib.sha256(b"synthetic-plan").hexdigest(),
            "sanitized_digest_sha256": hashlib.sha256(
                sanitized_plan_bytes
            ).hexdigest(),
            "sanitized_queryplan": sanitized_queryplan,
            "final_relop": {
                "available": True,
                "representation": "json",
                "content": final_relop,
                "digest_sha256": hashlib.sha256(final_relop_bytes).hexdigest(),
                "canonical_digest_sha256": hashlib.sha256(
                    final_relop_bytes
                ).hexdigest(),
                "logical_ids": ["logical-op-filter", "logical-op-source"],
            },
            "operator_count": 2,
            "complete_physical_queryplan": True,
            "provenance": "automatic",
            "recovery": {
                "required": False,
                "prompted": False,
                "command": "",
                "deeplink_status": "not_needed",
                "deeplink_url": "",
                "outcome": "accepted",
                "deficiency": "",
                "automatic_evidence": "",
                "prompted_at_utc": "",
                "prompt_digest_sha256": "",
            },
        },
        "network_beacon": {
            "state": "ENABLED",
            "route": "https://dev.azure.com/msazure/One/_git/Azure-Kusto-Service",
            "purpose": "Outbound source navigation to exact synthetic source evidence.",
        },
        "stages": stages,
    }
