from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def check_model(path: Path, expected: list[str]) -> dict:
    index = path / "model.safetensors.index.json"
    refs = sorted({v for v in json.loads(index.read_text())["weight_map"].values()})
    actual = sorted(p.name for p in path.glob("*.safetensors") if p.name != index.name)
    return {"path": str(path), "index_exists": index.is_file(), "index_references": refs, "actual_shards": actual, "index_exact": refs == sorted(expected) == actual, "nonzero": all((path / n).stat().st_size > 0 for n in actual)}

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True); ap.add_argument("--gemma", required=True); ap.add_argument("--glm", required=True); ap.add_argument("--schema", required=True)
    a = ap.parse_args()
    from transformers import AutoConfig, AutoProcessor, AutoTokenizer
    out = {"offline": True, "schema_sha256": sha256(Path(a.schema)), "models": {}}
    for key, raw, names in [("gemma4", a.gemma, ["model-00001-of-00002.safetensors", "model-00002-of-00002.safetensors"]), ("glm", a.glm, [f"model-{i:05d}-of-00048.safetensors" for i in range(1, 49)])]:
        p = Path(raw)
        item = check_model(p, names)
        item["config_class"] = type(AutoConfig.from_pretrained(p, local_files_only=True, trust_remote_code=False)).__name__
        item["tokenizer_class"] = type(AutoTokenizer.from_pretrained(p, local_files_only=True, trust_remote_code=False)).__name__
        item["processor_class"] = type(AutoProcessor.from_pretrained(p, local_files_only=True, trust_remote_code=False)).__name__
        out["models"][key] = item
    Path(a.output).write_text(json.dumps(out, indent=2) + "\n")
if __name__ == "__main__": main()
