from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SERIALIZED_CHILD_KEYS = {
    "build",
    "probe",
    "left",
    "right",
    "source",
    "from",
    "to",
    "step",
    "segments",
    "data",
    "subquery",
    "operands",
    "operators",
    "extensions",
}
LOGICAL_MARKERS = {"logicalplan", "relop", "reloptree", "replotree"}
PHYSICAL_TYPE_RE = re.compile(
    r"^Kusto\.DataNode\.DataEngineQueryPlan\.([A-Za-z_][A-Za-z0-9_]*)(?:,\s*DataNode)?$"
)


class PlanRecoveryError(ValueError):
    pass


def build_queryplan_command(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise PlanRecoveryError("The supplied query must be non-empty.")
    return f".show queryplan <|\n{query}"


def is_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value
    ):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo == timezone.utc


def _decode_json(value: Any, location: str) -> Any:
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PlanRecoveryError(f"{location} must be UTF-8 JSON.") from exc
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise PlanRecoveryError(f"{location} is not structurally valid JSON: {exc.msg}.") from exc


def _collect_queryplan_cells(value: Any) -> list[Any]:
    if isinstance(value, list):
        cells: list[Any] = []
        for item in value:
            cells.extend(_collect_queryplan_cells(item))
        return cells
    if not isinstance(value, dict):
        return []
    direct = next((item for key, item in value.items() if key.lower() == "queryplan"), None)
    if direct is not None:
        return [direct]
    lowered = {key.lower(): item for key, item in value.items()}
    if (
        str(lowered.get("resulttype", "")).lower() == "queryplan"
        and "content" in lowered
    ):
        return [lowered["content"]]

    columns = value.get("Columns", value.get("columns"))
    rows = value.get("Rows", value.get("rows"))
    if isinstance(columns, list) and isinstance(rows, list):
        names = [
            column.get("ColumnName", column.get("columnName", column.get("Name", "")))
            if isinstance(column, dict)
            else str(column)
            for column in columns
        ]
        lowered_names = [str(name).lower() for name in names]
        if "queryplan" in lowered_names:
            index = lowered_names.index("queryplan")
            return [
                row[index]
                for row in rows
                if isinstance(row, list) and len(row) > index
            ]
        if "resulttype" in lowered_names and "content" in lowered_names:
            result_index = lowered_names.index("resulttype")
            content_index = lowered_names.index("content")
            return [
                row[content_index]
                for row in rows
                if isinstance(row, list)
                and len(row) > max(result_index, content_index)
                and str(row[result_index]).lower() == "queryplan"
            ]

    cells = []
    for key in ("Rows", "rows", "Tables", "tables", "PrimaryResult", "primaryResult"):
        if key in value:
            cells.extend(_collect_queryplan_cells(value[key]))
    return cells


def _queryplan_cell(payload: Any) -> Any:
    payload = _decode_json(payload, "Payload")
    if not isinstance(payload, (dict, list)):
        raise PlanRecoveryError("The response must be a JSON object or a row array.")
    cells = _collect_queryplan_cells(payload)
    if len(cells) == 1:
        return _decode_json(cells[0], "QueryPlan cell")
    if len(cells) > 1:
        raise PlanRecoveryError("The response must contain exactly one QueryPlan cell.")
    if isinstance(payload, dict) and "RootOperator" in payload:
        return payload
    if isinstance(payload, dict) and any(
        key.lower() in LOGICAL_MARKERS | {"queryhints", "statistics"} for key in payload
    ):
        raise PlanRecoveryError(
            "The payload contains logical Relop/hints/statistics but no complete physical QueryPlan."
        )
    raise PlanRecoveryError("The response has no QueryPlan cell or physical plan root.")


def _validate_flags(value: Any, location: str = "QueryPlan") -> None:
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_flags(item, f"{location}[{index}]")
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        lowered = key.lower()
        if lowered in {"iscomplete", "complete", "istruncated", "truncated", "hasmore"}:
            if not isinstance(item, bool):
                raise PlanRecoveryError(f"{location}.{key} must be boolean.")
            if lowered in {"iscomplete", "complete"} and not item:
                raise PlanRecoveryError(f"{location}.{key} marks the plan incomplete.")
            if lowered in {"istruncated", "truncated", "hasmore"} and item:
                raise PlanRecoveryError(f"{location}.{key} marks the plan truncated.")
        _validate_flags(item, f"{location}.{key}")


def _serialized_descendants(value: Any, location: str) -> tuple[int, bool]:
    if isinstance(value, list):
        total = 0
        found = False
        for index, item in enumerate(value):
            child_count, child_found = _serialized_descendants(
                item, f"{location}[{index}]"
            )
            if not child_found:
                raise PlanRecoveryError(
                    f"{location}[{index}] is not a complete physical operator."
                )
            total += child_count
            found = found or child_found
        return total, found
    if not isinstance(value, dict):
        return 0, False

    node_type = value.get("$type")
    is_node = isinstance(node_type, str) and bool(node_type.strip())
    if "$type" in value and not is_node:
        raise PlanRecoveryError(f"{location} has an invalid physical $type.")
    if is_node:
        type_match = PHYSICAL_TYPE_RE.fullmatch(node_type)
        if not type_match:
            raise PlanRecoveryError(
                f"{location}.$type is not a source-backed physical QueryPlan type."
            )
        if "logical" in type_match.group(1).lower() or "relop" in type_match.group(1).lower():
            raise PlanRecoveryError(f"{location} is logical rather than physical.")
        node_id = value.get("NodeId")
        if isinstance(node_id, bool) or not isinstance(node_id, int) or node_id < 0:
            raise PlanRecoveryError(f"{location}.NodeId must be a non-negative integer.")

    total = 1 if is_node else 0
    found = is_node
    for key, item in value.items():
        if key.lower() not in SERIALIZED_CHILD_KEYS:
            if _contains_physical_type(item):
                raise PlanRecoveryError(
                    f"{location}.{key} contains a physical operator in an unknown child lane."
                )
            continue
        child_count, child_found = _serialized_descendants(
            item, f"{location}.{key}"
        )
        if not isinstance(item, (dict, list)) or not item or not child_found:
            raise PlanRecoveryError(
                f"{location}.{key} must contain a complete physical operator payload."
            )
        total += child_count
        found = found or child_found
    return total, found


def _contains_physical_type(value: Any) -> bool:
    if isinstance(value, list):
        return any(_contains_physical_type(item) for item in value)
    if not isinstance(value, dict):
        return False
    return "$type" in value or any(_contains_physical_type(item) for item in value.values())


def _validate_serialized_plan(plan: dict[str, Any]) -> int:
    root = plan.get("RootOperator")
    if not isinstance(root, dict):
        raise PlanRecoveryError("QueryPlan is missing its physical RootOperator object.")
    node_id = root.get("NodeId")
    if isinstance(node_id, bool) or not isinstance(node_id, int) or node_id < 0:
        raise PlanRecoveryError("QueryPlan.RootOperator.NodeId must be a non-negative integer.")
    operators = root.get("Operators")
    if not isinstance(operators, list) or not operators:
        raise PlanRecoveryError(
            "QueryPlan.RootOperator.Operators must contain physical operators."
        )
    operator_count, found = _serialized_descendants(
        operators, "QueryPlan.RootOperator.Operators"
    )
    if not found:
        raise PlanRecoveryError("QueryPlan has no serialized physical operators.")
    return operator_count


def _validate_physical_plan(plan: Any) -> int:
    if not isinstance(plan, dict):
        raise PlanRecoveryError("QueryPlan cell must decode to a JSON object.")
    _validate_flags(plan)
    if any(key.lower() in LOGICAL_MARKERS for key in plan):
        raise PlanRecoveryError(
            "The QueryPlan cell contains a logical Relop tree, not a complete physical QueryPlan."
        )
    if "RootOperator" in plan:
        return _validate_serialized_plan(plan)
    raise PlanRecoveryError("QueryPlan has no recognized physical RootOperator tree.")


def _structural_projection(value: Any) -> Any:
    if isinstance(value, list):
        projected = [
            item
            for child in value
            if (item := _structural_projection(child)) is not None
        ]
        return projected or None
    if not isinstance(value, dict):
        return None

    projected: dict[str, Any] = {}
    if "$type" in value:
        projected["$type"] = PHYSICAL_TYPE_RE.fullmatch(value["$type"]).group(1)
    if "NodeId" in value:
        projected["NodeId"] = value["NodeId"]
    for key, child in value.items():
        if key.lower() not in SERIALIZED_CHILD_KEYS:
            continue
        child_projection = _structural_projection(child)
        if child_projection is not None:
            projected[key] = child_projection
    return projected or None


def _sanitize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    root = plan["RootOperator"]
    return {
        "RootOperator": {
            "NodeId": root["NodeId"],
            "Operators": _structural_projection(root["Operators"]),
        }
    }


def inspect_queryplan_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, bytes):
        raw_bytes = payload
    elif isinstance(payload, str):
        raw_bytes = payload.encode("utf-8")
    else:
        raise PlanRecoveryError(
            "QueryPlan inspection requires the exact original JSON bytes or text."
        )
    if not raw_bytes.strip():
        raise PlanRecoveryError("The supplied QueryPlan output is empty.")
    decoded_payload = _decode_json(payload, "Payload")
    _validate_flags(decoded_payload, "Response")
    cell = _queryplan_cell(decoded_payload)
    operator_count = _validate_physical_plan(cell)
    sanitized = _sanitize_plan(cell)
    sanitized_bytes = json.dumps(
        sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "complete": True,
        "operator_count": operator_count,
        "digest_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "sanitized_digest_sha256": hashlib.sha256(sanitized_bytes).hexdigest(),
        "sanitized_queryplan": sanitized,
    }


def pending_recovery(query: str, *, automatic_deficiency: str) -> dict[str, Any]:
    return {
        "complete_physical_queryplan": False,
        "provenance": "pending",
        "recovery": {
            "required": True,
            "prompted": False,
            "command": build_queryplan_command(query),
            "deeplink_status": "not_attempted",
            "deeplink_url": "",
            "outcome": "pending",
            "deficiency": automatic_deficiency,
            "automatic_evidence": automatic_deficiency,
            "prompted_at_utc": "",
            "prompt_digest_sha256": "",
        },
    }


def build_recovery_prompt(
    *,
    automatic_evidence: str,
    command: str,
    deeplink_url: str = "",
) -> str:
    link = (
        f"Open the non-executing command in Kusto/Fabric Explorer: {deeplink_url}\n\n"
        if deeplink_url
        else "A Kusto/Fabric Explorer deeplink could not be generated; use the command below.\n\n"
    )
    return (
        f"Automatic evidence found: {automatic_evidence}\n"
        "Missing artifact: a complete physical QueryPlan operator tree.\n\n"
        f"{link}"
        "Exact non-executing command:\n"
        "```kusto\n"
        f"{command}\n"
        "```\n\n"
        "Can you paste the QueryPlan result cell/JSON here, or, if it is too large, attach it "
        "or save it locally and provide the file path?"
    )


def record_recovery_prompt(
    query: str,
    *,
    automatic_evidence: str,
    automatic_deficiency: str,
    deeplink_status: str,
    prompted_at_utc: str,
    deeplink_url: str = "",
) -> dict[str, Any]:
    if not automatic_evidence.strip() or not automatic_deficiency.strip():
        raise PlanRecoveryError(
            "Recovery prompting requires automatic evidence and its exact deficiency."
        )
    if deeplink_status not in {"generated", "failed", "unavailable"}:
        raise PlanRecoveryError("Recovery must record the deeplink generation result.")
    if deeplink_status == "generated":
        parsed = urlparse(deeplink_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise PlanRecoveryError("Generated recovery deeplink must be absolute HTTPS.")
    elif deeplink_url:
        raise PlanRecoveryError("A failed or unavailable deeplink must not claim a URL.")
    if not is_utc_timestamp(prompted_at_utc):
        raise PlanRecoveryError("Prompt timestamp must be UTC RFC 3339.")
    command = build_queryplan_command(query)
    prompt = build_recovery_prompt(
        automatic_evidence=automatic_evidence,
        command=command,
        deeplink_url=deeplink_url,
    )
    return {
        "required": True,
        "prompted": True,
        "command": command,
        "deeplink_status": deeplink_status,
        "deeplink_url": deeplink_url,
        "outcome": "pending",
        "deficiency": automatic_deficiency,
        "automatic_evidence": automatic_evidence,
        "prompted_at_utc": prompted_at_utc,
        "prompt_digest_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    }


def _require_prompt_record(recovery: dict[str, Any]) -> dict[str, Any]:
    required = {
        "required",
        "prompted",
        "command",
        "deeplink_status",
        "deeplink_url",
        "outcome",
        "deficiency",
        "automatic_evidence",
        "prompted_at_utc",
        "prompt_digest_sha256",
    }
    if not isinstance(recovery, dict) or set(recovery) != required:
        raise PlanRecoveryError("A complete recorded recovery prompt is required.")
    if recovery["required"] is not True or recovery["prompted"] is not True:
        raise PlanRecoveryError("ESTIMATED or user-supplied evidence requires a recorded prompt.")
    if recovery["outcome"] != "pending":
        raise PlanRecoveryError("The recovery prompt record has already been resolved.")
    expected = record_recovery_prompt(
        recovery["command"].removeprefix(".show queryplan <|\n"),
        automatic_evidence=recovery["automatic_evidence"],
        automatic_deficiency=recovery["deficiency"],
        deeplink_status=recovery["deeplink_status"],
        prompted_at_utc=recovery["prompted_at_utc"],
        deeplink_url=recovery["deeplink_url"],
    )
    if expected != recovery:
        raise PlanRecoveryError("Recovery prompt record is inconsistent or has been altered.")
    return dict(recovery)


def accepted_recovery(
    payload: Any,
    *,
    provenance: str,
    tool: str,
    collected_at_utc: str,
    prompt_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if provenance not in {"automatic", "user_supplied"}:
        raise PlanRecoveryError("Accepted evidence provenance must be automatic or user_supplied.")
    if not is_utc_timestamp(collected_at_utc):
        raise PlanRecoveryError("Collection timestamp must be UTC RFC 3339.")
    result = inspect_queryplan_payload(payload)
    if result["complete"] is not True:
        raise PlanRecoveryError("Accepted evidence did not pass complete QueryPlan inspection.")
    prompted = provenance == "user_supplied"
    if prompted:
        recovery = _require_prompt_record(prompt_record or {})
        recovery["outcome"] = "accepted"
    else:
        if prompt_record is not None:
            raise PlanRecoveryError("Automatic complete evidence must skip user recovery.")
        recovery = {
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
        }
    return {
        "tool": tool,
        "collected_at_utc": collected_at_utc,
        "non_executing": True,
        "digest_sha256": result["digest_sha256"],
        "sanitized_digest_sha256": result["sanitized_digest_sha256"],
        "sanitized_queryplan": result["sanitized_queryplan"],
        "operator_count": result["operator_count"],
        "complete_physical_queryplan": True,
        "provenance": provenance,
        "recovery": recovery,
    }


def estimated_recovery(
    prompt_record: dict[str, Any],
    *,
    outcome: str,
) -> dict[str, Any]:
    if outcome not in {"user_declined", "user_could_not_provide", "user_chose_after_rejection"}:
        raise PlanRecoveryError("ESTIMATED fallback requires an explicit user recovery outcome.")
    recovery = _require_prompt_record(prompt_record)
    recovery["outcome"] = outcome
    return {
        "sanitized_digest_sha256": "",
        "sanitized_queryplan": {},
        "complete_physical_queryplan": False,
        "provenance": "estimated_after_recovery",
        "recovery": recovery,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect physical QueryPlan recovery evidence.")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--query-file")
    inputs.add_argument("--payload-file")
    parser.add_argument("--record-prompt", action="store_true")
    parser.add_argument("--automatic-evidence")
    parser.add_argument("--automatic-deficiency")
    parser.add_argument("--deeplink-status")
    parser.add_argument("--deeplink-url", default="")
    parser.add_argument("--prompted-at-utc")
    args = parser.parse_args()
    try:
        if args.query_file:
            query = Path(args.query_file).read_bytes().decode("utf-8")
            if args.record_prompt:
                missing = [
                    name
                    for name in (
                        "automatic_evidence",
                        "automatic_deficiency",
                        "deeplink_status",
                        "prompted_at_utc",
                    )
                    if not getattr(args, name)
                ]
                if missing:
                    parser.error(
                        "--record-prompt requires "
                        + ", ".join("--" + name.replace("_", "-") for name in missing)
                    )
                recovery = record_recovery_prompt(
                    query,
                    automatic_evidence=args.automatic_evidence,
                    automatic_deficiency=args.automatic_deficiency,
                    deeplink_status=args.deeplink_status,
                    deeplink_url=args.deeplink_url,
                    prompted_at_utc=args.prompted_at_utc,
                )
                print(
                    json.dumps(
                        {
                            "prompt": build_recovery_prompt(
                                automatic_evidence=recovery["automatic_evidence"],
                                command=recovery["command"],
                                deeplink_url=recovery["deeplink_url"],
                            ),
                            "recovery": recovery,
                        },
                        ensure_ascii=False,
                    )
                )
            else:
                print(json.dumps({"command": build_queryplan_command(query)}, ensure_ascii=False))
            return 0
        if args.payload_file:
            if args.record_prompt:
                parser.error("--record-prompt requires --query-file")
            payload = Path(args.payload_file).read_bytes()
            print(json.dumps(inspect_queryplan_payload(payload), ensure_ascii=False))
            return 0
    except (OSError, PlanRecoveryError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
