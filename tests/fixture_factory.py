from __future__ import annotations

import hashlib
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
                value[key] = [source_link("Synthetic source evidence", 10 + counter[0] % 150)]
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
        substep = stage["substeps"][0]
        substep["behavior"] = f"Query-specific {stage['title']} behavior."
        substep["change_badge"] = outcome
        substep["summary"] = f"Synthetic walkthrough for {stage['title']}."
        substep["what_happens"] = f"The {stage['title']} owner processes the synthetic shape."
        substep["why"] = "This state is required before the next lifecycle handoff."
        substep["debug"] = "Break at the linked synthetic method and inspect the current node."
        substep["next"] = "Advance to the next evidenced lifecycle owner."
        substep["method_path"] = [f"Synthetic.{stage_id}.Enter", f"Synthetic.{stage_id}.Leave"]
        substep["artifact"]["title"] = f"{stage['title']} synthetic artifact"
        substep["artifact"]["before"] = f"{stage_id}: before"
        substep["artifact"]["after"] = (
            substep["artifact"]["before"]
            if outcome == "SCHEDULED_NO_OP"
            else f"{stage_id}: after"
        )
        runner = substep["runner"]
        runner["title"] = f"Run the {stage['title'].lower()} {runner['type']} yourself"
        runner["no_op"] = {
            "enabled": outcome == "SCHEDULED_NO_OP",
            "gates": ["Synthetic partition gate is absent."] if outcome == "SCHEDULED_NO_OP" else [],
            "reasons": ["The tree remains unchanged."] if outcome == "SCHEDULED_NO_OP" else [],
        }
        runner["experiments"][0]["title"] = f"Compare {stage['title']} evidence gates"
        runner["experiments"][0]["options"] = [
            {"id": f"{stage_id}-baseline", "label": "Baseline evidence"},
            {"id": f"{stage_id}-alternate", "label": "Alternate gate"},
        ]
        runner["experiments"][0]["results"] = [
            {
                "option_id": f"{stage_id}-baseline",
                "result": f"Baseline {stage['title']} state is visible.",
            },
            {
                "option_id": f"{stage_id}-alternate",
                "result": f"Alternate {stage['title']} gate changes the visible explanation.",
            },
        ]
        for action in runner["actions"]:
            action["evidence_kind"] = outcome
            action["what"] = f"Apply the synthetic {stage['title']} action."
            action["why"] = "The linked evidence establishes this action."
            action["result"] = "The synthetic state advances visibly."
            action["stack_effect"] = "Compiler-only until execution; no concrete stack address claimed."
            action["heap_effect"] = "Lifetime ownership is described conceptually without byte-size claims."
            action["before"] = f"{stage_id}: runner before"
            action["after"] = (
                action["before"] if outcome == "SCHEDULED_NO_OP" else f"{stage_id}: runner after"
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
            item = runner["pass"]["applicable_passes"][0]
            item["title"] = f"Applicable {stage['title']} synthetic pass"
            item["outcome"] = outcome
            item["before"] = f"{stage_id}: cumulative before"
            item["after"] = item["before"] if outcome == "SCHEDULED_NO_OP" else f"{stage_id}: cumulative after"
            runner["pass"]["cumulative_before"] = item["before"]
            runner["pass"]["cumulative_after"] = item["after"]

    physical = stages[7]["substeps"][0]["runner"]["physical"]
    child = _operator("op-source", "node-source", "Synthetic source", [])
    root = _operator("op-filter", "node-filter", "Synthetic filter", [child])
    physical["full_plan"] = {"complete": True, "operator_count": 2, "roots": [root]}
    physical["logical_to_physical"] = [
        {
            "logical_id": "logical-op-filter",
            "physical_operator_ids": ["op-filter"],
            "reason": "The synthetic logical filter maps to the physical filter.",
            "source_links": [],
        },
        {
            "logical_id": "logical-op-source",
            "physical_operator_ids": ["op-source"],
            "reason": "The synthetic logical source maps to the physical source.",
            "source_links": [],
        },
    ]

    execute = stages[9]["substeps"][0]["runner"]["execute"]
    execute["components"][0]["evidence_ref"] = "op-filter"
    execute["components"][0]["state"] = "active"
    execute["components"][0]["ownership"] = "The synthetic coordinator owns the current batch."
    execute["components"][0]["breakpoint"] = "Before the synthetic predicate callback."
    execute["action_timeline"][0].update(
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
    for stage in stages:
        if stage["id"] == "partial-queries":
            stage["evidence_kind"] = "SCHEDULED_NO_OP"
            stage["substeps"][0]["change_badge"] = "SCHEDULED_NO_OP"
            stage["substeps"][0]["runner"]["actions"][0]["evidence_kind"] = "SCHEDULED_NO_OP"
    _fill_links(stages, [0])
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
        "plan": {
            "tool": "synthetic non-executing plan fixture",
            "collected_at_utc": "2026-01-01T00:00:00Z",
            "non_executing": True,
            "digest_sha256": hashlib.sha256(b"synthetic-plan").hexdigest(),
            "operator_count": 2,
        },
        "network_beacon": {
            "state": "ENABLED",
            "route": "https://dev.azure.com/msazure/One/_git/Azure-Kusto-Service",
            "purpose": "Outbound source navigation to exact synthetic source evidence.",
        },
        "stages": stages,
    }
