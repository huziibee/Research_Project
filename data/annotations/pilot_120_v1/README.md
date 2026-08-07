# Pilot-120 v1 artefacts

**Status:** NOT FROZEN (see `STATUS.json`)

Expected layout after a successful final-protocol freeze:

```text
source_canonical.jsonl          # exactly 120 repaired evidence records
blind_packages/ANN-A.jsonl      # evidence-only
blind_packages/ANN-B.jsonl      # evidence-only
annotations_raw/ANN-A.jsonl     # independent final-protocol labels
annotations_raw/ANN-B.jsonl
adjudication/disagreements.jsonl
adjudication/decisions.jsonl
reports/final_protocol_agreement.json
final_gold.jsonl
manifest.json
hashes.json
freeze_report.json
STATUS.json
```

Do not load these artefacts for training/dev/tuning. Evaluation command:

```bash
python3 -m ambiguity_manager.evaluation.pilot_120_cli evaluate \
  --config configs/evaluation/pilot_120_v1.json \
  --predictions <PREDICTIONS.jsonl>
```
