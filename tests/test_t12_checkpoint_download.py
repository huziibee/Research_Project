"""Tests for T12 Slice 3B checkpoint download controller."""

from __future__ import annotations

import ast
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ambiguity_manager.governance.ethics import derive_ticket_verdict, validate_ethics_determination
from ambiguity_manager.model.candidate_evidence import REGISTER_REL
from ambiguity_manager.model.checkpoint_download import (
    AUTHORIZED_REPOSITORY_ID,
    AUTHORIZED_REVISION_SHA,
    EVIDENCE_REL,
    EXPECTED_DOWNLOAD_BYTES,
    INCLUDE_PATTERNS,
    MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES,
    MINIMUM_FREE_DISK_BYTES,
    build_scaffold_manifest,
    build_file_inventory,
    cache_dir_is_wsl_native,
    filter_allowed_repo_files,
    manifest_from_dry_run,
    matches_exclude_pattern,
    matches_include_pattern,
    perform_dry_run,
    perform_preflight,
    repo_contains_checkpoint_weights,
    streaming_sha256_hex,
    validate_checkpoint_download_evidence,
    validate_commit_sha,
    validate_download_approval,
    validate_dry_run_before_download,
    validate_no_token_for_ungated,
    validate_repository_id,
    validate_size_tolerance,
    verify_downloaded_snapshot,
    DryRunResult,
    RepoFileEntry,
)
from ambiguity_manager.model.environment import INFERENCE_ENV_REL, TRAINING_ENV_REL
from ambiguity_manager.model.environment_evidence import EVIDENCE_REL as ENV_EVIDENCE_REL
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root
REGISTER_PATH = ROOT / REGISTER_REL
EVIDENCE_PATH = ROOT / EVIDENCE_REL
ETHICS_PATH = ROOT / "configs" / "governance" / "human_annotation_governance.json"
SCRIPT_PATH = ROOT / "scripts" / "t12_download_checkpoint.py"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class _FakeHub:
    def __init__(
        self,
        *,
        files: list[str] | None = None,
        sizes: dict[str, int] | None = None,
        gated: bool = False,
        sha: str = AUTHORIZED_REVISION_SHA,
    ) -> None:
        self.files = files or [
            "config.json",
            "generation_config.json",
            "merges.txt",
            "model.safetensors",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.json",
            "LICENSE",
            "README.md",
            "pytorch_model.bin",
            "onnx/model.onnx",
        ]
        self.sizes = sizes or {name: 100 for name in self.files}
        self.gated = gated
        self.sha = sha

    def model_info(self, repo_id: str, *, revision: str) -> SimpleNamespace:
        return SimpleNamespace(gated=self.gated, sha=self.sha)

    def list_repo_files(self, repo_id: str, *, revision: str) -> list[str]:
        return list(self.files)

    def repo_info(self, repo_id: str, *, revision: str, files_metadata: bool = False) -> SimpleNamespace:
        siblings = [
            SimpleNamespace(rfilename=name, size=self.sizes.get(name, 0))
            for name in self.files
        ]
        return SimpleNamespace(siblings=siblings)


class T12CheckpointDownloadPolicyTests(unittest.TestCase):
    def test_exact_repository_id_required(self) -> None:
        self.assertEqual(validate_repository_id(AUTHORIZED_REPOSITORY_ID), [])
        self.assertTrue(validate_repository_id("other/model"))

    def test_exact_commit_sha_required(self) -> None:
        self.assertEqual(validate_commit_sha(AUTHORIZED_REVISION_SHA, field="revision"), [])
        self.assertTrue(validate_commit_sha("short", field="revision"))

    def test_revision_alias_rejected(self) -> None:
        errors = validate_commit_sha("main", field="revision")
        self.assertTrue(errors)

    def test_third_party_repository_rejected(self) -> None:
        errors = validate_repository_id("TheBloke/Qwen2.5-1.5B-Instruct-GPTQ")
        self.assertTrue(errors)

    def test_gated_candidate_rejected_in_preflight(self) -> None:
        register = _load_json(REGISTER_PATH)
        entry = next(e for e in register["entries"] if e["entry_id"] == "t12-cand-001")
        bad_entry = dict(entry)
        bad_entry["gated_access"] = True
        with mock.patch(
            "ambiguity_manager.model.checkpoint_download.load_register",
            return_value={"selected_model": None, "entries": [bad_entry]},
        ):
            result = perform_preflight(
                ROOT,
                repo_id=AUTHORIZED_REPOSITORY_ID,
                revision=AUTHORIZED_REVISION_SHA,
                cache_dir=Path("/tmp/hf-cache"),
                free_bytes=MINIMUM_FREE_DISK_BYTES,
                cumulative_cache_bytes=0,
            )
        self.assertIn("candidate entry must be ungated", result.errors)

    def test_selected_model_must_remain_null(self) -> None:
        register = _load_json(REGISTER_PATH)
        self.assertIsNone(register["selected_model"])

    def test_dry_run_before_download(self) -> None:
        manifest = build_scaffold_manifest()
        self.assertTrue(validate_dry_run_before_download(manifest))

    def test_download_requires_explicit_approval_flag(self) -> None:
        self.assertTrue(validate_download_approval(approve=False))
        self.assertEqual(validate_download_approval(approve=True), [])

    def test_50_gib_free_disk_gate(self) -> None:
        from ambiguity_manager.model.checkpoint_download import validate_free_disk

        self.assertTrue(validate_free_disk(free_bytes=MINIMUM_FREE_DISK_BYTES - 1))
        self.assertEqual(validate_free_disk(free_bytes=MINIMUM_FREE_DISK_BYTES), [])

    def test_30_gib_cumulative_byte_cap(self) -> None:
        from ambiguity_manager.model.checkpoint_download import validate_cumulative_cap

        self.assertTrue(
            validate_cumulative_cap(
                cumulative_bytes=MAXIMUM_CUMULATIVE_DOWNLOAD_BYTES,
                additional_bytes=1,
            )
        )

    def test_100_mib_estimate_tolerance(self) -> None:
        self.assertEqual(validate_size_tolerance(required_bytes=EXPECTED_DOWNLOAD_BYTES), [])
        self.assertTrue(
            validate_size_tolerance(
                required_bytes=EXPECTED_DOWNLOAD_BYTES + 104_857_601,
            )
        )

    def test_allowlist_correctness(self) -> None:
        self.assertTrue(matches_include_pattern("model.safetensors"))
        self.assertTrue(matches_include_pattern("config.json"))
        self.assertTrue(matches_include_pattern("tokenizer.model"))
        self.assertFalse(matches_include_pattern("modeling_qwen2.py"))

    def test_excluded_format_detection(self) -> None:
        self.assertTrue(matches_exclude_pattern("pytorch_model.bin"))
        self.assertTrue(matches_exclude_pattern("onnx/model.onnx"))
        self.assertTrue(matches_exclude_pattern("weights.gguf"))
        self.assertTrue(matches_exclude_pattern("model-GPTQ.safetensors"))
        self.assertTrue(matches_exclude_pattern("original/model.safetensors"))

    def test_filter_allowed_repo_files(self) -> None:
        files = filter_allowed_repo_files(
            [
                "config.json",
                "model.safetensors",
                "pytorch_model.bin",
                "onnx/model.onnx",
                "README.md",
            ]
        )
        self.assertEqual(set(files), {"config.json", "model.safetensors", "README.md"})

    def test_no_token_accepted_for_ungated_model(self) -> None:
        self.assertEqual(validate_no_token_for_ungated(token=None), [])
        self.assertTrue(validate_no_token_for_ungated(token="hf_secret"))

    def test_no_windows_duplicate_cache(self) -> None:
        self.assertFalse(cache_dir_is_wsl_native(Path("/mnt/c/Users/cache")))
        self.assertFalse(cache_dir_is_wsl_native(Path("C:/Users/cache")))
        self.assertTrue(cache_dir_is_wsl_native(Path("/home/cache/huggingface/hub")))

    def test_no_repository_local_checkpoint_destination(self) -> None:
        violations = repo_contains_checkpoint_weights(ROOT)
        self.assertEqual(violations, [])

    def test_manifest_rejects_usernames_and_absolute_paths(self) -> None:
        manifest = build_scaffold_manifest()
        manifest["note"] = "/home/user/cache"
        errors = validate_checkpoint_download_evidence(manifest)
        self.assertTrue(any("absolute path" in error for error in errors))

    def test_resolved_sha_must_equal_authorised_sha(self) -> None:
        hub = _FakeHub(sha="deadbeef" * 5)
        with self.assertRaises(ValueError) as ctx:
            perform_dry_run(
                hub,
                repo_id=AUTHORIZED_REPOSITORY_ID,
                revision=AUTHORIZED_REVISION_SHA,
                cache_dir=Path("/tmp/cache"),
                file_size_lookup=lambda name: 10,
                cached_file_lookup=lambda name: False,
                cumulative_cache_bytes=0,
            )
        self.assertIn("resolved Hub commit", str(ctx.exception))

    def test_file_inventory_must_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / AUTHORIZED_REVISION_SHA
            snapshot.mkdir()
            for name in ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"):
                (snapshot / name).write_text("x", encoding="utf-8")
            inventory = [
                {"relpath": "config.json", "size_bytes": 1, "sha256": None},
                {"relpath": "model.safetensors", "size_bytes": 1, "sha256": None},
                {"relpath": "tokenizer.json", "size_bytes": 1, "sha256": None},
                {"relpath": "tokenizer_config.json", "size_bytes": 1, "sha256": None},
            ]
            result = verify_downloaded_snapshot(snapshot, dry_run_inventory=inventory)
            self.assertTrue(all(result["required_file_checks"].values()))

            with self.assertRaises(ValueError):
                verify_downloaded_snapshot(
                    snapshot,
                    dry_run_inventory=inventory + [{"relpath": "extra.bin", "size_bytes": 1, "sha256": None}],
                )

    def test_streaming_sha256(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(b"abc" * 10000)
            path = Path(handle.name)
        try:
            digest = streaming_sha256_hex(path, chunk_bytes=128)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
        finally:
            path.unlink(missing_ok=True)

    def test_no_torch_import_required_in_core_module(self) -> None:
        self.assertIsNone(importlib.util.find_spec("torch"))

    def test_checkpoint_load_verified_remains_false(self) -> None:
        for rel in (INFERENCE_ENV_REL, TRAINING_ENV_REL):
            manifest = _load_json(ROOT / rel)
            self.assertFalse(manifest["checkpoint_load_verified"])
        env_evidence = _load_json(ROOT / ENV_EVIDENCE_REL)
        self.assertFalse(env_evidence["checkpoint_load_verified"])

    def test_selected_model_and_candidate_status_unchanged(self) -> None:
        register = _load_json(REGISTER_PATH)
        entry = next(e for e in register["entries"] if e["entry_id"] == "t12-cand-001")
        self.assertIsNone(register["selected_model"])
        self.assertEqual(entry["verification_status"], "candidate_evaluated")

    def test_t11_remains_blocked(self) -> None:
        ethics = _load_json(ETHICS_PATH)
        self.assertEqual(validate_ethics_determination(ethics), [])
        self.assertEqual(derive_ticket_verdict(ethics), "BLOCKED")

    def test_t13_t14_not_started(self) -> None:
        for rel in (
            "docs/reports/ticket_T13_completion_report.md",
            "docs/reports/ticket_T14_completion_report.md",
        ):
            self.assertFalse((ROOT / rel).exists())

    def test_scaffold_manifest_validation_passes(self) -> None:
        manifest = _load_json(EVIDENCE_PATH)
        register = _load_json(REGISTER_PATH)
        errors = validate_checkpoint_download_evidence(manifest, register=register)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_candidate_entry_must_exist_and_be_eligible(self) -> None:
        register = _load_json(REGISTER_PATH)
        result = perform_preflight(
            ROOT,
            repo_id=AUTHORIZED_REPOSITORY_ID,
            revision=AUTHORIZED_REVISION_SHA,
            cache_dir=Path("/tmp/hf-cache"),
            hub=_FakeHub(),
            free_bytes=MINIMUM_FREE_DISK_BYTES,
            cumulative_cache_bytes=0,
        )
        with mock.patch(
            "ambiguity_manager.model.checkpoint_download.is_wsl_linux_runtime",
            return_value=True,
        ):
            result = perform_preflight(
                ROOT,
                repo_id=AUTHORIZED_REPOSITORY_ID,
                revision=AUTHORIZED_REVISION_SHA,
                cache_dir=Path("/tmp/hf-cache"),
                hub=_FakeHub(),
                free_bytes=MINIMUM_FREE_DISK_BYTES,
                cumulative_cache_bytes=0,
            )
        self.assertIn("wsl_runtime", result.checks)


class T12CheckpointDownloadMockedHubTests(unittest.TestCase):
    def test_dry_run_inventory_and_bytes(self) -> None:
        hub = _FakeHub(
            sizes={
                "config.json": 1000,
                "model.safetensors": EXPECTED_DOWNLOAD_BYTES,
                "tokenizer.json": 2000,
                "tokenizer_config.json": 500,
                "generation_config.json": 100,
                "merges.txt": 100,
                "vocab.json": 100,
                "LICENSE": 100,
                "README.md": 100,
            }
        )
        dry_run = perform_dry_run(
            hub,
            repo_id=AUTHORIZED_REPOSITORY_ID,
            revision=AUTHORIZED_REVISION_SHA,
            cache_dir=Path("/tmp/cache"),
            file_size_lookup=lambda name: hub.sizes.get(name, 0),
            cached_file_lookup=lambda name: name == "config.json",
            cumulative_cache_bytes=0,
        )
        self.assertIn("config.json", dry_run.files_already_cached)
        self.assertIn("model.safetensors", dry_run.files_requiring_download)
        self.assertEqual(dry_run.total_required_bytes, sum(hub.sizes[n] for n in dry_run.files_requiring_download))
        manifest = manifest_from_dry_run(dry_run, free_disk_before_bytes=MINIMUM_FREE_DISK_BYTES)
        self.assertEqual(manifest["dry_run_status"], "completed")
        self.assertEqual(manifest["overall_status"], "dry_run_complete")

    def test_build_file_inventory_uses_allowlist(self) -> None:
        hub = _FakeHub()
        inventory = build_file_inventory(
            hub,
            repo_id=AUTHORIZED_REPOSITORY_ID,
            revision=AUTHORIZED_REVISION_SHA,
            file_size_lookup=lambda name: 1,
        )
        names = {entry.relpath for entry in inventory}
        self.assertIn("model.safetensors", names)
        self.assertNotIn("pytorch_model.bin", names)
        self.assertNotIn("onnx/model.onnx", names)

    def test_gated_hub_metadata_rejected(self) -> None:
        hub = _FakeHub(gated=True)
        with self.assertRaises(ValueError) as ctx:
            perform_dry_run(
                hub,
                repo_id=AUTHORIZED_REPOSITORY_ID,
                revision=AUTHORIZED_REVISION_SHA,
                cache_dir=Path("/tmp/cache"),
                file_size_lookup=lambda name: 1,
                cached_file_lookup=lambda name: False,
                cumulative_cache_bytes=0,
            )
        self.assertIn("gated", str(ctx.exception))


class T12CheckpointDownloadScriptImportTests(unittest.TestCase):
    def test_no_model_load_in_script_imports(self) -> None:
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        forbidden = {"torch", "transformers", "peft", "trl"}
        self.assertFalse(forbidden & imported)

    def test_script_has_separate_modes(self) -> None:
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        for command in ("preflight", "dry-run", "download", "verify", "report"):
            self.assertIn(f'"{command}"', source)

    def test_no_automodel_reference_in_script(self) -> None:
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("AutoModelForCausalLM", source)
        self.assertNotIn("from_pretrained", source)


class T12CheckpointDownloadIntegrationTests(unittest.TestCase):
    @mock.patch("scripts.t12_download_checkpoint._build_hub_client")
    @mock.patch("scripts.t12_download_checkpoint.perform_preflight")
    def test_download_command_rejects_without_approval(
        self,
        mock_preflight: mock.Mock,
        mock_hub: mock.Mock,
    ) -> None:
        spec = importlib.util.spec_from_file_location("t12_download_checkpoint", SCRIPT_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        parser = module.build_parser()
        args = parser.parse_args(["download"])
        exit_code = module.cmd_download(args)
        self.assertEqual(exit_code, 1)
        mock_preflight.assert_not_called()

    def test_normal_package_import_remains_ml_free(self) -> None:
        import ambiguity_manager  # noqa: F401

        self.assertIsNone(importlib.util.find_spec("torch"))


if __name__ == "__main__":
    unittest.main()
