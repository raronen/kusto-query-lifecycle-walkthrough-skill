from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]

from fixture_factory import rich_model
from browser_smoke import find_edge, run_smoke
from model_contract import ModelError
import render_walkthrough
from render_walkthrough import render
from spec_compliance import (
    AUDITORS,
    EXPECTED_ACCEPTANCE_ITEMS,
    EXPECTED_SPEC_SHA256,
    MANIFEST_PATH,
    SPEC_PATH,
    audit_rendered_html,
    build_manifest,
    parse_acceptance_items,
    validate_manifest,
)
from test_skill import create_source_workspace, retarget_model


class ManifestCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_spec_digest_and_all_acceptance_items_are_exactly_covered(self) -> None:
        raw_spec = SPEC_PATH.read_bytes()
        self.assertEqual(len(raw_spec), 153001)
        self.assertEqual(len(raw_spec.decode("utf-8").splitlines()), 2775)
        parsed = parse_acceptance_items()
        self.assertEqual(EXPECTED_ACCEPTANCE_ITEMS, 93)
        self.assertEqual(len(parsed), 93)
        self.assertEqual(self.manifest["spec_sha256"], EXPECTED_SPEC_SHA256)
        self.assertEqual(self.manifest["acceptance_item_count"], 93)
        self.assertEqual(self.manifest["automated_count"], 93)
        self.assertEqual(self.manifest["manual_count"], 0)
        self.assertEqual(
            sum(1 for item in self.manifest["items"] if item["current_behavior"]),
            25,
        )
        validate_manifest(self.manifest)

        parsed_pairs = {(item.stable_id, item.normalized_hash) for item in parsed}
        manifest_pairs = {
            (item["id"], item["normalized_sha256"]) for item in self.manifest["items"]
        }
        self.assertEqual(manifest_pairs, parsed_pairs)
        self.assertEqual(len({item["id"] for item in self.manifest["items"]}), 93)

    def test_manifest_regeneration_is_deterministic(self) -> None:
        self.assertEqual(build_manifest(), self.manifest)

    def test_every_item_names_an_implemented_automated_auditor(self) -> None:
        for item in self.manifest["items"]:
            with self.subTest(item=item["id"]):
                verification = item["verification"]
                self.assertIn(verification["auditor"], AUDITORS)
                self.assertEqual(
                    verification["assertion"], f"verify-{item['id'].lower()}"
                )
                self.assertIn(
                    verification["kind"], {"static", "browser", "browser-geometry"}
                )
                expected_test = (
                    "tests/test_spec_compliance.py"
                    if verification["kind"] == "static"
                    else "tests/browser_smoke.py"
                )
                self.assertEqual(verification["test"], expected_test)

    def test_manifest_rejects_duplicates_missing_orphans_and_hash_drift(self) -> None:
        mutations = []
        duplicate = copy.deepcopy(self.manifest)
        duplicate["items"].append(copy.deepcopy(duplicate["items"][0]))
        mutations.append(duplicate)
        missing = copy.deepcopy(self.manifest)
        missing["items"].pop()
        mutations.append(missing)
        orphan = copy.deepcopy(self.manifest)
        orphan["items"][0]["id"] = "AC-ORPHANED"
        mutations.append(orphan)
        drift = copy.deepcopy(self.manifest)
        drift["items"][0]["normalized_sha256"] = "0" * 64
        mutations.append(drift)

        for index, manifest in enumerate(mutations):
            with self.subTest(mutation=index):
                with self.assertRaises(ModelError):
                    validate_manifest(manifest)

    def test_spec_parser_rejects_unreviewed_wording_drift(self) -> None:
        original = SPEC_PATH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp:
            changed = Path(temp) / "changed-spec.md"
            changed.write_text(
                original.replace(
                    "Single self-contained HTML file",
                    "One self-contained HTML file",
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ModelError, "digest changed"):
                parse_acceptance_items(changed)


class GeneratedArtifactComplianceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_parent = tempfile.TemporaryDirectory()
        source_workspace, source_head = create_source_workspace(Path(cls.source_parent.name))
        cls.source_workspace = source_workspace
        cls.source_head = source_head
        cls.output_parent = tempfile.TemporaryDirectory()
        output = Path(cls.output_parent.name) / "walkthrough.html"
        render(retarget_model(rich_model(), source_head), output, source_workspace)
        cls.output = output
        cls.rendered = output.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.output_parent.cleanup()
        cls.source_parent.cleanup()

    def test_complete_artifact_passes_all_93_requirements(self) -> None:
        result = audit_rendered_html(self.rendered)
        self.assertEqual(
            result,
            {
                "ok": True,
                "requirements": 93,
                "automated": 93,
                "manual": 0,
                "sections": 12,
                "model_substeps": 45,
                "runner_substeps": 41,
                "runner_omissions": 4,
            },
        )

    def test_all_browser_and_geometry_requirements(self) -> None:
        edge = find_edge()
        if edge is None:
            self.skipTest("Microsoft Edge is required for browser compliance verification.")
        result = run_smoke(self.output, edge)
        self.assertEqual(len(result["visited"]), 45)
        self.assertEqual(len(result["executionStates"]), 6)
        self.assertEqual(result["resources"], [])

    def test_failed_compliance_audit_never_publishes_partial_html(self) -> None:
        output = Path(self.output_parent.name) / "must-not-exist.html"
        original = render_walkthrough.audit_rendered_html
        render_walkthrough.audit_rendered_html = lambda _html: (_ for _ in ()).throw(
            ModelError("forced compliance failure")
        )
        try:
            with self.assertRaisesRegex(ModelError, "forced compliance failure"):
                render(
                    retarget_model(rich_model(), self.source_head),
                    output,
                    self.source_workspace,
                )
        finally:
            render_walkthrough.audit_rendered_html = original
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix(".html.tmp").exists())

    def test_representative_breakage_in_every_acceptance_category_is_rejected(self) -> None:
        mutations = {
            "file-bootstrap": (
                "<title>Kusto Query Lifecycle: Two-Level Interactive Walkthrough</title>",
                "<title>Broken</title>",
            ),
            "stage-level": ('id="previous-stage"', 'id="broken-previous-stage"'),
            "substep-level": ('id="step-slider"', 'id="broken-step-slider"'),
            "runner-engines": ("compiler-lab", "compiler-system-broken"),
            "gating": (
                "button.disabled=index!==next",
                "button.disabled=index===next",
            ),
            "traversal": ("}, 850);", "}, 851);"),
            "network-beacon": ("position: fixed", "position: absolute"),
            "source-links": ("noopener noreferrer", "noopener"),
            "keyboard-accessibility": ("ArrowLeft", "LeftArrowBroken"),
            "layout-responsive-print": (
                "@media (max-width: 520px)",
                "@media (max-width: 519px)",
            ),
            "persistence-safety": (
                '"use strict";',
                '"use strict";\n    localStorage.setItem("broken", "1");',
            ),
            "data-integrity": ("var(--text)", "var(--broken-text)"),
        }
        for category, (old, new) in mutations.items():
            with self.subTest(category=category):
                self.assertIn(old, self.rendered)
                broken = self.rendered.replace(old, new)
                with self.assertRaises(ModelError):
                    audit_rendered_html(broken)


if __name__ == "__main__":
    unittest.main()
