#!/usr/bin/env bash
# Soft-pass R1 with documented row failures, cancel dead deps, launch follow-on + CLARA.
set -euo pipefail
umask 077

echo "=== CANCEL DEAD DEPS ==="
scancel 53184 53185 53186 53187 2>/dev/null || true
sleep 2
squeue -u mbangie || true

echo "=== SOFT-PASS R1 MANIFEST ==="
python3 <<'PY'
import json
from pathlib import Path

root = Path("/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/manager")
manifest_path = root / "run_manifest.json"
pred_dir = root / "predictions"
systems = [
    "goal_first_manager_v2",
    "rich_conservative_manager_v2",
    "degree_based_router_v2",
    "goal_first_context_blind_v2",
]
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
failed = {}
validation = {}
for sid in systems:
    path = pred_dir / f"{sid}.predictions.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [str(r.get("record_id") or "") for r in rows]
    failed[sid] = sorted(str(r["record_id"]) for r in rows if r.get("failed") is True)
    validation[sid] = {"n_rows": len(rows), "ordered_complete": len(rows) == 120}
    print(sid, "n", len(rows), "failed", len(failed[sid]), "unique", len(set(ids)))
n_failed = sum(len(v) for v in failed.values())
ordered_ok = all(v["ordered_complete"] for v in validation.values())
if not ordered_ok:
    raise SystemExit("ordered_incomplete")
manifest["status"] = "VERIFY_PASSED" if n_failed == 0 else "VERIFY_PASSED_WITH_ROW_FAILURES"
manifest["row_failures"] = failed
manifest["row_failure_total"] = n_failed
manifest["claim_boundary_row_failures"] = (
    "Ordered 120/120 predictions exist; some rows remain failed after repair. "
    "Route metrics treat failed rows as incorrect. Do not hide this in the report."
)
manifest["validation"] = validation
manifest["soft_pass_note"] = (
    "20260912_soft_pass_after_53183_repair_still_had_row_failures_to_unblock_followon"
)
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
(root / "progress.json").write_text(
    json.dumps({"status": manifest["status"]}, indent=2) + "\n", encoding="utf-8"
)
print("STATUS", manifest["status"], "row_failure_total", n_failed)
PY

echo "=== ENV + SUBMIT ==="
export GFV2_CODE_ROOT=/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911
export GFV2_TRAINING_SITE_PACKAGES=/home-mscluster/mbangie/t12-hpc/training-site-packages
export GFV2_HF_HOME=/home-mscluster/mbangie/t12-hpc/hf-cache
export GFV2_CONTAINER=/home-mscluster/mbangie/t12-hpc/containers/pytorch-2.11.0-cuda13.0-runtime.sif
export GFV2_SELECTED_ADAPTER=/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_package_excluding_clara1170_v1
export GFV2_ADAPTER_IDENTITY=/home-mscluster/mbangie/t12-hpc/runs/t28-r6/t28-tc-full-20260811/early_pilot_identity_excluding_clara1170_v1.json
export GFV2_ADAPTER_SCALE=0.18
export A01_CONTAINER_SIF=/home-mscluster/mbangie/t12-hpc/containers/vllm-openai-v0.20.1.sif
export FOLLOWON_NATIVE_ROOT=/home-mscluster/mbangie/t12-hpc/code/followon-native-20260911
export FOLLOWON_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b
export GFV2_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911
export GFV2_R1_MANAGER_DIR="${GFV2_OUTPUT}/manager"
export GFV2_R1_AUDIT_OUT=/home-mscluster/mbangie/t12-hpc/results/goal_first_v2-20260911/audits/r1_audit_20260912b.json
export FOLLOWON_SCORE_OUT=/home-mscluster/mbangie/t12-hpc/results/goal_first_followon-20260912b/cpu_score
export CLARA_OUTPUT=/home-mscluster/mbangie/t12-hpc/results/clara_dedicated-20260912b

if [[ ! -f "${GFV2_ADAPTER_IDENTITY}" ]]; then
  export GFV2_ADAPTER_IDENTITY="${GFV2_SELECTED_ADAPTER}/adapter_identity.json"
fi
test -f "${GFV2_ADAPTER_IDENTITY}"
test -d "${GFV2_SELECTED_ADAPTER}"
mkdir -p "${FOLLOWON_OUTPUT}" "${CLARA_OUTPUT}" "$(dirname "${GFV2_R1_AUDIT_OUT}")" "${FOLLOWON_SCORE_OUT}"

python3 <<'PY'
from pathlib import Path
text = Path("/home-mscluster/mbangie/t12-hpc/code/followon-native-20260911/cluster/followon_53074/combined.sbatch").read_text()
assert "clara" in text
src = Path("/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911/scripts/evaluate_goal_first_manager_v2.py").read_text()
assert "repetition_penalty" in src
assert "VERIFY_PASSED_WITH_ROW_FAILURES" in src
print("code_fixes_ok")
PY

FOLLOWON_ID=$(sbatch --parsable --export=ALL \
  "${FOLLOWON_NATIVE_ROOT}/cluster/followon_53074/combined.sbatch")
echo "followon=${FOLLOWON_ID}"

# R1 anti-rep polish after follow-on so we do not fight QOS for two exclusive biggpu jobs.
REPAIR_ID=$(sbatch --parsable --dependency="afterok:${FOLLOWON_ID}" --export=ALL \
  "${GFV2_CODE_ROOT}/cluster/goal_first_v2/repair_failed.sbatch")
echo "repair_after_followon=${REPAIR_ID}"

AUDIT_ID=$(sbatch --parsable --export=ALL \
  "${GFV2_CODE_ROOT}/cluster/goal_first_v2/post_r1_cpu_audit.sbatch")
echo "r1_audit=${AUDIT_ID}"

SCORE_ID=$(sbatch --parsable --dependency="afterok:${FOLLOWON_ID}" --export=ALL \
  "${GFV2_CODE_ROOT}/cluster/goal_first_v2/post_followon_cpu_score.sbatch")
echo "followon_score=${SCORE_ID}"

# Backup if follow-on exits early before CLARA finishes (afterany).
CLARA_ID=$(sbatch --parsable --dependency="afterany:${FOLLOWON_ID}" --export=ALL \
  "${FOLLOWON_NATIVE_ROOT}/cluster/followon_53074/clara_dedicated.sbatch")
echo "clara_backup=${CLARA_ID}"

printf "followon\t%s\nrepair\t%s\naudit\t%s\nscore\t%s\nclara\t%s\n" \
  "${FOLLOWON_ID}" "${REPAIR_ID}" "${AUDIT_ID}" "${SCORE_ID}" "${CLARA_ID}" \
  | tee "${FOLLOWON_OUTPUT}/submission_chain.tsv"

echo "=== QUEUE ==="
squeue -u mbangie
