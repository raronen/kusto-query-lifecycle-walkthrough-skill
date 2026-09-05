from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from plan_recovery import PlanRecoveryError, build_queryplan_command


TRACE_KEYS = {"optimizertrace", "optimizer_trace", "passtrace", "pass_trace"}


class OptimizerTraceError(ValueError):
    pass


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def summarize_driver_receipt(
    receipt: Any,
    *,
    source_head: str,
    cluster_uri: str,
    command: str,
    request_scope_digest_sha256: str,
    raw_trace_digest_sha256: str,
    expected_outcome: str,
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise OptimizerTraceError("Local trace driver receipt must be an object.")
    required = {
        "driver",
        "primary_checkout",
        "worktree_path",
        "worktree_root",
        "worktree_isolated",
        "ownership_marker_digest_sha256",
        "ownership_marker_validated",
        "requested_base_ref",
        "resolved_base_ref",
        "worktree_head",
        "worktree_detached",
        "cluster_uri",
        "trace_url",
        "loopback_port",
        "preexisting_listener_pids",
        "preexisting_processes_preserved",
        "build_launcher_pid",
        "build_owned_process_ids",
        "build_job_object_assigned",
        "build_timed_out",
        "build_all_processes_exited",
        "service_launcher_pid",
        "service_pid",
        "service_owned_process_ids",
        "service_job_object_assigned",
        "service_all_processes_exited",
        "request_scope",
        "command",
        "non_executing",
        "supplied_query_executed",
        "primary_head_before",
        "primary_head_after",
        "primary_head_tree",
        "primary_index_tree_before",
        "primary_index_tree_after",
        "primary_status_before_clean",
        "primary_status_after_clean",
        "service_stopped",
        "port_released",
        "worktree_removed",
        "worktree_root_removed",
        "worktree_registration_removed",
        "cleanup_finally",
        "outcome",
        "failure",
        "trace_output_digest_sha256",
        "receipt_digest_sha256",
    }
    if set(receipt) != required:
        raise OptimizerTraceError(
            "Local trace driver receipt has an incomplete or unsupported shape."
        )
    digest_source = dict(receipt)
    receipt_digest = digest_source.pop("receipt_digest_sha256")
    if receipt_digest != _canonical_digest(digest_source):
        raise OptimizerTraceError("Local trace driver receipt digest does not match.")
    if receipt["driver"] != "local_trace_driver.v1":
        raise OptimizerTraceError("Local trace driver identity is invalid.")
    if receipt["resolved_base_ref"] != source_head:
        raise OptimizerTraceError("Resolved base ref does not match source HEAD.")
    base_ref_matches_source = receipt["primary_head_before"] == source_head
    detached_head_matches_source = (
        receipt["worktree_head"] == source_head
        and receipt["worktree_detached"] is True
    )
    if not base_ref_matches_source:
        raise OptimizerTraceError("Primary checkout HEAD does not match source HEAD.")
    parsed_cluster = urlparse(cluster_uri)
    parsed_trace = urlparse(str(receipt["trace_url"]))
    loopback_endpoint_validated = (
        receipt["cluster_uri"] == cluster_uri
        and parsed_cluster.hostname is not None
        and parsed_trace.hostname == parsed_cluster.hostname
        and parsed_trace.port == parsed_cluster.port
        and receipt["loopback_port"] == parsed_cluster.port
    )
    if not loopback_endpoint_validated:
        raise OptimizerTraceError("Receipt loopback endpoint does not match acquisition.")
    scope_digest = hashlib.sha256(str(receipt["request_scope"]).encode("utf-8")).hexdigest()
    if scope_digest != request_scope_digest_sha256:
        raise OptimizerTraceError("Receipt request scope digest does not match trace.")
    if receipt["command"] != command:
        raise OptimizerTraceError("Receipt command does not match trace command.")
    if receipt["non_executing"] is not True or receipt[
        "supplied_query_executed"
    ] is not False:
        raise OptimizerTraceError("Receipt violates the non-execution boundary.")
    primary_checkout_preserved = (
        receipt["primary_head_after"] == source_head
        and receipt["primary_index_tree_before"] == receipt["primary_head_tree"]
        and receipt["primary_index_tree_after"]
        == receipt["primary_index_tree_before"]
        and receipt["primary_status_before_clean"] is True
        and receipt["primary_status_after_clean"] is True
    )
    if not primary_checkout_preserved:
        raise OptimizerTraceError("Primary checkout was not preserved.")
    if receipt["outcome"] != expected_outcome:
        raise OptimizerTraceError("Receipt outcome does not match acquisition outcome.")
    if expected_outcome == "captured":
        if receipt["trace_output_digest_sha256"] != raw_trace_digest_sha256:
            raise OptimizerTraceError("Receipt trace-output digest does not match payload.")
        if not detached_head_matches_source:
            raise OptimizerTraceError(
                "Detached worktree HEAD does not match source HEAD."
            )
    safe_true_fields = (
        "worktree_isolated",
        "ownership_marker_validated",
        "preexisting_processes_preserved",
        "build_all_processes_exited",
        "service_all_processes_exited",
        "service_stopped",
        "port_released",
        "worktree_removed",
        "worktree_root_removed",
        "worktree_registration_removed",
        "cleanup_finally",
    )
    for field in safe_true_fields:
        if receipt[field] is not True:
            raise OptimizerTraceError(f"Receipt safety field {field} is not true.")
    if receipt["preexisting_listener_pids"] != []:
        raise OptimizerTraceError("Receipt shows a preexisting listener.")
    if expected_outcome == "captured" and (
        receipt["build_job_object_assigned"] is not True
        or receipt["service_job_object_assigned"] is not True
        or receipt["build_timed_out"] is not False
    ):
        raise OptimizerTraceError("Captured receipt lacks Job Object containment.")
    return {
        "receipt_digest_sha256": receipt_digest,
        "source_head_digest_sha256": hashlib.sha256(
            source_head.encode("utf-8")
        ).hexdigest(),
        "validated": True,
        "base_ref_matches_source": base_ref_matches_source,
        "detached_head_matches_source": detached_head_matches_source,
        "worktree_isolated": True,
        "ownership_marker_validated": True,
        "loopback_endpoint_validated": True,
        "port_was_free": True,
        "preexisting_processes_preserved": True,
        "build_job_object_assigned": bool(receipt["build_job_object_assigned"]),
        "service_job_object_assigned": bool(receipt["service_job_object_assigned"]),
        "build_timed_out": bool(receipt["build_timed_out"]),
        "all_owned_processes_exited": True,
        "service_stopped": True,
        "port_released": True,
        "worktree_registration_removed": True,
        "worktree_path_removed": True,
        "primary_checkout_preserved": True,
        "cleanup_finally": True,
        "outcome": expected_outcome,
        "trace_output_digest_sha256": receipt["trace_output_digest_sha256"],
    }


def _decode_json(value: Any, location: str) -> Any:
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise OptimizerTraceError(f"{location} must be UTF-8 JSON.") from exc
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise OptimizerTraceError(
            f"{location} is not structurally valid JSON: {exc.msg}."
        ) from exc


def _collect_trace_cells(value: Any) -> list[Any]:
    if isinstance(value, list):
        cells: list[Any] = []
        for item in value:
            cells.extend(_collect_trace_cells(item))
        return cells
    if not isinstance(value, dict):
        return []
    for key, item in value.items():
        if key.lower() in TRACE_KEYS:
            return [item]
    lowered = {key.lower(): item for key, item in value.items()}
    if (
        str(lowered.get("resulttype", "")).lower() in TRACE_KEYS
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
        indexes = [
            index for index, name in enumerate(lowered_names) if name in TRACE_KEYS
        ]
        if indexes:
            index = indexes[0]
            return [
                row[index]
                for row in rows
                if isinstance(row, list) and len(row) > index
            ]
    cells: list[Any] = []
    for key in ("Rows", "rows", "Tables", "tables", "PrimaryResult", "primaryResult"):
        if key in value:
            cells.extend(_collect_trace_cells(value[key]))
    return cells


def _canonical_relop_snapshot(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OptimizerTraceError(
            f"{location} must be nonempty canonical Relop JSON text."
        )
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise OptimizerTraceError(
            f"{location} must be parseable canonical Relop JSON."
        ) from exc
    if not isinstance(decoded, (dict, list)) or not decoded:
        raise OptimizerTraceError(
            f"{location} must decode to a nonempty Relop object or array."
        )
    canonical = json.dumps(
        decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if value != canonical:
        raise OptimizerTraceError(
            f"{location} must already use canonical JSON serialization."
        )
    return canonical


def inspect_optimizer_trace_payload(
    payload: Any,
    query: str,
    *,
    final_relop_canonical_digest_sha256: str,
) -> dict[str, Any]:
    if (
        not isinstance(final_relop_canonical_digest_sha256, str)
        or len(final_relop_canonical_digest_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in final_relop_canonical_digest_sha256
        )
    ):
        raise OptimizerTraceError("Final RelopTree digest must be lowercase SHA-256.")
    if isinstance(payload, bytes):
        raw_bytes = payload
    elif isinstance(payload, str):
        raw_bytes = payload.encode("utf-8")
    else:
        raise OptimizerTraceError(
            "Optimizer trace inspection requires the exact original JSON bytes or text."
        )
    if not raw_bytes.strip():
        raise OptimizerTraceError("The supplied optimizer trace output is empty.")
    decoded = _decode_json(payload, "Optimizer trace payload")
    cells = _collect_trace_cells(decoded)
    if len(cells) != 1:
        if not cells:
            raise OptimizerTraceError("The response has no optimizer trace payload.")
        raise OptimizerTraceError(
            "The response must contain exactly one optimizer trace payload."
        )
    trace = _decode_json(cells[0], "Optimizer trace cell")
    if not isinstance(trace, dict):
        raise OptimizerTraceError("The optimizer trace cell must decode to an object.")
    if trace.get("non_executing") is not True:
        raise OptimizerTraceError("Optimizer trace must attest non_executing=true.")
    if trace.get("supplied_query_executed") is not False:
        raise OptimizerTraceError(
            "Optimizer trace must attest supplied_query_executed=false."
        )
    command = trace.get("command")
    try:
        expected_command = build_queryplan_command(query)
    except PlanRecoveryError as exc:
        raise OptimizerTraceError(str(exc)) from exc
    if command != expected_command:
        raise OptimizerTraceError(
            "Optimizer trace command must be the exact non-executing .show queryplan wrapper."
        )
    request_scope = trace.get("request_scope")
    if not isinstance(request_scope, str) or not request_scope.strip():
        raise OptimizerTraceError("Optimizer trace requires a nonempty request_scope.")
    request_scope_digest = hashlib.sha256(request_scope.encode("utf-8")).hexdigest()
    passes = trace.get("passes")
    if not isinstance(passes, list) or not passes:
        raise OptimizerTraceError("Optimizer trace must contain per-pass snapshots.")

    captured: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous_after_digest = ""
    for index, value in enumerate(passes):
        location = f"OptimizerTrace.passes[{index}]"
        if not isinstance(value, dict):
            raise OptimizerTraceError(f"{location} must be an object.")
        if set(value) != {
            "sequence",
            "phase",
            "canonical_pass_id",
            "concrete_pass",
            "request_scope",
            "executed",
            "changed",
            "before",
            "after",
        }:
            raise OptimizerTraceError(
                f"{location} has an incomplete or unsupported event shape."
            )
        sequence = value["sequence"]
        if isinstance(sequence, bool) or sequence != index + 1:
            raise OptimizerTraceError(
                f"{location}.sequence must be strictly increasing from 1."
            )
        phase = value["phase"]
        if phase not in {"initial-optimize", "partial-queries", "final-optimize"}:
            raise OptimizerTraceError(f"{location}.phase is invalid.")
        pass_id = value["canonical_pass_id"]
        if (
            not isinstance(pass_id, str)
            or not pass_id
            or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for character in pass_id)
        ):
            raise OptimizerTraceError(
                f"{location}.canonical_pass_id must be a lowercase identifier."
            )
        if pass_id in seen:
            raise OptimizerTraceError(f"{location}.canonical_pass_id is duplicated.")
        seen.add(pass_id)
        concrete_pass = value["concrete_pass"]
        if (
            not isinstance(concrete_pass, str)
            or not concrete_pass.strip()
            or not all(
                character.isalnum() or character in "._+`"
                for character in concrete_pass
            )
        ):
            raise OptimizerTraceError(
                f"{location}.concrete_pass must be a concrete qualified pass identity."
            )
        if value["request_scope"] != request_scope:
            raise OptimizerTraceError(
                f"{location}.request_scope does not match the trace request scope."
            )
        if value["executed"] is not True:
            raise OptimizerTraceError(
                f"{location}.executed must be true for a captured pass."
            )
        before = _canonical_relop_snapshot(value["before"], f"{location}.before")
        after = _canonical_relop_snapshot(value["after"], f"{location}.after")
        before_digest = hashlib.sha256(before.encode("utf-8")).hexdigest()
        after_digest = hashlib.sha256(after.encode("utf-8")).hexdigest()
        if value["changed"] is not (before_digest != after_digest):
            raise OptimizerTraceError(
                f"{location}.changed contradicts the canonical structural snapshots."
            )
        if previous_after_digest and before_digest != previous_after_digest:
            raise OptimizerTraceError(
                f"{location} breaks pass-to-pass snapshot continuity."
            )
        previous_after_digest = after_digest
        captured.append(
            {
                "id": pass_id,
                "sequence": sequence,
                "phase": phase,
                "concrete_pass": concrete_pass,
                "request_scope_digest_sha256": request_scope_digest,
                "changed": value["changed"],
                "before": before,
                "after": after,
                "before_digest_sha256": before_digest,
                "after_digest_sha256": after_digest,
            }
        )
    if (
        captured[-1]["after_digest_sha256"]
        != final_relop_canonical_digest_sha256
    ):
        raise OptimizerTraceError(
            "Terminal optimizer snapshot digest does not match the final RelopTree digest."
        )
    return {
        "raw_digest_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "request_scope_digest_sha256": request_scope_digest,
        "command": expected_command,
        "captured_passes": captured,
    }


def build_optimizer_trace_record(
    payload: Any,
    query: str,
    *,
    authorization: str,
    workspace_kind: str = "local_development",
    final_relop_canonical_digest_sha256: str,
    source_head: str,
    cluster_uri: str,
    method: str,
    instrumentation_changed: bool,
    build_attempted: bool,
    build_succeeded: bool,
    restart_attempted: bool,
    restart_succeeded: bool,
    cleanup_status: str,
    driver_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if authorization not in {"explicit_local", "read_only_only"}:
        raise OptimizerTraceError("Trace authorization is invalid.")
    if workspace_kind not in {"local_development", "remote_read_only"}:
        raise OptimizerTraceError("Trace workspace kind is invalid.")
    if authorization == "explicit_local" and workspace_kind != "local_development":
        raise OptimizerTraceError(
            "Explicit local authorization requires a local-development workspace."
        )
    if method not in {
        "existing_non_executing_trace",
        "request_scoped_local_instrumentation",
    }:
        raise OptimizerTraceError("Trace acquisition method is invalid.")
    if method == "request_scoped_local_instrumentation":
        if authorization != "explicit_local":
            raise OptimizerTraceError(
                "Request-scoped instrumentation requires explicit_local authorization."
            )
        if not all(
            (
                instrumentation_changed,
                build_attempted,
                build_succeeded,
                restart_attempted,
                restart_succeeded,
            )
        ):
            raise OptimizerTraceError(
                "Instrumented capture requires successful instrumentation, build, and restart."
            )
        if cleanup_status != "completed":
            raise OptimizerTraceError(
                "Request-scoped instrumentation must be removed after capture."
            )
        if not isinstance(driver_receipt, dict) or not driver_receipt:
            raise OptimizerTraceError(
                "Instrumented capture requires the local trace driver receipt."
            )
    elif instrumentation_changed or cleanup_status != "not_required":
        raise OptimizerTraceError(
            "Existing trace capture must not claim instrumentation changes or cleanup."
        )
    inspected = inspect_optimizer_trace_payload(
        payload,
        query,
        final_relop_canonical_digest_sha256=(
            final_relop_canonical_digest_sha256
        ),
    )
    receipt_summary = (
        summarize_driver_receipt(
            driver_receipt,
            source_head=source_head,
            cluster_uri=cluster_uri,
            command=inspected["command"],
            request_scope_digest_sha256=inspected[
                "request_scope_digest_sha256"
            ],
            raw_trace_digest_sha256=inspected["raw_digest_sha256"],
            expected_outcome="captured",
        )
        if method == "request_scoped_local_instrumentation"
        else {}
    )
    return {
        "provenance": "runtime_per_pass",
        "status": "CAPTURED",
        "description": (
            "Runtime per-pass snapshots were captured by a request-scoped, non-executing "
            "local-development plan request."
        ),
        "source_links": [],
        "acquisition": {
            "authorization": authorization,
            "workspace_kind": workspace_kind,
            "attempted": True,
            "method": method,
            "instrumentation_changed": instrumentation_changed,
            "build_attempted": build_attempted,
            "build_succeeded": build_succeeded,
            "restart_attempted": restart_attempted,
            "restart_succeeded": restart_succeeded,
            "command": inspected["command"],
            "non_executing": True,
            "supplied_query_executed": False,
            "request_scope_digest_sha256": inspected[
                "request_scope_digest_sha256"
            ],
            "cleanup_status": cleanup_status,
            "outcome": "captured",
            "failure": "",
            "raw_digest_sha256": inspected["raw_digest_sha256"],
            "driver_receipt": receipt_summary,
        },
        "captured_passes": inspected["captured_passes"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate request-scoped optimizer pass snapshots without executing a query."
    )
    parser.add_argument("--payload-file", required=True)
    parser.add_argument("--query-file", required=True)
    parser.add_argument("--final-relop-canonical-digest-sha256", required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--cluster-uri", required=True)
    parser.add_argument(
        "--authorization",
        choices=("explicit_local", "read_only_only"),
        required=True,
    )
    parser.add_argument("--driver-receipt-file")
    parser.add_argument(
        "--workspace-kind",
        choices=("local_development", "remote_read_only"),
        required=True,
    )
    parser.add_argument(
        "--method",
        choices=(
            "existing_non_executing_trace",
            "request_scoped_local_instrumentation",
        ),
        required=True,
    )
    parser.add_argument("--instrumentation-changed", action="store_true")
    parser.add_argument("--build-attempted", action="store_true")
    parser.add_argument("--build-succeeded", action="store_true")
    parser.add_argument("--restart-attempted", action="store_true")
    parser.add_argument("--restart-succeeded", action="store_true")
    parser.add_argument(
        "--cleanup-status",
        choices=("not_required", "completed"),
        required=True,
    )
    args = parser.parse_args()
    try:
        payload = Path(args.payload_file).read_bytes()
        query = Path(args.query_file).read_text(encoding="utf-8")
        driver_receipt = (
            json.loads(Path(args.driver_receipt_file).read_text(encoding="utf-8"))
            if args.driver_receipt_file
            else None
        )
        record = build_optimizer_trace_record(
            payload,
            query,
            authorization=args.authorization,
            workspace_kind=args.workspace_kind,
            final_relop_canonical_digest_sha256=(
                args.final_relop_canonical_digest_sha256
            ),
            source_head=args.source_head,
            cluster_uri=args.cluster_uri,
            method=args.method,
            instrumentation_changed=args.instrumentation_changed,
            build_attempted=args.build_attempted,
            build_succeeded=args.build_succeeded,
            restart_attempted=args.restart_attempted,
            restart_succeeded=args.restart_succeeded,
            cleanup_status=args.cleanup_status,
            driver_receipt=driver_receipt,
        )
    except (OSError, OptimizerTraceError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
