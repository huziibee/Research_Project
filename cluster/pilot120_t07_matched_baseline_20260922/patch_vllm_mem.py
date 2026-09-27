from pathlib import Path

p = Path("/home-mscluster/mbangie/t12-hpc/code/pilot120_t07_matched_baseline-20260922/scripts/annotation/server_lifecycle.py")
text = p.read_text(encoding="utf-8")
old = '"--gpu-memory-utilization","0.90"'
new = '"--gpu-memory-utilization",os.environ.get("A01_GPU_MEM_UTIL","0.70")'
if old not in text:
    raise SystemExit("pattern_missing")
p.write_text(text.replace(old, new, 1), encoding="utf-8")
print("patched_gpu_util")
