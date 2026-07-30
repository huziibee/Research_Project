import json
from transformers import AutoConfig, AutoTokenizer, AutoProcessor
import transformers
print(json.dumps({"transformers": transformers.__version__, "gemma_classes": [x for x in dir(transformers) if "Gemma" in x or "Glm4" in x]}, flush=True))
for name, path in [("gemma", "/home-mscluster/mbangie/models/dual_llm_benchmark_v1/gemma-4-26b-a4b-it"), ("glm", "/home-mscluster/mbangie/models/dual_llm_benchmark_v1/glm-4.7-flash-bf16")]:
    print(json.dumps({"start": name}, flush=True))
    print(json.dumps({"config": type(AutoConfig.from_pretrained(path, local_files_only=True, trust_remote_code=False)).__name__}, flush=True))
    print(json.dumps({"tokenizer": type(AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)).__name__}, flush=True))
    print(json.dumps({"processor": type(AutoProcessor.from_pretrained(path, local_files_only=True, trust_remote_code=False)).__name__}, flush=True))
