from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse


STAGES = (
    ("syntax", "Syntax", "standard"),
    ("semantic", "Semantic", "standard"),
    ("relop", "Relop", "standard"),
    ("preparation", "Preparation", "standard"),
    ("initial-optimize", "Initial optimize", "optimizer"),
    ("partial-queries", "Partial queries", "optimizer"),
    ("final-optimize", "Final optimize", "optimizer"),
    ("physical-plan", "Physical plan", "physical"),
    ("serialize-native-boundary", "Serialize/native boundary", "serialization"),
    ("execute", "Execute", "execute"),
)

EVIDENCE_KINDS = {
    "OBSERVED",
    "TRANSFORMED",
    "SCHEDULED_NO_OP",
    "NO_OP",
    "ESTIMATED",
}


class ModelError(ValueError):
    pass


def query_slug(query: str, cluster_uri: str, database: str) -> str:
    words = re.findall(r"[a-z0-9]+", query.lower())[:4]
    hint = "-".join(words) or "walkthrough"
    digest_input = json.dumps(
        [query, cluster_uri.rstrip("/").lower(), database],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:12]
    return f"kusto-query-{hint[:48].strip('-')}-{digest}"


def load_model(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelError(f"Unable to read model '{path}': {exc}") from exc
    if not isinstance(value, dict):
        raise ModelError("The model root must be a JSON object.")
    return value


def _require_object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelError(f"{location} must be an object.")
    return value


def _require_list(value: Any, location: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list):
        raise ModelError(f"{location} must be an array.")
    if nonempty and not value:
        raise ModelError(f"{location} must not be empty.")
    return value


def _text(value: Any, location: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ModelError(f"{location} must be a string.")
    if not allow_empty and not value.strip():
        raise ModelError(f"{location} must not be empty.")
    return value


def _require_keys(value: dict[str, Any], keys: Iterable[str], location: str) -> None:
    missing = [key for key in keys if key not in value]
    if missing:
        raise ModelError(f"{location} is missing required fields: {', '.join(missing)}.")


def _reject_extra(value: dict[str, Any], allowed: Iterable[str], location: str) -> None:
    extras = sorted(set(value) - set(allowed))
    if extras:
        raise ModelError(f"{location} contains unsupported fields: {', '.join(extras)}.")


def is_authorized_source_remote(remote: str, project: str) -> bool:
    normalized = remote.strip().removesuffix(".git")
    scp_match = re.fullmatch(
        r"git@ssh\.dev\.azure\.com:v3/msazure/([^/]+)/Azure-Kusto-Service",
        normalized,
        flags=re.IGNORECASE,
    )
    if scp_match:
        return scp_match.group(1).lower() == project.lower()

    parsed = urlparse(normalized)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if parsed.scheme.lower() == "https" and parsed.hostname == "dev.azure.com":
        return [segment.lower() for segment in segments] == [
            "msazure",
            project.lower(),
            "_git",
            "azure-kusto-service",
        ]
    if parsed.scheme.lower() == "ssh" and parsed.hostname == "ssh.dev.azure.com":
        return [segment.lower() for segment in segments] == [
            "v3",
            "msazure",
            project.lower(),
            "azure-kusto-service",
        ]
    return False


def verify_source_workspace(workspace: Path, model: dict[str, Any]) -> None:
    resolved = workspace.expanduser().resolve()
    expected_head = model["source"]["workspace_head"]
    try:
        head = subprocess.run(
            ["git", "-C", str(resolved), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip().lower()
        remote = subprocess.run(
            ["git", "-C", str(resolved), "remote", "get-url", "origin"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ModelError(f"Unable to verify source workspace '{resolved}': {exc}") from exc
    if not is_authorized_source_remote(remote, model["source"]["project"]):
        raise ModelError("Source workspace origin is not msazure/Azure-Kusto-Service.")
    if head != expected_head:
        raise ModelError(
            "Model source commit is stale: source.workspace_head does not match "
            "the authorized workspace HEAD."
        )

    line_counts: dict[str, int] = {}

    def inspect(value: Any, location: str) -> None:
        if isinstance(value, dict):
            if {"url", "path", "start_line", "end_line", "commit"} <= set(value):
                source_path = PurePosixPath(value["path"].lstrip("/"))
                if ".." in source_path.parts:
                    raise ModelError(f"{location}.path escapes the source workspace.")
                git_path = source_path.as_posix()
                if git_path not in line_counts:
                    try:
                        blob = subprocess.run(
                            ["git", "-C", str(resolved), "show", f"{expected_head}:{git_path}"],
                            check=True,
                            capture_output=True,
                        ).stdout
                    except (OSError, subprocess.CalledProcessError) as exc:
                        raise ModelError(
                            f"{location}.path does not exist at source workspace HEAD."
                        ) from exc
                    line_counts[git_path] = len(blob.splitlines())
                if value["end_line"] > line_counts[git_path]:
                    raise ModelError(
                        f"{location} line range exceeds the source file at workspace HEAD."
                    )
            for key, child in value.items():
                inspect(child, f"{location}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                inspect(child, f"{location}[{index}]")

    inspect(model["stages"], "model.stages")


def validate_source_link(link_value: Any, head: str, project: str, location: str) -> None:
    link = _require_object(link_value, location)
    required = ("label", "url", "path", "start_line", "end_line", "commit")
    _require_keys(link, required, location)
    _reject_extra(link, required, location)
    _text(link["label"], f"{location}.label")
    source_path = _text(link["path"], f"{location}.path")
    if not source_path.startswith("/"):
        raise ModelError(f"{location}.path must start with '/'.")
    if link["commit"] != head:
        raise ModelError(f"{location}.commit must match source.workspace_head.")
    start = link["start_line"]
    end = link["end_line"]
    if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
        raise ModelError(f"{location} must contain a valid inclusive line range.")

    raw_url = _text(link["url"], f"{location}.url")
    parsed = urlparse(raw_url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "dev.azure.com":
        raise ModelError(f"{location}.url must be an absolute Azure DevOps HTTPS URL.")
    segments = [segment for segment in parsed.path.split("/") if segment]
    if [segment.lower() for segment in segments] != [
        "msazure",
        project.lower(),
        "_git",
        "azure-kusto-service",
    ]:
        raise ModelError(
            f"{location}.url must use the canonical "
            f"msazure/{project}/Azure-Kusto-Service route."
        )
    query = parse_qs(parsed.query)
    if query.get("version") != [f"GC{head}"]:
        raise ModelError(f"{location}.url must be pinned to source.workspace_head.")
    if query.get("path") != [source_path]:
        raise ModelError(f"{location}.url path must match the link path.")
    if query.get("line") != [str(start)] or query.get("lineEnd") != [str(end)]:
        raise ModelError(f"{location}.url line parameters must match the link range.")


def _validate_links(
    value: Any, head: str, project: str, location: str, *, nonempty: bool
) -> list[Any]:
    links = _require_list(value, location, nonempty=nonempty)
    for index, link in enumerate(links):
        validate_source_link(link, head, project, f"{location}[{index}]")
    return links


def _validate_action(
    action_value: Any, head: str, project: str, location: str, *, optimizer: bool
) -> None:
    action = _require_object(action_value, location)
    required = (
        "id",
        "title",
        "description",
        "evidence_kind",
        "before",
        "after",
        "source_links",
    )
    _require_keys(action, required, location)
    allowed = required + ("traversal", "predicate", "applicability", "optimization")
    _reject_extra(action, allowed, location)
    for key in ("id", "title", "description"):
        _text(action[key], f"{location}.{key}")
    before = _text(action["before"], f"{location}.before", allow_empty=True)
    after = _text(action["after"], f"{location}.after", allow_empty=True)
    kind = action["evidence_kind"]
    if kind not in EVIDENCE_KINDS:
        raise ModelError(f"{location}.evidence_kind is invalid or still pending.")
    _validate_links(
        action["source_links"], head, project, f"{location}.source_links", nonempty=True
    )

    if optimizer:
        for key in ("predicate", "applicability", "optimization"):
            _text(action.get(key), f"{location}.{key}")
        traversal = _require_list(action.get("traversal"), f"{location}.traversal", nonempty=True)
        for index, node in enumerate(traversal):
            _text(node, f"{location}.traversal[{index}]")
        if kind == "TRANSFORMED" and before == after:
            raise ModelError(f"{location} claims TRANSFORMED but before and after are identical.")
        if kind == "SCHEDULED_NO_OP" and before != after:
            raise ModelError(f"{location} claims SCHEDULED_NO_OP but before and after differ.")
        if kind not in {"TRANSFORMED", "SCHEDULED_NO_OP", "ESTIMATED"}:
            raise ModelError(
                f"{location} optimizer evidence must be TRANSFORMED, "
                "SCHEDULED_NO_OP, or ESTIMATED."
            )


def _validate_operator(node_value: Any, head: str, project: str, location: str) -> int:
    node = _require_object(node_value, location)
    required = ("operator_id", "name", "details", "source_links", "children")
    _require_keys(node, required, location)
    _reject_extra(node, required, location)
    for key in ("operator_id", "name", "details"):
        _text(node[key], f"{location}.{key}")
    _validate_links(
        node["source_links"], head, project, f"{location}.source_links", nonempty=True
    )
    children = _require_list(node["children"], f"{location}.children")
    return 1 + sum(
        _validate_operator(child, head, project, f"{location}.children[{index}]")
        for index, child in enumerate(children)
    )


def _validate_frame(frame_value: Any, head: str, project: str, location: str) -> None:
    frame = _require_object(frame_value, location)
    _require_keys(frame, ("language", "frame", "source_links"), location)
    _reject_extra(frame, ("language", "frame", "source_links"), location)
    if frame["language"] not in {"Managed", "C++", "Rust"}:
        raise ModelError(f"{location}.language is invalid.")
    _text(frame["frame"], f"{location}.frame")
    _validate_links(
        frame["source_links"], head, project, f"{location}.source_links", nonempty=True
    )


def _validate_heap_zone(zone_value: Any, head: str, project: str, location: str) -> None:
    zone = _require_object(zone_value, location)
    required = ("zone", "language", "state", "details", "evidence_basis", "source_links")
    _require_keys(zone, required, location)
    _reject_extra(zone, required, location)
    for key in ("zone", "details", "evidence_basis"):
        _text(zone[key], f"{location}.{key}")
    if zone["language"] not in {"Managed", "C++", "Rust"}:
        raise ModelError(f"{location}.language is invalid.")
    if zone["state"] not in {"borrowed", "owned", "released"}:
        raise ModelError(f"{location}.state is invalid.")
    _validate_links(
        zone["source_links"], head, project, f"{location}.source_links", nonempty=True
    )


def _validate_component(component_value: Any, head: str, project: str, location: str) -> None:
    component = _require_object(component_value, location)
    required = (
        "name",
        "evidence_ref",
        "role",
        "pull_direction",
        "data_direction",
        "ownership_now",
        "next_breakpoint",
        "failure",
        "cancellation",
        "lifetime",
        "source_links",
    )
    _require_keys(component, required, location)
    _reject_extra(component, required, location)
    for key in required[:-1]:
        _text(component[key], f"{location}.{key}")
    _validate_links(
        component["source_links"], head, project, f"{location}.source_links", nonempty=True
    )


def _validate_timeline(event_value: Any, head: str, project: str, location: str) -> None:
    event = _require_object(event_value, location)
    required = (
        "id",
        "title",
        "user_event",
        "description",
        "call_stack",
        "heap_zones",
        "components",
        "source_links",
    )
    _require_keys(event, required, location)
    _reject_extra(event, required, location)
    for key in ("id", "title", "user_event", "description"):
        _text(event[key], f"{location}.{key}")
    for index, frame in enumerate(
        _require_list(event["call_stack"], f"{location}.call_stack", nonempty=True)
    ):
        _validate_frame(frame, head, project, f"{location}.call_stack[{index}]")
    for index, zone in enumerate(_require_list(event["heap_zones"], f"{location}.heap_zones")):
        _validate_heap_zone(zone, head, project, f"{location}.heap_zones[{index}]")
    for index, component in enumerate(
        _require_list(event["components"], f"{location}.components", nonempty=True)
    ):
        _validate_component(component, head, project, f"{location}.components[{index}]")
    _validate_links(
        event["source_links"], head, project, f"{location}.source_links", nonempty=True
    )


def validate_complete_model(model: dict[str, Any]) -> None:
    required = (
        "schema_version",
        "model_state",
        "evidence_mode",
        "estimate_reason",
        "query",
        "source",
        "plan",
        "stages",
    )
    _require_keys(model, required, "model")
    _reject_extra(model, required, "model")
    if model["schema_version"] != "1.0":
        raise ModelError("model.schema_version must be '1.0'.")
    if model["model_state"] != "COMPLETE":
        raise ModelError("model.model_state must be COMPLETE before rendering.")
    mode = model["evidence_mode"]
    if mode not in {"EVIDENCE", "ESTIMATED"}:
        raise ModelError("model.evidence_mode must be EVIDENCE or ESTIMATED.")
    estimate_reason = _text(
        model["estimate_reason"], "model.estimate_reason", allow_empty=(mode == "EVIDENCE")
    )
    if mode == "EVIDENCE" and estimate_reason:
        raise ModelError("model.estimate_reason must be empty in EVIDENCE mode.")

    query = _require_object(model["query"], "model.query")
    _require_keys(query, ("text", "cluster_uri", "database", "title", "slug"), "model.query")
    _reject_extra(query, ("text", "cluster_uri", "database", "title", "slug"), "model.query")
    for key in ("text", "cluster_uri", "database", "title", "slug"):
        _text(query[key], f"model.query.{key}")
    parsed_cluster = urlparse(query["cluster_uri"])
    if parsed_cluster.scheme != "https" or not parsed_cluster.netloc:
        raise ModelError("model.query.cluster_uri must be an absolute HTTPS URI.")
    expected_slug = query_slug(query["text"], query["cluster_uri"], query["database"])
    if query["slug"] != expected_slug:
        raise ModelError("model.query.slug is not the stable query-derived slug.")

    source = _require_object(model["source"], "model.source")
    _require_keys(
        source, ("organization", "project", "repository", "workspace_head"), "model.source"
    )
    _reject_extra(
        source, ("organization", "project", "repository", "workspace_head"), "model.source"
    )
    if source["organization"] != "msazure" or source["repository"] != "Azure-Kusto-Service":
        raise ModelError("model.source must target msazure/Azure-Kusto-Service.")
    project = _text(source["project"], "model.source.project")
    head = _text(source["workspace_head"], "model.source.workspace_head")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ModelError("model.source.workspace_head must be a lowercase 40-character commit.")

    plan = _require_object(model["plan"], "model.plan")
    _require_keys(
        plan,
        ("tool", "collected_at_utc", "non_executing", "digest_sha256", "operator_count"),
        "model.plan",
    )
    _reject_extra(
        plan,
        ("tool", "collected_at_utc", "non_executing", "digest_sha256", "operator_count"),
        "model.plan",
    )
    _text(plan["tool"], "model.plan.tool")
    _text(plan["collected_at_utc"], "model.plan.collected_at_utc")
    if plan["non_executing"] is not True:
        raise ModelError("model.plan.non_executing must be exactly true.")
    digest = _text(plan["digest_sha256"], "model.plan.digest_sha256", allow_empty=True)
    if mode == "EVIDENCE" and not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ModelError("EVIDENCE mode requires a SHA-256 plan digest.")
    if not isinstance(plan["operator_count"], int) or plan["operator_count"] < 1:
        raise ModelError("model.plan.operator_count must be a positive integer.")

    stages = _require_list(model["stages"], "model.stages")
    if len(stages) != len(STAGES):
        raise ModelError("model.stages must contain exactly ten stages.")

    execution_refs: set[str] = set()

    for index, ((expected_id, expected_title, expected_kind), stage_value) in enumerate(
        zip(STAGES, stages, strict=True)
    ):
        location = f"model.stages[{index}]"
        stage = _require_object(stage_value, location)
        required_stage = (
            "id",
            "order",
            "title",
            "kind",
            "summary",
            "evidence_kind",
            "no_op_explanation",
            "source_links",
            "actions",
        )
        _require_keys(stage, required_stage, location)
        allowed_stage = required_stage + ("physical_plan", "boundaries", "timeline")
        _reject_extra(stage, allowed_stage, location)
        if (
            stage["id"] != expected_id
            or stage["title"] != expected_title
            or stage["kind"] != expected_kind
            or stage["order"] != index + 1
        ):
            raise ModelError(f"{location} does not match the required lifecycle order.")
        _text(stage["summary"], f"{location}.summary")
        evidence_kind = stage["evidence_kind"]
        if evidence_kind not in EVIDENCE_KINDS:
            raise ModelError(f"{location}.evidence_kind is invalid or still pending.")
        if mode == "ESTIMATED" and evidence_kind not in {"ESTIMATED", "NO_OP"}:
            raise ModelError(f"{location} must be visibly ESTIMATED or NO_OP in ESTIMATED mode.")
        if mode == "EVIDENCE" and evidence_kind == "ESTIMATED":
            raise ModelError(f"{location} cannot use ESTIMATED evidence in EVIDENCE mode.")
        no_op = _text(
            stage["no_op_explanation"],
            f"{location}.no_op_explanation",
            allow_empty=evidence_kind not in {"NO_OP", "SCHEDULED_NO_OP"},
        )
        if evidence_kind not in {"NO_OP", "SCHEDULED_NO_OP"} and no_op:
            raise ModelError(f"{location}.no_op_explanation is only valid for no-op evidence.")
        _validate_links(
            stage["source_links"], head, project, f"{location}.source_links", nonempty=True
        )
        actions = _require_list(stage["actions"], f"{location}.actions")
        for action_index, action in enumerate(actions):
            _validate_action(
                action,
                head,
                project,
                f"{location}.actions[{action_index}]",
                optimizer=expected_kind == "optimizer",
            )
            if mode == "EVIDENCE" and action["evidence_kind"] == "ESTIMATED":
                raise ModelError(
                    f"{location}.actions[{action_index}] cannot be ESTIMATED in EVIDENCE mode."
                )
            if mode == "ESTIMATED" and action["evidence_kind"] != "ESTIMATED":
                raise ModelError(
                    f"{location}.actions[{action_index}] must be ESTIMATED in ESTIMATED mode."
                )

        if expected_kind in {"standard", "optimizer"} and evidence_kind not in {
            "NO_OP",
            "SCHEDULED_NO_OP",
        } and not actions:
            raise ModelError(f"{location} requires at least one query-specific action.")
        if expected_kind == "optimizer" and actions:
            action_kinds = {action["evidence_kind"] for action in actions}
            derived_kind = (
                "ESTIMATED"
                if action_kinds == {"ESTIMATED"}
                else "TRANSFORMED"
                if "TRANSFORMED" in action_kinds
                else "SCHEDULED_NO_OP"
            )
            if evidence_kind != derived_kind:
                raise ModelError(
                    f"{location}.evidence_kind contradicts its optimizer action outcomes."
                )
        if expected_kind == "physical":
            physical = _require_object(stage.get("physical_plan"), f"{location}.physical_plan")
            _require_keys(physical, ("complete", "operator_count", "root"), f"{location}.physical_plan")
            _reject_extra(
                physical, ("complete", "operator_count", "root"), f"{location}.physical_plan"
            )
            count = _validate_operator(
                physical["root"], head, project, f"{location}.physical_plan.root"
            )
            def collect_operator_ids(node: dict[str, Any]) -> None:
                execution_refs.add(node["operator_id"])
                for child in node["children"]:
                    collect_operator_ids(child)

            collect_operator_ids(physical["root"])
            if physical["operator_count"] != count or plan["operator_count"] != count:
                raise ModelError(f"{location}.physical_plan operator counts do not match its tree.")
            if mode == "EVIDENCE" and physical["complete"] is not True:
                raise ModelError("EVIDENCE mode requires a complete physical plan.")
            if mode == "ESTIMATED" and physical["complete"] is not False:
                raise ModelError("ESTIMATED mode must not claim that the physical plan is complete.")
        elif "physical_plan" in stage:
            raise ModelError(f"{location} must not contain physical_plan.")

        if expected_kind == "serialization":
            boundaries = _require_list(
                stage.get("boundaries"),
                f"{location}.boundaries",
                nonempty=evidence_kind != "NO_OP",
            )
            if evidence_kind == "NO_OP" and boundaries:
                raise ModelError(f"{location} is NO_OP but contains serialization boundaries.")
            for boundary_index, boundary in enumerate(boundaries):
                _validate_action(
                    boundary,
                    head,
                    project,
                    f"{location}.boundaries[{boundary_index}]",
                    optimizer=False,
                )
                execution_refs.add(boundary["id"])
                if mode == "EVIDENCE" and boundary["evidence_kind"] == "ESTIMATED":
                    raise ModelError(
                        f"{location}.boundaries[{boundary_index}] cannot be ESTIMATED "
                        "in EVIDENCE mode."
                    )
                if mode == "ESTIMATED" and boundary["evidence_kind"] != "ESTIMATED":
                    raise ModelError(
                        f"{location}.boundaries[{boundary_index}] must be ESTIMATED "
                        "in ESTIMATED mode."
                    )
        elif "boundaries" in stage:
            raise ModelError(f"{location} must not contain boundaries.")

        if expected_kind == "execute":
            timeline = _require_list(stage.get("timeline"), f"{location}.timeline", nonempty=True)
            for event_index, event in enumerate(timeline):
                _validate_timeline(event, head, project, f"{location}.timeline[{event_index}]")
                for component_index, component in enumerate(event["components"]):
                    if component["evidence_ref"] not in execution_refs:
                        raise ModelError(
                            f"{location}.timeline[{event_index}].components[{component_index}] "
                            "references an operator or boundary absent from this walkthrough."
                        )
        elif "timeline" in stage:
            raise ModelError(f"{location} must not contain timeline.")


def safe_json_for_html(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return raw.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
