# Ticket completion report

## Ticket
- ID: T12
- Slice: 2 — reproducible WSL2 inference/training environments and CUDA compatibility verification
- Slice verdict: **PASS**
- Full T12 ticket: **not complete** (no model selected; checkpoint loading untested)

## Preconditions checked
- Slice 1 committed at `c60f043` with 437-test baseline
- DEV-20260711-001 authorises T12 while T11 remains BLOCKED
- Driver 546.30 (CUDA 12.3 max); PyTorch cu118 selected
- No model weights downloaded; no research data accessed

## Slice 2 scope completed
- Two isolated WSL2 Python 3.11 environments (`t12-inference-wsl2`, `t12-training-wsl2`)
- Exact platform lockfiles compiled and installed via `uv`
- Deterministic environment probe script with CUDA and bitsandbytes verification
- Tracked compatibility evidence and environment manifests
- OS compiler dependency (`build-essential`) recorded separately from Python locks

## Slice 2 scope explicitly not done
- Model shortlist / candidate bake-off (Slice 3+)
- Checkpoint `from_pretrained` loading
- 4-bit quantised checkpoint loading
- LoRA/QLoRA adapter creation or training
- Model selection or licence register population
- T13/T14 activities

## Files created/changed

### Created
- `requirements/t12-inference.in`
- `requirements/t12-training.in`
- `requirements/locks/t12-inference-wsl2.lock`
- `requirements/locks/t12-training-wsl2.lock`
- `scripts/t12_probe_environment.py`
- `scripts/t12_wsl2_bootstrap.sh`
- `scripts/t12_wsl2_training_only.sh`
- `src/ambiguity_manager/model/environment_evidence.py`
- `configs/model/evidence/t12_environment_compatibility.json`
- `tests/test_t12_environment_compatibility.py`
- `docs/reports/ticket_T12_slice2_completion_report.md`

### Modified
- `.gitignore`
- `configs/environments/t12_inference_environment.json`
- `configs/environments/t12_training_environment.json`
- `src/ambiguity_manager/model/environment.py`
- `tests/test_t12_environment_manifests.py`

## Environment verification summary

| Environment | Status | bitsandbytes | CUDA compute | Imports |
|-------------|--------|--------------|--------------|---------|
| `t12-inference-wsl2` | `verified_compatible` | `cuda_operation_verified` | passed | all ok |
| `t12-training-wsl2` | `verified_compatible` | `cuda_operation_verified` | passed | all ok |

### Measured package versions (both environments unless noted)
- Python 3.11.15, uv 0.11.28
- torch 2.7.0+cu118 (CUDA build 11.8)
- transformers 5.13.0, tokenizers 0.22.2, safetensors 0.8.0, accelerate 1.14.0
- bitsandbytes 0.49.2
- peft 0.19.1, trl 1.8.0, datasets 5.0.0 (training only)

### CUDA smoke test (both environments)
- 32×32 matrix multiply on `cuda:0`
- `max_abs_diff`: 0.0, tolerance: 1e-4
- peak allocated: 8.137 MiB, peak reserved: 22.0 MiB

### bitsandbytes probe (both environments)
- Adam8bit optimizer step on CUDA tensor
- Status: `cuda_operation_verified`
- Requires host `build-essential` (gcc/g++/make); not in Python lockfiles

## OS compiler dependency provenance
| Package | Version |
|---------|---------|
| build-essential | 12.12ubuntu2.26.04.1 |
| gcc | 15.2.0 |
| g++ | 15.2.0 |
| make | 4.4.1 |

Environment variables: `CC=/usr/bin/gcc`, `CXX=/usr/bin/g++`

Bootstrap scripts check for gcc/g++/make and print:
`sudo apt-get update && sudo apt-get install -y build-essential`
when absent. Scripts never store or automate sudo passwords.

## Lockfile hashes (unchanged after build-essential install)
| File | SHA-256 |
|------|---------|
| `requirements/t12-inference.in` | `f79266858f8bc9c6960cc3c30ded8fab455f896928118812076444ad344fc0a9` |
| `requirements/t12-training.in` | `50641e8310b2fb5dc7e02ca7433357b975534520f548b9abaf343a07594aaac5` |
| `requirements/locks/t12-inference-wsl2.lock` | `ef7f9e0dd68901b6292ea8ebc89a653f5ef527bed5c2d14b1d1d2aa4bbe769b3` |
| `requirements/locks/t12-training-wsl2.lock` | `6a124016d3627cbb35d98b93bf309112e5bb655b35285fb8bbf1aaea99b795ea` |

## Non-blocking observations
1. `_POSIX_C_SOURCE` redefinition warning during Triton compilation
2. WSL ldconfig warning: `/usr/lib/wsl/lib/libcuda.so.1 is not a symbolic link`

Neither blocked Slice 2 PASS.

## Tests written first
- `tests/test_t12_environment_compatibility.py` — 30 deterministic Slice 2 tests

## Commands run
- `PYTHONPATH=src python -W error::ResourceWarning -m unittest discover -s tests` → OK
- `PYTHONPATH=src python scripts/validate_governance.py` → OK
- `git diff --check` → no whitespace errors

## Governance state preserved
- `selected_model`: null
- Model licence register `entries`: []
- `checkpoint_load_verified`: false (both manifests)
- T11 verdict: BLOCKED
- T13/T14: not started
- `pyproject.toml` core dependencies: empty

## Slice 2 verdict
**PASS** — both WSL2 environments are `verified_compatible` with CUDA and bitsandbytes operation verified. Full T12 ticket remains open pending model selection and later slices.
