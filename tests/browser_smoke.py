from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

import websocket


EDGE_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)


class DevTools:
    def __init__(self, url: str) -> None:
        self.socket = websocket.create_connection(url, timeout=10, origin="http://localhost")
        self.sequence = 0

    def close(self) -> None:
        self.socket.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.sequence += 1
        message_id = self.sequence
        self.socket.send(
            json.dumps({"id": message_id, "method": method, "params": params or {}})
        )
        while True:
            response = json.loads(self.socket.recv())
            if response.get("id") != message_id:
                continue
            if "error" in response:
                raise RuntimeError(f"DevTools {method} failed: {response['error']}")
            return response.get("result", {})

    def evaluate(self, expression: str) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            raise RuntimeError(
                details.get("exception", {}).get("description")
                or details.get("text", "Browser JavaScript evaluation failed.")
            )
        value = result.get("result", {})
        if value.get("subtype") == "error":
            raise RuntimeError(value.get("description", "Browser JavaScript evaluation failed."))
        return value.get("value")


def find_edge() -> Path | None:
    return next((path for path in EDGE_CANDIDATES if path.is_file()), None)


def _debug_target(port: int, page_url: str) -> str:
    endpoint = f"http://127.0.0.1:{port}/json/list"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(endpoint, timeout=1) as response:
                targets = json.load(response)
            page = next(
                target
                for target in targets
                if target.get("type") == "page" and target.get("url") == page_url
            )
            return page["webSocketDebuggerUrl"]
        except (OSError, StopIteration):
            time.sleep(0.1)
    raise RuntimeError("Edge DevTools endpoint did not become ready.")


def run_smoke(html_path: Path, edge_path: Path) -> dict[str, Any]:
    port = 9387
    page_url = html_path.resolve().as_uri()
    with tempfile.TemporaryDirectory(
        prefix="kusto-walkthrough-edge-", ignore_cleanup_errors=True
    ) as profile:
        process = subprocess.Popen(
            [
                str(edge_path),
                "--headless=new",
                "--disable-gpu",
                "--disable-extensions",
                "--no-first-run",
                "--allow-file-access-from-files",
                "--remote-allow-origins=*",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile}",
                page_url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            cdp = DevTools(_debug_target(port, page_url))
            try:
                cdp.call("Runtime.enable")
                cdp.call("Page.enable")
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if cdp.evaluate(
                        'document.readyState === "complete" && '
                        'Boolean(window.walkthroughApp)'
                    ):
                        break
                    time.sleep(0.05)
                result = cdp.evaluate(
                    """
                    (async () => {
                      const app = window.walkthroughApp;
                      const data = JSON.parse(document.getElementById("walkthrough-data").textContent);
                      const expected = {
                        compiler: "compiler-lab",
                        pass: "pass-lab",
                        physical: "physical-lab",
                        boundary: "boundary-lab",
                        execute: "execution-lab"
                      };
                      const labIds = Object.values(expected);
                      const omitted = new Set(["3-0", "3-3", "5-0", "5-1"]);
                      const visited = [];
                      const failures = [];
                      const ariaLabelChanges = new Set();
                      const ariaObserver = new MutationObserver(records => records.forEach(record =>
                        ariaLabelChanges.add(record.target.id)));
                      ariaObserver.observe(document.documentElement, {
                        subtree: true,
                        attributes: true,
                        attributeFilter: ["aria-label"]
                      });
                      const check = (condition, message) => { if (!condition) failures.push(message); };
                      const clickText = (root, text) => {
                        const button = [...root.querySelectorAll("button")]
                          .find(item => item.textContent.includes(text));
                        if (button) button.click();
                        return button;
                      };
                      const wait = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

                      check(document.querySelectorAll("#workspace > .stage-overview").length === 1,
                        "stage overview is not a workspace child");
                      check(document.querySelectorAll("#workspace > .artifact-card").length === 1,
                        "artifact card is not a workspace child");
                      check(document.querySelector(".center > .pass-lab + .step-detail"),
                        "pass lab was not relocated immediately before step detail");
                      check(document.querySelectorAll(".compiler-lab").length === 1 &&
                        document.querySelectorAll(".pass-lab").length === 1 &&
                        document.querySelectorAll(".physical-lab").length === 1 &&
                        document.querySelectorAll(".boundary-lab").length === 1 &&
                        document.querySelectorAll(".execution-lab").length === 1,
                        "five authored labs are not distinct singletons");
                      check([...document.querySelectorAll("#stage-strip .name")]
                        .map(node => node.textContent).join("|") ===
                        "Syntax|Semantic|Relop|Preparation|Initial optimize|Partial queries|" +
                        "Final optimize|Physical plan|Serialize|Execute",
                        "stage ordering or labels are not canonical");
                      check(document.getElementById("final-relop-content").textContent.includes(
                        '"LogicalId": "logical-op-filter"'),
                        "actual final RelopTree content is not visibly rendered");
                      check(document.getElementById("final-relop-digest").textContent.includes(
                        data.plan.final_relop.digest_sha256),
                        "final RelopTree digest is not visibly rendered");
                      check(document.getElementById("optimizer-trace-status").textContent ===
                        data.optimizer_trace.status,
                        "optimizer trace status is not visibly rendered");
                      check(document.getElementById("optimizer-acquisition").textContent.includes(
                        data.optimizer_trace.acquisition.method) &&
                        document.getElementById("optimizer-acquisition").textContent.includes(
                          "Plan-only request; supplied query not executed"),
                        "optimizer trace acquisition and safety are not visibly rendered");

                      data.stages.forEach((stage, stageIndex) => {
                        app.selectStage(stageIndex);
                        stage.substeps.forEach((substep, substepIndex) => {
                          app.selectSubstep(substepIndex);
                          const visible = labIds.filter(id =>
                            document.getElementById(id).classList.contains("visible"));
                          const wanted = substep.runner ? expected[substep.runner.type] : null;
                          check(wanted ? visible.length === 1 && visible[0] === wanted : visible.length === 0,
                            `lab visibility ${substep.id}: ${visible.join(",")}`);
                          if (substep.runner?.type === "compiler") {
                            const kind = stageIndex === 0 ? "syntax" : stageIndex === 1 ? "semantic" : "relop";
                            check(document.getElementById("compiler-lab").classList.contains(kind),
                              `compiler kind ${substep.id}`);
                            check(document.getElementById("compiler-rail").children.length ===
                              substep.runner.actions.length, `compiler rail count ${substep.id}`);
                          }
                          if (substep.runner?.type === "pass") {
                            check(document.getElementById("pass-rail").children.length ===
                              substep.runner.actions.length, `pass rail count ${substep.id}`);
                          }
                          if (substep.runner?.type === "physical") {
                            check(document.getElementById("physical-rail").children.length ===
                              substep.runner.actions.length, `physical rail count ${substep.id}`);
                          }
                          if (substep.runner?.type === "boundary") {
                            check(document.getElementById("boundary-rail").children.length ===
                              substep.runner.actions.length, `boundary rail count ${substep.id}`);
                          }
                          if (substep.runner?.type === "execute") {
                            check(document.getElementById("execution-rail").children.length ===
                              substep.runner.actions.length, `execution rail count ${substep.id}`);
                          }
                          check(omitted.has(substep.id) === !substep.runner,
                            `runner omission ${substep.id}`);
                          check(Number(document.getElementById("step-slider").value) === substepIndex,
                            `slider binding ${substep.id}`);
                          check(document.querySelectorAll("#substep-strip .substep").length ===
                            stage.substeps.length, `substep rail count ${substep.id}`);
                          const methodAnchors = [...document.querySelectorAll("#call-path a")];
                          check(methodAnchors.length === substep.method_path.length,
                            `method path count ${substep.id}`);
                          substep.method_path.forEach((method, methodIndex) => {
                            const anchor = methodAnchors[methodIndex];
                            check(anchor?.textContent === `${method.name} ↗` &&
                              anchor?.href === method.source_links[0].url &&
                              anchor?.title.includes(method.source_links[0].path.split("/").pop()),
                              `method path source ${substep.id}:${method.name}`);
                          });
                          visited.push(`${substep.id}:${substep.runner?.type || "none"}`);
                        });
                      });

                      app.selectStage(2);
                      app.selectSubstep(2);
                      app.selectStage(-1);
                      app.selectStage(10);
                      check(app.snapshot().stage === 2 && app.snapshot().substep === 2,
                        "stage bounds changed selection");
                      app.selectStage(4);
                      check(app.snapshot().substep === 0 && app.snapshot().runner === 0,
                        "stage change did not reset substep and runner");
                      check(app.snapshot().visited.includes(2) && app.snapshot().visited.includes(4),
                        "visited-stage memory missing");
                      window.scrollTo(0, 500);
                      const scrollBefore = window.scrollY;
                      app.selectSubstep(1);
                      await new Promise(resolve => requestAnimationFrame(resolve));
                      check(window.scrollY === scrollBefore, "substep selection changed page scroll");
                      const stepSlider = document.getElementById("step-slider");
                      stepSlider.value = 2;
                      stepSlider.dispatchEvent(new Event("input", {bubbles: true}));
                      check(app.snapshot().substep === 2, "substep slider is not bidirectional");

                      app.selectStage(0);
                      app.selectSubstep(0);
                      app.selectCompilerAction(1);
                      app.applyCompilerAction();
                      check(app.snapshot().compilerApplied === -1 &&
                        document.getElementById("compiler-apply").disabled,
                        "compiler strict-next gate failed");
                      app.selectCompilerAction(0);
                      app.applyCompilerAction();
                      app.selectCompilerAction(1);
                      const compilerBeforeApply = document.getElementById("compiler-before").textContent +
                        document.getElementById("compiler-after").textContent;
                      app.applyCompilerAction();
                      check(app.snapshot().compilerApplied === 1, "compiler application failed");
                      check(compilerBeforeApply === document.getElementById("compiler-before").textContent +
                        document.getElementById("compiler-after").textContent,
                        "compiler apply changed displayed state");
                      document.getElementById("compiler-reset").click();
                      check(app.snapshot().compilerApplied === -1, "compiler reset failed");
                      app.selectStage(2);
                      app.selectSubstep(1);
                      check(document.getElementById("compiler-mapping-grid").children.length === 0,
                        "S3.2 mapping appeared before the map option");
                      clickText(document.getElementById("compiler-options"), "Semantic/CSL → Relop map");
                      check(document.getElementById("compiler-mapping-grid").children.length > 0,
                        "S3.2 mapping did not appear for the map option");

                      app.selectStage(4);
                      app.selectSubstep(0);
                      check(document.querySelectorAll("#optimization-rows > .pass-row").length === 22,
                        "pass table does not bind 22 canonical passes");
                      app.selectPass(1);
                      app.applySelectedPass();
                      check(app.snapshot().passApplied === -1, "pass strict-next gate failed");
                      app.selectPass(0);
                      const passBeforeApply = document.getElementById("pass-before").textContent +
                        document.getElementById("pass-after").textContent;
                      app.applySelectedPass();
                      check(app.snapshot().passApplied === 0, "pass application failed");
                      check(passBeforeApply === document.getElementById("pass-before").textContent +
                        document.getElementById("pass-after").textContent,
                        "pass apply changed displayed state");
                      document.getElementById("optimization-rows").rows[1].click();
                      check(app.snapshot().runner === 1, "pass table row did not select pass");
                      check([...document.querySelectorAll("#optimization-rows tr")]
                        .every(row => row.cells.length === 4 && row.dataset.passIndex !== ""),
                        "pass table row binding is incomplete");
                      check(document.querySelectorAll("#optimization-rows .pass-mark.changes").length === 5,
                        "S5.1 pass change marks are wrong");

                      app.selectStage(7);
                      app.selectSubstep(0);
                      app.selectPhysicalAction(1);
                      app.applyPhysicalAction();
                      check(app.snapshot().physicalApplied === -1, "physical strict-next gate failed");
                      app.selectPhysicalAction(0);
                      const physicalBeforeApply = document.getElementById("physical-before").textContent +
                        document.getElementById("physical-after").textContent;
                      app.applyPhysicalAction();
                      check(app.snapshot().physicalApplied === 0, "physical application failed");
                      check(physicalBeforeApply === document.getElementById("physical-before").textContent +
                        document.getElementById("physical-after").textContent,
                        "physical apply changed displayed state");
                      app.selectSubstep(4);
                      const deep = document.getElementById("physical-plan-deep-dive");
                      const deepText = document.getElementById("physical-deep-body").textContent;
                      check(!deep.hidden &&
                        deepText.includes("Complete physical operator tree") &&
                        deepText.includes("Logical → physical mappings") &&
                        deepText.includes("Input schema") &&
                        deepText.includes("Output schema") &&
                        deepText.includes("Execution eligibility") &&
                        deepText.includes("Rust eligibility") &&
                        deepText.includes("Target scope") &&
                        deepText.includes("Remote query metadata") &&
                        document.querySelectorAll("#physical-deep-body [data-operator-id]").length === 2,
                        "physical deep dive is incomplete");

                      app.selectStage(0);
                      app.selectSubstep(0);
                      app.setTraversal(999);
                      check(app.snapshot().traversal === 10, "traversal upper bound failed");
                      app.toggleTraversal();
                      await wait(900);
                      check(app.snapshot().traversal >= 1 && app.snapshot().traversalTimer,
                        "traversal play did not advance");
                      app.toggleTraversal();
                      check(!app.snapshot().traversalTimer, "traversal play did not pause");
                      app.selectStage(1);
                      app.selectSubstep(4);
                      check(app.snapshot().traversal === 17, "S2.5 focus did not clamp to 17");

                      document.getElementById("stage-toggle").click();
                      document.getElementById("artifact-toggle").click();
                      check(document.getElementById("workspace").classList.contains("stage-collapsed") &&
                        document.getElementById("workspace").classList.contains("artifact-collapsed"),
                        "independent collapse classes missing");
                      check(document.querySelector(".stage-overview").classList.contains("collapsed") &&
                        document.querySelector(".artifact-card").classList.contains("collapsed"),
                        "collapse state missing on cards");
                      check(document.getElementById("stage-toggle").getAttribute("aria-expanded") === "false" &&
                        document.getElementById("artifact-toggle").getAttribute("aria-expanded") === "false" &&
                        document.getElementById("stage-toggle").textContent === "+" &&
                        document.getElementById("artifact-toggle").textContent === "+" &&
                        document.getElementById("stage-toggle").title.startsWith("Expand") &&
                        document.getElementById("artifact-toggle").title.startsWith("Expand"),
                        "collapse controls are not synchronized");
                      document.getElementById("stage-toggle").click();
                      document.getElementById("artifact-toggle").click();

                      app.selectStage(8);
                      app.selectSubstep(0);
                      data.stages[8].substeps[0].runner.actions.forEach((action, index) => {
                        app.selectBoundaryAction(index);
                        check(document.querySelector("#boundary-lanes .active")?.dataset.lane === action.lane,
                          `boundary lane ${action.id}`);
                      });
                      app.selectBoundaryAction(0);
                      check([...document.querySelectorAll("#boundary-primary button")]
                        .filter(button => button.textContent.startsWith("NodeId")).map(button =>
                          button.textContent.trim()).join(",") ===
                        "NodeId 0,NodeId 1,NodeId 2,NodeId 3,NodeId 4,NodeId 6",
                        "boundary node ids are not canonical");
                      check(clickText(document.getElementById("boundary-primary"), "JSON") &&
                        document.getElementById("boundary-primary").textContent.includes("NodeId"),
                        "boundary JSON view failed");
                      check(clickText(document.getElementById("boundary-primary"), "UTF-8 bytes") &&
                        document.querySelector("#boundary-primary pre").textContent.includes("0000"),
                        "boundary bytes view failed");
                      document.getElementById("boundary-play").click();
                      await wait(1200);
                      check(app.snapshot().boundaryTimer && app.snapshot().runner === 1,
                        "boundary play did not advance at 1100ms");
                      document.getElementById("boundary-play").click();
                      app.selectSubstep(1);
                      const contextBefore = document.querySelector("#boundary-primary pre").textContent;
                      document.querySelector("#boundary-primary input").click();
                      check(document.querySelector("#boundary-primary pre").textContent !== contextBefore,
                        "boundary context toggle failed");
                      clickText(document.getElementById("boundary-secondary"), "Context");
                      check(document.getElementById("boundary-secondary").textContent.includes("Correct"),
                        "boundary context quiz failed");
                      app.selectSubstep(2);
                      check(document.querySelectorAll("#boundary-secondary table tbody tr").length > 0 &&
                        clickText(document.getElementById("boundary-secondary"), "Healthy handoff"),
                        "boundary handoff simulator failed");
                      const boundaryAnchors = [...document.querySelectorAll("#boundary-lab a")];
                      check(boundaryAnchors.length === 7 &&
                        boundaryAnchors.every(anchor => anchor.rel === "noreferrer" &&
                          anchor.target === "_blank" && Boolean(anchor.href)),
                        "boundary source-link count or rel policy is not canonical");

                      const executionStates = [];
                      app.selectStage(9);
                      data.stages[9].substeps.forEach((substep, index) => {
                        app.selectSubstep(index);
                        const actionCount = substep.runner.execute.action_timeline.length;
                        const scenarioCount = index < 3 ? 3 : 4;
                        const selectedIndex = Math.min(3, actionCount - 1);
                        const execute = substep.runner.execute;
                        const event = execute.action_timeline[selectedIndex];
                        app.selectExecutionAction(selectedIndex);
                        const executionBeforeApply =
                          document.getElementById("stack-list").textContent +
                          document.getElementById("heap-list").textContent;
                        app.applyExecutionAction();
                        const componentStates = [...document.querySelectorAll(
                          "#execution-components [data-component-state]")]
                          .map(node => node.dataset.componentState);
                        check(app.snapshot().executionApplied === selectedIndex,
                          `execution ungated apply ${substep.id}`);
                        check(executionBeforeApply ===
                          document.getElementById("stack-list").textContent +
                          document.getElementById("heap-list").textContent,
                          `execution apply changed runtime state ${substep.id}`);
                        check([...document.querySelectorAll("#heap-list .heap-zone")]
                          .map(zone => zone.dataset.zone).join(",") ===
                          "managed,borrowed,cpp,rust" &&
                          document.getElementById("stack-list").children.length > 0,
                          `execution memory/stack ${substep.id}`);
                        check([...document.querySelectorAll("#stack-list .stack-frame")]
                          .every((frame, frameIndex) =>
                            frame.dataset.frameKind === execute.call_stack[frameIndex].kind),
                          `execution frame kinds ${substep.id}`);
                        check(document.querySelector("#execution-lanes .active")?.dataset.language ===
                          event.lang, `execution language lane ${substep.id}`);
                        check(componentStates.length === substep.runner.execute.components.length &&
                          componentStates.includes("active") &&
                          componentStates.every(state => ["active", "waiting", "off"].includes(state)),
                          `execution components ${substep.id}`);
                        execute.components.forEach(component => {
                          const wanted = component.id === event.active ? "active" :
                            event.live.includes(component.id) ? "waiting" : "off";
                          check(document.querySelector(
                            `[data-component-id="${component.id}"]`)?.dataset.componentState === wanted,
                            `execution component state ${substep.id}:${component.id}`);
                        });
                        const folded = {};
                        ["managed", "borrowed", "cpp", "rust"].forEach(zone => folded[zone] = new Map());
                        execute.heap_zones.forEach(item => folded[item.zone].set(item.id, item.state));
                        execute.action_timeline.slice(0, selectedIndex + 1).forEach(item =>
                          item.memory.forEach(memory => folded[memory.zone].set(
                            memory.id,
                            memory.op === "add" ? "live" :
                              memory.op === "update" ? "mutated" : "released"
                          )));
                        Object.values(folded).forEach(zone => zone.forEach((status, id) => {
                          check(document.querySelector(
                            `[data-memory-id="${id}"]`)?.dataset.memoryState === status,
                            `execution memory fold ${substep.id}:${id}`);
                        }));
                        check(document.getElementById("scenario-buttons").children.length === scenarioCount,
                          `execution scenarios ${substep.id}`);
                        check([...document.getElementById("scenario-buttons").children]
                          .map(button => button.textContent).join(",") ===
                          execute.scenarios.map(scenario => scenario.type).join(","),
                          `execution scenario binding ${substep.id}`);
                        executionStates.push(substep.id);
                      });

                      const networkExpected = {
                        "1-0": ["possible", "May fetch"],
                        "1-2": ["possible", "May fetch"],
                        "5-2": ["possible", "Conditional"],
                        "7-3": ["none", "No HTTP"],
                        "8-2": ["none", "No external HTTP"],
                        "9-3": ["imminent", "HTTP imminent"],
                        "9-4": ["active", "HTTP active"],
                        "9-5": ["none", "HTTP response consumed"]
                      };
                      Object.entries(networkExpected).forEach(([key, value]) => {
                        const [stage, step] = key.split("-").map(Number);
                        app.selectStage(stage);
                        app.selectSubstep(step);
                        check(document.getElementById("network-beacon").dataset.state === value[0] &&
                          document.getElementById("network-state").textContent === value[1],
                          `network state ${key}`);
                      });
                      const exceptionalNetwork = [];
                      data.stages.forEach((stage, stageIndex) =>
                        stage.substeps.forEach((_substep, substepIndex) => {
                          app.selectStage(stageIndex);
                          app.selectSubstep(substepIndex);
                          const state = document.getElementById("network-beacon").dataset.state;
                          if (state === "active" || state === "imminent") {
                            exceptionalNetwork.push(`${stageIndex}-${substepIndex}:${state}`);
                          }
                        }));
                      check(exceptionalNetwork.join(",") === "9-3:imminent,9-4:active",
                        `active/imminent network positions ${exceptionalNetwork.join(",")}`);

                      const precise = data.stages.flatMap(stage =>
                        stage.substeps.map(substep => substep.source_links[0].url));
                      check(new Set(precise).size === 45, "45 precise source links are not distinct");
                      check([...document.querySelectorAll("a[href]")].every(anchor =>
                        anchor.target === "_blank"), "an outbound anchor does not target _blank");
                      check(document.querySelectorAll("[role], [tabindex], [aria-selected], [aria-current]").length === 0,
                        "forbidden accessibility attributes are present");
                      check(document.querySelectorAll("[aria-live]").length === 1 &&
                        document.querySelector("[aria-live]")?.id === "network-beacon",
                        "network beacon is not the only aria-live region");
                      await Promise.resolve();
                      ariaObserver.disconnect();
                      check([...ariaLabelChanges].join(",") === "pass-rail",
                        `unexpected runtime aria-label changes: ${[...ariaLabelChanges].join(",")}`);

                      app.selectStage(0);
                      document.body.dispatchEvent(new KeyboardEvent("keydown", {key: "ArrowDown", bubbles: true}));
                      check(app.snapshot().stage === 1, "ArrowDown stage navigation failed");
                      document.body.dispatchEvent(new KeyboardEvent("keydown", {key: "ArrowRight", bubbles: true}));
                      check(app.snapshot().substep === 1, "ArrowRight substep navigation failed");
                      const held = app.snapshot().substep;
                      document.getElementById("step-slider").dispatchEvent(
                        new KeyboardEvent("keydown", {key: "ArrowRight", bubbles: true}));
                      check(app.snapshot().substep === held, "keyboard handler captured an input");

                      return {
                        visited,
                        executionStates,
                        failures,
                        resources: performance.getEntriesByType("resource").map(entry => entry.name),
                        stageButtons: document.querySelectorAll("#stage-strip > button").length,
                        ariaLive: document.querySelectorAll("[aria-live]").length
                      };
                    })()
                    """
                )
                if result["failures"]:
                    raise RuntimeError("; ".join(result["failures"]))
                if len(result["visited"]) != 45:
                    raise RuntimeError(f"Browser visited {len(result['visited'])} of 45 substeps.")
                if len(result["executionStates"]) != 6:
                    raise RuntimeError("Browser did not exercise all six execution substeps.")
                if result["stageButtons"] != 10 or result["ariaLive"] != 1:
                    raise RuntimeError("Canonical stage or aria-live count is wrong.")
                if result["resources"]:
                    raise RuntimeError(f"Unexpected runtime resources: {result['resources']}")

                wide_expected = (
                    "1-0,1-1,1-2,1-3,1-4,3-1,4-0,4-1,4-2,4-3,4-4,5-2,"
                    "6-0,6-1,6-2,6-3,6-4,7-0,7-1,7-2,7-3,7-4,8-0,8-1,8-2,"
                    "9-0,9-1,9-2,9-3,9-4,9-5"
                )
                for width in (1920, 3840):
                    cdp.call(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": width,
                            "height": 900,
                            "deviceScaleFactor": 1.25,
                            "mobile": False,
                        },
                    )
                    geometry = cdp.evaluate(
                        """
                        (() => {
                          const app = window.walkthroughApp;
                          const data = JSON.parse(document.getElementById("walkthrough-data").textContent);
                          const overlaps = [];
                          data.stages.forEach((stage, stageIndex) => {
                            app.selectStage(stageIndex);
                            stage.substeps.forEach((_substep, substepIndex) => {
                              app.selectSubstep(substepIndex);
                              const center = document.querySelector(".center");
                              const artifact = document.querySelector(".artifact-card").getBoundingClientRect();
                              const childRight = Math.max(...[...center.children]
                                .filter(child => getComputedStyle(child).display !== "none")
                                .map(child => child.getBoundingClientRect().right));
                              if (childRight > artifact.left + 0.5) {
                                overlaps.push(`${stageIndex}-${substepIndex}`);
                              }
                            });
                          });
                          return {
                            overlaps: overlaps.join(","),
                            shellWidth: document.querySelector(".shell").getBoundingClientRect().width,
                            workspaceColumns: getComputedStyle(
                              document.getElementById("workspace")).gridTemplateColumns
                          };
                        })()
                        """
                    )
                    if geometry["overlaps"] != wide_expected:
                        raise RuntimeError(
                            f"{width}px overlap set is not canonical: {geometry['overlaps']}"
                        )
                    if abs(geometry["shellWidth"] - 1580) > 0.1:
                        raise RuntimeError(f"{width}px shell did not honor the 1580px cap.")

                cdp.call(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": 1280, "height": 720, "deviceScaleFactor": 1.25, "mobile": False},
                )
                cdp.evaluate("window.walkthroughApp.selectStage(4); window.walkthroughApp.selectSubstep(0)")
                overlap = cdp.evaluate(
                    """
                    (() => {
                      const center = document.querySelector(".center");
                      const artifact = document.querySelector(".artifact-card");
                      const artifactRect = artifact.getBoundingClientRect();
                      const childRight = Math.max(...[...center.children]
                        .filter(child => getComputedStyle(child).display !== "none")
                        .map(child => child.getBoundingClientRect().right));
                      const x = artifactRect.left + 10;
                      const y = artifactRect.top + 100;
                      return {
                        overlaps: childRight > artifactRect.left,
                        occluded: artifact.contains(document.elementFromPoint(x, y)),
                        sticky: getComputedStyle(artifact).position === "sticky",
                        substepNoScroll: document.getElementById("substep-strip").scrollWidth ===
                          document.getElementById("substep-strip").clientWidth,
                        passNoScroll: document.getElementById("pass-rail").scrollWidth ===
                          document.getElementById("pass-rail").clientWidth
                      };
                    })()
                    """
                )
                if not all(overlap.values()):
                    raise RuntimeError(f"Canonical overlap/occlusion behavior failed: {overlap}")

                for width, expected in (
                    (1181, {"artifact": "sticky", "columns": 3}),
                    (1180, {"artifact": "static", "columns": 2}),
                    (850, {"artifact": "static", "columns": 2}),
                    (820, {"artifact": "static", "columns": 1}),
                ):
                    cdp.call(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": width,
                            "height": 900,
                            "deviceScaleFactor": 1.25,
                            "mobile": False,
                        },
                    )
                    responsive = cdp.evaluate(
                        """
                        (() => {
                          window.walkthroughApp.selectStage(4);
                          window.walkthroughApp.selectSubstep(0);
                          return {
                            artifact: getComputedStyle(document.querySelector(".artifact-card")).position,
                            columns: getComputedStyle(
                              document.getElementById("workspace")).gridTemplateColumns.split(" ").length,
                            centerTrack: document.querySelector(".center").getBoundingClientRect().width,
                            workspaceTrack: document.getElementById("workspace").getBoundingClientRect().width
                          };
                        })()
                        """
                    )
                    if (
                        responsive["artifact"] != expected["artifact"]
                        or responsive["columns"] != expected["columns"]
                    ):
                        raise RuntimeError(
                            f"{width}px breakpoint behavior is wrong: {responsive}"
                        )
                    if width == 820 and responsive["centerTrack"] < 950:
                        raise RuntimeError("The 820px canonical min-content overflow is missing.")

                cdp.call(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": 520, "height": 900, "deviceScaleFactor": 1, "mobile": False},
                )
                narrow = cdp.evaluate(
                    'matchMedia("(max-width: 520px)").matches && '
                    'getComputedStyle(document.querySelector(".workspace")).gridTemplateColumns.length > 0'
                )
                if not narrow:
                    raise RuntimeError("The 520px responsive breakpoint did not activate.")
                cdp.call("Emulation.setEmulatedMedia", {"media": "print"})
                print_hidden = cdp.evaluate(
                    'getComputedStyle(document.querySelector("button")).display === "none" && '
                    'getComputedStyle(document.querySelector("input")).display === "none"'
                )
                if not print_hidden:
                    raise RuntimeError("Print media did not hide button and input controls.")

                cdp.call("Page.reload")
                time.sleep(0.4)
                restored = cdp.evaluate(
                    'window.walkthroughApp.snapshot().stage === 0 && '
                    'window.walkthroughApp.snapshot().substep === 0 && '
                    'window.walkthroughApp.snapshot().runner === 0 && '
                    'window.walkthroughApp.snapshot().visited.join(",") === "0" && '
                    '!window.walkthroughApp.snapshot().traversalTimer && '
                    '!window.walkthroughApp.snapshot().boundaryTimer && '
                    'window.walkthroughApp.snapshot().compilerApplied === -1 && '
                    'window.walkthroughApp.snapshot().passApplied === -1 && '
                    'window.walkthroughApp.snapshot().physicalApplied === -1 && '
                    'window.walkthroughApp.snapshot().executionApplied === -1 && '
                    '!document.getElementById("workspace").classList.contains("stage-collapsed") && '
                    '!document.getElementById("workspace").classList.contains("artifact-collapsed")'
                )
                if not restored:
                    raise RuntimeError("Reload did not restore canonical initial state.")
                return result
            finally:
                cdp.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise all 45 walkthrough substeps in Edge.")
    parser.add_argument("html")
    parser.add_argument("--edge")
    args = parser.parse_args()
    edge = Path(args.edge).resolve() if args.edge else find_edge()
    if edge is None:
        parser.error("Microsoft Edge was not found")
    result = run_smoke(Path(args.html), edge)
    print(f"PASS: exercised {len(result['visited'])} substeps with no runtime requests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
