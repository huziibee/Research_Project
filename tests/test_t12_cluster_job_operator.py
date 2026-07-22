"""CPU-only unit tests for the T12 Slurm cluster job operator."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ambiguity_manager.model.cluster.atomic_outputs import sha256_file
from ambiguity_manager.model.cluster.job_operator import (
    ClusterJobOperator,
    OperatorError,
    count_jsonl_rows,
    ensure_no_forbidden_tokens,
    get_profile,
    load_profiles,
    parse_sbatch_job_id,
    remote_path_under_root,
    validate_job_id,
)
from ambiguity_manager.paths import ProjectPaths

ROOT = ProjectPaths.from_repo_root().root


def _load_canary_module():
    path = ROOT / "scripts" / "t12_cluster_canary.py"
    spec = importlib.util.spec_from_file_location("t12_cluster_canary_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.ssh_responses: list[subprocess.CompletedProcess[str]] = []
        self.git_map: dict[tuple[str, ...], subprocess.CompletedProcess[str]] = {}
        self.default_ssh = subprocess.CompletedProcess(["ssh"], 0, stdout="ok\n", stderr="")

    def __call__(self, cmd: list[str], kwargs=None) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(cmd))
        if cmd and cmd[0] == "git":
            args = tuple(cmd[3:])
            if args in self.git_map:
                return self.git_map[args]
            if args and args[0] == "archive":
                output = None
                for part in args:
                    if part.startswith("--output="):
                        output = Path(part.split("=", 1)[1])
                if output is not None:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(b"fake-archive")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd and cmd[0] == "ssh":
            if self.ssh_responses:
                return self.ssh_responses.pop(0)
            return self.default_ssh
        if cmd and cmd[0] == "scp":
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


class OperatorUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "configs" / "cluster").mkdir(parents=True)
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "src").mkdir(parents=True)
        (self.root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        profiles = json.loads((ROOT / "configs/cluster/t12_job_profiles.json").read_text(encoding="utf-8"))
        (self.root / "configs/cluster/t12_job_profiles.json").write_text(
            json.dumps(profiles, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.root / "scripts/t12_cluster_canary.py").write_text("# canary\n", encoding="utf-8")
        self.runner = FakeRunner()
        self.head = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        self.runner.git_map = {
            ("branch", "--show-current"): subprocess.CompletedProcess(
                [], 0, stdout="feature/t12-cluster-redesign\n", stderr=""
            ),
            ("diff", "--cached", "--name-only"): subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            ("diff", "--name-only"): subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            ("status", "--porcelain=v1", "--untracked-files=all"): subprocess.CompletedProcess(
                [],
                0,
                stdout="?? configs.zip\n?? test-output.txt\n?? t12-abcdef0.tar.gz\n",
                stderr="",
            ),
            ("rev-parse", "HEAD"): subprocess.CompletedProcess([], 0, stdout=self.head + "\n", stderr=""),
        }

    def _operator(self, **kwargs) -> ClusterJobOperator:
        return ClusterJobOperator(
            repo_root=self.root,
            runner=self.runner,
            sleep_fn=lambda _s: None,
            **kwargs,
        )

    def test_run_packages_exact_head(self) -> None:
        op = self._operator()
        self.runner.ssh_responses = [
            subprocess.CompletedProcess([], 0, stdout="ok\n", stderr=""),
            subprocess.CompletedProcess(
                [], 0, stdout="/home/u/t12-hpc/runs/t12-canary/.prep-x\n", stderr=""
            ),
            subprocess.CompletedProcess([], 0, stdout="ARCHIVE_HASH_MATCH\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="4123\n", stderr=""),
        ]
        record = op.run_profile("canary")
        self.assertEqual(record["source_commit_sha"], self.head)
        self.assertEqual(record["job_id"], "4123")
        local_archive = list((self.root / "outputs/t12_cluster_jobs").rglob("t12-aaaaaaa.tar.gz"))
        self.assertEqual(len(local_archive), 1)
        self.assertEqual(sha256_file(local_archive[0]), record["archive_sha256"])

    def test_dirty_staged_index_blocks(self) -> None:
        self.runner.git_map[("diff", "--cached", "--name-only")] = subprocess.CompletedProcess(
            [], 0, stdout="foo.py\n", stderr=""
        )
        op = self._operator()
        with self.assertRaises(OperatorError) as ctx:
            op.run_profile("canary")
        self.assertIn("staged_index", str(ctx.exception))

    def test_unexpected_tracked_modification_blocks(self) -> None:
        self.runner.git_map[("diff", "--name-only")] = subprocess.CompletedProcess(
            [], 0, stdout="src/x.py\n", stderr=""
        )
        op = self._operator()
        with self.assertRaises(OperatorError) as ctx:
            op.run_profile("canary")
        self.assertIn("unexpected_tracked", str(ctx.exception))

    def test_allowed_teach_dirty_does_not_block(self) -> None:
        self.runner.git_map[("diff", "--name-only")] = subprocess.CompletedProcess(
            [], 0, stdout="data/raw/TEACh\n", stderr=""
        )
        self.runner.ssh_responses = [
            subprocess.CompletedProcess([], 0, stdout="ok\n", stderr=""),
            subprocess.CompletedProcess(
                [], 0, stdout="/home/u/t12-hpc/runs/t12-canary/.prep-x\n", stderr=""
            ),
            subprocess.CompletedProcess([], 0, stdout="ARCHIVE_HASH_MATCH\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="4124\n", stderr=""),
        ]
        op = self._operator()
        record = op.run_profile("canary")
        self.assertEqual(record["job_id"], "4124")

    def test_source_manifest_hash_deterministic(self) -> None:
        op = self._operator()
        m1 = op.build_source_identity_manifest(
            source_commit_sha=self.head,
            source_archive_sha256="b" * 64,
            archive_filename="t12-aaaaaaa.tar.gz",
            packaging_timestamp="2026-07-21T12:00:00Z",
        )
        m2 = op.build_source_identity_manifest(
            source_commit_sha=self.head,
            source_archive_sha256="b" * 64,
            archive_filename="t12-aaaaaaa.tar.gz",
            packaging_timestamp="2026-07-21T12:00:00Z",
        )
        self.assertEqual(m1, m2)
        self.assertEqual(m1["transfer_method"], "git_archive")

    def test_ssh_batchmode_failure_blocks(self) -> None:
        self.runner.ssh_responses = [
            subprocess.CompletedProcess([], 1, stdout="", stderr="Permission denied"),
        ]
        op = self._operator()
        with self.assertRaises(OperatorError) as ctx:
            op.run_profile("canary")
        self.assertIn("ssh_batchmode_failed", str(ctx.exception))

    def test_sbatch_job_id_parsing(self) -> None:
        self.assertEqual(parse_sbatch_job_id("4123\n"), "4123")
        self.assertEqual(parse_sbatch_job_id("4123;cluster\n"), "4123")

    def test_malformed_job_id_blocks(self) -> None:
        with self.assertRaises(OperatorError):
            parse_sbatch_job_id("not-a-job")
        with self.assertRaises(OperatorError):
            validate_job_id("12ab")

    def test_state_file_written_atomically(self) -> None:
        op = self._operator()
        op._update_run("t12-canary-1", {"run_id": "t12-canary-1", "job_id": "1"})
        self.assertTrue(op.state_path.is_file())
        payload = json.loads(op.state_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["latest_run_id"], "t12-canary-1")

    def test_latest_resolves(self) -> None:
        op = self._operator()
        op._update_run("run-a", {"run_id": "run-a", "job_id": "1"})
        op._update_run("run-b", {"run_id": "run-b", "job_id": "2"})
        self.assertEqual(op.resolve_run_record("latest")["run_id"], "run-b")
        self.assertEqual(op.resolve_run_record("2")["run_id"], "run-b")

    def test_squeue_state_parsing(self) -> None:
        op = self._operator()
        op._update_run("run-a", {"run_id": "run-a", "job_id": "99", "profile": "canary"})
        self.runner.ssh_responses = [
            subprocess.CompletedProcess(
                [], 0, stdout="99|RUNNING|(None)|mscluster01|00:01:02\n", stderr=""
            )
        ]
        status = op.status("latest")
        self.assertEqual(status.state, "RUNNING")
        self.assertEqual(status.node, "mscluster01")
        self.assertFalse(status.terminal)

    def test_sacct_fallback(self) -> None:
        op = self._operator()
        op._update_run("run-a", {"run_id": "run-a", "job_id": "99", "profile": "canary"})
        self.runner.ssh_responses = [
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(
                [],
                0,
                stdout="99|FAILED|1:0|00:00:05|mscluster02|NonZeroExitCode\n",
                stderr="",
            ),
        ]
        status = op.status("latest")
        self.assertEqual(status.state, "FAILED")
        self.assertEqual(status.source, "sacct")
        self.assertTrue(status.terminal)
        self.assertFalse(status.success)

    def test_pending_reason_retention(self) -> None:
        op = self._operator()
        op._update_run("run-a", {"run_id": "run-a", "job_id": "99", "profile": "canary"})
        self.runner.ssh_responses = [
            subprocess.CompletedProcess(
                [], 0, stdout="99|PENDING|(Resources)||00:00:00\n", stderr=""
            )
        ]
        status = op.status("latest")
        self.assertEqual(status.state, "PENDING")
        self.assertEqual(status.reason, "(Resources)")

    def test_terminal_failure_not_success(self) -> None:
        op = self._operator()
        op._update_run("run-a", {"run_id": "run-a", "job_id": "99", "profile": "canary"})
        self.runner.ssh_responses = [
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(
                [], 0, stdout="99|TIMEOUT|0:0|00:10:00|node|TimedOut\n", stderr=""
            ),
        ]
        status = op.status("latest")
        self.assertTrue(status.terminal)
        self.assertFalse(status.success)

    def test_polling_stops_at_terminal(self) -> None:
        op = self._operator()
        op._update_run("run-a", {"run_id": "run-a", "job_id": "99", "profile": "canary"})
        self.runner.ssh_responses = [
            subprocess.CompletedProcess([], 0, stdout="99|RUNNING|(None)|n1|00:00:01\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(
                [], 0, stdout="99|COMPLETED|0:0|00:00:02|n1|\n", stderr=""
            ),
        ]
        status = op.poll("latest", interval=0.01, timeout=10.0, pull=False)
        self.assertEqual(status.state, "COMPLETED")
        self.assertTrue(status.success)

    def test_local_timeout_does_not_cancel(self) -> None:
        clock = {"t": 0.0}

        def monotonic() -> float:
            return clock["t"]

        def sleep_fn(seconds: float) -> None:
            clock["t"] += float(seconds)

        op = ClusterJobOperator(
            repo_root=self.root,
            runner=self.runner,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic,
        )
        op._update_run("run-a", {"run_id": "run-a", "job_id": "99", "profile": "canary"})
        self.runner.ssh_responses = [
            subprocess.CompletedProcess([], 0, stdout="99|RUNNING|(None)|n1|00:00:01\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="99|RUNNING|(None)|n1|00:00:02\n", stderr=""),
        ]
        status = op.poll("latest", interval=30.0, timeout=10.0, pull=False)
        self.assertEqual(status.state, "RUNNING")
        joined = " ".join(" ".join(c) for c in self.runner.calls)
        self.assertNotIn("scancel", joined)

    def test_pull_destination_collision_blocks(self) -> None:
        op = self._operator()
        run_id = "t12-canary-collision"
        pull = self.root / "outputs/t12_cluster_jobs" / run_id / "pulled"
        pull.mkdir(parents=True)
        (pull / "existing.txt").write_text("x", encoding="utf-8")
        op._update_run(
            run_id,
            {
                "run_id": run_id,
                "job_id": "1",
                "profile": "canary",
                "remote_result_path_template": "${T12_CLUSTER_ROOT}/runs/t12-canary/" + run_id,
            },
        )
        with self.assertRaises(OperatorError) as ctx:
            op.pull(run_id)
        self.assertIn("pull_destination_exists", str(ctx.exception))

    def test_failed_job_evidence_can_be_pulled(self) -> None:
        run_id = "t12-canary-failed"
        remote = f"/home/u/t12-hpc/runs/t12-canary/{run_id}"
        calls: list[list[str]] = []

        def runner(cmd, kwargs=None):
            calls.append(list(cmd))
            if cmd[0] == "scp":
                dest = Path(cmd[-1])
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "canary_result.json").write_text("{}", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[0] == "ssh":
                remote_cmd = cmd[-1]
                if "printf" in remote_cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout=remote + "\n", stderr="")
                if "test -d" in remote_cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout="EXISTS\n", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

        op = ClusterJobOperator(repo_root=self.root, runner=runner, sleep_fn=lambda _s: None)
        op._update_run(
            run_id,
            {
                "run_id": run_id,
                "job_id": "55",
                "profile": "canary",
                "last_known_slurm_state": "FAILED",
            },
        )
        pulled = op.pull(run_id)
        self.assertTrue((pulled / "canary_result.json").is_file())

    def _seed_verify_bundle(self, run_id: str, *, bad_hash: bool = False, bad_count: bool = False) -> Path:
        pull = self.root / "outputs/t12_cluster_jobs" / run_id / "pulled"
        pull.mkdir(parents=True)
        records = pull / "canary_records.jsonl"
        records.write_text('{"record_id":"canary-001"}\n', encoding="utf-8")
        result_path = pull / "canary_result.json"
        result_path.write_text(json.dumps({"success": True}) + "\n", encoding="utf-8")
        src = {
            "schema_version": "1.0.0",
            "source_commit_sha": self.head,
            "source_archive_sha256": "c" * 64,
            "transfer_method": "git_archive",
            "archive_filename": "t12-aaaaaaa.tar.gz",
            "packaging_timestamp": "2026-07-21T12:00:00Z",
        }
        src_path = pull / "source_identity_manifest.json"
        src_path.write_text(json.dumps(src) + "\n", encoding="utf-8")
        files = []
        for path in (records, result_path, src_path):
            entry = {
                "relative_path": path.name,
                "sha256": ("0" * 64) if (bad_hash and path == records) else sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            if path.suffix == ".jsonl":
                entry["row_count"] = 99 if bad_count else 1
            files.append(entry)
        (pull / "run_manifest.json").write_text(json.dumps({"files": files}) + "\n", encoding="utf-8")
        return pull

    def test_manifest_hash_verification_passes(self) -> None:
        op = self._operator()
        run_id = "t12-canary-verify-ok"
        self._seed_verify_bundle(run_id)
        op._update_run(
            run_id,
            {
                "run_id": run_id,
                "job_id": "7",
                "profile": "canary",
                "source_commit_sha": self.head,
                "archive_sha256": "c" * 64,
                "local_pull_path": f"outputs/t12_cluster_jobs/{run_id}/pulled",
                "pulled": True,
            },
        )
        result_doc = op.verify(run_id)
        self.assertTrue(result_doc["passed"])

    def test_wrong_hash_fails(self) -> None:
        op = self._operator()
        run_id = "t12-canary-verify-bad-hash"
        self._seed_verify_bundle(run_id, bad_hash=True)
        op._update_run(
            run_id,
            {
                "run_id": run_id,
                "job_id": "7",
                "profile": "canary",
                "source_commit_sha": self.head,
                "archive_sha256": "c" * 64,
                "local_pull_path": f"outputs/t12_cluster_jobs/{run_id}/pulled",
                "pulled": True,
            },
        )
        with self.assertRaises(OperatorError):
            op.verify(run_id)

    def test_wrong_jsonl_count_fails(self) -> None:
        op = self._operator()
        run_id = "t12-canary-verify-bad-count"
        self._seed_verify_bundle(run_id, bad_count=True)
        op._update_run(
            run_id,
            {
                "run_id": run_id,
                "job_id": "7",
                "profile": "canary",
                "source_commit_sha": self.head,
                "archive_sha256": "c" * 64,
                "local_pull_path": f"outputs/t12_cluster_jobs/{run_id}/pulled",
                "pulled": True,
            },
        )
        with self.assertRaises(OperatorError):
            op.verify(run_id)

    def test_credentials_never_persisted(self) -> None:
        op = self._operator()
        with self.assertRaises(OperatorError):
            op.save_state({"runs": {}, "password": "secret"})

    def test_remote_paths_cannot_escape(self) -> None:
        with self.assertRaises(OperatorError):
            remote_path_under_root("/tmp/../etc/passwd", cluster_root_expr="$HOME/t12-hpc")

    def test_profile_names_allowlisted(self) -> None:
        doc = load_profiles(ROOT)
        with self.assertRaises(OperatorError):
            get_profile(doc, "d_final")
        profile = get_profile(doc, "canary")
        self.assertFalse(profile["gpus_required"])

    def test_no_destructive_command_generated(self) -> None:
        op = self._operator()
        text = op._render_sbatch(
            profile=get_profile(load_profiles(ROOT), "canary"),
            run_id="t12-canary-20260721T120000Z-abcdef0",
            head_sha=self.head,
            archive_sha="d" * 64,
            archive_filename="t12-abcdef0.tar.gz",
        )
        ensure_no_forbidden_tokens(text)
        self.assertNotIn("rm -rf", text)
        self.assertNotIn("scancel", text)
        self.assertNotIn("git init", text)

    def test_no_ml_imports(self) -> None:
        banned = {"torch", "transformers", "vllm"}
        for name in banned:
            self.assertNotIn(name, sys.modules)
        import ambiguity_manager.model.cluster.job_operator as mod

        for name in banned:
            self.assertNotIn(name, sys.modules)
        self.assertTrue(mod.__name__.endswith("job_operator"))


class CanaryScriptTests(unittest.TestCase):
    def test_canary_writes_evidence(self) -> None:
        canary = _load_canary_module()
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = Path(tmp) / "out"
            src_manifest = Path(tmp) / "source_identity_manifest.json"
            src_manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "source_commit_sha": "a" * 40,
                        "source_archive_sha256": "b" * 64,
                        "transfer_method": "git_archive",
                        "archive_filename": "x.tar.gz",
                        "packaging_timestamp": "2026-07-21T12:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            rc = canary.main(
                [
                    "--result-dir",
                    str(result_dir),
                    "--run-id",
                    "t12-canary-test",
                    "--source-commit",
                    "a" * 40,
                    "--source-archive-sha256",
                    "b" * 64,
                    "--source-identity-manifest",
                    str(src_manifest),
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue((result_dir / "run_manifest.json").is_file())
            self.assertEqual(count_jsonl_rows(result_dir / "canary_records.jsonl"), 1)


if __name__ == "__main__":
    unittest.main()
