from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "walkthrough-template.html"
INVENTORY = ROOT / "references" / "feature-parity-inventory.json"


class StaticParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = TEMPLATE.read_text(encoding="utf-8")
        cls.inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))

    def test_template_declares_all_contract_feature_ids(self) -> None:
        for feature_id in self.inventory["required_feature_ids"]:
            with self.subTest(feature_id=feature_id):
                self.assertIn(f'"{feature_id}"', self.template)

    def test_inventory_covers_canonical_surface_families_and_previous_gaps(self) -> None:
        inventory = self.inventory["canonical_semantic_inventory"]
        self.assertEqual(len(inventory["runner_systems"]), 5)
        self.assertEqual(len(inventory["panel_families"]), 13)
        self.assertGreaterEqual(len(inventory["source_link_surfaces"]), 25)
        self.assertGreaterEqual(len(self.inventory["previous_sample_gaps"]), 10)

    def test_all_specialized_runner_renderers_exist(self) -> None:
        for function_name in (
            "renderCompiler",
            "renderPass",
            "renderPhysical",
            "renderBoundary",
            "renderExecute",
            "renderNoOp",
        ):
            with self.subTest(function_name=function_name):
                self.assertRegex(self.template, rf"function\s+{function_name}\s*\(")
        self.assertIn("runner.boundary.node_byte_ranges", self.template)
        self.assertNotIn("runner.boundary.node_ranges", self.template)

    def test_browser_smoke_visits_every_stage_and_substep(self) -> None:
        self.assertIn("model.stages.forEach((stage, stageIndex)", self.template)
        self.assertIn("stage.substeps.forEach((substep, substepIndex)", self.template)
        for lab_id in ("compiler-lab", "pass-lab", "physical-lab", "boundary-lab", "execute-lab"):
            with self.subTest(lab_id=lab_id):
                self.assertIn(f'"{lab_id}"', self.template)

    def test_global_controls_have_event_handlers(self) -> None:
        for control_id in (
            "stage-overview-toggle",
            "substep-prev",
            "substep-next",
            "substep-slider",
            "traversal-prev",
            "traversal-play",
            "traversal-slider",
            "traversal-next",
            "runner-reset",
            "runner-prev",
            "runner-next",
            "runner-apply",
            "runner-slider",
        ):
            with self.subTest(control_id=control_id):
                self.assertIn(f'byId("{control_id}").addEventListener', self.template)

    def test_template_javascript_has_valid_syntax(self) -> None:
        scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", self.template, re.DOTALL)
        self.assertGreaterEqual(len(scripts), 2)
        with tempfile.TemporaryDirectory() as directory:
            script_path = Path(directory) / "template.js"
            script_path.write_text(scripts[-1], encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(script_path)],
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_inventory_auditor_is_deterministic(self) -> None:
        command = [
            sys.executable,
            str(ROOT / "scripts" / "audit_html_features.py"),
            str(TEMPLATE),
        ]
        first = subprocess.run(command, check=True, capture_output=True, text=True).stdout
        second = subprocess.run(command, check=True, capture_output=True, text=True).stdout
        self.assertEqual(first, second)
        report = json.loads(first)["documents"][0]
        self.assertEqual(report["remote_dependencies"], [])
        self.assertGreaterEqual(report["tags"]["button"], 10)
        self.assertGreaterEqual(report["input_types"]["range"], 3)
        self.assertGreaterEqual(report["tags"]["details"], 1)

    def test_no_remote_runtime_dependencies(self) -> None:
        self.assertNotRegex(self.template, r"<script[^>]+src=")
        self.assertNotRegex(self.template, r"<link[^>]+rel=[\"']stylesheet")
        self.assertNotIn("@import", self.template)
        self.assertNotRegex(self.template, r"url\(\s*[\"']?https?://")


if __name__ == "__main__":
    unittest.main()
