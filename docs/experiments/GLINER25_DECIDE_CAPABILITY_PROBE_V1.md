# GLiNER2.5-Decide local capability-status probe

**Status:** exploratory local result, 2026-10-02. The model was installed in
an ignored, isolated Python 3.11 environment. No Pilot-120 source, gold,
historical prediction, or paper result was changed. Text-free case-level
predictions and the summary are tracked under
[`research/pilot120/gliner25_decide_capability_probe_v1`](../../research/pilot120/gliner25_decide_capability_probe_v1/).
This is a candidate classifier probe, not an
official pipeline score or a validated replacement for the Figure 6 gates.

## Model and question

The [model card](https://huggingface.co/fastino/GLiNER2.5-Decide) describes
the English 340M-parameter GLiNER2.5-Decide checkpoint as an operational
classifier that accepts task-specific candidate labels. The vendor reports
60.2% average exact match on its own 17-domain benchmark, compared with
59.6% for its 1B Decide variant. These are vendor results on a different
dataset. The model is Apache-2.0 and explicitly does not produce reasoning,
explanations, or open-ended task representations. The [GLiNER2 library](https://github.com/fastino-ai/GLiNER2)
documents local installation with `gliner2[local]` and `AutoExtractor`.

The frozen Pilot-120 `capability_status` ontology has five labels:
`capable`, `conditionally_capable`, `incapable`, `unauthorized`, and `unsafe`.
It is **not a pure physical-capability label**: authorization and safety are
included. This probe tests whether a fixed five-label GLiNER2 classifier
recovers that existing status from the original command, dialogue, scene, and
robot capability context. It does not receive gold or prior predictions.
The fixed label descriptions and source renderer are in
[`gliner25_decide_capability_probe_v1.py`](../../scripts/experiments/gliner25_decide_capability_probe_v1.py).

## Exact inputs and run

| Item | Version or SHA-256 |
| --- | --- |
| Model | `fastino/GLiNER2.5-Decide@5a7adf72a23b4d311abae6ce050d7f0012bb3416` |
| `model.safetensors` | `40a5a23ff860dc3dff426cecd1048cacdd29c648c96db209dad818e9686dc997` |
| [Source](../../data/annotations/pilot_120_v1/source_canonical.jsonl) | `f33b1e29f1e8aa256a475f07213aa07247def47d8e2148d54a472a40b71b05c9` |
| [Gold](../../data/annotations/pilot_120_v1/pilot_120_final_gold.jsonl) | `5e23ad1a92ff1873c8f039a8ce560a111dd6fb6b8ae8c11d6cf34dbfa1c360db` |
| Local runtime | Python 3.11.15, `gliner2==2.0.0`, `torch==2.14.1+cpu`, `transformers==4.57.6`, `hf_xet==1.6.0` |
| Prediction JSONL | `4d9553f666d14eaef0bca08ae2b7f51a531821ef98e4f19fa1d2728a04ce7521` |
| Summary JSON | `4bf3a11a81a52baa17f9c80038fb699669b1dbee7da6186894848efc1c2a68c4` |
| Ten-file model snapshot manifest | `77e7c87764194fca2336196658f6a3a2f45999c14db2160bef610a9584cb7ec5` |

Install from repository root on a machine with Python 3.11 and sufficient
free space for the ~1.95 GB checkpoint and dependencies:

```powershell
py -3.11 -m venv outputs/model_runs/gliner25_decide/env
outputs/model_runs/gliner25_decide/env/Scripts/python.exe -m pip install -r configs/experiments/gliner25_decide_windows_py311_requirements_v1.txt
outputs/model_runs/gliner25_decide/env/Scripts/python.exe -c "from huggingface_hub import snapshot_download; snapshot_download('fastino/GLiNER2.5-Decide', revision='5a7adf72a23b4d311abae6ce050d7f0012bb3416', local_dir='outputs/model_runs/gliner25_decide/model')"
$env:HF_HUB_OFFLINE = '1'
outputs/model_runs/gliner25_decide/env/Scripts/python.exe scripts/experiments/gliner25_decide_capability_probe_v1.py --model-dir outputs/model_runs/gliner25_decide/model --output-dir outputs/model_runs/gliner25_decide/pilot120_capability_probe_v1
```

The [requirements file](../../configs/experiments/gliner25_decide_windows_py311_requirements_v1.txt)
records the exact observed Windows Python 3.11 CPU package versions. The
[snapshot manifest](../../research/pilot120/gliner25_decide_capability_probe_v1/model_snapshot_sha256.json)
records the pinned revision and SHA-256 of all ten downloaded model files.
The script checks the full model snapshot and the frozen source hash before
inference. It checks gold only after prediction, requires the same 120 unique
source and gold IDs, writes one prediction per source ID, retains
failed cases in the denominator, and records the fixed schema and confusion
matrix in `summary.json`. A one-case offline smoke on `CA-0007` succeeded
before the full run. The full output has 120 rows, zero failures, and the
prediction hash above. The downloaded model and working run outputs remain
under the ignored `outputs/model_runs/gliner25_decide/` directory. Copies of
the text-free [predictions](../../research/pilot120/gliner25_decide_capability_probe_v1/predictions.jsonl),
[summary](../../research/pilot120/gliner25_decide_capability_probe_v1/summary.json),
and [checksum manifest](../../research/pilot120/gliner25_decide_capability_probe_v1/SHA256_FINAL.txt)
are tracked for audit. After the review fixes, a second offline 120-case run
with the final script produced byte-identical prediction and summary hashes.

## Observed result

Exact five-class status: **104/120 (86.7%)**, with zero inference failures.
The majority-class predictor (`capable` for every case) would score 97/120
(80.8%). The per-class result matters more than the aggregate:

| Gold status | Number | Correct | Main misses |
| --- | ---: | ---: | --- |
| `capable` | 97 | 97 | None |
| `conditionally_capable` | 2 | 0 | Both `capable` |
| `incapable` | 7 | 0 | Six `capable`, one `conditionally_capable` |
| `unauthorized` | 12 | 7 | Four `capable`, one `incapable` |
| `unsafe` | 2 | 0 | Both `incapable` |

Twelve of the 23 non-`capable` cases were labelled `capable`. The model
therefore cannot safely serve as the sole capability, authorization, or
safety gate in the current flow. Its confidence output is uncalibrated for
this project and was not used to select or reject predictions.

Pilot-120 has already informed this project's development. This is a
development-set probe with fixed labels, not a new held-out validation or a
matched comparison to Qwen routing. It tests a status category, not intent,
the 13 CPC task slots, Pilot-17 ambiguity types, grounding, route correctness,
or end-to-end robot task understanding. Those require separate, frozen
evaluation protocols and reference annotations. Any revised label wording,
binary decomposition, or threshold is a **new versioned condition** and must
not replace these rows or be presented as a clean held-out improvement.
