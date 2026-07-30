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
    readiness_timeout=int(os.environ.get("A02_READY_TIMEOUT_SECONDS", "900"))
    readiness_started=time.monotonic()
    for _ in range(max(1, readiness_timeout // 2)):
        if proc.poll() is not None: break
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{a.port}/v1/models",timeout=2): ready=True; break
        except Exception: time.sleep(2)
    readiness_seconds=time.monotonic()-readiness_started
    if not ready:
        print(f"SERVER_NOT_READY after {readiness_seconds:.1f}s; terminating model server", flush=True)
        if proc.poll() is None: os.killpg(proc.pid,signal.SIGTERM)
        try: proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            if proc.poll() is None: os.killpg(proc.pid,signal.SIGKILL)
            proc.wait(timeout=30)
        raise SystemExit(f"server failed readiness check after {readiness_seconds:.1f}s")
    print(f"SERVER_READY after {readiness_seconds:.1f}s", flush=True)
    try: code=subprocess.call(prefix+[a.runner,*a.runner_args])
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
        cleanup_started=time.monotonic()
        try: proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            if proc.poll() is None: os.killpg(proc.pid,signal.SIGKILL)
            proc.wait(timeout=30)
        print(f"SERVER_CLEANUP_COMPLETE after {time.monotonic()-cleanup_started:.1f}s", flush=True)
        if proc.poll() is None: raise SystemExit("server did not exit")
    raise SystemExit(code)
if __name__=="__main__": main()
