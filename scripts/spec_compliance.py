from __future__ import annotations

import argparse
import hashlib
import html as html_module
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from canonical_spec import CANONICAL_SUBSTEPS, NETWORK_OVERRIDES, RUNNERLESS_KEYS
from model_contract import ModelError, validate_complete_model


ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "references" / "query-lifecycle-two-level-walkthrough.spec.md"
MANIFEST_PATH = ROOT / "references" / "spec-compliance-manifest.json"
EXPECTED_SPEC_SHA256 = "63b9cf2ad7f8c8e0169e6300f6c82df4e5e2957472de6f4d54492833c7a73206"
EXPECTED_ACCEPTANCE_ITEMS = 93

SECTION_SURFACES = {
    "20.1": ["assets/walkthrough-template.html", "scripts/render_walkthrough.py"],
    "20.2": ["scripts/canonical_spec.py", "assets/walkthrough-template.html"],
    "20.3": ["scripts/canonical_spec.py", "scripts/model_contract.py", "references/evidence-model.schema.json"],
    "20.4": ["scripts/canonical_spec.py", "assets/walkthrough-template.html"],
    "20.5": ["assets/walkthrough-template.html", "tests/browser_smoke.py"],
    "20.6": ["assets/walkthrough-template.html", "tests/browser_smoke.py"],
    "20.7": ["scripts/canonical_spec.py", "assets/walkthrough-template.html"],
    "20.8": ["scripts/model_contract.py", "assets/walkthrough-template.html"],
    "20.9": ["assets/walkthrough-template.html", "tests/browser_smoke.py"],
    "20.10": ["assets/walkthrough-template.html", "tests/browser_smoke.py"],
    "20.11": ["assets/walkthrough-template.html", "tests/browser_smoke.py"],
    "20.12": ["scripts/canonical_spec.py", "scripts/model_contract.py", "assets/walkthrough-template.html"],
}
SECTION_VERIFICATION = {
    "20.1": "audit_file_bootstrap",
    "20.2": "audit_stage_level",
    "20.3": "audit_substep_level",
    "20.4": "audit_runner_engines",
    "20.5": "audit_gating",
    "20.6": "audit_traversal",
    "20.7": "audit_network_beacon",
    "20.8": "audit_source_links",
    "20.9": "audit_keyboard_accessibility",
    "20.10": "audit_layout_responsive_print",
    "20.11": "audit_persistence_safety",
    "20.12": "audit_data_integrity",
}
GEOMETRY_SECTIONS = {"20.7", "20.10"}


@dataclass(frozen=True)
class AcceptanceItem:
    section: str
    heading: str
    start_line: int
    end_line: int
    wording: str
    normalized_hash: str
    stable_id: str
    current_behavior: bool


def _normalized_wording(lines: list[str]) -> str:
    normalized = " ".join(line.strip() for line in lines)
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFC", normalized)).strip()
    return normalized


def parse_acceptance_items(spec_path: Path = SPEC_PATH) -> list[AcceptanceItem]:
    raw = spec_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SPEC_SHA256:
        raise ModelError(
            f"Authoritative specification digest changed: expected {EXPECTED_SPEC_SHA256}, got {digest}."
        )
    lines = raw.decode("utf-8").splitlines()
    section: tuple[str, str] | None = None
    pending: dict[str, Any] | None = None
    parsed: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        heading = re.match(r"^### (20\.\d+) (.+)$", line)
        if heading:
            if pending:
                parsed.append(pending)
                pending = None
            section = (heading.group(1), heading.group(2))
            continue
        if section and line.startswith("- [ ] "):
            if pending:
                parsed.append(pending)
            pending = {
                "section": section[0],
                "heading": section[1],
                "start_line": line_number,
                "end_line": line_number,
                "parts": [line[6:]],
            }
            continue
        if pending and line.startswith("      "):
            pending["parts"].append(line)
            pending["end_line"] = line_number
            continue
        if pending and (line.startswith("### ") or line == "---"):
            parsed.append(pending)
            pending = None
    if pending:
        parsed.append(pending)

    items: list[AcceptanceItem] = []
    used_ids: set[str] = set()
    for entry in parsed:
        wording = _normalized_wording(entry["parts"])
        digest = hashlib.sha256(wording.encode("utf-8")).hexdigest()
        prefix_length = 16
        stable_id = f"AC-{digest[:prefix_length].upper()}"
        while stable_id in used_ids:
            prefix_length += 2
            stable_id = f"AC-{digest[:prefix_length].upper()}"
        used_ids.add(stable_id)
        items.append(
            AcceptanceItem(
                section=entry["section"],
                heading=entry["heading"],
                start_line=entry["start_line"],
                end_line=entry["end_line"],
                wording=wording,
                normalized_hash=digest,
                stable_id=stable_id,
                current_behavior="**[C]**" in wording,
            )
        )
    if len(items) != EXPECTED_ACCEPTANCE_ITEMS:
        raise ModelError(
            f"Authoritative specification must contain {EXPECTED_ACCEPTANCE_ITEMS} acceptance items; "
            f"found {len(items)}."
        )
    return items


def build_manifest(spec_path: Path = SPEC_PATH) -> dict[str, Any]:
    items = parse_acceptance_items(spec_path)
    return {
        "schema_version": "1.0",
        "spec_path": "references/query-lifecycle-two-level-walkthrough.spec.md",
        "spec_sha256": EXPECTED_SPEC_SHA256,
        "acceptance_item_count": EXPECTED_ACCEPTANCE_ITEMS,
        "automated_count": EXPECTED_ACCEPTANCE_ITEMS,
        "manual_count": 0,
        "workflow_extensions": [
            {
                "id": "WE-PHYSICAL-QUERYPLAN-RECOVERY",
                "scope": "pre-render evidence acquisition",
                "reason": (
                    "Require a user-assisted recovery attempt before ESTIMATED fallback when "
                    "automatic evidence lacks a complete physical QueryPlan."
                ),
                "implementation": [
                    "scripts/plan_recovery.py",
                    "scripts/model_contract.py",
                    "references/evidence-collection.md",
                ],
                "canonical_spec_impact": "none",
            }
        ],
        "parameterizations": [
            {
                "item_id": "AC-A2326BC5E437D8D5",
                "reason": "The reusable skill must pin Azure DevOps links to the authorized local workspace current HEAD, not the canonical example commit.",
                "verification": "validate_complete_model and audit_source_links verify the dynamic commit.",
            },
            {
                "item_id": "AC-D56D410B5B6FF37C",
                "reason": "The 45 precise link targets remain position-distinct but their paths and lines are query-specific.",
                "verification": "audit_source_links verifies one distinct current-HEAD link per canonical substep.",
            },
            {
                "item_id": "AC-E1C807335EEB0B74",
                "reason": "S4.4 retains the canonical duplicate method-path behavior while its exact line is resolved from current source.",
                "verification": "audit_source_links verifies a current-HEAD S4.4 source link.",
            },
            {
                "item_id": "AC-6FFCBFC759F3545E",
                "reason": "The five-of-22 transformation result is canonical example data; reusable runs preserve the 22-position lab but derive transformation versus scheduled-no-op outcomes from query evidence.",
                "verification": "validate_complete_model verifies every pass outcome and its before/after evidence; the rich fixture reproduces the canonical five-of-22 state.",
            },
            {
                "item_id": "AC-2670B83728DD0691",
                "reason": "The six-node explorer and its interaction contract are fixed, while NodeIds, node labels, fields, and byte ranges are query-specific evidence rather than copied canonical plan data.",
                "verification": "audit_runner_engines and browser smoke verify the six-node/three-view explorer; model validation verifies byte ranges.",
            },
            {
                "item_id": "AC-8401760312A9A392",
                "reason": "The four canonical heap zones and selected-event fold are fixed; heap object ids, labels, and details are query-specific.",
                "verification": "audit_runner_engines and browser smoke verify zone order, folding, and status transitions.",
            },
        ],
        "items": [
            {
                "id": item.stable_id,
                "section": item.section,
                "heading": item.heading,
                "start_line": item.start_line,
                "end_line": item.end_line,
                "wording": item.wording,
                "normalized_sha256": item.normalized_hash,
                "normative": True,
                "current_behavior": item.current_behavior,
                "applicability": "always",
                "implementation_surfaces": SECTION_SURFACES[item.section],
                "verification": {
                    "assertion": f"verify-{item.stable_id.lower()}",
                    "kind": "browser-geometry"
                    if item.section in GEOMETRY_SECTIONS
                    else "browser"
                    if item.section in {"20.1", "20.2", "20.3", "20.4", "20.5", "20.6", "20.8", "20.9", "20.11"}
                    else "static",
                    "auditor": SECTION_VERIFICATION[item.section],
                    "test": (
                        "tests/browser_smoke.py"
                        if item.section
                        in {
                            "20.1",
                            "20.2",
                            "20.3",
                            "20.4",
                            "20.5",
                            "20.6",
                            "20.7",
                            "20.8",
                            "20.9",
                            "20.10",
                            "20.11",
                        }
                        else "tests/test_spec_compliance.py"
                    ),
                },
            }
            for item in items
        ],
    }


def validate_manifest(manifest: dict[str, Any], spec_path: Path = SPEC_PATH) -> None:
    parsed = parse_acceptance_items(spec_path)
    entries = manifest.get("items")
    if not isinstance(entries, list):
        raise ModelError("Compliance manifest items must be an array.")
    expected = {item.stable_id: item for item in parsed}
    actual: dict[str, dict[str, Any]] = {}
    assertion_ids: set[str] = set()
    for entry in entries:
        item_id = entry.get("id")
        if not isinstance(item_id, str) or item_id in actual:
            raise ModelError("Compliance manifest contains a missing or duplicate item id.")
        actual[item_id] = entry
    missing = sorted(set(expected) - set(actual))
    orphaned = sorted(set(actual) - set(expected))
    if missing or orphaned:
        raise ModelError(f"Compliance manifest coverage mismatch; missing={missing}, orphaned={orphaned}.")
    for item_id, source in expected.items():
        entry = actual[item_id]
        if entry.get("normalized_sha256") != source.normalized_hash:
            raise ModelError(f"Compliance manifest wording hash drifted for {item_id}.")
        if entry.get("wording") != source.wording:
            raise ModelError(f"Compliance manifest wording drifted for {item_id}.")
        if entry.get("applicability") != "always":
            raise ModelError(f"Compliance manifest item {item_id} is not marked always applicable.")
        verification = entry.get("verification")
        if (
            not isinstance(verification, dict)
            or not verification.get("auditor")
            or not verification.get("test")
            or not verification.get("assertion")
        ):
            raise ModelError(f"Compliance manifest item {item_id} lacks an automated verification.")
        kind = verification.get("kind")
        if kind not in {"static", "browser", "browser-geometry"}:
            raise ModelError(f"Compliance manifest item {item_id} has an invalid verification kind.")
        expected_test = (
            "tests/test_spec_compliance.py"
            if kind == "static"
            else "tests/browser_smoke.py"
        )
        if verification["test"] != expected_test:
            raise ModelError(
                f"Compliance manifest item {item_id} points to the wrong verification suite."
            )
        expected_assertion = f"verify-{item_id.lower()}"
        if verification["assertion"] != expected_assertion:
            raise ModelError(
                f"Compliance manifest item {item_id} has a non-canonical assertion id."
            )
        if verification["assertion"] in assertion_ids:
            raise ModelError(
                f"Compliance manifest assertion {verification['assertion']} is duplicated."
            )
        assertion_ids.add(verification["assertion"])
    if manifest.get("manual_count") != 0 or manifest.get("automated_count") != len(parsed):
        raise ModelError("Compliance manifest coverage totals are inconsistent.")
    parameterizations = manifest.get("parameterizations")
    if not isinstance(parameterizations, list):
        raise ModelError("Compliance manifest parameterizations must be an array.")
    extensions = manifest.get("workflow_extensions")
    if not isinstance(extensions, list) or not any(
        extension.get("id") == "WE-PHYSICAL-QUERYPLAN-RECOVERY"
        and extension.get("canonical_spec_impact") == "none"
        for extension in extensions
        if isinstance(extension, dict)
    ):
        raise ModelError("Compliance manifest lacks the physical QueryPlan recovery extension.")
    parameterized_ids: set[str] = set()
    for entry in parameterizations:
        if not isinstance(entry, dict):
            raise ModelError("Compliance manifest contains an invalid parameterization.")
        item_id = entry.get("item_id")
        if item_id not in actual or item_id in parameterized_ids:
            raise ModelError(
                "Compliance manifest parameterization is orphaned or duplicated."
            )
        if not entry.get("reason") or not entry.get("verification"):
            raise ModelError(
                f"Compliance manifest parameterization {item_id} is undocumented."
            )
        parameterized_ids.add(item_id)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ModelError(message)


def audit_model(model: dict[str, Any]) -> None:
    validate_complete_model(model)
    _require(
        [len(stage["substeps"]) for stage in model["stages"]]
        == [len(stage) for stage in CANONICAL_SUBSTEPS],
        "Canonical substep counts are not preserved.",
    )
    precise_urls: list[str] = []
    for stage_index, (stage, expected_stage) in enumerate(
        zip(model["stages"], CANONICAL_SUBSTEPS, strict=True)
    ):
        for substep_index, (substep, expected) in enumerate(
            zip(stage["substeps"], expected_stage, strict=True)
        ):
            location = f"stages[{stage_index}].substeps[{substep_index}]"
            _require(substep["id"] == expected.key, f"{location} has a non-canonical key.")
            _require(substep["title"] == expected.title, f"{location} has a non-canonical title.")
            runner = substep.get("runner")
            if expected.runner_type is None:
                _require(runner is None, f"{location} must omit its runner.")
            else:
                _require(isinstance(runner, dict), f"{location} must include its runner.")
                _require(runner["type"] == expected.runner_type, f"{location} has the wrong runner.")
                _require(
                    len(runner["actions"]) == expected.item_count,
                    f"{location} has the wrong action/pass/event count.",
                )
            _require(substep["source_links"], f"{location} lacks a precise source link.")
            precise_urls.append(substep["source_links"][0]["url"])
    _require(len(precise_urls) == 45, "The model must expose 45 precise substep links.")
    _require(len(set(precise_urls)) == 45, "The 45 precise substep links must be distinct.")
    _require(
        {
            substep["id"]
            for stage in model["stages"]
            for substep in stage["substeps"]
            if "runner" not in substep
        }
        == RUNNERLESS_KEYS,
        "The four canonical runner omissions are not exact.",
    )


def _extract_model(rendered_html: str) -> dict[str, Any]:
    match = re.search(
        r'<script type="application/json" id="walkthrough-data">(.*?)</script>',
        rendered_html,
        flags=re.DOTALL,
    )
    if not match:
        raise ModelError("Rendered HTML lacks the embedded walkthrough model.")
    return json.loads(html_module.unescape(match.group(1)))


def audit_file_bootstrap(rendered_html: str, model: dict[str, Any]) -> None:
    _require('<html lang="en">' in rendered_html, "Document language is missing.")
    _require(
        "<title>Kusto Query Lifecycle: Two-Level Interactive Walkthrough</title>" in rendered_html,
        "Canonical document title is missing.",
    )
    _require('"use strict";' in rendered_html, "Strict JavaScript mode is missing.")
    _require(
        "initializePassTable();\n    render();" in rendered_html,
        "Canonical bootstrap calls are missing or reordered.",
    )
    forbidden = (
        "<script src=",
        "<link rel=",
        "@import",
        "fetch(",
        "XMLHttpRequest",
        "WebSocket",
        "import(",
        "eval(",
        "document.cookie",
    )
    for token in forbidden:
        _require(token not in rendered_html, f"Forbidden external/runtime dependency found: {token}")
    _require("classList.add(\"pass-row\")" in rendered_html, "Pass-table row wiring is missing.")
    for token in (
        'document.querySelector(".step-detail").before(document.querySelector(".pass-lab"))',
        "row.dataset.passIndex=i",
        "if(row.cells.length===3)row.insertCell()",
        'if(event.target.closest("a"))return',
    ):
        _require(token in rendered_html, f"Canonical bootstrap wiring is missing: {token}")


def audit_stage_level(rendered_html: str, model: dict[str, Any]) -> None:
    for element_id in ("stage-strip", "journey-progress", "previous-stage", "next-stage"):
        _require(f'id="{element_id}"' in rendered_html, f"Missing stage control #{element_id}.")
    _require(len(model["stages"]) == 10, "Exactly ten stages are required.")
    _require("visitedStages: new Set([0])" in rendered_html, "Initial visited-stage behavior is missing.")
    _require("state.visitedStages.add(state.stage)" in rendered_html, "Visited-stage tracking is missing.")
    for token in (
        'el("button",`stage-button${i===state.stage?" selected":""}${state.visitedStages.has(i)?" visited":""}`)',
        'byId("journey-progress").textContent=`Stage ${state.stage+1} of ${model.stages.length}`',
        'byId("previous-stage").disabled=state.stage===0',
        'byId("next-stage").disabled=state.stage===model.stages.length-1',
        "stopTraversal();stopBoundaryPlay();state.stage=i;state.substep=0;resetLabs();",
        "state.traversal=traversalFocuses[i][0]??0",
    ):
        _require(token in rendered_html, f"Canonical stage behavior is missing: {token}")


def audit_substep_level(rendered_html: str, model: dict[str, Any]) -> None:
    audit_model(model)
    for element_id in ("substep-strip", "previous-step", "step-slider", "next-step", "step-action"):
        _require(f'id="{element_id}"' in rendered_html, f"Missing substep control #{element_id}.")
    _require(
        "window.requestAnimationFrame(() => window.scrollTo(scrollX, scrollY))" in rendered_html,
        "Two-phase substep scroll restoration is missing.",
    )
    for token in (
        "s.max=currentStage().substeps.length-1",
        "s.value=state.substep",
        'byId("step-action").textContent=x.summary',
        'el("span","walk",x.behavior)',
        'el("span","change",x.change_badge)',
        'if(x.runner)badges.append(el("span","runner-count",runnerCount(x)))',
    ):
        _require(token in rendered_html, f"Canonical substep behavior is missing: {token}")


def audit_runner_engines(rendered_html: str, model: dict[str, Any]) -> None:
    for lab_id in ("compiler-lab", "pass-lab", "physical-lab", "boundary-lab", "execution-lab"):
        _require(lab_id in rendered_html, f"Missing specialized runner {lab_id}.")
    _require(
        "physical-plan-deep-dive" in rendered_html and 'currentSubstep().id!=="7-4"' in rendered_html,
        "S8.5-only physical deep dive is missing.",
    )
    _require(
        'currentSubstep().id==="2-1"' in rendered_html and 'mappingMode.value!=="map"' in rendered_html,
        "S3.2 mapping gate is missing.",
    )
    for token in (
        "function renderBoundaryPlan(",
        "function renderBoundaryContext(",
        "function renderBoundaryHandoff(",
        "function executionMemoryAt(",
        "function renderExecutionComponents(",
        "function physicalDeepDive(",
        "Complete physical operator tree",
        "Logical → physical mappings",
        "Remote query metadata",
        "const ids=[0,1,2,3,4,6]",
        '["Plan","Context","Both"]',
        'fact("PLAN REBUILT?","No")',
    ):
        _require(token in rendered_html, f"Canonical runner engine is missing: {token}")


def audit_gating(rendered_html: str, model: dict[str, Any]) -> None:
    for token in (
        "button.disabled=index!==next",
        "state.compilerActionIndex===state.appliedCompilerActionThrough+1",
        "state.passIndex===state.appliedPassThrough+1",
        "state.physicalActionIndex===state.appliedPhysicalActionThrough+1",
        "Applied",
        "Math.max(state.appliedExecutionActionThrough,state.executionActionIndex)",
        "apply.disabled=false",
    ):
        _require(token in rendered_html, f"Canonical runner gating marker is missing: {token}")


def audit_traversal(rendered_html: str, model: dict[str, Any]) -> None:
    for token in (
        "}, 850);",
        "b.dataset.order=d.order.indexOf(id)+1",
        'current&&seen?" returning"',
        'visited?" visited"',
        "d.order.findIndex((x,n)=>n>=state.traversal&&x===id)",
    ):
        _require(token in rendered_html, f"Canonical traversal behavior is missing: {token}")


def audit_network_beacon(rendered_html: str, model: dict[str, Any]) -> None:
    _require("position: fixed" in rendered_html and "z-index: 100" in rendered_html, "Beacon geometry is wrong.")
    for key in NETWORK_OVERRIDES:
        _require(f'"{key}"' in rendered_html, f"Missing network override {key}.")
    _require(rendered_html.count('"active"') >= 1, "Active beacon state is missing.")
    _require(rendered_html.count('"imminent"') >= 1, "Imminent beacon state is missing.")


def audit_source_links(rendered_html: str, model: dict[str, Any]) -> None:
    audit_model(model)
    _require("noopener noreferrer" in rendered_html and '"noreferrer"' in rendered_html, "Source-link rel policies are missing.")
    _require("↗" in rendered_html and "–" in rendered_html, "Canonical source-link label format is missing.")
    for token in (
        'a.target="_blank"',
        'a.rel=boundary?"noreferrer":"noopener noreferrer"',
        ".sort((a,b)=>b.length-a.length)",
        "(?<![A-Za-z0-9_])(",
        'closest("a, button, code, pre, script, style")',
        "function renderBoundarySources(",
        "links.slice(0,7)",
    ):
        _require(token in rendered_html, f"Canonical source-link behavior is missing: {token}")


def audit_keyboard_accessibility(rendered_html: str, model: dict[str, Any]) -> None:
    for key in ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"):
        _require(key in rendered_html, f"Missing keyboard action {key}.")
    _require('event.target.matches("input, button")' in rendered_html, "Canonical keyboard focus defect is missing.")
    _require("outline: 3px solid var(--amber); outline-offset: 2px" in rendered_html, "Focus outline is wrong.")
    for forbidden in ("aria-selected", "aria-current", "tabindex=", "role="):
        _require(forbidden not in rendered_html, f"Forbidden canonical accessibility attribute found: {forbidden}")
    _require(rendered_html.count('aria-live="polite"') == 1, "Network beacon must be the only aria-live region.")
    for token in (
        'toggleCard(".stage-overview","stage-collapsed","stage-toggle","stage overview")',
        'toggleCard(".artifact-card","artifact-collapsed","artifact-toggle","artifact card")',
        'button.setAttribute("aria-expanded",String(!collapsed))',
    ):
        _require(token in rendered_html, f"Canonical collapse accessibility is missing: {token}")


def audit_layout_responsive_print(rendered_html: str, model: dict[str, Any]) -> None:
    for token in (
        "min(1580px, calc(100% - 26px))",
        "@media (max-width: 1180px)",
        "@media (max-width: 850px)",
        "@media (max-width: 820px)",
        "@media (max-width: 520px)",
        "button, input { display: none !important; }",
        ".center { display: grid; }",
        "grid-template-columns:minmax(300px,.72fr) minmax(560px,1.45fr) minmax(300px,.75fr)",
        "grid-template-columns:54px minmax(560px,1.45fr) 54px",
        ".boundary-workspace { min-width:780px;",
        ".substep-card { display:flex; flex:0 0 auto; flex-direction:column; width:155px;",
    ):
        _require(token in rendered_html, f"Canonical layout/print rule is missing: {token}")


def audit_persistence_safety(rendered_html: str, model: dict[str, Any]) -> None:
    for forbidden in (
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "document.cookie",
        "window.location.hash",
        "history.",
        "try {",
        "catch (",
    ):
        _require(forbidden not in rendered_html, f"Forbidden persistence/error surface found: {forbidden}")


def audit_data_integrity(rendered_html: str, model: dict[str, Any]) -> None:
    audit_model(model)
    _require(rendered_html.count('"PassManager.Execute":') == 2, "Canonical duplicate method target is missing.")
    _require(rendered_html.count("var(--text)") == 4, "--text must be referenced exactly four times.")
    _require(rendered_html.count("--surface:") == 1 and rendered_html.count("var(--surface)") == 0, "--surface contract is wrong.")


AUDITORS: dict[str, Callable[[str, dict[str, Any]], None]] = {
    name: globals()[name] for name in SECTION_VERIFICATION.values()
}


def audit_rendered_html(
    rendered_html: str,
    manifest: dict[str, Any] | None = None,
    *,
    spec_path: Path = SPEC_PATH,
) -> dict[str, Any]:
    manifest = manifest or json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    validate_manifest(manifest, spec_path)
    model = _extract_model(rendered_html)
    completed: set[str] = set()
    verified_assertions: set[str] = set()
    for entry in manifest["items"]:
        auditor = entry["verification"]["auditor"]
        if auditor not in completed:
            AUDITORS[auditor](rendered_html, model)
            completed.add(auditor)
        verified_assertions.add(entry["verification"]["assertion"])
    expected_assertions = {
        entry["verification"]["assertion"] for entry in manifest["items"]
    }
    _require(
        verified_assertions == expected_assertions
        and len(verified_assertions) == len(manifest["items"]),
        "Not every manifest assertion was executed.",
    )
    return {
        "ok": True,
        "requirements": len(manifest["items"]),
        "automated": manifest["automated_count"],
        "manual": manifest["manual_count"],
        "sections": len(completed),
        "model_substeps": sum(len(stage["substeps"]) for stage in model["stages"]),
        "runner_substeps": sum(
            1
            for stage in model["stages"]
            for substep in stage["substeps"]
            if "runner" in substep
        ),
        "runner_omissions": sum(
            1
            for stage in model["stages"]
            for substep in stage["substeps"]
            if "runner" not in substep
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or run the authoritative-spec compliance audit.")
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--html")
    args = parser.parse_args()
    try:
        if args.write_manifest:
            manifest = build_manifest()
            MANIFEST_PATH.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            print(json.dumps({"ok": True, "manifest": str(MANIFEST_PATH), "items": 93}))
            return 0
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        validate_manifest(manifest)
        if args.model:
            audit_model(json.loads(Path(args.model).read_text(encoding="utf-8")))
        result = (
            audit_rendered_html(Path(args.html).read_text(encoding="utf-8"), manifest)
            if args.html
            else {"ok": True, "requirements": 93, "automated": 93, "manual": 0}
        )
    except (ModelError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
