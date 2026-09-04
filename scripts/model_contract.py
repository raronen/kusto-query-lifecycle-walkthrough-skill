from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, urlparse

from canonical_spec import BOUNDARY_LANES_BY_KEY, CANONICAL_SUBSTEPS
from plan_recovery import (
    SERIALIZED_CHILD_KEYS,
    build_recovery_prompt,
    is_utc_timestamp,
)


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

RUNNER_TYPES = {
    stage_id: tuple(substep.runner_type for substep in CANONICAL_SUBSTEPS[index])
    for index, (stage_id, _title, _kind) in enumerate(STAGES)
}

EVIDENCE_KINDS = {
    "OBSERVED",
    "TRANSFORMED",
    "SCHEDULED_NO_OP",
    "NO_OP",
    "ESTIMATED",
}
NO_OP_KINDS = {"NO_OP", "SCHEDULED_NO_OP"}
LANGUAGES = {"Managed", "C++", "Rust"}
HEAP_STATES = {"live", "mutated", "released"}
COMPONENT_STATES = {"active", "waiting", "not-created"}


class ModelError(ValueError):
    pass


def validate_cluster_uri(value: str, location: str = "cluster URI") -> None:
    if not isinstance(value, str) or not value:
        raise ModelError(f"{location} must be a non-empty string.")
    if any(character.isspace() for character in value):
        raise ModelError(f"{location} must not contain whitespace.")
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise ModelError(f"{location} is not a valid absolute URI: {exc}") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.netloc or hostname is None:
        raise ModelError(
            f"{location} must be absolute HTTPS, or HTTP only for a loopback host."
        )
    if parsed.username is not None or parsed.password is not None:
        raise ModelError(f"{location} must not contain userinfo.")
    if parsed.netloc.endswith(":"):
        raise ModelError(f"{location} contains an empty port.")
    if scheme == "https":
        return
    normalized_host = hostname.lower()
    if normalized_host == "localhost":
        return
    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError as exc:
        raise ModelError(f"{location} permits HTTP only for a loopback host.") from exc
    if isinstance(address, ipaddress.IPv4Address) and address.is_loopback:
        return
    if isinstance(address, ipaddress.IPv6Address) and normalized_host == "::1":
        return
    raise ModelError(f"{location} permits HTTP only for localhost, 127.0.0.0/8, or ::1.")


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


def _object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelError(f"{location} must be an object.")
    return value


def _list(value: Any, location: str, *, nonempty: bool = False) -> list[Any]:
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


def _identifier(value: Any, location: str) -> str:
    identifier = _text(value, location)
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", identifier):
        raise ModelError(f"{location} must be a lowercase identifier.")
    return identifier


def _boolean(value: Any, location: str) -> bool:
    if not isinstance(value, bool):
        raise ModelError(f"{location} must be a boolean.")
    return value


def _integer(value: Any, location: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ModelError(f"{location} must be an integer of at least {minimum}.")
    return value


def _shape(
    value: Any,
    required: Iterable[str],
    location: str,
    optional: Iterable[str] = (),
) -> dict[str, Any]:
    result = _object(value, location)
    required_set = set(required)
    missing = sorted(required_set - set(result))
    if missing:
        raise ModelError(f"{location} is missing required fields: {', '.join(missing)}.")
    extras = sorted(set(result) - required_set - set(optional))
    if extras:
        raise ModelError(f"{location} contains unsupported fields: {', '.join(extras)}.")
    return result


def _unique(
    values: list[Any],
    key: Callable[[Any], Any],
    location: str,
    description: str,
) -> None:
    seen: set[Any] = set()
    for index, value in enumerate(values):
        item = key(value)
        if item in seen:
            raise ModelError(f"{location}[{index}] repeats {description} '{item}'.")
        seen.add(item)


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
    expected = ["msazure", project.lower(), "_git", "azure-kusto-service"]
    if parsed.scheme.lower() == "https" and parsed.hostname == "dev.azure.com":
        return [segment.lower() for segment in segments] == expected
    if (
        parsed.scheme.lower() == "https"
        and parsed.netloc.lower() == "msazure.visualstudio.com"
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    ):
        return [segment.lower() for segment in segments] == [
            "defaultcollection",
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
                if ".." in source_path.parts or source_path.is_absolute():
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
    required = ("label", "url", "path", "start_line", "end_line", "commit")
    link = _shape(link_value, required, location)
    _text(link["label"], f"{location}.label")
    source_path = _text(link["path"], f"{location}.path")
    source_parts = PurePosixPath(source_path)
    if not source_path.startswith("/") or ".." in source_parts.parts:
        raise ModelError(f"{location}.path must be an absolute repository path without '..'.")
    if link["commit"] != head:
        raise ModelError(f"{location}.commit must match source.workspace_head.")
    start = _integer(link["start_line"], f"{location}.start_line", minimum=1)
    end = _integer(link["end_line"], f"{location}.end_line", minimum=1)
    if end < start:
        raise ModelError(f"{location} must contain a valid inclusive line range.")

    raw_url = _text(link["url"], f"{location}.url")
    parsed = urlparse(raw_url)
    canonical_path = f"/msazure/{project}/_git/Azure-Kusto-Service"
    if (
        parsed.scheme != "https"
        or parsed.netloc != "dev.azure.com"
        or parsed.path != canonical_path
        or parsed.fragment
    ):
        raise ModelError(
            f"{location}.url must use the exact canonical Azure DevOps HTTPS route "
            f"https://dev.azure.com{canonical_path}."
        )
    query = parse_qs(parsed.query, keep_blank_values=True)
    if query.get("version") != [f"GC{head}"]:
        raise ModelError(f"{location}.url must be pinned to source.workspace_head.")
    if query.get("path") != [source_path]:
        raise ModelError(f"{location}.url path must match the link path.")
    if query.get("line") != [str(start)] or query.get("lineEnd") != [str(end + 1)]:
        raise ModelError(f"{location}.url line parameters must match the link range.")


def _links(
    value: Any,
    head: str,
    project: str,
    location: str,
    *,
    nonempty: bool = True,
) -> list[Any]:
    links = _list(value, location, nonempty=nonempty)
    for index, link in enumerate(links):
        validate_source_link(link, head, project, f"{location}[{index}]")
    return links


def _evidence_kind(value: Any, location: str, mode: str) -> str:
    if value not in EVIDENCE_KINDS:
        raise ModelError(f"{location} is invalid or still pending.")
    if mode == "EVIDENCE" and value == "ESTIMATED":
        raise ModelError(f"{location} cannot be ESTIMATED in EVIDENCE mode.")
    if mode == "ESTIMATED" and value not in {"ESTIMATED", "NO_OP"}:
        raise ModelError(f"{location} must be visibly ESTIMATED or NO_OP in ESTIMATED mode.")
    return value


def _validate_overview(value: Any, location: str) -> None:
    keys = ("input", "output", "owner", "not_responsible", "handoff")
    overview = _shape(value, keys, location)
    for key in keys:
        _text(overview[key], f"{location}.{key}")


def _validate_table(
    value: Any, head: str, project: str, location: str
) -> None:
    table = _shape(value, ("id", "title", "columns", "rows", "source_links"), location)
    _identifier(table["id"], f"{location}.id")
    _text(table["title"], f"{location}.title")
    columns = _list(table["columns"], f"{location}.columns", nonempty=True)
    for index, column in enumerate(columns):
        _text(column, f"{location}.columns[{index}]")
    if len(set(columns)) != len(columns):
        raise ModelError(f"{location}.columns must be unique.")
    rows = _list(table["rows"], f"{location}.rows", nonempty=True)
    for index, row in enumerate(rows):
        cells = _list(row, f"{location}.rows[{index}]")
        if len(cells) != len(columns):
            raise ModelError(f"{location}.rows[{index}] must match the column count.")
        for cell_index, cell in enumerate(cells):
            _text(cell, f"{location}.rows[{index}][{cell_index}]")
    _links(table["source_links"], head, project, f"{location}.source_links")


def _validate_additional_context(
    value: Any, head: str, project: str, location: str
) -> None:
    context = _shape(value, ("summary", "tables"), location)
    _text(context["summary"], f"{location}.summary")
    tables = _list(context["tables"], f"{location}.tables", nonempty=True)
    for index, table in enumerate(tables):
        _validate_table(table, head, project, f"{location}.tables[{index}]")
    _unique(tables, lambda item: item["id"], f"{location}.tables", "table id")


def _validate_traversal(
    value: Any, head: str, project: str, location: str
) -> None:
    traversal = _shape(value, ("nodes", "snapshots"), location)
    nodes = _list(traversal["nodes"], f"{location}.nodes", nonempty=True)
    node_ids: set[str] = set()
    for index, node_value in enumerate(nodes):
        node_location = f"{location}.nodes[{index}]"
        node = _shape(
            node_value, ("id", "label", "state", "source_links"), node_location
        )
        node_id = _identifier(node["id"], f"{node_location}.id")
        if node_id in node_ids:
            raise ModelError(f"{node_location}.id must be unique within the traversal.")
        node_ids.add(node_id)
        _text(node["label"], f"{node_location}.label")
        _text(node["state"], f"{node_location}.state")
        _links(node["source_links"], head, project, f"{node_location}.source_links")
    snapshots = _list(
        traversal["snapshots"], f"{location}.snapshots", nonempty=True
    )
    if len(snapshots) < 2:
        raise ModelError(f"{location}.snapshots must contain at least two snapshots.")
    signatures: set[tuple[str, str, str, str]] = set()
    snapshot_ids: set[str] = set()
    for index, snapshot_value in enumerate(snapshots):
        snapshot_location = f"{location}.snapshots[{index}]"
        snapshot = _shape(
            snapshot_value,
            (
                "id",
                "current",
                "movement",
                "return_value",
                "next",
            ),
            snapshot_location,
        )
        snapshot_id = _identifier(snapshot["id"], f"{snapshot_location}.id")
        if snapshot_id in snapshot_ids:
            raise ModelError(f"{snapshot_location}.id must be unique.")
        snapshot_ids.add(snapshot_id)
        current = _identifier(
            snapshot["current"], f"{snapshot_location}.current"
        )
        if current not in node_ids:
            raise ModelError(
                f"{snapshot_location}.current must reference a declared traversal node."
            )
        for key in ("movement", "return_value", "next"):
            _text(snapshot[key], f"{snapshot_location}.{key}")
        signature = tuple(
            snapshot[key] for key in ("current", "movement", "return_value", "next")
        )
        if signature in signatures:
            raise ModelError(f"{snapshot_location} duplicates another traversal snapshot.")
        signatures.add(signature)


def _validate_artifact(
    value: Any,
    head: str,
    project: str,
    location: str,
    *,
    no_op: bool,
) -> None:
    artifact = _shape(
        value,
        ("title", "collapsed_by_default", "before", "after", "operators"),
        location,
    )
    _text(artifact["title"], f"{location}.title")
    _boolean(
        artifact["collapsed_by_default"], f"{location}.collapsed_by_default"
    )
    before = _text(artifact["before"], f"{location}.before")
    after = _text(artifact["after"], f"{location}.after")
    operators = _list(
        artifact["operators"], f"{location}.operators", nonempty=True
    )
    for index, operator_value in enumerate(operators):
        operator_location = f"{location}.operators[{index}]"
        operator = _shape(
            operator_value,
            ("id", "label", "state", "source_links"),
            operator_location,
        )
        _identifier(operator["id"], f"{operator_location}.id")
        _text(operator["label"], f"{operator_location}.label")
        _text(operator["state"], f"{operator_location}.state")
        _links(
            operator["source_links"],
            head,
            project,
            f"{operator_location}.source_links",
        )
    _unique(operators, lambda item: item["id"], f"{location}.operators", "operator id")
    if no_op and before != after:
        raise ModelError(f"{location} is a no-op artifact but before and after differ.")
    if not no_op and before == after:
        raise ModelError(f"{location} must show distinct before and after representations.")


def _validate_runner_action(
    value: Any,
    head: str,
    project: str,
    mode: str,
    location: str,
    *,
    require_pass_fields: bool = False,
    require_boundary_lane: bool = False,
) -> None:
    action = _shape(
        value,
        (
            "id",
            "title",
            "evidence_kind",
            "what",
            "why",
            "result",
            "stack_effect",
            "heap_effect",
            "before",
            "after",
            "source_links",
        ),
        location,
        optional=("traversal", "predicate", "applicability", "optimization", "lane"),
    )
    _identifier(action["id"], f"{location}.id")
    for key in ("title", "what", "why", "result", "stack_effect", "heap_effect"):
        _text(action[key], f"{location}.{key}")
    _evidence_kind(action["evidence_kind"], f"{location}.evidence_kind", mode)
    _text(action["before"], f"{location}.before", allow_empty=True)
    _text(action["after"], f"{location}.after", allow_empty=True)
    pass_fields = ("traversal", "predicate", "applicability", "optimization")
    if require_pass_fields:
        for key in pass_fields:
            _text(action.get(key), f"{location}.{key}")
    elif any(key in action for key in pass_fields):
        raise ModelError(f"{location} contains pass-only fields outside a pass runner.")
    if require_boundary_lane:
        if action.get("lane") not in {"C#", "Interop", "C++"}:
            raise ModelError(f"{location}.lane must be C#, Interop, or C++.")
    elif "lane" in action:
        raise ModelError(f"{location}.lane is valid only for a boundary runner.")
    _links(action["source_links"], head, project, f"{location}.source_links")


def _validate_runner_snapshot(
    value: Any, head: str, project: str, location: str
) -> tuple[str, str, str, str]:
    snapshot = _shape(
        value,
        (
            "id",
            "label",
            "progress",
            "current",
            "movement",
            "return_value",
            "next",
            "visible_state",
            "source_links",
        ),
        location,
    )
    _identifier(snapshot["id"], f"{location}.id")
    for key in (
        "label",
        "current",
        "movement",
        "return_value",
        "next",
        "visible_state",
    ):
        _text(snapshot[key], f"{location}.{key}")
    progress = _integer(snapshot["progress"], f"{location}.progress")
    if progress > 100:
        raise ModelError(f"{location}.progress must not exceed 100.")
    _links(snapshot["source_links"], head, project, f"{location}.source_links")
    return tuple(
        snapshot[key] for key in ("current", "movement", "return_value", "next")
    )


def _validate_experiment(
    value: Any, head: str, project: str, location: str
) -> None:
    experiment = _shape(
        value,
        ("id", "title", "control", "options", "results", "source_links"),
        location,
    )
    _identifier(experiment["id"], f"{location}.id")
    _text(experiment["title"], f"{location}.title")
    if experiment["control"] not in {"select", "toggle", "failure", "inspect", "scenario"}:
        raise ModelError(f"{location}.control is not a supported interactive control.")
    options = _list(experiment["options"], f"{location}.options", nonempty=True)
    if len(options) < 2:
        raise ModelError(f"{location}.options must contain at least two interactive choices.")
    for index, option_value in enumerate(options):
        option_location = f"{location}.options[{index}]"
        option = _shape(option_value, ("id", "label"), option_location)
        _identifier(option["id"], f"{option_location}.id")
        _text(option["label"], f"{option_location}.label")
    _unique(options, lambda item: item["id"], f"{location}.options", "option id")
    option_ids = {item["id"] for item in options}
    results = _list(experiment["results"], f"{location}.results", nonempty=True)
    for index, result_value in enumerate(results):
        result_location = f"{location}.results[{index}]"
        result = _shape(result_value, ("option_id", "result"), result_location)
        _identifier(result["option_id"], f"{result_location}.option_id")
        if result["option_id"] not in option_ids:
            raise ModelError(
                f"{result_location}.option_id must reference an experiment option."
            )
        _text(result["result"], f"{result_location}.result")
    _unique(
        results,
        lambda item: item["option_id"],
        f"{location}.results",
        "option result",
    )
    if {item["option_id"] for item in results} != option_ids:
        raise ModelError(f"{location}.results must cover every experiment option.")
    _links(experiment["source_links"], head, project, f"{location}.source_links")


def _validate_mapping(
    value: Any,
    head: str,
    project: str,
    location: str,
) -> None:
    entries = _list(value, location)
    for index, entry_value in enumerate(entries):
        entry_location = f"{location}[{index}]"
        entry = _shape(
            entry_value, ("from", "to", "reason", "source_links"), entry_location
        )
        for key in ("from", "to", "reason"):
            _text(entry[key], f"{entry_location}.{key}")
        _links(entry["source_links"], head, project, f"{entry_location}.source_links")


def _validate_compiler(
    value: Any,
    stage_id: str,
    mode: str,
    head: str,
    project: str,
    location: str,
) -> None:
    compiler = _shape(
        value,
        ("mode", "before_actions", "after_actions", "mapping"),
        location,
    )
    expected_mode = {
        "syntax": "syntax",
        "semantic": "semantic",
        "relop": "relop",
    }[stage_id]
    if compiler["mode"] != expected_mode:
        raise ModelError(f"{location}.mode must be '{expected_mode}' for {stage_id}.")
    for key in ("before_actions", "after_actions"):
        actions = _list(compiler[key], f"{location}.{key}", nonempty=True)
        for index, action in enumerate(actions):
            _validate_runner_action(
                action, head, project, mode, f"{location}.{key}[{index}]"
            )
        _unique(actions, lambda item: item["id"], f"{location}.{key}", "action id")
    _validate_mapping(
        compiler["mapping"], head, project, f"{location}.mapping"
    )
    if stage_id in {"semantic", "relop"} and not compiler["mapping"]:
        raise ModelError(f"{location}.mapping is required for {stage_id}.")


def _validate_pass(
    value: Any,
    badge: str,
    mode: str,
    head: str,
    project: str,
    location: str,
) -> None:
    pass_data = _shape(
        value,
        (
            "applicable_passes",
            "cumulative_before",
            "cumulative_after",
            "additional_context_tables",
        ),
        location,
    )
    passes = _list(
        pass_data["applicable_passes"],
        f"{location}.applicable_passes",
        nonempty=badge != "NO_OP",
    )
    if badge == "NO_OP" and passes:
        raise ModelError(f"{location} must not list passes for an inapplicable NO_OP.")
    for index, pass_value in enumerate(passes):
        pass_location = f"{location}.applicable_passes[{index}]"
        item = _shape(
            pass_value,
            (
                "id",
                "title",
                "traversal",
                "predicate",
                "applicability",
                "optimization",
                "before",
                "after",
                "outcome",
                "source_links",
            ),
            pass_location,
        )
        _identifier(item["id"], f"{pass_location}.id")
        for key in (
            "title",
            "traversal",
            "predicate",
            "applicability",
            "optimization",
            "before",
            "after",
        ):
            _text(item[key], f"{pass_location}.{key}")
        if item["outcome"] not in {
            "OBSERVED",
            "TRANSFORMED",
            "SCHEDULED_NO_OP",
            "ESTIMATED",
        }:
            raise ModelError(f"{pass_location}.outcome is invalid for an applicable pass.")
        if mode == "EVIDENCE" and item["outcome"] == "ESTIMATED":
            raise ModelError(
                f"{pass_location}.outcome cannot be ESTIMATED in EVIDENCE mode."
            )
        if item["outcome"] == "TRANSFORMED" and item["before"] == item["after"]:
            raise ModelError(
                f"{pass_location} claims TRANSFORMED but before and after are identical."
            )
        if item["outcome"] == "SCHEDULED_NO_OP" and item["before"] != item["after"]:
            raise ModelError(
                f"{pass_location} claims SCHEDULED_NO_OP but before and after differ."
            )
        _links(item["source_links"], head, project, f"{pass_location}.source_links")
    _unique(passes, lambda item: item["id"], f"{location}.applicable_passes", "pass id")
    outcomes = {item["outcome"] for item in passes}
    if badge == "TRANSFORMED" and "TRANSFORMED" not in outcomes:
        raise ModelError(f"{location} does not contain a transformed pass.")
    if badge == "SCHEDULED_NO_OP" and outcomes != {"SCHEDULED_NO_OP"}:
        raise ModelError(f"{location} scheduled-no-op outcome is inconsistent.")
    if badge == "ESTIMATED" and outcomes != {"ESTIMATED"}:
        raise ModelError(f"{location} estimated outcome is inconsistent.")
    if badge == "OBSERVED" and outcomes != {"OBSERVED"}:
        raise ModelError(f"{location} observed outcome is inconsistent.")
    before = _text(pass_data["cumulative_before"], f"{location}.cumulative_before")
    after = _text(pass_data["cumulative_after"], f"{location}.cumulative_after")
    if badge == "TRANSFORMED" and before == after:
        raise ModelError(f"{location} transformed cumulative artifacts are identical.")
    if badge in NO_OP_KINDS and before != after:
        raise ModelError(f"{location} no-op cumulative artifacts differ.")
    tables = _list(
        pass_data["additional_context_tables"],
        f"{location}.additional_context_tables",
        nonempty=True,
    )
    for index, table in enumerate(tables):
        _validate_table(
            table, head, project, f"{location}.additional_context_tables[{index}]"
        )


def _validate_schema_fields(value: Any, location: str) -> None:
    fields = _list(value, location, nonempty=True)
    for index, field_value in enumerate(fields):
        field_location = f"{location}[{index}]"
        field = _shape(
            field_value, ("name", "type", "nullable", "description"), field_location
        )
        for key in ("name", "type", "description"):
            _text(field[key], f"{field_location}.{key}")
        _boolean(field["nullable"], f"{field_location}.nullable")
    _unique(fields, lambda item: item["name"], location, "field name")


def _validate_remote_metadata(
    value: Any, head: str, project: str, location: str
) -> None:
    metadata = _shape(
        value,
        ("applicable", "cluster", "database", "endpoint", "reason", "source_links"),
        location,
    )
    applicable = _boolean(metadata["applicable"], f"{location}.applicable")
    for key in ("cluster", "database", "endpoint"):
        _text(metadata[key], f"{location}.{key}", allow_empty=not applicable)
    reason = _text(metadata["reason"], f"{location}.reason", allow_empty=applicable)
    if applicable and reason:
        raise ModelError(f"{location}.reason must be empty when remote metadata applies.")
    _links(metadata["source_links"], head, project, f"{location}.source_links")


def _validate_operator(
    value: Any,
    head: str,
    project: str,
    location: str,
    ids: set[str],
    node_ids: set[str],
) -> int:
    operator = _shape(
        value,
        (
            "operator_id",
            "node_id",
            "name",
            "details",
            "logical_operator_ids",
            "input_schema",
            "output_schema",
            "key_indexes",
            "execution_eligibility",
            "rust_eligibility",
            "target_scope",
            "remote_metadata",
            "source_links",
            "children",
        ),
        location,
    )
    operator_id = _identifier(operator["operator_id"], f"{location}.operator_id")
    node_id = _identifier(operator["node_id"], f"{location}.node_id")
    if operator_id in ids:
        raise ModelError(f"{location}.operator_id must be globally unique.")
    if node_id in node_ids:
        raise ModelError(f"{location}.node_id must be globally unique.")
    ids.add(operator_id)
    node_ids.add(node_id)
    for key in ("name", "details", "execution_eligibility", "rust_eligibility", "target_scope"):
        _text(operator[key], f"{location}.{key}")
    logical_ids = _list(
        operator["logical_operator_ids"],
        f"{location}.logical_operator_ids",
        nonempty=True,
    )
    for index, logical_id in enumerate(logical_ids):
        _identifier(logical_id, f"{location}.logical_operator_ids[{index}]")
    _validate_schema_fields(operator["input_schema"], f"{location}.input_schema")
    _validate_schema_fields(operator["output_schema"], f"{location}.output_schema")
    indexes = _list(operator["key_indexes"], f"{location}.key_indexes")
    for index, key_index in enumerate(indexes):
        _integer(key_index, f"{location}.key_indexes[{index}]")
    if len(set(indexes)) != len(indexes):
        raise ModelError(f"{location}.key_indexes must be unique.")
    _validate_remote_metadata(
        operator["remote_metadata"], head, project, f"{location}.remote_metadata"
    )
    _links(operator["source_links"], head, project, f"{location}.source_links")
    children = _list(operator["children"], f"{location}.children")
    return 1 + sum(
        _validate_operator(
            child,
            head,
            project,
            f"{location}.children[{index}]",
            ids,
            node_ids,
        )
        for index, child in enumerate(children)
    )


def _topology_sort_key(node: tuple[Any, ...]) -> tuple[str, str]:
    return node[0], node[1]


def _sanitized_nodes(value: Any, location: str, node_ids: set[str]) -> list[tuple[Any, ...]]:
    if isinstance(value, list):
        if not value:
            raise ModelError(f"{location} must not be empty.")
        result: list[tuple[Any, ...]] = []
        for index, item in enumerate(value):
            children = _sanitized_nodes(item, f"{location}[{index}]", node_ids)
            if not children:
                raise ModelError(f"{location}[{index}] has no sanitized physical operator.")
            result.extend(children)
        return result
    node = _object(value, location)
    allowed = {"$type", "NodeId"} | {
        key for key in node if key.lower() in SERIALIZED_CHILD_KEYS
    }
    extras = sorted(set(node) - allowed)
    if extras:
        raise ModelError(
            f"{location} contains unsafe or unsupported sanitized fields: {', '.join(extras)}."
        )
    has_type = "$type" in node
    if has_type != ("NodeId" in node):
        raise ModelError(f"{location} must pair $type with NodeId.")
    descendants: list[tuple[Any, ...]] = []
    for key, child in node.items():
        if key.lower() in SERIALIZED_CHILD_KEYS:
            descendants.extend(_sanitized_nodes(child, f"{location}.{key}", node_ids))
    if not has_type:
        if not descendants:
            raise ModelError(f"{location} has no sanitized physical operator.")
        return descendants
    node_type = _text(node["$type"], f"{location}.$type")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", node_type):
        raise ModelError(f"{location}.$type is not a normalized physical type.")
    numeric_id = _integer(node["NodeId"], f"{location}.NodeId")
    node_id = f"node-{numeric_id}"
    if node_id in node_ids:
        raise ModelError(f"{location}.NodeId is duplicated.")
    node_ids.add(node_id)
    return [
        (
            node_id,
            node_type,
            tuple(sorted(descendants, key=_topology_sort_key)),
        )
    ]


def _validate_sanitized_queryplan(
    value: Any, mode: str, digest: str, plan_count: int
) -> tuple[Any, ...] | None:
    if mode == "ESTIMATED":
        if value != {}:
            raise ModelError("ESTIMATED mode must not retain sanitized QueryPlan evidence.")
        return None
    plan = _shape(value, ("RootOperator",), "model.plan.sanitized_queryplan")
    root = _shape(
        plan["RootOperator"],
        ("NodeId", "Operators"),
        "model.plan.sanitized_queryplan.RootOperator",
    )
    _integer(root["NodeId"], "model.plan.sanitized_queryplan.RootOperator.NodeId")
    node_ids: set[str] = set()
    topology = tuple(
        sorted(
            _sanitized_nodes(
                root["Operators"],
                "model.plan.sanitized_queryplan.RootOperator.Operators",
                node_ids,
            ),
            key=_topology_sort_key,
        )
    )
    if len(node_ids) != plan_count:
        raise ModelError(
            "model.plan.sanitized_queryplan operator count does not match model.plan.operator_count."
        )
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != digest:
        raise ModelError(
            "model.plan.sanitized_digest_sha256 does not match sanitized QueryPlan evidence."
        )
    return topology


def _model_operator_topology(roots: list[Any]) -> tuple[Any, ...]:
    def node(value: dict[str, Any]) -> tuple[Any, ...]:
        return (
            value["node_id"],
            value["name"],
            tuple(
                sorted(
                    (node(child) for child in value["children"]),
                    key=_topology_sort_key,
                )
            ),
        )

    return tuple(sorted((node(root) for root in roots), key=_topology_sort_key))


def _validate_physical(
    value: Any,
    plan_count: int,
    plan_topology: tuple[Any, ...] | None,
    mode: str,
    head: str,
    project: str,
    location: str,
) -> set[str]:
    physical = _shape(
        value,
        (
            "input_contract",
            "full_plan",
            "logical_to_physical",
        ),
        location,
        optional=("raw_plan_sections",),
    )
    contract = _shape(
        physical["input_contract"],
        ("title", "collapsible", "fields", "source_links"),
        f"{location}.input_contract",
    )
    _text(contract["title"], f"{location}.input_contract.title")
    if _boolean(
        contract["collapsible"], f"{location}.input_contract.collapsible"
    ) is not True:
        raise ModelError(f"{location}.input_contract.collapsible must be exactly true.")
    _validate_schema_fields(contract["fields"], f"{location}.input_contract.fields")
    _links(
        contract["source_links"],
        head,
        project,
        f"{location}.input_contract.source_links",
    )
    full_plan = _shape(
        physical["full_plan"],
        ("complete", "operator_count", "roots"),
        f"{location}.full_plan",
    )
    complete = _boolean(full_plan["complete"], f"{location}.full_plan.complete")
    if mode == "EVIDENCE" and not complete:
        raise ModelError("EVIDENCE mode requires a complete full physical plan tree.")
    if mode == "ESTIMATED" and complete:
        raise ModelError("ESTIMATED mode must not claim a complete physical plan.")
    expected_count = _integer(
        full_plan["operator_count"], f"{location}.full_plan.operator_count", minimum=1
    )
    roots = _list(full_plan["roots"], f"{location}.full_plan.roots", nonempty=True)
    operator_ids: set[str] = set()
    node_ids: set[str] = set()
    actual_count = sum(
        _validate_operator(
            root,
            head,
            project,
            f"{location}.full_plan.roots[{index}]",
            operator_ids,
            node_ids,
        )
        for index, root in enumerate(roots)
    )
    if expected_count != actual_count or plan_count != actual_count:
        raise ModelError(f"{location}.full_plan operator counts do not match its tree.")
    if mode == "EVIDENCE" and _model_operator_topology(roots) != plan_topology:
        raise ModelError(
            f"{location}.full_plan topology does not match the sanitized QueryPlan evidence."
        )
    mappings = _list(
        physical["logical_to_physical"],
        f"{location}.logical_to_physical",
        nonempty=True,
    )
    for index, mapping_value in enumerate(mappings):
        mapping_location = f"{location}.logical_to_physical[{index}]"
        mapping = _shape(
            mapping_value,
            ("logical_id", "physical_operator_ids", "reason", "source_links"),
            mapping_location,
        )
        _identifier(mapping["logical_id"], f"{mapping_location}.logical_id")
        mapped_ids = _list(
            mapping["physical_operator_ids"],
            f"{mapping_location}.physical_operator_ids",
            nonempty=True,
        )
        for mapped_index, mapped_id in enumerate(mapped_ids):
            _identifier(
                mapped_id,
                f"{mapping_location}.physical_operator_ids[{mapped_index}]",
            )
        if not set(mapped_ids) <= operator_ids:
            raise ModelError(
                f"{mapping_location}.physical_operator_ids references an absent operator."
            )
        _text(mapping["reason"], f"{mapping_location}.reason")
        _links(
            mapping["source_links"],
            head,
            project,
            f"{mapping_location}.source_links",
        )
    for index, section_value in enumerate(physical.get("raw_plan_sections", [])):
        section_location = f"{location}.raw_plan_sections[{index}]"
        section = _shape(
            section_value,
            (
                "title",
                "content",
                "sanitized",
                "contains_proprietary_data",
                "digest_sha256",
                "source_links",
            ),
            section_location,
        )
        _text(section["title"], f"{section_location}.title")
        _text(section["content"], f"{section_location}.content")
        if section["sanitized"] is not True or section["contains_proprietary_data"] is not False:
            raise ModelError(
                f"{section_location} must be sanitized and contain no proprietary data."
            )
        if not re.fullmatch(
            r"[0-9a-f]{64}", _text(section["digest_sha256"], f"{section_location}.digest_sha256")
        ):
            raise ModelError(f"{section_location}.digest_sha256 must be a SHA-256 digest.")
        _links(
            section["source_links"], head, project, f"{section_location}.source_links"
        )
    return operator_ids


def _validate_representation(
    value: Any, head: str, project: str, location: str
) -> None:
    representation = _shape(
        value, ("label", "content", "source_links"), location
    )
    _text(representation["label"], f"{location}.label")
    _text(representation["content"], f"{location}.content")
    _links(
        representation["source_links"], head, project, f"{location}.source_links"
    )


def _validate_boundary(
    value: Any, head: str, project: str, location: str
) -> set[str]:
    boundary = _shape(
        value,
        (
            "lanes",
            "representations",
            "node_byte_ranges",
            "selectable_views",
            "context_toggle_comparisons",
            "failure_injections",
            "debugger_map",
        ),
        location,
    )
    lanes = _list(boundary["lanes"], f"{location}.lanes", nonempty=True)
    boundary_ids: set[str] = set()
    lane_ids: set[str] = set()
    for index, lane_value in enumerate(lanes):
        lane_location = f"{location}.lanes[{index}]"
        lane = _shape(
            lane_value,
            ("id", "boundary_id", "title", "input", "output", "source_links"),
            lane_location,
        )
        lane_id = _identifier(lane["id"], f"{lane_location}.id")
        if lane_id not in {"managed", "json", "utf-8", "native"}:
            raise ModelError(f"{lane_location}.id is not a supported boundary lane.")
        lane_ids.add(lane_id)
        boundary_id = _identifier(
            lane["boundary_id"], f"{lane_location}.boundary_id"
        )
        if boundary_id in boundary_ids:
            raise ModelError(f"{lane_location}.boundary_id must be unique.")
        boundary_ids.add(boundary_id)
        for key in ("title", "input", "output"):
            _text(lane[key], f"{lane_location}.{key}")
        _links(lane["source_links"], head, project, f"{lane_location}.source_links")
    if lane_ids != {"managed", "json", "utf-8", "native"} or len(lanes) != 4:
        raise ModelError(
            f"{location}.lanes must contain managed, json, utf-8, and native exactly once."
        )
    representations = _shape(
        boundary["representations"],
        ("object", "json", "bytes"),
        f"{location}.representations",
    )
    for key in ("object", "json", "bytes"):
        _validate_representation(
            representations[key],
            head,
            project,
            f"{location}.representations.{key}",
        )
    ranges = _list(
        boundary["node_byte_ranges"],
        f"{location}.node_byte_ranges",
        nonempty=True,
    )
    for index, range_value in enumerate(ranges):
        range_location = f"{location}.node_byte_ranges[{index}]"
        byte_range = _shape(
            range_value,
            ("node_id", "start", "end", "description", "source_links"),
            range_location,
        )
        _identifier(byte_range["node_id"], f"{range_location}.node_id")
        start = _integer(byte_range["start"], f"{range_location}.start")
        end = _integer(byte_range["end"], f"{range_location}.end")
        if end <= start:
            raise ModelError(f"{range_location} must be a non-empty half-open byte range.")
        _text(byte_range["description"], f"{range_location}.description")
        _links(
            byte_range["source_links"],
            head,
            project,
            f"{range_location}.source_links",
        )
    simple_specs = {
        "selectable_views": ("id", "title", "content", "source_links"),
        "context_toggle_comparisons": (
            "id",
            "title",
            "without_context",
            "with_context",
            "source_links",
        ),
        "failure_injections": (
            "id",
            "title",
            "injection",
            "expected_failure",
            "source_links",
        ),
        "debugger_map": (
            "id",
            "boundary_id",
            "managed_location",
            "native_location",
            "source_links",
        ),
    }
    for field, keys in simple_specs.items():
        items = _list(boundary[field], f"{location}.{field}", nonempty=True)
        for index, item_value in enumerate(items):
            item_location = f"{location}.{field}[{index}]"
            item = _shape(item_value, keys, item_location)
            for key in keys[:-1]:
                if key in {"id", "boundary_id"}:
                    _identifier(item[key], f"{item_location}.{key}")
                else:
                    _text(item[key], f"{item_location}.{key}")
            if field == "debugger_map" and item["boundary_id"] not in boundary_ids:
                raise ModelError(
                    f"{item_location}.boundary_id references an absent boundary."
                )
            _links(item["source_links"], head, project, f"{item_location}.source_links")
        _unique(items, lambda item: item["id"], f"{location}.{field}", "id")
    return boundary_ids


def _validate_execute(
    value: Any,
    evidence_refs: set[str],
    head: str,
    project: str,
    location: str,
    expected_events: int,
    expected_scenarios: int,
) -> None:
    execute = _shape(
        value,
        (
            "action_timeline",
            "language_lanes",
            "call_stack",
            "heap_zones",
            "components",
            "scenarios",
        ),
        location,
    )
    timeline = _list(
        execute["action_timeline"], f"{location}.action_timeline", nonempty=True
    )
    if len(timeline) != expected_events:
        raise ModelError(
            f"{location}.action_timeline must contain exactly {expected_events} canonical events."
        )
    for index, event_value in enumerate(timeline):
        event_location = f"{location}.action_timeline[{index}]"
        event = _shape(
            event_value,
            (
                "id",
                "title",
                "what",
                "why",
                "stack_effect",
                "heap_effect",
                "lang",
                "memory",
                "active",
                "live",
                "source_links",
            ),
            event_location,
        )
        _identifier(event["id"], f"{event_location}.id")
        for key in ("title", "what", "why", "stack_effect", "heap_effect"):
            _text(event[key], f"{event_location}.{key}")
        if event["lang"] not in {"cpp", "rust", "csharp"}:
            raise ModelError(f"{event_location}.lang is invalid.")
        memory_events = _list(event["memory"], f"{event_location}.memory")
        for memory_index, memory_value in enumerate(memory_events):
            memory_location = f"{event_location}.memory[{memory_index}]"
            memory = _shape(
                memory_value,
                ("op", "zone", "id", "title", "detail"),
                memory_location,
            )
            if memory["op"] not in {"add", "update", "release"}:
                raise ModelError(f"{memory_location}.op is invalid.")
            if memory["zone"] not in {"managed", "borrowed", "cpp", "rust"}:
                raise ModelError(f"{memory_location}.zone is invalid.")
            _identifier(memory["id"], f"{memory_location}.id")
            _text(memory["title"], f"{memory_location}.title")
            _text(memory["detail"], f"{memory_location}.detail")
        _identifier(event["active"], f"{event_location}.active")
        live_components = _list(event["live"], f"{event_location}.live")
        for live_index, component_id in enumerate(live_components):
            _identifier(component_id, f"{event_location}.live[{live_index}]")
        if len(set(live_components)) != len(live_components):
            raise ModelError(f"{event_location}.live must not contain duplicates.")
        _links(event["source_links"], head, project, f"{event_location}.source_links")
    _unique(timeline, lambda item: item["id"], f"{location}.action_timeline", "event id")

    lanes = _list(execute["language_lanes"], f"{location}.language_lanes", nonempty=True)
    lane_languages: set[str] = set()
    for index, lane_value in enumerate(lanes):
        lane_location = f"{location}.language_lanes[{index}]"
        lane = _shape(
            lane_value, ("language", "role", "applicability", "source_links"), lane_location
        )
        if lane["language"] not in LANGUAGES:
            raise ModelError(f"{lane_location}.language is invalid.")
        lane_languages.add(lane["language"])
        _text(lane["role"], f"{lane_location}.role")
        _text(lane["applicability"], f"{lane_location}.applicability")
        _links(lane["source_links"], head, project, f"{lane_location}.source_links")
    if len(lane_languages) != len(lanes):
        raise ModelError(f"{location}.language_lanes must not repeat a language.")

    stack = _list(execute["call_stack"], f"{location}.call_stack", nonempty=True)
    for index, frame_value in enumerate(stack):
        frame_location = f"{location}.call_stack[{index}]"
        frame = _shape(
            frame_value,
            ("position", "language", "kind", "frame", "what", "why", "source_links"),
            frame_location,
        )
        if frame["position"] != index:
            raise ModelError(
                f"{frame_location}.position must preserve the top-first call-stack order."
            )
        if frame["language"] not in lane_languages:
            raise ModelError(f"{frame_location}.language lacks an applicable language lane.")
        if frame["kind"] not in {"cpp", "csharp", "rust", "abi"}:
            raise ModelError(f"{frame_location}.kind is invalid.")
        for key in ("frame", "what", "why"):
            _text(frame[key], f"{frame_location}.{key}")
        _links(frame["source_links"], head, project, f"{frame_location}.source_links")

    zones = _list(execute["heap_zones"], f"{location}.heap_zones")
    for index, zone_value in enumerate(zones):
        zone_location = f"{location}.heap_zones[{index}]"
        zone = _shape(
            zone_value,
            (
                "id",
                "zone",
                "language",
                "state",
                "what",
                "why",
                "owner",
                "source_links",
            ),
            zone_location,
        )
        _identifier(zone["id"], f"{zone_location}.id")
        if zone["zone"] not in {"managed", "borrowed", "cpp", "rust"}:
            raise ModelError(f"{zone_location}.zone is invalid.")
        if zone["language"] not in lane_languages:
            raise ModelError(f"{zone_location}.language lacks an applicable language lane.")
        if zone["state"] not in HEAP_STATES:
            raise ModelError(f"{zone_location}.state is invalid.")
        for key in ("what", "why", "owner"):
            _text(zone[key], f"{zone_location}.{key}")
        _links(zone["source_links"], head, project, f"{zone_location}.source_links")
    if [zone["zone"] for zone in zones] != ["managed", "borrowed", "cpp", "rust"]:
        raise ModelError(
            f"{location}.heap_zones must preserve managed, borrowed, cpp, rust order."
        )

    components = _list(
        execute["components"], f"{location}.components", nonempty=True
    )
    for index, component_value in enumerate(components):
        component_location = f"{location}.components[{index}]"
        component = _shape(
            component_value,
            (
                "id",
                "name",
                "evidence_ref",
                "state",
                "role",
                "pull_direction",
                "data_direction",
                "ownership",
                "breakpoint",
                "source_links",
            ),
            component_location,
        )
        _identifier(component["id"], f"{component_location}.id")
        _identifier(
            component["evidence_ref"], f"{component_location}.evidence_ref"
        )
        for key in (
            "name",
            "role",
            "pull_direction",
            "data_direction",
            "ownership",
            "breakpoint",
        ):
            _text(component[key], f"{component_location}.{key}")
        if component["evidence_ref"] not in evidence_refs:
            raise ModelError(
                f"{component_location}.evidence_ref references an operator or boundary "
                "absent from this walkthrough."
            )
        if component["state"] not in COMPONENT_STATES:
            raise ModelError(f"{component_location}.state is invalid.")
        _links(
            component["source_links"],
            head,
            project,
            f"{component_location}.source_links",
        )
    _unique(components, lambda item: item["id"], f"{location}.components", "component id")
    component_ids = {component["id"] for component in components}
    for index, event in enumerate(timeline):
        referenced = {event["active"], *event["live"]}
        dangling = sorted(referenced - component_ids)
        if dangling:
            raise ModelError(
                f"{location}.action_timeline[{index}] references absent components {dangling}."
            )

    scenarios = _list(execute["scenarios"], f"{location}.scenarios", nonempty=True)
    if len(scenarios) != expected_scenarios:
        raise ModelError(
            f"{location}.scenarios must contain exactly {expected_scenarios} canonical scenarios."
        )
    scenario_types: set[str] = set()
    for index, scenario_value in enumerate(scenarios):
        scenario_location = f"{location}.scenarios[{index}]"
        scenario = _shape(
            scenario_value,
            ("type", "trigger", "behavior", "ownership_effect", "source_links"),
            scenario_location,
        )
        if scenario["type"] not in {
            "failure",
            "cancellation",
            "memory",
            "lifetime",
            "memory/lifetime",
        }:
            raise ModelError(f"{scenario_location}.type is invalid.")
        scenario_types.update(scenario["type"].split("/"))
        for key in ("trigger", "behavior", "ownership_effect"):
            _text(scenario[key], f"{scenario_location}.{key}")
        _links(scenario["source_links"], head, project, f"{scenario_location}.source_links")
    if scenario_types != {"failure", "cancellation", "memory", "lifetime"}:
        raise ModelError(
            f"{location}.scenarios must cover failure, cancellation, memory, and lifetime."
        )


def _validate_runner(
    value: Any,
    stage_id: str,
    badge: str,
    stage_no_op: bool,
    plan_count: int,
    plan_topology: tuple[Any, ...] | None,
    mode: str,
    head: str,
    project: str,
    location: str,
    evidence_refs: set[str],
    expected_runner_type: str,
    expected_item_count: int,
    expected_runner_mode: str,
    expected_scenario_count: int,
    expected_key: str,
) -> None:
    common = (
        "type",
        "title",
        "actions",
        "snapshots",
        "experiments",
        "no_op",
        "source_links",
    )
    runner_type = expected_runner_type
    runner = _shape(value, common + (runner_type,), location)
    if runner["type"] != runner_type:
        raise ModelError(f"{location}.type must be '{runner_type}' for this canonical substep.")
    required_gate = stage_no_op or badge in NO_OP_KINDS
    title = _text(runner["title"], f"{location}.title")
    if not re.fullmatch(r"Run the .+ yourself", title):
        raise ModelError(f"{location}.title must follow 'Run the ... yourself'.")
    if runner_type not in title.lower():
        raise ModelError(
            f"{location}.title must identify its '{runner_type}' runner type."
        )
    actions = _list(runner["actions"], f"{location}.actions", nonempty=True)
    if len(actions) != expected_item_count:
        raise ModelError(
            f"{location}.actions must contain exactly {expected_item_count} canonical items."
        )
    for index, action in enumerate(actions):
        _validate_runner_action(
            action,
            head,
            project,
            mode,
            f"{location}.actions[{index}]",
            require_pass_fields=runner_type == "pass",
            require_boundary_lane=runner_type == "boundary",
        )
        if required_gate and action["before"] != action["after"]:
            raise ModelError(
                f"{location}.actions[{index}] is gated as a no-op but changes its artifact."
            )
        if required_gate and action["evidence_kind"] != badge:
            raise ModelError(
                f"{location}.actions[{index}].evidence_kind must match its no-op outcome."
            )
    _unique(actions, lambda item: item["id"], f"{location}.actions", "action id")
    if runner_type == "boundary":
        actual_lanes = tuple(action["lane"] for action in actions)
        if actual_lanes != BOUNDARY_LANES_BY_KEY[expected_key]:
            raise ModelError(
                f"{location}.actions must preserve the canonical boundary lane distribution."
            )
    snapshots = _list(runner["snapshots"], f"{location}.snapshots", nonempty=True)
    if len(snapshots) < 2:
        raise ModelError(f"{location}.snapshots must contain at least two snapshots.")
    if len(actions) > len(snapshots):
        raise ModelError(
            f"{location}.snapshots must make every runner action reachable."
        )
    signatures = {
        _validate_runner_snapshot(
            snapshot, head, project, f"{location}.snapshots[{index}]"
        )
        for index, snapshot in enumerate(snapshots)
    }
    if len(signatures) != len(snapshots):
        raise ModelError(f"{location}.snapshots must be distinct.")
    _unique(snapshots, lambda item: item["id"], f"{location}.snapshots", "snapshot id")
    experiments = _list(
        runner["experiments"], f"{location}.experiments", nonempty=True
    )
    for index, experiment in enumerate(experiments):
        _validate_experiment(
            experiment, head, project, f"{location}.experiments[{index}]"
        )
    _unique(
        experiments,
        lambda item: item["id"],
        f"{location}.experiments",
        "experiment id",
    )
    no_op = _shape(
        runner["no_op"],
        ("enabled", "gates", "reasons"),
        f"{location}.no_op",
    )
    enabled = _boolean(no_op["enabled"], f"{location}.no_op.enabled")
    gates = _list(
        no_op["gates"], f"{location}.no_op.gates", nonempty=required_gate
    )
    reasons = _list(
        no_op["reasons"], f"{location}.no_op.reasons", nonempty=required_gate
    )
    for index, gate in enumerate(gates):
        _text(gate, f"{location}.no_op.gates[{index}]")
    for index, reason in enumerate(reasons):
        _text(reason, f"{location}.no_op.reasons[{index}]")
    if enabled != required_gate:
        raise ModelError(f"{location}.no_op.enabled does not match the substep/stage outcome.")
    if not required_gate and (gates or reasons):
        raise ModelError(
            f"{location}.no_op gates/reasons are only valid when the gate is active."
        )
    _links(runner["source_links"], head, project, f"{location}.source_links")

    if runner_type == "compiler":
        _validate_compiler(
            runner["compiler"],
            stage_id,
            mode,
            head,
            project,
            f"{location}.compiler",
        )
        if runner["compiler"]["mode"] != expected_runner_mode:
            raise ModelError(f"{location}.compiler.mode must be '{expected_runner_mode}'.")
        if required_gate:
            compiler_actions = (
                runner["compiler"]["before_actions"] + runner["compiler"]["after_actions"]
            )
            for index, action in enumerate(compiler_actions):
                if action["evidence_kind"] != badge or action["before"] != action["after"]:
                    raise ModelError(
                        f"{location}.compiler action {index} contradicts its no-op outcome."
                    )
    elif runner_type == "pass":
        _validate_pass(
            runner["pass"], badge, mode, head, project, f"{location}.pass"
        )
    elif runner_type == "physical":
        evidence_refs.update(
            _validate_physical(
                runner["physical"],
                plan_count,
                plan_topology,
                mode,
                head,
                project,
                f"{location}.physical",
            )
        )
    elif runner_type == "boundary":
        evidence_refs.update(
            _validate_boundary(
                runner["boundary"], head, project, f"{location}.boundary"
            )
        )
    else:
        _validate_execute(
            runner["execute"],
            evidence_refs,
            head,
            project,
            f"{location}.execute",
            expected_item_count,
            expected_scenario_count,
        )


def _validate_substep(
    value: Any,
    stage_id: str,
    stage_no_op: bool,
    plan_count: int,
    plan_topology: tuple[Any, ...] | None,
    mode: str,
    head: str,
    project: str,
    location: str,
    evidence_refs: set[str],
    expected_key: str,
    expected_title: str,
    expected_runner_type: str | None,
    expected_item_count: int,
    expected_runner_mode: str,
    expected_scenario_count: int,
) -> str:
    required = (
        "id",
        "title",
        "behavior",
        "change_badge",
        "summary",
        "what_happens",
        "why",
        "debug",
        "next",
        "method_path",
        "source_links",
        "traversal",
        "artifact",
    )
    substep = _shape(value, required, location, optional=("runner",))
    if substep["id"] != expected_key:
        raise ModelError(f"{location}.id must be canonical key '{expected_key}'.")
    if substep["title"] != expected_title:
        raise ModelError(f"{location}.title must be '{expected_title}'.")
    for key in (
        "title",
        "behavior",
        "summary",
        "what_happens",
        "why",
        "debug",
        "next",
    ):
        _text(substep[key], f"{location}.{key}")
    method_path = _list(
        substep["method_path"], f"{location}.method_path", nonempty=True
    )
    for index, method_value in enumerate(method_path):
        method_location = f"{location}.method_path[{index}]"
        method = _shape(method_value, ("name", "source_links"), method_location)
        _text(method["name"], f"{method_location}.name")
        _links(method["source_links"], head, project, f"{method_location}.source_links")
    badge = _evidence_kind(substep["change_badge"], f"{location}.change_badge", mode)
    if stage_no_op and badge not in NO_OP_KINDS:
        raise ModelError(f"{location}.change_badge must be a no-op when its stage is a no-op.")
    _links(substep["source_links"], head, project, f"{location}.source_links")
    _validate_traversal(
        substep["traversal"], head, project, f"{location}.traversal"
    )
    _validate_artifact(
        substep["artifact"],
        head,
        project,
        f"{location}.artifact",
        no_op=badge in NO_OP_KINDS,
    )
    if expected_runner_type is None:
        if "runner" in substep:
            raise ModelError(f"{location}.runner must be omitted for this canonical substep.")
    else:
        if "runner" not in substep:
            raise ModelError(f"{location}.runner is required for this canonical substep.")
        _validate_runner(
            substep["runner"],
            stage_id,
            badge,
            stage_no_op,
            plan_count,
            plan_topology,
            mode,
            head,
            project,
            f"{location}.runner",
            evidence_refs,
            expected_runner_type,
            expected_item_count,
            expected_runner_mode,
            expected_scenario_count,
            expected_key,
        )
    return badge


def _validate_network_beacon(value: Any, project: str, location: str) -> None:
    beacon = _shape(value, ("state", "route", "purpose"), location)
    if beacon["state"] not in {"ENABLED", "DISABLED"}:
        raise ModelError(f"{location}.state must be ENABLED or DISABLED.")
    route = _text(beacon["route"], f"{location}.route")
    expected = f"https://dev.azure.com/msazure/{project}/_git/Azure-Kusto-Service"
    if route != expected:
        raise ModelError(f"{location}.route must be the canonical source repository route.")
    purpose = _text(beacon["purpose"], f"{location}.purpose")
    if "source" not in purpose.lower() or "navigation" not in purpose.lower():
        raise ModelError(f"{location}.purpose must explicitly describe outbound source navigation.")


def _validate_plan_recovery(plan: dict[str, Any], query: str, mode: str) -> None:
    complete = _boolean(
        plan["complete_physical_queryplan"], "model.plan.complete_physical_queryplan"
    )
    provenance = _text(plan["provenance"], "model.plan.provenance")
    recovery = _shape(
        plan["recovery"],
        (
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
        ),
        "model.plan.recovery",
    )
    required = _boolean(recovery["required"], "model.plan.recovery.required")
    prompted = _boolean(recovery["prompted"], "model.plan.recovery.prompted")
    command = _text(
        recovery["command"], "model.plan.recovery.command", allow_empty=(mode == "EVIDENCE")
    )
    deeplink_status = _text(
        recovery["deeplink_status"], "model.plan.recovery.deeplink_status"
    )
    deeplink_url = _text(
        recovery["deeplink_url"], "model.plan.recovery.deeplink_url", allow_empty=True
    )
    outcome = _text(recovery["outcome"], "model.plan.recovery.outcome")
    deficiency = _text(
        recovery["deficiency"], "model.plan.recovery.deficiency", allow_empty=(mode == "EVIDENCE")
    )
    automatic_evidence = _text(
        recovery["automatic_evidence"],
        "model.plan.recovery.automatic_evidence",
        allow_empty=(mode == "EVIDENCE"),
    )
    prompted_at_utc = _text(
        recovery["prompted_at_utc"],
        "model.plan.recovery.prompted_at_utc",
        allow_empty=not prompted,
    )
    prompt_digest = _text(
        recovery["prompt_digest_sha256"],
        "model.plan.recovery.prompt_digest_sha256",
        allow_empty=not prompted,
    )
    expected_command = f".show queryplan <|\n{query}"
    if prompted:
        if not is_utc_timestamp(prompted_at_utc):
            raise ModelError("Recovery prompt timestamp must be UTC RFC 3339.")
        if not re.fullmatch(r"[0-9a-f]{64}", prompt_digest):
            raise ModelError("Recovery prompt requires its SHA-256 digest.")
        expected_prompt = build_recovery_prompt(
            automatic_evidence=automatic_evidence,
            command=command,
            deeplink_url=deeplink_url,
        )
        if hashlib.sha256(expected_prompt.encode("utf-8")).hexdigest() != prompt_digest:
            raise ModelError("Recovery prompt digest does not match its recorded content.")
    elif automatic_evidence or prompted_at_utc or prompt_digest:
        raise ModelError("Unprompted recovery must not claim prompt evidence.")

    if mode == "EVIDENCE":
        if not complete or provenance not in {"automatic", "user_supplied"}:
            raise ModelError(
                "EVIDENCE mode requires a complete physical QueryPlan from automatic or user-supplied evidence."
            )
        if outcome != "accepted":
            raise ModelError("EVIDENCE mode requires an accepted physical QueryPlan.")
        if provenance == "automatic":
            if (
                required
                or prompted
                or command
                or deeplink_status != "not_needed"
                or deeplink_url
                or deficiency
                or automatic_evidence
            ):
                raise ModelError(
                    "Automatic complete physical QueryPlan evidence must skip user recovery."
                )
        else:
            if not required or not prompted:
                raise ModelError(
                    "User-supplied physical QueryPlan evidence must record the recovery prompt."
                )
            if "user" not in plan["tool"].lower() or "non-executing" not in plan["tool"].lower():
                raise ModelError(
                    "User-supplied evidence tool must identify user-supplied non-executing provenance."
                )
            if command != expected_command:
                raise ModelError(
                    "User-supplied recovery command must preserve the exact query."
                )
            if deeplink_status not in {"generated", "failed", "unavailable"}:
                raise ModelError("User-supplied recovery must record a deeplink attempt.")
            if deeplink_status == "generated":
                parsed = urlparse(deeplink_url)
                if parsed.scheme != "https" or not parsed.netloc:
                    raise ModelError(
                        "Generated recovery deeplink must be an absolute HTTPS URI."
                    )
            elif deeplink_url:
                raise ModelError(
                    "Failed or unavailable deeplink recovery must not claim a URL."
                )
            if not deficiency:
                raise ModelError(
                    "User-supplied recovery must record the automatic QueryPlan deficiency."
                )
            if not automatic_evidence:
                raise ModelError(
                    "User-supplied recovery must record the automatic evidence found."
                )
    else:
        allowed_outcomes = {
            "user_declined",
            "user_could_not_provide",
            "user_chose_after_rejection",
        }
        if complete or provenance != "estimated_after_recovery":
            raise ModelError(
                "ESTIMATED mode requires missing complete physical QueryPlan evidence after recovery."
            )
        if not required or not prompted:
            raise ModelError(
                "ESTIMATED mode is forbidden until physical QueryPlan recovery was prompted."
            )
        if command != expected_command:
            raise ModelError(
                "Recovery command must preserve the exact query in '.show queryplan <|' syntax."
            )
        if outcome not in allowed_outcomes:
            raise ModelError(
                "ESTIMATED mode requires an explicit user decline, inability, or choice after rejection."
            )
        if deeplink_status not in {"generated", "failed", "unavailable"}:
            raise ModelError("Recovery must record the deeplink generation attempt.")
        if deeplink_status == "generated":
            parsed = urlparse(deeplink_url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ModelError("Generated recovery deeplink must be an absolute HTTPS URI.")
        elif deeplink_url:
            raise ModelError("Failed or unavailable deeplink recovery must not claim a URL.")
        if not deficiency:
            raise ModelError("ESTIMATED recovery must name the missing physical QueryPlan artifact.")
        if not automatic_evidence:
            raise ModelError("ESTIMATED recovery must record the automatic evidence found.")


def validate_complete_model(model: dict[str, Any]) -> None:
    root_keys = (
        "schema_version",
        "model_state",
        "evidence_mode",
        "estimate_reason",
        "query",
        "source",
        "plan",
        "network_beacon",
        "stages",
    )
    _shape(model, root_keys, "model")
    if model["schema_version"] != "2.0":
        raise ModelError("model.schema_version must be '2.0'.")
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
    if mode == "ESTIMATED" and (
        "queryplan" not in estimate_reason.lower()
        or not any(
            term in estimate_reason.lower()
            for term in ("declined", "could not", "unusable", "rejected", "chose")
        )
    ):
        raise ModelError(
            "model.estimate_reason must record the missing QueryPlan and explicit recovery outcome."
        )

    query = _shape(
        model["query"],
        ("text", "cluster_uri", "database", "title", "slug"),
        "model.query",
    )
    for key in ("text", "cluster_uri", "database", "title", "slug"):
        _text(query[key], f"model.query.{key}")
    validate_cluster_uri(query["cluster_uri"], "model.query.cluster_uri")
    if query["slug"] != query_slug(
        query["text"], query["cluster_uri"], query["database"]
    ):
        raise ModelError("model.query.slug is not the stable query-derived slug.")

    source = _shape(
        model["source"],
        ("organization", "project", "repository", "workspace_head"),
        "model.source",
    )
    if source["organization"] != "msazure" or source["repository"] != "Azure-Kusto-Service":
        raise ModelError("model.source must target msazure/Azure-Kusto-Service.")
    project = _text(source["project"], "model.source.project")
    head = _text(source["workspace_head"], "model.source.workspace_head")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ModelError("model.source.workspace_head must be a lowercase 40-character commit.")
    _validate_network_beacon(model["network_beacon"], project, "model.network_beacon")

    plan = _shape(
        model["plan"],
        (
            "tool",
            "collected_at_utc",
            "non_executing",
            "digest_sha256",
            "sanitized_digest_sha256",
            "sanitized_queryplan",
            "operator_count",
            "complete_physical_queryplan",
            "provenance",
            "recovery",
        ),
        "model.plan",
    )
    _text(plan["tool"], "model.plan.tool")
    collected_at_utc = _text(
        plan["collected_at_utc"], "model.plan.collected_at_utc"
    )
    if not is_utc_timestamp(collected_at_utc):
        raise ModelError("model.plan.collected_at_utc must be a valid UTC RFC 3339 timestamp.")
    if plan["non_executing"] is not True:
        raise ModelError("model.plan.non_executing must be exactly true.")
    digest = _text(plan["digest_sha256"], "model.plan.digest_sha256", allow_empty=True)
    sanitized_digest = _text(
        plan["sanitized_digest_sha256"],
        "model.plan.sanitized_digest_sha256",
        allow_empty=(mode == "ESTIMATED"),
    )
    if mode == "EVIDENCE" and not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ModelError("EVIDENCE mode requires a SHA-256 plan digest.")
    if mode == "EVIDENCE" and not re.fullmatch(r"[0-9a-f]{64}", sanitized_digest):
        raise ModelError("EVIDENCE mode requires a sanitized QueryPlan SHA-256 digest.")
    if mode == "ESTIMATED" and sanitized_digest:
        raise ModelError("ESTIMATED mode must not claim a sanitized physical QueryPlan digest.")
    _validate_plan_recovery(plan, query["text"], mode)
    plan_count = _integer(plan["operator_count"], "model.plan.operator_count", minimum=1)
    plan_topology = _validate_sanitized_queryplan(
        plan["sanitized_queryplan"], mode, sanitized_digest, plan_count
    )

    stages = _list(model["stages"], "model.stages")
    if len(stages) != len(STAGES):
        raise ModelError("model.stages must contain exactly ten stages.")
    evidence_refs: set[str] = set()
    for index, ((expected_id, expected_title, expected_kind), stage_value) in enumerate(
        zip(STAGES, stages, strict=True)
    ):
        location = f"model.stages[{index}]"
        required = (
            "id",
            "order",
            "title",
            "kind",
            "evidence_kind",
            "no_op_explanation",
            "source_links",
            "overview",
            "substeps",
        )
        stage = _shape(stage_value, required, location, optional=("additional_context",))
        if (
            stage["id"] != expected_id
            or stage["title"] != expected_title
            or stage["kind"] != expected_kind
            or stage["order"] != index + 1
        ):
            raise ModelError(f"{location} does not match the required lifecycle order.")
        evidence_kind = _evidence_kind(
            stage["evidence_kind"], f"{location}.evidence_kind", mode
        )
        stage_no_op = evidence_kind in NO_OP_KINDS
        explanation = _text(
            stage["no_op_explanation"],
            f"{location}.no_op_explanation",
            allow_empty=not stage_no_op,
        )
        if not stage_no_op and explanation:
            raise ModelError(
                f"{location}.no_op_explanation is only valid for no-op evidence."
            )
        _links(stage["source_links"], head, project, f"{location}.source_links")
        _validate_overview(stage["overview"], f"{location}.overview")
        if expected_kind == "optimizer" or expected_id == "preparation":
            if "additional_context" not in stage:
                raise ModelError(
                    f"{location}.additional_context is required for preparation and optimizer stages."
                )
            _validate_additional_context(
                stage["additional_context"],
                head,
                project,
                f"{location}.additional_context",
            )
        elif "additional_context" in stage:
            _validate_additional_context(
                stage["additional_context"],
                head,
                project,
                f"{location}.additional_context",
            )
        substeps = _list(stage["substeps"], f"{location}.substeps", nonempty=True)
        expected_substeps = CANONICAL_SUBSTEPS[index]
        if len(substeps) != len(expected_substeps):
            raise ModelError(
                f"{location}.substeps must contain exactly {len(expected_substeps)} canonical substeps."
            )
        badges = [
            _validate_substep(
                substep,
                expected_id,
                stage_no_op,
                plan_count,
                plan_topology,
                mode,
                head,
                project,
                f"{location}.substeps[{substep_index}]",
                evidence_refs,
                expected_substep.key,
                expected_substep.title,
                expected_substep.runner_type,
                expected_substep.item_count,
                expected_substep.runner_mode,
                expected_substep.scenario_count,
            )
            for substep_index, (substep, expected_substep) in enumerate(
                zip(substeps, expected_substeps, strict=True)
            )
        ]
        _unique(substeps, lambda item: item["id"], f"{location}.substeps", "substep id")
        badge_set = set(badges)
        if evidence_kind == "OBSERVED" and badge_set != {"OBSERVED"}:
            raise ModelError(
                f"{location}.evidence_kind contradicts its substep change badges."
            )
        if evidence_kind == "TRANSFORMED" and "TRANSFORMED" not in badge_set:
            raise ModelError(
                f"{location}.evidence_kind contradicts its substep change badges."
            )
        if evidence_kind == "SCHEDULED_NO_OP" and badge_set != {"SCHEDULED_NO_OP"}:
            raise ModelError(
                f"{location}.evidence_kind contradicts its substep change badges."
            )
        if evidence_kind == "NO_OP" and badge_set != {"NO_OP"}:
            raise ModelError(
                f"{location}.evidence_kind contradicts its substep change badges."
            )
        if expected_kind == "optimizer":
            derived = (
                "ESTIMATED"
                if set(badges) == {"ESTIMATED"}
                else "TRANSFORMED"
                if "TRANSFORMED" in badges
                else "SCHEDULED_NO_OP"
                if set(badges) == {"SCHEDULED_NO_OP"}
                else evidence_kind
            )
            if evidence_kind != derived:
                raise ModelError(
                    f"{location}.evidence_kind contradicts its pass runner outcomes."
                )


def safe_json_for_html(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return raw.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
