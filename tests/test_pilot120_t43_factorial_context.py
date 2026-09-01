from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from ambiguity_manager.governance.hashing import canonical_json_bytes, sha256_hex
from scripts import pilot120_t43_factorial_context as t43


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/annotations/pilot_120_v1/source_canonical.jsonl"
FROZEN = ROOT / "data/annotations/pilot_120_v1/frozen/FROZEN_MANIFEST.json"
POLICY = ROOT / "configs/evaluation/pilot120_t43_factorial_context_policy_v1.json"


def _manifest() -> dict:
    return t43.build_manifest(source_path=SOURCE, frozen_manifest_path=FROZEN, policy_path=POLICY)


def _attestation(record_id: str, condition: dict) -> dict:
    payload = canonical_json_bytes(condition["input_payload"])
    prompt = f"prompt:{record_id}:{condition['condition_id']}".encode("utf-8")
    rendered = f"rendered:{record_id}:{condition['condition_id']}".encode("utf-8")
    token_ids = b"[1,2,3]"
    return {
        "record_id": record_id,
        "condition_id": condition["condition_id"],
        "input_payload_utf8_base64": base64.b64encode(payload).decode("ascii"),
        "input_payload_sha256": sha256_hex(payload),
        "prompt_input_utf8_base64": base64.b64encode(prompt).decode("ascii"),
        "prompt_input_sha256": sha256_hex(prompt),
        "rendered_input_utf8_base64": base64.b64encode(rendered).decode("ascii"),
        "rendered_input_sha256": sha256_hex(rendered),
        "token_ids_json_utf8_base64": base64.b64encode(token_ids).decode("ascii"),
        "token_ids_sha256": sha256_hex(token_ids),
        "prompt_token_count": 3,
    }


def test_builds_complete_frozen_eight_condition_matrix_with_44_dialogue_eligible() -> None:
    manifest = _manifest()
    assert manifest["status"] == "T43_CPU_ONLY_FACTORIAL_CONTEXT_MANIFEST_PREPARED"
    assert len(manifest["records"]) == 120
    assert sum(len(record["conditions"]) for record in manifest["records"]) == 960
    assert manifest["natural_context_availability_counts"] == {"scene": 120, "dialogue": 44, "capability": 120}
    assert manifest["dialogue_effect_population"]["n_eligible"] == 44
    assert manifest["execution_readiness"] == "NOT_COMPUTED"


def test_retained_source_tokens_are_exact_and_removed_contexts_are_absent() -> None:
    manifest = _manifest()
    source_lines = {json.loads(line)["record_id"]: line.encode("utf-8") for line in SOURCE.read_text(encoding="utf-8").splitlines() if line}
    record = manifest["records"][0]
    full = next(item for item in record["conditions"] if item["condition_id"] == "S1_D1_C1")
    blind = next(item for item in record["conditions"] if item["condition_id"] == "S0_D0_C0")
    assert full["input_payload"]["command"] == json.loads(source_lines[record["record_id"]])["command"]
    assert blind["input_payload"]["scene_context"] is None
    assert blind["input_payload"]["dialogue_history"] == []
    assert blind["input_payload"]["capability_context"] is None
    raw_command = t43._raw_top_level_value_bytes(source_lines[record["record_id"]], "command")
    attested = base64.b64decode(full["retained_source_value_attestations"]["command"]["source_value_utf8_base64"])
    assert attested == raw_command
    assert full["prompt_render_token_placeholder"]["status"] == "NOT_COMPUTED"


def test_static_verifier_rejects_a_changed_retained_source_attestation() -> None:
    manifest = _manifest()
    full = manifest["records"][0]["conditions"][0]
    full["retained_source_value_attestations"]["command"]["source_value_sha256"] = "0" * 64
    with pytest.raises(t43.T43ManifestError, match="manifest_static_mismatch:records"):
        t43.verify_static_manifest(manifest=manifest, source_path=SOURCE, frozen_manifest_path=FROZEN, policy_path=POLICY)


def test_runtime_attestation_verifier_requires_all_960_exact_input_payloads(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = _manifest()
    rows = [_attestation(record["record_id"], condition) for record in manifest["records"] for condition in record["conditions"]]
    path = ROOT / "not_a_real_runtime_attestation.jsonl"
    monkeypatch.setattr(t43, "_load_jsonl", lambda _path: rows)
    monkeypatch.setattr(t43, "_sha256", lambda _path: "a" * 64)
    verified = t43.verify_runtime_attestations(manifest=manifest, path=path)
    assert verified["status"] == "T43_RUNTIME_INPUT_RENDER_TOKEN_ATTESTATION_VERIFY_PASSED"
    assert verified["condition_input_count"] == 960
    monkeypatch.setattr(t43, "_load_jsonl", lambda _path: rows[:-1])
    with pytest.raises(t43.T43ManifestError, match="runtime_attestation_missing_conditions:1"):
        t43.verify_runtime_attestations(manifest=manifest, path=path)
