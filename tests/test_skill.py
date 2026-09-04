from __future__ import annotations

import copy
import hashlib
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

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"
sys.path[:0] = [str(SCRIPTS), str(TESTS)]

from fixture_factory import QUERY, rich_model
from canonical_spec import CANONICAL_SUBSTEPS, RUNNERLESS_KEYS
from model_contract import (
    ModelError,
    STAGES,
    query_slug,
    validate_cluster_uri,
    validate_complete_model,
    _validate_plan_recovery,
)
from plan_recovery import (
    PlanRecoveryError,
    accepted_recovery,
    build_queryplan_command,
    build_recovery_prompt,
    estimated_recovery,
    inspect_queryplan_payload,
    pending_recovery,
    record_recovery_prompt,
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
                            "syntheticAnchor": value["label"],
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
    @staticmethod
    def physical_queryplan() -> dict:
        return {
            "QueryPlan": {
                "RootOperator": {
                    "NodeId": 0,
                    "Operators": [
                        {
                            "$type": "Kusto.DataNode.DataEngineQueryPlan.HashJoin, DataNode",
                            "NodeId": 1,
                            "Build": {
                                "$type": "Kusto.DataNode.DataEngineQueryPlan.IteratorScan, DataNode",
                                "NodeId": 2,
                            },
                            "Probe": {
                                "$type": "Kusto.DataNode.DataEngineQueryPlan.RemoteQueryNode, DataNode",
                                "NodeId": 3,
                            },
                        }
                    ],
                }
            }
        }

    def test_queryplan_wrapper_preserves_exact_query_and_is_plan_only(self) -> None:
        query = "let x = 1;\r\nSyntheticEvents\r\n| where Message == '<| literal'\r\n"
        command = build_queryplan_command(query)
        self.assertEqual(command, f".show queryplan <|\n{query}")
        self.assertEqual(command.removeprefix(".show queryplan <|\n"), query)
        self.assertNotIn("| project QueryPlan", command)

    def test_complete_automatic_queryplan_skips_recovery_prompt(self) -> None:
        payload = json.dumps(self.physical_queryplan())
        result = inspect_queryplan_payload(payload)
        plan = accepted_recovery(
            payload,
            provenance="automatic",
            tool="synthetic non-executing automatic plan",
            collected_at_utc="2026-01-01T00:00:00Z",
        )
        self.assertTrue(plan["complete_physical_queryplan"])
        self.assertFalse(plan["recovery"]["required"])
        self.assertFalse(plan["recovery"]["prompted"])
        self.assertEqual(plan["recovery"]["deeplink_status"], "not_needed")

    def test_queryplan_table_envelope_and_raw_digest_are_supported(self) -> None:
        cell = json.dumps(
            {
                "RootOperator": {
                    "NodeId": 0,
                    "Operators": [
                        {
                            "$type": "Kusto.DataNode.DataEngineQueryPlan.IteratorScan, DataNode",
                            "NodeId": 1,
                        }
                    ],
                }
            },
            separators=(",", ":"),
        )
        raw = json.dumps(
            {
                "Tables": [
                    {
                        "Columns": [
                            {"ColumnName": "QueryPlan"},
                            {"ColumnName": "Other"},
                        ],
                        "Rows": [[cell, 1]],
                    }
                ]
            },
            separators=(",", ":"),
        ).encode("utf-8")
        result = inspect_queryplan_payload(raw)
        self.assertEqual(result["operator_count"], 1)
        self.assertEqual(result["digest_sha256"], hashlib.sha256(raw).hexdigest())
        result_type_envelope = {
            "Rows": [{"ResultType": "QueryPlan", "Content": cell}]
        }
        self.assertEqual(
            inspect_queryplan_payload(json.dumps(result_type_envelope))["operator_count"], 1
        )

    def test_logical_only_and_missing_queryplan_require_recovery(self) -> None:
        for payload, message in (
            ({"Relop": {"Kind": "Logical"}}, "logical Relop"),
            ({"Rows": [{"Statistics": {}}]}, "no QueryPlan"),
        ):
            with self.subTest(payload=payload), self.assertRaisesRegex(
                PlanRecoveryError, message
            ):
                inspect_queryplan_payload(json.dumps(payload))
        state = pending_recovery(
            QUERY, automatic_deficiency="Logical Relop found; complete QueryPlan missing."
        )
        self.assertTrue(state["recovery"]["required"])
        self.assertFalse(state["recovery"]["prompted"])
        self.assertEqual(
            state["recovery"]["command"], build_queryplan_command(QUERY)
        )

    def test_deeplink_failure_still_produces_exact_command_and_prompt(self) -> None:
        command = build_queryplan_command(QUERY)
        prompt = build_recovery_prompt(
            automatic_evidence="logical Relop and statistics only",
            command=command,
        )
        self.assertIn("complete physical QueryPlan", prompt)
        self.assertIn(command, prompt)
        self.assertIn("deeplink could not be generated", prompt)
        self.assertIn("QueryPlan result cell/JSON", prompt)
        self.assertIn("attach it", prompt)

    def test_user_supplied_complete_queryplan_upgrades_evidence_and_redacts(self) -> None:
        raw = json.dumps(
            {
                "QueryPlan": {
                    "RequestId": "sensitive-request",
                    "RootOperator": {
                        "NodeId": 0,
                        "Operators": [
                            {
                                "$type": "Kusto.DataNode.DataEngineQueryPlan.HashJoin, DataNode",
                                "NodeId": 1,
                                "Properties": [
                                    {
                                        "Name": "Literal",
                                        "Value": "customer@example.test",
                                    }
                                ],
                                "Build": {
                                    "$type": "Kusto.DataNode.DataEngineQueryPlan.IteratorScan, DataNode",
                                    "NodeId": 2,
                                    "AuthorizationValue": "secret",
                                },
                                "Probe": {
                                    "$type": "Kusto.DataNode.DataEngineQueryPlan.RemoteQueryNode, DataNode",
                                    "NodeId": 3,
                                },
                            }
                        ],
                    },
                }
            }
        )
        result = inspect_queryplan_payload(raw)
        self.assertEqual(result["operator_count"], 3)
        sanitized = json.dumps(result["sanitized_queryplan"])
        self.assertNotIn("sensitive-request", sanitized)
        self.assertNotIn("customer@example.test", sanitized)
        self.assertNotIn('"secret"', sanitized)
        prompt_record = record_recovery_prompt(
            QUERY,
            automatic_evidence="Automatic collection returned logical Relop and statistics.",
            automatic_deficiency="Automatic result contained only logical Relop.",
            deeplink_status="failed",
            prompted_at_utc="2026-01-01T00:00:00Z",
        )
        plan = accepted_recovery(
            raw,
            provenance="user_supplied",
            tool="user-supplied non-executing QueryPlan cell",
            collected_at_utc="2026-01-01T00:00:00Z",
            prompt_record=prompt_record,
        )
        self.assertTrue(plan["recovery"]["prompted"])
        _validate_plan_recovery(plan, QUERY, "EVIDENCE")

    def test_invalid_or_incomplete_queryplan_is_rejected(self) -> None:
        with self.assertRaisesRegex(PlanRecoveryError, "exact original JSON bytes"):
            inspect_queryplan_payload(self.physical_queryplan())
        cases = (
            ("", "empty"),
            ("not-json", "valid JSON"),
            (json.dumps({"QueryPlan": {"Kind": "Logical"}}), "RootOperator"),
            (json.dumps({"replotree": {"relop": "Scan"}}), "logical Relop"),
            (
                json.dumps(
                    {
                        "QueryPlan": {
                            "RootOperator": {
                                "NodeId": 0,
                                "Operators": [{"$type": "AnythingAtAll", "NodeId": 1}],
                            }
                        }
                    }
                ),
                "source-backed physical QueryPlan type",
            ),
            (json.dumps({"QueryPlan": {"RootOperator": {"Operators": []}}}), "NodeId"),
            (
                json.dumps(
                    {
                        "IsTruncated": True,
                        "QueryPlan": self.physical_queryplan()["QueryPlan"],
                    }
                ),
                "truncated",
            ),
            (
                json.dumps(
                    {
                        "QueryPlan": {
                            "IsTruncated": True,
                            "RootOperator": {
                                "NodeId": 0,
                                "Operators": [
                                    {
                                        "$type": "Kusto.DataNode.DataEngineQueryPlan.IteratorScan, DataNode",
                                        "NodeId": 1,
                                    }
                                ],
                            }
                        }
                    }
                ),
                "truncated",
            ),
            (
                json.dumps(
                    {
                        "QueryPlan": {
                            "IsTruncated": "true",
                            "RootOperator": {
                                "NodeId": 0,
                                "Operators": [
                                    {
                                        "$type": "Kusto.DataNode.DataEngineQueryPlan.IteratorScan, DataNode",
                                        "NodeId": 1,
                                    }
                                ],
                            },
                        }
                    }
                ),
                "must be boolean",
            ),
            (
                json.dumps(
                    {
                        "QueryPlan": {
                            "RootOperator": {
                                "NodeId": 0,
                                "Operators": [
                                    {
                                        "$type": "Kusto.DataNode.DataEngineQueryPlan.HashJoin, DataNode",
                                        "NodeId": 1,
                                        "Build": {"NodeId": 2},
                                    }
                                ],
                            }
                        }
                    }
                ),
                "complete physical operator payload",
            ),
            (
                json.dumps(
                    {
                        "QueryPlan": {
                            "RootOperator": {
                                "NodeId": 0,
                                "Operators": [
                                    {
                                        "$type": "Kusto.DataNode.DataEngineQueryPlan.HashJoin, DataNode",
                                        "NodeId": 1,
                                        "UnexpectedLane": {
                                            "$type": "Kusto.DataNode.DataEngineQueryPlan.IteratorScan, DataNode",
                                            "NodeId": 2,
                                        },
                                    }
                                ],
                            }
                        }
                    }
                ),
                "unknown child lane",
            ),
            (
                json.dumps(
                    {
                        "QueryPlan": {
                            "RootOperator": {
                                "NodeId": 0,
                                "Operators": [
                                    {
                                        "$type": "Kusto.DataNode.DataEngineQueryPlan.IteratorScan, DataNode",
                                        "NodeId": 1,
                                    },
                                    {},
                                ],
                            }
                        }
                    }
                ),
                "not a complete physical operator",
            ),
            (
                json.dumps(
                    {
                        "QueryPlan": {
                            "RootOperator": {
                                "NodeId": 0,
                                "Operators": [
                                    {
                                        "$type": "Kusto.DataNode.DataEngineQueryPlan.HashJoin, DataNode",
                                        "NodeId": 1,
                                        "Build": {},
                                    }
                                ],
                            }
                        }
                    }
                ),
                "complete physical operator payload",
            ),
            (
                json.dumps(
                    {
                        "QueryPlan": {
                            "RootOperator": {
                                "NodeId": 0,
                                "Operators": [
                                    {
                                        "$type": "Kusto.DataNode.DataEngineQueryPlan.HashJoin, DataNode",
                                        "NodeId": 1,
                                        "Build": "truncated",
                                    }
                                ],
                            }
                        }
                    }
                ),
                "complete physical operator payload",
            ),
            (
                json.dumps(
                    {
                        "QueryPlan": {
                            "RootOperator": {
                                "NodeId": 0,
                                "Operators": [
                                    {
                                        "$type": "Kusto.DataNode.DataEngineQueryPlan.LogicalRelop, DataNode",
                                        "NodeId": 1,
                                    }
                                ],
                            }
                        }
                    }
                ),
                "logical rather than physical",
            ),
        )
        for payload, deficiency in cases:
            with self.subTest(deficiency=deficiency), self.assertRaisesRegex(
                PlanRecoveryError, deficiency
            ):
                inspect_queryplan_payload(payload)

    def test_estimated_requires_explicit_user_outcome_and_records_provenance(self) -> None:
        prompt_record = record_recovery_prompt(
            QUERY,
            automatic_evidence="Automatic collection returned logical Relop only.",
            automatic_deficiency="Complete physical QueryPlan cell missing.",
            deeplink_status="failed",
            prompted_at_utc="2026-01-01T00:00:00Z",
        )
        plan = estimated_recovery(
            prompt_record,
            outcome="user_could_not_provide",
        )
        _validate_plan_recovery(plan, QUERY, "ESTIMATED")
        silent = copy.deepcopy(plan)
        silent["recovery"]["prompted"] = False
        with self.assertRaisesRegex(ModelError, "Unprompted recovery"):
            _validate_plan_recovery(silent, QUERY, "ESTIMATED")
        with self.assertRaisesRegex(PlanRecoveryError, "recorded recovery prompt"):
            estimated_recovery({}, outcome="user_declined")
        with self.assertRaisesRegex(PlanRecoveryError, "Collection timestamp"):
            accepted_recovery(
                json.dumps(self.physical_queryplan()),
                provenance="automatic",
                tool="automatic non-executing plan",
                collected_at_utc="not-a-time",
            )
        with self.assertRaisesRegex(PlanRecoveryError, "UTC RFC 3339"):
            record_recovery_prompt(
                QUERY,
                automatic_evidence="Logical Relop only.",
                automatic_deficiency="QueryPlan missing.",
                deeplink_status="failed",
                prompted_at_utc="2026-02-30T99:00:00Z",
            )

        model = rich_model()
        model["evidence_mode"] = "ESTIMATED"
        model["estimate_reason"] = (
            "The complete physical QueryPlan was unavailable and the user could not provide it "
            "after the recovery prompt."
        )
        model["plan"].update(plan)
        for stage in model["stages"]:
            if stage["evidence_kind"] == "NO_OP":
                continue
            stage["evidence_kind"] = "ESTIMATED"
            stage["no_op_explanation"] = ""
            for substep in stage["substeps"]:
                if substep["change_badge"] == "NO_OP":
                    continue
                substep["change_badge"] = "ESTIMATED"
                if substep["artifact"]["before"] == substep["artifact"]["after"]:
                    substep["artifact"]["after"] += " (estimated)"
                runner = substep.get("runner")
                if not runner:
                    continue
                runner["no_op"] = {"enabled": False, "gates": [], "reasons": []}
                for action in runner["actions"]:
                    action["evidence_kind"] = "ESTIMATED"
                if runner["type"] == "compiler":
                    for action in (
                        runner["compiler"]["before_actions"]
                        + runner["compiler"]["after_actions"]
                    ):
                        action["evidence_kind"] = "ESTIMATED"
                elif runner["type"] == "pass":
                    for pass_item in runner["pass"]["applicable_passes"]:
                        pass_item["outcome"] = "ESTIMATED"
                elif runner["type"] == "physical":
                    runner["physical"]["full_plan"]["complete"] = False
        validate_complete_model(model)

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
        invalid = rich_model()
        invalid["plan"]["collected_at_utc"] = "2026-02-30T99:00:00Z"
        with self.assertRaisesRegex(ModelError, "valid UTC RFC 3339"):
            validate_complete_model(invalid)

    def test_canonical_substeps_have_exact_runner_topology_and_distinct_states(self) -> None:
        model = rich_model()
        self.assertEqual(sum(len(stage["substeps"]) for stage in model["stages"]), 45)
        for stage, expected_stage in zip(model["stages"], CANONICAL_SUBSTEPS, strict=True):
            self.assertEqual(len(stage["substeps"]), len(expected_stage))
            for substep, expected in zip(stage["substeps"], expected_stage, strict=True):
                self.assertEqual(substep["id"], expected.key)
                self.assertEqual(substep["title"], expected.title)
                if expected.runner_type is None:
                    self.assertNotIn("runner", substep)
                    continue
                runner = substep["runner"]
                self.assertEqual(runner["type"], expected.runner_type)
                self.assertEqual(len(runner["actions"]), expected.item_count)
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
        with self.assertRaisesRegex(ModelError, "runner is required"):
            validate_complete_model(model)

    def test_runner_is_rejected_at_the_four_canonical_omissions(self) -> None:
        model = rich_model()
        omissions = {
            substep["id"]: substep
            for stage in model["stages"]
            for substep in stage["substeps"]
            if "runner" not in substep
        }
        self.assertEqual(set(omissions), RUNNERLESS_KEYS)
        omissions["3-0"]["runner"] = copy.deepcopy(model["stages"][3]["substeps"][1]["runner"])
        with self.assertRaisesRegex(ModelError, "runner must be omitted"):
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
        partial["substeps"][2]["runner"]["no_op"]["enabled"] = False
        with self.assertRaisesRegex(ModelError, "does not match"):
            validate_complete_model(model)

    def test_no_op_runner_actions_cannot_claim_transformations(self) -> None:
        model = rich_model()
        partial = model["stages"][5]
        action = partial["substeps"][2]["runner"]["actions"][0]
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
        runner["snapshots"].pop()
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

    def test_every_method_path_entry_requires_its_own_source_link(self) -> None:
        model = rich_model()
        model["stages"][0]["substeps"][0]["method_path"][0]["source_links"] = []
        with self.assertRaisesRegex(ModelError, "must not be empty"):
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

    def test_physical_tree_must_match_sanitized_queryplan_topology(self) -> None:
        model = rich_model()
        physical = model["stages"][7]["substeps"][0]["runner"]["physical"]["full_plan"]
        physical["roots"][0]["name"] = "IteratorScan"
        with self.assertRaisesRegex(ModelError, "topology does not match"):
            validate_complete_model(model)

        model = rich_model()
        model["plan"]["sanitized_queryplan"]["RootOperator"]["Operators"][0][
            "Build"
        ]["NodeId"] = 99
        canonical = json.dumps(
            model["plan"]["sanitized_queryplan"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        model["plan"]["sanitized_digest_sha256"] = hashlib.sha256(canonical).hexdigest()
        with self.assertRaisesRegex(ModelError, "topology does not match"):
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
        with self.assertRaisesRegex(ModelError, "exactly 3 canonical scenarios"):
            validate_complete_model(model)
        model = rich_model()
        execute = model["stages"][9]["substeps"][0]["runner"]["execute"]
        execute["scenarios"][-1]["type"] = "memory"
        with self.assertRaisesRegex(ModelError, "cover failure, cancellation, memory, and lifetime"):
            validate_complete_model(model)

    def test_execute_scenario_counts_follow_canonical_topology(self) -> None:
        model = rich_model()
        self.assertEqual(
            [
                len(substep["runner"]["execute"]["scenarios"])
                for substep in model["stages"][9]["substeps"]
            ],
            [3, 3, 3, 4, 4, 4],
        )
        model["stages"][9]["substeps"][0]["runner"]["execute"]["scenarios"].append(
            copy.deepcopy(
                model["stages"][9]["substeps"][3]["runner"]["execute"]["scenarios"][-1]
            )
        )
        with self.assertRaisesRegex(ModelError, "exactly 3 canonical scenarios"):
            validate_complete_model(model)

    def test_execution_domains_and_references_are_enforced(self) -> None:
        mutations = (
            ("lang", "managed", "lang is invalid"),
            ("memory_op", "allocate", "op is invalid"),
            ("memory_zone", "stack", "zone is invalid"),
            ("frame_kind", "managed", "kind is invalid"),
            ("active", "missing-component", "references absent components"),
        )
        for field, value, message in mutations:
            with self.subTest(field=field):
                model = rich_model()
                execute = model["stages"][9]["substeps"][0]["runner"]["execute"]
                if field == "memory_op":
                    execute["action_timeline"][0]["memory"][0]["op"] = value
                elif field == "memory_zone":
                    execute["action_timeline"][0]["memory"][0]["zone"] = value
                elif field == "frame_kind":
                    execute["call_stack"][0]["kind"] = value
                else:
                    execute["action_timeline"][0][field] = value
                with self.assertRaisesRegex(ModelError, message):
                    validate_complete_model(model)

    def test_boundary_action_lanes_are_required_and_bounded(self) -> None:
        model = rich_model()
        action = model["stages"][8]["substeps"][0]["runner"]["actions"][0]
        action.pop("lane")
        with self.assertRaisesRegex(ModelError, "lane must be C#, Interop, or C\\+\\+"):
            validate_complete_model(model)
        model = rich_model()
        action = model["stages"][8]["substeps"][0]["runner"]["actions"][0]
        action["lane"] = "Rust"
        with self.assertRaisesRegex(ModelError, "lane must be C#, Interop, or C\\+\\+"):
            validate_complete_model(model)
        model = rich_model()
        action = model["stages"][8]["substeps"][2]["runner"]["actions"][-1]
        action["lane"] = "Interop"
        with self.assertRaisesRegex(ModelError, "canonical boundary lane distribution"):
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
        self.assertIn(
            "<title>Kusto Query Lifecycle: Two-Level Interactive Walkthrough</title>",
            self.text,
        )
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
        self.assertIn(
            "<title>Kusto Query Lifecycle: Two-Level Interactive Walkthrough</title>",
            text,
        )
        self.assertIn("<h1>&lt;Unsafe &amp; title&gt;</h1>", text)
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

    def test_scaffolder_creates_v2_draft_with_canonical_topology(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "draft.json"
            result = self.run_scaffolder("https://example.kusto.windows.net", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            draft = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(draft["schema_version"], "2.0")
        self.assertEqual(draft["model_state"], "DRAFT")
        self.assertEqual(len(draft["stages"]), 10)
        self.assertIs(draft["plan"]["non_executing"], True)
        fixture_query = (ROOT / "tests" / "fixtures" / "synthetic-query.kql").read_bytes().decode(
            "utf-8"
        )
        self.assertEqual(draft["query"]["text"], fixture_query)
        self.assertEqual(
            draft["plan"]["recovery"]["command"],
            f".show queryplan <|\n{fixture_query}",
        )
        self.assertEqual(draft["source"]["workspace_head"], self.source_head)
        self.assertEqual(sum(len(stage["substeps"]) for stage in draft["stages"]), 45)
        for stage, expected_stage in zip(draft["stages"], CANONICAL_SUBSTEPS, strict=True):
            for substep, expected in zip(stage["substeps"], expected_stage, strict=True):
                self.assertEqual(substep["id"], expected.key)
                self.assertEqual(substep.get("runner", {}).get("type"), expected.runner_type)

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

    def test_plan_recovery_cli_records_a_deterministic_prompt(self) -> None:
        query_path = ROOT / "tests" / "fixtures" / "synthetic-query.kql"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "plan_recovery.py"),
                "--query-file",
                str(query_path),
                "--record-prompt",
                "--automatic-evidence",
                "Logical Relop and statistics only.",
                "--automatic-deficiency",
                "Complete physical QueryPlan missing.",
                "--deeplink-status",
                "failed",
                "--prompted-at-utc",
                "2026-01-01T00:00:00Z",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        exact_query = query_path.read_bytes().decode("utf-8")
        self.assertEqual(
            payload["recovery"]["command"], f".show queryplan <|\n{exact_query}"
        )
        self.assertIn("complete physical QueryPlan", payload["prompt"])
        self.assertRegex(payload["recovery"]["prompt_digest_sha256"], r"^[0-9a-f]{64}$")

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
            self.assertIn("scripts/plan_recovery.py", names)
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

    def test_json_schema_allows_only_position_validated_runner_omissions(self) -> None:
        schema = json.loads(
            (ROOT / "references" / "evidence-model.schema.json").read_text(encoding="utf-8")
        )
        self.assertIs(schema["additionalProperties"], False)
        self.assertNotIn("runner", schema["$defs"]["substep"]["required"])
        self.assertIn("runner", schema["$defs"]["compilerSubsteps"]["items"]["allOf"][1]["required"])
        experiment = schema["$defs"]["experiment"]["properties"]
        self.assertEqual(experiment["options"]["minItems"], 2)
        self.assertEqual(experiment["results"]["minItems"], 2)
        runner = schema["$defs"]["runner"]["properties"]
        self.assertEqual(runner["actions"]["minItems"], 1)
        self.assertEqual(runner["snapshots"]["minItems"], 2)
        self.assertEqual(runner["experiments"]["minItems"], 1)
        scenarios = schema["$defs"]["executeRunner"]["properties"]["scenarios"]
        self.assertEqual((scenarios["minItems"], scenarios["maxItems"]), (3, 4))
        self.assertEqual(
            schema["$defs"]["timelineAction"]["properties"]["lang"]["enum"],
            ["cpp", "rust", "csharp"],
        )
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

    def test_json_schema_enforces_complete_recovery_states(self) -> None:
        schema = json.loads(
            (ROOT / "references" / "evidence-model.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        model = rich_model()
        self.assertEqual(list(validator.iter_errors(model)), [])

        invalid = copy.deepcopy(model)
        invalid["plan"]["provenance"] = "estimated_after_recovery"
        invalid["plan"]["complete_physical_queryplan"] = False
        self.assertTrue(list(validator.iter_errors(invalid)))

        invalid = copy.deepcopy(model)
        invalid["plan"]["provenance"] = "user_supplied"
        invalid["plan"]["recovery"]["prompted"] = False
        self.assertTrue(list(validator.iter_errors(invalid)))

        prompt_record = record_recovery_prompt(
            QUERY,
            automatic_evidence="Logical Relop only.",
            automatic_deficiency="Complete QueryPlan missing.",
            deeplink_status="generated",
            deeplink_url="https://dataexplorer.azure.com/clusters/example",
            prompted_at_utc="2026-01-01T00:00:00Z",
        )
        recovered = copy.deepcopy(model)
        recovered["plan"]["provenance"] = "user_supplied"
        recovered["plan"]["tool"] = "user-supplied non-executing QueryPlan cell"
        recovered["plan"]["recovery"] = {
            **prompt_record,
            "outcome": "accepted",
        }
        self.assertEqual(list(validator.iter_errors(recovered)), [])

        invalid = copy.deepcopy(recovered)
        invalid["plan"]["recovery"]["command"] = ""
        self.assertTrue(list(validator.iter_errors(invalid)))
        invalid = copy.deepcopy(recovered)
        invalid["plan"]["recovery"]["deeplink_url"] = ""
        self.assertTrue(list(validator.iter_errors(invalid)))
        estimated_pattern = schema["allOf"][1]["then"]["properties"]["plan"][
            "properties"
        ]["recovery"]["properties"]["command"]["pattern"]
        self.assertIsNotNone(
            re.fullmatch(estimated_pattern, ".show queryplan <|\n\nSyntheticEvents")
        )

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
