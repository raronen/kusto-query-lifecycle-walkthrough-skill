from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PACKAGE_FILES = (
    Path("SKILL.md"),
    Path("assets/walkthrough-template.html"),
    Path("references/applicability-rules.md"),
    Path("references/artifact-quality.md"),
    Path("references/evidence-collection.md"),
    Path("references/evidence-model.schema.json"),
    Path("references/source-grounding.md"),
    Path("scripts/Publish-Walkthrough.ps1"),
    Path("scripts/model_contract.py"),
    Path("scripts/render_walkthrough.py"),
    Path("scripts/scaffold_model.py"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic Copilot skill archive.")
    parser.add_argument(
        "--output",
        default=str(ROOT / "dist" / "kusto-query-lifecycle-walkthrough.skill"),
    )
    args = parser.parse_args()
    output = Path(args.output).expanduser().resolve()

    missing = [str(path) for path in PACKAGE_FILES if not (ROOT / path).is_file()]
    if missing:
        parser.error(f"missing package files: {', '.join(missing)}")
    skill_lines = (ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()
    if len(skill_lines) >= 500:
        parser.error("SKILL.md must remain under 500 lines")
    forbidden = [path for path in PACKAGE_FILES if path.name.lower() in {"readme.md", "changelog.md"}]
    if forbidden:
        parser.error("skill package must not contain README or changelog files")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in sorted(PACKAGE_FILES, key=lambda item: item.as_posix()):
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, (ROOT / relative).read_bytes())

    print(
        json.dumps(
            {
                "ok": True,
                "archive": str(output),
                "files": len(PACKAGE_FILES),
                "skill_lines": len(skill_lines),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
