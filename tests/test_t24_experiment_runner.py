from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.schema.v2.taxonomies import RouteLabel  # noqa: E402
from ambiguity_manager.systems.contracts import (  # noqa: E402
    StructuredAnalysis,
    SystemInput,
    SystemResult,
)
from ambiguity_manager.systems.errors import (  # noqa: E402
    DuplicateResultError,
    OfficialRunBlockedError,
)
from ambiguity_manager.systems.execution import (  # noqa: E402
    ExperimentRunner,
    OfficialPrerequisites,
)

FIXTURES_DIR = ROOT / "tests" / "fixtures" / "t16_t24_synthetic"
INPUTS_PATH = FIXTURES_DIR / "inputs.jsonl"
CACHED_ANALYSES_PATH = FIXTURES_DIR / "cached_analyses.json"


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_inputs() -> list[SystemInput]:
    return [SystemInput.from_dict(row) for row in _load_jsonl(INPUTS_PATH)]


def _load_cached_analyses() -> dict[str, StructuredAnalysis]:
    raw = json.loads(CACHED_ANALYSES_PATH.read_text(encoding="utf-8"))
    return {
        record_id: StructuredAnalysis.from_dict(payload)
        for record_id, payload in raw.items()
    }


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _config(*, run_mode: str, systems: list[str], config_id: str = "test_config") -> dict:
    return {
        "config_id": config_id,
        "run_mode": run_mode,
        "systems": systems,
    }


def _make_prerequisites(base_dir: Path, *, include_gold: bool = True, include_t15: bool = True) -> OfficialPrerequisites:
    gold_path = base_dir / "gold.jsonl"
    split_path = base_dir / "t15_split.json"
    if include_gold:
        gold_path.write_text("{}\n", encoding="utf-8")
    if include_t15:
        split_path.write_text("{}\n", encoding="utf-8")
    return OfficialPrerequisites(
        adjudicated_gold_dataset=gold_path if include_gold else None,
        t15_split_manifest=split_path if include_t15 else None,
        protocol_freeze_identifier="protocol-freeze-1",
        selected_model_strategy="provider-strategy-v1",
        handbook_version="handbook-v1",
    )


class StubSystem:
    def __init__(
        self,
        system_id: str,
        *,
        behavior_by_record: dict[str, object] | None = None,
        provider: object | None = object(),
    ) -> None:
        self.system_id = system_id
        self.system_version = "stub-1.0.0"
        self.behavior_by_record = behavior_by_record or {}
        self.provider = provider
        self.calls: list[str] = []

    def run(
        self,
        system_input: SystemInput,
        *,
        cached_analysis: StructuredAnalysis | None = None,
    ) -> SystemResult:
        self.calls.append(system_input.record_id)
        behavior = self.behavior_by_record.get(system_input.record_id, "ok")
        if isinstance(behavior, Exception):
            raise behavior

        execution_status = "ok"
        route: str | None = "execute"
        if isinstance(behavior, dict):
            execution_status = str(behavior.get("execution_status", "ok"))
            route = behavior.get("route", "execute")
        elif behavior == "not_executable":
            execution_status = "not_executable"
            route = None
        elif behavior == "provider_unavailable":
            execution_status = "provider_unavailable"
            route = None
        elif behavior == "clarify":
            route = "clarify"
        elif behavior == "reject":
            route = "face_preserving_rejection"

        analysis = copy.deepcopy(cached_analysis) if cached_analysis is not None else StructuredAnalysis()
        route_label = RouteLabel(route) if route is not None else None
        return SystemResult(
            record_id=system_input.record_id,
            system_id=self.system_id,
            system_version=self.system_version,
            analysis=analysis,
            recommended_strategy=route_label,
            clarification_targets=["object"] if route == "clarify" else [],
            clarification_question="Which object?" if route == "clarify" else None,
            rejection_reason="capability_limitation" if route == "face_preserving_rejection" else None,
            execution_status=execution_status,
            runtime_metadata={"stub_behavior": behavior},
            synthetic_only=True,
            official_result=False,
        ).with_computed_hash()


class ExperimentRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = _load_inputs()
        cls.cached_analyses = _load_cached_analyses()

    def test_synthetic_run_succeeds(self) -> None:
        records = self.inputs[:2]
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "synthetic-run"
            summary = runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=records,
                cached_analyses=self.cached_analyses,
                output_dir=output_dir,
            )

            self.assertEqual(summary["results_written"], 2)
            self.assertEqual(summary["failures_written"], 0)
            self.assertTrue((output_dir / "results.jsonl").is_file())
            self.assertTrue((output_dir / "summary.json").is_file())
            self.assertEqual(runner.verify_run(output_dir)["duplicates"], 0)

    def test_official_run_blocked_without_gold(self) -> None:
        runner = ExperimentRunner(registry={"always_execute": StubSystem("always_execute")})
        records = self.inputs[:1]

        with tempfile.TemporaryDirectory() as tmpdir:
            prerequisites = _make_prerequisites(Path(tmpdir), include_gold=False, include_t15=True)
            with self.assertRaises(OfficialRunBlockedError) as ctx:
                runner.run(
                    config=_config(run_mode="official", systems=["always_execute"]),
                    records=records,
                    prerequisites=prerequisites,
                )
        self.assertIn("adjudicated_gold_dataset", ctx.exception.missing)

    def test_official_run_blocked_without_t15_split(self) -> None:
        runner = ExperimentRunner(registry={"always_execute": StubSystem("always_execute")})
        records = self.inputs[:1]

        with tempfile.TemporaryDirectory() as tmpdir:
            prerequisites = _make_prerequisites(Path(tmpdir), include_gold=True, include_t15=False)
            with self.assertRaises(OfficialRunBlockedError) as ctx:
                runner.run(
                    config=_config(run_mode="official", systems=["always_execute"]),
                    records=records,
                    prerequisites=prerequisites,
                )
        self.assertIn("t15_split_manifest", ctx.exception.missing)

    def test_official_model_backed_run_blocked_without_model_provider(self) -> None:
        runner = ExperimentRunner(
            registry={"direct_base_llm": StubSystem("direct_base_llm", provider=None)}
        )
        records = self.inputs[:1]

        with tempfile.TemporaryDirectory() as tmpdir:
            prerequisites = _make_prerequisites(Path(tmpdir), include_gold=True, include_t15=True)
            with self.assertRaises(OfficialRunBlockedError) as ctx:
                runner.run(
                    config=_config(run_mode="official", systems=["direct_base_llm"]),
                    records=records,
                    prerequisites=prerequisites,
                )
        self.assertIn("model_provider", ctx.exception.missing)

    def test_duplicate_results_are_blocked(self) -> None:
        records = self.inputs[:1]
        runner = ExperimentRunner(registry={"always_execute": StubSystem("always_execute")})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "dup-run"
            runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=records,
                cached_analyses=self.cached_analyses,
                output_dir=output_dir,
            )
            with self.assertRaises(DuplicateResultError):
                runner.run(
                    config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                    records=records,
                    cached_analyses=self.cached_analyses,
                    output_dir=output_dir,
                )

    def test_resume_preserves_completed_records(self) -> None:
        records = self.inputs[:2]
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "resume-run"
            runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=records[:1],
                cached_analyses=self.cached_analyses,
                output_dir=output_dir,
            )
            summary = runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=records,
                cached_analyses=self.cached_analyses,
                output_dir=output_dir,
                resume=True,
            )

            self.assertEqual(Counter(stub.calls), Counter({"syn_clear_execute": 1, "syn_referential_clarify": 1}))
            self.assertEqual(summary["results_written"], 1)
            self.assertEqual(summary["completed_keys"], 2)
            self.assertEqual(len(_read_jsonl(output_dir / "results.jsonl")), 2)

    def test_failures_are_retained(self) -> None:
        records = self.inputs[:2]
        stub = StubSystem(
            "always_execute",
            behavior_by_record={"syn_referential_clarify": RuntimeError("boom")},
        )
        runner = ExperimentRunner(registry={"always_execute": stub})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "failure-run"
            summary = runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=records,
                cached_analyses=self.cached_analyses,
                output_dir=output_dir,
            )
            results = _read_jsonl(output_dir / "results.jsonl")
            failures = _read_jsonl(output_dir / "failures.jsonl")

        self.assertEqual(summary["results_written"], 1)
        self.assertEqual(summary["failures_written"], 1)
        self.assertEqual(summary["skipped_or_failed_retained"], 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["error_type"], "RuntimeError")
        self.assertEqual(results[-1]["execution_status"], "failed")

    def test_not_executable_results_are_retained(self) -> None:
        record = [self.inputs[0]]
        stub = StubSystem(
            "always_execute",
            behavior_by_record={"syn_clear_execute": "not_executable"},
        )
        runner = ExperimentRunner(registry={"always_execute": stub})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "not-exec-run"
            summary = runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=record,
                cached_analyses=self.cached_analyses,
                output_dir=output_dir,
            )
            results = _read_jsonl(output_dir / "results.jsonl")

        self.assertEqual(summary["results_written"], 1)
        self.assertEqual(summary["not_executable_count"], 1)
        self.assertEqual(results[0]["execution_status"], "not_executable")

    def test_manifest_hash_inputs_are_deterministic(self) -> None:
        records = self.inputs[:2]
        runner = ExperimentRunner(registry={"always_execute": StubSystem("always_execute")})
        config = _config(
            run_mode="synthetic_smoke",
            systems=["always_execute"],
            config_id="deterministic-config",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir_a = Path(tmpdir) / "run-a"
            output_dir_b = Path(tmpdir) / "run-b"
            summary_a = runner.run(
                config=config,
                records=records,
                cached_analyses=self.cached_analyses,
                output_dir=output_dir_a,
            )
            summary_b = runner.run(
                config=config,
                records=records,
                cached_analyses=self.cached_analyses,
                output_dir=output_dir_b,
            )
            manifest_a = json.loads((output_dir_a / "run_manifest.json").read_text(encoding="utf-8"))
            manifest_b = json.loads((output_dir_b / "run_manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(summary_a["run_id"], summary_b["run_id"])
        self.assertEqual(summary_a["config_hash"], summary_b["config_hash"])
        self.assertEqual(summary_a["input_manifest_hash"], summary_b["input_manifest_hash"])
        self.assertEqual(manifest_a["config_hash"], manifest_b["config_hash"])
        self.assertEqual(manifest_a["input_manifest_hash"], manifest_b["input_manifest_hash"])
        self.assertEqual(
            manifest_a["provenance"]["config_hashes"]["experiment_config"],
            manifest_b["provenance"]["config_hashes"]["experiment_config"],
        )

    def test_protected_label_leakage_gate_blocks_official_run(self) -> None:
        runner = ExperimentRunner(registry={"always_execute": StubSystem("always_execute")})
        records = self.inputs[:1]

        with tempfile.TemporaryDirectory() as tmpdir:
            prerequisites = _make_prerequisites(Path(tmpdir), include_gold=True, include_t15=True)
            with self.assertRaises(OfficialRunBlockedError) as ctx:
                runner.run(
                    config=_config(run_mode="official", systems=["always_execute"]),
                    records=records,
                    prerequisites=prerequisites,
                    protected_labels_in_prompts=True,
                )
        self.assertIn("protected_label_leakage", ctx.exception.missing)


if __name__ == "__main__":
    unittest.main()
