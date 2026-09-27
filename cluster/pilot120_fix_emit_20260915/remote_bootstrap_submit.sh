#!/bin/bash
set -euo pipefail
SRC=/home-mscluster/mbangie/t12-hpc/code/goal_first_v2-20260911
DEST=/home-mscluster/mbangie/t12-hpc/code/pilot120_fix_emit-20260915
OUT=/home-mscluster/mbangie/t12-hpc/results/pilot120_fix_emit-20260915
mkdir -p "$DEST" "$OUT" /home-mscluster/mbangie/t12-hpc/logs /tmp/p120_fix_overlay
# Refresh DEST from known-good tree if eval missing
if [ ! -f "$DEST/scripts/evaluate_goal_first_manager_v2.py" ]; then
  rsync -a --delete --exclude outputs --exclude .git "$SRC/" "$DEST/"
fi
# Overlay staged files if present
if [ -d /tmp/p120_fix_overlay ]; then
  cp -f /tmp/p120_fix_overlay/goal_first_analysis_v2.py "$DEST/src/ambiguity_manager/systems/" 2>/dev/null || true
  cp -f /tmp/p120_fix_overlay/response_generation.py "$DEST/src/ambiguity_manager/systems/" 2>/dev/null || true
  cp -f /tmp/p120_fix_overlay/score_official_sidecar_followon.py "$DEST/scripts/" 2>/dev/null || true
  mkdir -p "$DEST/cluster/pilot120_fix_emit_20260915"
  cp -f /tmp/p120_fix_overlay/fix_emit.sbatch /tmp/p120_fix_overlay/submit.sh /tmp/p120_fix_overlay/README.md \
    "$DEST/cluster/pilot120_fix_emit_20260915/" 2>/dev/null || true
  chmod +x "$DEST/cluster/pilot120_fix_emit_20260915/"*.sh 2>/dev/null || true
  sed -i 's/\r$//' "$DEST/cluster/pilot120_fix_emit_20260915/"*.sh "$DEST/cluster/pilot120_fix_emit_20260915/"*.sbatch 2>/dev/null || true
fi
grep -n "CRITICAL CPC RULE\|unknown.*filled\|provider_version" \
  "$DEST/src/ambiguity_manager/systems/goal_first_analysis_v2.py" \
  "$DEST/src/ambiguity_manager/systems/response_generation.py" | head -20
export FIX_CODE_ROOT="$DEST" FIX_OUTPUT="$OUT" MEGA_JOB=54259
bash "$DEST/cluster/pilot120_fix_emit_20260915/submit.sh"
