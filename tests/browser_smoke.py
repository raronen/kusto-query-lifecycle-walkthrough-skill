from __future__ import annotations

import argparse
import subprocess
from html.parser import HTMLParser
from pathlib import Path


EDGE_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)


class SmokeResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.attributes: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "output" and values.get("id") == "browser-smoke-result":
            self.attributes = values


def find_edge() -> Path | None:
    return next((path for path in EDGE_CANDIDATES if path.is_file()), None)


def run_smoke(html_path: Path, edge_path: Path) -> str:
    uri = html_path.resolve().as_uri() + "#smoke"
    result = subprocess.run(
        [
            str(edge_path),
            "--headless",
            "--disable-gpu",
            "--disable-extensions",
            "--no-first-run",
            "--allow-file-access-from-files",
            "--dump-dom",
            uri,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=45,
    )
    if 'id="browser-smoke-result"' not in result.stdout:
        raise RuntimeError("Browser did not emit the interaction smoke result.")
    if "PASS: interactive state changed" not in result.stdout:
        raise RuntimeError("Browser interaction smoke did not observe a state transition.")
    parser = SmokeResultParser()
    parser.feed(result.stdout)
    if parser.attributes is None:
        raise RuntimeError("Browser smoke result could not be parsed.")
    visited = parser.attributes.get("data-visited", "").split(",")
    runner_types = {item.rsplit(":", 1)[-1] for item in visited if ":" in item}
    if len(visited) < 10 or runner_types != {"compiler", "pass", "physical", "boundary", "execute"}:
        raise RuntimeError("Browser smoke did not render every phase and specialized runner type.")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the generated walkthrough in Edge headless.")
    parser.add_argument("html")
    parser.add_argument("--edge")
    args = parser.parse_args()
    edge = Path(args.edge).resolve() if args.edge else find_edge()
    if edge is None:
        parser.error("Microsoft Edge was not found")
    output = run_smoke(Path(args.html), edge)
    print(f"PASS: {len(output)} bytes of executed DOM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
