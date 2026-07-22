"""Result-status and RunContext approval tests for T23/T24.

Covers runner-owned synthetic/development/official semantics, evaluator
status inheritance, mixed-status rejection, and verify_run corruption
detection for run flags and context-blind cache substitution.
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

from ambiguity_manager.evaluation.evaluator import (  # noqa: E402
    DeterministicEvaluator,
    GoldRecord,
    PredictionRecord,
)
from ambiguity_manager.schema.v2.taxonomies import RouteLabel  # noqa: E402
from ambiguity_manager.systems.analysis import build_analysis_identity  # noqa: E402
from ambiguity_manager.systems.contracts import (  # noqa: E402
    AnalysisProvenance,
    InputProvenance,
    StructuredAnalysis,
    SystemInput,
    SystemResult,
)
from ambiguity_manager.systems.errors import (  # noqa: E402
    EvaluationContractError,
    OfficialRunBlockedError,
)
from ambiguity_manager.systems.execution import (  # noqa: E402
    ExperimentRunner,
    OfficialPrerequisites,
    RunContext,
)
from ambiguity_manager.systems.variants import SYSTEM_IDS  # noqa: E402

FIXTURES_DIR = ROOT / "tests" / "fixtures" / "t16_t24_synthetic"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _config(*, run_mode: str, systems: list[str], config_id: str = "status_test") -> dict:
    return {"config_id": config_id, "run_mode": run_mode, "systems": systems}


class StubSystem:
    def __init__(
        self,
        system_id: str,
        *,
        set_synthetic_only: bool = True,
        set_official_result: bool = False,
        system_version: str = "stub-1.0.0",
    ) -> None:
        self.system_id = system_id
        self.system_version = system_version
        self.provider = object()
        self._set_synthetic_only = set_synthetic_only
        self._set_official_result = set_official_result

    def run(
        self,
        system_input: SystemInput,
        *,
        cached_analysis: StructuredAnalysis | None = None,
    ) -> SystemResult:
        analysis = copy.deepcopy(cached_analysis) if cached_analysis is not None else StructuredAnalysis()
        return SystemResult(
            record_id=system_input.record_id,
            system_id=self.system_id,
            system_version=self.system_version,
            analysis=analysis,
            recommended_strategy=RouteLabel.EXECUTE,
            execution_status="ok",
            synthetic_only=self._set_synthetic_only,
            official_result=self._set_official_result,
        ).with_computed_hash()


def _non_synthetic_record(record_id: str = "real_1") -> SystemInput:
    return SystemInput(
        record_id=record_id,
        command="Pick up the mug.",
        input_provenance=InputProvenance(source="teach_derived"),
    )


def _synthetic_record(record_id: str = "syn_1") -> SystemInput:
    return SystemInput(
        record_id=record_id,
        command="Pick up the mug.",
        input_provenance=InputProvenance(source="synthetic"),
    )


def _prediction(
    *,
    record_id: str = "r1",
    system_id: str = "always_execute",
    synthetic_only: bool = True,
    official_result: bool = False,
    run_mode: str = "synthetic_smoke",
    run_id: str = "run-1",
) -> PredictionRecord:
    payload = {
        "record_id": record_id,
        "system_id": system_id,
        "system_version": "1.0.0",
        "analysis": {"speech_act": "directive_command"},
        "recommended_strategy": "execute",
        "execution_status": "ok",
        "synthetic_only": synthetic_only,
        "official_result": official_result,
        "run_mode": run_mode,
        "run_id": run_id,
    }
    return PredictionRecord.from_dict(payload)


def _gold(record_id: str = "r1") -> GoldRecord:
    return GoldRecord.from_dict(
        {
            "record_id": record_id,
            "speech_act": "directive_command",
            "label_eligibility": {"intent_slots": True, "routing": True},
        }
    )


class RunStatusSemanticsTests(unittest.TestCase):
    def test_synthetic_run_flags(self) -> None:
        stub = StubSystem("always_execute", set_synthetic_only=False, set_official_result=True)
        runner = ExperimentRunner(registry={"always_execute": stub})
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=[_synthetic_record()],
                output_dir=Path(tmpdir) / "run",
            )
            rows = _read_jsonl(Path(tmpdir) / "run" / "results.jsonl")
        self.assertTrue(summary["synthetic_only"])
        self.assertFalse(summary["official_result"])
        self.assertTrue(rows[0]["synthetic_only"])
        self.assertFalse(rows[0]["official_result"])

    def test_development_non_synthetic_flags(self) -> None:
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = runner.run(
                config=_config(run_mode="development", systems=["always_execute"]),
                records=[_non_synthetic_record()],
                output_dir=Path(tmpdir) / "run",
            )
        self.assertFalse(summary["synthetic_only"])
        self.assertFalse(summary["official_result"])

    def test_development_synthetic_fixture_flags(self) -> None:
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = runner.run(
                config=_config(run_mode="development", systems=["always_execute"]),
                records=[_synthetic_record()],
                output_dir=Path(tmpdir) / "run",
            )
        self.assertTrue(summary["synthetic_only"])
        self.assertFalse(summary["official_result"])

    def test_official_missing_prerequisites_blocks_with_no_result_rows(self) -> None:
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            with self.assertRaises(OfficialRunBlockedError):
                runner.run(
                    config=_config(run_mode="official", systems=["always_execute"]),
                    records=[_non_synthetic_record()],
                    prerequisites=OfficialPrerequisites(),
                    output_dir=output_dir,
                )
            self.assertFalse((output_dir / "results.jsonl").exists())

    def test_approved_official_context_after_satisfied_gates(self) -> None:
        # Hypothetical fully satisfied official gate using temporary test doubles.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            gold = tmp / "gold.jsonl"
            gold.write_text('{"record_id":"x"}\n', encoding="utf-8")
            split = tmp / "split.json"
            split.write_text("{}", encoding="utf-8")
            prereq = OfficialPrerequisites(
                adjudicated_gold_dataset=gold,
                t15_split_manifest=split,
                protocol_freeze_identifier="freeze-test-1",
                handbook_version="hb-test-1",
                selected_model_strategy=None,
                selected_base_model=None,
                selected_adapter=None,
            )
            # pending -> gates -> approved
            pending = RunContext.pending_official()
            self.assertFalse(pending.approved)
            self.assertFalse(pending.official_result)

            # Capability-free stub systems that do not require model strategy.
            stub = StubSystem("always_execute")
            runner = ExperimentRunner(registry={"always_execute": stub})
            # Always-execute requires approved provenance in official mode.
            # Satisfy via a provenance-approved cached analysis double.
            from ambiguity_manager.systems.capabilities import is_provenance_approved

            analysis = StructuredAnalysis(
                analysis_provenance=AnalysisProvenance(
                    provider_id="approved_cache",
                    method="deterministic",
                    notes="approved_for_official_test",
                )
            )
            # If provenance approval is strict, bypass by checking what is_provenance_approved needs.
            _ = is_provenance_approved
            # Use a minimal registry override path: run with empty capabilities check by
            # exercising approved_official factory directly for the status contract,
            # and separately confirm runner produces official_result when gates pass.
            approved = RunContext.approved_official()
            self.assertTrue(approved.approved)
            self.assertFalse(approved.synthetic_only)
            self.assertTrue(approved.official_result)

            # Monkey-patch check_official_gates to simulate all gates passing.
            original = runner.check_official_gates

            def _ok(**kwargs):  # noqa: ANN003
                return None

            runner.check_official_gates = _ok  # type: ignore[method-assign]
            from ambiguity_manager.systems.analysis_cache import migrate_legacy_cache

            record = _non_synthetic_record()
            typed_cache = migrate_legacy_cache(
                {"real_1": analysis},
                records=[record],
                analysis_variant="full_context",
            )
            try:
                summary = runner.run(
                    config=_config(run_mode="official", systems=["always_execute"]),
                    records=[record],
                    cached_analyses=typed_cache,
                    prerequisites=prereq,
                    output_dir=tmp / "official_run",
                )
            finally:
                runner.check_official_gates = original  # type: ignore[method-assign]

            rows = _read_jsonl(tmp / "official_run" / "results.jsonl")
            self.assertFalse(summary["synthetic_only"])
            self.assertTrue(summary["official_result"])
            self.assertFalse(rows[0]["synthetic_only"])
            self.assertTrue(rows[0]["official_result"])
            self.assertEqual(rows[0]["run_mode"], "official")
            manifest = json.loads((tmp / "official_run" / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["run_context"]["official_result"])
            self.assertTrue(manifest["run_context"]["approved"])

    def test_adapters_cannot_override_run_context_flags(self) -> None:
        stub = StubSystem("always_execute", set_synthetic_only=False, set_official_result=True)
        runner = ExperimentRunner(registry={"always_execute": stub})
        with tempfile.TemporaryDirectory() as tmpdir:
            runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=[_synthetic_record()],
                output_dir=Path(tmpdir) / "run",
            )
            rows = _read_jsonl(Path(tmpdir) / "run" / "results.jsonl")
        self.assertTrue(rows[0]["synthetic_only"])
        self.assertFalse(rows[0]["official_result"])

    def test_evaluator_bundle_preserves_run_flags(self) -> None:
        ctx = RunContext.for_run_mode("development", synthetic_inputs=False)
        pred = _prediction(
            synthetic_only=False,
            official_result=False,
            run_mode="development",
        )
        bundle = DeterministicEvaluator().evaluate([_gold()], [pred], run_context=ctx)
        assert not isinstance(bundle, dict)
        self.assertFalse(bundle.synthetic_only)
        self.assertFalse(bundle.official_result)
        self.assertEqual(bundle.run_mode, "development")

    def test_seven_system_evaluation_preserves_identical_run_flags(self) -> None:
        ctx = RunContext.for_run_mode("synthetic_smoke")
        preds = [
            _prediction(system_id=sid, record_id="r1")
            for sid in SYSTEM_IDS
        ]
        bundles = DeterministicEvaluator().evaluate_all_systems(
            [_gold()], preds, run_context=ctx
        )
        self.assertEqual(len(bundles), 7)
        for sid, bundle in bundles.items():
            self.assertTrue(bundle.synthetic_only, msg=sid)
            self.assertFalse(bundle.official_result, msg=sid)
            self.assertEqual(bundle.run_mode, "synthetic_smoke", msg=sid)

    def test_mixed_run_mode_results_are_rejected(self) -> None:
        preds = [
            _prediction(system_id="always_execute", run_mode="synthetic_smoke"),
            _prediction(system_id="always_clarify", run_mode="development", synthetic_only=False),
        ]
        with self.assertRaises(EvaluationContractError):
            DeterministicEvaluator().evaluate([_gold()], preds)

    def test_corrupted_official_result_caught_by_verify_run(self) -> None:
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=[_synthetic_record()],
                output_dir=output_dir,
            )
            results_path = output_dir / "results.jsonl"
            rows = _read_jsonl(results_path)
            rows[0]["official_result"] = True
            rows[0]["result_hash"] = SystemResult.from_dict(rows[0]).compute_hash()
            results_path.write_text(
                json.dumps(rows[0], sort_keys=True) + "\n", encoding="utf-8"
            )
            # Refresh file hashes in manifest so hash check doesn't mask flag check.
            manifest_path = output_dir / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            from ambiguity_manager.systems.hashing import sha256_hex, sha256_json

            results_bytes = results_path.read_bytes()
            manifest["results_file"] = {
                "sha256": sha256_hex(results_bytes),
                "size_bytes": len(results_bytes),
            }
            manifest["manifest_hash"] = sha256_json(
                {k: v for k, v in manifest.items() if k != "manifest_hash"}
            )
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            report = runner.verify_run(output_dir)
            self.assertFalse(report["ok"])
            self.assertFalse(report["checks"]["flag_consistency"])

    def test_official_result_cannot_be_produced_from_synthetic_inputs(self) -> None:
        stub = StubSystem("always_execute")
        runner = ExperimentRunner(registry={"always_execute": stub})

        def _ok(**kwargs):  # noqa: ANN003
            return None

        runner.check_official_gates = _ok  # type: ignore[method-assign]
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(OfficialRunBlockedError) as ctx:
                runner.run(
                    config=_config(run_mode="official", systems=["always_execute"]),
                    records=[_synthetic_record()],
                    output_dir=Path(tmpdir) / "run",
                )
            self.assertTrue(
                any("synthetic" in item for item in ctx.exception.missing)
            )
            self.assertFalse((Path(tmpdir) / "run" / "results.jsonl").exists())

    def test_official_status_not_inferred_from_gold_alone(self) -> None:
        # Gold exists, but without a verified official run context the bundle
        # must remain non-official.
        gold = [_gold()]
        pred = _prediction(synthetic_only=True, official_result=False, run_mode="synthetic_smoke")
        bundle = DeterministicEvaluator().evaluate(gold, [pred])
        assert not isinstance(bundle, dict)
        self.assertTrue(bundle.synthetic_only)
        self.assertFalse(bundle.official_result)
        self.assertNotEqual(bundle.run_mode, "official")


class CacheManifestAndVerifierTests(unittest.TestCase):
    def test_cache_manifest_records_variant_and_source_input_hash(self) -> None:
        runner = ExperimentRunner(registry={"always_execute": StubSystem("always_execute")})
        record = _non_synthetic_record("cache_1")
        analysis = StructuredAnalysis(
            analysis_provenance=AnalysisProvenance(
                provider_id="full_context_provider",
                method="full_context",
            )
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            runner.run(
                config=_config(run_mode="development", systems=["always_execute"]),
                records=[record],
                cached_analyses={"cache_1": analysis},
                output_dir=Path(tmpdir) / "run",
            )
            manifest = json.loads(
                (Path(tmpdir) / "run" / "input_manifest.json").read_text(encoding="utf-8")
            )
        entry = manifest["records"][0]
        self.assertEqual(entry["analysis_variant"], "full_context")
        self.assertEqual(entry["source_input_hash"], record.fingerprint())
        self.assertEqual(
            entry["analysis_identity"]["analysis_content_hash"],
            analysis.fingerprint(),
        )

    def test_context_blind_cache_substitution_fails_verification(self) -> None:
        from ambiguity_manager.systems.variants import ContextBlindManagerSystem
        from ambiguity_manager.systems.manager import FullManager
        from ambiguity_manager.systems.providers import DeterministicAnalysisProvider
        from ambiguity_manager.schema.v2.records import UnresolvedSlot
        from ambiguity_manager.schema.v2.taxonomies import CapabilityStatus, RiskLevel
        from ambiguity_manager.schema.v2.records import CPC, CPCSlot
        from ambiguity_manager.schema.v2.taxonomies import CPCSlotStatus

        def _cpc(**filled: str) -> CPC:
            c = CPC.empty_unknown()
            for key, value in filled.items():
                setattr(c, key, CPCSlot(value=value, status=CPCSlotStatus.FILLED))
            return c

        record = SystemInput(
            record_id="cb_1",
            command="Pick it up.",
            scene_context="user pointed to the red cup",
            input_provenance=InputProvenance(source="synthetic"),
        )
        ablated = record.without_context()
        blind_analysis = StructuredAnalysis(
            speech_act="directive_command",
            cpc=_cpc(action="pick"),
            unresolved_slots=[UnresolvedSlot(slot_name="object", reason="no_scene")],
            risk_level=RiskLevel.LOW,
            capability_status=CapabilityStatus.CAPABLE,
            analysis_provenance=AnalysisProvenance(
                provider_id="context_blind_cache",
                method="context_blind",
                analysis_id=ablated.fingerprint(),
                notes=f"ablated_input_hash={ablated.fingerprint()}",
            ),
        )
        provider = DeterministicAnalysisProvider({"cb_1": blind_analysis})
        system = ContextBlindManagerSystem(
            analysis_provider=provider,
            inner=FullManager(analysis_provider=provider),
        )
        runner = ExperimentRunner(registry={"context_blind_manager": system})
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["context_blind_manager"]),
                records=[record],
                cached_analyses={"cb_1": blind_analysis},
                output_dir=output_dir,
            )
            # Corrupt: claim the executed analysis was full_context.
            results_path = output_dir / "results.jsonl"
            rows = _read_jsonl(results_path)
            meta = rows[0].setdefault("runtime_metadata", {})
            identity = meta.setdefault("analysis_identity", {})
            identity["analysis_variant"] = "full_context"
            rows[0]["result_hash"] = SystemResult.from_dict(rows[0]).compute_hash()
            results_path.write_text(
                json.dumps(rows[0], sort_keys=True) + "\n", encoding="utf-8"
            )
            from ambiguity_manager.systems.hashing import sha256_hex, sha256_json

            manifest_path = output_dir / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            results_bytes = results_path.read_bytes()
            manifest["results_file"] = {
                "sha256": sha256_hex(results_bytes),
                "size_bytes": len(results_bytes),
            }
            manifest["manifest_hash"] = sha256_json(
                {k: v for k, v in manifest.items() if k != "manifest_hash"}
            )
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            report = runner.verify_run(output_dir)
            self.assertFalse(report["ok"])
            self.assertFalse(report["checks"]["context_blind_analysis_identity_consistent"])

    def test_manifest_corruption_of_variant_or_hash_fails_verification(self) -> None:
        runner = ExperimentRunner(registry={"always_execute": StubSystem("always_execute")})
        record = _synthetic_record("m1")
        analysis = StructuredAnalysis(
            analysis_provenance=AnalysisProvenance(provider_id="p", method="full_context")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "run"
            runner.run(
                config=_config(run_mode="synthetic_smoke", systems=["always_execute"]),
                records=[record],
                cached_analyses={"m1": analysis},
                output_dir=output_dir,
            )
            from ambiguity_manager.systems.hashing import sha256_json

            for field, value in (
                ("analysis_variant", "context_blind"),
                ("source_input_hash", "0" * 64),
                ("analysis_content_hash", "1" * 64),
            ):
                with self.subTest(field=field):
                    manifest_path = output_dir / "run_manifest.json"
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    corrupted = copy.deepcopy(manifest)
                    corrupted["input_manifest"]["records"][0][field] = value
                    if field in corrupted["input_manifest"]["records"][0].get(
                        "analysis_identity", {}
                    ):
                        corrupted["input_manifest"]["records"][0]["analysis_identity"][field] = value
                    corrupted["input_manifest_hash"] = sha256_json(corrupted["input_manifest"])
                    corrupted["manifest_hash"] = sha256_json(
                        {k: v for k, v in corrupted.items() if k != "manifest_hash"}
                    )
                    manifest_path.write_text(
                        json.dumps(corrupted, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    # Standalone file must also be corrupted or file-consistency fails first.
                    (output_dir / "input_manifest.json").write_text(
                        json.dumps(
                            corrupted["input_manifest"], indent=2, sort_keys=True
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    report = runner.verify_run(output_dir)
                    # Corrupting variant/hash changes input_manifest content vs
                    # record_identity fingerprints / recomputation expectations.
                    self.assertFalse(report["ok"])


if __name__ == "__main__":
    unittest.main()
