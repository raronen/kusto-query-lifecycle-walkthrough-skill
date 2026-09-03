from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from model_contract import (
    ModelError,
    STAGES,
    query_slug,
    validate_cluster_uri,
    validate_complete_model,
)
from render_walkthrough import render


HEAD = "a" * 40
QUERY = (ROOT / "tests" / "fixtures" / "synthetic-query.kql").read_text(encoding="utf-8")


def source_link(label: str, source_path: str = "/synthetic/Component.cs", line: int = 10) -> dict:
    query = urlencode(
        {
            "path": source_path,
            "version": f"GC{HEAD}",
            "line": line,
            "lineEnd": line + 3,
            "lineStartColumn": 1,
            "lineEndColumn": 1,
        }
    )
    return {
        "label": label,
        "url": (
            "https://dev.azure.com/msazure/One/_git/"
            f"Azure-Kusto-Service?{query}"
        ),
        "path": source_path,
        "start_line": line,
        "end_line": line + 3,
        "commit": HEAD,
    }


def action(
    action_id: str,
    *,
    kind: str = "OBSERVED",
    before: str = "input",
    after: str = "output",
    optimizer: bool = False,
) -> dict:
    value = {
        "id": action_id,
        "title": action_id.replace("-", " ").title(),
        "description": f"Synthetic description for {action_id}.",
        "evidence_kind": kind,
        "before": before,
        "after": after,
        "source_links": [source_link(f"{action_id} implementation")],
    }
    if optimizer:
        value.update(
            {
                "traversal": ["root", "filter", "source"],
                "predicate": "The synthetic tree contains a filter above a source.",
                "applicability": "The supplied synthetic query contains a where operator.",
                "optimization": "Reduces rows before synthetic projection.",
            }
        )
    return value


def complete_model() -> dict:
    cluster = "https://example.kusto.windows.net"
    database = "Synthetic"
    stages = []
    for index, (stage_id, title, kind) in enumerate(STAGES, start=1):
        stage = {
            "id": stage_id,
            "order": index,
            "title": title,
            "kind": kind,
            "summary": f"Synthetic query-specific summary for {title}.",
            "evidence_kind": "OBSERVED",
            "no_op_explanation": "",
            "source_links": [source_link(f"{title} source", line=10 + index)],
            "actions": [],
        }
        if kind == "standard":
            stage["actions"] = [action(f"{stage_id}-action")]
        elif kind == "optimizer":
            evidence_kind = "SCHEDULED_NO_OP" if stage_id == "partial-queries" else "TRANSFORMED"
            before = "same tree" if evidence_kind == "SCHEDULED_NO_OP" else "tree before"
            after = before if evidence_kind == "SCHEDULED_NO_OP" else "tree after"
            stage["evidence_kind"] = evidence_kind
            stage["no_op_explanation"] = (
                "The scheduler visited the synthetic filter, but its required partition "
                "shape is absent, so the tree remains unchanged."
                if evidence_kind == "SCHEDULED_NO_OP"
                else ""
            )
            stage["actions"] = [
                action(
                    f"{stage_id}-pass",
                    kind=evidence_kind,
                    before=before,
                    after=after,
                    optimizer=True,
                )
            ]
        elif kind == "physical":
            child = {
                "operator_id": "op-2",
                "name": "Synthetic source",
                "details": "Reads synthetic fixture rows.",
                "source_links": [source_link("Synthetic source operator", line=80)],
                "children": [],
            }
            stage["physical_plan"] = {
                "complete": True,
                "operator_count": 2,
                "root": {
                    "operator_id": "op-1",
                    "name": "Synthetic filter",
                    "details": "Filters the synthetic severity field.",
                    "source_links": [source_link("Synthetic filter operator", line=70)],
                    "children": [child],
                },
            }
        elif kind == "serialization":
            stage["boundaries"] = [action("managed-native-boundary")]
        elif kind == "execute":
            stage["timeline"] = [
                {
                    "id": "request-next-batch",
                    "title": "Request next synthetic batch",
                    "user_event": "The user advances the execution timeline.",
                    "description": "A conceptual pull requests the next synthetic batch.",
                    "call_stack": [
                        {
                            "language": "Managed",
                            "frame": "SyntheticCoordinator.Pull",
                            "source_links": [source_link("Managed pull frame", line=90)],
                        },
                        {
                            "language": "C++",
                            "frame": "SyntheticOperator::Next",
                            "source_links": [source_link("Native next frame", line=100)],
                        },
                    ],
                    "heap_zones": [
                        {
                            "zone": "Synthetic query lifetime",
                            "language": "Managed",
                            "state": "owned",
                            "details": "The coordinator owns the synthetic lifetime token.",
                            "evidence_basis": "The linked synthetic type holds the token.",
                            "source_links": [source_link("Lifetime owner", line=110)],
                        }
                    ],
                    "components": [
                        {
                            "name": "Synthetic filter runtime",
                            "evidence_ref": "op-1",
                            "role": "Evaluates the synthetic predicate.",
                            "pull_direction": "Coordinator to filter to source.",
                            "data_direction": "Source to filter to coordinator.",
                            "ownership_now": "The coordinator owns the current batch.",
                            "next_breakpoint": "Before the synthetic predicate callback.",
                            "failure": "Predicate failure terminates this synthetic event.",
                            "cancellation": "The synthetic lifetime token is observed before pull.",
                            "lifetime": "Released after the batch leaves the coordinator.",
                            "source_links": [source_link("Runtime component", line=120)],
                        }
                    ],
                    "source_links": [source_link("Timeline event", line=130)],
                }
            ]
        stages.append(stage)

    return {
        "schema_version": "1.0",
        "model_state": "COMPLETE",
        "evidence_mode": "EVIDENCE",
        "estimate_reason": "",
        "query": {
            "text": QUERY,
            "cluster_uri": cluster,
            "database": database,
            "title": "Synthetic Kusto lifecycle walkthrough",
            "slug": query_slug(QUERY, cluster, database),
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
        "stages": stages,
    }


def create_source_workspace(parent: Path) -> tuple[Path, str]:
    workspace = parent / "Azure-Kusto-Service"
    workspace.mkdir()
    commands = (
        ["git", "init", "-q", str(workspace)],
        ["git", "-C", str(workspace), "config", "user.email", "synthetic@example.invalid"],
        ["git", "-C", str(workspace), "config", "user.name", "Synthetic Fixture"],
    )
    for command in commands:
        subprocess.run(command, check=True, capture_output=True, text=True)
    synthetic_source = workspace / "synthetic"
    synthetic_source.mkdir()
    source_file = synthetic_source / "Component.cs"
    source_file.write_text(
        "".join(f"// synthetic line {line}\n" for line in range(1, 201)),
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(workspace), "add", "synthetic/Component.cs"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(workspace), "commit", "-q", "-m", "Synthetic fixture"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "remote",
            "add",
            "origin",
            "https://dev.azure.com/msazure/One/_git/Azure-Kusto-Service",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    head = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return workspace, head


def retarget_model(model: dict, head: str) -> dict:
    model = copy.deepcopy(model)
    model["source"]["workspace_head"] = head

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if {"url", "path", "start_line", "end_line", "commit"} <= value.keys():
                value["commit"] = head
                value["url"] = (
                    "https://dev.azure.com/msazure/One/_git/Azure-Kusto-Service?"
                    + urlencode(
                        {
                            "path": value["path"],
                            "version": f"GC{head}",
                            "line": value["start_line"],
                            "lineEnd": value["end_line"],
                            "lineStartColumn": 1,
                            "lineEndColumn": 1,
                        }
                    )
                )
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(model)
    return model


class ContractTests(unittest.TestCase):
    def test_cluster_uri_accepts_https_and_loopback_http(self) -> None:
        accepted = (
            "https://example.kusto.windows.net",
            "HTTPS://EXAMPLE.KUSTO.WINDOWS.NET:443/path",
            "http://localhost:8080",
            "HTTP://LOCALHOST:8080/path?x=1",
            "http://127.0.0.1",
            "http://127.42.0.9:9000",
            "http://[::1]",
            "http://[::1]:8080/path",
        )
        for uri in accepted:
            with self.subTest(uri=uri):
                validate_cluster_uri(uri)

    def test_cluster_uri_rejects_non_loopback_http_and_other_schemes(self) -> None:
        rejected = (
            "http://example.kusto.windows.net",
            "http://localhost.example.com",
            "http://localhost.evil",
            "http://localhost@evil.example",
            "http://evil@localhost",
            "http://127.0.0.1@evil.example",
            "http://128.0.0.1",
            "http://[::2]",
            "ftp://localhost",
            "file://localhost/path",
            "localhost:8080",
            "https:///missing-host",
        )
        for uri in rejected:
            with self.subTest(uri=uri):
                with self.assertRaises(ModelError):
                    validate_cluster_uri(uri)

    def test_complete_model_applies_cluster_uri_contract(self) -> None:
        model = complete_model()
        model["query"]["cluster_uri"] = "http://127.42.0.9:8080"
        model["query"]["slug"] = query_slug(
            model["query"]["text"],
            model["query"]["cluster_uri"],
            model["query"]["database"],
        )
        validate_complete_model(model)

        model["query"]["cluster_uri"] = "http://remote.example"
        model["query"]["slug"] = query_slug(
            model["query"]["text"],
            model["query"]["cluster_uri"],
            model["query"]["database"],
        )
        with self.assertRaisesRegex(ModelError, "loopback"):
            validate_complete_model(model)

    def test_complete_synthetic_model_validates(self) -> None:
        validate_complete_model(complete_model())

    def test_requires_exact_ten_phase_order(self) -> None:
        model = complete_model()
        model["stages"][0], model["stages"][1] = model["stages"][1], model["stages"][0]
        with self.assertRaisesRegex(ModelError, "lifecycle order"):
            validate_complete_model(model)

    def test_no_op_requires_precise_explanation(self) -> None:
        model = complete_model()
        model["stages"][5]["no_op_explanation"] = ""
        with self.assertRaisesRegex(ModelError, "must not be empty"):
            validate_complete_model(model)

    def test_transformation_requires_changed_before_after(self) -> None:
        model = complete_model()
        optimizer = model["stages"][4]["actions"][0]
        optimizer["after"] = optimizer["before"]
        with self.assertRaisesRegex(ModelError, "before and after are identical"):
            validate_complete_model(model)

    def test_source_links_are_absolute_line_specific_and_pinned(self) -> None:
        model = complete_model()
        model["stages"][0]["source_links"][0]["url"] = (
            "https://dev.azure.com/msazure/One/_git/Azure-Kusto-Service"
            "?path=/synthetic/Component.cs&version=GBmain"
        )
        with self.assertRaisesRegex(ModelError, "pinned"):
            validate_complete_model(model)

    def test_source_links_reject_lookalike_repository_routes(self) -> None:
        model = complete_model()
        link = model["stages"][0]["source_links"][0]
        link["url"] = link["url"].replace(
            "/_git/Azure-Kusto-Service", "/_git/Other/Azure-Kusto-Service"
        )
        with self.assertRaisesRegex(ModelError, "canonical"):
            validate_complete_model(model)

    def test_source_links_still_require_https(self) -> None:
        model = complete_model()
        link = model["stages"][0]["source_links"][0]
        link["url"] = link["url"].replace("https://", "http://", 1)
        with self.assertRaisesRegex(ModelError, "Azure DevOps HTTPS"):
            validate_complete_model(model)

    def test_physical_tree_must_match_plan_operator_count(self) -> None:
        model = complete_model()
        model["stages"][7]["physical_plan"]["operator_count"] = 1
        with self.assertRaisesRegex(ModelError, "operator counts"):
            validate_complete_model(model)

    def test_execute_components_must_reference_present_operator_or_boundary(self) -> None:
        model = complete_model()
        model["stages"][9]["timeline"][0]["components"][0]["evidence_ref"] = "absent-op"
        with self.assertRaisesRegex(ModelError, "absent from this walkthrough"):
            validate_complete_model(model)

    def test_unexpected_fields_are_rejected_before_embedding(self) -> None:
        model = complete_model()
        model["unexpected_secret"] = "must not reach HTML"
        with self.assertRaisesRegex(ModelError, "unsupported fields"):
            validate_complete_model(model)

    def test_optimizer_stage_must_match_action_outcome(self) -> None:
        model = complete_model()
        model["stages"][4]["evidence_kind"] = "SCHEDULED_NO_OP"
        model["stages"][4]["no_op_explanation"] = "Contradictory fixture."
        with self.assertRaisesRegex(ModelError, "contradicts"):
            validate_complete_model(model)

    def test_estimated_mode_is_visible_and_cannot_claim_complete_plan(self) -> None:
        model = complete_model()
        model["evidence_mode"] = "ESTIMATED"
        model["estimate_reason"] = "Synthetic plan tooling was unavailable."
        model["plan"]["digest_sha256"] = ""
        for stage in model["stages"]:
            if stage["no_op_explanation"]:
                stage["evidence_kind"] = "NO_OP"
                stage["actions"] = []
            else:
                stage["evidence_kind"] = "ESTIMATED"
                for item in stage["actions"]:
                    item["evidence_kind"] = "ESTIMATED"
            for item in stage.get("boundaries", []):
                item["evidence_kind"] = "ESTIMATED"
        model["stages"][7]["physical_plan"]["complete"] = False
        validate_complete_model(model)


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_parent = tempfile.TemporaryDirectory()
        cls.source_workspace, cls.source_head = create_source_workspace(
            Path(cls.source_parent.name)
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.source_parent.cleanup()

    def render_html(self, model: dict | None = None) -> str:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "walkthrough.html"
            adjusted = retarget_model(model or complete_model(), self.source_head)
            render(adjusted, output, self.source_workspace)
            return output.read_text(encoding="utf-8")

    def test_html_has_title_h1_charset_and_evidence_meta(self) -> None:
        text = self.render_html()
        self.assertIn("<title>Synthetic Kusto lifecycle walkthrough</title>", text)
        self.assertIn("<h1>Synthetic Kusto lifecycle walkthrough</h1>", text)
        self.assertRegex(text, r'<meta charset="utf-8">')
        self.assertIn('name="walkthrough-evidence-mode" content="EVIDENCE"', text)

    def test_html_has_no_remote_runtime_dependencies(self) -> None:
        text = self.render_html()
        self.assertNotRegex(text, r"<script[^>]+src=")
        self.assertNotRegex(text, r"<link[^>]+rel=[\"']stylesheet")
        self.assertNotIn("@import", text)
        self.assertNotRegex(text, r"url\(\s*[\"']?https?://")

    def test_renderer_escapes_title_and_embedded_model(self) -> None:
        model = complete_model()
        dangerous = '</script><img src=x onerror="alert(1)">'
        model["query"]["text"] = dangerous
        model["query"]["title"] = "<Unsafe & title>"
        model["query"]["slug"] = query_slug(
            dangerous, model["query"]["cluster_uri"], model["query"]["database"]
        )
        text = self.render_html(model)
        self.assertIn("<title>&lt;Unsafe &amp; title&gt;</title>", text)
        self.assertNotIn("<img src=x", text)
        self.assertNotIn("</script><img", text)
        self.assertIn("\\u003c/script\\u003e", text)

    def test_contains_all_ten_phases_and_no_op_explanation(self) -> None:
        text = self.render_html()
        for _, title, _ in STAGES:
            self.assertIn(f'"title":"{title}"', text)
        self.assertIn("The scheduler visited the synthetic filter", text)

    def test_execute_components_render_below_stack_and_heap(self) -> None:
        text = self.render_html()
        stack = text.index('id = "conceptual-call-stack"')
        heap = text.index('id = "heap-lifetime-zones"')
        components = text.index('id = "runtime-components"')
        self.assertLess(stack, components)
        self.assertLess(heap, components)
        self.assertIn("Runtime components below stack and heap", text)

    def test_renderer_rejects_stale_workspace_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ModelError, "stale"):
                render(complete_model(), Path(directory) / "walkthrough.html", self.source_workspace)

    def test_renderer_rejects_nonexistent_source_line_target(self) -> None:
        model = retarget_model(complete_model(), self.source_head)
        model["stages"][0]["source_links"][0]["path"] = "/synthetic/Missing.cs"
        model["stages"][0]["source_links"][0]["url"] = (
            "https://dev.azure.com/msazure/One/_git/Azure-Kusto-Service?"
            + urlencode(
                {
                    "path": "/synthetic/Missing.cs",
                    "version": f"GC{self.source_head}",
                    "line": 11,
                    "lineEnd": 14,
                    "lineStartColumn": 1,
                    "lineEndColumn": 1,
                }
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ModelError, "does not exist at source workspace HEAD"):
                render(model, Path(directory) / "walkthrough.html", self.source_workspace)

    def test_renderer_rejects_untracked_source_file(self) -> None:
        untracked = self.source_workspace / "synthetic" / "Untracked.cs"
        untracked.write_text("// untracked\n" * 40, encoding="utf-8")
        model = retarget_model(complete_model(), self.source_head)
        link = model["stages"][0]["source_links"][0]
        link["path"] = "/synthetic/Untracked.cs"
        link["url"] = (
            "https://dev.azure.com/msazure/One/_git/Azure-Kusto-Service?"
            + urlencode(
                {
                    "path": link["path"],
                    "version": f"GC{self.source_head}",
                    "line": link["start_line"],
                    "lineEnd": link["end_line"],
                    "lineStartColumn": 1,
                    "lineEndColumn": 1,
                }
            )
        )
        try:
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ModelError, "does not exist at source workspace HEAD"):
                    render(model, Path(directory) / "walkthrough.html", self.source_workspace)
        finally:
            untracked.unlink()

    def test_renderer_rejects_lookalike_source_origin(self) -> None:
        subprocess.run(
            [
                "git",
                "-C",
                str(self.source_workspace),
                "remote",
                "set-url",
                "origin",
                "https://evil.example/dev.azure.com/msazure/One/_git/Azure-Kusto-Service",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        try:
            model = retarget_model(complete_model(), self.source_head)
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ModelError, "origin is not"):
                    render(model, Path(directory) / "walkthrough.html", self.source_workspace)
        finally:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.source_workspace),
                    "remote",
                    "set-url",
                    "origin",
                    "https://dev.azure.com/msazure/One/_git/Azure-Kusto-Service",
                ],
                check=True,
                capture_output=True,
                text=True,
            )


class ScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_parent = tempfile.TemporaryDirectory()
        cls.source_workspace, cls.source_head = create_source_workspace(
            Path(cls.source_parent.name)
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.source_parent.cleanup()

    def test_scaffolder_creates_non_executing_draft_with_ten_phases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "draft.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "scaffold_model.py"),
                    "--query-file",
                    str(ROOT / "tests" / "fixtures" / "synthetic-query.kql"),
                    "--cluster-uri",
                    "https://example.kusto.windows.net",
                    "--database",
                    "Synthetic",
                    "--source-workspace",
                    str(self.source_workspace),
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            response = json.loads(result.stdout)
            draft = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(response["state"], "DRAFT")
            self.assertEqual(len(draft["stages"]), 10)
            self.assertIs(draft["plan"]["non_executing"], True)
            self.assertEqual(draft["query"]["text"], QUERY)
            self.assertEqual(draft["source"]["workspace_head"], self.source_head)

    def test_scaffolder_accepts_localhost_http(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "draft.json"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "scaffold_model.py"),
                    "--query-file",
                    str(ROOT / "tests" / "fixtures" / "synthetic-query.kql"),
                    "--cluster-uri",
                    "http://localhost:8080",
                    "--database",
                    "Synthetic",
                    "--source-workspace",
                    str(self.source_workspace),
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            draft = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(draft["query"]["cluster_uri"], "http://localhost:8080")

    def test_scaffolder_rejects_remote_http(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "scaffold_model.py"),
                    "--query-file",
                    str(ROOT / "tests" / "fixtures" / "synthetic-query.kql"),
                    "--cluster-uri",
                    "http://example.kusto.windows.net",
                    "--database",
                    "Synthetic",
                    "--source-workspace",
                    str(self.source_workspace),
                    "--output",
                    str(Path(directory) / "draft.json"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("loopback", result.stderr)

    def test_packager_builds_deterministic_skill_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.skill"
            second = Path(directory) / "second.skill"
            for target in (first, second):
                subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPTS / "package_skill.py"),
                        "--output",
                        str(target),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
                self.assertIn("SKILL.md", names)
                self.assertNotIn("README.md", names)
                self.assertNotIn("CHANGELOG.md", names)

    def test_publish_wrapper_requires_exact_companion_success(self) -> None:
        text = (SCRIPTS / "Publish-Walkthrough.ps1").read_text(encoding="utf-8")
        self.assertIn("$companionOk -isnot [bool] -or -not $companionOk", text)
        self.assertIn("@('Favorites bar', 'Imported')", text)
        self.assertNotIn("$OutputRoot", text)

    def test_schema_is_strict_and_requires_execution_fields(self) -> None:
        schema = json.loads(
            (ROOT / "references" / "evidence-model.schema.json").read_text(encoding="utf-8")
        )
        self.assertIs(schema["additionalProperties"], False)
        component_required = schema["$defs"]["component"]["required"]
        for field in (
            "evidence_ref",
            "pull_direction",
            "data_direction",
            "ownership_now",
            "next_breakpoint",
            "failure",
            "cancellation",
            "lifetime",
        ):
            self.assertIn(field, component_required)

    def test_schema_cluster_uri_patterns_cover_only_https_or_loopback_http(self) -> None:
        schema = json.loads(
            (ROOT / "references" / "evidence-model.schema.json").read_text(encoding="utf-8")
        )
        alternatives = schema["properties"]["query"]["properties"]["cluster_uri"]["anyOf"]

        def accepted(uri: str) -> bool:
            return any(re.search(item["pattern"], uri) is not None for item in alternatives)

        for uri in (
            "https://example.kusto.windows.net",
            "http://localhost:8080",
            "http://127.0.0.1",
            "http://127.42.0.9",
            "http://[::1]:8080",
        ):
            with self.subTest(uri=uri):
                self.assertTrue(accepted(uri))
        for uri in (
            "http://example.kusto.windows.net",
            "http://localhost.evil",
            "http://localhost@evil",
            "http://evil@localhost",
            "http://128.0.0.1",
            "ftp://localhost",
        ):
            with self.subTest(uri=uri):
                self.assertFalse(accepted(uri))


if __name__ == "__main__":
    unittest.main()
