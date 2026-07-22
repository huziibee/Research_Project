"""T23 runner integrity hardening tests.

Covers: full input-manifest hashing (Section C), resume contract
verification (Section D), run-mode-owned flags (Section E), the protected
data gate (Section F), and the strengthened ``verify_run`` (Section G).
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ambiguity_manager.schema.v2.taxonomies import RouteLabel  # noqa: E402
from ambiguity_manager.systems.contracts import (  # noqa: E402
    InputProvenance,
    StructuredAnalysis,
    SystemInput,
    SystemResult,
)
from ambiguity_manager.systems.errors import (  # noqa: E402
    OfficialRunBlockedError,
    ProtectedDataBlockedError,
    ResumeContractError,
)
from ambiguity_manager.systems.execution import (  # noqa: E402
    ExperimentRunner,
    OfficialPrerequisites,
    RunContext,
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


def _config(*, run_mode: str, systems: list[str], config_id: str = "integrity_test") -> dict:
    return {
        "config_id": config_id,
        "run_mode": run_mode,
        "systems": systems,
    }


class StubSystem:
    def __init__(
        self,
        system_id: str,
        *,
        behavior_by_record: dict[str, object] | None = None,
        system_version: str = "stub-1.0.0",
        set_synthetic_only: bool = True,
        set_official_result: bool = False,
    ) -> None:
        self.system_id = system_id
        self.system_version = system_version
        self.behavior_by_record = behavior_by_record or {}
        self.provider = object()
        self.calls: list[str] = []
        self._set_synthetic_only = set_synthetic_only
        self._set_official_result = set_official_result

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

        analysis = copy.deepcopy(cached_analysis) if cached_analysis is not None else StructuredAnalysis()
        return SystemResult(
            record_id=system_input.record_id,
            system_id=self.system_id,
            system_version=self.system_version,
            analysis=analysis,
            recommended_strategy=RouteLabel.EXECUTE,
            execution_status="ok",
            runtime_metadata={"stub_behavior": str(behavior)},
            # Deliberately hostile defaults: an adapter that always claims to
            # be an official, non-synthetic result. The runner must override
            # this unconditionally (Section E).
            synthetic_only=self._set_synthetic_only,
            official_result=self._set_official_result,
        ).with_computed_hash()


class RunContextTests(unittest.TestCase):
    def test_synthetic_smoke_flags(self) -> None:
        ctx = RunContext.for_run_mode("synthetic_smoke")
        self.assertTrue(ctx.synthetic_only)
        self.assertFalse(ctx.official_result)
        self.assertTrue(ctx.approved)

    def test_development_flags_non_synthetic(self) -> None:
        ctx = RunContext.for_run_mode("development", synthetic_inputs=False)
        self.assertFalse(ctx.synthetic_only)
        self.assertFalse(ctx.official_result)

    def test_development_flags_synthetic_inputs(self) -> None:
        ctx = RunContext.for_run_mode("development", synthetic_inputs=True)
        self.assertTrue(ctx.synthetic_only)
        self.assertFalse(ctx.official_result)

    def test_for_run_mode_official_is_pending_not_approved(self) -> None:
        ctx = RunContext.for_run_mode("official")
        self.assertEqual(ctx.run_mode, "official")
        self.assertFalse(ctx.synthetic_only)
        self.assertFalse(ctx.official_result)
        self.assertFalse(ctx.approved)
        with self.assertRaises(Exception):
            ctx.ensure_executable()

    def test_approved_official_sets_official_result_true(self) -> None:
        ctx = RunContext.approved_official()
        self.assertTrue(ctx.approved)
        self.assertFalse(ctx.synthetic_only)
        self.assertTrue(ctx.official_result)

    def test_unknown_run_mode_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RunContext.for_run_mode("bogus_mode")

    def test_apply_overrides_adapter_supplied_flags(self) -> None:
        ctx = RunContext.for_run_mode("development", synthetic_inputs=False)
        hostile = SystemResult(
            record_id="rec-1",
            system_id="always_execute",
            system_version="1.0.0",
            analysis=StructuredAnalysis(),
            recommended_strategy=None,
            synthetic_only=True,
            official_result=True,
        ).with_computed_hash()
        original_hash = hostile.result_hash

        fixed = ctx.apply(hostile, run_id="dev-test")

        self.assertFalse(fixed.synthetic_only)
        self.assertFalse(fixed.official_result)
        self.assertEqual(fixed.run_mode, "development")
        self.assertEqual(fixed.run_id, "dev-test")
        # The hash must be recomputed once the flags are forced, or a
        # verifier would flag a false "corruption".
        self.assertEqual(fixed.result_hash, fixed.compute_hash())
        self.assertNotEqual(fixed.result_hash, original_hash)


class RunnerModeOwnsFlagsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = _load_inputs()
        cls.cached = _load_cached_analyses()

    def test_adapter_cannot_claim_official_result_in_synthetic_run(self) -> None:
        stub = StubSystem("always_execute", set_synthetic_only=False, set_official_result=True)
        runner = ExperimentRunner(registry={"always_execute": stub})
        records = self.inputs[:1]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=records,
                cached_analyses=self.cached,
                output_dir=output_dir,
            )
            rows = _read_jsonl(output_dir / "results.jsonl")

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["synthetic_only"])
        self.assertFalse(rows[0]["official_result"])
        # The stored hash must match the runner-owned flags, not the
        # adapter's original (overridden) values.
        self.assertEqual(rows[0]["result_hash"], SystemResult.from_dict(rows[0]).compute_hash())

    def test_development_run_on_non_synthetic_inputs_sets_synthetic_only_false(self) -> None:
        stub = StubSystem("always_execute", set_synthetic_only=True, set_official_result=False)
        runner = ExperimentRunner(registry={"always_execute": stub})
        records = [
            SystemInput(
                record_id="dev_real_1",
                command="Pick up the mug.",
                input_provenance=InputProvenance(source="teach_derived"),
            )
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            summary = runner.run(
                config=_config(run_mode="development", systems=["always_execute"]),
                records=records,
                cached_analyses={},
                output_dir=output_dir,
            )
            rows = _read_jsonl(output_dir / "results.jsonl")

        self.assertFalse(summary["synthetic_only"])
        self.assertFalse(summary["official_result"])
        self.assertFalse(rows[0]["synthetic_only"])
        self.assertFalse(rows[0]["official_result"])

    def test_development_run_on_synthetic_fixtures_sets_synthetic_only_true(self) -> None:
        stub = StubSystem("always_execute", set_synthetic_only=False, set_official_result=False)
        runner = ExperimentRunner(registry={"always_execute": stub})
        records = self.inputs[:1]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            summary = runner.run(
                config=_config(run_mode="development", systems=["always_execute"]),
                records=records,
                cached_analyses=self.cached,
                output_dir=output_dir,
            )
            rows = _read_jsonl(output_dir / "results.jsonl")

        self.assertTrue(summary["synthetic_only"])
        self.assertFalse(summary["official_result"])
        self.assertTrue(rows[0]["synthetic_only"])
        self.assertFalse(rows[0]["official_result"])


class ProtectedDataGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cached = _load_cached_analyses()

    def _protected_record(self) -> SystemInput:
        return SystemInput(
            record_id="syn_clear_execute",
            command="Pick up the red mug.",
            protected_data=True,
        )

    def test_synthetic_run_rejects_protected_record(self) -> None:
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            with self.assertRaises(ProtectedDataBlockedError):
                runner.run(
                    config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                    records=[self._protected_record()],
                    output_dir=output_dir,
                )
            self.assertFalse(output_dir.exists())

    def test_development_run_rejects_protected_record(self) -> None:
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            with self.assertRaises(ProtectedDataBlockedError):
                runner.run(
                    config=_config(run_mode="development", systems=["always_execute"]),
                    records=[self._protected_record()],
                    output_dir=output_dir,
                )

    def test_non_protected_record_unaffected(self) -> None:
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})
        record = SystemInput(record_id="syn_clear_execute", command="Pick up the red mug.")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            summary = runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=[record],
                cached_analyses=self.cached,
                output_dir=output_dir,
            )
        self.assertEqual(summary["results_written"], 1)


class InputManifestHashingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = _load_inputs()
        cls.cached = _load_cached_analyses()

    def _run(self, output_dir: Path, records, cached=None) -> dict:
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})
        return runner.run(
            config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
            records=records,
            cached_analyses=cached if cached is not None else self.cached,
            output_dir=output_dir,
        )

    def test_manifest_is_full_record_content_not_just_ids(self) -> None:
        records = self.inputs[:1]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            self._run(output_dir, records)
            manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))

        input_manifest = manifest["input_manifest"]
        self.assertIn("records", input_manifest)
        entry = input_manifest["records"][0]
        self.assertEqual(entry["record_id"], records[0].record_id)
        self.assertEqual(entry["input"]["command"], records[0].command)
        self.assertEqual(entry["input"]["scene_context"], records[0].scene_context)
        self.assertEqual(entry["input"]["capability_context"], records[0].capability_context)
        self.assertIn("label_eligibility", entry["input"])
        self.assertIn("protected_data", entry["input"])
        self.assertEqual(entry["cached_analysis"], self.cached[records[0].record_id].to_dict())
        self.assertIn("record_ordering_policy", input_manifest)
        self.assertIn("input_schema_version", input_manifest)

    def test_manifest_hash_has_no_volatile_timestamp(self) -> None:
        records = self.inputs[:1]
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            summary_a = self._run(Path(tmpdir1) / "run", records)
            summary_b = self._run(Path(tmpdir2) / "run", records)
        self.assertEqual(summary_a["input_manifest_hash"], summary_b["input_manifest_hash"])

    def test_changing_scene_context_changes_manifest_hash(self) -> None:
        base = self.inputs[0]
        mutated = SystemInput(
            record_id=base.record_id,
            command=base.command,
            dialogue_history=base.dialogue_history,
            scene_context="objects: a completely different scene",
            capability_context=base.capability_context,
            input_provenance=base.input_provenance,
            label_eligibility=base.label_eligibility,
            protected_data=base.protected_data,
        )
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            summary_a = self._run(Path(tmpdir1) / "run", [base])
            summary_b = self._run(Path(tmpdir2) / "run", [mutated])
        self.assertNotEqual(summary_a["input_manifest_hash"], summary_b["input_manifest_hash"])

    def test_changing_cached_analysis_changes_manifest_hash(self) -> None:
        records = self.inputs[:1]
        record_id = records[0].record_id
        cached_a = {record_id: copy.deepcopy(self.cached[record_id])}
        cached_b = {record_id: copy.deepcopy(self.cached[record_id])}
        cached_b[record_id].intent_summary = "a different summary entirely"

        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            summary_a = self._run(Path(tmpdir1) / "run", records, cached=cached_a)
            summary_b = self._run(Path(tmpdir2) / "run", records, cached=cached_b)
        self.assertNotEqual(summary_a["input_manifest_hash"], summary_b["input_manifest_hash"])

    def test_changing_label_eligibility_changes_manifest_hash(self) -> None:
        base = self.inputs[0]
        different_eligibility = SystemInput(
            record_id=base.record_id,
            command=base.command,
            dialogue_history=base.dialogue_history,
            scene_context=base.scene_context,
            capability_context=base.capability_context,
            input_provenance=base.input_provenance,
            label_eligibility=None,
            protected_data=base.protected_data,
        )
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            manifest_a = self._run(Path(tmpdir1) / "run", [base])["input_manifest_hash"]
            manifest_b = self._run(Path(tmpdir2) / "run", [different_eligibility])["input_manifest_hash"]
        self.assertNotEqual(manifest_a, manifest_b)

    def test_identical_reruns_produce_identical_manifest_hash(self) -> None:
        records = self.inputs[:3]
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            manifest_a = self._run(Path(tmpdir1) / "run", records)["input_manifest_hash"]
            manifest_b = self._run(Path(tmpdir2) / "run", records)["input_manifest_hash"]
        self.assertEqual(manifest_a, manifest_b)


class ResumeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = _load_inputs()
        cls.cached = _load_cached_analyses()

    def test_resume_with_grown_record_set_succeeds(self) -> None:
        records = self.inputs[:2]
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=records[:1],
                cached_analyses=self.cached,
                output_dir=output_dir,
            )
            summary = runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=records,
                cached_analyses=self.cached,
                output_dir=output_dir,
                resume=True,
            )
        self.assertEqual(summary["completed_keys"], 2)

    def test_resume_refuses_when_completed_record_input_changed(self) -> None:
        records = self.inputs[:2]
        record_id = records[0].record_id
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=records[:1],
                cached_analyses=self.cached,
                output_dir=output_dir,
            )
            tampered = SystemInput(
                record_id=record_id,
                command="This is not the original command at all.",
                scene_context=records[0].scene_context,
                capability_context=records[0].capability_context,
                input_provenance=records[0].input_provenance,
                label_eligibility=records[0].label_eligibility,
            )
            with self.assertRaises(ResumeContractError):
                runner.run(
                    config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                    records=[tampered, records[1]],
                    cached_analyses=self.cached,
                    output_dir=output_dir,
                    resume=True,
                )

    def test_resume_refuses_when_existing_result_hash_corrupted(self) -> None:
        records = self.inputs[:1]
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=records,
                cached_analyses=self.cached,
                output_dir=output_dir,
            )
            results_path = output_dir / "results.jsonl"
            rows = _read_jsonl(results_path)
            rows[0]["result_hash"] = "0" * 64
            results_path.write_text(
                "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ResumeContractError):
                runner.run(
                    config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                    records=self.inputs[:2],
                    cached_analyses=self.cached,
                    output_dir=output_dir,
                    resume=True,
                )

    def test_resume_refuses_when_config_changes(self) -> None:
        records = self.inputs[:1]
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"], config_id="a"),
                records=records,
                cached_analyses=self.cached,
                output_dir=output_dir,
            )
            with self.assertRaises(ResumeContractError):
                runner.run(
                    config=_config(run_mode="synthetic_smoke", systems=["always_execute"], config_id="b"),
                    records=records,
                    cached_analyses=self.cached,
                    output_dir=output_dir,
                    resume=True,
                )

    def test_resume_refuses_when_completed_record_dropped_from_new_call(self) -> None:
        records = self.inputs[:2]
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=records,
                cached_analyses=self.cached,
                output_dir=output_dir,
            )
            with self.assertRaises(ResumeContractError):
                runner.run(
                    config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                    records=records[:1],
                    cached_analyses=self.cached,
                    output_dir=output_dir,
                    resume=True,
                )


class VerifyRunCorruptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = _load_inputs()
        cls.cached = _load_cached_analyses()

    def _fresh_run(self, output_dir: Path):
        records = self.inputs[:3]
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})
        runner.run(
            config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
            records=records,
            cached_analyses=self.cached,
            output_dir=output_dir,
        )
        return runner

    def test_clean_run_verifies_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner = self._fresh_run(output_dir)
            report = runner.verify_run(output_dir)
            self.assertTrue((output_dir / "verification_report.json").is_file())
        self.assertTrue(report["ok"])
        self.assertTrue(all(report["checks"].values()))

    def test_changed_field_in_result_row_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner = self._fresh_run(output_dir)
            results_path = output_dir / "results.jsonl"
            rows = _read_jsonl(results_path)
            rows[0]["execution_status"] = "failed"
            results_path.write_text(
                "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n",
                encoding="utf-8",
            )
            report = runner.verify_run(output_dir)
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["all_result_hashes_valid"])

    def test_changed_result_hash_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner = self._fresh_run(output_dir)
            results_path = output_dir / "results.jsonl"
            rows = _read_jsonl(results_path)
            rows[0]["result_hash"] = "f" * 64
            results_path.write_text(
                "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n",
                encoding="utf-8",
            )
            report = runner.verify_run(output_dir)
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["all_result_hashes_valid"])
        self.assertIn(report["result_hash_mismatches"][0], report["result_hash_mismatches"])

    def test_missing_row_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner = self._fresh_run(output_dir)
            results_path = output_dir / "results.jsonl"
            rows = _read_jsonl(results_path)
            results_path.write_text(
                "\n".join(json.dumps(r, sort_keys=True) for r in rows[1:]) + "\n",
                encoding="utf-8",
            )
            report = runner.verify_run(output_dir)
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["no_missing_results"])
        self.assertTrue(report["missing_result_keys"])

    def test_extra_row_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner = self._fresh_run(output_dir)
            results_path = output_dir / "results.jsonl"
            rows = _read_jsonl(results_path)
            extra = copy.deepcopy(rows[0])
            extra["record_id"] = "not_a_real_record"
            extra_result = SystemResult.from_dict(extra)
            extra_result.record_id = "not_a_real_record"
            extra = extra_result.with_computed_hash().to_dict()
            extra["run_id"] = rows[0]["run_id"]
            extra["run_mode"] = rows[0]["run_mode"]
            rows.append(extra)
            results_path.write_text(
                "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n",
                encoding="utf-8",
            )
            report = runner.verify_run(output_dir)
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["no_extra_results"])
        self.assertTrue(report["extra_result_keys"])

    def test_modified_input_manifest_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner = self._fresh_run(output_dir)
            manifest_path = output_dir / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["input_manifest"]["records"][0]["input"]["command"] = "tampered command"
            manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
            report = runner.verify_run(output_dir)
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["input_manifest_hash_valid"])
        self.assertFalse(report["checks"]["manifest_hash_valid"])

    def test_wrong_summary_count_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner = self._fresh_run(output_dir)
            summary_path = output_dir / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["results_written"] = summary["results_written"] + 5
            summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
            report = runner.verify_run(output_dir)
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["results_written_consistent"])
        self.assertFalse(report["checks"]["summary_file_hash_valid"])

    def test_wrong_results_file_hash_recorded_in_manifest_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner = self._fresh_run(output_dir)
            manifest_path = output_dir / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["results_file"]["sha256"] = "a" * 64
            manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
            report = runner.verify_run(output_dir)
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["results_file_hash_valid"])
        # Editing the manifest without recomputing manifest_hash must also
        # surface as a manifest integrity failure.
        self.assertFalse(report["checks"]["manifest_hash_valid"])

    def test_duplicate_rows_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner = self._fresh_run(output_dir)
            results_path = output_dir / "results.jsonl"
            rows = _read_jsonl(results_path)
            rows.append(copy.deepcopy(rows[0]))
            results_path.write_text(
                "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n",
                encoding="utf-8",
            )
            report = runner.verify_run(output_dir)
        self.assertFalse(report["ok"])
        self.assertFalse(report["checks"]["no_duplicate_results"])
        self.assertEqual(report["duplicates"], 1)


if __name__ == "__main__":
    unittest.main()
