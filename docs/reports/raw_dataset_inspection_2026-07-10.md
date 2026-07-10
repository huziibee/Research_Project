# Raw Dataset Inspection — Manual Snapshot (2026-07-10)

**Type:** Manual inspection snapshot (human-directed, read-only).
**Status:** Informational. This snapshot does **not** replace the automated T02
dataset audit (`docs/mapping/dataset_audit.md` and
`outputs/metrics/dataset_audit.json`), which must be produced by code in ticket
T02. Counts here were gathered by manual inspection and targeted commands; treat
them as provisional until T02 verifies them programmatically.

**Scope inspected:** `data/raw/` (read-only). No raw files were modified.

---

## Filesystem vs Git reconciliation (verified 2026-07-10)

An earlier filesystem inspection reported IndirectRequests, SafeAgentBench, and
VAGUE payloads as "missing / metadata-only". A later `git ls-files data/raw`
showed the payload files as tracked. This was reconciled by reading the actual
files on disk (size + magic-byte header, LFS-pointer check):

| File | Tracked in Git | Present on disk | Real payload | LFS pointer / stub |
|---|---|---|---|---|
| `IndirectRequests/train/data-00000-of-00001.arrow` | Yes | Yes (94,424 B) | Yes (Arrow magic `FF FF FF FF ...`) | No |
| `IndirectRequests/validation/data-00000-of-00001.arrow` | Yes | Yes (97,784 B) | Yes (Arrow) | No |
| `IndirectRequests/test/data-00000-of-00001.arrow` | Yes | Yes (166,608 B) | Yes (Arrow) | No |
| `SafeAgentBench/abstract/train.arrow/data-00000-of-00001.arrow` | Yes | Yes (37,920 B) | Yes (Arrow) | No |
| `SafeAgentBench/unsafe_detailed/.../data-00000-of-00001.arrow` | Yes | Yes (63,176 B) | Yes (Arrow) | No |
| `SafeAgentBench/safe_detailed/.../data-00000-of-00001.arrow` | Yes | Yes (70,264 B) | Yes (Arrow) | No |
| `SafeAgentBench/long_horizon/.../data-00000-of-00001.arrow` | Yes | Yes (10,832 B) | Yes (Arrow) | No |
| `vague_bench/data/train-00000-of-00001.parquet` | Yes | Yes (220,902,219 B) | Yes (Parquet magic `PAR1`) | No |

**Conclusion:** The Arrow and Parquet payloads for IndirectRequests,
SafeAgentBench, and VAGUE are **real data present on disk and tracked in Git**,
not LFS pointers or metadata stubs. The earlier "missing payload" finding was
**incorrect** and is superseded by this verified reconciliation. The
`vague_bench/.cache/huggingface/**/*.metadata` files are HuggingFace download
cache stubs, which likely caused the earlier confusion; the authoritative
parquet exists at `vague_bench/data/train-00000-of-00001.parquet`.

---

## Git tracking summary (`git ls-files data/raw`, 2026-07-10)

Total tracked paths under `data/raw`: **1,939**.

| Entry | Tracked paths | Note |
|---|---:|---|
| `.venv/` | 1,904 | Virtualenv accidentally tracked; not a dataset |
| `SafeAgentBench/` | 12 | 4 Arrow shards + metadata JSON |
| `IndirectRequests/` | 10 | 3 Arrow shards + metadata JSON |
| `codraw-icr-v2/` | 5 | README, PDF, clipmap, 2 TSV |
| `vague_bench/` | 3 | README, `.gitattributes`, parquet |
| gitlinks | 5 | `AmbiK`, `CLARA-Dataset`, `ClariQ`, `TEACh`, `teach_tatc` |

T00 does not untrack, delete, move, or modify any of these files. A separate,
explicit decision is required to `git rm --cached data/raw/.venv/**` and to
convert the ignore policy into actual untracking.

---

## Per-dataset findings

### AmbiK — `data/raw/AmbiK`
- Real data present: `AmbiK_data.csv` (**1,000** records), `ambik_dataset/ambik_test_900.csv` (**900**), `ambik_test_400.csv` (**400**), `ambik_calib_100.csv` (**100**); `ambik_knowno_data/knowno_data.csv` (**300**).
- Formats: CSV, YAML, TXT, PY, IPYNB. No compression.
- Licence file: none found in folder.
- Role: **core training/development**.
- Unverified: mapping of `ambiguity_type` values to project taxonomy (deferred to T01/T03).

### CLARA-Dataset (SaGC) — `data/raw/CLARA-Dataset`
- Real data present: `data/agument.json` (**5,345** top-level records). `data/sample.json` is a small craft template.
- Record shape: `{scene:{floorplan,objects,people}, goal, label, task}`; label semantics `0=clear,1=ambiguous,2=infeasible,3=ignore` per README.
- Licence file: none found.
- Role: **conditional core** (after label verification, T07).
- Unverified: label→route mapping (`TODO_VERIFY_LABEL_MAPPING`).

### ClariQ — `data/raw/ClariQ`
- Real data present (rows excluding header): `train.tsv` 9,176; `dev.tsv` 2,313; `test.tsv` 61; `test_with_labels.tsv` 4,499; `question_bank.tsv` 3,941; `multi_turn_human_generated_data.tsv` 499. Plus qrel files.
- Licence file: none found.
- Role: **auxiliary / optional augmentation** (never robot gold without explicit decision).
- Unverified: unique topic counts (README claims 187 train / 50 dev topics).

### IndirectRequests — `data/raw/IndirectRequests`
- Real Arrow payloads present and tracked (see reconciliation table). Metadata counts: train **246**, validation **272**, test **388** (total **906**).
- Format: HuggingFace Arrow dataset. Empty `license` field in metadata.
- Role: **core training/development**.
- Unverified: row-level schema vs metadata feature list (deferred to T04).

### SafeAgentBench — `data/raw/SafeAgentBench`
- Real Arrow payloads present and tracked. Metadata counts: `abstract` **100**, `unsafe_detailed` **300**, `safe_detailed` **300**, `long_horizon` **50** (total **750**).
- Per-config schemas differ. Empty `license` field in metadata.
- Role: **safety stress test** (challenge-only, separate results).

### codraw-icr-v2 — `data/raw/codraw-icr-v2`
- Real data present: `codraw-icr-v2.tsv` (**8,765** data rows), `codraw-icr-v2_raw.tsv` (**15,300** data rows), `clipmap.json`, `annotation-report.pdf` (present per Git; note: earlier snapshot said PDF missing — Git tracks it).
- Licence: README states CC BY-NC 4.0 and references `license.txt`; `license.txt` not found in folder.
- Role: **clarification benchmark** / conditional context source.

### VAGUE — `data/raw/vague_bench`
- Real parquet payload present and tracked: `data/train-00000-of-00001.parquet` (~221 MB). HF card claims **1,677** examples.
- `.cache/huggingface/**` contains download stub metadata only (not the payload).
- Licence file: none found in folder.
- Role: **conditional core** (text/caption path), pending schema verification (T06).

### TEACh — `data/raw/TEACh`
- Game JSON present: **2,275** `.game.json` (train 1,482; valid_seen 181; valid_unseen 612). `meta_data.tar.gz` archive present; other archives absent. No `games/test/`.
- Licence files present: `DATALICENSE`, `SOFTWARELICENSE`, `IMAGESLICENSE`.
- Role: **exclude** from core per approved plan.

### teach_tatc — `data/raw/teach_tatc`
- Code-only fork; **no episode/game data** present. `download_data.sh` uses `gdown`.
- Licence files present (same family as TEACh).
- Role: **exclude**.

---

## TEACh vs teach_tatc overlap
Not duplicate payloads on disk today: TEACh holds the only local game JSON;
teach_tatc is code-only. Both excluded from core.

## Missing / not blocking
Dynamic-RDMM, RefCOCO, ReferIt3D, CMC, and the manual compound extension are not
present in `data/raw/`; per the approved plan these are not T00 blockers.

## Confirmed vs assumed
- Confirmed: file existence, sizes, magic bytes, Git tracking, and the counts listed above.
- Assumed / deferred to T01–T08: label mappings, unique-ID counts, row-level schema validation, licence terms where no licence file exists.
