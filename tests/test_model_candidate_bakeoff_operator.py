"""CPU-only tests for model-candidate bake-off provider and operator integration."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from ambiguity_manager.model.base_model_candidates import ALLOWLISTED_CANDIDATE_IDS
from ambiguity_manager.model.bakeoff_provider import (
    BAKEOFF_EVIDENCE,
    PREFLIGHT_EVIDENCE,
    TRANSPORT_EVIDENCE,
    BakeoffProviderError,
    assert_prompt_contract_same_across_candidates,
    check_provider_available,
    load_bakeoff_prompt_contract,
    load_bakeoff_runtime_config,
    pipeline_request_from_development_record,
    prompt_contract_hash_for_candidate,
    run_candidate_preflight,
    run_transport_smoke,
    validate_candidate_id,
)
from ambiguity_manager.model.cluster.job_operator import (
    ClusterJobOperator,
    OperatorError,
    ensure_no_forbidden_tokens,
    get_profile,
    load_profiles,
    render_profile_entry_args,
    validate_candidate_id as operator_validate_candidate_id,
)
from ambiguity_manager.model.generation_pipeline import (
    GenerationPipelineResult,
    PipelineFinalStatus,
)
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.ssh_responses: list[subprocess.CompletedProcess[str]] = []
        self.git_map: dict[tuple[str, ...], subprocess.CompletedProcess[str]] = {}
        self.default_ssh = subprocess.CompletedProcess(["ssh"], 0, stdout="ok\n", stderr="")

    def __call__(self, cmd: list[str], kwargs=None) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(cmd))
        if cmd and cmd[0] == "git":
            args = tuple(cmd[3:])
            if args in self.git_map:
                return self.git_map[args]
            if args and args[0] == "archive":
                output = None
                for part in args:
                    if part.startswith("--output="):
                        output = Path(part.split("=", 1)[1])
                if output is not None:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(b"fake-archive")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd and cmd[0] == "ssh":
            if self.ssh_responses:
                return self.ssh_responses.pop(0)
            return self.default_ssh
        if cmd and cmd[0] == "scp":
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


class FakeGenerator:
    def __init__(self, *_args, **_kwargs) -> None:
        self.generate_calls = 0

    def generate(self, *_args, **_kwargs):
        from ambiguity_manager.model.generation_pipeline import GeneratorOutput

        self.generate_calls += 1
        return GeneratorOutput(
            raw_output='{"speech_act":"directive_command","intent_summary":"ok","cpc":{"frame_id":"f1","action":"pick","object":"mug","destination":null,"manner":null,"attributes":[],"confidence":"unknown"},"candidate_interpretations":[],"selected_interpretation":null,"unresolved_slots":[],"supporting_evidence":[],"ambiguity_present":false,"ambiguity_types":[],"primary_ambiguity_type":null,"compound_ambiguity":false,"compound_ambiguity_count":0,"risk_relevant":false,"risk_level":"none","capability_status":"capable","recommended_strategy":"execute","strategy_sequence":["execute"],"clarification_question":null,"clarification_subtype":null,"clarification_targets":[],"rejection_reason":null,"resolved_slots":[],"resolution_method":null,"resolution_evidence":[],"context_sampling_uncertainty":null}',
            generation_status="success",
        )


class FakeBackend:
    lifecycle_state = "started"
    last_structured_decode_metadata = {"unconstrained_fallback_indicated": False}

    def start(self) -> None:
        return None

    def close(self) -> None:
        return None

    def generate_batch(self, requests):
        return []


class ModelCandidateBakeoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self._copy_tree(ROOT / "configs", self.root / "configs")
        env_src = ROOT / "configs" / "environments"
        if env_src.exists():
            self._copy_tree(env_src, self.root / "configs/environments")
        self._copy_tree(ROOT / "data" / "development" / "model_selection_v1", self.root / "data/development/model_selection_v1")
        self._copy_tree(ROOT / "src", self.root / "src")
        (self.root / "scripts").mkdir(parents=True, exist_ok=True)
        for name in (
            "t12_model_candidate_preflight.py",
            "t12_model_candidate_transport_smoke.py",
            "t12_model_candidate_bakeoff.py",
            "t12_cluster_canary.py",
        ):
            src = ROOT / "scripts" / name
            if src.is_file():
                (self.root / "scripts" / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        self.head = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        self.runner = FakeRunner()
        self.runner.git_map = {
            ("branch", "--show-current"): subprocess.CompletedProcess([], 0, stdout="feature/t12-cluster-redesign\n", stderr=""),
            ("diff", "--cached", "--name-only"): subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            ("diff", "--name-only"): subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            ("status", "--porcelain=v1", "--untracked-files=all"): subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            ("rev-parse", "HEAD"): subprocess.CompletedProcess([], 0, stdout=self.head + "\n", stderr=""),
        }

    def _copy_tree(self, src: Path, dest: Path) -> None:
        if not src.exists():
            return
        import shutil

        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)

    def _operator(self, **kwargs) -> ClusterJobOperator:
        return ClusterJobOperator(
            repo_root=self.root,
            runner=self.runner,
            sleep_fn=lambda _s: None,
            **kwargs,
        )

    def _source_manifest(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "source_commit_sha": self.head,
                    "source_archive_sha256": "b" * 64,
                    "transfer_method": "git_archive",
                    "archive_filename": "t12-aaaaaaa.tar.gz",
                    "packaging_timestamp": "2026-07-22T12:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def test_allowlisted_profile_names(self) -> None:
        doc = load_profiles(self.root)
        for name in (
            "model_candidate_preflight",
            "model_candidate_transport_smoke",
            "model_candidate_bakeoff",
        ):
            profile = get_profile(doc, name)
            self.assertTrue(profile["gpus_required"])
            self.assertTrue(profile["requires_candidate_id"])

    def test_allowlisted_candidate_ids(self) -> None:
        self.assertEqual(
            ALLOWLISTED_CANDIDATE_IDS,
            frozenset({"qwen3_8b", "phi4_14b", "mistral_small_24b_2501"}),
        )
        with self.assertRaises(BakeoffProviderError):
            validate_candidate_id("Qwen/Qwen3-8B")
        with self.assertRaises(OperatorError):
            operator_validate_candidate_id("mistral-ai/foo")

    def test_exact_revision_in_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "out"
            manifest = Path(tmp) / "source_identity_manifest.json"
            self._source_manifest(manifest)
            result = run_candidate_preflight(
                candidate_id="qwen3_8b",
                result_dir=result_dir,
                run_id="test-preflight",
                source_commit=self.head,
                source_archive_sha256="c" * 64,
                source_identity_manifest=manifest,
                root=self.root,
                skip_runtime_import_check=True,
                tokenizer_factory=lambda **_k: object(),
            )
            provenance = json.loads((result_dir / "candidate_provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(result["revision"], provenance["revision"])
            self.assertEqual(provenance["revision"], "b968826d9c46dd6066d109eabc6255188de91218")

    def test_run_packages_source_commit(self) -> None:
        op = self._operator()
        profile = get_profile(load_profiles(self.root), "model_candidate_transport_smoke")
        prep_rel = "runs/model-candidate-transport-smoke/.prep-x"
        self.runner.ssh_responses = [
            subprocess.CompletedProcess([], 0, stdout="ok\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout=f"/home/u/t12-hpc/{prep_rel}\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="ARCHIVE_HASH_MATCH\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="9001\n", stderr=""),
        ]
        record = op.run_profile("model_candidate_transport_smoke", candidate_id="qwen3_8b")
        self.assertEqual(record["source_commit_sha"], self.head)
        self.assertEqual(record["candidate_id"], "qwen3_8b")
        sbatch = list((self.root / "outputs/t12_cluster_jobs").rglob("submit.sbatch"))[0].read_text(encoding="utf-8")
        self.assertIn("--candidate-id qwen3_8b", sbatch)
        self.assertIn(profile["remote_result_root_template"].split("/")[-1], sbatch)

    def test_no_secrets_persisted(self) -> None:
        op = self._operator()
        with self.assertRaises(OperatorError):
            op.save_state({"runs": {}, "password": "secret"})

    def test_pull_with_mocked_subprocess(self) -> None:
        run_id = "t12-mc-transport-test"
        remote = f"/home/u/t12-hpc/runs/model-candidate-transport-smoke/{run_id}"

        def runner(cmd, kwargs=None):
            if cmd[0] == "scp":
                dest = Path(cmd[-1])
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "transport_smoke_summary.json").write_text("{}", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[0] == "ssh":
                remote_cmd = cmd[-1]
                if "printf" in remote_cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout=remote + "\n", stderr="")
                if "test -d" in remote_cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout="EXISTS\n", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

        op = ClusterJobOperator(repo_root=self.root, runner=runner, sleep_fn=lambda _s: None)
        op._update_run(
            run_id,
            {
                "run_id": run_id,
                "job_id": "77",
                "profile": "model_candidate_transport_smoke",
                "candidate_id": "qwen3_8b",
                "remote_result_rel_path": f"runs/model-candidate-transport-smoke/{run_id}",
            },
        )
        pulled = op.pull(run_id)
        self.assertTrue((pulled / "transport_smoke_summary.json").is_file())

    def test_verify_detects_corrupt_candidate_evidence(self) -> None:
        op = self._operator()
        run_id = "t12-mc-verify-bad"
        pull = self.root / "outputs/t12_cluster_jobs" / run_id / "pulled"
        pull.mkdir(parents=True)
        summary = pull / "transport_smoke_summary.json"
        summary.write_text(json.dumps({"ok": True}) + "\n", encoding="utf-8")
        files = [
            {
                "relative_path": summary.name,
                "sha256": "0" * 64,
                "size_bytes": summary.stat().st_size,
            }
        ]
        for name in TRANSPORT_EVIDENCE:
            path = pull / name
            if path == summary:
                continue
            if name.endswith(".jsonl"):
                path.write_text("{}\n", encoding="utf-8")
            elif name == "run_manifest.json":
                continue
            else:
                path.write_text("{}\n", encoding="utf-8")
            files.append(
                {
                    "relative_path": name,
                    "sha256": "f" * 64,
                    "size_bytes": 1,
                }
            )
        (pull / "run_manifest.json").write_text(json.dumps({"files": files}) + "\n", encoding="utf-8")
        (pull / "source_identity_manifest.json").write_text("{}", encoding="utf-8")
        op._update_run(
            run_id,
            {
                "run_id": run_id,
                "job_id": "1",
                "profile": "model_candidate_transport_smoke",
                "source_commit_sha": self.head,
                "archive_sha256": "c" * 64,
                "local_pull_path": f"outputs/t12_cluster_jobs/{run_id}/pulled",
                "pulled": True,
            },
        )
        with self.assertRaises(OperatorError):
            op.verify(run_id)

    def test_lazy_import_isolation(self) -> None:
        banned = {"torch", "transformers", "vllm"}
        for name in banned:
            self.assertNotIn(name, sys.modules)
        import ambiguity_manager.model.cluster.job_operator as operator_mod
        import ambiguity_manager.model.bakeoff_provider as provider_mod

        self.assertTrue(operator_mod.__name__.endswith("job_operator"))
        self.assertTrue(provider_mod.__name__.endswith("bakeoff_provider"))
        for name in banned:
            self.assertNotIn(name, sys.modules)

    def test_provider_unavailable_handled_honestly(self) -> None:
        with mock.patch.dict(sys.modules, {"vllm": None}):
            availability = check_provider_available()
        if availability.available:
            self.skipTest("vLLM present in environment")
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "out"
            manifest = Path(tmp) / "source_identity_manifest.json"
            self._source_manifest(manifest)
            summary = run_transport_smoke(
                candidate_id="qwen3_8b",
                result_dir=result_dir,
                run_id="transport-blocked",
                source_commit=self.head,
                source_archive_sha256="d" * 64,
                source_identity_manifest=manifest,
                root=self.root,
            )
            self.assertEqual(summary["status"], "blocked")
            self.assertEqual(summary["reason"], "provider_unavailable")

    def test_prompt_contract_same_across_candidates(self) -> None:
        record = json.loads(
            (self.root / "data/development/model_selection_v1/inputs.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()[0]
        )
        assert_prompt_contract_same_across_candidates(record=record)
        hashes = {
            candidate_id: prompt_contract_hash_for_candidate(record=record)
            for candidate_id in ALLOWLISTED_CANDIDATE_IDS
        }
        self.assertEqual(len(set(hashes.values())), 1)

    def test_full_and_context_blind_inputs_differ(self) -> None:
        record = json.loads(
            (self.root / "data/development/model_selection_v1/inputs.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()[1]
        )
        runtime = load_bakeoff_runtime_config(self.root)
        from ambiguity_manager.model.base_model_candidates import load_base_model_candidate_registry

        candidate = load_base_model_candidate_registry(self.root / "configs/model/base_model_candidates_v1.json").get_candidate(
            "qwen3_8b"
        )
        full = pipeline_request_from_development_record(
            record, candidate=candidate, runtime_config=runtime, analysis_variant="full_context"
        )
        blind = pipeline_request_from_development_record(
            record, candidate=candidate, runtime_config=runtime, analysis_variant="context_blind"
        )
        self.assertIsNotNone(full.scene_context)
        self.assertIsNone(blind.scene_context)

    def test_raw_attempts_retained_in_transport_smoke(self) -> None:
        from ambiguity_manager.model.attempt_evidence import AttemptEvidenceEntry, AttemptKind
        from ambiguity_manager.model.bakeoff_provider import _collect_attempt_rows

        attempt = AttemptEvidenceEntry(
            caller_request_id="bakeoff:full_context:msel_t12_syn_001",
            attempt_index=0,
            attempt_kind=AttemptKind.INITIAL.value,
            prompt_message_hash=None,
            rendered_prompt_hash=None,
            repair_prompt_hash=None,
            response_mode_identity=None,
            response_mode_status=None,
            structured_decode_contract_hash=None,
            semantic_schema_hash=None,
            backend_identifier=None,
            backend_configuration_hash=None,
            model_repository="Qwen/Qwen3-8B",
            model_revision="b968826d9c46dd6066d109eabc6255188de91218",
            container_sha=None,
            raw_generated_text='{"speech_act":"directive_command"}',
            generation_status="success",
            json_extraction_status="success",
            generation_error_type=None,
            generation_error_message=None,
            engine_request_id=None,
            finish_reason=None,
            prompt_tokens=None,
            completion_tokens=None,
        )
        pipeline_result = GenerationPipelineResult(
            request_id="bakeoff:full_context:msel_t12_syn_001",
            final_status=PipelineFinalStatus.REJECTED_AFTER_ATTEMPTS.value,
            accepted_canonical_prediction=None,
            attempt_entries=(attempt,),
            attempts_used=1,
            attempts_exhausted=True,
            failure_categories=(),
            failure_reasons=(),
            semantic_schema_hash="a" * 64,
            structured_decode_contract_hash="b" * 64,
            caller_command_hash="c" * 64,
            integrity_context_hash="d" * 64,
            accepted_raw_attempt_index=None,
        )
        raw_rows, _, _, _ = _collect_attempt_rows(
            pipeline_result,
            record_id="msel_t12_syn_001",
            variant="full_context",
        )
        self.assertEqual(len(raw_rows), 1)
        self.assertEqual(raw_rows[0]["raw_output"], '{"speech_act":"directive_command"}')

    def test_provenance_complete_in_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "out"
            manifest = Path(tmp) / "source_identity_manifest.json"
            self._source_manifest(manifest)
            run_candidate_preflight(
                candidate_id="phi4_14b",
                result_dir=result_dir,
                run_id="preflight-prov",
                source_commit=self.head,
                source_archive_sha256="f" * 64,
                source_identity_manifest=manifest,
                root=self.root,
                skip_runtime_import_check=True,
                tokenizer_factory=lambda **_k: type("Tok", (), {"apply_chat_template": lambda *_a, **_k: "prompt"})(),
            )
            provenance = json.loads((result_dir / "candidate_provenance.json").read_text(encoding="utf-8"))
            for key in (
                "provider_id",
                "provider_version",
                "candidate_id",
                "checkpoint_identity",
                "runtime_config_hash",
                "prompt_contract_id",
                "semantic_schema_hash",
                "selected_adapter",
                "selected_model_strategy",
            ):
                self.assertIn(key, provenance)
            self.assertIsNone(provenance["selected_adapter"])
            self.assertIsNone(provenance["selected_model_strategy"])

    def test_no_unconstrained_fallback_flag_in_runtime(self) -> None:
        runtime = load_bakeoff_runtime_config(self.root)
        self.assertFalse(runtime.attempt_bounds["unconstrained_fallback_permitted"])
        prompt = load_bakeoff_prompt_contract(self.root)
        self.assertFalse(prompt.valid_for_official_use)

    def test_gpu_sbatch_avoids_destructive_patterns(self) -> None:
        op = self._operator()
        profile = get_profile(load_profiles(self.root), "model_candidate_preflight")
        text = op._render_sbatch(
            profile=profile,
            run_id="t12-mc-preflight-test",
            head_sha=self.head,
            archive_sha="d" * 64,
            archive_filename="t12-aaaaaaa.tar.gz",
            candidate_id="qwen3_8b",
        )
        ensure_no_forbidden_tokens(text)
        self.assertNotIn("rm -rf", text)
        self.assertNotIn("set -euo pipefail", text)
        self.assertIn("#SBATCH --gres=gpu:1", text)
        self.assertIn("--candidate-id qwen3_8b", text)

    def test_render_profile_entry_args_rejects_missing_candidate(self) -> None:
        profile = get_profile(load_profiles(self.root), "model_candidate_bakeoff")
        with self.assertRaises(OperatorError):
            render_profile_entry_args(profile, candidate_id=None)

    def test_expected_evidence_file_sets(self) -> None:
        self.assertIn("candidate_provenance.json", PREFLIGHT_EVIDENCE)
        self.assertIn("analysis_outputs.jsonl", TRANSPORT_EVIDENCE)
        self.assertIn("analysis_cache_entries.jsonl", BAKEOFF_EVIDENCE)


if __name__ == "__main__":
    unittest.main()
