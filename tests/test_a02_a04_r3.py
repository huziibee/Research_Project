import hashlib, json
from pathlib import Path

ROOT = Path(__file__).parents[1]

def test_active_pair_and_retired_mistral_are_frozen():
    m = json.loads((ROOT / "configs/annotation/a02_a04_r3_model_selection_v2.json").read_text())
    assert m["active_pair"]["annotator_a_gemma4"]["revision"] == "4d7ae4984b7db7de8f8457170b3f1a419ee76d52"
    assert m["active_pair"]["annotator_b_glm"]["revision"] == "7dd20894a642a0aa287e9827cb1a1f7f91386b67"
    assert m["active_pair"]["annotator_a_gemma4"]["family"] != m["active_pair"]["annotator_b_glm"]["family"]
    assert m["retired"]["annotator_a_mistral_retired_incompatible"]["status"] == "retired_incompatible"

def test_frozen_pilot_prompt_and_schema_hashes():
    p = json.loads((ROOT / "data/dual_llm_benchmark_v1/manifests/a03_pilot_manifest.json").read_text())
    assert p["record_count"] == 40
    assert p["manifest_hash"] == "81d56440801c24a68032e3512dc7c6ca8c4fbd2317bdf56a78cf0d36172e6de1"
    i = json.loads((ROOT / "configs/annotation/a02_a04_r3_inference.json").read_text())
    assert i["prompt_hash"] and i["schema_hash"] and i["handbook_hash"]

def test_r3_sequential_offline_no_gres_and_full_run_gate():
    pilot = (ROOT / "cluster/annotation/a03_dual_annotator_pilot.sbatch").read_text()
    assert "--exclusive" in pilot and "--mem=110G" in pilot and "--gres=" not in pilot
    assert "HF_HUB_OFFLINE=1" in pilot and "HF_HUB_DISABLE_TELEMETRY=1" in pilot
    assert "releasing allocation without model load" in pilot
    assert "GPU_WAIT_DEADLINE" not in pilot
    assert "gemma-4-26b-a4b-it" in pilot and "glm-4.7-flash-bf16" in pilot
    assert "mistral-small-4" not in pilot
    assert "log()" in pilot and "GEMMA canary start" in pilot and "GLM canary start" in pilot
    full = (ROOT / "cluster/annotation/a05_full_dual_annotation.sbatch").read_text()
    assert "A01_PILOT_APPROVED" in full

def test_exact_pilot_jsonl_hash():
    data = (ROOT / "data/dual_llm_benchmark_v1/manifests/a03_pilot_manifest.jsonl").read_bytes()
    assert hashlib.sha256(data).hexdigest() == "23a34310ff167fce2171178a306b0c2b441a2ea2c1466d9d7302e23e2d0744e6"

def test_schema_invalid_confidence_is_retryable_not_silently_coerced():
    import importlib.util
    spec = importlib.util.spec_from_file_location("r3_runner", ROOT / "scripts/annotation/run_vllm_annotator.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.parsed_schema_errors({"record_id": "r", "confidence": 0.9}, "r") == ["confidence_must_be_frozen_enum"]
    assert module.parsed_schema_errors({"record_id": "r", "confidence": "high"}, "r") == []
