"""Start one vLLM server, run one annotator, and release GPU memory before return."""
from __future__ import annotations
import argparse,os,shlex,signal,subprocess,time,urllib.request
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--model",required=True); ap.add_argument("--revision",required=True); ap.add_argument("--port",type=int,required=True); ap.add_argument("--runner",required=True); ap.add_argument("--runner-args",nargs=argparse.REMAINDER,required=True); ap.add_argument("--log",required=True); a=ap.parse_args()
    container=os.environ.get("A01_CONTAINER_SIF")
    prefix=["apptainer","exec","--nv",container,"python3"] if container else ["python"]
    extra_args=shlex.split(os.environ.get("A01_VLLM_EXTRA_ARGS", ""))
    cmd=prefix+["-m","vllm.entrypoints.openai.api_server","--model",a.model,"--revision",a.revision,"--port",str(a.port),"--max-model-len",os.environ.get("A01_MAX_MODEL_LEN","8192"),"--max-num-seqs","1","--tensor-parallel-size","1","--gpu-memory-utilization","0.90",*extra_args]
    with open(a.log,"a",encoding="utf-8") as log: proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    ready=False
    for _ in range(180):
        if proc.poll() is not None: break
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{a.port}/v1/models",timeout=2): ready=True; break
        except Exception: time.sleep(2)
    if not ready:
        if proc.poll() is None: os.killpg(proc.pid,signal.SIGTERM)
        proc.wait(timeout=30)
        raise SystemExit("server failed readiness check")
    try: code=subprocess.call(prefix+[a.runner,*a.runner_args])
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
        try: proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            if proc.poll() is None: os.killpg(proc.pid,signal.SIGKILL)
            proc.wait()
        if proc.poll() is None: raise SystemExit("server did not exit")
    raise SystemExit(code)
if __name__=="__main__": main()
