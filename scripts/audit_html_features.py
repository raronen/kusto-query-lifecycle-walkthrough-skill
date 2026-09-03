from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


TRACKED_CLASS_TOKENS = {
    "action-rail",
    "additional-context",
    "artifact-panel",
    "boundary-lab",
    "compiler-lab",
    "component",
    "deep-dive",
    "event-panel",
    "execution-lab",
    "heap-zone",
    "lane",
    "network-beacon",
    "pass-lab",
    "physical-lab",
    "runner-lab",
    "stage-nav",
    "substep-detail",
    "substep-rail",
    "traversal-lab",
    "tree",
    "tree-node",
}


class InventoryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: Counter[str] = Counter()
        self.classes: Counter[str] = Counter()
        self.ids: set[str] = set()
        self.feature_ids: set[str] = set()
        self.input_types: Counter[str] = Counter()
        self.remote_dependencies: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        self.tags[tag] += 1
        if values.get("id"):
            self.ids.add(values["id"])
        if values.get("data-feature-id"):
            self.feature_ids.add(values["data-feature-id"])
        for token in (values.get("class") or "").split():
            if token in TRACKED_CLASS_TOKENS:
                self.classes[token] += 1
        if tag == "input":
            self.input_types[(values.get("type") or "text").lower()] += 1
        if tag == "script" and values.get("src", "").startswith(("http://", "https://")):
            self.remote_dependencies.append(values["src"])
        if tag == "link" and values.get("href", "").startswith(("http://", "https://")):
            self.remote_dependencies.append(values["href"])


def audit(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    parser = InventoryParser()
    parser.feed(text)
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "lines": len(text.splitlines()),
        "tags": dict(sorted(parser.tags.items())),
        "tracked_classes": dict(sorted(parser.classes.items())),
        "ids": sorted(parser.ids),
        "feature_ids": sorted(parser.feature_ids),
        "input_types": dict(sorted(parser.input_types.items())),
        "script_functions": sorted(
            set(re.findall(r"\bfunction\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", text))
        ),
        "source_link_literals": len(re.findall(r"https://dev\.azure\.com/msazure/", text)),
        "remote_dependencies": parser.remote_dependencies,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory reusable HTML interaction surfaces.")
    parser.add_argument("html", nargs="+")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = {"documents": [audit(Path(item).expanduser().resolve()) for item in args.html]}
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
