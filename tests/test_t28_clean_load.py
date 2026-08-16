from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.model.t28_trainer import package_manifest, verify_package_checksums

from scripts.t28_clean_load_verify import verification_status


class T28CleanLoadMetadataTests(unittest.TestCase):
    def test_metadata_only_is_not_reported_as_a_model_load(self) -> None:
        self.assertEqual(
            verification_status(metadata_ok=True, load_requested=False, load_ok=False),
            "VERIFY_METADATA_ONLY",
        )
        self.assertEqual(
            verification_status(metadata_ok=True, load_requested=True, load_ok=True),
            "MODEL_LOAD_PASSED",
        )
        self.assertEqual(
            verification_status(metadata_ok=True, load_requested=True, load_ok=False),
            "MODEL_LOAD_FAILED",
        )

    def test_package_checksum_roundtrip_and_base_identity(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            package = Path(td) / "adapter"
            package.mkdir()
            (package / "adapter_config.json").write_text("{}", encoding="utf-8")
            (package / "adapter_model.safetensors").write_bytes(b"weights")
            (package / "base_identity_reference.json").write_text(
                json.dumps(
                    {
                        "immutable": True,
                        "selected_base_model": "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218",
                    }
                ),
                encoding="utf-8",
            )
            identity = {
                "base_model": "Qwen/Qwen3-8B",
                "base_revision": "b968826d9c46dd6066d109eabc6255188de91218",
                "run_id": "t28-full-train-20260728T222000Z-r5-retry5",
                "canonical_sha256": "1e51cac046e014a6b890b10a155d22e32e01aa276d4507a10ad4f86abcf9942a",
            }
            manifest = package_manifest(package, identity)
            (package / "package_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(verify_package_checksums(package, manifest))
            self.assertEqual(manifest["identity"]["base_revision"], identity["base_revision"])
            # Mutate weights -> fail closed.
            (package / "adapter_model.safetensors").write_bytes(b"tampered")
            self.assertFalse(verify_package_checksums(package, manifest))


if __name__ == "__main__":
    unittest.main()
