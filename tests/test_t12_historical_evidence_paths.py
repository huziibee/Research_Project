"""Tests for relocated historical WSL T12 evidence paths."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from ambiguity_manager.model.candidate_evidence import EVIDENCE_REL as CANDIDATE_EVIDENCE_REL
from ambiguity_manager.model.checkpoint_download import EVIDENCE_REL as CHECKPOINT_EVIDENCE_REL
from ambiguity_manager.model.environment import INFERENCE_ENV_REL, TRAINING_ENV_REL
from ambiguity_manager.model.environment_evidence import EVIDENCE_REL as ENV_COMPAT_REL
from ambiguity_manager.model.hardware import HARDWARE_MANIFEST_REL
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root

HISTORICAL_PATHS = (
    "configs/environments/historical/t12_inference_environment.json",
    "configs/environments/historical/t12_training_environment.json",
    "configs/model/evidence/historical/t12_hardware_manifest.json",
    "configs/model/evidence/historical/t12_environment_compatibility.json",
    "configs/model/evidence/historical/t12_model_candidates.json",
    "configs/model/evidence/historical/t12_checkpoint_download.json",
    "requirements/historical/t12-wsl2/t12-inference.in",
    "requirements/historical/t12-wsl2/t12-training.in",
    "requirements/historical/t12-wsl2/t12-inference-wsl2.lock",
    "requirements/historical/t12-wsl2/t12-training-wsl2.lock",
    "scripts/historical/t12-wsl2/t12_probe_environment.py",
    "scripts/historical/t12-wsl2/t12_wsl2_bootstrap.sh",
    "scripts/historical/t12-wsl2/t12_wsl2_training_only.sh",
    "scripts/historical/t12-wsl2/t12_download_checkpoint.py",
)


class T12HistoricalEvidencePathsTests(unittest.TestCase):
    def test_historical_files_exist(self) -> None:
        for relpath in HISTORICAL_PATHS:
            with self.subTest(relpath=relpath):
                self.assertTrue((ROOT / relpath).is_file(), msg=relpath)

    def test_module_constants_point_to_historical_paths(self) -> None:
        self.assertIn("historical", INFERENCE_ENV_REL)
        self.assertIn("historical", TRAINING_ENV_REL)
        self.assertIn("historical", HARDWARE_MANIFEST_REL)
        self.assertIn("historical", ENV_COMPAT_REL)
        self.assertIn("historical", CANDIDATE_EVIDENCE_REL)
        self.assertIn("historical", CHECKPOINT_EVIDENCE_REL)

    def test_historical_checkpoint_download_references_qwen25(self) -> None:
        data = json.loads((ROOT / CHECKPOINT_EVIDENCE_REL).read_text(encoding="utf-8"))
        self.assertIn("Qwen2.5", data["official_repository_id"])

    def test_historical_readme_exists(self) -> None:
        readme = ROOT / "configs/model/evidence/historical/README.md"
        self.assertTrue(readme.is_file())
        self.assertIn("historical", readme.read_text(encoding="utf-8").lower())

    def test_ordinary_imports_do_not_load_ml_libraries(self) -> None:
        for module_name in (
            "ambiguity_manager.model.cluster.identities",
            "ambiguity_manager.model.cluster.manifest_schemas",
            "ambiguity_manager.model.cluster.path_policy",
        ):
            spec = importlib.util.find_spec(module_name)
            self.assertIsNotNone(spec)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)


if __name__ == "__main__":
    unittest.main()
