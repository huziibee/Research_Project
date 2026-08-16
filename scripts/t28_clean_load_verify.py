#!/usr/bin/env python3
"""Clean-path package verification with an opt-in, real base-plus-adapter load."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from ambiguity_manager.model.t28_trainer import verify_package_checksums  # noqa: E402


def verification_status(*, metadata_ok: bool, load_requested: bool, load_ok: bool) -> str:
    if not metadata_ok:
        return "VERIFY_FAILED"
    if not load_requested:
        return "VERIFY_METADATA_ONLY"
    return "MODEL_LOAD_PASSED" if load_ok else "MODEL_LOAD_FAILED"


def perform_model_load(*, package: Path, base_model: str, base_revision: str) -> dict[str, object]:
    """Load the immutable base and packaged PEFT adapter without generation."""
    import torch
    from peft import PeftConfig, PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    adapter_config = PeftConfig.from_pretrained(str(package), local_files_only=True)
    adapter_base = str(getattr(adapter_config, "base_model_name_or_path", ""))
    if adapter_base and adapter_base != base_model:
        raise ValueError(f"adapter base mismatch: {adapter_base!r} != {base_model!r}")
    tokenizer = AutoTokenizer.from_pretrained(base_model, revision=base_revision, local_files_only=True)
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        revision=base_revision,
        local_files_only=True,
        quantization_config=quantization,
        device_map="auto",
    )
    model = PeftModel.from_pretrained(base, str(package), local_files_only=True)
    model.eval()
    return {
        "adapter_base_model": adapter_base or base_model,
        "tokenizer_class": type(tokenizer).__name__,
        "model_class": type(model).__name__,
        "cuda_available": torch.cuda.is_available(),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--base-revision", required=True)
    p.add_argument("--schema-registry", type=Path, required=True)
    p.add_argument("--base-model", default="Qwen/Qwen3-8B")
    p.add_argument("--perform-model-load", action="store_true")
    a = p.parse_args()
    manifest = json.loads((a.package / "package_manifest.json").read_text(encoding="utf-8"))
    metadata_ok = verify_package_checksums(a.package, manifest) and manifest.get("identity", {}).get("base_revision") == a.base_revision
    load_ok = False
    load_detail: dict[str, object] | None = None
    load_error = None
    if metadata_ok and a.perform_model_load:
        try:
            load_detail = perform_model_load(
                package=a.package, base_model=a.base_model, base_revision=a.base_revision
            )
            load_ok = True
        except Exception as exc:  # noqa: BLE001
            load_error = f"{type(exc).__name__}: {exc}"
    status = verification_status(
        metadata_ok=metadata_ok, load_requested=a.perform_model_load, load_ok=load_ok
    )
    evidence = {
        "status": status,
        "package_checksums": metadata_ok,
        "base_model": a.base_model,
        "base_revision": a.base_revision,
        "model_load_requested": a.perform_model_load,
        "model_load": load_detail,
        "model_load_error": load_error,
        "protected_data_accessed": False,
        "schema_registry": str(a.schema_registry),
        "clean_path": True,
    }
    a.output.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, sort_keys=True))
    return 0 if status in {"VERIFY_METADATA_ONLY", "MODEL_LOAD_PASSED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
