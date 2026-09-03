from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from model_contract import STAGES, is_authorized_source_remote, query_slug


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
    if len(head) != 40:
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
    if not args.cluster_uri.startswith("https://"):
        parser.error("--cluster-uri must be an absolute HTTPS URI")
    if not args.database.strip():
        parser.error("--database must not be empty")

    slug = query_slug(query, args.cluster_uri, args.database)
    stages = [
        {
            "id": stage_id,
            "order": index,
            "title": title,
            "kind": kind,
            "summary": "",
            "evidence_kind": "PENDING",
            "no_op_explanation": "",
            "source_links": [],
            "actions": [],
        }
        for index, (stage_id, title, kind) in enumerate(STAGES, start=1)
    ]
    model = {
        "schema_version": "1.0",
        "model_state": "DRAFT",
        "evidence_mode": "ESTIMATED",
        "estimate_reason": "Plan evidence has not been collected.",
        "query": {
            "text": query,
            "cluster_uri": args.cluster_uri,
            "database": args.database,
            "title": "Kusto query lifecycle walkthrough",
            "slug": slug,
        },
        "source": {
            "organization": "msazure",
            "project": args.project,
            "repository": "Azure-Kusto-Service",
            "workspace_head": resolve_head(args.source_workspace, args.project),
        },
        "plan": {
            "tool": "pending non-executing query-plan collection",
            "collected_at_utc": "",
            "non_executing": True,
            "digest_sha256": "",
            "operator_count": 0,
        },
        "stages": stages,
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"model": str(output), "slug": slug, "state": "DRAFT"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
