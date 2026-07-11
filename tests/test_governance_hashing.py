"""Tests for governance canonical hashing and contract sidecar format."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.governance.hashing import (
    CONTRACT_SIDECAR_REL_PATH,
    canonical_json_bytes,
    parse_sidecar_line,
    sha256_hex,
    verify_contract_sidecar,
    write_contract_sidecar,
)


class TestGovernanceHashing(unittest.TestCase):
    def test_canonical_bytes_deterministic(self) -> None:
        payload = {"b": 2, "a": 1, "nested": {"z": True, "y": "text"}}
        first = canonical_json_bytes(payload)
        second = canonical_json_bytes({"nested": {"y": "text", "z": True}, "a": 1, "b": 2})
        self.assertEqual(first, second)
        self.assertEqual(first, b'{"a":1,"b":2,"nested":{"y":"text","z":true}}')

    def test_canonical_bytes_no_trailing_newline(self) -> None:
        payload = {"x": 1}
        self.assertFalse(canonical_json_bytes(payload).endswith(b"\n"))

    def test_sidecar_format_exact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "configs" / "research" / "research_contract_v1.json"
            json_path.parent.mkdir(parents=True)
            json_path.write_text('{"contract_version":"1.0.0"}', encoding="utf-8")
            sidecar_path = root / "configs" / "research" / "research_contract_v1.sha256"
            digest = write_contract_sidecar(json_path, sidecar_path)
            line = sidecar_path.read_text(encoding="utf-8")
            self.assertTrue(line.endswith("\n"))
            self.assertEqual(
                line,
                f"{digest}  {CONTRACT_SIDECAR_REL_PATH}\n",
            )
            parsed_digest, parsed_path = parse_sidecar_line(line)
            self.assertEqual(parsed_digest, digest)
            self.assertEqual(parsed_path, CONTRACT_SIDECAR_REL_PATH)

    def test_sidecar_verification_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "configs" / "research" / "research_contract_v1.json"
            json_path.parent.mkdir(parents=True)
            payload = {"z": 3, "a": 1}
            json_path.write_bytes(canonical_json_bytes(payload))
            sidecar_path = root / "configs" / "research" / "research_contract_v1.sha256"
            write_contract_sidecar(json_path, sidecar_path)
            self.assertTrue(verify_contract_sidecar(json_path, sidecar_path))

    def test_sidecar_tamper_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "configs" / "research" / "research_contract_v1.json"
            json_path.parent.mkdir(parents=True)
            json_path.write_bytes(canonical_json_bytes({"a": 1}))
            sidecar_path = root / "configs" / "research" / "research_contract_v1.sha256"
            write_contract_sidecar(json_path, sidecar_path)
            json_path.write_bytes(canonical_json_bytes({"a": 2}))
            self.assertFalse(verify_contract_sidecar(json_path, sidecar_path))

    def test_sha256_hex_matches_known_vector(self) -> None:
        self.assertEqual(
            sha256_hex(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_contract_json_must_not_contain_hash_field(self) -> None:
        from ambiguity_manager.governance.research_contract import validate_research_contract

        data = json.loads(
            (Path(__file__).resolve().parents[1] / "configs" / "research" / "research_contract_v1.json").read_text(
                encoding="utf-8"
            )
        )
        errors = validate_research_contract(data)
        self.assertEqual(errors, [], msg=f"unexpected errors: {errors}")
        data["content_hash"] = "bad"
        self.assertTrue(any("content_hash" in e for e in validate_research_contract(data)))


if __name__ == "__main__":
    unittest.main()
