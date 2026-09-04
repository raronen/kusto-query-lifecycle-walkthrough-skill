from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"
sys.path[:0] = [str(SCRIPTS), str(TESTS)]

from fixture_factory import QUERY, rich_model
from model_contract import (
    ModelError,
    RUNNER_TYPES,
    STAGES,
    query_slug,
    validate_cluster_uri,
    validate_complete_model,
)
from render_walkthrough import render


POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


def create_source_workspace(parent: Path) -> tuple[Path, str]:
    workspace = parent / "Azure-Kusto-Service"
    workspace.mkdir()
    for command in (
        ["git", "init", "-q", str(workspace)],
        ["git", "-C", str(workspace), "config", "user.email", "synthetic@example.invalid"],
        ["git", "-C", str(workspace), "config", "user.name", "Synthetic Fixture"],
    ):
        subprocess.run(command, check=True, capture_output=True, text=True)
    source = workspace / "synthetic"
    source.mkdir()
    (source / "Component.cs").write_text(
        "".join(f"// synthetic line {line}\n" for line in range(1, 241)),
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
    adjusted = copy.deepcopy(model)
    adjusted["source"]["workspace_head"] = head

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
                            "lineEnd": value["end_line"] + 1,
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

    visit(adjusted)
    return adjusted


class ContractTests(unittest.TestCase):
    def test_cluster_uri_accepts_https_and_loopback_http(self) -> None:
        for uri in (
            "https://example.kusto.windows.net",
            "HTTPS://EXAMPLE.KUSTO.WINDOWS.NET:443/path",
            "http://localhost:8080",
            "HTTP://LOCALHOST:8080/path?x=1",
            "http://127.0.0.1",
            "http://127.42.0.9:9000",
            "http://[::1]",
            "http://[::1]:8080/path",
        ):
            with self.subTest(uri=uri):
                validate_cluster_uri(uri)

    def test_cluster_uri_rejects_non_loopback_http_and_other_schemes(self) -> None:
        for uri in (
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
        ):
            with self.subTest(uri=uri), self.assertRaises(ModelError):
                validate_cluster_uri(uri)

    def test_complete_model_applies_cluster_uri_contract(self) -> None:
        model = rich_model()
        model["query"]["cluster_uri"] = "http://127.42.0.9:8080"
        model["query"]["slug"] = query_slug(
            model["query"]["text"], model["query"]["cluster_uri"], model["query"]["database"]
        )
        validate_complete_model(model)
        model["query"]["cluster_uri"] = "http://remote.example"
        model["query"]["slug"] = query_slug(
            model["query"]["text"], model["query"]["cluster_uri"], model["query"]["database"]
        )
        with self.assertRaisesRegex(ModelError, "loopback"):
            validate_complete_model(model)

    def test_rich_v2_model_validates(self) -> None:
        validate_complete_model(rich_model())

    def test_every_substep_has_phase_specific_runner_and_distinct_states(self) -> None:
        model = rich_model()
        expected = {stage_id: RUNNER_TYPES[stage_id] for stage_id, _, _ in STAGES}
        for stage in model["stages"]:
            self.assertGreaterEqual(len(stage["substeps"]), 1)
            for substep in stage["substeps"]:
                runner = substep["runner"]
                self.assertEqual(runner["type"], expected[stage["id"]])
                self.assertRegex(runner["title"], r"^Run the .+ yourself$")
                self.assertGreaterEqual(len(substep["traversal"]["snapshots"]), 2)
                self.assertGreaterEqual(len(runner["snapshots"]), 2)
                self.assertNotEqual(runner["snapshots"][0], runner["snapshots"][1])
                for experiment in runner["experiments"]:
                    options = {item["id"] for item in experiment["options"]}
                    results = {item["option_id"] for item in experiment["results"]}
                    self.assertGreaterEqual(len(options), 2)
                    self.assertEqual(options, results)

    def test_missing_runner_fails_validation(self) -> None:
        model = rich_model()
        del model["stages"][0]["substeps"][0]["runner"]
        with self.assertRaisesRegex(ModelError, "missing required fields: runner"):
            validate_complete_model(model)

    def test_wrong_runner_type_fails_validation(self) -> None:
        model = rich_model()
        model["stages"][0]["substeps"][0]["runner"]["type"] = "execute"
        with self.assertRaisesRegex(ModelError, "must be 'compiler'"):
            validate_complete_model(model)

    def test_no_op_requires_explanation_runner_gates_and_unchanged_artifacts(self) -> None:
        model = rich_model()
        partial = model["stages"][5]
        partial["no_op_explanation"] = ""
        with self.assertRaisesRegex(ModelError, "must not be empty"):
            validate_complete_model(model)
        partial["no_op_explanation"] = "Synthetic query-specific no-op."
        partial["substeps"][0]["runner"]["no_op"]["enabled"] = False
        with self.assertRaisesRegex(ModelError, "does not match"):
            validate_complete_model(model)

    def test_no_op_runner_actions_cannot_claim_transformations(self) -> None:
        model = rich_model()
        partial = model["stages"][5]
        action = partial["substeps"][0]["runner"]["actions"][0]
        action["evidence_kind"] = "TRANSFORMED"
        with self.assertRaisesRegex(ModelError, "must match its no-op outcome"):
            validate_complete_model(model)

        model = rich_model()
        syntax = model["stages"][0]
        syntax["evidence_kind"] = "NO_OP"
        syntax["no_op_explanation"] = "The supplied shape requires no syntax rewrite."
        substep = syntax["substeps"][0]
        substep["change_badge"] = "NO_OP"
        substep["artifact"]["after"] = substep["artifact"]["before"]
        runner = substep["runner"]
        runner["no_op"] = {
            "enabled": True,
            "gates": ["The parser gate found no rewrite."],
            "reasons": ["The syntax tree remains unchanged."],
        }
        for item in runner["actions"]:
            item["evidence_kind"] = "NO_OP"
            item["after"] = item["before"]
        for item in runner["compiler"]["before_actions"] + runner["compiler"]["after_actions"]:
            item["evidence_kind"] = "NO_OP"
            item["after"] = item["before"]
        runner["compiler"]["after_actions"][0]["evidence_kind"] = "TRANSFORMED"
        with self.assertRaisesRegex(ModelError, "contradicts its no-op outcome"):
            validate_complete_model(model)

    def test_every_runner_action_must_be_reachable(self) -> None:
        model = rich_model()
        runner = model["stages"][0]["substeps"][0]["runner"]
        for suffix in ("second", "unreachable"):
            runner["actions"].append(copy.deepcopy(runner["actions"][0]))
            runner["actions"][-1]["id"] = f"{suffix}-action"
        with self.assertRaisesRegex(ModelError, "every runner action reachable"):
            validate_complete_model(model)

    def test_transformation_requires_distinct_artifacts(self) -> None:
        model = rich_model()
        artifact = model["stages"][4]["substeps"][0]["artifact"]
        artifact["after"] = artifact["before"]
        with self.assertRaisesRegex(ModelError, "distinct before and after"):
            validate_complete_model(model)

    def test_source_links_are_absolute_line_specific_and_commit_pinned(self) -> None:
        model = rich_model()
        link = model["stages"][0]["source_links"][0]
        link["url"] = (
            "https://dev.azure.com/msazure/One/_git/Azure-Kusto-Service"
            "?path=/synthetic/Component.cs&version=GBmain"
        )
        with self.assertRaisesRegex(ModelError, "pinned"):
            validate_complete_model(model)
        model = rich_model()
        link = model["stages"][0]["source_links"][0]
        link["url"] = link["url"].replace(
            f"lineEnd={link['end_line'] + 1}", f"lineEnd={link['end_line']}"
        )
        with self.assertRaisesRegex(ModelError, "line parameters"):
            validate_complete_model(model)

    def test_source_links_reject_http_and_lookalike_routes(self) -> None:
        model = rich_model()
        link = model["stages"][0]["source_links"][0]
        link["url"] = link["url"].replace("https://", "http://", 1)
        with self.assertRaisesRegex(ModelError, "canonical Azure DevOps HTTPS route"):
            validate_complete_model(model)
        model = rich_model()
        link = model["stages"][0]["source_links"][0]
        link["url"] = link["url"].replace(
            "/_git/Azure-Kusto-Service", "/_git/Other/Azure-Kusto-Service"
        )
        with self.assertRaisesRegex(ModelError, "canonical"):
            validate_complete_model(model)

    def test_physical_tree_count_and_execute_references_are_enforced(self) -> None:
        model = rich_model()
        physical = model["stages"][7]["substeps"][0]["runner"]["physical"]["full_plan"]
        physical["operator_count"] = 1
        with self.assertRaisesRegex(ModelError, "operator counts"):
            validate_complete_model(model)
        model = rich_model()
        component = model["stages"][9]["substeps"][0]["runner"]["execute"]["components"][0]
        component["evidence_ref"] = "absent-op"
        with self.assertRaisesRegex(ModelError, "absent from this walkthrough"):
            validate_complete_model(model)

    def test_execute_stack_components_and_scenarios_are_strict(self) -> None:
        model = rich_model()
        execute = model["stages"][9]["substeps"][0]["runner"]["execute"]
        execute["call_stack"][0]["position"] = 1
        with self.assertRaisesRegex(ModelError, "top-first"):
            validate_complete_model(model)
        model = rich_model()
        execute = model["stages"][9]["substeps"][0]["runner"]["execute"]
        execute["scenarios"].pop()
        with self.assertRaisesRegex(ModelError, "cover failure, cancellation, memory, and lifetime"):
            validate_complete_model(model)

    def test_unexpected_fields_are_rejected(self) -> None:
        model = rich_model()
        model["unexpected_secret"] = "must not reach HTML"
        with self.assertRaisesRegex(ModelError, "unsupported fields"):
            validate_complete_model(model)


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_parent = tempfile.TemporaryDirectory()
        cls.source_workspace, cls.source_head = create_source_workspace(
            Path(cls.source_parent.name)
        )
        cls.model = retarget_model(rich_model(), cls.source_head)
        cls.output_parent = tempfile.TemporaryDirectory()
        cls.output = Path(cls.output_parent.name) / "walkthrough.html"
        render(cls.model, cls.output, cls.source_workspace)
        cls.text = cls.output.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.output_parent.cleanup()
        cls.source_parent.cleanup()

    def test_html_metadata_and_all_ten_phases(self) -> None:
        self.assertIn("<title>Synthetic Kusto lifecycle walkthrough</title>", self.text)
        self.assertIn("<h1>Synthetic Kusto lifecycle walkthrough</h1>", self.text)
        self.assertRegex(self.text, r'<meta charset="utf-8">')
        self.assertIn('name="walkthrough-evidence-mode" content="EVIDENCE"', self.text)
        for _, title, _ in STAGES:
            self.assertIn(f'"title":"{title}"', self.text)

    def test_html_has_no_remote_runtime_dependencies(self) -> None:
        self.assertNotRegex(self.text, r"<script[^>]+src=")
        self.assertNotRegex(self.text, r"<link[^>]+rel=[\"']stylesheet")
        self.assertNotIn("@import", self.text)
        self.assertNotRegex(self.text, r"url\(\s*[\"']?https?://")

    def test_renderer_escapes_title_and_embedded_model(self) -> None:
        model = copy.deepcopy(self.model)
        dangerous = '</script><img src=x onerror="alert(1)">'
        model["query"]["text"] = dangerous
        model["query"]["title"] = "<Unsafe & title>"
        model["query"]["slug"] = query_slug(
            dangerous, model["query"]["cluster_uri"], model["query"]["database"]
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "escaped.html"
            render(model, output, self.source_workspace)
            text = output.read_text(encoding="utf-8")
        self.assertIn("<title>&lt;Unsafe &amp; title&gt;</title>", text)
        self.assertNotIn("<img src=x", text)
        self.assertNotIn("</script><img", text)
        self.assertIn("\\u003c/script\\u003e", text)

    def test_every_specialized_lab_and_no_op_is_embedded(self) -> None:
        for runner_type in {"compiler", "pass", "physical", "boundary", "execute"}:
            self.assertIn(f'"type":"{runner_type}"', self.text)
        self.assertIn("The synthetic query has no partition boundary", self.text)
        self.assertIn('"enabled":true', self.text)

    def test_components_are_rendered_below_stack_and_heap(self) -> None:
        stack = self.text.index('id = "conceptual-call-stack"')
        heap = self.text.index('id = "heap-lifetime-zones"')
        components = self.text.index('id = "runtime-components"')
        self.assertLess(stack, components)
        self.assertLess(heap, components)
        self.assertIn("Runtime components below stack and heap", self.text)

    def test_renderer_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory) / "other.html"
            render(self.model, other, self.source_workspace)
            self.assertEqual(self.output.read_bytes(), other.read_bytes())

    def test_renderer_rejects_stale_workspace_head_and_missing_blob(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ModelError, "stale"):
                render(rich_model(), Path(directory) / "stale.html", self.source_workspace)
        model = copy.deepcopy(self.model)
        link = model["stages"][0]["source_links"][0]
        link["path"] = "/synthetic/Missing.cs"
        link["url"] = (
            "https://dev.azure.com/msazure/One/_git/Azure-Kusto-Service?"
            + urlencode(
                {
                    "path": link["path"],
                    "version": f"GC{self.source_head}",
                    "line": link["start_line"],
                    "lineEnd": link["end_line"] + 1,
                    "lineStartColumn": 1,
                    "lineEndColumn": 1,
                }
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ModelError, "does not exist at source workspace HEAD"):
                render(model, Path(directory) / "missing.html", self.source_workspace)


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

    def run_scaffolder(self, cluster_uri: str, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "scaffold_model.py"),
                "--query-file",
                str(ROOT / "tests" / "fixtures" / "synthetic-query.kql"),
                "--cluster-uri",
                cluster_uri,
                "--database",
                "Synthetic",
                "--source-workspace",
                str(self.source_workspace),
                "--output",
                str(output),
            ],
            capture_output=True,
            text=True,
        )

    def run_publish_wrapper(
        self,
        directory: Path,
        publisher_path: Path,
        publisher_timeout_seconds: int = 5,
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        if POWERSHELL is None:
            self.skipTest("PowerShell is unavailable")
        model_path = directory / "model.json"
        output_path = directory / "walkthrough.html"
        model_path.write_text(
            json.dumps(retarget_model(rich_model(), self.source_head)),
            encoding="utf-8",
        )

        def quote(value: Path) -> str:
            return "'" + str(value).replace("'", "''") + "'"

        wrapper = SCRIPTS / "Publish-Walkthrough.ps1"
        command = (
            f"& {{ & {quote(wrapper)} -ModelPath {quote(model_path)} "
            f"-SourceWorkspace {quote(self.source_workspace)} "
            f"-PublisherPath {quote(publisher_path)} -OutputPath {quote(output_path)} "
            f"-PublisherTimeoutSeconds {publisher_timeout_seconds} "
            "| ConvertTo-Json -Depth 10 -Compress }"
        )
        result = subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout) if result.returncode == 0 else {}
        return result, payload

    def test_scaffolder_creates_v2_draft_with_mandatory_runners(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "draft.json"
            result = self.run_scaffolder("https://example.kusto.windows.net", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            draft = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(draft["schema_version"], "2.0")
        self.assertEqual(draft["model_state"], "DRAFT")
        self.assertEqual(len(draft["stages"]), 10)
        self.assertIs(draft["plan"]["non_executing"], True)
        self.assertEqual(draft["query"]["text"], QUERY)
        self.assertEqual(draft["source"]["workspace_head"], self.source_head)
        for stage in draft["stages"]:
            self.assertGreaterEqual(len(stage["substeps"]), 1)
            self.assertEqual(stage["substeps"][0]["runner"]["type"], RUNNER_TYPES[stage["id"]])

    def test_scaffolder_accepts_localhost_and_rejects_remote_http(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "draft.json"
            accepted = self.run_scaffolder("http://localhost:8080", output)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["query"]["cluster_uri"],
                "http://localhost:8080",
            )
            rejected = self.run_scaffolder(
                "http://example.kusto.windows.net", Path(directory) / "rejected.json"
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("loopback", rejected.stderr)

    def test_packager_builds_deterministic_skill_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.skill"
            second = Path(directory) / "second.skill"
            for target in (first, second):
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS / "package_skill.py"), "--output", str(target)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
            self.assertIn("references/feature-parity-contract.md", names)
            self.assertIn("references/feature-parity-inventory.json", names)
            self.assertNotIn("README.md", names)
            self.assertNotIn("CHANGELOG.md", names)

    def test_publish_wrapper_is_noninteractive_and_has_no_companion_preflight(self) -> None:
        text = (SCRIPTS / "Publish-Walkthrough.ps1").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"(?i)Read-Host|PromptForChoice|ShouldContinue|preflight")
        self.assertLess(text.index("& python @arguments"), text.index("Test-Path -LiteralPath $PublisherPath"))
        self.assertLess(text.index("try {", text.index("$driverPath = $null")), text.index("Test-Path -LiteralPath $PublisherPath"))
        self.assertNotIn("Join-Path $env:USERPROFILE", text)
        self.assertLess(text.index("try {", text.index("$driverPath = $null")), text.index("GetFolderPath"))
        self.assertIn("catch {", text)
        self.assertNotIn("ReadToEnd", text)
        self.assertIn("StandardOutput.BaseStream.CopyToAsync([IO.Stream]::Null)", text)
        self.assertIn("StandardError.BaseStream.CopyToAsync([IO.Stream]::Null)", text)
        self.assertIn("$process.Kill($true)", text)
        self.assertIn("Ok = $true", text)
        self.assertIn("BookmarkStatus = $bookmarkStatus", text)
        self.assertIn("BookmarkError = $bookmarkError", text)
        self.assertIn("@('Favorites bar', 'Imported')", text)

    def test_publish_wrapper_succeeds_when_publisher_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, payload = self.run_publish_wrapper(root, root / "missing-publisher.ps1")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIs(payload["Ok"], True)
            self.assertEqual(payload["BookmarkStatus"], "skipped")
            self.assertIn("was not found", payload["BookmarkError"])
            self.assertTrue(Path(payload["HtmlPath"]).is_file())
            self.assertIsNone(payload["CompanionResult"])

    def test_publish_wrapper_preserves_html_when_publisher_throws(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            publisher = root / "failing-publisher.ps1"
            publisher.write_text("throw 'synthetic companion failure'\n", encoding="utf-8")
            result, payload = self.run_publish_wrapper(root, publisher)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIs(payload["Ok"], True)
            self.assertEqual(payload["BookmarkStatus"], "failed")
            self.assertIn("synthetic companion failure", payload["BookmarkError"])
            self.assertTrue(Path(payload["HtmlPath"]).is_file())

    def test_publish_wrapper_contains_publisher_exit_and_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exiting = root / "exiting-publisher.ps1"
            exiting.write_text("exit 7\n", encoding="utf-8")
            result, payload = self.run_publish_wrapper(root, exiting)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIs(payload["Ok"], True)
            self.assertEqual(payload["BookmarkStatus"], "failed")
            self.assertTrue(Path(payload["HtmlPath"]).is_file())

            hanging = root / "hanging-publisher.ps1"
            hanging.write_text("Start-Sleep -Seconds 30\n", encoding="utf-8")
            result, payload = self.run_publish_wrapper(
                root, hanging, publisher_timeout_seconds=1
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIs(payload["Ok"], True)
            self.assertEqual(payload["BookmarkStatus"], "failed")
            self.assertIn("timed out after 1 seconds", payload["BookmarkError"])
            self.assertTrue(Path(payload["HtmlPath"]).is_file())

    def test_publish_wrapper_requires_exact_true_only_for_published_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            false_publisher = root / "false-publisher.ps1"
            false_publisher.write_text(
                "[pscustomobject]@{ CompanionResult = [pscustomobject]@{ ok = 'true' } }\n",
                encoding="utf-8",
            )
            result, payload = self.run_publish_wrapper(root, false_publisher)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIs(payload["Ok"], True)
            self.assertEqual(payload["BookmarkStatus"], "failed")
            self.assertIn("exact boolean true", payload["BookmarkError"])

            true_publisher = root / "true-publisher.ps1"
            true_publisher.write_text(
                "[pscustomobject]@{ CompanionResult = [pscustomobject]@{ ok = $true } }\n",
                encoding="utf-8",
            )
            result, payload = self.run_publish_wrapper(root, true_publisher)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(payload["BookmarkStatus"], "published")
            self.assertIsNone(payload["BookmarkError"])

    def test_json_schema_enforces_v2_runner_and_experiment_contract(self) -> None:
        schema = json.loads(
            (ROOT / "references" / "evidence-model.schema.json").read_text(encoding="utf-8")
        )
        self.assertIs(schema["additionalProperties"], False)
        self.assertIn("runner", schema["$defs"]["substep"]["required"])
        experiment = schema["$defs"]["experiment"]["properties"]
        self.assertEqual(experiment["options"]["minItems"], 2)
        self.assertEqual(experiment["results"]["minItems"], 2)
        runner = schema["$defs"]["runner"]["properties"]
        self.assertEqual(runner["actions"]["minItems"], 1)
        self.assertEqual(runner["snapshots"]["minItems"], 2)
        self.assertEqual(runner["experiments"]["minItems"], 1)
        component_required = schema["$defs"]["executeComponent"]["required"]
        for field in (
            "evidence_ref",
            "state",
            "pull_direction",
            "data_direction",
            "ownership",
            "breakpoint",
        ):
            self.assertIn(field, component_required)

    def test_schema_cluster_uri_patterns_cover_only_https_or_loopback_http(self) -> None:
        schema = json.loads(
            (ROOT / "references" / "evidence-model.schema.json").read_text(encoding="utf-8")
        )
        alternatives = schema["$defs"]["query"]["properties"]["cluster_uri"]["anyOf"]

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
