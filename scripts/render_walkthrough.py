from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path

from model_contract import (
    ModelError,
    load_model,
    safe_json_for_html,
    validate_complete_model,
    verify_source_workspace,
)
from spec_compliance import audit_rendered_html


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "assets" / "walkthrough-template.html"


def documents_root() -> Path:
    home = Path.home()
    one_drive = home / "OneDrive - Microsoft" / "Documents"
    if one_drive.is_dir():
        return one_drive
    documents = home / "Documents"
    if documents.is_dir():
        return documents
    raise ModelError("Neither OneDrive Documents nor local Documents exists.")


def render(model: dict, output: Path, source_workspace: Path) -> dict:
    validate_complete_model(model)
    verify_source_workspace(source_workspace, model)
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    title = model["query"]["title"]
    replacements = {
        "__DOCUMENT_TITLE__": html.escape(title, quote=True),
        "__EVIDENCE_MODE__": html.escape(model["evidence_mode"], quote=True),
        "__MODEL_JSON__": safe_json_for_html(model),
    }
    for marker, value in replacements.items():
        if marker not in template:
            raise ModelError(f"Template marker {marker} is missing.")
        template = template.replace(marker, value)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".html.tmp")
    temporary.write_text(template, encoding="utf-8", newline="\n")
    try:
        compliance = audit_rendered_html(template)
    except (ModelError, OSError, json.JSONDecodeError):
        temporary.unlink(missing_ok=True)
        raise
    os.replace(temporary, output)
    return compliance


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and render a lifecycle evidence model.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--source-workspace", required=True)
    parser.add_argument("--output")
    parser.add_argument("--output-root")
    args = parser.parse_args()
    if args.output and args.output_root:
        parser.error("--output and --output-root are mutually exclusive")

    try:
        model_path = Path(args.model).expanduser().resolve()
        model = load_model(model_path)
        slug = model.get("query", {}).get("slug", "invalid")
        if args.output:
            output = Path(args.output).expanduser().resolve()
        else:
            root = (
                Path(args.output_root).expanduser().resolve()
                if args.output_root
                else documents_root() / "Bookmarks"
            )
            output = root / slug / f"{slug}.html"
        compliance = render(model, output, Path(args.source_workspace))
    except (ModelError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")

    print(
        json.dumps(
            {
                "ok": True,
                "html_path": str(output),
                "title": model["query"]["title"],
                "slug": model["query"]["slug"],
                "evidence_mode": model["evidence_mode"],
                "plan_provenance": model["plan"]["provenance"],
                "compliance": compliance,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
