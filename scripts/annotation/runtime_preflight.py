"""A01-only runtime and model-architecture preflight; never installs globally."""
from __future__ import annotations
import argparse, importlib, json, platform, shutil, subprocess, sys
from pathlib import Path
def version(name):
    try: return importlib.import_module(name).__version__
    except Exception as e: return {"status":"error","error":repr(e)}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output",required=True); ap.add_argument("--container",required=True); ap.add_argument("--model-manifest",required=True); a=ap.parse_args()
    checks={"hostname":platform.node(),"python":sys.version,"packages":{x:version(x) for x in ("vllm","transformers","compressed_tensors")},"container":str(Path(a.container)),"model_manifest":str(Path(a.model_manifest))}
    checks["commands"]={x:shutil.which(x) for x in ("apptainer","nvidia-smi")}
    for module, cls in (("transformers","Gemma4ForCausalLM"),("transformers","Gemma4ForConditionalGeneration"),("transformers","Glm4MoeLiteForCausalLM")):
        try: checks[f"{module}.{cls}"]={"status":"present","module":module,"class":hasattr(importlib.import_module(module),cls)}
        except Exception as e: checks[f"{module}.{cls}"]={"status":"error","error":repr(e)}
    checks["structured_json_api"]="requires live container probe"
    checks["nvfp4"]="requires live container/model-config probe"
    p=Path(a.output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(checks,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
