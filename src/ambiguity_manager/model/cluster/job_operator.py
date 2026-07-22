"""Local Slurm run/status/poll/pull/verify operator for T12 cluster jobs.

CPU-only. Does not import torch, transformers, or vLLM.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ambiguity_manager.model.cluster.atomic_outputs import sha256_file
from ambiguity_manager.model.cluster.path_policy import validate_path_template
from ambiguity_manager.paths import ProjectPaths

PROFILES_REL = "configs/cluster/t12_job_profiles.json"
STATE_DIR_REL = "outputs/t12_cluster_jobs"
STATE_FILE_NAME = "state.json"

COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ARCHIVE_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
JOB_ID_RE = re.compile(r"^[0-9]+$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,120}$")
PROFILE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

TERMINAL_STATES = frozenset(
    {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "TIMEOUT",
        "OUT_OF_MEMORY",
        "NODE_FAIL",
        "PREEMPTED",
    }
)
KNOWN_STATES = TERMINAL_STATES | frozenset(
    {"PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "REQUEUED", "SUSPENDED"}
)

# Unrelated local paths that must not block packaging (never staged by operator).
ALLOWED_UNTRACKED_PREFIXES = (
    "data/raw/TEACh",
    "configs.zip",
    "test-output.txt",
)
ALLOWED_DIRTY_PREFIXES = (
    "data/raw/TEACh",
)
ALLOWED_UNTRACKED_GLOBS = (
    re.compile(r"^t12-[0-9a-f]+\.tar\.gz$"),
)

FORBIDDEN_REMOTE_TOKENS = (
    "rm -rf",
    "rm -fr",
    "git init",
    "scancel",
    "passwd",
    "private_key",
    "BEGIN OPENSSH",
)

FORBIDDEN_STATE_KEYS = (
    "password",
    "private_key",
    "key_path",
    "passphrase",
    "token",
    "email",
)

CommandRunner = Callable[[Sequence[str], Mapping[str, Any] | None], subprocess.CompletedProcess[str]]


class OperatorError(RuntimeError):
    """Raised for operator validation or execution failures."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_runner(cmd: Sequence[str], kwargs: Mapping[str, Any] | None = None) -> subprocess.CompletedProcess[str]:
    options: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "check": False,
    }
    if kwargs:
        options.update(kwargs)
    return subprocess.run(list(cmd), **options)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def load_profiles(repo_root: Path) -> dict[str, Any]:
    path = repo_root / PROFILES_REL
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0.0":
        raise OperatorError("profiles.schema_version must be 1.0.0")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise OperatorError("profiles.profiles must be a non-empty object")
    for name in profiles:
        if not PROFILE_NAME_RE.match(name):
            raise OperatorError(f"invalid_profile_name:{name}")
    return payload


def get_profile(profiles_doc: dict[str, Any], name: str) -> dict[str, Any]:
    if not PROFILE_NAME_RE.match(name):
        raise OperatorError(f"invalid_profile_name:{name}")
    profiles = profiles_doc["profiles"]
    if name not in profiles:
        raise OperatorError(f"profile_not_allowlisted:{name}")
    profile = profiles[name]
    if not isinstance(profile, dict):
        raise OperatorError(f"invalid_profile:{name}")
    template = str(profile["remote_result_root_template"])
    errors = validate_path_template(template)
    if errors:
        raise OperatorError(f"unsafe_remote_result_root:{';'.join(errors)}")
    if bool(profile.get("gpus_required")):
        raise OperatorError("gpus_required_profiles_not_supported_by_operator_v1")
    return profile


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.match(run_id):
        raise OperatorError(f"invalid_run_id:{run_id}")
    if ".." in run_id or "/" in run_id or "\\" in run_id:
        raise OperatorError(f"invalid_run_id:{run_id}")
    return run_id


def validate_job_id(job_id: str) -> str:
    if not JOB_ID_RE.match(job_id):
        raise OperatorError(f"invalid_job_id:{job_id}")
    return job_id


def parse_sbatch_job_id(stdout: str) -> str:
    text = (stdout or "").strip()
    if not text:
        raise OperatorError("sbatch_empty_job_id")
    # sbatch --parsable may emit "jobid;cluster"
    candidate = text.splitlines()[-1].strip().split(";")[0].strip()
    return validate_job_id(candidate)


def count_jsonl_rows(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def ensure_no_forbidden_tokens(command: Sequence[str] | str) -> None:
    joined = " ".join(command) if isinstance(command, (list, tuple)) else str(command)
    lowered = joined.lower()
    for token in FORBIDDEN_REMOTE_TOKENS:
        if token.lower() in lowered:
            raise OperatorError(f"destructive_or_forbidden_command:{token}")


def remote_path_under_root(remote_path: str, *, cluster_root_expr: str) -> None:
    """Best-effort local validation that remote paths stay under configured root."""
    if ".." in remote_path.split("/"):
        raise OperatorError(f"remote_path_escape:{remote_path}")
    if remote_path.startswith("/") and "t12-hpc" not in remote_path and "${T12_CLUSTER_ROOT}" not in remote_path:
        # Absolute paths must still reference the known cluster root layout.
        if "/runs/" not in remote_path:
            raise OperatorError(f"remote_path_escape:{remote_path}")
    _ = cluster_root_expr


def sanitize_state(payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload)
    lowered = text.lower()
    for key in FORBIDDEN_STATE_KEYS:
        if f'"{key}"' in lowered or f"'{key}'" in lowered:
            raise OperatorError(f"forbidden_state_key:{key}")
    return payload


@dataclass
class JobStatus:
    job_id: str
    state: str
    reason: str | None = None
    node: str | None = None
    elapsed: str | None = None
    exit_code: str | None = None
    source: str = "squeue"

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def success(self) -> bool:
        return self.state == "COMPLETED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "state": self.state,
            "reason": self.reason,
            "node": self.node,
            "elapsed": self.elapsed,
            "exit_code": self.exit_code,
            "source": self.source,
            "terminal": self.terminal,
            "success": self.success,
        }


class ClusterJobOperator:
    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        ssh_alias: str = "wits-mscluster",
        runner: CommandRunner | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        monotonic_fn: Callable[[], float] | None = None,
        dry_run: bool = False,
    ) -> None:
        self.repo_root = (repo_root or ProjectPaths.from_repo_root().root).resolve()
        self.ssh_alias = ssh_alias
        self.runner = runner or _default_runner
        self.sleep_fn = sleep_fn or time.sleep
        self.monotonic_fn = monotonic_fn or time.monotonic
        self.dry_run = dry_run
        self.profiles_doc = load_profiles(self.repo_root)
        self.state_dir = self.repo_root / STATE_DIR_REL
        self.state_path = self.state_dir / STATE_FILE_NAME

    # --- git / safety -------------------------------------------------
    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return self.runner(["git", "-C", str(self.repo_root), *args], None)

    def _require_clean_for_submit(self, profile: dict[str, Any]) -> str:
        branch = self._git("branch", "--show-current").stdout.strip()
        required = profile.get("required_branch")
        if required and branch != required:
            raise OperatorError(f"branch_mismatch:expected={required}:actual={branch}")

        staged = self._git("diff", "--cached", "--name-only").stdout.strip()
        if staged:
            raise OperatorError("staged_index_blocks_submission")

        tracked = self._git("diff", "--name-only").stdout.strip()
        if tracked:
            unexpected = [
                path
                for path in tracked.splitlines()
                if path.strip() and not self._is_allowed_dirty(path.strip())
            ]
            if unexpected:
                raise OperatorError(
                    "unexpected_tracked_modifications:" + ",".join(unexpected)
                )

        porcelain = self._git("status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
        for line in porcelain:
            if not line.strip():
                continue
            path = line[3:].strip() if len(line) > 3 else line.strip()
            if self._is_allowed_untracked(path):
                continue
            # Ignore operator runtime outputs
            if path.startswith("outputs/t12_cluster_jobs/"):
                continue
            raise OperatorError(f"unexpected_untracked_or_dirty:{path}")

        head = self._git("rev-parse", "HEAD").stdout.strip()
        if not COMMIT_SHA_RE.match(head):
            raise OperatorError(f"invalid_head_sha:{head}")
        return head

    def _is_allowed_dirty(self, path: str) -> bool:
        normalised = path.replace("\\", "/")
        for prefix in ALLOWED_DIRTY_PREFIXES:
            if normalised == prefix or normalised.startswith(prefix.rstrip("/") + "/"):
                return True
        return False

    def _is_allowed_untracked(self, path: str) -> bool:
        normalised = path.replace("\\", "/")
        if self._is_allowed_dirty(normalised):
            return True
        for prefix in ALLOWED_UNTRACKED_PREFIXES:
            if normalised == prefix or normalised.startswith(prefix.rstrip("/") + "/"):
                return True
        base = Path(normalised).name
        return any(pattern.match(base) for pattern in ALLOWED_UNTRACKED_GLOBS)

    # --- state --------------------------------------------------------
    def load_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {"schema_version": "1.0.0", "latest_run_id": None, "runs": {}}
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        return sanitize_state(payload)

    def save_state(self, payload: dict[str, Any]) -> None:
        sanitize_state(payload)
        atomic_write_json(self.state_path, payload)

    def resolve_run_record(self, identifier: str) -> dict[str, Any]:
        state = self.load_state()
        runs = state.get("runs") or {}
        if identifier == "latest":
            latest = state.get("latest_run_id")
            if not latest or latest not in runs:
                raise OperatorError("no_latest_run")
            return dict(runs[latest])
        if identifier in runs:
            return dict(runs[identifier])
        for record in runs.values():
            if str(record.get("job_id")) == identifier:
                return dict(record)
            if str(record.get("run_id")) == identifier:
                return dict(record)
        raise OperatorError(f"unknown_run_or_job:{identifier}")

    def _update_run(self, run_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        state = self.load_state()
        runs = state.setdefault("runs", {})
        record = dict(runs.get(run_id) or {"run_id": run_id})
        record.update(updates)
        runs[run_id] = record
        state["latest_run_id"] = run_id
        state["schema_version"] = "1.0.0"
        self.save_state(state)
        return record

    # --- SSH helpers --------------------------------------------------
    def ssh(self, remote_command: str) -> subprocess.CompletedProcess[str]:
        ensure_no_forbidden_tokens(remote_command)
        cmd = ["ssh", "-o", "BatchMode=yes", self.ssh_alias, "--", remote_command]
        if self.dry_run:
            return subprocess.CompletedProcess(cmd, 0, stdout="DRY_RUN\n", stderr="")
        return self.runner(cmd, None)

    def scp_to_remote(self, local_path: Path, remote_path: str) -> subprocess.CompletedProcess[str]:
        ensure_no_forbidden_tokens(remote_path)
        remote_path_under_root(remote_path, cluster_root_expr="${T12_CLUSTER_ROOT}")
        destination = f"{self.ssh_alias}:{remote_path}"
        cmd = ["scp", "-o", "BatchMode=yes", str(local_path), destination]
        if self.dry_run:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return self.runner(cmd, None)

    def scp_from_remote(self, remote_path: str, local_path: Path) -> subprocess.CompletedProcess[str]:
        ensure_no_forbidden_tokens(remote_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        source = f"{self.ssh_alias}:{remote_path}"
        cmd = ["scp", "-o", "BatchMode=yes", "-r", source, str(local_path)]
        if self.dry_run:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return self.runner(cmd, None)

    def test_ssh_batch_mode(self) -> None:
        result = self.ssh("printf ok")
        if result.returncode != 0 or "ok" not in (result.stdout or ""):
            raise OperatorError(f"ssh_batchmode_failed:{result.stderr or result.stdout}")

    def remote_cluster_root_expr(self) -> str:
        env_name = str(self.profiles_doc.get("cluster_root_env", "T12_CLUSTER_ROOT"))
        default = str(self.profiles_doc.get("cluster_root_default_remote", "$HOME/t12-hpc"))
        return f'"${{{env_name}:-{default}}}"'

    # --- packaging ----------------------------------------------------
    def build_source_identity_manifest(
        self,
        *,
        source_commit_sha: str,
        source_archive_sha256: str,
        archive_filename: str,
        packaging_timestamp: str,
    ) -> dict[str, Any]:
        if not COMMIT_SHA_RE.match(source_commit_sha):
            raise OperatorError("invalid_source_commit_sha")
        if not ARCHIVE_SHA_RE.match(source_archive_sha256):
            raise OperatorError("invalid_source_archive_sha256")
        return {
            "schema_version": "1.0.0",
            "source_commit_sha": source_commit_sha,
            "source_archive_sha256": source_archive_sha256,
            "transfer_method": "git_archive",
            "archive_filename": archive_filename,
            "packaging_timestamp": packaging_timestamp,
        }

    def create_git_archive(self, *, head_sha: str, destination: Path) -> tuple[str, int]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = self._git(
            "archive",
            "--format=tar.gz",
            "--prefix=t12-src/",
            f"--output={destination}",
            head_sha,
        )
        if result.returncode != 0:
            raise OperatorError(f"git_archive_failed:{result.stderr}")
        digest = sha256_file(destination)
        size = destination.stat().st_size
        return digest, size

    def _make_run_id(self, profile_name: str, profile: dict[str, Any], head_sha: str) -> str:
        prefix = str(profile.get("run_id_prefix") or f"t12-{profile_name}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return validate_run_id(f"{prefix}-{stamp}-{head_sha[:7]}")

    def _render_sbatch(
        self,
        *,
        profile: dict[str, Any],
        run_id: str,
        head_sha: str,
        archive_sha: str,
        archive_filename: str,
    ) -> str:
        partition = str(profile["partition"])
        time_limit = str(profile["time_limit"])
        mem = int(profile["memory_mb"])
        cpus = int(profile["cpus"])
        job_name = str(profile.get("job_name") or "t12-job")
        entry = str(profile["entry_point"])
        root_expr = '${T12_CLUSTER_ROOT:-$HOME/t12-hpc}'
        # Intentionally no rm -rf. Refuse existing result dir instead.
        return f"""#!/usr/bin/env bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={mem}
#SBATCH --time={time_limit}
#SBATCH --output={root_expr}/logs/{job_name}-%j.out
#SBATCH --error={root_expr}/logs/{job_name}-%j.err

set -euo pipefail

export T12_CLUSTER_ROOT="${{T12_CLUSTER_ROOT:-$HOME/t12-hpc}}"
RUN_ID={shlex.quote(run_id)}
SOURCE_COMMIT={shlex.quote(head_sha)}
ARCHIVE_SHA={shlex.quote(archive_sha)}
ARCHIVE_NAME={shlex.quote(archive_filename)}
PREP_DIR="${{T12_CLUSTER_ROOT}}/runs/t12-canary/.prep-${{RUN_ID}}"
RESULT_DIR="${{T12_CLUSTER_ROOT}}/runs/t12-canary/${{RUN_ID}}"
SRC_ROOT="${{PREP_DIR}}/source/t12-src"

mkdir -p "${{T12_CLUSTER_ROOT}}/logs"
mkdir -p "${{T12_CLUSTER_ROOT}}/runs/t12-canary"

if [[ -e "${{RESULT_DIR}}" ]]; then
  echo "RESULT_DIR_EXISTS:${{RESULT_DIR}}" >&2
  exit 40
fi
mkdir -p "${{RESULT_DIR}}"

if [[ ! -d "${{SRC_ROOT}}" ]]; then
  echo "SOURCE_NOT_EXTRACTED:${{SRC_ROOT}}" >&2
  exit 41
fi

export PYTHONPATH="${{SRC_ROOT}}/src${{PYTHONPATH:+:$PYTHONPATH}}"
python3 "${{SRC_ROOT}}/{entry}" \\
  --result-dir "${{RESULT_DIR}}" \\
  --run-id "${{RUN_ID}}" \\
  --source-commit "${{SOURCE_COMMIT}}" \\
  --source-archive-sha256 "${{ARCHIVE_SHA}}" \\
  --source-identity-manifest "${{PREP_DIR}}/source_identity_manifest.json"

echo "CANARY_JOB_DONE run_id=${{RUN_ID}} job_id=${{SLURM_JOB_ID}}"
"""

    # --- public actions -----------------------------------------------
    def run_profile(
        self,
        profile_name: str,
        *,
        poll: bool = False,
        pull: bool = False,
        interval: float = 30.0,
        timeout: float = 3600.0,
    ) -> dict[str, Any]:
        profile = get_profile(self.profiles_doc, profile_name)
        head_sha = "0" * 40 if self.dry_run else self._require_clean_for_submit(profile)
        if self.dry_run:
            # Still capture real HEAD for dry-run messaging when possible.
            probed = self._git("rev-parse", "HEAD")
            if probed.returncode == 0 and COMMIT_SHA_RE.match(probed.stdout.strip()):
                head_sha = probed.stdout.strip()

        run_id = self._make_run_id(profile_name, profile, head_sha)
        local_run_dir = self.state_dir / run_id
        local_run_dir.mkdir(parents=True, exist_ok=True)

        archive_filename = f"t12-{head_sha[:7]}.tar.gz"
        archive_path = local_run_dir / archive_filename
        packaging_timestamp = _utc_now()

        if self.dry_run:
            archive_sha = "a" * 64
            archive_bytes = 0
            print(f"DRY-RUN: would create git archive for {head_sha}")
        else:
            archive_sha, archive_bytes = self.create_git_archive(head_sha=head_sha, destination=archive_path)

        manifest = self.build_source_identity_manifest(
            source_commit_sha=head_sha,
            source_archive_sha256=archive_sha,
            archive_filename=archive_filename,
            packaging_timestamp=packaging_timestamp,
        )
        manifest_path = local_run_dir / "source_identity_manifest.json"
        atomic_write_json(manifest_path, manifest)

        sbatch_text = self._render_sbatch(
            profile=profile,
            run_id=run_id,
            head_sha=head_sha,
            archive_sha=archive_sha,
            archive_filename=archive_filename,
        )
        ensure_no_forbidden_tokens(sbatch_text)
        sbatch_path = local_run_dir / "submit.sbatch"
        sbatch_path.write_text(sbatch_text, encoding="utf-8", newline="\n")

        remote_meta = {
            "run_id": run_id,
            "profile": profile_name,
            "source_commit_sha": head_sha,
            "source_archive_sha256": archive_sha,
            "archive_bytes": archive_bytes,
            "remote_result_path_template": f"{profile['remote_result_root_template']}/{run_id}",
            "remote_prep_path_template": f"{profile['remote_result_root_template']}/.prep-{run_id}",
            "submission_timestamp_utc": packaging_timestamp,
        }
        atomic_write_json(local_run_dir / "remote_metadata.json", remote_meta)

        if not self.dry_run:
            self.test_ssh_batch_mode()

        root_expr = self.remote_cluster_root_expr()
        prep_rel = f"runs/t12-canary/.prep-{run_id}"
        result_rel = f"runs/t12-canary/{run_id}"

        mkdir_cmd = (
            f"ROOT={root_expr}; "
            f"mkdir -p \"$ROOT/logs\" \"$ROOT/runs/t12-canary\"; "
            f"test ! -e \"$ROOT/{result_rel}\"; "
            f"test ! -e \"$ROOT/{prep_rel}\"; "
            f"mkdir -p \"$ROOT/{prep_rel}/source\"; "
            f"printf '%s\\n' \"$ROOT/{prep_rel}\""
        )
        mkdir_result = self.ssh(mkdir_cmd)
        if mkdir_result.returncode != 0:
            raise OperatorError(f"remote_prep_mkdir_failed:{mkdir_result.stderr or mkdir_result.stdout}")
        remote_prep = (mkdir_result.stdout or "").strip().splitlines()[-1].strip()
        if not remote_prep and not self.dry_run:
            raise OperatorError("remote_prep_path_unresolved")

        if self.dry_run:
            remote_prep = f"$HOME/t12-hpc/{prep_rel}"

        transfers: list[tuple[Path, str]] = [
            (manifest_path, "source_identity_manifest.json"),
            (sbatch_path, "submit.sbatch"),
        ]
        if archive_path.exists():
            transfers.insert(0, (archive_path, archive_filename))
        elif not self.dry_run:
            raise OperatorError(f"archive_missing:{archive_path}")

        for local, name in transfers:
            transferred = self.scp_to_remote(local, f"{remote_prep}/{name}")
            if transferred.returncode != 0:
                raise OperatorError(f"scp_failed:{name}:{transferred.stderr}")

        verify_cmd = (
            f"cd {shlex.quote(remote_prep)} && "
            f"OBS=$(sha256sum {shlex.quote(archive_filename)} | cut -d' ' -f1) && "
            f"EXP=$(python3 -c 'import json;print(json.load(open(\"source_identity_manifest.json\"))[\"source_archive_sha256\"])') && "
            f"test \"$OBS\" = \"$EXP\" && "
            f"mkdir -p source && "
            f"tar -xzf {shlex.quote(archive_filename)} -C source && "
            f"test -f source/t12-src/{profile['entry_point']} && "
            f"echo ARCHIVE_HASH_MATCH"
        )
        if self.dry_run:
            print("DRY-RUN: would verify remote archive hash and extract source")
        else:
            verified = self.ssh(verify_cmd)
            if verified.returncode != 0 or "ARCHIVE_HASH_MATCH" not in (verified.stdout or ""):
                raise OperatorError(f"remote_archive_verify_failed:{verified.stderr or verified.stdout}")

        submit_cmd = f"cd {shlex.quote(remote_prep)} && sbatch --parsable submit.sbatch"
        if self.dry_run:
            job_id = "0"
            print("DRY-RUN: would submit sbatch --parsable")
        else:
            submitted = self.ssh(submit_cmd)
            if submitted.returncode != 0:
                raise OperatorError(f"sbatch_failed:{submitted.stderr or submitted.stdout}")
            job_id = parse_sbatch_job_id(submitted.stdout)

        record = self._update_run(
            run_id,
            {
                "run_id": run_id,
                "job_id": job_id,
                "profile": profile_name,
                "source_commit_sha": head_sha,
                "archive_sha256": archive_sha,
                "archive_bytes": archive_bytes,
                "submission_timestamp_utc": packaging_timestamp,
                "last_known_slurm_state": "SUBMITTED",
                "remote_result_path_template": remote_meta["remote_result_path_template"],
                "remote_prep_path_template": remote_meta["remote_prep_path_template"],
                "remote_prep_path_resolved": remote_prep if not self.dry_run else None,
                "local_run_dir": str(local_run_dir.relative_to(self.repo_root)).replace("\\", "/"),
                "local_pull_path": None,
                "pulled": False,
                "verification_result": None,
                "ssh_alias": self.ssh_alias,
            },
        )

        print(f"Submitted job {job_id}")
        print(f"Run ID: {run_id}")
        print("Check:")
        print("python scripts/t12_cluster_job.py --status latest")
        print("Wait and pull:")
        print("python scripts/t12_cluster_job.py --poll latest --pull")

        if poll:
            self.poll(run_id, interval=interval, timeout=timeout, pull=pull)
        elif pull:
            self.pull(run_id)
        return record

    def status(self, identifier: str = "latest") -> JobStatus:
        record = self.resolve_run_record(identifier)
        job_id = validate_job_id(str(record["job_id"]))
        status = self._query_job_status(job_id)
        self._update_run(
            str(record["run_id"]),
            {
                "last_known_slurm_state": status.state,
                "last_status": status.as_dict(),
                "last_status_timestamp_utc": _utc_now(),
            },
        )
        self._print_status(status, run_id=str(record["run_id"]))
        return status

    def _query_job_status(self, job_id: str) -> JobStatus:
        squeue_fmt = "%i|%T|%R|%N|%M"
        squeue_cmd = f"squeue -h -j {shlex.quote(job_id)} -o '{squeue_fmt}'"
        queued = self.ssh(squeue_cmd)
        line = (queued.stdout or "").strip().splitlines()
        if queued.returncode == 0 and line and "|" in line[0]:
            parts = line[0].split("|")
            while len(parts) < 5:
                parts.append("")
            state = parts[1].strip().upper() or "UNKNOWN"
            reason = parts[2].strip() or None
            node = parts[3].strip() or None
            elapsed = parts[4].strip() or None
            return JobStatus(
                job_id=job_id,
                state=state,
                reason=reason,
                node=node,
                elapsed=elapsed,
                exit_code=None,
                source="squeue",
            )

        # Disappearance from squeue is NOT success — fall back to sacct.
        sacct_fmt = "JobID,State,ExitCode,Elapsed,NodeList,Reason"
        sacct_cmd = (
            f"sacct -n -P -j {shlex.quote(job_id)} "
            f"--format={sacct_fmt}"
        )
        accounted = self.ssh(sacct_cmd)
        if accounted.returncode != 0:
            raise OperatorError(f"sacct_failed:{accounted.stderr or accounted.stdout}")
        rows = [row for row in (accounted.stdout or "").splitlines() if row.strip()]
        if not rows:
            raise OperatorError(f"job_not_found_in_squeue_or_sacct:{job_id}")
        # Prefer the batch step or first row.
        chosen = rows[0]
        for row in rows:
            if ".batch" in row.split("|")[0]:
                chosen = row
                break
        parts = chosen.split("|")
        while len(parts) < 6:
            parts.append("")
        state = parts[1].strip().upper() or "UNKNOWN"
        # Map Slurm compound states.
        if state.startswith("CANCELLED"):
            state = "CANCELLED"
        return JobStatus(
            job_id=job_id,
            state=state,
            reason=parts[5].strip() or None,
            node=parts[4].strip() or None,
            elapsed=parts[3].strip() or None,
            exit_code=parts[2].strip() or None,
            source="sacct",
        )

    def _print_status(self, status: JobStatus, *, run_id: str) -> None:
        print(f"Run ID: {run_id}")
        print(f"Job ID: {status.job_id}")
        print(f"State: {status.state}")
        if status.reason:
            print(f"Reason: {status.reason}")
        if status.node:
            print(f"Node: {status.node}")
        if status.elapsed:
            print(f"Elapsed: {status.elapsed}")
        if status.exit_code is not None:
            print(f"Exit code: {status.exit_code}")
        print(f"Source: {status.source}")
        if status.terminal and not status.success:
            print("Terminal failure (not reported as success).")

    def poll(
        self,
        identifier: str = "latest",
        *,
        interval: float = 30.0,
        timeout: float = 3600.0,
        pull: bool = False,
    ) -> JobStatus:
        if interval <= 0:
            raise OperatorError("invalid_interval")
        if timeout <= 0:
            raise OperatorError("invalid_timeout")
        record = self.resolve_run_record(identifier)
        run_id = str(record["run_id"])
        job_id = validate_job_id(str(record["job_id"]))
        started = self.monotonic_fn()
        last_state: str | None = None
        status: JobStatus | None = None
        while True:
            status = self._query_job_status(job_id)
            self._update_run(
                run_id,
                {
                    "last_known_slurm_state": status.state,
                    "last_status": status.as_dict(),
                    "last_status_timestamp_utc": _utc_now(),
                },
            )
            if status.state != last_state:
                self._print_status(status, run_id=run_id)
                last_state = status.state
            if status.terminal:
                if pull:
                    self.pull(run_id)
                return status
            if self.monotonic_fn() - started >= timeout:
                print(
                    f"Local poll timeout after {timeout}s; job {status.job_id} "
                    f"left running (no automatic cancellation)."
                )
                return status
            self.sleep_fn(interval)

    def pull(self, identifier: str = "latest", *, force: bool = False) -> Path:
        record = self.resolve_run_record(identifier)
        run_id = validate_run_id(str(record["run_id"]))
        local_run_dir = self.state_dir / run_id
        pull_dir = local_run_dir / "pulled"
        if pull_dir.exists() and any(pull_dir.iterdir()) and not force:
            raise OperatorError(f"pull_destination_exists:{pull_dir}")
        if force and pull_dir.exists():
            # Local-only replace: rename aside; never delete remote.
            backup = local_run_dir / f"pulled.bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            pull_dir.rename(backup)

        root_expr = self.remote_cluster_root_expr()
        resolve_cmd = f"ROOT={root_expr}; printf '%s\\n' \"$ROOT/runs/t12-canary/{run_id}\""
        resolved = self.ssh(resolve_cmd)
        if resolved.returncode != 0:
            raise OperatorError(f"remote_result_resolve_failed:{resolved.stderr}")
        remote_result = (resolved.stdout or "").strip().splitlines()[-1].strip()
        if not remote_result:
            raise OperatorError("remote_result_path_empty")
        remote_path_under_root(remote_result, cluster_root_expr="${T12_CLUSTER_ROOT}")

        exists = self.ssh(f"test -d {shlex.quote(remote_result)} && echo EXISTS")
        if "EXISTS" not in (exists.stdout or ""):
            raise OperatorError(f"remote_result_missing:{remote_result}")

        local_run_dir.mkdir(parents=True, exist_ok=True)
        transferred = self.scp_from_remote(remote_result, pull_dir)
        if transferred.returncode != 0:
            raise OperatorError(f"pull_failed:{transferred.stderr}")

        # scp -r remote_dir local may create pull_dir/<basename> or fill pull_dir
        if pull_dir.is_dir():
            children = list(pull_dir.iterdir())
            if len(children) == 1 and children[0].is_dir() and children[0].name == run_id:
                nested = children[0]
                for child in nested.iterdir():
                    target = pull_dir / child.name
                    if target.exists():
                        raise OperatorError(f"pull_collision:{target}")
                    child.rename(target)
                nested.rmdir()

        files = sorted(p for p in pull_dir.rglob("*") if p.is_file())
        print(f"Pulled to: {pull_dir}")
        print("Files received:")
        for path in files:
            print(f"  {path.relative_to(pull_dir)} ({path.stat().st_size} bytes)")
        print("Verify:")
        print(f"python scripts/t12_cluster_job.py --verify {run_id}")

        self._update_run(
            run_id,
            {
                "pulled": True,
                "local_pull_path": str(pull_dir.relative_to(self.repo_root)).replace("\\", "/"),
                "remote_result_path_resolved": remote_result,
                "pull_timestamp_utc": _utc_now(),
            },
        )
        return pull_dir

    def verify(self, identifier: str = "latest") -> dict[str, Any]:
        record = self.resolve_run_record(identifier)
        run_id = validate_run_id(str(record["run_id"]))
        profile_name = str(record["profile"])
        profile = get_profile(self.profiles_doc, profile_name)
        pull_rel = record.get("local_pull_path")
        if not pull_rel:
            raise OperatorError("results_not_pulled")
        pull_dir = self.repo_root / str(pull_rel)
        if not pull_dir.is_dir():
            raise OperatorError(f"pull_dir_missing:{pull_dir}")

        manifest_path = pull_dir / "run_manifest.json"
        if not manifest_path.is_file():
            raise OperatorError("run_manifest_missing")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        errors: list[str] = []
        expected_files = {str(name) for name in profile["expected_result_files"]}
        listed = {str(entry["relative_path"]): entry for entry in manifest.get("files", [])}

        present = {path.name for path in pull_dir.iterdir() if path.is_file()}
        missing = sorted(expected_files - present)
        # Extra files beyond expected + run_manifest internals are reported.
        extras = sorted(present - expected_files - {"run_manifest.json"})
        if missing:
            errors.append(f"missing_files:{','.join(missing)}")
        if extras:
            errors.append(f"extra_files:{','.join(extras)}")

        for rel, entry in listed.items():
            path = pull_dir / rel
            if not path.is_file():
                errors.append(f"manifest_file_missing:{rel}")
                continue
            observed_sha = sha256_file(path)
            if observed_sha != entry.get("sha256"):
                errors.append(f"hash_mismatch:{rel}")
            observed_size = path.stat().st_size
            if int(entry.get("size_bytes", -1)) != observed_size:
                errors.append(f"size_mismatch:{rel}")
            if path.suffix == ".jsonl":
                rows = count_jsonl_rows(path)
                expected_rows = entry.get("row_count")
                if expected_rows is not None and int(expected_rows) != rows:
                    errors.append(f"jsonl_count_mismatch:{rel}")

        source_manifest = pull_dir / "source_identity_manifest.json"
        if source_manifest.is_file():
            src = json.loads(source_manifest.read_text(encoding="utf-8"))
            if src.get("source_commit_sha") != record.get("source_commit_sha"):
                errors.append("source_commit_mismatch")
            if src.get("source_archive_sha256") != record.get("archive_sha256"):
                errors.append("source_archive_sha_mismatch")

        result = {
            "schema_version": "1.0.0",
            "run_id": run_id,
            "verified_at_utc": _utc_now(),
            "passed": not errors,
            "errors": errors,
            "missing_files": missing,
            "extra_files": extras,
            "files_checked": sorted(listed.keys()),
        }
        out = self.state_dir / run_id / "verification.json"
        atomic_write_json(out, result)
        self._update_run(run_id, {"verification_result": result["passed"], "verification_path": str(out.relative_to(self.repo_root)).replace("\\", "/")})
        if errors:
            print(f"VERIFY_FAILED: {'; '.join(errors)}")
            raise OperatorError("verification_failed")
        print("VERIFY_PASSED")
        return result

    def list_runs(self) -> list[dict[str, Any]]:
        state = self.load_state()
        runs = list((state.get("runs") or {}).values())
        runs.sort(key=lambda item: str(item.get("submission_timestamp_utc") or ""), reverse=True)
        if not runs:
            print("No recorded runs.")
            return []
        for item in runs:
            print(
                f"{item.get('run_id')} job={item.get('job_id')} "
                f"profile={item.get('profile')} state={item.get('last_known_slurm_state')} "
                f"pulled={item.get('pulled')}"
            )
        return runs
